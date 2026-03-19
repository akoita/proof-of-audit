import subprocess
from pathlib import Path

from proof_of_audit_agent.backends.local_docker import LocalDockerBackend


def test_local_docker_backend_constructs_hardened_command(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "bundle"
    test_path = source_root / "test" / "ChallengeEvidence.t.sol"
    test_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.write_text("contract ChallengeEvidenceTest {}\n", encoding="utf-8")
    captured: dict[str, object] = {}

    def executor(command, **kwargs):  # type: ignore[no-untyped-def]
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, "ok", "")

    backend = LocalDockerBackend(
        image="ghcr.io/foundry-rs/foundry:v1.3.1",
        executor=executor,
        which=lambda binary: f"/usr/bin/{binary}",
    )

    result = backend.execute(
        command=[
            "forge",
            "test",
            "--root",
            str(source_root),
            "--match-path",
            str(test_path),
            "--fork-url",
            "https://rpc.example",
            "--fork-block-number",
            "42",
            "--gas-limit",
            "30000000",
            "--no-ffi",
            "-vv",
        ],
        cwd=source_root,
        env={
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "USER": "proof-of-audit",
            "FOUNDRY_DISABLE_NIGHTLY_WARNING": "1",
            "FOUNDRY_DISABLE_TELEMETRY": "1",
        },
        timeout_seconds=60,
        memory_limit_bytes=512 * 1024 * 1024,
    )

    docker_command = captured["command"]
    kwargs = captured["kwargs"]

    assert result.backend == "docker"
    assert result.isolation_level == "container"
    assert docker_command[:2] == ["docker", "run"]
    assert "--pull" in docker_command
    assert docker_command[docker_command.index("--pull") + 1] == "never"
    assert "--read-only" in docker_command
    assert "--cap-drop=ALL" in docker_command
    assert "--security-opt" in docker_command
    assert "no-new-privileges:true" in docker_command
    assert "--network" in docker_command
    assert docker_command[docker_command.index("--network") + 1] == "bridge"
    assert "--mount" in docker_command
    assert (
        docker_command[docker_command.index("--mount") + 1]
        == f"type=bind,src={source_root.resolve()},dst=/evidence,readonly"
    )
    assert "--tmpfs" in docker_command
    assert docker_command[docker_command.index("--tmpfs") + 1].startswith("/tmp:")
    assert "--memory" in docker_command
    assert docker_command[docker_command.index("--memory") + 1] == f"{512 * 1024 * 1024}b"
    image_index = docker_command.index("ghcr.io/foundry-rs/foundry:v1.3.1")
    assert docker_command[image_index + 1] == "forge"
    assert "--root" in docker_command
    assert docker_command[docker_command.index("--root") + 1] == "/evidence"
    assert "--match-path" in docker_command
    assert (
        docker_command[docker_command.index("--match-path") + 1]
        == "/evidence/test/ChallengeEvidence.t.sol"
    )
    assert "--cache-path" in docker_command
    assert docker_command[docker_command.index("--cache-path") + 1] == "/tmp/forge-cache"
    assert "--out" in docker_command
    assert docker_command[docker_command.index("--out") + 1] == "/tmp/forge-out"
    assert kwargs["timeout"] == 60
    assert kwargs["cwd"] == source_root


def test_local_docker_backend_availability_requires_binary_and_image() -> None:
    assert (
        LocalDockerBackend(
            image="ghcr.io/foundry-rs/foundry:v1.3.1",
            which=lambda binary: None,
        ).is_available()
        is False
    )
    assert (
        LocalDockerBackend(
            image="",
            which=lambda binary: f"/usr/bin/{binary}",
        ).is_available()
        is False
    )
    assert (
        LocalDockerBackend(
            image="ghcr.io/foundry-rs/foundry:v1.3.1",
            which=lambda binary: f"/usr/bin/{binary}",
        ).is_available()
        is True
    )
