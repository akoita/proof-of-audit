"""Regression: public Base Sepolia feature surface must stay disclosed (#303)."""

from __future__ import annotations

import json
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
DEPLOYMENT = ROOT_DIR / "deployments" / "base-sepolia.json"
DEPLOYED_VERSION_DOC = ROOT_DIR / "docs" / "DEPLOYED_VERSION.md"
PROTOCOL_DOC = ROOT_DIR / "docs" / "AUDIT_REQUEST_PROTOCOL.md"
MARKETPLACE_VIEW = (
    ROOT_DIR / "web" / "app" / "components" / "views" / "marketplace-view.tsx"
)


def test_base_sepolia_manifest_discloses_marketplace_undeployed() -> None:
    payload = json.loads(DEPLOYMENT.read_text(encoding="utf-8"))
    surface = payload["feature_surface"]
    assert surface["marketplace_audit_request_path"] == (
        "undeployed_on_public_networks"
    )
    assert surface["deployed_constructor_arity"] == 4
    assert surface["source_constructor_arity"] == 8
    assert "AuditRequest marketplace escrow" in payload["undeployed_feature_set"]
    assert payload["docs"]["deployed_version"] == "docs/DEPLOYED_VERSION.md"


def test_deployed_version_doc_exists_and_names_live_address() -> None:
    text = DEPLOYED_VERSION_DOC.read_text(encoding="utf-8")
    assert "0xf2da3947d028b85e597fe1df4633a87ef4a85f24" in text
    assert "undeployed" in text.lower()
    assert "#303" in text or "issues/303" in text


def test_protocol_and_ui_surface_public_caveat() -> None:
    protocol = PROTOCOL_DOC.read_text(encoding="utf-8")
    assert "undeployed" in protocol.lower()
    assert "DEPLOYED_VERSION.md" in protocol

    ui = MARKETPLACE_VIEW.read_text(encoding="utf-8")
    assert "marketplace-undeployed-banner" in ui
    assert "DEPLOYED_VERSION.md" in ui
