from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any, Protocol


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


def create_store(
    *,
    root: Path,
    kind: str = "sqlite",
    database_path: Path | None = None,
) -> AuditStore:
    normalized_kind = kind.strip().lower() if kind else "sqlite"
    if normalized_kind == "json":
        return JsonStore(root)
    if normalized_kind == "sqlite":
        return SqliteStore(
            database_path or root / "audits.sqlite3",
            legacy_root=root,
        )
    raise ValueError(f"unsupported store kind: {kind}")
