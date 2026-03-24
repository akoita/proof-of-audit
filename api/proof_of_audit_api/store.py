from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable, Mapping, Protocol


def _parse_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if not normalized:
        return default
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"invalid boolean value: {value}")


def _record_target_key(record: dict[str, Any]) -> str:
    target_key = record.get("target_key")
    if isinstance(target_key, str) and target_key:
        return target_key.strip().lower()

    contract_address = record.get("contract_address")
    if isinstance(contract_address, str) and contract_address:
        return contract_address.strip().lower()

    submission = record.get("submission")
    if isinstance(submission, dict):
        submission_contract = submission.get("contract_address")
        if isinstance(submission_contract, str) and submission_contract:
            return submission_contract.strip().lower()

    return ""


class AuditStore(Protocol):
    def write(self, audit_id: str, payload: dict[str, Any]) -> None: ...

    def read(self, audit_id: str) -> dict[str, Any] | None: ...

    def list_all(self) -> list[dict[str, Any]]: ...

    def list_by_target_key(self, target_key: str) -> list[dict[str, Any]]: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class CloudSqlPostgresConfig:
    instance_connection_name: str
    database: str
    user: str
    password: str | None = None
    enable_iam_auth: bool = False
    ip_type: str = "public"

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "CloudSqlPostgresConfig":
        values = {
            "PROOF_OF_AUDIT_STORE_INSTANCE_CONNECTION_NAME": str(
                env.get("PROOF_OF_AUDIT_STORE_INSTANCE_CONNECTION_NAME") or ""
            ).strip(),
            "PROOF_OF_AUDIT_STORE_DATABASE": str(
                env.get("PROOF_OF_AUDIT_STORE_DATABASE") or ""
            ).strip(),
            "PROOF_OF_AUDIT_STORE_USER": str(
                env.get("PROOF_OF_AUDIT_STORE_USER") or ""
            ).strip(),
        }
        missing = [key for key, value in values.items() if not value]
        if missing:
            raise ValueError(
                "missing Cloud SQL PostgreSQL settings: " + ", ".join(sorted(missing))
            )

        enable_iam_auth = _parse_bool(
            env.get("PROOF_OF_AUDIT_STORE_ENABLE_IAM_AUTH"),
            default=False,
        )
        password = str(env.get("PROOF_OF_AUDIT_STORE_PASSWORD") or "").strip() or None
        if not enable_iam_auth and password is None:
            raise ValueError(
                "PROOF_OF_AUDIT_STORE_PASSWORD is required when "
                "PROOF_OF_AUDIT_STORE_ENABLE_IAM_AUTH is false"
            )

        ip_type = str(env.get("PROOF_OF_AUDIT_STORE_IP_TYPE") or "public").strip().lower()
        if ip_type not in {"public", "private", "psc"}:
            raise ValueError(
                "PROOF_OF_AUDIT_STORE_IP_TYPE must be one of: public, private, psc"
            )

        return cls(
            instance_connection_name=values[
                "PROOF_OF_AUDIT_STORE_INSTANCE_CONNECTION_NAME"
            ],
            database=values["PROOF_OF_AUDIT_STORE_DATABASE"],
            user=values["PROOF_OF_AUDIT_STORE_USER"],
            password=password,
            enable_iam_auth=enable_iam_auth,
            ip_type=ip_type,
        )


class JsonStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def write(self, audit_id: str, payload: dict[str, Any]) -> None:
        path = self.root / f"{audit_id}.json"
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def read(self, audit_id: str) -> dict[str, Any] | None:
        path = self.root / f"{audit_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list_all(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for path in sorted(self.root.glob("*.json")):
            try:
                records.append(json.loads(path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
        return records

    def list_by_target_key(self, target_key: str) -> list[dict[str, Any]]:
        normalized_target_key = target_key.strip().lower()
        return [
            record
            for record in self.list_all()
            if _record_target_key(record) == normalized_target_key
        ]

    def close(self) -> None:
        return None


class SqliteStore:
    def __init__(self, database_path: Path, *, legacy_root: Path | None = None) -> None:
        self.database_path = database_path
        self.legacy_root = legacy_root
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        self._import_legacy_if_needed()

    def write(self, audit_id: str, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, sort_keys=True)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO audits (id, payload)
                VALUES (?, ?)
                ON CONFLICT(id) DO UPDATE SET payload = excluded.payload
                """,
                (audit_id, encoded),
            )

    def read(self, audit_id: str) -> dict[str, Any] | None:
        self._import_legacy_if_needed()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM audits WHERE id = ?",
                (audit_id,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(str(row[0]))

    def list_all(self) -> list[dict[str, Any]]:
        self._import_legacy_if_needed()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM audits ORDER BY id ASC"
            ).fetchall()
        return [json.loads(str(row[0])) for row in rows]

    def list_by_target_key(self, target_key: str) -> list[dict[str, Any]]:
        normalized_target_key = target_key.strip().lower()
        return [
            record
            for record in self.list_all()
            if _record_target_key(record) == normalized_target_key
        ]

    def import_legacy_json(self, root: Path) -> None:
        if not root.exists():
            return
        for path in sorted(root.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            audit_id = payload.get("id")
            if not isinstance(audit_id, str) or not audit_id:
                continue
            if self._contains(audit_id):
                continue
            self._write_without_import(audit_id, payload)

    def _write_without_import(self, audit_id: str, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, sort_keys=True)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO audits (id, payload)
                VALUES (?, ?)
                ON CONFLICT(id) DO UPDATE SET payload = excluded.payload
                """,
                (audit_id, encoded),
            )

    def _import_legacy_if_needed(self) -> None:
        if self.legacy_root is None:
            return
        for path in sorted(self.legacy_root.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            audit_id = payload.get("id")
            if not isinstance(audit_id, str) or not audit_id:
                continue
            if not self._contains(audit_id):
                self._write_without_import(audit_id, payload)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS audits (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _contains(self, audit_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM audits WHERE id = ?",
                (audit_id,),
            ).fetchone()
        return row is not None

    def close(self) -> None:
        return None


def _build_cloudsql_connector(ip_type: str) -> tuple[Any, Any]:
    from google.cloud.sql.connector import Connector, IPTypes

    ip_types = {
        "public": IPTypes.PUBLIC,
        "private": IPTypes.PRIVATE,
        "psc": IPTypes.PSC,
    }
    return Connector(refresh_strategy="lazy"), ip_types[ip_type]


class PostgresStore:
    def __init__(
        self,
        config: CloudSqlPostgresConfig,
        *,
        legacy_root: Path | None = None,
        connector_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.config = config
        self.legacy_root = legacy_root
        if connector_factory is None:
            self._connector, self._ip_type = _build_cloudsql_connector(config.ip_type)
        else:
            self._connector = connector_factory()
            self._ip_type = config.ip_type
        self._initialize()
        self._import_legacy_if_needed()

    def write(self, audit_id: str, payload: dict[str, Any]) -> None:
        self._write_without_import(audit_id, payload)

    def read(self, audit_id: str) -> dict[str, Any] | None:
        self._import_legacy_if_needed()
        row = self._fetchone(
            "SELECT payload::text FROM audits WHERE id = %s",
            (audit_id,),
        )
        if row is None:
            return None
        return json.loads(str(row[0]))

    def list_all(self) -> list[dict[str, Any]]:
        self._import_legacy_if_needed()
        rows = self._fetchall("SELECT payload::text FROM audits ORDER BY id ASC")
        return [json.loads(str(row[0])) for row in rows]

    def list_by_target_key(self, target_key: str) -> list[dict[str, Any]]:
        normalized_target_key = target_key.strip().lower()
        return [
            record
            for record in self.list_all()
            if _record_target_key(record) == normalized_target_key
        ]

    def import_legacy_json(self, root: Path) -> None:
        if not root.exists():
            return
        for path in sorted(root.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            audit_id = payload.get("id")
            if not isinstance(audit_id, str) or not audit_id:
                continue
            if self._contains(audit_id):
                continue
            self._write_without_import(audit_id, payload)

    def close(self) -> None:
        close = getattr(self._connector, "close", None)
        if callable(close):
            close()

    def _write_without_import(self, audit_id: str, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, sort_keys=True)
        self._execute(
            """
            INSERT INTO audits (id, payload)
            VALUES (%s, %s::jsonb)
            ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload
            """,
            (audit_id, encoded),
        )

    def _import_legacy_if_needed(self) -> None:
        if self.legacy_root is None:
            return
        for path in sorted(self.legacy_root.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            audit_id = payload.get("id")
            if not isinstance(audit_id, str) or not audit_id:
                continue
            if not self._contains(audit_id):
                self._write_without_import(audit_id, payload)

    def _initialize(self) -> None:
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS audits (
                id TEXT PRIMARY KEY,
                payload JSONB NOT NULL
            )
            """
        )

    def _connect(self) -> Any:
        kwargs: dict[str, Any] = {
            "user": self.config.user,
            "db": self.config.database,
            "ip_type": self._ip_type,
            "enable_iam_auth": self.config.enable_iam_auth,
        }
        if not self.config.enable_iam_auth and self.config.password is not None:
            kwargs["password"] = self.config.password
        return self._connector.connect(
            self.config.instance_connection_name,
            "pg8000",
            **kwargs,
        )

    def _execute(self, query: str, parameters: tuple[Any, ...] = ()) -> None:
        connection = self._connect()
        try:
            cursor = connection.cursor()
            try:
                cursor.execute(query, parameters)
            finally:
                close_cursor = getattr(cursor, "close", None)
                if callable(close_cursor):
                    close_cursor()
            commit = getattr(connection, "commit", None)
            if callable(commit):
                commit()
        finally:
            connection.close()

    def _fetchone(
        self, query: str, parameters: tuple[Any, ...] = ()
    ) -> tuple[Any, ...] | None:
        connection = self._connect()
        try:
            cursor = connection.cursor()
            try:
                cursor.execute(query, parameters)
                row = cursor.fetchone()
            finally:
                close_cursor = getattr(cursor, "close", None)
                if callable(close_cursor):
                    close_cursor()
            commit = getattr(connection, "commit", None)
            if callable(commit):
                commit()
            return row
        finally:
            connection.close()

    def _fetchall(
        self, query: str, parameters: tuple[Any, ...] = ()
    ) -> list[tuple[Any, ...]]:
        connection = self._connect()
        try:
            cursor = connection.cursor()
            try:
                cursor.execute(query, parameters)
                rows = cursor.fetchall()
            finally:
                close_cursor = getattr(cursor, "close", None)
                if callable(close_cursor):
                    close_cursor()
            commit = getattr(connection, "commit", None)
            if callable(commit):
                commit()
            return list(rows)
        finally:
            connection.close()

    def _contains(self, audit_id: str) -> bool:
        row = self._fetchone(
            "SELECT 1 FROM audits WHERE id = %s",
            (audit_id,),
        )
        return row is not None


def create_store(
    *,
    root: Path,
    kind: str = "sqlite",
    database_path: Path | None = None,
    postgres_config: CloudSqlPostgresConfig | None = None,
) -> AuditStore:
    normalized_kind = kind.strip().lower() if kind else "sqlite"
    if normalized_kind == "json":
        return JsonStore(root)
    if normalized_kind == "sqlite":
        return SqliteStore(
            database_path or root / "audits.sqlite3",
            legacy_root=root,
        )
    if normalized_kind == "cloudsql-postgres":
        if postgres_config is None:
            raise ValueError(
                "cloudsql-postgres store requires CloudSqlPostgresConfig settings"
            )
        return PostgresStore(
            postgres_config,
            legacy_root=root,
        )
    raise ValueError(f"unsupported store kind: {kind}")
