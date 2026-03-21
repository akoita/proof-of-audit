from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from typing import Any
from urllib import error, request


DEFAULT_API_URL = "http://127.0.0.1:8080"

# ── ANSI helpers (no external deps) ──────────────────────────────────────────

_NO_COLOR = False


def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if not hasattr(sys.stdout, "isatty"):
        return False
    return sys.stdout.isatty()


class C:
    """ANSI color codes."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"

    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    MAGENTA = "\033[35m"
    WHITE = "\033[97m"
    GRAY = "\033[90m"

    BG_CYAN = "\033[46m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_RED = "\033[41m"
    BG_MAGENTA = "\033[45m"


def c(text: str, *codes: str) -> str:
    if _NO_COLOR:
        return text
    prefix = "".join(codes)
    return f"{prefix}{text}{C.RESET}"


# ── Typing / timing helpers ──────────────────────────────────────────────────

_TYPING_DELAY = 0.0  # seconds per character
_PAUSE_BETWEEN = 0.8  # seconds between phases
_NO_SLEEP = False


def _type_print(text: str, *, end: str = "\n") -> None:
    if _TYPING_DELAY > 0 and not _NO_SLEEP:
        for ch in text:
            sys.stdout.write(ch)
            sys.stdout.flush()
            time.sleep(_TYPING_DELAY)
        sys.stdout.write(end)
        sys.stdout.flush()
    else:
        print(text, end=end)


def _pause(factor: float = 1.0) -> None:
    if not _NO_SLEEP and _PAUSE_BETWEEN > 0:
        time.sleep(_PAUSE_BETWEEN * factor)


# ── Layout helpers ───────────────────────────────────────────────────────────

def _term_width() -> int:
    return shutil.get_terminal_size((120, 36)).columns


def _hr() -> None:
    w = min(_term_width(), 100)
    print(c("─" * w, C.DIM))


def _blank() -> None:
    print()


def _phase_header(emoji: str, title: str, subtitle: str) -> None:
    _blank()
    _hr()
    _type_print(f"  {emoji}  {c(title, C.BOLD, C.CYAN)}")
    _type_print(f"     {c(subtitle, C.DIM, C.ITALIC)}")
    _hr()
    _blank()


def _narrative(text: str) -> None:
    _type_print(c(f"  ▸ {text}", C.WHITE))
    _blank()


def _curl_line(cmd: str) -> None:
    _type_print(c(f"  $ {cmd}", C.GRAY, C.DIM))


def _field(label: str, value: str, *, indent: int = 4) -> None:
    pad = " " * indent
    _type_print(f"{pad}{c(label + ':', C.CYAN)}  {c(str(value), C.YELLOW)}")


def _status_badge(label: str, *, ok: bool = True) -> None:
    if ok:
        badge = c(f" ✓ {label} ", C.BOLD, C.BG_GREEN, C.WHITE)
    else:
        badge = c(f" ✗ {label} ", C.BOLD, C.BG_RED, C.WHITE)
    _type_print(f"    {badge}")


def _mini_json(payload: dict[str, Any], keys: list[str], *, indent: int = 4) -> None:
    for key in keys:
        val = payload
        for part in key.split("."):
            if isinstance(val, dict):
                val = val.get(part, "—")
            else:
                val = "—"
                break
        display_key = key.split(".")[-1]
        _field(display_key, str(val), indent=indent)


def _wei_to_eth(wei: int | str | None) -> str:
    if wei is None:
        return "—"
    return f"{int(wei) / 1e18:.4f} ETH"


def _short_hash(h: str | None) -> str:
    if not h or len(h) < 14:
        return h or "—"
    return f"{h[:10]}…{h[-4:]}"


def _box(lines: list[str], *, title: str = "") -> None:
    w = min(_term_width(), 90)
    inner = w - 4
    _blank()
    if title:
        pad_left = (inner - len(title)) // 2
        pad_right = inner - len(title) - pad_left
        _type_print(c(f"  ╔{'═' * pad_left} {title} {'═' * pad_right}╗", C.BOLD, C.CYAN))
    else:
        _type_print(c(f"  ╔{'═' * inner}══╗", C.BOLD, C.CYAN))
    for line in lines:
        visible_len = len(line.replace(C.RESET, "").replace(C.BOLD, "").replace(C.DIM, "")
                          .replace(C.CYAN, "").replace(C.GREEN, "").replace(C.YELLOW, "")
                          .replace(C.RED, "").replace(C.MAGENTA, "").replace(C.WHITE, "")
                          .replace(C.GRAY, "").replace(C.ITALIC, ""))
        padding = max(0, inner - visible_len)
        _type_print(c("  ║ ", C.CYAN) + line + " " * padding + c(" ║", C.CYAN))
    _type_print(c(f"  ╚{'═' * inner}══╝", C.BOLD, C.CYAN))
    _blank()


# ── API helpers ──────────────────────────────────────────────────────────────

def api_request(
    base_url: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(
        f"{base_url}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with request.urlopen(req) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError as json_error:
            raise RuntimeError(f"non-json API error from {path}: {raw}") from json_error


# ── Summarizers ──────────────────────────────────────────────────────────────

def summarize_auditor(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "service_id": payload["service_id"],
        "capability": payload["capability"],
        "agent_id": payload.get("agent_id"),
        "agent_registry": payload.get("agent_registry"),
        "identity_source": payload.get("identity_source"),
        "validation_registry_address": payload.get("validation_registry_address"),
        "submission_modes": payload["submission_modes"],
        "resolution_modes": payload["resolution_modes"],
    }


def summarize_registration(payload: dict[str, Any]) -> dict[str, Any]:
    extension = payload["x-proof-of-audit"]
    return {
        "type": payload["type"],
        "supportedTrust": payload["supportedTrust"],
        "registrations": payload["registrations"],
        "service_endpoints": payload["services"],
        "extension": {
            "id": extension["id"],
            "serviceType": extension["serviceType"],
            "resolutionPolicy": extension["resolutionPolicy"],
        },
    }


def summarize_config(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "network": payload["network"],
        "chain_id": payload["chain_id"],
        "contract_address": payload["contract_address"],
        "required_stake_wei": payload["required_stake_wei"],
        "required_challenge_bond_wei": payload["required_challenge_bond_wei"],
        "challenge_window_seconds": payload["challenge_window_seconds"],
    }


def summarize_fixture(payload: dict[str, Any], fixture_id: str) -> dict[str, Any]:
    fixtures = payload.get("items", [])
    fixture = next((item for item in fixtures if item["id"] == fixture_id), None)
    if fixture is None:
        available = ", ".join(sorted(item["id"] for item in fixtures))
        raise RuntimeError(
            f"fixture '{fixture_id}' not found; available fixtures: {available}"
        )
    return {
        "id": fixture["id"],
        "benchmark_id": fixture["benchmark_id"],
        "address": fixture["address"],
        "challenge_proof_uri": fixture["challenge_proof_uri"],
        "note": fixture["note"],
    }


def summarize_audit(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": payload["id"],
        "status": payload["status"],
        "agent": {
            "id": payload["agent"]["id"],
            "name": payload["agent"]["name"],
            "version": payload["agent"]["version"],
        },
        "submission": payload["submission"],
        "report": {
            "summary": payload["report"]["summary"],
            "confidence": payload["report"]["confidence"],
            "finding_count": payload["report"]["finding_count"],
            "max_severity": payload["report"]["max_severity"],
            "report_hash": payload["report"]["report_hash"],
        },
        "onchain": payload.get("onchain"),
        "challenge": payload.get("challenge"),
        "validation": payload.get("validation"),
    }


# ── CLI ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the terminal-first Proof-of-Audit agent demo."
    )
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--fixture-id", default="clean-vault")
    parser.add_argument("--submitted-by", default="terminal-agent")
    parser.add_argument("--challenger", default="terminal-challenger")
    parser.add_argument("--pause-seconds", type=float, default=0.8)
    parser.add_argument("--no-sleep", action="store_true")
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument(
        "--typing-speed",
        choices=["instant", "fast", "slow"],
        default="fast",
        help="Typing effect speed (instant=0, fast=0.008s, slow=0.025s per char)",
    )
    parser.add_argument(
        "--show-deployment",
        action="store_true",
        help="Show live Base Sepolia deployment info alongside the demo flow",
    )
    return parser.parse_args()


# ── Demo flow ────────────────────────────────────────────────────────────────

def main() -> int:
    global _NO_COLOR, _TYPING_DELAY, _PAUSE_BETWEEN, _NO_SLEEP

    args = parse_args()
    base_url = args.api_url.rstrip("/")
    _NO_SLEEP = args.no_sleep
    _PAUSE_BETWEEN = args.pause_seconds

    if args.no_color or not _supports_color():
        _NO_COLOR = True

    speed_map = {"instant": 0.0, "fast": 0.008, "slow": 0.025}
    _TYPING_DELAY = speed_map[args.typing_speed]

    # ── Title banner ─────────────────────────────────────────────────────
    _blank()
    _box(
        [
            c("PROOF-OF-AUDIT", C.BOLD, C.WHITE),
            c("Agent Trust & Enforcement Infrastructure", C.DIM),
            "",
            c("Trust comes from visible economic commitment,", C.ITALIC, C.WHITE),
            c("not branding.", C.ITALIC, C.WHITE),
        ],
        title="🛡️  Demo",
    )
    _pause(0.5)

    # ── Live deployment info (opt-in) ────────────────────────────────
    if args.show_deployment:
        _blank()
        _hr()
        _type_print(f"  🌐  {c('LIVE DEPLOYMENT — Base Sepolia', C.BOLD, C.CYAN)}")
        _hr()
        _blank()
        _narrative(
            "This same flow runs on Base Sepolia with real ETH at stake."
        )
        _field(
            "ProofOfAudit",
            "0xf2dA3947d028b85e597Fe1Df4633a87eF4A85F24",
        )
        _field(
            "Basescan",
            "https://sepolia.basescan.org/address/0xf2dA3947d028b85e597Fe1Df4633a87eF4A85F24",
        )
        _field(
            "IdentityRegistry",
            "0x8004A818BFB912233c491871b3d84c89A494BD9e",
        )
        _field(
            "ValidationRegistry",
            "0x8004B663056A597Dffe9eCcC1965A193B7388713",
        )
        _blank()
        _status_badge("Verified on Base Sepolia")
        _pause()

    # ── Phase 1: Discover ────────────────────────────────────────────────
    _phase_header(
        "🔍",
        "PHASE 1 — Discover the Auditor",
        "Who is the agent? Can I trust it?",
    )
    _narrative(
        "An agent caller starts by discovering the auditor identity, its"
    )
    _narrative(
        "ERC-8004 registration, and the active chain configuration."
    )
    _pause(0.5)

    # /auditor
    _curl_line(f"curl -s {base_url}/auditor")
    status_code, auditor = api_request(base_url, "GET", "/auditor")
    if status_code != 200:
        raise RuntimeError(f"/auditor returned {status_code}")

    auditor_summary = summarize_auditor(auditor)
    _blank()
    _field("Service ID", auditor_summary["service_id"])
    _field("Capability", auditor_summary["capability"])
    _field("Agent ID", auditor_summary.get("agent_id", "—"))
    _field("Identity source", auditor_summary.get("identity_source", "—"))
    _field("Resolution modes", ", ".join(auditor_summary["resolution_modes"]))
    _field("Submission modes", ", ".join(auditor_summary["submission_modes"]))
    _blank()
    _status_badge("Auditor discovered")
    _pause()

    # /auditor/registration
    _blank()
    _curl_line(f"curl -s {base_url}/auditor/registration")
    status_code, registration = api_request(base_url, "GET", "/auditor/registration")
    if status_code != 200:
        raise RuntimeError(f"/auditor/registration returned {status_code}")

    reg = summarize_registration(registration)
    _blank()
    _field("Type", reg["type"])
    _field("Trust model", ", ".join(reg["supportedTrust"]))
    _field("Service type", reg["extension"]["serviceType"])
    _field("Resolution policy", reg["extension"]["resolutionPolicy"])
    if reg["registrations"]:
        r = reg["registrations"][0]
        _field("Agent registry", _short_hash(r.get("agentRegistry", "—")))
    _blank()
    _status_badge("ERC-8004 registration verified")
    _pause()

    # /config
    _blank()
    _curl_line(f"curl -s {base_url}/config")
    status_code, config = api_request(base_url, "GET", "/config")
    if status_code != 200:
        raise RuntimeError(f"/config returned {status_code}")

    cfg = summarize_config(config)
    _blank()
    _field("Network", cfg["network"])
    _field("Chain ID", cfg["chain_id"])
    _field("Contract", _short_hash(cfg["contract_address"]))
    _field("Required stake", _wei_to_eth(cfg["required_stake_wei"]))
    _field("Challenge bond", _wei_to_eth(cfg["required_challenge_bond_wei"]))
    _blank()
    _status_badge("Chain configuration loaded")
    _pause()

    # ── Phase 2: Select fixture ──────────────────────────────────────────
    _phase_header(
        "📋",
        "PHASE 2 — Select a Benchmark Contract",
        "Pick a known contract to audit.",
    )
    _narrative(
        "The demo uses a curated fixture. Plain proof-URI evidence goes"
    )
    _narrative(
        f"to manual review; executable evidence gets an advisory verifier verdict."
    )
    _pause(0.3)

    _curl_line(f"curl -s {base_url}/fixtures")
    status_code, fixtures = api_request(base_url, "GET", "/fixtures")
    if status_code != 200:
        raise RuntimeError(f"/fixtures returned {status_code}")

    fixture = summarize_fixture(fixtures, args.fixture_id)
    _blank()
    _field("Fixture", fixture["id"])
    _field("Benchmark", fixture["benchmark_id"])
    _field("Address", _short_hash(fixture["address"]))
    _field("Challenge PoC", fixture["challenge_proof_uri"])
    _field("Note", fixture["note"])
    _blank()
    _status_badge(f"Fixture '{fixture['id']}' selected")
    _pause()

    # ── Phase 3: Create draft claim ──────────────────────────────────────
    _phase_header(
        "📝",
        "PHASE 3 — Create a Draft Claim",
        "The agent produces a review judgment.",
    )
    _narrative(
        "The auditor analyzes the contract and produces a review claim."
    )
    _narrative(
        "At this stage it is only an uncommitted draft."
    )
    _pause(0.3)

    create_payload = {
        "input_kind": "demo_fixture",
        "fixture_id": fixture["id"],
        "submitted_by": args.submitted_by,
    }
    _curl_line(
        f"curl -s -X POST {base_url}/audits "
        f"-H 'content-type: application/json' "
        f"-d '{json.dumps(create_payload)}'"
    )
    status_code, created = api_request(base_url, "POST", "/audits", create_payload)
    if status_code != 201:
        raise RuntimeError(f"/audits returned {status_code}: {created}")

    audit = summarize_audit(created)
    audit_id = audit["id"]
    _blank()
    _field("Audit ID", audit_id)
    _field("Status", c(audit["status"].upper(), C.YELLOW, C.BOLD))
    _field("Agent", f"{audit['agent']['name']} v{audit['agent']['version']}")
    _field("Summary", audit["report"]["summary"])
    _field("Confidence", audit["report"]["confidence"])
    _field("Findings", audit["report"]["finding_count"])
    _field("Report hash", _short_hash(audit["report"]["report_hash"]))
    _blank()
    _status_badge("Draft claim created")
    _pause()

    # ── Phase 4: Publish on-chain ────────────────────────────────────────
    _phase_header(
        "⛓️",
        "PHASE 4 — Stake & Publish On-Chain",
        "The agent puts its money where its mouth is.",
    )
    _narrative(
        "Now the agent stakes ETH behind its judgment and publishes the"
    )
    _narrative(
        "claim on-chain. This makes it visible, portable, and challengeable."
    )
    _pause(0.3)

    publish_payload = {"stake_wei": int(config["required_stake_wei"])}
    _curl_line(
        f"curl -s -X POST {base_url}/audits/{audit_id}/publish "
        f"-H 'content-type: application/json' "
        f"-d '{json.dumps(publish_payload)}'"
    )
    status_code, published = api_request(
        base_url, "POST", f"/audits/{audit_id}/publish", publish_payload
    )
    if status_code != 200:
        raise RuntimeError(f"publish returned {status_code}: {published}")

    audit = summarize_audit(published)
    onchain = audit.get("onchain") or {}
    validation = audit.get("validation") or {}
    _blank()
    _field("Status", c(audit["status"].upper(), C.GREEN, C.BOLD))
    _field("On-chain audit ID", onchain.get("audit_id", "—"))
    _field("Stake", _wei_to_eth(onchain.get("stake_wei", 0)))
    _field("Publish tx", _short_hash(onchain.get("publish_tx_hash")))
    _field("Validation status", validation.get("status", "—"))
    _field("Validation request", _short_hash(validation.get("request_hash")))
    _blank()
    _status_badge("Claim published on-chain")
    _pause()

    # ── Phase 5: Inspect validation request ──────────────────────────────
    _phase_header(
        "🔗",
        "PHASE 5 — Inspect Validation Trail",
        "ERC-8004-aligned interoperability mirror.",
    )
    _narrative(
        "The validation request mirrors the published claim in an"
    )
    _narrative(
        "ERC-8004-aligned format for downstream agent consumers."
    )
    _pause(0.3)

    _curl_line(f"curl -s {base_url}/audits/{audit_id}/validation/request")
    status_code, val_req = api_request(
        base_url, "GET", f"/audits/{audit_id}/validation/request"
    )
    if status_code != 200:
        raise RuntimeError(f"validation/request returned {status_code}")

    _blank()
    _field("Type", val_req.get("type", "—"))
    _field("Request type", val_req.get("requestType", "—"))
    _field("Agent ID", val_req.get("agentId", "—"))
    _field("Validator", _short_hash(val_req.get("validatorAddress")))
    claim = val_req.get("claim", {})
    _field("Target contract", _short_hash(claim.get("targetContract")))
    _field("Report hash", _short_hash(claim.get("reportHash")))
    _field("Summary", claim.get("summary", "—"))
    _blank()
    _status_badge("Validation request available")
    _pause()

    # ── Phase 6: Challenge ───────────────────────────────────────────────
    _phase_header(
        "⚔️",
        "PHASE 6 — Challenge the Claim",
        "Submit evidence that the judgment is wrong.",
    )
    _narrative(
        "A challenger submits evidence against the claim."
    )
    _narrative(
        "Plain proof-URI evidence goes to manual review. Executable evidence gets an advisory verifier verdict."
    )
    _pause(0.3)

    challenge_payload = {
        "proof_uri": fixture["challenge_proof_uri"],
        "challenger": args.challenger,
    }
    _curl_line(
        f"curl -s -X POST {base_url}/audits/{audit_id}/challenge "
        f"-H 'content-type: application/json' "
        f"-d '{json.dumps(challenge_payload)}'"
    )
    status_code, challenged = api_request(
        base_url, "POST", f"/audits/{audit_id}/challenge", challenge_payload
    )
    if status_code != 200:
        raise RuntimeError(f"challenge returned {status_code}: {challenged}")

    audit = summarize_audit(challenged)
    ch = audit.get("challenge") or {}
    _blank()
    _field("Status", c(audit["status"].upper(), C.GREEN, C.BOLD))
    _field("Challenge status", c(str(ch.get("status", "—")).upper(), C.MAGENTA, C.BOLD))
    _field("Resolution path", ch.get("resolution_path", "—"))
    _field("Verifier", ch.get("verifier", "—"))
    _field("Verification", ch.get("verification_summary", "—"))
    _field("Challenger", ch.get("challenger", "—"))
    _field("Challenge tx", _short_hash(ch.get("challenge_tx_hash")))
    _field("Resolve tx", _short_hash(ch.get("resolve_tx_hash")))
    _field("Payout", _wei_to_eth(ch.get("payout_wei")))
    _blank()
    _status_badge("Challenge opened")
    _pause()

    # ── Phase 7: Validation response ─────────────────────────────────────
    _phase_header(
        "📄",
        "PHASE 7 — Validation Response",
        "The final resolved outcome in ERC-8004 format.",
    )
    _narrative(
        "After resolution, the validation bridge mirrors the final"
    )
    _narrative(
        "outcome so other agents can consume it in a standards-aligned way."
    )
    _pause(0.3)

    _curl_line(f"curl -s {base_url}/audits/{audit_id}/validation/response")
    status_code, val_resp = api_request(
        base_url, "GET", f"/audits/{audit_id}/validation/response"
    )
    _blank()
    if status_code == 404:
        _field("Status", c("PENDING MANUAL REVIEW", C.YELLOW, C.BOLD))
        _field("Note", "Validation response is published after the challenge is manually resolved.")
        _field("Verifier", "manual-proof-review-v1")
        _blank()
        _status_badge("Manual review pending — response will be published after arbitration", ok=False)
    else:
        if status_code != 200:
            raise RuntimeError(f"validation/response returned {status_code}")
        _field("Type", val_resp.get("type", "—"))
        _field("Response", val_resp.get("response", "—"))
        _field("Tag", c(str(val_resp.get("tag", "—")), C.RED, C.BOLD))
        outcome = val_resp.get("outcome", {})
        _field("Audit status", outcome.get("auditStatus", "—"))
        _field("Challenge status", outcome.get("challengeStatus", "—"))
        _field("Resolution path", outcome.get("resolutionPath", "—"))
        evidence = val_resp.get("evidence", {})
        _field("Proof URI", evidence.get("proofUri", "—"))
        _field("Verification", evidence.get("verificationSummary", "—"))
        _blank()
        _status_badge("Validation response recorded")
    _pause()

    # ── Phase 8: Final record ────────────────────────────────────────────
    _phase_header(
        "✅",
        "PHASE 8 — Final Audit Record",
        "The complete lifecycle in one view.",
    )

    _curl_line(f"curl -s {base_url}/audits/{audit_id}")
    status_code, final_record = api_request(base_url, "GET", f"/audits/{audit_id}")
    if status_code != 200:
        raise RuntimeError(f"/audits/{audit_id} returned {status_code}")

    audit = summarize_audit(final_record)
    ch = audit.get("challenge") or {}
    onchain = audit.get("onchain") or {}
    val = audit.get("validation") or {}

    _blank()
    _field("Audit ID", audit["id"])
    _field("Final status", c(audit["status"].upper(), C.GREEN, C.BOLD))
    _field("Agent", audit["agent"]["name"])
    _field("Report", audit["report"]["summary"])
    _field("On-chain ID", onchain.get("audit_id", "—"))
    _field("Stake", _wei_to_eth(onchain.get("stake_wei", 0)))
    _field("Challenge", c(str(ch.get("resolution", "—")).upper(), C.MAGENTA, C.BOLD))
    _field("Payout", _wei_to_eth(ch.get("payout_wei", 0)))
    _field("Validation", val.get("response_tag", "—"))
    _pause(0.5)

    # ── Summary banner ───────────────────────────────────────────────────
    _box(
        [
            "",
            c("  Lifecycle complete", C.BOLD, C.GREEN),
            "",
            f"  {c('draft', C.YELLOW)} → {c('published', C.CYAN)} → {c('challenged', C.MAGENTA)} → {c('resolved', C.GREEN)}",
            "",
            c("  The judgment was stake-backed, challenged with evidence,", C.WHITE),
            c("  and resolved transparently on-chain.", C.WHITE),
            "",
            c("  Trust comes from visible economic commitment.", C.DIM, C.ITALIC),
            "",
        ]
        + (
            [
                c("  ─── Live on Base Sepolia ───", C.DIM, C.CYAN),
                c("  Contract: 0xf2dA…F24 · sepolia.basescan.org", C.DIM),
                "",
            ]
            if args.show_deployment
            else []
        ),
        title="🛡️  Proof-of-Audit",
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
