import unittest
from unittest.mock import patch

from proof_of_audit_api.publisher import OnchainPublishError
from helpers import build_onchain_test_context


class PublishVerificationRetryTest(unittest.TestCase):
    def test_create_audit_request_returns_allowlist_and_identity_metadata(self) -> None:
        onchain = build_onchain_test_context()
        created = onchain.publisher.create_audit_request(
            target_address=onchain.web3.eth.accounts[3],
            bounty_wei=2 * 10**17,
            response_window_seconds=3600,
            allowlist_enabled=True,
            identity_registry=onchain.contract_config.auditor_agent_registry,
            required_agent_id=onchain.contract_config.auditor_agent_id or 0,
            allowlisted_auditors=[onchain.publisher.account.address],
        )

        request_record = onchain.publisher.get_audit_request(created.request_id)

        self.assertTrue(request_record.eligibility["allowlist_enabled"])
        self.assertEqual(
            request_record.eligibility["identity_registry"],
            onchain.contract_config.auditor_agent_registry,
        )
        self.assertEqual(
            request_record.eligibility["required_agent_id"],
            onchain.contract_config.auditor_agent_id,
        )
        self.assertEqual(
            request_record.eligibility["allowlisted_auditor_addresses"],
            [onchain.publisher.account.address.lower()],
        )

    def test_submit_audit_request_claim_returns_claim_metadata(self) -> None:
        onchain = build_onchain_test_context()
        created = onchain.publisher.create_audit_request(
            target_address=onchain.web3.eth.accounts[3],
            bounty_wei=2 * 10**17,
            response_window_seconds=3600,
        )

        claim = onchain.publisher.submit_audit_request_claim(
            request_id=created.request_id,
            agent_registry=onchain.contract_config.auditor_agent_registry or "",
            agent_id=onchain.contract_config.auditor_agent_id or 0,
            report_hash="0x" + "11" * 32,
            metadata_hash="0x" + "22" * 32,
            max_severity=3,
            finding_count=1,
            stake_wei=10**16,
        )

        self.assertEqual(claim.request_id, created.request_id)
        self.assertEqual(claim.claim_id, 1)
        onchain_claim = onchain.publisher.get_audit_request_claim(claim.claim_id)
        self.assertEqual(onchain_claim.state, "submitted")
        self.assertEqual(onchain_claim.agent_id, onchain.contract_config.auditor_agent_id)

    def test_request_claim_challenge_and_resolution_return_metadata(self) -> None:
        onchain = build_onchain_test_context()
        created = onchain.publisher.create_audit_request(
            target_address=onchain.web3.eth.accounts[3],
            bounty_wei=2 * 10**17,
            response_window_seconds=3600,
        )
        claim = onchain.publisher.submit_audit_request_claim(
            request_id=created.request_id,
            agent_registry=onchain.contract_config.auditor_agent_registry or "",
            agent_id=onchain.contract_config.auditor_agent_id or 0,
            report_hash="0x" + "11" * 32,
            metadata_hash="0x" + "22" * 32,
            max_severity=3,
            finding_count=1,
            stake_wei=10**16,
        )

        challenge = onchain.secondary_publisher.challenge_audit_request_claim(
            claim_id=claim.claim_id,
            agent_registry=onchain.secondary_contract_config.auditor_agent_registry or "",
            agent_id=onchain.secondary_contract_config.auditor_agent_id or 0,
            evidence_hash="0x" + "33" * 32,
            challenge_bond_wei=5 * 10**15,
        )

        self.assertEqual(challenge.request_id, created.request_id)
        self.assertEqual(challenge.claim_id, claim.claim_id)
        challenged_claim = onchain.publisher.get_audit_request_claim(claim.claim_id)
        self.assertEqual(challenged_claim.state, "challenged")
        self.assertEqual(
            challenged_claim.challenger_address,
            onchain.secondary_publisher.account.address,
        )

        resolution = onchain.arbiter_client.resolve_audit_request_claim_challenge(
            claim_id=claim.claim_id,
            upheld=True,
        )

        self.assertEqual(resolution.claim_id, claim.claim_id)
        self.assertEqual(resolution.resolution, "upheld")
        self.assertEqual(resolution.gross_payout_wei, 10**16 + 5 * 10**15)
        self.assertEqual(resolution.resolution_fee_wei, 0)
        self.assertEqual(resolution.payout_wei, 10**16 + 5 * 10**15)
        resolved_claim = onchain.publisher.get_audit_request_claim(claim.claim_id)
        self.assertEqual(resolved_claim.state, "slashed")
        self.assertEqual(resolved_claim.resolution, "upheld")

    def test_request_settlement_lifecycle_returns_distribution_metadata(self) -> None:
        onchain = build_onchain_test_context()
        created = onchain.publisher.create_audit_request(
            target_address=onchain.web3.eth.accounts[3],
            bounty_wei=2 * 10**17,
            response_window_seconds=3600,
        )
        claim = onchain.publisher.submit_audit_request_claim(
            request_id=created.request_id,
            agent_registry=onchain.contract_config.auditor_agent_registry or "",
            agent_id=onchain.contract_config.auditor_agent_id or 0,
            report_hash="0x" + "11" * 32,
            metadata_hash="0x" + "22" * 32,
            max_severity=3,
            finding_count=1,
            stake_wei=10**16,
        )

        tester = onchain.web3.provider.ethereum_tester
        latest = tester.get_block_by_number("latest")
        tester.time_travel(int(latest["timestamp"]) + 86401)
        tester.mine_block()

        onchain.publisher.classify_audit_request_claims(
            request_id=created.request_id,
            max_claims=1,
        )
        onchain.publisher.finalize_audit_request_settlement(request_id=created.request_id)

        settlement = onchain.publisher.get_audit_request_settlement(created.request_id)
        self.assertTrue(settlement.finalized)
        self.assertEqual(settlement.eligible_claim_count, 1)
        self.assertEqual(settlement.eligible_stake_wei, 10**16)
        self.assertEqual(settlement.distributable_bounty_wei, 2 * 10**17)

        claim_preview = onchain.publisher.preview_audit_request_claim_settlement(
            claim.claim_id
        )
        self.assertTrue(claim_preview.eligible)
        self.assertFalse(claim_preview.withdrawn)
        self.assertEqual(claim_preview.bounty_share_wei, 2 * 10**17)
        self.assertEqual(claim_preview.payout_wei, 2 * 10**17 + 10**16)

        withdrawal = onchain.publisher.withdraw_audit_request_claim_settlement(
            claim_id=claim.claim_id
        )
        self.assertEqual(withdrawal.request_id, created.request_id)
        self.assertEqual(withdrawal.claim_id, claim.claim_id)
        self.assertEqual(withdrawal.returned_stake_wei, 10**16)
        self.assertEqual(withdrawal.bounty_share_wei, 2 * 10**17)
        self.assertEqual(withdrawal.payout_wei, 2 * 10**17 + 10**16)

        refund_preview = onchain.publisher.preview_audit_request_refund(created.request_id)
        self.assertTrue(refund_preview.available)
        self.assertEqual(refund_preview.refund_wei, 0)

    def test_marketplace_fee_config_and_accruals_are_visible(self) -> None:
        onchain = build_onchain_test_context(protocol_fee_bps=500, resolution_fee_bps=1000)
        fee_config = onchain.publisher.get_marketplace_fee_config()
        self.assertEqual(fee_config.treasury_address, onchain.contract_config.treasury_address)
        self.assertEqual(fee_config.protocol_fee_bps, 500)
        self.assertEqual(fee_config.resolution_fee_bps, 1000)
        self.assertEqual(fee_config.fee_denominator, 10_000)

        created = onchain.publisher.create_audit_request(
            target_address=onchain.web3.eth.accounts[3],
            bounty_wei=2 * 10**17,
            response_window_seconds=3600,
        )
        claim = onchain.publisher.submit_audit_request_claim(
            request_id=created.request_id,
            agent_registry=onchain.contract_config.auditor_agent_registry or "",
            agent_id=onchain.contract_config.auditor_agent_id or 0,
            report_hash="0x" + "11" * 32,
            metadata_hash="0x" + "22" * 32,
            max_severity=3,
            finding_count=1,
            stake_wei=10**16,
        )
        tester = onchain.web3.provider.ethereum_tester
        latest = tester.get_block_by_number("latest")
        tester.time_travel(int(latest["timestamp"]) + 86401)
        tester.mine_block()

        onchain.publisher.classify_audit_request_claims(
            request_id=created.request_id,
            max_claims=1,
        )
        onchain.publisher.finalize_audit_request_settlement(request_id=created.request_id)

        settlement = onchain.publisher.get_audit_request_settlement(created.request_id)
        self.assertEqual(settlement.protocol_fee_wei, 10**16)
        self.assertEqual(settlement.distributable_bounty_wei, 19 * 10**16)

    def test_verify_published_record_retries_until_chain_state_catches_up(self) -> None:
        publisher = build_onchain_test_context().publisher

        with (
            patch.object(
                publisher,
                "_verify_onchain_record",
                side_effect=[
                    OnchainPublishError("On-chain target address did not match publish input."),
                    OnchainPublishError("On-chain target address did not match publish input."),
                    None,
                ],
            ) as verify_mock,
            patch("proof_of_audit_api.publisher.time.sleep") as sleep_mock,
        ):
            publisher._verify_published_record_with_retry(
                audit_id=1,
                target="0x1000000000000000000000000000000000000001",
                report_hash="0x" + "11" * 32,
                metadata_hash="0x" + "22" * 32,
                max_severity=3,
                finding_count=1,
                stake_wei=10**16,
            )

        self.assertEqual(verify_mock.call_count, 3)
        self.assertEqual(sleep_mock.call_count, 2)
        self.assertEqual(
            [call.args[0] for call in sleep_mock.call_args_list],
            [0.25, 0.5],
        )

    def test_verify_published_record_raises_after_retry_budget_is_exhausted(self) -> None:
        publisher = build_onchain_test_context().publisher

        with (
            patch.object(
                publisher,
                "_verify_onchain_record",
                side_effect=OnchainPublishError(
                    "On-chain target address did not match publish input."
                ),
            ) as verify_mock,
            patch("proof_of_audit_api.publisher.time.sleep") as sleep_mock,
        ):
            with self.assertRaises(OnchainPublishError) as exc:
                publisher._verify_published_record_with_retry(
                    audit_id=1,
                    target="0x1000000000000000000000000000000000000001",
                    report_hash="0x" + "11" * 32,
                    metadata_hash="0x" + "22" * 32,
                    max_severity=3,
                    finding_count=1,
                    stake_wei=10**16,
                )

        self.assertEqual(verify_mock.call_count, 4)
        self.assertEqual(sleep_mock.call_count, 3)
        self.assertIn("receipt was confirmed", str(exc.exception))
        self.assertIn("On-chain target address did not match publish input.", str(exc.exception))
