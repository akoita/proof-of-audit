"""Tests for the agent personas manifest (demo/agents.json)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
AGENTS_PATH = REPO_ROOT / "demo" / "agents.json"


@pytest.fixture()
def manifest() -> dict:
    return json.loads(AGENTS_PATH.read_text(encoding="utf-8"))


@pytest.fixture()
def agents(manifest: dict) -> list[dict]:
    return manifest["agents"]


def test_schema_version(manifest: dict) -> None:
    assert manifest["schema_version"] == "agent-personas/v1"


def test_agent_count(agents: list[dict]) -> None:
    assert len(agents) >= 4, "Demo requires at least 4 agent personas"


def test_unique_service_ids(agents: list[dict]) -> None:
    ids = [a["service_id"] for a in agents]
    assert len(ids) == len(set(ids)), f"Duplicate service_ids: {ids}"


def test_unique_agent_ids(agents: list[dict]) -> None:
    ids = [a["identity"]["agent_id"] for a in agents]
    assert len(ids) == len(set(ids)), f"Duplicate agent_ids: {ids}"


def test_unique_finding_id_prefixes(agents: list[dict]) -> None:
    prefixes = [a["finding_id_prefix"] for a in agents]
    assert len(prefixes) == len(set(prefixes)), f"Duplicate finding_id_prefix: {prefixes}"


def test_unique_anvil_account_indices(agents: list[dict]) -> None:
    indices = [a["identity"]["anvil_account_index"] for a in agents]
    assert len(indices) == len(set(indices)), f"Duplicate anvil_account_index: {indices}"


def test_llm_agents_have_env_keys(agents: list[dict]) -> None:
    for agent in agents:
        if agent["runtime_mode"] == "agent_forge":
            assert agent.get("llm_provider"), f"{agent['service_id']}: missing llm_provider"
            assert agent.get("env_keys"), f"{agent['service_id']}: missing env_keys"


def test_static_agents_no_llm_provider(agents: list[dict]) -> None:
    for agent in agents:
        if agent["runtime_mode"] in ("deterministic", "hybrid"):
            assert agent.get("llm_provider") is None, (
                f"{agent['service_id']}: static/hybrid should not set llm_provider"
            )


def test_service_id_format(agents: list[dict]) -> None:
    import re
    for agent in agents:
        assert re.match(r"^agent-[a-z0-9-]+$", agent["service_id"]), (
            f"Invalid service_id format: {agent['service_id']}"
        )


def test_all_agents_have_required_fields(agents: list[dict]) -> None:
    required = {
        "service_id", "name", "description", "profile", "runtime_mode",
        "capabilities", "detectors", "finding_id_prefix", "challenge_strategy",
        "image", "env_keys", "identity",
    }
    for agent in agents:
        missing = required - set(agent.keys())
        assert not missing, f"{agent.get('service_id', '?')}: missing fields {missing}"


@pytest.mark.parametrize("profile,expected_detectors", [
    ("reentrancy-specialist", ["reentrancy"]),
    ("access-control-specialist", ["access_control"]),
])
def test_specialist_detectors_match_profile(
    agents: list[dict], profile: str, expected_detectors: list[str]
) -> None:
    matches = [a for a in agents if a["profile"] == profile]
    assert matches, f"No agent with profile {profile}"
    for agent in matches:
        assert agent["detectors"] == expected_detectors, (
            f"{agent['service_id']}: detectors mismatch for {profile}"
        )


def test_gemini_agent_exists(agents: list[dict]) -> None:
    gemini = [a for a in agents if a.get("llm_provider") == "gemini"]
    assert len(gemini) >= 1, "At least one Gemini LLM agent required"
    assert "GEMINI_API_KEY" in gemini[0]["env_keys"]


def test_openai_agent_exists(agents: list[dict]) -> None:
    openai = [a for a in agents if a.get("llm_provider") == "openai"]
    assert len(openai) >= 1, "At least one OpenAI LLM agent required"
    assert "OPENAI_API_KEY" in openai[0]["env_keys"]
