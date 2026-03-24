from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


CONTRACT_ARTIFACT_ROOT_ENV_VAR = "PROOF_OF_AUDIT_CONTRACT_ARTIFACT_ROOT"
PACKAGE_ARTIFACT_ROOT = Path(__file__).resolve().parent / "artifacts"
SOURCE_ARTIFACT_ROOT = Path(__file__).resolve().parents[2] / "contracts" / "out"


def resolve_contract_artifact_path(contract_dir: str, artifact_file: str) -> Path:
    checked_paths: list[Path] = []

    configured_root = os.environ.get(CONTRACT_ARTIFACT_ROOT_ENV_VAR)
    if configured_root:
        configured_path = (
            Path(configured_root).expanduser() / contract_dir / artifact_file
        )
        checked_paths.append(configured_path)
        if configured_path.is_file():
            return configured_path

    packaged_path = PACKAGE_ARTIFACT_ROOT / contract_dir / artifact_file
    checked_paths.append(packaged_path)
    if packaged_path.is_file():
        return packaged_path

    source_tree_path = SOURCE_ARTIFACT_ROOT / contract_dir / artifact_file
    checked_paths.append(source_tree_path)
    if source_tree_path.is_file():
        return source_tree_path

    checked = ", ".join(str(path) for path in checked_paths)
    raise FileNotFoundError(
        f"Unable to locate contract artifact '{artifact_file}'. Checked: {checked}"
    )


def load_contract_artifact_json(
    contract_dir: str, artifact_file: str
) -> dict[str, Any]:
    artifact_path = resolve_contract_artifact_path(contract_dir, artifact_file)
    return json.loads(artifact_path.read_text(encoding="utf-8"))
