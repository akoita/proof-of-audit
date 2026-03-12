import unittest
from pathlib import Path
import tempfile

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

    def test_manifest_fixture_address_maps_to_benchmark(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = Path(tmpdir) / "demo-fixtures.localhost.json"
            manifest.write_text(
                """
{
  "fixtures": [
    {
      "id": "unchecked-treasury",
      "label": "Unchecked Treasury",
      "contract_name": "UncheckedTreasury",
      "entry_contract": "UncheckedTreasury",
      "benchmark_id": "unchecked-treasury",
      "address": "0x9999000000000000000000000000000000000004",
      "note": "Imported registry and unchecked external call",
      "source_path": "demo/contracts/UncheckedTreasury.sol"
    }
  ]
}
""".strip()
                + "\n",
                encoding="utf-8",
            )

            worker = AuditWorker(manifest)
            report = worker.run_audit("0x9999000000000000000000000000000000000004")

            self.assertEqual(report.benchmark_id, "unchecked-treasury")
            self.assertEqual(report.max_severity, 2)
            self.assertEqual(len(report.findings), 1)


if __name__ == "__main__":
    unittest.main()
