from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

import pytest

from proof_of_audit_api.config import ContractConfig
from proof_of_audit_api.service import AuditService
from proof_of_audit_api.store import SqliteStore


def test_service_imports_legacy_request_catalog_on_startup_and_keeps_backup(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    legacy_path = data_root / "audit-requests.json"
    original = json.dumps(
        {
            "items": [
                {
                    "request_id": 12,
                    "status": "open",
                    "contract_address": "0xABCDEF",
                    "created_at": "2026-10-01T12:00:00Z",
                },
                {
                    "request_id": 0,
                    "status": "open",
                    "contract_address": "0x1000000000000000000000000000000000000001",
                    "created_at": "2026-10-01T11:00:00Z",
                },
            ]
        },
        indent=2,
    ).encode()
    legacy_path.write_bytes(original)

    service = AuditService(data_root, contract_config=ContractConfig.from_env({}))
    try:
        request = service.get_audit_request("12")
        assert request is not None
        assert request["request_id"] == "12"
        assert request["contract_address"] == "0xabcdef"
        zero_request = service.get_audit_request("0")
        assert zero_request is not None
        assert zero_request["request_id"] == "0"
        assert len(service.list_audit_requests()) == 2
        assert legacy_path.read_bytes() == original
        assert service.store.read_request("12") is not None
    finally:
        service.close()

    reloaded = AuditService(data_root, contract_config=ContractConfig.from_env({}))
    try:
        assert reloaded.get_audit_request("12") is not None
        assert len(reloaded.store.list_requests()) == 2
    finally:
        reloaded.close()


def test_service_startup_rejects_malformed_catalog_without_audit_leak(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "audit-requests.json").write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="must contain an items list"):
        AuditService(data_root, contract_config=ContractConfig.from_env({}))

    store = SqliteStore(data_root / "audits.sqlite3", legacy_root=data_root)
    assert store.list_all() == []


def test_service_startup_keeps_id_bearing_catalog_out_of_audit_records(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "audit-requests.json").write_text(
        json.dumps(
            {
                "id": "catalog-as-audit",
                "items": [
                    {
                        "request_id": "request-1",
                        "contract_address": "0x1000000000000000000000000000000000000001",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    service = AuditService(data_root, contract_config=ContractConfig.from_env({}))
    try:
        assert service.store.read("catalog-as-audit") is None
        assert service.store.list_all() == []
        assert service.get_audit_request("request-1") is not None
    finally:
        service.close()


def test_service_request_writes_are_safe_across_instances_sharing_sqlite(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    database_path = tmp_path / "shared.sqlite3"
    services = [
        AuditService(
            data_root,
            contract_config=ContractConfig.from_env({}),
            store_path=database_path,
        )
        for _ in range(4)
    ]
    payloads = [
        {
            "request_id": f"request-{index}",
            "status": "open",
            "contract_address": "0x1000000000000000000000000000000000000001",
            "created_at": f"2026-10-01T00:00:{index:02d}Z",
        }
        for index in range(48)
    ]

    def write(index: int) -> None:
        services[index % len(services)]._upsert_audit_request_record(payloads[index])

    try:
        with ThreadPoolExecutor(max_workers=len(services)) as executor:
            list(executor.map(write, range(len(payloads))))

        requests = services[0].list_audit_requests()
        assert {item["request_id"] for item in requests} == {
            item["request_id"] for item in payloads
        }
    finally:
        for service in services:
            service.close()


def test_startup_migration_failure_closes_owned_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "audit-requests.json").write_text(
        json.dumps({"items": [{"request_id": "request-1"}]}),
        encoding="utf-8",
    )

    class FailingStore:
        def __init__(self) -> None:
            self.close_called = False

        def import_legacy_requests(self, legacy_path: Path) -> None:
            del legacy_path
            raise ValueError("migration failed")

        def close(self) -> None:
            self.close_called = True

    store = FailingStore()
    monkeypatch.setattr(
        "proof_of_audit_api.service.create_store",
        lambda **kwargs: store,
    )

    with pytest.raises(ValueError, match="migration failed"):
        AuditService(data_root)

    assert store.close_called


def test_service_uses_store_methods_without_rewriting_legacy_catalog(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    catalog_path = data_root / "audit-requests.json"
    original = json.dumps({"items": []}, indent=2).encode()
    catalog_path.write_bytes(original)
    service = AuditService(
        data_root,
        contract_config=ContractConfig.from_env({}),
    )
    try:
        service._upsert_audit_request_record(
            {
                "request_id": "request-1",
                "status": "open",
                "contract_address": "0x1000000000000000000000000000000000000001",
            }
        )
        request = service.get_audit_request("request-1")
        assert request is not None
        assert request["status"] == "open"
        assert catalog_path.read_bytes() == original
    finally:
        service.close()


def test_sqlite_request_store_restart_smoke(tmp_path: Path) -> None:
    database_path = tmp_path / "requests.sqlite3"
    first_store = SqliteStore(database_path)
    first_store.write_request("request-1", {"request_id": "request-1"})

    second_store = SqliteStore(database_path)

    assert second_store.read_request("request-1") == {"request_id": "request-1"}
