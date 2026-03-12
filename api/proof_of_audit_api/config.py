from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping

DEFAULT_API_ENV_FILE = Path(__file__).resolve().parents[1] / ".env.local"


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


@dataclass(frozen=True)
class ContractConfig:
    network: str
    chain_id: int
    contract_address: str | None
    explorer_base_url: str
    arbiter: str | None
    rpc_url: str | None
    publisher_private_key: str | None
    required_stake_wei: int
    required_challenge_bond_wei: int
    challenge_window_seconds: int

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        env_file: Path | None = None,
    ) -> "ContractConfig":
        if env is None:
            source: dict[str, str] = load_env_file(env_file or DEFAULT_API_ENV_FILE)
            source.update(os.environ)
        else:
            source = dict(env)
        return cls(
            network=source.get("PROOF_OF_AUDIT_NETWORK", "base-sepolia"),
            chain_id=int(source.get("PROOF_OF_AUDIT_CHAIN_ID", "84532")),
            contract_address=source.get("PROOF_OF_AUDIT_CONTRACT_ADDRESS") or None,
            explorer_base_url=source.get(
                "PROOF_OF_AUDIT_EXPLORER_BASE_URL",
                "https://sepolia.basescan.org",
            ).rstrip("/"),
            arbiter=source.get("PROOF_OF_AUDIT_ARBITER") or None,
            rpc_url=source.get("PROOF_OF_AUDIT_RPC_URL")
            or source.get("BASE_SEPOLIA_RPC_URL")
            or None,
            publisher_private_key=source.get("PROOF_OF_AUDIT_PRIVATE_KEY") or None,
            required_stake_wei=int(
                source.get("PROOF_OF_AUDIT_REQUIRED_STAKE_WEI", "10000000000000000")
            ),
            required_challenge_bond_wei=int(
                source.get(
                    "PROOF_OF_AUDIT_REQUIRED_CHALLENGE_BOND_WEI",
                    "5000000000000000",
                )
            ),
            challenge_window_seconds=int(
                source.get("PROOF_OF_AUDIT_CHALLENGE_WINDOW_SECONDS", "86400")
            ),
        )

    @property
    def deployment_ready(self) -> bool:
        return bool(self.contract_address and self.rpc_url)

    def transaction_url(self, tx_hash: str) -> str:
        return f"{self.explorer_base_url}/tx/{tx_hash}"
