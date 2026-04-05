#!/usr/bin/env python3
"""Register multi-agent identities from demo/agents.json.

Reads the agent persona manifest and registers each agent's identity
in the on-chain ``AgentIdentityRegistry``, funds operator wallets, and
writes per-agent deployment records to a JSON output file.

Usage:
    python scripts/register-multi-agent-identities.py \
        --registry-address 0x... \
        --rpc-url http://127.0.0.1:8545 \
        --admin-private-key 0x... \
        --agents-manifest demo/agents.json \
        --output deployments/multi-agent-identities.localhost.json \
        [--fund-amount-wei 100000000000000000] \
        [--deployer-private-key 0x...]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

# Well-known Anvil accounts (index 0-9).
# Each entry: (address, private_key).
ANVIL_ACCOUNTS: list[tuple[str, str]] = [
    ("0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266", "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"),
    ("0x70997970C51812dc3A010C7d01b50e0d17dc79C8", "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"),
    ("0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC", "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a"),
    ("0x90F79bf6EB2c4f870365E785982E1f101E93b906", "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6"),
    ("0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65", "0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a"),
    ("0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc", "0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba"),
    ("0x976EA74026E726554dB657fA54763abd0C3a0aa9", "0x92db14e403b83dfe3df233f83dfa3a0d7096f21ca9b0d6d6b8d88b2b4ec1564e"),
    ("0x14dC79964da2C08dA15Fd353d30fF18Dc80D3c94", "0x4bbbf85ce3377467afe5d46f804f221813b2bb87f24d81f60f1fcdbf7cbf4356"),
    ("0x23618e81E3f5cdF7f54C3d65f7FBc0aBf5B21E8f", "0xdbda1821b80551c9d65939329250298aa3472ba22feea921c0cf5d620ea67b97"),
    ("0xa0Ee7A142d267C1f36714E4a8F75612F20a79720", "0x2a871d0798f97d79848a013d4936a73bf4cc922c825d33c1cf7073dff6d409c6"),
]


def _cast_call(address: str, sig: str, *args: str, rpc_url: str) -> str:
    """Run ``cast call`` and return stripped stdout."""
    cmd = ["cast", "call", address, sig, *args, "--rpc-url", rpc_url]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _cast_send(to: str, sig: str, *args: str, rpc_url: str, private_key: str) -> dict:
    """Run ``cast send --json`` and return the parsed JSON receipt."""
    cmd = [
        "cast", "send", to, sig, *args,
        "--rpc-url", rpc_url,
        "--private-key", private_key,
        "--json",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def _cast_balance(address: str, rpc_url: str) -> int:
    """Get balance in wei."""
    cmd = ["cast", "balance", address, "--rpc-url", rpc_url]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return int(result.stdout.strip())


def _cast_send_value(to: str, value: str, rpc_url: str, private_key: str) -> dict:
    """Send ETH value."""
    cmd = [
        "cast", "send", to,
        "--value", value,
        "--rpc-url", rpc_url,
        "--private-key", private_key,
        "--json",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def _wallet_address(private_key: str) -> str:
    cmd = ["cast", "wallet", "address", "--private-key", private_key]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _get_next_agent_id(registry: str, rpc_url: str) -> int:
    raw = _cast_call(registry, "nextAgentId()(uint256)", rpc_url=rpc_url)
    return int(raw)


def _register_agent(
    registry: str,
    owner: str,
    registration_uri: str,
    rpc_url: str,
    admin_private_key: str,
) -> tuple[int, str]:
    """Register an agent and return (agent_id, tx_hash)."""
    receipt = _cast_send(
        registry,
        "registerAgent(address,string)",
        owner,
        registration_uri,
        rpc_url=rpc_url,
        private_key=admin_private_key,
    )
    tx_hash = receipt.get("transactionHash") or receipt.get("txHash") or receipt.get("hash") or ""

    # Derive agent_id from nextAgentId - 1 (it auto-incremented)
    agent_id = _get_next_agent_id(registry, rpc_url) - 1
    return agent_id, tx_hash


def _agent_registration_uri(service_id: str) -> str:
    """Build a placeholder registration URI for a demo agent."""
    return (
        f"https://raw.githubusercontent.com/akoita/proof-of-audit/main/"
        f"docs/registrations/{service_id}.json"
    )


def _resolve_operator_account(agent: dict) -> tuple[str, str]:
    """Resolve operator address and private key from Anvil account index."""
    identity = agent.get("identity", {})
    index = identity.get("anvil_account_index", 0)
    if index < 0 or index >= len(ANVIL_ACCOUNTS):
        raise ValueError(
            f"Agent {agent['service_id']} has anvil_account_index={index}, "
            f"but only {len(ANVIL_ACCOUNTS)} Anvil accounts are available."
        )
    return ANVIL_ACCOUNTS[index]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Register multi-agent identities from demo/agents.json"
    )
    parser.add_argument("--registry-address", required=True)
    parser.add_argument("--rpc-url", default="http://127.0.0.1:8545")
    parser.add_argument("--admin-private-key", required=True)
    parser.add_argument(
        "--agents-manifest",
        default="demo/agents.json",
    )
    parser.add_argument(
        "--output",
        default="deployments/multi-agent-identities.localhost.json",
    )
    parser.add_argument(
        "--fund-amount-wei",
        default="100000000000000000",
        help="Amount in wei to fund each operator wallet (default: 0.1 ETH).",
    )
    parser.add_argument(
        "--deployer-private-key",
        help="Private key for funding wallets (defaults to Anvil account 0).",
    )
    parser.add_argument(
        "--network",
        default="anvil-local",
    )
    parser.add_argument(
        "--chain-id",
        type=int,
        default=31337,
    )
    args = parser.parse_args()

    manifest_path = Path(args.agents_manifest)
    if not manifest_path.exists():
        print(f"Agents manifest not found: {manifest_path}", file=sys.stderr)
        return 1

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    agents = manifest.get("agents", [])
    if not agents:
        print("No agents found in manifest.", file=sys.stderr)
        return 1

    deployer_key = args.deployer_private_key or ANVIL_ACCOUNTS[0][1]
    fund_amount = args.fund_amount_wei

    results: dict[str, dict] = {}
    print(f"Registering {len(agents)} agent identities...")
    print(f"  Registry: {args.registry_address}")
    print(f"  Network:  {args.network} (chain {args.chain_id})")
    print()

    for agent in agents:
        service_id = agent["service_id"]
        name = agent["name"]
        operator_address, operator_key = _resolve_operator_account(agent)
        registration_uri = _agent_registration_uri(service_id)

        print(f"  [{service_id}] {name}")
        print(f"    Operator: {operator_address}")

        # Register the agent identity
        agent_id, tx_hash = _register_agent(
            registry=args.registry_address,
            owner=operator_address,
            registration_uri=registration_uri,
            rpc_url=args.rpc_url,
            admin_private_key=args.admin_private_key,
        )
        print(f"    Agent ID: {agent_id}")
        print(f"    TX:       {tx_hash}")

        # Fund operator wallet if needed
        balance = _cast_balance(operator_address, args.rpc_url)
        if balance < int(fund_amount):
            print(f"    Funding {fund_amount} wei...")
            _cast_send_value(
                to=operator_address,
                value=fund_amount,
                rpc_url=args.rpc_url,
                private_key=deployer_key,
            )
            new_balance = _cast_balance(operator_address, args.rpc_url)
            print(f"    Balance: {balance} → {new_balance} wei")
        else:
            print(f"    Balance: {balance} wei (sufficient)")

        results[service_id] = {
            "service_id": service_id,
            "name": name,
            "agent_id": agent_id,
            "operator_address": operator_address,
            "operator_private_key": operator_key,
            "registration_uri": registration_uri,
            "registry_address": args.registry_address,
            "register_tx_hash": tx_hash,
            "profile": agent.get("profile"),
            "runtime_mode": agent.get("runtime_mode"),
            "detectors": agent.get("detectors", []),
            "capabilities": agent.get("capabilities", []),
            "challenge_strategy": agent.get("challenge_strategy"),
        }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output = {
        "schema_version": "multi-agent-identities/v1",
        "network": args.network,
        "chain_id": args.chain_id,
        "rpc_url": args.rpc_url,
        "registry_address": args.registry_address,
        "generated_at": datetime.now(UTC).isoformat(),
        "agent_count": len(results),
        "agents": results,
    }
    output_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print()
    print(f"✓ {len(results)} agent identities registered.")
    print(f"  Output: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
