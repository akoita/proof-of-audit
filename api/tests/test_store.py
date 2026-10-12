from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
from threading import Barrier

import pytest

from proof_of_audit_api.store import (
    CloudSqlPostgresConfig,
    JsonStore,
    PostgresStore,
    SqliteStore,
    create_store,
)


class FakePostgresCursor:
    def __init__(self, connection: "FakePostgresConnection") -> None:
        self.connection = connection
        self.rows: list[tuple[object, ...]] = []

    def execute(self, query: str, parameters: tuple[object, ...]) -> None:
        normalized_query = " ".join(query.split())
        self.connection.connector.queries.append(normalized_query)
        if normalized_query.startswith("CREATE TABLE IF NOT EXISTS audits") or normalized_query.startswith(
            "CREATE TABLE IF NOT EXISTS audit_requests"
        ):
            self.rows = []
            return
        if normalized_query.startswith("INSERT INTO audits"):
            audit_id, encoded_payload = parameters
            self.connection.records[str(audit_id)] = str(encoded_payload)
            self.rows = []
            return
        if normalized_query.startswith("INSERT INTO audit_requests"):
            request_id, encoded_payload = parameters
            if str(request_id) == self.connection.connector.fail_request_id:
                raise RuntimeError("injected request write failure")
            if "DO NOTHING" in normalized_query:
                self.connection.requests.setdefault(
                    str(request_id), str(encoded_payload)
                )
            else:
                self.connection.requests[str(request_id)] = str(encoded_payload)
            self.rows = []
            return
        if normalized_query == "SELECT payload::text FROM audits WHERE id = %s":
            audit_id = str(parameters[0])
            payload = self.connection.records.get(audit_id)
            self.rows = [] if payload is None else [(payload,)]
            return
        if normalized_query == "SELECT payload::text FROM audits ORDER BY id ASC":
            self.rows = [
                (payload,) for _, payload in sorted(self.connection.records.items())
            ]
            return
        if normalized_query == "SELECT 1 FROM audits WHERE id = %s":
            audit_id = str(parameters[0])
            self.rows = [] if audit_id not in self.connection.records else [(1,)]
            return
        if normalized_query == "SELECT payload::text FROM audit_requests WHERE request_id = %s":
            request_id = str(parameters[0])
            payload = self.connection.requests.get(request_id)
            self.rows = [] if payload is None else [(payload,)]
            return
        if normalized_query == "SELECT payload::text FROM audit_requests ORDER BY request_id ASC":
            self.rows = [
                (payload,) for _, payload in sorted(self.connection.requests.items())
            ]
            return
        raise AssertionError(f"unexpected query: {normalized_query}")

    def fetchone(self) -> tuple[object, ...] | None:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[tuple[object, ...]]:
        return list(self.rows)

    def close(self) -> None:
        self.connection.cursor_close_count += 1


class FakePostgresConnection:
    def __init__(self, connector: "FakePostgresConnector") -> None:
        self.connector = connector
        self.records = dict(connector.records)
        self.requests = dict(connector.requests)
        self.commit_count = 0
        self.rollback_count = 0
        self.cursor_close_count = 0
        self.closed = False

    def cursor(self) -> FakePostgresCursor:
        return FakePostgresCursor(self)

    def commit(self) -> None:
        self.connector.records = dict(self.records)
        self.connector.requests = dict(self.requests)
        self.commit_count += 1

    def rollback(self) -> None:
        self.records = dict(self.connector.records)
        self.requests = dict(self.connector.requests)
        self.rollback_count += 1

    def close(self) -> None:
        self.closed = True


class FakePostgresConnector:
    def __init__(self) -> None:
        self.records: dict[str, str] = {}
        self.requests: dict[str, str] = {}
        self.closed = False
        self.calls: list[dict[str, object]] = []
        self.connections: list[FakePostgresConnection] = []
        self.queries: list[str] = []
        self.fail_request_id: str | None = None

    def connect(self, instance_connection_name: str, driver: str, **kwargs: object) -> FakePostgresConnection:
        self.calls.append(
            {
                "instance_connection_name": instance_connection_name,
                "driver": driver,
                **kwargs,
            }
        )
        connection = FakePostgresConnection(self)
        self.connections.append(connection)
        return connection

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


def test_sqlite_audit_import_skips_request_catalog(tmp_path: Path) -> None:
    catalog_path = tmp_path / "audit-requests.json"
    catalog_path.write_text(
        json.dumps({"id": "catalog-as-audit", "items": [{"request_id": "req-1"}]}),
        encoding="utf-8",
    )
    store = SqliteStore(tmp_path / "audits.sqlite3", legacy_root=tmp_path)

    store.import_legacy_json(tmp_path)

    assert store.read("catalog-as-audit") is None
    assert store.list_all() == []


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


def test_postgres_audit_import_skips_request_catalog(tmp_path: Path) -> None:
    catalog_path = tmp_path / "audit-requests.json"
    catalog_path.write_text(
        json.dumps({"id": "catalog-as-audit", "items": [{"request_id": "req-1"}]}),
        encoding="utf-8",
    )
    store = PostgresStore(
        build_postgres_config(),
        legacy_root=tmp_path,
        connector_factory=FakePostgresConnector,
    )

    store.import_legacy_json(tmp_path)

    assert store.read("catalog-as-audit") is None
    assert store.list_all() == []


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


def test_sqlite_store_persists_requests_and_isolates_audit_ids(tmp_path: Path) -> None:
    database_path = tmp_path / "audits.sqlite3"
    store = SqliteStore(database_path)
    audit_payload = {"id": "shared-id", "kind": "audit"}
    request_payload = {"request_id": "shared-id", "kind": "request"}

    store.write("shared-id", audit_payload)
    store.write_request("shared-id", request_payload)

    reloaded = SqliteStore(database_path)
    assert reloaded.read("shared-id") == audit_payload
    assert reloaded.read_request("shared-id") == request_payload
    assert reloaded.list_all() == [audit_payload]
    assert reloaded.list_requests() == [request_payload]


def test_sqlite_store_concurrent_request_writes_keep_every_row(tmp_path: Path) -> None:
    database_path = tmp_path / "shared.sqlite3"
    stores = [SqliteStore(database_path) for _ in range(4)]
    payloads = [
        {"request_id": f"request-{index}", "value": index}
        for index in range(80)
    ]

    def write(index: int) -> None:
        stores[index % len(stores)].write_request(
            payloads[index]["request_id"], payloads[index]
        )

    with ThreadPoolExecutor(max_workers=len(stores)) as executor:
        list(executor.map(write, range(len(payloads))))

    assert {item["request_id"] for item in stores[0].list_requests()} == {
        item["request_id"] for item in payloads
    }


def test_sqlite_store_concurrent_legacy_imports_are_idempotent(tmp_path: Path) -> None:
    database_path = tmp_path / "shared.sqlite3"
    legacy_path = tmp_path / "audit-requests.json"
    payloads = [
        {"request_id": f"request-{index}", "value": index}
        for index in range(24)
    ]
    legacy_path.write_text(json.dumps({"items": payloads}), encoding="utf-8")
    barrier = Barrier(4)

    def import_requests() -> None:
        store = SqliteStore(database_path)
        barrier.wait()
        store.import_legacy_requests(legacy_path)

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda _: import_requests(), range(4)))

    assert len(SqliteStore(database_path).list_requests()) == len(payloads)


def test_sqlite_legacy_request_import_preserves_existing_rows_and_backup(
    tmp_path: Path,
) -> None:
    legacy_path = tmp_path / "audit-requests.json"
    legacy_bytes = json.dumps(
        {
            "items": [
                {"request_id": "existing", "status": "legacy"},
                {"id": 17, "status": "legacy-integer-id"},
            ]
        }
    ).encode()
    legacy_path.write_bytes(legacy_bytes)
    store = SqliteStore(tmp_path / "audits.sqlite3")
    store.write_request("existing", {"request_id": "existing", "status": "newer"})

    store.import_legacy_requests(legacy_path)
    assert store.read_request("17") == {"id": 17, "status": "legacy-integer-id"}
    store.write_request("17", {"request_id": "17", "status": "updated"})
    store.import_legacy_requests(legacy_path)

    assert store.read_request("existing") == {
        "request_id": "existing",
        "status": "newer",
    }
    assert store.read_request("17") == {"request_id": "17", "status": "updated"}
    assert legacy_path.read_bytes() == legacy_bytes


@pytest.mark.parametrize(
    ("items", "message"),
    [
        ([{"request_id": "valid"}, {"request_id": {"private": "value"}}], "invalid request ID"),
        ([{"request_id": "duplicate"}, {"id": "duplicate"}], "duplicate request IDs"),
        ([{"request_id": "valid"}, "malformed"], "malformed item"),
    ],
)
def test_sqlite_legacy_request_import_validates_before_writing(
    tmp_path: Path,
    items: list[object],
    message: str,
) -> None:
    legacy_path = tmp_path / "audit-requests.json"
    legacy_path.write_text(json.dumps({"items": items}), encoding="utf-8")
    store = SqliteStore(tmp_path / "audits.sqlite3")

    with pytest.raises(ValueError, match=message) as error:
        store.import_legacy_requests(legacy_path)

    assert "private" not in str(error.value)
    assert "value" not in str(error.value)
    assert store.list_requests() == []


def test_sqlite_legacy_request_import_rolls_back_transaction_on_write_failure(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "audits.sqlite3"
    store = SqliteStore(database_path)
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        CREATE TRIGGER fail_second_request
        BEFORE INSERT ON audit_requests
        WHEN NEW.request_id = 'second'
        BEGIN
            SELECT RAISE(ABORT, 'injected request insert failure');
        END
        """
    )
    connection.commit()
    connection.close()
    legacy_path = tmp_path / "audit-requests.json"
    legacy_path.write_text(
        json.dumps(
            {
                "items": [
                    {"request_id": "first"},
                    {"request_id": "second"},
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(sqlite3.IntegrityError):
        store.import_legacy_requests(legacy_path)

    assert store.list_requests() == []


def test_json_store_keeps_request_catalog_and_sidecar_out_of_audit_listing(
    tmp_path: Path,
) -> None:
    store = JsonStore(tmp_path)
    store.write("audit-1", {"id": "audit-1", "kind": "audit"})
    catalog_path = tmp_path / "audit-requests.json"
    catalog_bytes = json.dumps(
        {"items": [{"request_id": "request-1", "kind": "request"}]}
    ).encode()
    catalog_path.write_bytes(catalog_bytes)

    store.import_legacy_requests(catalog_path)

    assert store.read_request("request-1") == {
        "request_id": "request-1",
        "kind": "request",
    }
    assert store.list_all() == [{"id": "audit-1", "kind": "audit"}]
    assert catalog_path.read_bytes() == catalog_bytes


def test_postgres_store_request_methods_upsert_and_close_connections(
    tmp_path: Path,
) -> None:
    connector = FakePostgresConnector()
    store = PostgresStore(build_postgres_config(), connector_factory=lambda: connector)
    request_payload = {"request_id": "request-1", "status": "open"}

    store.write_request("request-1", request_payload)
    assert store.read_request("request-1") == request_payload
    assert store.list_requests() == [request_payload]

    assert any(
        query.startswith("INSERT INTO audit_requests")
        and "ON CONFLICT (request_id) DO UPDATE" in query
        for query in connector.queries
    )
    assert all(connection.closed for connection in connector.connections)

    connector.fail_request_id = "write-failure"
    with pytest.raises(RuntimeError, match="injected request write failure"):
        store.write_request("write-failure", {"request_id": "write-failure"})
    assert connector.connections[-1].rollback_count == 1
    assert connector.connections[-1].closed


def test_postgres_legacy_request_import_rolls_back_and_closes_on_failure(
    tmp_path: Path,
) -> None:
    connector = FakePostgresConnector()
    store = PostgresStore(build_postgres_config(), connector_factory=lambda: connector)
    connector.fail_request_id = "second"
    legacy_path = tmp_path / "audit-requests.json"
    legacy_path.write_text(
        json.dumps(
            {
                "items": [
                    {"request_id": "first"},
                    {"request_id": "second"},
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="injected request write failure"):
        store.import_legacy_requests(legacy_path)

    assert connector.requests == {}
    assert connector.connections[-1].rollback_count == 1
    assert connector.connections[-1].closed
