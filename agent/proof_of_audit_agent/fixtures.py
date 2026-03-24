from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DEMO_FIXTURES_FILE = REPO_ROOT / "deployments" / "demo-fixtures.localhost.json"


@dataclass(frozen=True)
class DemoFixture:
    fixture_id: str
    label: str
    contract_name: str
    entry_contract: str
    benchmark_id: str
    address: str
    challenge_proof_uri: str
    note: str
    source_path: str

    @classmethod
    def from_dict(cls, payload: dict[str, str]) -> "DemoFixture":
        return cls(
            fixture_id=payload["id"],
            label=payload["label"],
            contract_name=payload["contract_name"],
            entry_contract=payload["entry_contract"],
            benchmark_id=payload["benchmark_id"],
            address=payload["address"].lower(),
            challenge_proof_uri=payload.get("challenge_proof_uri", "ipfs://benchmark-proof"),
            note=payload["note"],
            source_path=payload["source_path"],
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.fixture_id,
            "label": self.label,
            "contract_name": self.contract_name,
            "entry_contract": self.entry_contract,
            "benchmark_id": self.benchmark_id,
            "address": self.address,
            "challenge_proof_uri": self.challenge_proof_uri,
            "note": self.note,
            "source_path": self.source_path,
        }


def resolve_demo_fixtures_file(path: Path | None = None) -> Path | None:
    candidate = path or DEFAULT_DEMO_FIXTURES_FILE
    return candidate if candidate.exists() else None


def default_demo_fixtures_file_for_network(network: str | None = None) -> Path:
    if network:
        normalized_network = str(network).strip().lower()
        if normalized_network:
            network_candidate = (
                REPO_ROOT / "deployments" / f"demo-fixtures.{normalized_network}.json"
            )
            if network_candidate.exists():
                return network_candidate
    return DEFAULT_DEMO_FIXTURES_FILE


def load_demo_fixtures(path: Path | None = None) -> list[DemoFixture]:
    manifest_file = resolve_demo_fixtures_file(path)
    if manifest_file is None:
        return []

    payload = json.loads(manifest_file.read_text(encoding="utf-8"))
    return [
        DemoFixture.from_dict(item)
        for item in payload.get("fixtures", [])
    ]
