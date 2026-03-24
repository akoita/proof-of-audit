import unittest
from unittest.mock import patch

from proof_of_audit_api.publisher import OnchainPublishError
from helpers import build_onchain_test_context


class PublishVerificationRetryTest(unittest.TestCase):
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
