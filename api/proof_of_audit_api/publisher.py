from __future__ import annotations

from dataclasses import dataclass
import re
import time
from typing import Any

from hexbytes import HexBytes
from web3 import HTTPProvider, Web3
from web3.contract import Contract
from web3.contract.contract import ContractFunction
from web3.exceptions import ContractCustomError, ContractLogicError, TimeExhausted

from proof_of_audit_api.config import ContractConfig
from proof_of_audit_api.contract_artifacts import load_contract_artifact_json


class OnchainTransactionError(Exception):
    """Raised when an on-chain transaction cannot be executed or verified."""


class OnchainPublishError(OnchainTransactionError):
    """Raised when a publish transaction cannot be executed or verified."""


class OnchainChallengeError(OnchainTransactionError):
    """Raised when a challenge transaction cannot be executed or verified."""


class OnchainResolveError(OnchainTransactionError):
    """Raised when a resolution transaction cannot be executed or verified."""


class OnchainConfigurationError(OnchainTransactionError):
    """Raised when API-side contract transaction submission is not configured."""


@dataclass(frozen=True)
class PublishResult:
    audit_id: int
    tx_hash: str
    chain_id: int


@dataclass(frozen=True)
class ChallengeResult:
    audit_id: int
    tx_hash: str
    chain_id: int
    evidence_hash: str
    challenger_address: str
    challenge_bond_wei: int


@dataclass(frozen=True)
class ResolutionResult:
    audit_id: int
    tx_hash: str
    chain_id: int
    resolution: str
    beneficiary_address: str
    payout_wei: int


def load_contract_artifact() -> dict[str, Any]:
    return load_contract_artifact_json("ProofOfAudit.sol", "ProofOfAudit.json")


def load_contract_abi() -> list[dict[str, Any]]:
    return load_contract_artifact()["abi"]


def load_contract_bytecode() -> str:
    return load_contract_artifact()["bytecode"]["object"]


class ProofOfAuditPublisher:
    _PUBLISH_VERIFICATION_RETRY_DELAYS_SECONDS = (0.25, 0.5, 1.0)

    def __init__(
        self,
        contract_config: ContractConfig,
        web3: Web3 | None = None,
        private_key: str | None = None,
    ) -> None:
        self.contract_config = contract_config
        self.private_key = private_key or self._require_private_key(contract_config)
        self.web3 = web3 or self._build_web3(contract_config)
        self.account = self.web3.eth.account.from_key(self.private_key)
        self.contract = self._build_contract(contract_config)
        self.error_selectors = self._error_selectors()

    @classmethod
    def from_config_if_ready(
        cls, contract_config: ContractConfig, private_key: str | None = None
    ) -> "ProofOfAuditPublisher | None":
        if not (
            contract_config.contract_address
            and contract_config.rpc_url
            and (private_key or contract_config.publisher_private_key)
        ):
            return None
        return cls(contract_config, private_key=private_key)

    def publish_audit(
        self,
        *,
        target_address: str,
        report_hash: str,
        metadata_hash: str,
        max_severity: int,
        finding_count: int,
        stake_wei: int,
    ) -> PublishResult:
        target = Web3.to_checksum_address(target_address)
        report_hash_bytes = HexBytes(self._ensure_hex(report_hash))
        metadata_hash_bytes = HexBytes(self._ensure_hex(metadata_hash))
        runtime_chain_id = int(self.web3.eth.chain_id)

        publish_call = self.contract.functions.publishAudit(
            target,
            report_hash_bytes,
            metadata_hash_bytes,
            max_severity,
            finding_count,
        )
        try:
            receipt = self._submit_transaction(
                publish_call,
                value_wei=stake_wei,
                chain_id=runtime_chain_id,
                action_label="publish audit",
                error_cls=OnchainPublishError,
            )
        except OnchainPublishError:
            raise

        if receipt["status"] != 1:
            raise OnchainPublishError("Publish transaction reverted on-chain.")

        events = self.contract.events.AuditPublished().process_receipt(receipt)
        if not events:
            raise OnchainPublishError(
                "Publish transaction succeeded but AuditPublished event was missing."
            )
        audit_id = int(events[0]["args"]["auditId"])
        self._verify_published_record_with_retry(
            audit_id=audit_id,
            target=target,
            report_hash=report_hash,
            metadata_hash=metadata_hash,
            max_severity=max_severity,
            finding_count=finding_count,
            stake_wei=stake_wei,
        )
        return PublishResult(
            audit_id=audit_id,
            tx_hash=Web3.to_hex(receipt["transactionHash"]),
            chain_id=runtime_chain_id,
        )

    def _verify_published_record_with_retry(
        self,
        *,
        audit_id: int,
        target: str,
        report_hash: str,
        metadata_hash: str,
        max_severity: int,
        finding_count: int,
        stake_wei: int,
    ) -> None:
        last_error: OnchainPublishError | None = None
        delays = self._PUBLISH_VERIFICATION_RETRY_DELAYS_SECONDS
        attempt_count = len(delays) + 1

        for attempt in range(attempt_count):
            try:
                self._verify_onchain_record(
                    audit_id=audit_id,
                    target=target,
                    report_hash=report_hash,
                    metadata_hash=metadata_hash,
                    max_severity=max_severity,
                    finding_count=finding_count,
                    stake_wei=stake_wei,
                )
                return
            except OnchainPublishError as exc:
                last_error = exc
                if attempt == len(delays):
                    break
                time.sleep(delays[attempt])

        message = (
            "Publish transaction receipt was confirmed, but post-transaction on-chain "
            f"verification remained inconsistent after {attempt_count} attempts: {last_error}"
        )
        raise OnchainPublishError(message)

    def challenge_audit(
        self,
        *,
        audit_id: int,
        evidence_hash: str,
        challenge_bond_wei: int,
    ) -> ChallengeResult:
        runtime_chain_id = int(self.web3.eth.chain_id)
        challenge_call = self.contract.functions.challengeAudit(
            audit_id,
            HexBytes(evidence_hash),
        )

        try:
            receipt = self._submit_transaction(
                challenge_call,
                value_wei=challenge_bond_wei,
                chain_id=runtime_chain_id,
                action_label="open challenge",
                error_cls=OnchainChallengeError,
            )
        except OnchainChallengeError:
            raise

        if receipt["status"] != 1:
            raise OnchainChallengeError("Challenge transaction reverted on-chain.")

        events = self.contract.events.ChallengeOpened().process_receipt(receipt)
        if not events:
            raise OnchainChallengeError(
                "Challenge transaction succeeded but ChallengeOpened event was missing."
            )
        event = events[0]["args"]
        event_audit_id = int(event["auditId"])
        if event_audit_id != audit_id:
            raise OnchainChallengeError(
                "Challenge transaction emitted an unexpected audit id."
            )
        event_challenger = Web3.to_checksum_address(event["challenger"])
        event_evidence_hash = Web3.to_hex(event["evidenceHash"])
        event_bond = int(event["challengeBond"])
        if event_evidence_hash != evidence_hash:
            raise OnchainChallengeError(
                "Challenge transaction emitted an unexpected evidence hash."
            )
        if event_bond != challenge_bond_wei:
            raise OnchainChallengeError(
                "Challenge transaction emitted an unexpected challenge bond."
            )

        self._verify_onchain_challenge(
            audit_id=audit_id,
            challenger_address=event_challenger,
            evidence_hash=evidence_hash,
            challenge_bond_wei=challenge_bond_wei,
        )
        return ChallengeResult(
            audit_id=audit_id,
            tx_hash=Web3.to_hex(receipt["transactionHash"]),
            chain_id=runtime_chain_id,
            evidence_hash=evidence_hash,
            challenger_address=event_challenger,
            challenge_bond_wei=challenge_bond_wei,
        )

    def resolve_challenge(self, *, audit_id: int, upheld: bool) -> ResolutionResult:
        runtime_chain_id = int(self.web3.eth.chain_id)
        resolve_call = self.contract.functions.resolveChallenge(audit_id, upheld)

        try:
            receipt = self._submit_transaction(
                resolve_call,
                value_wei=0,
                chain_id=runtime_chain_id,
                action_label="resolve challenge",
                error_cls=OnchainResolveError,
            )
        except OnchainResolveError:
            raise

        if receipt["status"] != 1:
            raise OnchainResolveError("Resolution transaction reverted on-chain.")

        events = self.contract.events.ChallengeResolved().process_receipt(receipt)
        if not events:
            raise OnchainResolveError(
                "Resolution transaction succeeded but ChallengeResolved event was missing."
            )
        event = events[0]["args"]
        event_audit_id = int(event["auditId"])
        if event_audit_id != audit_id:
            raise OnchainResolveError(
                "Resolution transaction emitted an unexpected audit id."
            )
        resolution = self._resolution_label(int(event["resolution"]))
        beneficiary_address = Web3.to_checksum_address(event["beneficiary"])
        payout_wei = int(event["payout"])
        self._verify_onchain_resolution(audit_id=audit_id, resolution=resolution)
        return ResolutionResult(
            audit_id=audit_id,
            tx_hash=Web3.to_hex(receipt["transactionHash"]),
            chain_id=runtime_chain_id,
            resolution=resolution,
            beneficiary_address=beneficiary_address,
            payout_wei=payout_wei,
        )

    def _verify_onchain_record(
        self,
        *,
        audit_id: int,
        target: str,
        report_hash: str,
        metadata_hash: str,
        max_severity: int,
        finding_count: int,
        stake_wei: int,
    ) -> None:
        record = self.contract.functions.getAudit(audit_id).call()
        if Web3.to_checksum_address(record[1]) != target:
            raise OnchainPublishError("On-chain target address did not match publish input.")
        if Web3.to_hex(record[2]) != self._ensure_hex(report_hash):
            raise OnchainPublishError("On-chain report hash did not match publish input.")
        if Web3.to_hex(record[3]) != self._ensure_hex(metadata_hash):
            raise OnchainPublishError(
                "On-chain metadata hash did not match publish input."
            )
        if int(record[6]) != stake_wei:
            raise OnchainPublishError("On-chain stake amount did not match publish input.")
        if int(record[8]) != max_severity:
            raise OnchainPublishError("On-chain max severity did not match publish input.")
        if int(record[9]) != finding_count:
            raise OnchainPublishError("On-chain finding count did not match publish input.")

    def _verify_onchain_challenge(
        self,
        *,
        audit_id: int,
        challenger_address: str,
        evidence_hash: str,
        challenge_bond_wei: int,
    ) -> None:
        record = self.contract.functions.getAudit(audit_id).call()
        if int(record[10]) != 2:
            raise OnchainChallengeError("On-chain audit state is not Challenged.")
        if int(record[7]) != challenge_bond_wei:
            raise OnchainChallengeError(
                "On-chain challenge bond did not match challenge input."
            )
        if Web3.to_checksum_address(record[12]) != challenger_address:
            raise OnchainChallengeError(
                "On-chain challenger address did not match challenge input."
            )
        if Web3.to_hex(record[13]) != evidence_hash:
            raise OnchainChallengeError(
                "On-chain evidence hash did not match challenge input."
            )

    def _verify_onchain_resolution(
        self,
        *,
        audit_id: int,
        resolution: str,
    ) -> None:
        record = self.contract.functions.getAudit(audit_id).call()
        if int(record[10]) != 3:
            raise OnchainResolveError("On-chain audit state is not Resolved.")
        if self._resolution_label(int(record[11])) != resolution:
            raise OnchainResolveError(
                "On-chain resolution did not match resolution transaction output."
            )

    def _build_contract(self, contract_config: ContractConfig) -> Contract:
        if not contract_config.contract_address:
            raise OnchainConfigurationError(
                "PROOF_OF_AUDIT_CONTRACT_ADDRESS is required for API-side contract transactions."
            )
        return self.web3.eth.contract(
            address=Web3.to_checksum_address(contract_config.contract_address),
            abi=load_contract_abi(),
        )

    def _build_web3(self, contract_config: ContractConfig) -> Web3:
        if not contract_config.rpc_url:
            raise OnchainConfigurationError(
                "PROOF_OF_AUDIT_RPC_URL or BASE_SEPOLIA_RPC_URL is required for API-side contract transactions."
            )
        return Web3(HTTPProvider(contract_config.rpc_url))

    def _require_private_key(self, contract_config: ContractConfig) -> str:
        if not contract_config.publisher_private_key:
            raise OnchainConfigurationError(
                "PROOF_OF_AUDIT_PRIVATE_KEY is required for API-side contract transactions."
            )
        return contract_config.publisher_private_key

    def _submit_transaction(
        self,
        contract_call: ContractFunction,
        *,
        value_wei: int,
        chain_id: int,
        action_label: str,
        error_cls: type[OnchainTransactionError],
    ) -> Any:
        transaction = {
            "from": self.account.address,
            "nonce": self.web3.eth.get_transaction_count(self.account.address),
            "value": value_wei,
            "chainId": chain_id,
        }
        try:
            gas_estimate = contract_call.estimate_gas(transaction)
            transaction["gas"] = int(gas_estimate * 1.2)
            transaction.update(self._fee_fields())
            built_transaction = contract_call.build_transaction(transaction)
            signed = self.web3.eth.account.sign_transaction(
                built_transaction,
                self.private_key,
            )
            tx_hash = self.web3.eth.send_raw_transaction(signed.raw_transaction)
            return self.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        except error_cls:
            raise
        except TimeExhausted as exc:
            raise error_cls(
                f"Timed out while waiting for {action_label} transaction confirmation."
            ) from exc
        except (ContractLogicError, ContractCustomError, ValueError) as exc:
            raise error_cls(self._transaction_error_message(action_label, exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive network/runtime fallback
            raise error_cls(
                f"Failed to {action_label} on-chain: {exc}"
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

    def _error_selectors(self) -> dict[str, str]:
        selectors: dict[str, str] = {}
        for item in load_contract_abi():
            if item.get("type") != "error":
                continue
            argument_types = ",".join(
                input_item["type"] for input_item in item.get("inputs", [])
            )
            signature = f"{item['name']}({argument_types})"
            selectors[Web3.keccak(text=signature)[:4].hex()] = item["name"]
        return selectors

    def _transaction_error_message(self, action_label: str, exc: Exception) -> str:
        revert_name = self._decode_revert_name(str(exc))
        if revert_name is not None:
            return f"{action_label} reverted with {revert_name}."
        return f"Failed to {action_label} on-chain: {exc}"

    def _decode_revert_name(self, message: str) -> str | None:
        match = re.search(r"0x[0-9a-fA-F]{8,}", message)
        if match is None:
            return None
        selector = match.group(0)[2:10]
        return self.error_selectors.get(selector)

    def _ensure_hex(self, value: str) -> str:
        normalized = value.lower()
        return normalized if normalized.startswith("0x") else f"0x{normalized}"

    def _resolution_label(self, resolution: int) -> str:
        if resolution == 1:
            return "upheld"
        if resolution == 2:
            return "rejected"
        return "none"
