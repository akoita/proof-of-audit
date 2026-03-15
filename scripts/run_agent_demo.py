from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any
from urllib import error, request


DEFAULT_API_URL = "http://127.0.0.1:8080"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the terminal-first Proof-of-Audit agent demo."
    )
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--fixture-id", default="clean-vault")
    parser.add_argument("--submitted-by", default="terminal-agent")
    parser.add_argument("--challenger", default="terminal-challenger")
    parser.add_argument("--pause-seconds", type=float, default=1.0)
    parser.add_argument("--no-sleep", action="store_true")
    return parser.parse_args()


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
        payload = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(payload)
        except json.JSONDecodeError as json_error:
            raise RuntimeError(f"non-json API error from {path}: {payload}") from json_error


def sleep_for(args: argparse.Namespace) -> None:
    if not args.no_sleep and args.pause_seconds > 0:
        time.sleep(args.pause_seconds)


def print_heading(title: str) -> None:
    print()
    print(f"=== {title} ===")
    print()


def print_command(command: str) -> None:
    print(f"$ {command}")


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2))


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


def main() -> int:
    args = parse_args()
    base_url = args.api_url.rstrip("/")

    print_heading("Discover the auditor service")
    print_command(f"curl -s {base_url}/auditor")
    status_code, auditor = api_request(base_url, "GET", "/auditor")
    if status_code != 200:
        raise RuntimeError(f"/auditor returned {status_code}")
    print_json(summarize_auditor(auditor))
    sleep_for(args)

    print_command(f"curl -s {base_url}/auditor/registration")
    status_code, registration = api_request(base_url, "GET", "/auditor/registration")
    if status_code != 200:
        raise RuntimeError(f"/auditor/registration returned {status_code}")
    print_json(summarize_registration(registration))
    sleep_for(args)

    print_command(f"curl -s {base_url}/config")
    status_code, config = api_request(base_url, "GET", "/config")
    if status_code != 200:
        raise RuntimeError(f"/config returned {status_code}")
    print_json(summarize_config(config))
    sleep_for(args)

    print_heading("Select a deterministic fixture")
    print_command(f"curl -s {base_url}/fixtures")
    status_code, fixtures = api_request(base_url, "GET", "/fixtures")
    if status_code != 200:
        raise RuntimeError(f"/fixtures returned {status_code}")
    fixture = summarize_fixture(fixtures, args.fixture_id)
    print_json(fixture)
    sleep_for(args)

    print_heading("Create a draft claim")
    create_payload = {
        "input_kind": "demo_fixture",
        "fixture_id": fixture["id"],
        "submitted_by": args.submitted_by,
    }
    print_command(
        "curl -s -X POST "
        f"{base_url}/audits "
        "-H 'content-type: application/json' "
        f"-d '{json.dumps(create_payload)}'"
    )
    status_code, created = api_request(base_url, "POST", "/audits", create_payload)
    if status_code != 201:
        raise RuntimeError(f"/audits returned {status_code}: {created}")
    audit_id = created["id"]
    print_json(summarize_audit(created))
    sleep_for(args)

    print_heading("Publish the claim on-chain")
    publish_payload = {"stake_wei": int(config["required_stake_wei"])}
    print_command(
        "curl -s -X POST "
        f"{base_url}/audits/{audit_id}/publish "
        "-H 'content-type: application/json' "
        f"-d '{json.dumps(publish_payload)}'"
    )
    status_code, published = api_request(
        base_url,
        "POST",
        f"/audits/{audit_id}/publish",
        publish_payload,
    )
    if status_code != 200:
        raise RuntimeError(f"publish returned {status_code}: {published}")
    print_json(summarize_audit(published))
    sleep_for(args)

    print_heading("Inspect the validation request")
    print_command(f"curl -s {base_url}/audits/{audit_id}/validation/request")
    status_code, validation_request = api_request(
        base_url, "GET", f"/audits/{audit_id}/validation/request"
    )
    if status_code != 200:
        raise RuntimeError(
            f"/audits/{audit_id}/validation/request returned {status_code}"
        )
    print_json(validation_request)
    sleep_for(args)

    print_heading("Challenge the claim with curated evidence")
    challenge_payload = {
        "proof_uri": fixture["challenge_proof_uri"],
        "challenger": args.challenger,
    }
    print_command(
        "curl -s -X POST "
        f"{base_url}/audits/{audit_id}/challenge "
        "-H 'content-type: application/json' "
        f"-d '{json.dumps(challenge_payload)}'"
    )
    status_code, challenged = api_request(
        base_url,
        "POST",
        f"/audits/{audit_id}/challenge",
        challenge_payload,
    )
    if status_code != 200:
        raise RuntimeError(f"challenge returned {status_code}: {challenged}")
    print_json(summarize_audit(challenged))
    sleep_for(args)

    print_heading("Inspect the validation response")
    print_command(f"curl -s {base_url}/audits/{audit_id}/validation/response")
    status_code, validation_response = api_request(
        base_url, "GET", f"/audits/{audit_id}/validation/response"
    )
    if status_code != 200:
        raise RuntimeError(
            f"/audits/{audit_id}/validation/response returned {status_code}"
        )
    print_json(validation_response)
    sleep_for(args)

    print_heading("Fetch the final audit record")
    print_command(f"curl -s {base_url}/audits/{audit_id}")
    status_code, final_record = api_request(base_url, "GET", f"/audits/{audit_id}")
    if status_code != 200:
        raise RuntimeError(f"/audits/{audit_id} returned {status_code}")
    print_json(summarize_audit(final_record))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
