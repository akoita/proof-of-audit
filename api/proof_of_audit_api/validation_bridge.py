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


class ValidationBridgeError(Exception):
    """Raised when validation bridge requests or responses fail."""


class ValidationBridgeConfigurationError(ValidationBridgeError):
    """Raised when the validation bridge is not configured."""


@dataclass(frozen=True)
class ValidationRequestResult:
    request_hash: str
    tx_hash: str
    chain_id: int
    validator_address: str
    registry_address: str


@dataclass(frozen=True)
class ValidationResponseResult:
    request_hash: str
    response_hash: str
    tx_hash: str
    chain_id: int
    validator_address: str
    registry_address: str
    response: int
    tag: str


def load_validation_bridge_artifact() -> dict[str, Any]:
    return load_contract_artifact_json(
        "ValidationRegistryAdapter.sol",
        "ValidationRegistryAdapter.json",
    )


def load_validation_bridge_abi() -> list[dict[str, Any]]:
    return load_validation_bridge_artifact()["abi"]


class ValidationRegistryBridge:
    def __init__(self, contract_config: ContractConfig, web3: Web3 | None = None) -> None:
        self.contract_config = contract_config
        self.web3 = web3 or self._build_web3(contract_config)
        self.contract = self._build_contract(contract_config)
        self.owner_private_key = self._require_owner_private_key(contract_config)
        self.validator_private_key = self._require_validator_private_key(contract_config)
        self.owner_account = self.web3.eth.account.from_key(self.owner_private_key)
        self.validator_account = self.web3.eth.account.from_key(self.validator_private_key)

    @classmethod
    def from_config_if_ready(
        cls, contract_config: ContractConfig, web3: Web3 | None = None
    ) -> "ValidationRegistryBridge | None":
        if not (
            contract_config.validation_registry_address
            and contract_config.rpc_url
            and contract_config.auditor_agent_id is not None
            and contract_config.auditor_owner_private_key
            and contract_config.validator_private_key
            and contract_config.validator_address
        ):
            return None
        return cls(contract_config=contract_config, web3=web3)

    def build_hash(self, payload: dict[str, Any]) -> str:
        content = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return "0x" + sha256(content.encode("utf-8")).hexdigest()

    def submit_request(self, *, request_uri: str, request_hash: str) -> ValidationRequestResult:
        runtime_chain_id = int(self.web3.eth.chain_id)
        validator_address = self._validator_address()
        call = self.contract.functions.validationRequest(
            Web3.to_checksum_address(validator_address),
            int(self.contract_config.auditor_agent_id),
            request_uri,
            HexBytes(self._ensure_hex(request_hash)),
        )
        receipt = self._submit_transaction(
            call,
            account=self.owner_account,
            private_key=self.owner_private_key,
            chain_id=runtime_chain_id,
            action_label="submit validation request",
        )
        request_hash_hex = self._ensure_hex(request_hash)
        requests = self.contract.functions.getAgentValidations(
            int(self.contract_config.auditor_agent_id)
        ).call()
        normalized_requests = {Web3.to_hex(value) for value in requests}
        if request_hash_hex not in normalized_requests:
            raise ValidationBridgeError(
                "Validation request transaction succeeded but request hash was not recorded."
            )
        return ValidationRequestResult(
            request_hash=request_hash_hex,
            tx_hash=Web3.to_hex(receipt["transactionHash"]),
            chain_id=runtime_chain_id,
            validator_address=validator_address,
            registry_address=self.contract.address,
        )

    def submit_response(
        self,
        *,
        request_hash: str,
        response: int,
        response_uri: str,
        response_hash: str,
        tag: str,
    ) -> ValidationResponseResult:
        runtime_chain_id = int(self.web3.eth.chain_id)
        call = self.contract.functions.validationResponse(
            HexBytes(self._ensure_hex(request_hash)),
            response,
            response_uri,
            HexBytes(self._ensure_hex(response_hash)),
            tag,
        )
        receipt = self._submit_transaction(
            call,
            account=self.validator_account,
            private_key=self.validator_private_key,
            chain_id=runtime_chain_id,
            action_label="submit validation response",
        )
        status = self.contract.functions.getValidationStatus(
            HexBytes(self._ensure_hex(request_hash))
        ).call()
        if int(status[2]) != response:
            raise ValidationBridgeError(
                "Validation response transaction succeeded but response score did not match."
            )
        if Web3.to_hex(status[3]) != self._ensure_hex(response_hash):
            raise ValidationBridgeError(
                "Validation response transaction succeeded but response hash did not match."
            )
        if str(status[4]) != tag:
            raise ValidationBridgeError(
                "Validation response transaction succeeded but response tag did not match."
            )
        return ValidationResponseResult(
            request_hash=self._ensure_hex(request_hash),
            response_hash=self._ensure_hex(response_hash),
            tx_hash=Web3.to_hex(receipt["transactionHash"]),
            chain_id=runtime_chain_id,
            validator_address=self._validator_address(),
            registry_address=self.contract.address,
            response=response,
            tag=tag,
        )

    def _build_contract(self, contract_config: ContractConfig) -> Contract:
        if not contract_config.validation_registry_address:
            raise ValidationBridgeConfigurationError(
                "PROOF_OF_AUDIT_VALIDATION_REGISTRY_ADDRESS is required for the validation bridge."
            )
        return self.web3.eth.contract(
            address=Web3.to_checksum_address(contract_config.validation_registry_address),
            abi=load_validation_bridge_abi(),
        )

    def _build_web3(self, contract_config: ContractConfig) -> Web3:
        if not contract_config.rpc_url:
            raise ValidationBridgeConfigurationError(
                "PROOF_OF_AUDIT_RPC_URL or BASE_SEPOLIA_RPC_URL is required for the validation bridge."
            )
        return Web3(HTTPProvider(contract_config.rpc_url))

    def _require_owner_private_key(self, contract_config: ContractConfig) -> str:
        if not contract_config.auditor_owner_private_key:
            raise ValidationBridgeConfigurationError(
                "PROOF_OF_AUDIT_AUDITOR_OWNER_PRIVATE_KEY is required for validation requests."
            )
        return contract_config.auditor_owner_private_key

    def _require_validator_private_key(self, contract_config: ContractConfig) -> str:
        if not contract_config.validator_private_key:
            raise ValidationBridgeConfigurationError(
                "PROOF_OF_AUDIT_VALIDATOR_PRIVATE_KEY is required for validation responses."
            )
        return contract_config.validator_private_key

    def _validator_address(self) -> str:
        if not self.contract_config.validator_address:
            raise ValidationBridgeConfigurationError(
                "PROOF_OF_AUDIT_VALIDATOR_ADDRESS is required for validation requests."
            )
        return Web3.to_checksum_address(self.contract_config.validator_address)

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
                raise ValidationBridgeError(f"{action_label} reverted on-chain.")
            return receipt
        except ValidationBridgeError:
            raise
        except TimeExhausted as exc:
            raise ValidationBridgeError(
                f"Timed out while waiting for {action_label} confirmation."
            ) from exc
        except (ContractLogicError, ContractCustomError, ValueError) as exc:
            raise ValidationBridgeError(
                f"Failed to {action_label}: {exc}"
            ) from exc
        except Exception as exc:  # pragma: no cover - defensive fallback
            raise ValidationBridgeError(
                f"Failed to {action_label}: {exc}"
            ) from exc

    def _fee_fields(self) -> dict[str, int]:
        latest_block = self.web3.eth.get_block("latest")
        base_fee = latest_block.get("baseFeePerGas")
        if base_fee is None:
            return {"gasPrice": int(self.web3.eth.gas_price)}
        try:
            priority_fee = int(self.web3.eth.max_priority_fee)
        except Exception:  # pragma: no cover - provider-specific fallback
            priority_fee = self.web3.to_wei(1, "gwei")
        return {
            "maxPriorityFeePerGas": priority_fee,
            "maxFeePerGas": int(base_fee) * 2 + priority_fee,
        }

    def _ensure_hex(self, value: str) -> str:
        normalized = value.lower()
        return normalized if normalized.startswith("0x") else f"0x{normalized}"
