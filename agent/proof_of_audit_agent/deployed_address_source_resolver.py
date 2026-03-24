from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import tempfile
from urllib import error, parse, request


DEFAULT_SOURCIFY_BASE_URL = "https://sourcify.dev/server"
DEFAULT_EXPLORER_API_URL = "https://api.etherscan.io/v2/api"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 15


class VerifiedSourceResolutionError(ValueError):
    """Raised when verified source retrieval cannot materialize a usable source tree."""


@dataclass
class MaterializedVerifiedSource:
    path: Path
    tempdir: tempfile.TemporaryDirectory[str]
    entry_contract: str | None
    source_uri: str

    def cleanup(self) -> None:
        self.tempdir.cleanup()


class DeployedAddressSourceResolver:
    def __init__(
        self,
        *,
        sourcify_base_url: str = DEFAULT_SOURCIFY_BASE_URL,
        explorer_api_url: str | None = DEFAULT_EXPLORER_API_URL,
        explorer_api_key: str | None = None,
        timeout_seconds: int = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self.sourcify_base_url = sourcify_base_url.rstrip("/")
        self.explorer_api_url = explorer_api_url.rstrip("/") if explorer_api_url else None
        self.explorer_api_key = explorer_api_key or None
        self.timeout_seconds = timeout_seconds

    def resolve(
        self,
        *,
        chain_id: int | None,
        contract_address: str | None,
    ) -> MaterializedVerifiedSource:
        normalized_address = self._normalize_address(contract_address)
        if chain_id is None:
            raise VerifiedSourceResolutionError(
                "deployed_address live analysis requires a chain_id"
            )

        sourcify_source = self._resolve_from_sourcify(
            chain_id=chain_id,
            contract_address=normalized_address,
        )
        if sourcify_source is not None:
            return sourcify_source

        explorer_source = self._resolve_from_explorer(
            chain_id=chain_id,
            contract_address=normalized_address,
        )
        if explorer_source is not None:
            return explorer_source

        raise VerifiedSourceResolutionError(
            "No verified source was available for this deployed address."
        )

    def _resolve_from_sourcify(
        self,
        *,
        chain_id: int,
        contract_address: str,
    ) -> MaterializedVerifiedSource | None:
        url = (
            f"{self.sourcify_base_url}/v2/contract/{chain_id}/{contract_address}"
            "?fields=sources,metadata,compilation"
        )
        try:
            payload = self._read_json(url)
        except error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise VerifiedSourceResolutionError(
                f"Sourcify lookup failed with status {exc.code}."
            ) from exc
        except OSError as exc:
            raise VerifiedSourceResolutionError("Sourcify lookup failed.") from exc

        sources = payload.get("sources")
        if not isinstance(sources, dict) or not sources:
            return None
        return self._materialize_sources(
            sources=sources,
            metadata=payload.get("metadata"),
            entry_contract=self._compilation_name(payload),
            source_uri=f"sourcify://{chain_id}/{contract_address}",
        )

    def _resolve_from_explorer(
        self,
        *,
        chain_id: int,
        contract_address: str,
    ) -> MaterializedVerifiedSource | None:
        if not self.explorer_api_url or not self.explorer_api_key:
            return None

        query = parse.urlencode(
            {
                "chainid": str(chain_id),
                "module": "contract",
                "action": "getsourcecode",
                "address": contract_address,
                "apikey": self.explorer_api_key,
            }
        )
        url = f"{self.explorer_api_url}?{query}"
        try:
            payload = self._read_json(url)
        except OSError as exc:
            raise VerifiedSourceResolutionError(
                "Explorer verified-source lookup failed."
            ) from exc

        result = payload.get("result")
        if not isinstance(result, list) or not result:
            return None
        record = result[0]
        if not isinstance(record, dict):
            return None

        source_code = str(record.get("SourceCode") or "").strip()
        if not source_code or source_code.lower() == "contract source code not verified":
            return None

        contract_name = self._optional_string(record.get("ContractName"))
        std_json = self._parse_std_json_input(source_code)
        if std_json is not None:
            sources = std_json.get("sources")
            if not isinstance(sources, dict) or not sources:
                raise VerifiedSourceResolutionError(
                    "Explorer returned a standard-json payload without sources."
                )
            return self._materialize_sources(
                sources=sources,
                metadata=std_json,
                entry_contract=contract_name,
                source_uri=f"explorer://{chain_id}/{contract_address}",
            )

        if contract_name is None:
            contract_name = "VerifiedContract"
        tempdir = tempfile.TemporaryDirectory(prefix="proof-of-audit-address-")
        source_root = Path(tempdir.name) / "source"
        source_root.mkdir(parents=True, exist_ok=True)
        (source_root / f"{contract_name}.sol").write_text(source_code, encoding="utf-8")
        return MaterializedVerifiedSource(
            path=source_root,
            tempdir=tempdir,
            entry_contract=contract_name,
            source_uri=f"explorer://{chain_id}/{contract_address}",
        )

    def _materialize_sources(
        self,
        *,
        sources: dict[str, object],
        metadata: object,
        entry_contract: str | None,
        source_uri: str,
    ) -> MaterializedVerifiedSource:
        tempdir = tempfile.TemporaryDirectory(prefix="proof-of-audit-address-")
        source_root = Path(tempdir.name) / "source"
        source_root.mkdir(parents=True, exist_ok=True)
        try:
            for source_name, source_payload in sources.items():
                if not isinstance(source_name, str) or not source_name.strip():
                    raise VerifiedSourceResolutionError(
                        "Verified source payload contained an invalid path."
                    )
                if not isinstance(source_payload, dict):
                    raise VerifiedSourceResolutionError(
                        "Verified source payload contained an invalid source entry."
                    )
                content = source_payload.get("content")
                if not isinstance(content, str):
                    raise VerifiedSourceResolutionError(
                        f"Verified source content was missing for {source_name}."
                    )
                destination = self._safe_destination(source_root, source_name)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(content, encoding="utf-8")

            if metadata is not None:
                (source_root / "metadata.json").write_text(
                    json.dumps(metadata, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
        except Exception:
            tempdir.cleanup()
            raise

        return MaterializedVerifiedSource(
            path=source_root,
            tempdir=tempdir,
            entry_contract=entry_contract,
            source_uri=source_uri,
        )

    def _read_json(self, url: str) -> dict[str, object]:
        req = request.Request(url, method="GET")
        with request.urlopen(req, timeout=self.timeout_seconds) as response:
            payload = response.read()
        return json.loads(payload.decode("utf-8"))

    def _parse_std_json_input(self, source_code: str) -> dict[str, object] | None:
        normalized = source_code.strip()
        candidates = [normalized]
        if normalized.startswith("{{") and normalized.endswith("}}"):
            candidates.append(normalized[1:-1])
        for candidate in candidates:
            if not candidate.startswith("{"):
                continue
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and parsed.get("sources"):
                return parsed
        return None

    def _compilation_name(self, payload: dict[str, object]) -> str | None:
        compilation = payload.get("compilation")
        if not isinstance(compilation, dict):
            return None
        name = self._optional_string(compilation.get("name"))
        if name:
            return name
        fully_qualified_name = self._optional_string(compilation.get("fullyQualifiedName"))
        if fully_qualified_name and ":" in fully_qualified_name:
            return fully_qualified_name.rsplit(":", 1)[-1]
        return fully_qualified_name

    def _safe_destination(self, root: Path, relative_path: str) -> Path:
        resolved_root = root.resolve()
        destination = (root / relative_path).resolve()
        if not str(destination).startswith(str(resolved_root) + "/") and destination != resolved_root:
            raise VerifiedSourceResolutionError(
                "Verified source payload attempted to write outside the source root."
            )
        return destination

    def _normalize_address(self, contract_address: str | None) -> str:
        text = self._optional_string(contract_address)
        if text is None:
            raise VerifiedSourceResolutionError(
                "deployed_address live analysis requires a contract address"
            )
        return text.lower()

    def _optional_string(self, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
