from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from typing import Any

import httpx
import pytest
from web3 import HTTPProvider, Web3
from web3.contract import Contract

from proof_of_audit_api.publisher import load_contract_abi


ROOT_DIR = Path(__file__).resolve().parents[3]
STACK_SCRIPT = ROOT_DIR / "scripts" / "run-system-e2e-stack.sh"


@dataclass
class SystemStack:
    api_url: str
    rpc_url: str
    client: httpx.Client
    web3: Web3
    contract: Contract
    config: dict[str, Any]
    fixtures: list[dict[str, Any]]
    log_dir: Path

    def fixture_by_id(self, fixture_id: str) -> dict[str, Any]:
        for fixture in self.fixtures:
            if fixture["id"] == fixture_id:
                return fixture
        raise KeyError(fixture_id)


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


def _collect_logs(log_dir: Path) -> str:
    sections: list[str] = []
    for log_file in sorted(log_dir.glob("*.log")):
        try:
            content = log_file.read_text(encoding="utf-8")
        except FileNotFoundError:
            continue
        sections.append(f"===== {log_file.name} =====\n{content.strip()}\n")
    return "\n".join(sections).strip()


def _start_system_stack(
    tmp_root: Path,
    *,
    env_overrides: dict[str, str] | None = None,
) -> tuple[SystemStack, Callable[[], None]]:
    tmp_root.mkdir(parents=True, exist_ok=True)
    log_dir = tmp_root / "logs"
    data_root = tmp_root / "data"
    log_dir.mkdir()
    anvil_port = _find_free_port()
    api_port = _find_free_port()
    api_url = f"http://127.0.0.1:{api_port}"
    rpc_url = f"http://127.0.0.1:{anvil_port}"
    stack_log_path = log_dir / "stack.log"
    stack_log_handle = stack_log_path.open("w", encoding="utf-8")

    env = os.environ.copy()
    env.update(
        {
            "PYTHON_BIN": env.get("PYTHON_BIN", sys.executable),
            "E2E_DATA_ROOT": str(data_root),
            "E2E_LOG_DIR": str(log_dir),
            "E2E_ANVIL_HOST": "127.0.0.1",
            "E2E_ANVIL_PORT": str(anvil_port),
            "E2E_ANVIL_CHAIN_ID": "31339",
            "E2E_API_HOST": "127.0.0.1",
            "E2E_API_PORT": str(api_port),
            "PROOF_OF_AUDIT_RPC_URL": rpc_url,
        }
    )
    if env_overrides:
        env.update(env_overrides)
    process = subprocess.Popen(
        [str(STACK_SCRIPT)],
        cwd=ROOT_DIR,
        env=env,
        stdout=stack_log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )

    client = httpx.Client(base_url=api_url, timeout=10.0)
    def close() -> None:
        client.close()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=20)
        stack_log_handle.close()
    try:
        deadline = time.monotonic() + 120
        started = False
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(
                    f"system e2e stack exited early with code {process.returncode}\n{_collect_logs(log_dir)}"
                )
            try:
                response = client.get("/health")
            except httpx.HTTPError:
                time.sleep(1)
                continue
            if response.status_code == 200:
                started = True
                break
            time.sleep(1)

        if not started:
            raise RuntimeError(
                f"timed out waiting for the system e2e stack\n{_collect_logs(log_dir)}"
            )

        config = client.get("/config")
        fixtures = client.get("/fixtures")
        config.raise_for_status()
        fixtures.raise_for_status()
        config_payload = config.json()
        fixtures_payload = fixtures.json()["items"]
        web3 = Web3(HTTPProvider(rpc_url))
        contract = web3.eth.contract(
            address=Web3.to_checksum_address(config_payload["contract_address"]),
            abi=load_contract_abi(),
        )
    except Exception:
        close()
        raise

    return (
        SystemStack(
            api_url=api_url,
            rpc_url=rpc_url,
            client=client,
            web3=web3,
            contract=contract,
            config=config_payload,
            fixtures=fixtures_payload,
            log_dir=log_dir,
        ),
        close,
    )


@pytest.fixture(scope="session")
def system_stack(tmp_path_factory: pytest.TempPathFactory) -> Iterator[SystemStack]:
    stack, close = _start_system_stack(tmp_path_factory.mktemp("system-e2e"))
    try:
        yield stack
    finally:
        close()


@pytest.fixture
def system_stack_factory(tmp_path: Path) -> Iterator[Callable[..., SystemStack]]:
    closers: list[Callable[[], None]] = []

    def start(*, env_overrides: dict[str, str] | None = None) -> SystemStack:
        stack_index = len(closers)
        stack, close = _start_system_stack(
            tmp_path / f"stack-{stack_index}",
            env_overrides=env_overrides,
        )
        closers.append(close)
        return stack

    try:
        yield start
    finally:
        for close in reversed(closers):
            close()


@pytest.fixture(scope="session")
def forge_available() -> bool:
    return shutil.which("forge") is not None
