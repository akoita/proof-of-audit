from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any

from hexbytes import HexBytes
from web3 import HTTPProvider, Web3
from web3.contract import Contract
from web3.contract.contract import ContractFunction
from web3.exceptions import ContractCustomError, ContractLogicError, TimeExhausted

from proof_of_audit_api.config import ContractConfig
from proof_of_audit_api.contract_artifacts import load_contract_artifact_json


class ReputationBridgeError(Exception):
    """Raised when reputation bridge requests or responses fail."""


class ReputationBridgeConfigurationError(ReputationBridgeError):
    """Raised when the reputation bridge is not configured."""


@dataclass(frozen=True)
class ReputationClaimResult:
    claim_hash: str
    tx_hash: str
    chain_id: int
    registry_address: str


@dataclass(frozen=True)
class ReputationResolutionResult:
    claim_hash: str
    tx_hash: str
    chain_id: int
    registry_address: str
    claim_confirmed: bool


@dataclass(frozen=True)
class OnchainReputationSnapshot:
    agent_id: int
    total_claims: int
    resolved_challenges: int
    challenge_rejected_count: int
    challenge_upheld_count: int
    total_stake_wei: int
    last_update: int
    score: int
    registry_address: str
    source: str


def load_reputation_bridge_artifact() -> dict[str, Any]:
    return load_contract_artifact_json(
        "ReputationRegistryAdapter.sol",
        "ReputationRegistryAdapter.json",
    )


def load_reputation_bridge_abi() -> list[dict[str, Any]]:
    return load_reputation_bridge_artifact()["abi"]


class ReputationRegistryBridge:
    def __init__(self, contract_config: ContractConfig, web3: Web3 | None = None) -> None:
        self.contract_config = contract_config
        self.web3 = web3 or self._build_web3(contract_config)
        self.contract = self._build_contract(contract_config)
        self.owner_private_key = self._require_owner_private_key(contract_config)
        self.operator_private_key = self._require_operator_private_key(contract_config)
        self.owner_account = self.web3.eth.account.from_key(self.owner_private_key)
        self.operator_account = self.web3.eth.account.from_key(self.operator_private_key)

    @classmethod
    def from_config_if_ready(
        cls, contract_config: ContractConfig, web3: Web3 | None = None
    ) -> "ReputationRegistryBridge | None":
        if not (
            contract_config.reputation_registry_address
            and contract_config.rpc_url
            and contract_config.auditor_agent_id is not None
            and contract_config.auditor_owner_private_key
            and contract_config.reputation_operator_private_key
        ):
            return None
        return cls(contract_config=contract_config, web3=web3)

    def build_hash(self, payload: dict[str, Any]) -> str:
        content = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return "0x" + sha256(content.encode("utf-8")).hexdigest()

    def submit_claim(
        self, *, claim_uri: str, claim_hash: str, stake_wei: int
    ) -> ReputationClaimResult:
        runtime_chain_id = int(self.web3.eth.chain_id)
        call = self.contract.functions.recordClaim(
            int(self.contract_config.auditor_agent_id),
            HexBytes(self._ensure_hex(claim_hash)),
            int(stake_wei),
            claim_uri,
        )
        receipt = self._submit_transaction(
            call,
            account=self.owner_account,
            private_key=self.owner_private_key,
            chain_id=runtime_chain_id,
            action_label="submit reputation claim",
        )
        claims = self.contract.functions.getAgentClaims(
            int(self.contract_config.auditor_agent_id)
        ).call()
        claim_hash_hex = self._ensure_hex(claim_hash)
        if claim_hash_hex not in {Web3.to_hex(value) for value in claims}:
            raise ReputationBridgeError(
                "Reputation claim transaction succeeded but claim hash was not recorded."
            )
        return ReputationClaimResult(
            claim_hash=claim_hash_hex,
            tx_hash=Web3.to_hex(receipt["transactionHash"]),
            chain_id=runtime_chain_id,
            registry_address=self.contract.address,
        )

    def submit_resolution(
        self, *, claim_hash: str, claim_confirmed: bool, resolution_uri: str
    ) -> ReputationResolutionResult:
        runtime_chain_id = int(self.web3.eth.chain_id)
        call = self.contract.functions.recordResolution(
            HexBytes(self._ensure_hex(claim_hash)),
            bool(claim_confirmed),
            resolution_uri,
        )
        receipt = self._submit_transaction(
            call,
            account=self.operator_account,
            private_key=self.operator_private_key,
            chain_id=runtime_chain_id,
            action_label="submit reputation resolution",
        )
        status = self.contract.functions.getClaimStatus(
            HexBytes(self._ensure_hex(claim_hash))
        ).call()
        if bool(status[3]) is not True:
            raise ReputationBridgeError(
                "Reputation resolution transaction succeeded but resolution was not recorded."
            )
        if bool(status[4]) is not bool(claim_confirmed):
            raise ReputationBridgeError(
                "Reputation resolution transaction succeeded but confirmed flag did not match."
            )
        return ReputationResolutionResult(
            claim_hash=self._ensure_hex(claim_hash),
            tx_hash=Web3.to_hex(receipt["transactionHash"]),
            chain_id=runtime_chain_id,
            registry_address=self.contract.address,
            claim_confirmed=claim_confirmed,
        )

    def get_reputation(self, agent_id: int) -> OnchainReputationSnapshot:
        stats = self.contract.functions.getReputation(int(agent_id)).call()
        return OnchainReputationSnapshot(
            agent_id=agent_id,
            total_claims=int(stats[0]),
            resolved_challenges=int(stats[1]),
            challenge_rejected_count=int(stats[2]),
            challenge_upheld_count=int(stats[3]),
            total_stake_wei=int(stats[4]),
            last_update=int(stats[5]),
            score=int(stats[6]),
            registry_address=self.contract.address,
            source=self.contract_config.reputation_bridge_source or "configured",
        )

    def _build_contract(self, contract_config: ContractConfig) -> Contract:
        if not contract_config.reputation_registry_address:
            raise ReputationBridgeConfigurationError(
                "PROOF_OF_AUDIT_REPUTATION_REGISTRY_ADDRESS is required for the reputation bridge."
            )
        return self.web3.eth.contract(
            address=Web3.to_checksum_address(contract_config.reputation_registry_address),
            abi=load_reputation_bridge_abi(),
        )

    def _build_web3(self, contract_config: ContractConfig) -> Web3:
        if not contract_config.rpc_url:
            raise ReputationBridgeConfigurationError(
                "PROOF_OF_AUDIT_RPC_URL or BASE_SEPOLIA_RPC_URL is required for the reputation bridge."
            )
        return Web3(HTTPProvider(contract_config.rpc_url))

    def _require_owner_private_key(self, contract_config: ContractConfig) -> str:
        if not contract_config.auditor_owner_private_key:
            raise ReputationBridgeConfigurationError(
                "PROOF_OF_AUDIT_AUDITOR_OWNER_PRIVATE_KEY is required for reputation claims."
            )
        return contract_config.auditor_owner_private_key

    def _require_operator_private_key(self, contract_config: ContractConfig) -> str:
        if not contract_config.reputation_operator_private_key:
            raise ReputationBridgeConfigurationError(
                "PROOF_OF_AUDIT_REPUTATION_OPERATOR_PRIVATE_KEY is required for reputation resolutions."
            )
        return contract_config.reputation_operator_private_key

    def _submit_transaction(
        self,
        contract_call: ContractFunction,
        *,
        account: Any,
        private_key: str,
        chain_id: int,
        action_label: str,
    ) -> Any:
        transaction = {
            "from": account.address,
            "nonce": self.web3.eth.get_transaction_count(account.address),
            "value": 0,
            "chainId": chain_id,
        }
        try:
            gas_estimate = contract_call.estimate_gas(transaction)
            transaction["gas"] = int(gas_estimate * 1.2)
            transaction.update(self._fee_fields())
            built_transaction = contract_call.build_transaction(transaction)
            signed = self.web3.eth.account.sign_transaction(
                built_transaction,
                private_key,
            )
            tx_hash = self.web3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            if receipt["status"] != 1:
                raise ReputationBridgeError(f"{action_label} reverted on-chain.")
            return receipt
        except ReputationBridgeError:
            raise
        except TimeExhausted as exc:
            raise ReputationBridgeError(
                f"Timed out while waiting for {action_label} confirmation."
            ) from exc
        except (ContractLogicError, ContractCustomError, ValueError) as exc:
            raise ReputationBridgeError(f"Failed to {action_label}: {exc}") from exc
        except Exception as exc:  # pragma: no cover - defensive fallback
            raise ReputationBridgeError(f"Failed to {action_label}: {exc}") from exc

    def _fee_fields(self) -> dict[str, int]:
        latest_block = self.web3.eth.get_block("latest")
        base_fee = latest_block.get("baseFeePerGas")
        if base_fee is None:
            gas_price = int(self.web3.eth.gas_price)
            return {"gasPrice": gas_price}
        base_fee_int = int(base_fee)
        priority_fee = int(self.web3.to_wei(1, "gwei"))
        max_fee = max(base_fee_int * 2 + priority_fee, priority_fee)
        return {
            "maxFeePerGas": max_fee,
            "maxPriorityFeePerGas": priority_fee,
        }

    def _ensure_hex(self, value: str) -> str:
        if value.startswith("0x"):
            return value
        return "0x" + value
