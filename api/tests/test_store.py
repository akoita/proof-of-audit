from __future__ import annotations

import json
from pathlib import Path

from proof_of_audit_api.store import JsonStore, SqliteStore, create_store


def test_sqlite_store_persists_records(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "audits.sqlite3")
    payload = {"id": "audit-1", "status": "draft"}

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


def test_create_store_defaults_to_sqlite(tmp_path: Path) -> None:
    store = create_store(root=tmp_path)

    assert isinstance(store, SqliteStore)


def test_create_store_supports_json_mode(tmp_path: Path) -> None:
    store = create_store(root=tmp_path, kind="json")

    assert isinstance(store, JsonStore)
