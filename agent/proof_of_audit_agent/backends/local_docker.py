from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
from typing import Callable

from proof_of_audit_agent.backends.base import (
    EvidenceExecutionBackend,
    EvidenceExecutionResult,
)


Executor = Callable[..., subprocess.CompletedProcess[str]]
Which = Callable[[str], str | None]

DEFAULT_CONTAINER_WORKDIR = "/evidence"
DEFAULT_CONTAINER_HOME = "/tmp/proof-of-audit-home"
DEFAULT_CONTAINER_CACHE = "/tmp/forge-cache"
DEFAULT_CONTAINER_OUT = "/tmp/forge-out"


class LocalDockerBackend(EvidenceExecutionBackend):
    def __init__(
        self,
        *,
        image: str,
        docker_bin: str = "docker",
        container_executable_name: str = "forge",
        network: str = "bridge",
        cpus: str = "1.0",
        pids_limit: int = 256,
        tmpfs_size_bytes: int = 128 * 1024 * 1024,
        executor: Executor | None = None,
        which: Which | None = None,
    ) -> None:
        self.image = image.strip()
        self.docker_bin = docker_bin
        self.container_executable_name = container_executable_name
        self.network = network
        self.cpus = cpus
        self.pids_limit = pids_limit
        self.tmpfs_size_bytes = tmpfs_size_bytes
        self._executor = executor or subprocess.run
        self._which = which or shutil.which

    @property
    def backend_name(self) -> str:
        return "docker"

    @property
    def isolation_level(self) -> str:
        return "container"

    def is_available(self) -> bool:
        return bool(self.image) and self._which(self.docker_bin) is not None

    def execute(
        self,
        *,
        command: list[str],
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: int,
        memory_limit_bytes: int,
    ) -> EvidenceExecutionResult:
        if not command:
            raise OSError("Executable evidence runner produced an empty command.")
        docker_command = self._build_docker_command(
            command=command,
            cwd=cwd,
            env=env,
            memory_limit_bytes=memory_limit_bytes,
        )
        host_env = {
            "PATH": os.environ.get("PATH", ""),
            "LANG": env.get("LANG", "C.UTF-8"),
            "LC_ALL": env.get("LC_ALL", "C.UTF-8"),
            "HOME": os.environ.get("HOME", str(cwd)),
        }
        for key in (
            "DOCKER_HOST",
            "DOCKER_CONTEXT",
            "DOCKER_CONFIG",
            "DOCKER_TLS_VERIFY",
            "DOCKER_CERT_PATH",
            "XDG_RUNTIME_DIR",
        ):
            value = os.environ.get(key)
            if value:
                host_env[key] = value
        result = self._executor(
            docker_command,
            cwd=cwd,
            env=host_env,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        return EvidenceExecutionResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            backend=self.backend_name,
            isolation_level=self.isolation_level,
        )

    def _build_docker_command(
        self,
        *,
        command: list[str],
        cwd: Path,
        env: dict[str, str],
        memory_limit_bytes: int,
    ) -> list[str]:
        cwd = cwd.resolve()
        translated = [
            self.container_executable_name,
            *[self._translate_path_argument(arg, cwd) for arg in command[1:]],
            "--cache-path",
            DEFAULT_CONTAINER_CACHE,
            "--out",
            DEFAULT_CONTAINER_OUT,
        ]
        container_env = self._container_env(env)
        docker_command = [
            self.docker_bin,
            "run",
            "--rm",
            "--pull",
            "never",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--pids-limit",
            str(self.pids_limit),
            "--cpus",
            self.cpus,
            "--memory",
            f"{memory_limit_bytes}b",
            "--network",
            self.network,
            "--user",
            "65534:65534",
            "--workdir",
            DEFAULT_CONTAINER_WORKDIR,
            "--mount",
            f"type=bind,src={cwd},dst={DEFAULT_CONTAINER_WORKDIR},readonly",
            "--tmpfs",
            f"/tmp:rw,noexec,nosuid,nodev,size={self.tmpfs_size_bytes}",
        ]
        for key, value in container_env.items():
            docker_command.extend(["--env", f"{key}={value}"])
        docker_command.extend([self.image, *translated])
        return docker_command

    def _container_env(self, env: dict[str, str]) -> dict[str, str]:
        return {
            "HOME": DEFAULT_CONTAINER_HOME,
            "USER": env.get("USER", "proof-of-audit"),
            "LANG": env.get("LANG", "C.UTF-8"),
            "LC_ALL": env.get("LC_ALL", "C.UTF-8"),
            "FOUNDRY_DISABLE_NIGHTLY_WARNING": env.get(
                "FOUNDRY_DISABLE_NIGHTLY_WARNING", "1"
            ),
            "FOUNDRY_DISABLE_TELEMETRY": env.get("FOUNDRY_DISABLE_TELEMETRY", "1"),
        }

    def _translate_path_argument(self, argument: str, cwd: Path) -> str:
        path = Path(argument)
        if not path.is_absolute():
            return argument
        try:
            relative = path.resolve().relative_to(cwd)
        except ValueError:
            return argument
        return str(Path(DEFAULT_CONTAINER_WORKDIR) / relative)
