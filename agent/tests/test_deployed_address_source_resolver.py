import io
import json
from urllib import error

import pytest

from proof_of_audit_agent.deployed_address_source_resolver import (
    DeployedAddressSourceResolver,
    VerifiedSourceResolutionError,
)


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._buffer = io.BytesIO(payload)

    def read(self, size: int = -1) -> bytes:
        return self._buffer.read(size)

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb


def test_resolver_materializes_sourcify_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.dumps(
        {
            "compilation": {
                "name": "Vault",
                "fullyQualifiedName": "src/Vault.sol:Vault",
            },
            "metadata": {"compiler": {"version": "0.8.28"}},
            "sources": {
                "src/Vault.sol": {"content": "contract Vault {}\n"},
                "src/Helper.sol": {"content": "library Helper {}\n"},
            },
        }
    ).encode("utf-8")

    def fake_urlopen(req, timeout=0):  # type: ignore[no-untyped-def]
        assert req.full_url.endswith(
            "/v2/contract/84532/0xabc0000000000000000000000000000000000000?fields=sources,metadata,compilation"
        )
        assert timeout == 15
        return _FakeResponse(payload)

    monkeypatch.setattr(
        "proof_of_audit_agent.deployed_address_source_resolver.request.urlopen",
        fake_urlopen,
    )

    resolver = DeployedAddressSourceResolver(explorer_api_url=None)
    resolved = resolver.resolve(
        chain_id=84532,
        contract_address="0xAbC0000000000000000000000000000000000000",
    )
    try:
        assert resolved.entry_contract == "Vault"
        assert resolved.source_uri == "sourcify://84532/0xabc0000000000000000000000000000000000000"
        assert (resolved.path / "src" / "Vault.sol").read_text(encoding="utf-8") == "contract Vault {}\n"
        assert (resolved.path / "metadata.json").is_file()
    finally:
        resolved.cleanup()


def test_resolver_falls_back_to_explorer_standard_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sourcify_error = error.HTTPError(
        "https://sourcify.dev/server/v2/contract/84532/0xabc0000000000000000000000000000000000000",
        404,
        "not found",
        hdrs=None,
        fp=None,
    )
    explorer_payload = json.dumps(
        {
            "status": "1",
            "message": "OK",
            "result": [
                {
                    "ContractName": "Vault",
                    "SourceCode": '{{"language":"Solidity","sources":{"src/Vault.sol":{"content":"contract Vault {}\\n"}},"settings":{}}}',
                }
            ],
        }
    ).encode("utf-8")

    def fake_urlopen(req, timeout=0):  # type: ignore[no-untyped-def]
        if "sourcify.dev" in req.full_url:
            raise sourcify_error
        assert "module=contract" in req.full_url
        assert "action=getsourcecode" in req.full_url
        assert "chainid=84532" in req.full_url
        assert "address=0xabc0000000000000000000000000000000000000" in req.full_url
        assert "apikey=test-key" in req.full_url
        return _FakeResponse(explorer_payload)

    monkeypatch.setattr(
        "proof_of_audit_agent.deployed_address_source_resolver.request.urlopen",
        fake_urlopen,
    )

    resolver = DeployedAddressSourceResolver(explorer_api_key="test-key")
    resolved = resolver.resolve(
        chain_id=84532,
        contract_address="0xAbC0000000000000000000000000000000000000",
    )
    try:
        assert resolved.entry_contract == "Vault"
        assert resolved.source_uri == "explorer://84532/0xabc0000000000000000000000000000000000000"
        assert (resolved.path / "src" / "Vault.sol").read_text(encoding="utf-8") == "contract Vault {}\n"
        assert (resolved.path / "metadata.json").is_file()
    finally:
        resolved.cleanup()


def test_resolver_raises_when_no_verified_source_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(req, timeout=0):  # type: ignore[no-untyped-def]
        if "sourcify.dev" in req.full_url:
            raise error.HTTPError(req.full_url, 404, "not found", hdrs=None, fp=None)
        return _FakeResponse(
            json.dumps({"status": "0", "message": "NOTOK", "result": []}).encode("utf-8")
        )

    monkeypatch.setattr(
        "proof_of_audit_agent.deployed_address_source_resolver.request.urlopen",
        fake_urlopen,
    )

    resolver = DeployedAddressSourceResolver(explorer_api_key="test-key")
    with pytest.raises(VerifiedSourceResolutionError):
        resolver.resolve(
            chain_id=84532,
            contract_address="0xAbC0000000000000000000000000000000000000",
        )
