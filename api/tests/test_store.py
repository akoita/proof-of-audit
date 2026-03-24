from __future__ import annotations

import json
from pathlib import Path

import pytest

from proof_of_audit_api.store import (
    CloudSqlPostgresConfig,
    JsonStore,
    PostgresStore,
    SqliteStore,
    create_store,
)


class FakePostgresCursor:
    def __init__(self, records: dict[str, str]) -> None:
        self.records = records
        self.rows: list[tuple[object, ...]] = []

    def execute(self, query: str, parameters: tuple[object, ...]) -> None:
        normalized_query = " ".join(query.split())
        if normalized_query.startswith("CREATE TABLE IF NOT EXISTS audits"):
            self.rows = []
            return
        if normalized_query.startswith("INSERT INTO audits"):
            audit_id, encoded_payload = parameters
            self.records[str(audit_id)] = str(encoded_payload)
            self.rows = []
            return
        if normalized_query == "SELECT payload::text FROM audits WHERE id = %s":
            audit_id = str(parameters[0])
            payload = self.records.get(audit_id)
            self.rows = [] if payload is None else [(payload,)]
            return
        if normalized_query == "SELECT payload::text FROM audits ORDER BY id ASC":
            self.rows = [(payload,) for _, payload in sorted(self.records.items())]
            return
        if normalized_query == "SELECT 1 FROM audits WHERE id = %s":
            audit_id = str(parameters[0])
            self.rows = [] if audit_id not in self.records else [(1,)]
            return
        raise AssertionError(f"unexpected query: {normalized_query}")

    def fetchone(self) -> tuple[object, ...] | None:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[tuple[object, ...]]:
        return list(self.rows)

    def close(self) -> None:
        return None


class FakePostgresConnection:
    def __init__(self, records: dict[str, str]) -> None:
        self.records = records

    def cursor(self) -> FakePostgresCursor:
        return FakePostgresCursor(self.records)

    def commit(self) -> None:
        return None

    def close(self) -> None:
        return None


class FakePostgresConnector:
    def __init__(self) -> None:
        self.records: dict[str, str] = {}
        self.closed = False
        self.calls: list[dict[str, object]] = []

    def connect(self, instance_connection_name: str, driver: str, **kwargs: object) -> FakePostgresConnection:
        self.calls.append(
            {
                "instance_connection_name": instance_connection_name,
                "driver": driver,
                **kwargs,
            }
        )
        return FakePostgresConnection(self.records)

    def close(self) -> None:
        self.closed = True


def build_postgres_config(**overrides: object) -> CloudSqlPostgresConfig:
    values: dict[str, object] = {
        "instance_connection_name": "project:region:instance",
        "database": "proof_of_audit",
        "user": "auditor@example.iam",
        "password": None,
        "enable_iam_auth": True,
        "ip_type": "private",
    }
    values.update(overrides)
    return CloudSqlPostgresConfig(**values)


def test_sqlite_store_persists_records(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "audits.sqlite3")
    payload = {"id": "audit-1", "status": "draft", "target_key": "0xabc"}

    store.write("audit-1", payload)

    reloaded = SqliteStore(tmp_path / "audits.sqlite3")
    assert reloaded.read("audit-1") == payload
    assert reloaded.list_all() == [payload]


def test_sqlite_store_imports_legacy_json_files(tmp_path: Path) -> None:
    legacy_root = tmp_path / "legacy"
    legacy_root.mkdir()
    legacy_payload = {"id": "legacy-audit", "status": "draft"}
    (legacy_root / "legacy-audit.json").write_text(
        json.dumps(legacy_payload, indent=2),
        encoding="utf-8",
    )

    store = SqliteStore(tmp_path / "audits.sqlite3", legacy_root=legacy_root)

    assert store.read("legacy-audit") == legacy_payload


def test_sqlite_store_lists_records_by_target_key(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "audits.sqlite3")
    store.write("audit-1", {"id": "audit-1", "target_key": "0xabc"})
    store.write("audit-2", {"id": "audit-2", "target_key": "0xdef"})
    store.write("audit-3", {"id": "audit-3", "target_key": "0xabc"})

    assert [record["id"] for record in store.list_by_target_key("0xabc")] == [
        "audit-1",
        "audit-3",
    ]


def test_create_store_defaults_to_sqlite(tmp_path: Path) -> None:
    store = create_store(root=tmp_path)

    assert isinstance(store, SqliteStore)


def test_create_store_supports_json_mode(tmp_path: Path) -> None:
    store = create_store(root=tmp_path, kind="json")

    assert isinstance(store, JsonStore)


def test_postgres_store_persists_records(tmp_path: Path) -> None:
    connector = FakePostgresConnector()
    store = PostgresStore(
        build_postgres_config(),
        connector_factory=lambda: connector,
    )
    payload = {"id": "audit-1", "status": "draft", "target_key": "0xabc"}

    store.write("audit-1", payload)

    assert store.read("audit-1") == payload
    assert store.list_all() == [payload]
    assert connector.calls[-1]["driver"] == "pg8000"
    assert connector.calls[-1]["enable_iam_auth"] is True
    assert connector.calls[-1]["ip_type"] == "private"


def test_postgres_store_imports_legacy_json_files(tmp_path: Path) -> None:
    legacy_root = tmp_path / "legacy"
    legacy_root.mkdir()
    legacy_payload = {"id": "legacy-audit", "status": "draft"}
    (legacy_root / "legacy-audit.json").write_text(
        json.dumps(legacy_payload, indent=2),
        encoding="utf-8",
    )

    store = PostgresStore(
        build_postgres_config(),
        legacy_root=legacy_root,
        connector_factory=FakePostgresConnector,
    )

    assert store.read("legacy-audit") == legacy_payload


def test_postgres_store_lists_records_by_target_key(tmp_path: Path) -> None:
    store = PostgresStore(
        build_postgres_config(),
        connector_factory=FakePostgresConnector,
    )
    store.write("audit-1", {"id": "audit-1", "target_key": "0xabc"})
    store.write("audit-2", {"id": "audit-2", "target_key": "0xdef"})
    store.write("audit-3", {"id": "audit-3", "target_key": "0xabc"})

    assert [record["id"] for record in store.list_by_target_key("0xabc")] == [
        "audit-1",
        "audit-3",
    ]


def test_create_store_supports_cloudsql_postgres_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector = FakePostgresConnector()
    monkeypatch.setattr(
        "proof_of_audit_api.store._build_cloudsql_connector",
        lambda ip_type: (connector, ip_type),
    )
    store = create_store(
        root=tmp_path,
        kind="cloudsql-postgres",
        postgres_config=build_postgres_config(),
    )

    assert isinstance(store, PostgresStore)
    store.close()


def test_cloudsql_postgres_config_requires_explicit_settings() -> None:
    with pytest.raises(ValueError, match="PROOF_OF_AUDIT_STORE_INSTANCE_CONNECTION_NAME"):
        CloudSqlPostgresConfig.from_env({})


def test_cloudsql_postgres_config_requires_password_without_iam_auth() -> None:
    with pytest.raises(ValueError, match="PROOF_OF_AUDIT_STORE_PASSWORD"):
        CloudSqlPostgresConfig.from_env(
            {
                "PROOF_OF_AUDIT_STORE_INSTANCE_CONNECTION_NAME": "project:region:instance",
                "PROOF_OF_AUDIT_STORE_DATABASE": "proof_of_audit",
                "PROOF_OF_AUDIT_STORE_USER": "auditor",
                "PROOF_OF_AUDIT_STORE_ENABLE_IAM_AUTH": "false",
            }
        )


def test_cloudsql_postgres_config_parses_iam_auth_settings() -> None:
    config = CloudSqlPostgresConfig.from_env(
        {
            "PROOF_OF_AUDIT_STORE_INSTANCE_CONNECTION_NAME": "project:region:instance",
            "PROOF_OF_AUDIT_STORE_DATABASE": "proof_of_audit",
            "PROOF_OF_AUDIT_STORE_USER": "auditor@example.iam",
            "PROOF_OF_AUDIT_STORE_ENABLE_IAM_AUTH": "true",
            "PROOF_OF_AUDIT_STORE_IP_TYPE": "psc",
        }
    )

    assert config.enable_iam_auth is True
    assert config.password is None
    assert config.ip_type == "psc"
