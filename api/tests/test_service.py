from dataclasses import replace
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from web3 import Web3

from proof_of_audit_agent.challenge_verifier import (
    ChallengeVerificationResult,
    EvidenceContext,
)
from proof_of_audit_api.config import ContractConfig
from proof_of_audit_api.publisher import OnchainConfigurationError, OnchainRequestError
from proof_of_audit_api.service import (
    _EIP1967_BEACON_SLOT,
    _EIP1967_IMPLEMENTATION_SLOT,
    AuditService,
)
from helpers import build_onchain_test_context


def service_default_deterministic_verifier():
    from proof_of_audit_agent.challenge_verifier import ProofUriChallengeVerifier

    return ProofUriChallengeVerifier()


class RecordingVerifier:
    def __init__(self, result: ChallengeVerificationResult) -> None:
        self.result = result
        self.last_context: EvidenceContext | None = None

    def verify(self, context: EvidenceContext) -> ChallengeVerificationResult:
        self.last_context = context
        return self.result


class RaisingVerifier:
    def verify(self, context: EvidenceContext) -> ChallengeVerificationResult:
        raise RuntimeError("verifier crashed")


class AuditServiceTest(unittest.TestCase):
    def test_publish_audit_persists_challenge_policy_and_claim_metadata(self) -> None:
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

            published = service.publish_audit(
                created["id"],
                10**16,
                None,
                challenge_policy={
                    "allowed_evidence_types": ["deterministic_fixture"],
                    "min_severity_threshold": "medium",
                    "allow_informational_only": False,
                    "requires_material_incorrectness": True,
                    "admissibility_mode": "strict",
                },
            )

            expected_policy = {
                "policy_version": "challenge-policy/v1",
                "allowed_evidence_types": ["deterministic_fixture"],
                "min_severity_threshold": "medium",
                "allow_informational_only": False,
                "requires_material_incorrectness": True,
                "admissibility_mode": "strict",
            }
            self.assertEqual(published["onchain"]["challenge_policy"], expected_policy)
            validation_document = service.get_validation_request_document(created["id"])
            self.assertIsNotNone(validation_document)
            assert validation_document is not None
            self.assertEqual(validation_document["claim"]["challengePolicy"], expected_policy)
            reputation_document = service.get_reputation_claim_document(created["id"])
            self.assertIsNotNone(reputation_document)
            assert reputation_document is not None
            self.assertEqual(reputation_document["claim"]["challengePolicy"], expected_policy)

    def test_submit_audit_request_claim_binds_draft_audit_to_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            onchain = build_onchain_test_context()
            service = AuditService(
                Path(tmpdir),
                contract_config=onchain.contract_config,
                publisher=onchain.publisher,
                arbiter_client=onchain.arbiter_client,
            )

            request_record = service.create_audit_request(
                contract_address=onchain.web3.eth.accounts[3],
                bounty_wei=2 * 10**17,
                response_window_seconds=3600,
                submitted_by="market-user",
            )
            draft = service.create_audit(
                onchain.web3.eth.accounts[3],
                submitted_by="auditor",
            )

            published = service.submit_audit_request_claim(
                request_record["request_id"],
                audit_id=draft["id"],
                stake_wei=10**16,
            )

            self.assertEqual(published["status"], "published")
            self.assertEqual(published["onchain"]["request_id"], 1)
            self.assertEqual(published["onchain"]["request_claim_id"], 1)
            self.assertEqual(published["onchain"]["claim_state"], "submitted")
            claims = service.list_audit_request_claims(request_record["request_id"])
            self.assertEqual(len(claims), 1)
            self.assertEqual(claims[0]["claim_id"], "1")
            self.assertEqual(claims[0]["audit_id"], draft["id"])

            duplicate_draft = service.create_audit(
                onchain.web3.eth.accounts[3],
                submitted_by="auditor-duplicate",
            )
            with self.assertRaises(OnchainRequestError):
                service.submit_audit_request_claim(
                    request_record["request_id"],
                    audit_id=duplicate_draft["id"],
                    stake_wei=10**16,
                )

    def test_submit_audit_request_claim_persists_challenge_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            onchain = build_onchain_test_context()
            service = AuditService(
                Path(tmpdir),
                contract_config=onchain.contract_config,
                publisher=onchain.publisher,
                arbiter_client=onchain.arbiter_client,
            )

            request_record = service.create_audit_request(
                contract_address=onchain.web3.eth.accounts[3],
                bounty_wei=2 * 10**17,
                response_window_seconds=3600,
                submitted_by="market-user",
            )
            draft = service.create_audit(
                onchain.web3.eth.accounts[3],
                submitted_by="auditor",
            )

            published = service.submit_audit_request_claim(
                request_record["request_id"],
                audit_id=draft["id"],
                stake_wei=10**16,
                challenge_policy={
                    "allowed_evidence_types": ["executable_test", "deterministic_fixture"],
                    "min_severity_threshold": "high",
                    "allow_informational_only": False,
                },
            )

            self.assertEqual(
                published["onchain"]["challenge_policy"]["min_severity_threshold"],
                "high",
            )
            self.assertFalse(
                published["onchain"]["challenge_policy"]["allow_informational_only"]
            )
            claims = service.list_audit_request_claims(request_record["request_id"])
            self.assertEqual(len(claims), 1)
            self.assertEqual(
                claims[0]["challenge_policy"]["allowed_evidence_types"],
                ["deterministic_fixture", "executable_test"],
            )
            self.assertEqual(
                claims[0]["challenge_policy"]["min_severity_threshold"],
                "high",
            )

    def test_request_settlement_syncs_to_request_and_claim_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            onchain = build_onchain_test_context(protocol_fee_bps=500)
            service = AuditService(
                Path(tmpdir),
                contract_config=onchain.contract_config,
                publisher=onchain.publisher,
                arbiter_client=onchain.arbiter_client,
            )

            request_record = service.create_audit_request(
                contract_address=onchain.web3.eth.accounts[3],
                bounty_wei=2 * 10**17,
                response_window_seconds=3600,
                submitted_by="market-user",
            )
            draft = service.create_audit(
                onchain.web3.eth.accounts[3],
                submitted_by="auditor",
            )
            published = service.submit_audit_request_claim(
                request_record["request_id"],
                audit_id=draft["id"],
                stake_wei=10**16,
            )

            tester = onchain.web3.provider.ethereum_tester
            latest = tester.get_block_by_number("latest")
            tester.time_travel(int(latest["timestamp"]) + 86401)
            tester.mine_block()

            onchain.publisher.classify_audit_request_claims(request_id=1, max_claims=1)
            onchain.publisher.finalize_audit_request_settlement(request_id=1)
            onchain.publisher.withdraw_audit_request_claim_settlement(claim_id=1)

            refreshed_request = service.get_audit_request(request_record["request_id"])
            self.assertIsNotNone(refreshed_request)
            assert refreshed_request is not None
            self.assertTrue(refreshed_request["settlement_finalized"])
            self.assertEqual(refreshed_request["protocol_fee_wei"], 10**16)
            self.assertEqual(refreshed_request["classified_claim_count"], 1)
            self.assertEqual(refreshed_request["eligible_claim_count"], 1)
            self.assertEqual(refreshed_request["claimant_withdrawn_count"], 1)
            self.assertEqual(refreshed_request["eligible_stake_wei"], 10**16)
            self.assertEqual(refreshed_request["distributable_bounty_wei"], 19 * 10**16)
            self.assertTrue(refreshed_request["requester_refund_available"])
            self.assertEqual(refreshed_request["requester_refund_wei"], 0)

            claims = service.list_audit_request_claims(request_record["request_id"])
            self.assertEqual(len(claims), 1)
            self.assertEqual(claims[0]["claim_id"], str(published["onchain"]["request_claim_id"]))
            self.assertTrue(claims[0]["eligible_for_bounty"])
            self.assertTrue(claims[0]["settlement_withdrawn"])
            self.assertEqual(claims[0]["bounty_share_wei"], 19 * 10**16)
            self.assertEqual(claims[0]["settlement_payout_wei"], 20 * 10**16)

    def test_cross_auditor_request_claim_challenge_uses_verifier_and_slashes_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            onchain = build_onchain_test_context()
            primary_service = AuditService(
                Path(tmpdir),
                contract_config=onchain.contract_config,
                publisher=onchain.publisher,
                arbiter_client=onchain.arbiter_client,
            )
            request_record = primary_service.create_audit_request(
                contract_address=onchain.web3.eth.accounts[3],
                bounty_wei=2 * 10**17,
                response_window_seconds=3600,
                submitted_by="market-user",
            )
            draft = primary_service.create_audit(
                onchain.web3.eth.accounts[3],
                submitted_by="auditor",
            )
            published = primary_service.submit_audit_request_claim(
                request_record["request_id"],
                audit_id=draft["id"],
                stake_wei=10**16,
            )

            verifier = RecordingVerifier(
                ChallengeVerificationResult(
                    verifier="cross-auditor-verifier-v1",
                    status="verified",
                    summary="competing auditor produced a valid contradiction",
                    detail="the competing claim establishes a material disagreement",
                    resolution="upheld",
                    advisory_only=False,
                )
            )
            challenger_service = AuditService(
                Path(tmpdir),
                contract_config=onchain.secondary_contract_config,
                publisher=onchain.secondary_publisher,
                arbiter_client=onchain.arbiter_client,
                challenge_verifiers={"deterministic_fixture": verifier},
            )

            challenged = challenger_service.challenge_audit(
                published["id"],
                "ipfs://competing-auditor/disagreement-proof",
                challenger="competing-auditor",
            )

            self.assertIsNotNone(verifier.last_context)
            self.assertEqual(challenged["status"], "resolved")
            self.assertEqual(challenged["challenge"]["resolution"], "upheld")
            self.assertEqual(challenged["challenge"]["resolution_path"], "deterministic")
            self.assertEqual(
                challenged["challenge"]["challenger_address"],
                onchain.secondary_publisher.account.address,
            )
            self.assertEqual(challenged["onchain"]["request_claim_id"], 1)
            self.assertEqual(challenged["onchain"]["claim_state"], "slashed")
            claims = challenger_service.list_audit_request_claims(request_record["request_id"])
            self.assertEqual(claims[0]["claim_state"], "slashed")

    def test_request_claim_challenge_policy_blocks_inadmissible_upheld_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            onchain = build_onchain_test_context()
            primary_service = AuditService(
                Path(tmpdir),
                contract_config=onchain.contract_config,
                publisher=onchain.publisher,
                arbiter_client=onchain.arbiter_client,
            )
            request_record = primary_service.create_audit_request(
                contract_address=onchain.web3.eth.accounts[3],
                bounty_wei=2 * 10**17,
                response_window_seconds=3600,
                submitted_by="market-user",
            )
            draft = primary_service.create_audit(
                onchain.web3.eth.accounts[3],
                submitted_by="auditor",
            )
            published = primary_service.submit_audit_request_claim(
                request_record["request_id"],
                audit_id=draft["id"],
                stake_wei=10**16,
                challenge_policy={"admissibility_mode": "strict"},
            )

            challenger_service = AuditService(
                Path(tmpdir),
                contract_config=onchain.secondary_contract_config,
                publisher=onchain.secondary_publisher,
                arbiter_client=onchain.arbiter_client,
            )

            challenged = challenger_service.challenge_audit(
                published["id"],
                "ipfs://competing-auditor/manual-proof",
                challenger="competing-auditor",
            )

            self.assertEqual(challenged["status"], "challenged")
            self.assertEqual(
                challenged["challenge"]["policy_admissibility_status"],
                "inadmissible_policy_scope",
            )
            with self.assertRaisesRegex(
                ValueError, "inadmissible challenges cannot be upheld"
            ):
                challenger_service.resolve_audit(
                    published["id"],
                    upheld=True,
                    resolved_by="arbiter-operator",
                )

    def test_create_audit_request_persists_and_syncs_onchain_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            onchain = build_onchain_test_context()
            service = AuditService(
                Path(tmpdir),
                contract_config=onchain.contract_config,
                publisher=onchain.publisher,
                arbiter_client=onchain.arbiter_client,
            )

            created = service.create_audit_request(
                contract_address=onchain.web3.eth.accounts[3],
                bounty_wei=2 * 10**17,
                response_window_seconds=3600,
                filters={
                    "minimum_stake_wei": 10**16,
                    "whitelist_mode": "allowlist",
                    "allowed_service_ids": ["proof-of-audit-auditor"],
                    "required_identity_registry": onchain.contract_config.auditor_agent_registry,
                    "required_identity_agent_id": 1,
                },
                submitted_by="market-user",
            )

            self.assertEqual(created["request_id"], "1")
            self.assertEqual(created["status"], "open")
            self.assertEqual(
                created["contract_address"],
                onchain.web3.eth.accounts[3].lower(),
            )
            self.assertEqual(created["bounty_wei"], 2 * 10**17)
            self.assertEqual(created["claim_count"], 0)
            self.assertEqual(created["filters"]["whitelist_mode"], "allowlist")
            self.assertEqual(
                created["requester"],
                onchain.publisher.account.address.lower(),
            )
            self.assertTrue(str(created["request_tx_hash"]).startswith("0x"))
            self.assertEqual(
                created["filters"]["required_identity_registry"],
                onchain.contract_config.auditor_agent_registry.lower(),
            )
            self.assertEqual(created["filters"]["required_identity_agent_id"], 1)
            self.assertEqual(
                created["metadata"]["allowlisted_auditor_addresses"],
                [onchain.publisher.account.address.lower()],
            )
            self.assertEqual(
                created["metadata"]["onchain_eligibility"][
                    "allowlisted_auditor_addresses"
                ],
                [onchain.publisher.account.address.lower()],
            )

            tester = onchain.web3.provider.ethereum_tester
            latest = tester.get_block_by_number("latest")
            tester.time_travel(int(latest["timestamp"]) + 3601)
            tester.mine_block()

            refreshed = service.get_audit_request("1")

            self.assertIsNotNone(refreshed)
            assert refreshed is not None
            self.assertEqual(refreshed["status"], "closed")
            self.assertEqual(
                refreshed["metadata"]["onchain_eligibility"]["minimum_stake_wei"],
                10**16,
            )

    def test_create_audit_request_resolves_required_identity_service_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            onchain = build_onchain_test_context()
            service = AuditService(
                Path(tmpdir),
                contract_config=onchain.contract_config,
                publisher=onchain.publisher,
                arbiter_client=onchain.arbiter_client,
            )

            created = service.create_audit_request(
                contract_address=onchain.web3.eth.accounts[3],
                bounty_wei=2 * 10**17,
                response_window_seconds=3600,
                filters={
                    "required_identity_service_id": "proof-of-audit-auditor",
                },
                submitted_by="market-user",
            )

            self.assertEqual(
                created["filters"]["required_identity_registry"],
                onchain.contract_config.auditor_agent_registry.lower(),
            )
            self.assertEqual(created["filters"]["required_identity_agent_id"], 1)

    def test_predeployed_testnet_fixture_addresses_require_live_auditor(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AuditService(Path(tmpdir))

            with self.assertRaisesRegex(ValueError, "use live hosted agent-forge analysis"):
                service.create_audit(
                    "0xEbB43aa379270bcBbffDf33656AC37eBD7C81A11",
                    submitted_by="testnet-user",
                )

    def test_local_fixture_addresses_trim_contract_address(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            local_config = replace(ContractConfig.from_env({}), network="anvil-local")
            service = AuditService(Path(tmpdir), contract_config=local_config)

            created = service.create_audit(
                " 0xEbB43aa379270bcBbffDf33656AC37eBD7C81A11 ",
                submitted_by="testnet-user",
            )

            self.assertEqual(
                created["contract_address"],
                "0xebb43aa379270bcbbffdf33656ac37ebd7c81a11",
            )
            self.assertEqual(created["report"]["benchmark_id"], "reentrancy-bank")
            self.assertEqual(created["report"]["finding_count"], 1)

    def test_unknown_real_testnet_deployed_addresses_require_live_auditor(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AuditService(Path(tmpdir))

            with self.assertRaisesRegex(ValueError, "use live hosted agent-forge analysis"):
                service.create_audit(
                    "0x1234000000000000000000000000000000009876",
                    submitted_by="testnet-user",
                )

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
            self.assertEqual(
                listed[0]["target_key"],
                "0x1000000000000000000000000000000000000001",
            )
            self.assertEqual(
                listed[0]["target_auditor_key"],
                "0x1000000000000000000000000000000000000001::proof-of-audit-auditor",
            )
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
            hydrated = service.get_audit("legacy-audit")
            self.assertIsNotNone(hydrated)
            self.assertIn("submission", hydrated)
            self.assertEqual(hydrated["report"]["severity_breakdown"]["high"], 1)
            self.assertEqual(
                hydrated["report"]["normalized_findings"][0]["schema_version"],
                "normalized-audit-finding/v1",
            )
            self.assertIn(
                "reentrancy",
                hydrated["report"]["normalized_findings"][0]["vulnerability_classes"],
            )

    def test_list_audits_returns_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            local_config = replace(ContractConfig.from_env({}), network="anvil-local")
            service = AuditService(Path(tmpdir), contract_config=local_config)
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

    def test_list_target_claims_filters_by_normalized_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            local_config = replace(ContractConfig.from_env({}), network="anvil-local")
            service = AuditService(Path(tmpdir), contract_config=local_config)
            matching_first = service.create_audit(
                "0x1000000000000000000000000000000000000003",
                submitted_by="first",
            )
            service.create_audit(
                "0x1000000000000000000000000000000000000004",
                submitted_by="other",
            )
            matching_second = service.create_audit(
                "0x1000000000000000000000000000000000000003",
                submitted_by="second",
            )

            listed = service.list_target_claims(
                "0x1000000000000000000000000000000000000003"
            )

            self.assertEqual([record["id"] for record in listed], [
                matching_second["id"],
                matching_first["id"],
            ])
            self.assertTrue(
                all(
                    record["target_auditor_key"]
                    == "0x1000000000000000000000000000000000000003::proof-of-audit-auditor"
                    for record in listed
                )
            )

    def test_build_target_comparison_summarizes_claim_states(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            onchain = build_onchain_test_context()
            service = AuditService(
                Path(tmpdir),
                contract_config=onchain.contract_config,
                publisher=onchain.publisher,
                arbiter_client=onchain.arbiter_client,
                validation_bridge=onchain.validation_bridge,
                reputation_bridge=onchain.reputation_bridge,
            )
            published = service.create_audit(
                "0x1000000000000000000000000000000000000001",
                submitted_by="published",
            )
            service.publish_audit(published["id"], 10**16, None)

            challenged = service.create_audit(
                "0x1000000000000000000000000000000000000001",
                submitted_by="challenged",
            )
            service.publish_audit(challenged["id"], 10**16, None)
            service.challenge_audit(challenged["id"], "ipfs://wrong-proof", "whitehat")

            draft = service.create_audit(
                "0x1000000000000000000000000000000000000001",
                submitted_by="draft",
            )

            comparison = service.build_target_comparison(
                "0x1000000000000000000000000000000000000001"
            )

            self.assertEqual(comparison["target_key"], draft["contract_address"])
            self.assertEqual(comparison["summary"]["claim_count"], 3)
            self.assertEqual(comparison["summary"]["published_count"], 1)
            self.assertEqual(comparison["summary"]["challenged_count"], 1)
            self.assertEqual(comparison["summary"]["resolved_count"], 0)
            self.assertGreaterEqual(comparison["summary"]["max_severity"], 0)
            self.assertEqual(
                comparison["items"][0]["agent"]["reputation"]["resolved_challenge_count"],
                0,
            )

    def test_builds_explainable_auditor_reputation_from_resolved_challenges(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            onchain = build_onchain_test_context()
            service = AuditService(
                Path(tmpdir),
                contract_config=onchain.contract_config,
                publisher=onchain.publisher,
                arbiter_client=onchain.arbiter_client,
                validation_bridge=onchain.validation_bridge,
                reputation_bridge=onchain.reputation_bridge,
            )

            first = service.create_audit(
                "0x1000000000000000000000000000000000000001",
                submitted_by="resolved-rejected",
            )
            service.publish_audit(first["id"], 10**16, None)
            service.challenge_audit(
                first["id"],
                "ipfs://reentrancy-bank/withdraw-drain",
                "whitehat-one",
            )
            service.resolve_audit(
                first["id"],
                upheld=False,
                resolved_by="arbiter-one",
            )

            second = service.create_audit(
                "0x1000000000000000000000000000000000000003",
                submitted_by="resolved-upheld",
            )
            service.publish_audit(second["id"], 10**16, None)
            service.challenge_audit(
                second["id"],
                "ipfs://clean-vault/missed-reentrancy",
                "whitehat-two",
            )
            service.resolve_audit(
                second["id"],
                upheld=True,
                resolved_by="arbiter-two",
            )

            all_audits = service.list_audits()
            reputation = all_audits[0]["agent"]["reputation"]

            self.assertEqual(reputation["resolved_challenge_count"], 2)
            self.assertEqual(reputation["challenge_rejected_count"], 1)
            self.assertEqual(reputation["challenge_upheld_count"], 1)
            self.assertEqual(reputation["admissible_resolved_challenge_count"], 2)
            self.assertEqual(reputation["admissible_challenge_rejected_count"], 1)
            self.assertEqual(reputation["admissible_challenge_upheld_count"], 1)
            self.assertEqual(reputation["inadmissible_challenge_count"], 0)
            self.assertEqual(reputation["challenge_openness_score"], 100)
            self.assertEqual(reputation["challenge_openness_band"], "open")
            self.assertEqual(reputation["challenge_accuracy_score"], 50)
            self.assertEqual(reputation["challenge_accuracy_band"], "mixed")
            self.assertEqual(reputation["score"], 68)
            self.assertEqual(reputation["band"], "mixed")
            self.assertIn("challenge_openness_score", reputation["formula"])
            self.assertIn(
                "admissible_challenge_rejected_count",
                reputation["challenge_accuracy_formula"],
            )

    def test_inadmissible_challenges_are_tracked_separately_from_accuracy(self) -> None:
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
            service.publish_audit(
                created["id"],
                10**16,
                None,
                challenge_policy={"admissibility_mode": "strict"},
            )
            service.challenge_audit(
                created["id"],
                "ipfs://reentrancy-bank/withdraw-drain",
                challenger="whitehat",
            )
            service.resolve_audit(
                created["id"],
                upheld=False,
                resolved_by="arbiter-operator",
            )

            reputation = service.list_audits()[0]["agent"]["reputation"]

            self.assertEqual(reputation["resolved_challenge_count"], 1)
            self.assertEqual(reputation["challenge_rejected_count"], 1)
            self.assertEqual(reputation["inadmissible_challenge_count"], 1)
            self.assertEqual(reputation["admissible_resolved_challenge_count"], 0)
            self.assertEqual(reputation["admissible_challenge_rejected_count"], 0)
            self.assertEqual(reputation["challenge_accuracy_score"], 50)
            self.assertEqual(reputation["challenge_accuracy_band"], "provisional")
            self.assertEqual(reputation["challenge_openness_score"], 91)
            self.assertEqual(reputation["challenge_openness_band"], "open")
            self.assertEqual(reputation["score"], 64)
            self.assertEqual(reputation["band"], "mixed")

    def test_create_publish_and_challenge(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            onchain = build_onchain_test_context()
            service = AuditService(
                Path(tmpdir),
                contract_config=onchain.contract_config,
                publisher=onchain.publisher,
                arbiter_client=onchain.arbiter_client,
                validation_bridge=onchain.validation_bridge,
                reputation_bridge=onchain.reputation_bridge,
            )
            created = service.create_audit(
                onchain.web3.eth.accounts[2],
                submitted_by="judge",
            )

            self.assertEqual(created["status"], "draft")
            self.assertEqual(created["agent"]["id"], "proof-of-audit-auditor")
            self.assertEqual(created["report"]["benchmark_id"], "unknown")
            self.assertEqual(created["report"]["finding_count"], 0)
            self.assertIsInstance(created["submission"]["snapshot_block_number"], int)
            self.assertTrue(
                str(created["submission"]["snapshot_block_hash"]).startswith("0x")
            )
            self.assertTrue(
                str(created["submission"]["target_code_hash_at_snapshot"]).startswith(
                    "0x"
                )
            )
            self.assertEqual(
                created["submission"]["proxy_resolution_status"],
                "direct_target",
            )
            self.assertIsNone(created["submission"]["proxy_kind"])
            self.assertIsNone(
                created["submission"]["implementation_address_at_snapshot"]
            )

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
            self.assertEqual(
                published["onchain"]["snapshot_block_number"],
                created["submission"]["snapshot_block_number"],
            )
            self.assertEqual(
                published["onchain"]["snapshot_block_hash"],
                created["submission"]["snapshot_block_hash"],
            )
            self.assertEqual(
                published["onchain"]["target_code_hash_at_snapshot"],
                created["submission"]["target_code_hash_at_snapshot"],
            )
            self.assertEqual(
                published["onchain"]["proxy_resolution_status"],
                "direct_target",
            )
            self.assertIsNone(published["onchain"]["proxy_kind"])
            self.assertIsNone(
                published["onchain"]["implementation_address_at_snapshot"]
            )
            self.assertTrue(
                published["onchain"]["publish_tx_url"].startswith(
                    "http://127.0.0.1:8545/tx/0x"
                )
            )
            self.assertEqual(published["onchain"]["audit_id"], 1)
            self.assertEqual(published["validation"]["status"], "requested")
            self.assertEqual(
                published["validation"]["registry_address"],
                onchain.validation_registry.address,
            )
            self.assertEqual(published["validation"]["agent_id"], 1)
            self.assertEqual(
                published["validation"]["validator_address"],
                onchain.contract_config.validator_address,
            )
            self.assertTrue(
                published["validation"]["request_uri"].endswith(
                    f"/audits/{created['id']}/validation/request"
                )
            )
            self.assertTrue(published["validation"]["request_tx_hash"].startswith("0x"))
            self.assertEqual(published["reputation_trail"]["status"], "claim_recorded")
            self.assertEqual(
                published["reputation_trail"]["registry_address"],
                onchain.reputation_registry.address,
            )
            self.assertEqual(published["reputation_trail"]["agent_id"], 1)
            self.assertTrue(
                published["reputation_trail"]["claim_uri"].endswith(
                    f"/audits/{created['id']}/reputation/claim"
                )
            )
            self.assertTrue(published["reputation_trail"]["claim_tx_hash"].startswith("0x"))
            validation_requests = onchain.validation_registry.functions.getAgentValidations(1).call()
            self.assertEqual(len(validation_requests), 1)
            self.assertEqual(
                onchain.web3.to_hex(validation_requests[0]),
                published["validation"]["request_hash"],
            )
            reputation_claims = onchain.reputation_registry.functions.getAgentClaims(1).call()
            self.assertEqual(len(reputation_claims), 1)
            self.assertEqual(
                onchain.web3.to_hex(reputation_claims[0]),
                published["reputation_trail"]["claim_hash"],
            )
            validation_document = service.get_validation_request_document(created["id"])
            self.assertIsNotNone(validation_document)
            assert validation_document is not None
            self.assertEqual(
                validation_document["claim"]["snapshotBlockNumber"],
                created["submission"]["snapshot_block_number"],
            )
            self.assertEqual(
                validation_document["claim"]["snapshotBlockHash"],
                created["submission"]["snapshot_block_hash"],
            )
            self.assertEqual(
                validation_document["claim"]["proxyResolutionStatus"],
                "direct_target",
            )
            reputation_document = service.get_reputation_claim_document(created["id"])
            self.assertIsNotNone(reputation_document)
            assert reputation_document is not None
            self.assertEqual(
                reputation_document["claim"]["snapshotBlockNumber"],
                created["submission"]["snapshot_block_number"],
            )
            self.assertEqual(
                reputation_document["claim"]["targetCodeHashAtSnapshot"],
                created["submission"]["target_code_hash_at_snapshot"],
            )
            self.assertEqual(
                reputation_document["claim"]["proxyResolutionStatus"],
                "direct_target",
            )

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
                challenged["challenge"]["evidence_hash"],
            )
            self.assertEqual(
                challenged["challenge"]["challenge_hash"],
                challenged["challenge"]["evidence_hash"],
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
            self.assertEqual(resolved["validation"]["status"], "responded")
            self.assertEqual(resolved["validation"]["response"], 0)
            self.assertEqual(resolved["validation"]["response_tag"], "claim-refuted")
            self.assertEqual(resolved["validation"]["linked_resolution"], "upheld")
            self.assertTrue(resolved["validation"]["response_tx_hash"].startswith("0x"))
            self.assertEqual(
                resolved["reputation_trail"]["status"],
                "resolution_recorded",
            )
            self.assertFalse(resolved["reputation_trail"]["claim_confirmed"])
            self.assertEqual(
                resolved["reputation_trail"]["linked_resolution"],
                "upheld",
            )
            self.assertTrue(
                resolved["reputation_trail"]["resolution_tx_hash"].startswith("0x")
            )
            validation_status = onchain.validation_registry.functions.getValidationStatus(
                resolved["validation"]["request_hash"]
            ).call()
            self.assertEqual(int(validation_status[2]), 0)
            self.assertEqual(validation_status[4], "claim-refuted")
            onchain_reputation = onchain.reputation_registry.functions.getReputation(1).call()
            self.assertEqual(int(onchain_reputation[0]), 1)
            self.assertEqual(int(onchain_reputation[1]), 1)
            self.assertEqual(int(onchain_reputation[3]), 1)
            self.assertEqual(int(onchain_reputation[6]), 0)

    def test_publish_audit_prefers_public_api_base_url_for_validation_and_reputation_uris(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            onchain = build_onchain_test_context()
            contract_config = replace(
                onchain.contract_config,
                auditor_public_api_base_url="https://api.proof-of-audit.example.invalid",
            )
            service = AuditService(
                Path(tmpdir) / "public-api-seed-data",
                contract_config=contract_config,
                publisher=onchain.publisher,
                arbiter_client=onchain.arbiter_client,
                validation_bridge=onchain.validation_bridge,
                reputation_bridge=onchain.reputation_bridge,
            )

            created = service.create_audit(
                onchain.web3.eth.accounts[2],
                submitted_by="judge",
            )
            published = service.publish_audit(created["id"], 10**16, None)

            self.assertEqual(
                published["validation"]["request_uri"],
                f"https://api.proof-of-audit.example.invalid/audits/{created['id']}/validation/request",
            )
            self.assertEqual(
                published["reputation_trail"]["claim_uri"],
                f"https://api.proof-of-audit.example.invalid/audits/{created['id']}/reputation/claim",
            )

    def test_challenger_feed_tracks_published_opened_and_resolved_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            onchain = build_onchain_test_context()
            service = AuditService(
                Path(tmpdir),
                contract_config=onchain.contract_config,
                publisher=onchain.publisher,
                arbiter_client=onchain.arbiter_client,
                validation_bridge=onchain.validation_bridge,
                reputation_bridge=onchain.reputation_bridge,
            )
            created = service.create_audit(
                "0x1000000000000000000000000000000000000001",
                submitted_by="judge",
            )
            published = service.publish_audit(created["id"], 10**16, None)
            challenged = service.challenge_audit(
                created["id"],
                "ipfs://demo-poc",
                challenger="whitehat",
            )
            resolved = service.resolve_audit(
                created["id"],
                upheld=False,
                resolved_by="arbiter-operator",
            )

            events = service.list_challenger_events()

            self.assertEqual(
                [item["event_kind"] for item in events[:3]],
                ["challenge_resolved", "challenge_opened", "audit_published"],
            )
            latest = events[0]
            self.assertEqual(latest["audit_id"], created["id"])
            self.assertEqual(latest["service_id"], "proof-of-audit-auditor")
            self.assertEqual(latest["auditor_id"], "proof-of-audit-auditor")
            self.assertEqual(
                latest["published_audit_id"],
                published["onchain"]["audit_id"],
            )
            self.assertEqual(
                latest["challenge_tx_hash"],
                challenged["challenge"]["challenge_tx_hash"],
            )
            self.assertEqual(
                latest["resolve_tx_hash"],
                resolved["challenge"]["resolve_tx_hash"],
            )
            self.assertEqual(latest["current_state"], "resolved")
            self.assertEqual(latest["resolution"], "rejected")
            self.assertIsNotNone(latest["challenge_window_end"])

    def test_plain_proof_uri_challenge_stays_on_manual_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            onchain = build_onchain_test_context()
            service = AuditService(
                Path(tmpdir),
                contract_config=onchain.contract_config,
                publisher=onchain.publisher,
                arbiter_client=onchain.arbiter_client,
                validation_bridge=onchain.validation_bridge,
                reputation_bridge=onchain.reputation_bridge,
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

            self.assertEqual(challenged["status"], "challenged")
            self.assertEqual(challenged["challenge"]["status"], "opened")
            self.assertIsNone(challenged["challenge"].get("resolution"))
            self.assertEqual(
                challenged["challenge"]["verification_status"],
                "verifier_unavailable",
            )
            self.assertEqual(
                challenged["challenge"]["verification_dossier"]["schema_version"],
                "challenge-verifier-dossier/v1",
            )
            self.assertEqual(
                challenged["challenge"]["verification_dossier"]["policy"]["status"],
                "manual_review_required",
            )
            self.assertEqual(
                challenged["challenge"]["resolution_path"],
                "manual_fallback",
            )
            self.assertIsNone(challenged["validation"]["response"])
            self.assertIsNone(challenged["reputation_trail"]["claim_confirmed"])
            challenged_record = onchain.contract.functions.getAudit(1).call()
            self.assertEqual(int(challenged_record[10]), 2)
            self.assertEqual(int(challenged_record[11]), 0)

    def test_strict_challenge_policy_marks_plain_proof_inadmissible(self) -> None:
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
            service.publish_audit(
                created["id"],
                10**16,
                "auditor-agent-v1",
                challenge_policy={"admissibility_mode": "strict"},
            )

            challenged = service.challenge_audit(
                created["id"],
                "ipfs://clean-vault/missed-reentrancy",
                challenger="whitehat",
            )

            self.assertEqual(challenged["status"], "challenged")
            self.assertEqual(
                challenged["challenge"]["verification_status"],
                "inadmissible_policy_scope",
            )
            self.assertEqual(
                challenged["challenge"]["policy_admissibility_status"],
                "inadmissible_policy_scope",
            )
            self.assertEqual(
                challenged["challenge"]["verification_dossier"]["policy"][
                    "admissibility_status"
                ],
                "inadmissible_policy_scope",
            )
            self.assertEqual(
                challenged["challenge"]["verification_dossier"]["policy"][
                    "effective_policy"
                ]["admissibility_mode"],
                "strict",
            )
            with self.assertRaisesRegex(
                ValueError, "inadmissible challenges cannot be upheld"
            ):
                service.resolve_audit(
                    created["id"],
                    upheld=True,
                    resolved_by="arbiter-operator",
                )

            resolved = service.resolve_audit(
                created["id"],
                upheld=False,
                resolved_by="arbiter-operator",
            )
            self.assertEqual(resolved["status"], "resolved")
            self.assertEqual(resolved["challenge"]["status"], "rejected")

    def test_disallowed_evidence_type_is_inadmissible_without_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            onchain = build_onchain_test_context()
            evidence_path = Path(tmpdir) / "ChallengeEvidence.t.sol"
            evidence_path.write_text(
                "contract ChallengeEvidenceTest {}\n",
                encoding="utf-8",
            )
            executable_verifier = RecordingVerifier(
                ChallengeVerificationResult(
                    verifier="unexpected-executable-verifier",
                    status="verified",
                    summary="unexpected verifier run",
                    detail="this verifier should not have been called",
                    resolution="upheld",
                    advisory_only=False,
                )
            )
            service = AuditService(
                Path(tmpdir),
                contract_config=onchain.contract_config,
                publisher=onchain.publisher,
                arbiter_client=onchain.arbiter_client,
                challenge_verifiers={
                    "deterministic_fixture": service_default_deterministic_verifier(),
                    "executable_test": executable_verifier,
                },
            )
            created = service.create_audit(
                onchain.web3.eth.accounts[2],
                submitted_by="judge",
            )
            service.publish_audit(
                created["id"],
                10**16,
                "auditor-agent-v1",
                challenge_policy={"allowed_evidence_types": ["deterministic_fixture"]},
            )

            challenged = service.challenge_audit(
                created["id"],
                evidence_path.as_uri(),
                challenger="whitehat",
                evidence_type="executable_test",
                execution_env="foundry",
                evidence_manifest={
                    "bundle_format": "proof-of-audit-executable-evidence/v1",
                    "execution_env": "foundry",
                    "entrypoint": "ChallengeEvidence.t.sol",
                    "target_chain_id": onchain.contract_config.chain_id,
                },
            )

            self.assertIsNone(executable_verifier.last_context)
            self.assertEqual(
                challenged["challenge"]["verification_status"],
                "inadmissible_evidence_type",
            )
            self.assertEqual(
                challenged["challenge"]["policy_admissibility_status"],
                "inadmissible_evidence_type",
            )
            self.assertEqual(
                challenged["challenge"]["verification_dossier"]["policy"]["status"],
                "rejected",
            )
            self.assertEqual(
                challenged["challenge"]["verification_dossier"]["policy"][
                    "admissibility_status"
                ],
                "inadmissible_evidence_type",
            )

    def test_severity_threshold_marks_below_threshold_challenge_inadmissible(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            onchain = build_onchain_test_context()
            created_service = AuditService(
                Path(tmpdir) / "seed",
                contract_config=onchain.contract_config,
                publisher=onchain.publisher,
                arbiter_client=onchain.arbiter_client,
            )
            seeded = created_service.create_audit(
                "0x1000000000000000000000000000000000000001",
                submitted_by="judge",
            )
            high_severity_finding_id = seeded["report"]["findings"][0]["finding_id"]
            verifier = RecordingVerifier(
                ChallengeVerificationResult(
                    verifier="deterministic-match-v1",
                    status="verified",
                    summary="verifier found a supported high-severity disagreement",
                    detail="matched an existing high-severity finding",
                    resolution="upheld",
                    advisory_only=False,
                    matched_findings=[high_severity_finding_id],
                    unmatched_findings=[],
                )
            )
            service = AuditService(
                Path(tmpdir),
                contract_config=onchain.contract_config,
                publisher=onchain.publisher,
                arbiter_client=onchain.arbiter_client,
                challenge_verifiers={"deterministic_fixture": verifier},
            )
            created = service.create_audit(
                "0x1000000000000000000000000000000000000001",
                submitted_by="judge",
            )
            service.publish_audit(
                created["id"],
                10**16,
                "auditor-agent-v1",
                challenge_policy={"min_severity_threshold": "critical"},
            )

            challenged = service.challenge_audit(
                created["id"],
                "ipfs://reentrancy-bank/withdraw-drain",
                challenger="whitehat",
            )

            self.assertIsNotNone(verifier.last_context)
            self.assertEqual(challenged["status"], "challenged")
            self.assertEqual(
                challenged["challenge"]["verification_status"],
                "inadmissible_severity_below_threshold",
            )
            self.assertEqual(
                challenged["challenge"]["policy_admissibility_status"],
                "inadmissible_severity_below_threshold",
            )
            self.assertEqual(
                challenged["challenge"]["verification_dossier"]["policy"][
                    "admissibility_status"
                ],
                "inadmissible_severity_below_threshold",
            )
            self.assertEqual(challenged["challenge"]["status"], "opened")
            self.assertIsNone(challenged["challenge"].get("resolution"))

    def test_manual_resolution_still_records_rejected_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            onchain = build_onchain_test_context()
            service = AuditService(
                Path(tmpdir),
                contract_config=onchain.contract_config,
                publisher=onchain.publisher,
                arbiter_client=onchain.arbiter_client,
                validation_bridge=onchain.validation_bridge,
                reputation_bridge=onchain.reputation_bridge,
            )
            created = service.create_audit(
                "0x1000000000000000000000000000000000000001",
                submitted_by="judge",
            )
            service.publish_audit(created["id"], 10**16, "auditor-agent-v1")

            service.challenge_audit(
                created["id"],
                "ipfs://reentrancy-bank/withdraw-drain",
                challenger="whitehat",
            )
            challenged = service.resolve_audit(
                created["id"],
                upheld=False,
                resolved_by="arbiter-operator",
            )

            self.assertEqual(challenged["status"], "resolved")
            self.assertEqual(challenged["challenge"]["status"], "rejected")
            self.assertEqual(challenged["challenge"]["resolution"], "rejected")
            self.assertEqual(
                challenged["challenge"]["resolution_path"],
                "manual_fallback",
            )
            self.assertEqual(challenged["validation"]["status"], "responded")
            self.assertEqual(challenged["validation"]["response"], 100)
            self.assertEqual(challenged["validation"]["response_tag"], "claim-confirmed")
            self.assertEqual(challenged["reputation_trail"]["status"], "resolution_recorded")
            self.assertTrue(challenged["reputation_trail"]["claim_confirmed"])
            resolved_record = onchain.contract.functions.getAudit(1).call()
            self.assertEqual(int(resolved_record[10]), 3)
            self.assertEqual(int(resolved_record[11]), 2)

    def test_onchain_reputation_enriches_auditor_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            onchain = build_onchain_test_context()
            service = AuditService(
                Path(tmpdir),
                contract_config=onchain.contract_config,
                publisher=onchain.publisher,
                arbiter_client=onchain.arbiter_client,
                validation_bridge=onchain.validation_bridge,
                reputation_bridge=onchain.reputation_bridge,
            )
            created = service.create_audit(
                "0x1000000000000000000000000000000000000001",
                submitted_by="judge",
            )
            service.publish_audit(created["id"], 10**16, None)
            service.challenge_audit(
                created["id"],
                "ipfs://reentrancy-bank/withdraw-drain",
                challenger="whitehat",
            )
            service.resolve_audit(
                created["id"],
                upheld=False,
                resolved_by="arbiter-operator",
            )

            reputation = service.list_audits()[0]["agent"]["reputation"]

            self.assertEqual(reputation["source"], "project-local-custom")
            self.assertEqual(reputation["registry_address"], onchain.reputation_registry.address)
            self.assertEqual(reputation["agent_id"], 1)
            self.assertEqual(reputation["total_stake_wei"], 10**16)
            self.assertEqual(reputation["published_claim_count"], 1)
            self.assertEqual(reputation["challenge_rejected_count"], 1)
            self.assertEqual(reputation["score"], 100)

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
                "verifier_unavailable",
            )
            self.assertEqual(
                challenged["challenge"]["resolution_path"],
                "manual_fallback",
            )

    def test_challenge_persists_local_state_before_verifier_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            onchain = build_onchain_test_context()
            service = AuditService(
                Path(tmpdir),
                contract_config=onchain.contract_config,
                publisher=onchain.publisher,
                arbiter_client=onchain.arbiter_client,
                challenge_verifiers={
                    "deterministic_fixture": RaisingVerifier(),
                },
            )
            created = service.create_audit(
                "0x1000000000000000000000000000000000000003",
                submitted_by="judge",
            )
            service.publish_audit(created["id"], 10**16, "auditor-agent-v1")

            with self.assertRaisesRegex(RuntimeError, "verifier crashed"):
                service.challenge_audit(
                    created["id"],
                    "ipfs://wrong-proof",
                    challenger="whitehat",
                )

            hydrated = service.get_audit(created["id"])
            self.assertIsNotNone(hydrated)
            self.assertEqual(hydrated["status"], "challenged")
            self.assertEqual(hydrated["challenge"]["status"], "opened")
            self.assertEqual(hydrated["challenge"]["verification_status"], "pending")
            self.assertEqual(
                hydrated["challenge"]["resolution_path"],
                "manual_fallback",
            )
            self.assertTrue(hydrated["challenge"]["challenge_tx_hash"].startswith("0x"))

            audit_record = onchain.contract.functions.getAudit(1).call()
            self.assertEqual(int(audit_record[10]), 2)

    def test_executable_evidence_persists_advisory_output_and_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            onchain = build_onchain_test_context()
            evidence_path = Path(tmpdir) / "ChallengeEvidence.t.sol"
            evidence_path.write_text(
                "contract ChallengeEvidenceTest {}\n",
                encoding="utf-8",
            )
            executable_verifier = RecordingVerifier(
                ChallengeVerificationResult(
                    verifier="executable-evidence-advisory-v1",
                    status="verified",
                    summary="advisory upheld",
                    detail="new issue demonstrated",
                    resolution="upheld",
                    advisory_only=True,
                    execution_log="forge output",
                    matched_findings=[],
                    unmatched_findings=["rotateowner"],
                )
            )
            service = AuditService(
                Path(tmpdir),
                contract_config=onchain.contract_config,
                publisher=onchain.publisher,
                arbiter_client=onchain.arbiter_client,
                challenge_verifiers={
                    "deterministic_fixture": service_default_deterministic_verifier(),
                    "executable_test": executable_verifier,
                },
            )
            created = service.create_audit(
                "0x1000000000000000000000000000000000000003",
                submitted_by="judge",
            )
            service.publish_audit(created["id"], 10**16, "auditor-agent-v1")

            challenged = service.challenge_audit(
                created["id"],
                evidence_path.as_uri(),
                challenger="whitehat",
                evidence_type="executable_test",
                execution_env="foundry",
                evidence_manifest={
                    "bundle_format": "proof-of-audit-executable-evidence/v1",
                    "execution_env": "foundry",
                    "entrypoint": "ChallengeEvidence.t.sol",
                    "target_chain_id": onchain.contract_config.chain_id,
                },
            )

            self.assertEqual(challenged["status"], "challenged")
            self.assertEqual(challenged["challenge"]["status"], "opened")
            self.assertEqual(challenged["challenge"]["evidence_type"], "executable_test")
            self.assertEqual(challenged["challenge"]["execution_env"], "foundry")
            self.assertEqual(
                challenged["challenge"]["evidence_manifest"]["bundle_format"],
                "proof-of-audit-executable-evidence/v1",
            )
            self.assertTrue(challenged["challenge"]["evidence_hash"].startswith("0x"))
            self.assertEqual(
                challenged["challenge"]["challenge_hash"],
                challenged["challenge"]["evidence_hash"],
            )
            self.assertEqual(challenged["challenge"]["advisory_verdict"], "upheld")
            self.assertEqual(challenged["challenge"]["execution_log"], "forge output")
            self.assertEqual(challenged["challenge"]["unmatched_findings"], ["rotateowner"])
            self.assertEqual(
                challenged["challenge"]["verification_dossier"]["comparison"]["status"],
                "likely_new_issue",
            )
            self.assertEqual(
                challenged["challenge"]["verification_dossier"]["policy"]["status"],
                "manual_review_required",
            )
            self.assertEqual(
                challenged["challenge"]["verification_dossier"]["policy"]["recommended_resolution"],
                "upheld",
            )
            self.assertIn(
                "rationale",
                challenged["challenge"]["verification_dossier"]["comparison"],
            )
            self.assertIn(
                "confidence",
                challenged["challenge"]["verification_dossier"]["policy"],
            )
            hydrated = service.get_audit(created["id"])
            self.assertIsNotNone(hydrated)
            self.assertEqual(hydrated["challenge"]["evidence_type"], "executable_test")
            self.assertEqual(hydrated["challenge"]["execution_env"], "foundry")
            self.assertEqual(
                hydrated["challenge"]["evidence_manifest"]["pinned_block_number"],
                created["submission"]["snapshot_block_number"],
            )
            self.assertEqual(
                hydrated["challenge"]["evidence_hash"],
                challenged["challenge"]["evidence_hash"],
            )
            self.assertEqual(
                hydrated["challenge"]["verification_dossier"]["execution"]["execution_env"],
                "foundry",
            )
            self.assertEqual(hydrated["challenge"]["advisory_verdict"], "upheld")
            self.assertEqual(
                hydrated["challenge"]["verification_dossier_path"],
                f"/audits/{created['id']}/challenge/dossier",
            )
            self.assertEqual(
                service.get_challenge_verification_dossier(created["id"])["schema_version"],
                "challenge-verifier-dossier/v1",
            )
            self.assertIsNotNone(executable_verifier.last_context)
            self.assertEqual(
                executable_verifier.last_context.target_contract,
                created["contract_address"],
            )
            self.assertEqual(
                executable_verifier.last_context.evidence_type,
                "executable_test",
            )
            self.assertEqual(
                executable_verifier.last_context.execution_env,
                "foundry",
            )
            self.assertEqual(
                executable_verifier.last_context.evidence_manifest["entrypoint"],
                "ChallengeEvidence.t.sol",
            )
            self.assertEqual(
                executable_verifier.last_context.chain_id,
                onchain.contract_config.chain_id,
            )
            self.assertEqual(
                executable_verifier.last_context.rpc_url,
                onchain.contract_config.rpc_url,
            )
            self.assertEqual(
                executable_verifier.last_context.committed_evidence_hash,
                challenged["challenge"]["evidence_hash"],
            )
            self.assertEqual(
                executable_verifier.last_context.snapshot_block_number,
                created["submission"]["snapshot_block_number"],
            )

    def test_capture_snapshot_resolves_eip1967_proxy_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AuditService(Path(tmpdir), contract_config=ContractConfig.from_env({}))
            web3 = Mock()
            block_hash = bytes.fromhex("11" * 32)
            target_address = "0x1000000000000000000000000000000000000001"
            implementation_address = "0x2000000000000000000000000000000000000002"
            proxy_code = b"\x60\x00\x60\x00"
            implementation_code = b"\x60\x01\x60\x00"

            web3.eth.get_block.return_value = {"number": 42, "hash": block_hash}
            web3.eth.get_storage_at.side_effect = lambda address, slot, block_identifier=None: (
                bytes.fromhex("00" * 12 + implementation_address[2:].lower())
                if slot == _EIP1967_IMPLEMENTATION_SLOT
                else b"\x00" * 32
            )
            web3.eth.get_code.side_effect = (
                lambda address, block_identifier=None: (
                    proxy_code
                    if str(address).lower() == target_address.lower()
                    else implementation_code
                )
            )

            with patch.object(service, "_chain_web3_client", return_value=web3):
                snapshot = service._capture_deployed_address_snapshot(
                    {
                        "input_kind": "deployed_address",
                        "contract_address": target_address,
                    }
                )

            self.assertEqual(snapshot["snapshot_block_number"], 42)
            self.assertEqual(snapshot["snapshot_block_hash"], "0x" + "11" * 32)
            self.assertEqual(snapshot["proxy_kind"], "eip1967")
            self.assertEqual(snapshot["proxy_resolution_status"], "resolved")
            self.assertEqual(
                snapshot["implementation_address_at_snapshot"],
                implementation_address,
            )
            self.assertEqual(
                snapshot["implementation_code_hash_at_snapshot"],
                Web3.to_hex(Web3.keccak(implementation_code)),
            )

    def test_capture_snapshot_marks_beacon_proxy_as_unsupported(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AuditService(Path(tmpdir), contract_config=ContractConfig.from_env({}))
            web3 = Mock()
            target_address = "0x1000000000000000000000000000000000000001"
            beacon_address = "0x3000000000000000000000000000000000000003"
            proxy_code = b"\x60\x00\x60\x00"

            web3.eth.get_block.return_value = {
                "number": 84,
                "hash": bytes.fromhex("22" * 32),
            }
            web3.eth.get_storage_at.side_effect = lambda address, slot, block_identifier=None: (
                bytes.fromhex("00" * 12 + beacon_address[2:].lower())
                if slot == _EIP1967_BEACON_SLOT
                else b"\x00" * 32
            )
            web3.eth.get_code.return_value = proxy_code

            with patch.object(service, "_chain_web3_client", return_value=web3):
                snapshot = service._capture_deployed_address_snapshot(
                    {
                        "input_kind": "deployed_address",
                        "contract_address": target_address,
                    }
                )

            self.assertEqual(snapshot["proxy_kind"], "eip1967-beacon")
            self.assertEqual(
                snapshot["proxy_resolution_status"],
                "unsupported_proxy_topology",
            )
            self.assertIn("beacon", snapshot["proxy_resolution_detail"].lower())
            self.assertIsNone(snapshot["implementation_address_at_snapshot"])
            self.assertIsNone(snapshot["implementation_code_hash_at_snapshot"])

    def test_publish_round_trips_proxy_identity_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            onchain = build_onchain_test_context()
            service = AuditService(
                Path(tmpdir),
                contract_config=onchain.contract_config,
                publisher=onchain.publisher,
                arbiter_client=onchain.arbiter_client,
                validation_bridge=onchain.validation_bridge,
                reputation_bridge=onchain.reputation_bridge,
            )
            proxy_snapshot = {
                "snapshot_block_number": 42,
                "snapshot_block_hash": "0x" + "11" * 32,
                "target_code_hash_at_snapshot": "0x" + "22" * 32,
                "proxy_kind": "eip1967",
                "proxy_resolution_status": "resolved",
                "proxy_resolution_detail": "Resolved implementation identity.",
                "implementation_address_at_snapshot": "0x2000000000000000000000000000000000000002",
                "implementation_code_hash_at_snapshot": "0x" + "33" * 32,
            }

            with patch.object(
                service,
                "_capture_deployed_address_snapshot",
                return_value=proxy_snapshot,
            ):
                created = service.create_audit(
                    onchain.web3.eth.accounts[2],
                    submitted_by="judge",
                )
                published = service.publish_audit(created["id"], 10**16, None)

            self.assertEqual(created["submission"]["proxy_kind"], "eip1967")
            self.assertEqual(
                published["onchain"]["proxy_resolution_status"],
                "resolved",
            )
            self.assertEqual(
                published["onchain"]["implementation_address_at_snapshot"],
                proxy_snapshot["implementation_address_at_snapshot"],
            )
            validation_document = service.get_validation_request_document(created["id"])
            self.assertIsNotNone(validation_document)
            assert validation_document is not None
            self.assertEqual(
                validation_document["claim"]["proxyKind"],
                "eip1967",
            )
            self.assertEqual(
                validation_document["claim"]["implementationAddressAtSnapshot"],
                proxy_snapshot["implementation_address_at_snapshot"],
            )
            reputation_document = service.get_reputation_claim_document(created["id"])
            self.assertIsNotNone(reputation_document)
            assert reputation_document is not None
            self.assertEqual(
                reputation_document["claim"]["proxyResolutionStatus"],
                "resolved",
            )
            self.assertEqual(
                reputation_document["claim"]["implementationCodeHashAtSnapshot"],
                proxy_snapshot["implementation_code_hash_at_snapshot"],
            )

    def test_publish_rejects_deployed_address_code_drift_after_snapshot(self) -> None:
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

            with patch.object(
                service,
                "_capture_deployed_address_snapshot",
                return_value={
                    "snapshot_block_number": created["submission"]["snapshot_block_number"],
                    "snapshot_block_hash": created["submission"]["snapshot_block_hash"],
                    "target_code_hash_at_snapshot": "0x" + "12" * 32,
                },
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "target code changed since audit start",
                ):
                    service.publish_audit(created["id"], 10**16, None)

    def test_publish_rejects_proxy_implementation_drift_after_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            onchain = build_onchain_test_context()
            service = AuditService(
                Path(tmpdir),
                contract_config=onchain.contract_config,
                publisher=onchain.publisher,
                arbiter_client=onchain.arbiter_client,
            )
            initial_snapshot = {
                "snapshot_block_number": 42,
                "snapshot_block_hash": "0x" + "11" * 32,
                "target_code_hash_at_snapshot": "0x" + "22" * 32,
                "proxy_kind": "eip1967",
                "proxy_resolution_status": "resolved",
                "proxy_resolution_detail": "Resolved implementation identity.",
                "implementation_address_at_snapshot": "0x2000000000000000000000000000000000000002",
                "implementation_code_hash_at_snapshot": "0x" + "33" * 32,
            }
            with patch.object(
                service,
                "_capture_deployed_address_snapshot",
                return_value=initial_snapshot,
            ):
                created = service.create_audit(
                    onchain.web3.eth.accounts[2],
                    submitted_by="judge",
                )

            with patch.object(
                service,
                "_capture_deployed_address_snapshot",
                return_value={
                    **initial_snapshot,
                    "implementation_address_at_snapshot": "0x4000000000000000000000000000000000000004",
                    "implementation_code_hash_at_snapshot": "0x" + "44" * 32,
                },
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "proxy implementation changed since audit start",
                ):
                    service.publish_audit(created["id"], 10**16, None)

    def test_executable_challenge_rejects_conflicting_snapshot_block(self) -> None:
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
            service.publish_audit(created["id"], 10**16, None)

            with self.assertRaisesRegex(
                ValueError,
                "executable challenge evidence must use the audit snapshot block",
            ):
                service.challenge_audit(
                    created["id"],
                    "file:///tmp/ChallengeEvidence.t.sol",
                    challenger="whitehat",
                    evidence_type="executable_test",
                    execution_env="foundry",
                    evidence_manifest={
                        "bundle_format": "proof-of-audit-executable-evidence/v1",
                        "execution_env": "foundry",
                        "entrypoint": "ChallengeEvidence.t.sol",
                        "target_chain_id": onchain.contract_config.chain_id,
                        "pinned_block_number": created["submission"][
                            "snapshot_block_number"
                        ]
                        + 1,
                    },
                )

    def test_executable_evidence_requires_deployed_address_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            onchain = build_onchain_test_context()
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
                contract_config=replace(
                    onchain.contract_config,
                    demo_fixtures_file=fixtures_file,
                ),
                publisher=onchain.publisher,
                arbiter_client=onchain.arbiter_client,
            )
            created = service.create_audit_submission(
                {
                    "input_kind": "demo_fixture",
                    "fixture_id": "clean-vault",
                },
                submitted_by="judge",
            )
            service.publish_audit(created["id"], 10**16, "auditor-agent-v1")

            with self.assertRaisesRegex(
                ValueError,
                "executable_test challenge evidence is only supported for deployed_address audits",
            ):
                service.challenge_audit(
                    created["id"],
                    "file:///tmp/ChallengeEvidence.t.sol",
                    challenger="whitehat",
                    evidence_type="executable_test",
                    execution_env="foundry",
                    evidence_manifest={
                        "bundle_format": "proof-of-audit-executable-evidence/v1",
                        "execution_env": "foundry",
                        "entrypoint": "ChallengeEvidence.t.sol",
                        "target_chain_id": onchain.contract_config.chain_id,
                    },
                )

    def test_challenge_requires_publish(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            local_config = replace(ContractConfig.from_env({}), network="anvil-local")
            service = AuditService(Path(tmpdir), contract_config=local_config)
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
            local_config = replace(ContractConfig.from_env({}), network="anvil-local")
            service = AuditService(
                Path(tmpdir),
                contract_config=local_config,
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
            local_config = replace(ContractConfig.from_env({}), network="anvil-local")
            service = AuditService(Path(tmpdir), contract_config=local_config)

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

    def test_repository_submission_persists_execution_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AuditService(Path(tmpdir))

            created = service.create_audit_submission(
                {
                    "input_kind": "repository_url",
                    "repository_url": "https://github.com/example/repo",
                    "entry_contract": "Vault",
                },
                submitted_by="repo-test",
            )

            self.assertEqual(created["submission"]["input_kind"], "repository_url")
            self.assertEqual(created["report"]["benchmark_id"], "repository-url")
            self.assertIsNotNone(created["execution"])
            self.assertEqual(created["execution"]["status"], "fallback")

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
