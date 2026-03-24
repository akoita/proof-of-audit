import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from proof_of_audit_api.contract_artifacts import resolve_contract_artifact_path
from proof_of_audit_api.publisher import load_contract_artifact
from proof_of_audit_api.reputation_bridge import load_reputation_bridge_artifact
from proof_of_audit_api.validation_bridge import load_validation_bridge_artifact


class ContractArtifactLoaderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.artifact_root = Path(self.tempdir.name) / "contracts" / "out"
        self._write_artifact(
            "ProofOfAudit.sol",
            "ProofOfAudit.json",
            {
                "abi": [{"name": "publishAudit", "type": "function"}],
                "bytecode": {"object": "0x6000"},
                "contractName": "PackagedProofOfAudit",
            },
        )
        self._write_artifact(
            "ValidationRegistryAdapter.sol",
            "ValidationRegistryAdapter.json",
            {
                "abi": [{"name": "validationRequest", "type": "function"}],
                "contractName": "PackagedValidationRegistryAdapter",
            },
        )
        self._write_artifact(
            "ReputationRegistryAdapter.sol",
            "ReputationRegistryAdapter.json",
            {
                "abi": [{"name": "recordClaim", "type": "function"}],
                "contractName": "PackagedReputationRegistryAdapter",
            },
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _write_artifact(
        self, contract_dir: str, artifact_file: str, payload: dict[str, object]
    ) -> None:
        artifact_path = self.artifact_root / contract_dir / artifact_file
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(json.dumps(payload), encoding="utf-8")

    def test_resolve_contract_artifact_path_falls_back_to_repo_artifacts(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            artifact_path = resolve_contract_artifact_path(
                "ProofOfAudit.sol",
                "ProofOfAudit.json",
            )

        self.assertEqual(artifact_path.name, "ProofOfAudit.json")
        self.assertTrue(artifact_path.is_file())

    def test_loaders_use_configured_artifact_root_for_container_layout(self) -> None:
        with patch.dict(
            os.environ,
            {"PROOF_OF_AUDIT_CONTRACT_ARTIFACT_ROOT": str(self.artifact_root)},
            clear=False,
        ):
            publisher_artifact = load_contract_artifact()
            validation_artifact = load_validation_bridge_artifact()
            reputation_artifact = load_reputation_bridge_artifact()

        self.assertEqual(publisher_artifact["contractName"], "PackagedProofOfAudit")
        self.assertEqual(
            validation_artifact["contractName"],
            "PackagedValidationRegistryAdapter",
        )
        self.assertEqual(
            reputation_artifact["contractName"],
            "PackagedReputationRegistryAdapter",
        )
