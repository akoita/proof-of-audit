import unittest

from proof_of_audit_agent.worker import AuditWorker


class AuditWorkerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.worker = AuditWorker()

    def test_known_contract_returns_deterministic_finding(self) -> None:
        report = self.worker.run_audit(
            "0x1000000000000000000000000000000000000001"
        )

        self.assertEqual(report.benchmark_id, "reentrancy-bank")
        self.assertEqual(len(report.findings), 1)
        self.assertEqual(report.max_severity, 3)

    def test_unknown_contract_is_safe_fallback(self) -> None:
        report = self.worker.run_audit(
            "0x1234000000000000000000000000000000000000"
        )

        self.assertEqual(report.benchmark_id, "unknown")
        self.assertEqual(report.confidence, "low")
        self.assertEqual(report.findings, [])


if __name__ == "__main__":
    unittest.main()

