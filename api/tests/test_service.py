import tempfile
import unittest
from pathlib import Path
import json

from proof_of_audit_api.config import ContractConfig
from proof_of_audit_api.publisher import OnchainConfigurationError
from proof_of_audit_api.service import AuditService
from helpers import build_onchain_test_context


class AuditServiceTest(unittest.TestCase):
    def test_list_audits_hydrates_legacy_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_root = Path(tmpdir)
            legacy_record = {
                "id": "legacy-audit",
                "contract_address": "0x1000000000000000000000000000000000000001",
                "submitted_by": "legacy-user",
                "status": "draft",
                "created_at": "2026-03-14T10:00:00+00:00",
                "report": {
                    "benchmark_id": "reentrancy-bank",
                    "contract_address": "0x1000000000000000000000000000000000000001",
                    "summary": "Withdraw updates balance after the external call.",
                    "findings": [
                        {
                            "title": "Reentrancy in withdraw()",
                            "severity": "high",
                            "description": "ETH is sent to msg.sender before accounting is updated.",
                            "recommendation": "Apply checks-effects-interactions.",
                            "detector": "pattern.reentrancy",
                        }
                    ],
                    "supported_checks": [
                        "reentrancy",
                        "access_control",
                        "unchecked_external_call",
                    ],
                    "confidence": "high",
                    "report_hash": "legacy-report-hash",
                    "metadata_hash": "legacy-metadata-hash",
                    "max_severity": 3,
                },
                "onchain": None,
                "challenge": None,
            }
            (data_root / "legacy-audit.json").write_text(
                json.dumps(legacy_record, indent=2),
                encoding="utf-8",
            )
            service = AuditService(data_root)

            listed = service.list_audits()

            self.assertEqual(listed[0]["agent"]["id"], "proof-of-audit-auditor")
            self.assertEqual(listed[0]["submission"]["input_kind"], "deployed_address")
            self.assertEqual(listed[0]["report"]["finding_count"], 1)
            self.assertEqual(
                listed[0]["report"]["findings"][0]["finding_id"],
                "reentrancy-bank.reentrancy.reentrancy-in-withdraw",
            )
            self.assertEqual(
                listed[0]["report"]["findings"][0]["category"],
                "reentrancy",
            )
            persisted = json.loads((data_root / "legacy-audit.json").read_text(encoding="utf-8"))
            self.assertIn("submission", persisted)
            self.assertEqual(persisted["report"]["severity_breakdown"]["high"], 1)

    def test_list_audits_returns_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AuditService(Path(tmpdir))
            first = service.create_audit(
                "0x1000000000000000000000000000000000000003",
                submitted_by="first",
            )
            second = service.create_audit(
                "0x1000000000000000000000000000000000000002",
                submitted_by="second",
            )

            listed = service.list_audits()

            self.assertEqual(listed[0]["id"], second["id"])
            self.assertEqual(listed[1]["id"], first["id"])

    def test_create_publish_and_challenge(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            onchain = build_onchain_test_context()
            service = AuditService(
                Path(tmpdir),
                contract_config=onchain.contract_config,
                publisher=onchain.publisher,
                arbiter_client=onchain.arbiter_client,
            )
            created = service.create_audit(
                onchain.web3.eth.accounts[2],
                submitted_by="judge",
            )

            self.assertEqual(created["status"], "draft")
            self.assertEqual(created["agent"]["id"], "proof-of-audit-auditor")
            self.assertEqual(created["report"]["benchmark_id"], "unknown")
            self.assertEqual(created["report"]["finding_count"], 0)

            published = service.publish_audit(created["id"], 10**16, None)
            self.assertEqual(published["status"], "published")
            self.assertEqual(published["onchain"]["agent_identity"], "proof-of-audit-auditor")
            self.assertEqual(published["onchain"]["agent_name"], "Proof-of-Audit Auditor")
            self.assertEqual(published["onchain"]["network"], "eth-tester")
            self.assertEqual(
                published["onchain"]["chain_id"], onchain.contract_config.chain_id
            )
            self.assertEqual(
                published["onchain"]["contract_address"],
                onchain.contract_config.contract_address,
            )
            self.assertTrue(
                published["onchain"]["publish_tx_url"].startswith(
                    "http://127.0.0.1:8545/tx/0x"
                )
            )
            self.assertEqual(published["onchain"]["audit_id"], 1)

            challenged = service.challenge_audit(
                created["id"],
                "ipfs://demo-poc",
                challenger="whitehat",
            )
            self.assertEqual(challenged["status"], "challenged")
            self.assertEqual(challenged["challenge"]["status"], "opened")
            self.assertEqual(
                challenged["challenge"]["verification_status"],
                "verifier_unavailable",
            )
            self.assertEqual(
                challenged["challenge"]["challenger_address"],
                onchain.publisher.account.address,
            )
            self.assertEqual(
                challenged["challenge"]["challenge_bond_wei"],
                onchain.contract_config.required_challenge_bond_wei,
            )
            self.assertTrue(
                challenged["challenge"]["challenge_tx_url"].startswith(
                    "http://127.0.0.1:8545/tx/0x"
                )
            )
            audit_record = onchain.contract.functions.getAudit(1).call()
            self.assertEqual(int(audit_record[10]), 2)
            self.assertEqual(
                int(audit_record[7]),
                onchain.contract_config.required_challenge_bond_wei,
            )
            self.assertEqual(
                onchain.web3.to_checksum_address(audit_record[12]),
                onchain.publisher.account.address,
            )
            self.assertEqual(
                onchain.web3.to_hex(audit_record[13]),
                challenged["challenge"]["challenge_hash"],
            )

            resolved = service.resolve_audit(
                created["id"],
                upheld=True,
                resolved_by="arbiter-operator",
            )
            self.assertEqual(resolved["status"], "resolved")
            self.assertEqual(resolved["challenge"]["status"], "upheld")
            self.assertEqual(resolved["challenge"]["resolution"], "upheld")
            self.assertEqual(
                resolved["challenge"]["beneficiary_address"],
                onchain.web3.to_checksum_address(onchain.contract.functions.getAudit(1).call()[12]),
            )
            self.assertTrue(
                resolved["challenge"]["resolve_tx_url"].startswith(
                    "http://127.0.0.1:8545/tx/0x"
                )
            )
            resolved_record = onchain.contract.functions.getAudit(1).call()
            self.assertEqual(int(resolved_record[10]), 3)
            self.assertEqual(int(resolved_record[11]), 1)

    def test_verified_clean_fixture_challenge_auto_resolves_upheld(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            onchain = build_onchain_test_context()
            service = AuditService(
                Path(tmpdir),
                contract_config=onchain.contract_config,
                publisher=onchain.publisher,
                arbiter_client=onchain.arbiter_client,
            )
            created = service.create_audit(
                "0x1000000000000000000000000000000000000003",
                submitted_by="judge",
            )
            service.publish_audit(created["id"], 10**16, "auditor-agent-v1")

            challenged = service.challenge_audit(
                created["id"],
                "ipfs://clean-vault/missed-reentrancy",
                challenger="whitehat",
            )

            self.assertEqual(challenged["status"], "resolved")
            self.assertEqual(challenged["challenge"]["status"], "upheld")
            self.assertEqual(challenged["challenge"]["resolution"], "upheld")
            self.assertEqual(
                challenged["challenge"]["verification_status"],
                "verified",
            )
            self.assertEqual(
                challenged["challenge"]["resolved_by"],
                "deterministic-verifier",
            )
            resolved_record = onchain.contract.functions.getAudit(1).call()
            self.assertEqual(int(resolved_record[10]), 3)
            self.assertEqual(int(resolved_record[11]), 1)

    def test_verified_report_confirmation_auto_resolves_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            onchain = build_onchain_test_context()
            service = AuditService(
                Path(tmpdir),
                contract_config=onchain.contract_config,
                publisher=onchain.publisher,
                arbiter_client=onchain.arbiter_client,
            )
            created = service.create_audit(
                "0x1000000000000000000000000000000000000001",
                submitted_by="judge",
            )
            service.publish_audit(created["id"], 10**16, "auditor-agent-v1")

            challenged = service.challenge_audit(
                created["id"],
                "ipfs://reentrancy-bank/withdraw-drain",
                challenger="whitehat",
            )

            self.assertEqual(challenged["status"], "resolved")
            self.assertEqual(challenged["challenge"]["status"], "rejected")
            self.assertEqual(challenged["challenge"]["resolution"], "rejected")
            self.assertEqual(
                challenged["challenge"]["verification_status"],
                "verified",
            )
            resolved_record = onchain.contract.functions.getAudit(1).call()
            self.assertEqual(int(resolved_record[10]), 3)
            self.assertEqual(int(resolved_record[11]), 2)

    def test_invalid_evidence_stays_open_for_manual_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            onchain = build_onchain_test_context()
            service = AuditService(
                Path(tmpdir),
                contract_config=onchain.contract_config,
                publisher=onchain.publisher,
                arbiter_client=onchain.arbiter_client,
            )
            created = service.create_audit(
                "0x1000000000000000000000000000000000000003",
                submitted_by="judge",
            )
            service.publish_audit(created["id"], 10**16, "auditor-agent-v1")

            challenged = service.challenge_audit(
                created["id"],
                "ipfs://wrong-proof",
                challenger="whitehat",
            )

            self.assertEqual(challenged["status"], "challenged")
            self.assertEqual(challenged["challenge"]["status"], "opened")
            self.assertEqual(
                challenged["challenge"]["verification_status"],
                "invalid_evidence",
            )

    def test_challenge_requires_publish(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AuditService(Path(tmpdir))
            created = service.create_audit(
                "0x1000000000000000000000000000000000000003",
                submitted_by="judge",
            )

            with self.assertRaisesRegex(
                ValueError, "audit must be published before challenge"
            ):
                service.challenge_audit(
                    created["id"],
                    "ipfs://demo-poc",
                    challenger="whitehat",
                )

    def test_duplicate_challenge_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            onchain = build_onchain_test_context()
            service = AuditService(
                Path(tmpdir),
                contract_config=onchain.contract_config,
                publisher=onchain.publisher,
                arbiter_client=onchain.arbiter_client,
            )
            created = service.create_audit(
                onchain.web3.eth.accounts[2],
                submitted_by="judge",
            )
            service.publish_audit(created["id"], 10**16, "auditor-agent-v1")
            service.challenge_audit(
                created["id"],
                "ipfs://demo-poc",
                challenger="whitehat",
            )

            with self.assertRaisesRegex(ValueError, "already been challenged"):
                service.challenge_audit(
                    created["id"],
                    "ipfs://second-poc",
                    challenger="second-whitehat",
                )

    def test_resolution_requires_challenge(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            onchain = build_onchain_test_context()
            service = AuditService(
                Path(tmpdir),
                contract_config=onchain.contract_config,
                publisher=onchain.publisher,
                arbiter_client=onchain.arbiter_client,
            )
            created = service.create_audit(
                onchain.web3.eth.accounts[2],
                submitted_by="judge",
            )
            service.publish_audit(created["id"], 10**16, "auditor-agent-v1")

            with self.assertRaisesRegex(
                ValueError, "audit must be challenged before resolution"
            ):
                service.resolve_audit(
                    created["id"],
                    upheld=False,
                    resolved_by="arbiter-operator",
                )

    def test_publish_requires_onchain_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AuditService(
                Path(tmpdir),
                contract_config=ContractConfig.from_env({}),
            )
            created = service.create_audit(
                "0x1000000000000000000000000000000000000003",
                submitted_by="judge",
            )

            with self.assertRaisesRegex(
                OnchainConfigurationError,
                "On-chain publishing is not configured",
            ):
                service.publish_audit(created["id"], 10**16, "auditor-agent-v1")

    def test_multi_finding_benchmark_report_is_serialized(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AuditService(Path(tmpdir))

            created = service.create_audit(
                "0x1000000000000000000000000000000000000004",
                submitted_by="judge",
            )

            self.assertEqual(created["report"]["benchmark_id"], "dual-risk-vault")
            self.assertEqual(created["report"]["finding_count"], 2)
            self.assertEqual(created["report"]["severity_breakdown"]["high"], 1)
            self.assertEqual(created["report"]["severity_breakdown"]["medium"], 1)
            self.assertEqual(
                created["report"]["findings"][0]["finding_id"],
                "dual-risk-vault.rotate-owner.missing-access-control",
            )
            self.assertEqual(
                created["report"]["findings"][1]["evidence_uri"],
                "ipfs://dual-risk-vault/emergency-payout-failure",
            )

    def test_lists_demo_fixtures_from_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fixtures_file = Path(tmpdir) / "demo-fixtures.localhost.json"
            fixtures_file.write_text(
                json.dumps(
                    {
                        "fixtures": [
                            {
                                "id": "clean-vault",
                                "label": "Clean Vault",
                                "contract_name": "CleanVault",
                                "entry_contract": "CleanVault",
                                "benchmark_id": "clean-vault",
                                "address": "0x4444000000000000000000000000000000000004",
                                "challenge_proof_uri": "ipfs://clean-vault/missed-reentrancy",
                                "note": "Clean benchmark with medium confidence",
                                "source_path": "demo/contracts/CleanVault.sol",
                            }
                        ]
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            service = AuditService(
                Path(tmpdir),
                contract_config=ContractConfig.from_env(
                    {"PROOF_OF_AUDIT_DEMO_FIXTURES_FILE": str(fixtures_file)}
                ),
            )

            fixtures = service.list_demo_fixtures()

            self.assertEqual(len(fixtures), 1)
            self.assertEqual(fixtures[0]["label"], "Clean Vault")
            self.assertEqual(
                fixtures[0]["address"], "0x4444000000000000000000000000000000000004"
            )
            self.assertEqual(
                fixtures[0]["challenge_proof_uri"],
                "ipfs://clean-vault/missed-reentrancy",
            )


if __name__ == "__main__":
    unittest.main()
