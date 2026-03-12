from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Mapping


@dataclass(frozen=True)
class ContractConfig:
    network: str
    chain_id: int
    contract_address: str | None
    explorer_base_url: str
    arbiter: str | None
    rpc_url: str | None
    publisher_private_key: str | None
    required_stake_wei: int
    required_challenge_bond_wei: int
    challenge_window_seconds: int

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "ContractConfig":
        source = env or os.environ
        return cls(
            network=source.get("PROOF_OF_AUDIT_NETWORK", "base-sepolia"),
            chain_id=int(source.get("PROOF_OF_AUDIT_CHAIN_ID", "84532")),
            contract_address=source.get("PROOF_OF_AUDIT_CONTRACT_ADDRESS") or None,
            explorer_base_url=source.get(
                "PROOF_OF_AUDIT_EXPLORER_BASE_URL",
                "https://sepolia.basescan.org",
            ).rstrip("/"),
            arbiter=source.get("PROOF_OF_AUDIT_ARBITER") or None,
            rpc_url=source.get("PROOF_OF_AUDIT_RPC_URL")
            or source.get("BASE_SEPOLIA_RPC_URL")
            or None,
            publisher_private_key=source.get("PROOF_OF_AUDIT_PRIVATE_KEY") or None,
            required_stake_wei=int(
                source.get("PROOF_OF_AUDIT_REQUIRED_STAKE_WEI", "10000000000000000")
            ),
            required_challenge_bond_wei=int(
                source.get(
                    "PROOF_OF_AUDIT_REQUIRED_CHALLENGE_BOND_WEI",
                    "5000000000000000",
                )
            ),
            challenge_window_seconds=int(
                source.get("PROOF_OF_AUDIT_CHALLENGE_WINDOW_SECONDS", "86400")
            ),
        )

    @property
    def deployment_ready(self) -> bool:
        return bool(self.contract_address and self.rpc_url)

    def transaction_url(self, tx_hash: str) -> str:
        return f"{self.explorer_base_url}/tx/{tx_hash}"
