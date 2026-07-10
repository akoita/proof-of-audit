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


class OnchainRequestError(OnchainTransactionError):
    """Raised when an audit-request transaction cannot be executed or verified."""


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


@dataclass(frozen=True)
class AuditRequestCreateResult:
    request_id: int
    tx_hash: str
    chain_id: int


@dataclass(frozen=True)
class OnchainAuditRequest:
    request_id: int
    requester_address: str
    target_address: str
    created_at: int
    response_window_end: int
    bounty_wei: int
    claim_count: int
    state: str
    eligibility: dict[str, Any]


@dataclass(frozen=True)
class OnchainAuditRequestSettlement:
    request_id: int
    classified_claim_count: int
    eligible_claim_count: int
    claimant_withdrawn_count: int
    finalized: bool
    requester_refund_withdrawn: bool
    eligible_stake_wei: int
    protocol_fee_wei: int
    distributable_bounty_wei: int
    cumulative_bounty_withdrawn_wei: int


@dataclass(frozen=True)
class AuditRequestClaimResult:
    request_id: int
    claim_id: int
    tx_hash: str
    chain_id: int


@dataclass(frozen=True)
class AuditRequestClaimChallengeResult:
    request_id: int
    claim_id: int
    tx_hash: str
    chain_id: int
    evidence_hash: str
    challenger_address: str
    challenge_bond_wei: int


@dataclass(frozen=True)
class AuditRequestClaimResolutionResult:
    request_id: int
    claim_id: int
    tx_hash: str
    chain_id: int
    resolution: str
    beneficiary_address: str
    gross_payout_wei: int
    resolution_fee_wei: int
    payout_wei: int


@dataclass(frozen=True)
class OnchainAuditRequestClaim:
    claim_id: int
    request_id: int
    auditor_address: str
    agent_registry: str
    agent_id: int
    submitted_at: int
    challenged_at: int
    stake_wei: int
    challenge_bond_wei: int
    report_hash: str
    metadata_hash: str
    max_severity: int
    finding_count: int
    state: str
    resolution: str
    challenger_address: str | None
    evidence_hash: str | None


@dataclass(frozen=True)
class OnchainAuditRequestClaimSettlementPreview:
    claim_id: int
    eligible: bool
    withdrawn: bool
    bounty_share_wei: int
    payout_wei: int


@dataclass(frozen=True)
class OnchainAuditRequestRefundPreview:
    request_id: int
    available: bool
    refund_wei: int


@dataclass(frozen=True)
class AuditRequestSettlementResult:
    request_id: int
    tx_hash: str
    chain_id: int


@dataclass(frozen=True)
class AuditRequestClaimSettlementWithdrawalResult:
    request_id: int
    claim_id: int
    tx_hash: str
    chain_id: int
    beneficiary_address: str
    returned_stake_wei: int
    bounty_share_wei: int
    payout_wei: int


@dataclass(frozen=True)
class AuditRequestRefundWithdrawalResult:
    request_id: int
    tx_hash: str
    chain_id: int
    beneficiary_address: str
    refund_wei: int


@dataclass(frozen=True)
class MarketplaceFeeConfig:
    treasury_address: str
    protocol_fee_bps: int
    resolution_fee_bps: int
    fee_denominator: int


def load_contract_artifact() -> dict[str, Any]:
    return load_contract_artifact_json("ProofOfAudit.sol", "ProofOfAudit.json")


def load_contract_abi() -> list[dict[str, Any]]:
    return load_contract_artifact()["abi"]


def load_contract_bytecode() -> str:
    return load_contract_artifact()["bytecode"]["object"]


class ProofOfAuditPublisher:
    _PUBLISH_VERIFICATION_RETRY_DELAYS_SECONDS = (0.25, 0.5, 1.0)
    _IDENTITY_REGISTRY_ABI = [
        {
            "inputs": [{"internalType": "uint256", "name": "agentId", "type": "uint256"}],
            "name": "ownerOf",
            "outputs": [{"internalType": "address", "name": "", "type": "address"}],
            "stateMutability": "view",
            "type": "function",
        }
    ]

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
        challenger_key = getattr(contract_config, "challenger_private_key", None)
        self.challenger_account = (
            self.web3.eth.account.from_key(challenger_key)
            if challenger_key
            else self.account
        )
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
                account=self.challenger_account,
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

    def create_audit_request(
        self,
        *,
        target_address: str,
        bounty_wei: int,
        response_window_seconds: int,
        minimum_stake_wei: int = 0,
        allowlist_enabled: bool = False,
        identity_registry: str | None = None,
        required_agent_id: int = 0,
        allowlisted_auditors: list[str] | None = None,
    ) -> AuditRequestCreateResult:
        target = Web3.to_checksum_address(target_address)
        runtime_chain_id = int(self.web3.eth.chain_id)
        normalized_allowlist = [
            Web3.to_checksum_address(value)
            for value in (allowlisted_auditors or [])
        ]
        request_call = self.contract.functions.createAuditRequest(
            target,
            bounty_wei,
            response_window_seconds,
            (
                minimum_stake_wei,
                allowlist_enabled,
                Web3.to_checksum_address(identity_registry)
                if identity_registry
                else "0x0000000000000000000000000000000000000000",
                required_agent_id,
            ),
            normalized_allowlist,
        )
        receipt = self._submit_transaction(
            request_call,
            value_wei=bounty_wei,
            chain_id=runtime_chain_id,
            action_label="create audit request",
            error_cls=OnchainRequestError,
        )
        if receipt["status"] != 1:
            raise OnchainRequestError("Audit request transaction reverted on-chain.")

        events = self.contract.events.AuditRequested().process_receipt(receipt)
        if not events:
            raise OnchainRequestError(
                "Audit request transaction succeeded but AuditRequested event was missing."
            )
        event = events[0]["args"]
        request_id = int(event["requestId"])
        onchain_request = self.get_audit_request(request_id)
        if onchain_request.target_address != target:
            raise OnchainRequestError(
                "On-chain request target address did not match request input."
            )
        if onchain_request.bounty_wei != bounty_wei:
            raise OnchainRequestError(
                "On-chain request bounty did not match request input."
            )
        return AuditRequestCreateResult(
            request_id=request_id,
            tx_hash=Web3.to_hex(receipt["transactionHash"]),
            chain_id=runtime_chain_id,
        )

    def get_audit_request(self, request_id: int) -> OnchainAuditRequest:
        record = self.contract.functions.getAuditRequest(request_id).call()
        eligibility = record[7]
        allowlisted_auditor_addresses = [
            Web3.to_checksum_address(value).lower()
            for value in self.contract.functions.getAuditRequestAllowlistedAuditors(
                request_id
            ).call()
        ]
        return OnchainAuditRequest(
            request_id=request_id,
            requester_address=Web3.to_checksum_address(record[0]),
            target_address=Web3.to_checksum_address(record[1]),
            created_at=int(record[2]),
            response_window_end=int(record[3]),
            bounty_wei=int(record[4]),
            claim_count=int(record[5]),
            state=self._request_state_label(int(record[6])),
            eligibility={
                "minimum_stake_wei": int(eligibility[0]),
                "allowlist_enabled": bool(eligibility[1]),
                "allowlist_root": self._allowlist_commitment(
                    allowlisted_auditor_addresses
                ),
                "identity_registry": (
                    None
                    if int(eligibility[2], 16) == 0
                    else Web3.to_checksum_address(eligibility[2])
                ),
                "required_agent_id": int(eligibility[3]),
                "allowlisted_auditor_addresses": allowlisted_auditor_addresses,
            },
        )

    def get_audit_request_settlement(
        self, request_id: int
    ) -> OnchainAuditRequestSettlement:
        record = self.contract.functions.getAuditRequestSettlement(request_id).call()
        return OnchainAuditRequestSettlement(
            request_id=request_id,
            classified_claim_count=int(record[0]),
            eligible_claim_count=int(record[1]),
            claimant_withdrawn_count=int(record[2]),
            finalized=bool(record[3]),
            requester_refund_withdrawn=bool(record[4]),
            eligible_stake_wei=int(record[5]),
            protocol_fee_wei=int(record[6]),
            distributable_bounty_wei=int(record[7]),
            cumulative_bounty_withdrawn_wei=int(record[8]),
        )

    def get_marketplace_fee_config(self) -> MarketplaceFeeConfig:
        return MarketplaceFeeConfig(
            treasury_address=Web3.to_checksum_address(
                self.contract.functions.treasury().call()
            ),
            protocol_fee_bps=int(self.contract.functions.protocolFeeBps().call()),
            resolution_fee_bps=int(self.contract.functions.resolutionFeeBps().call()),
            fee_denominator=int(self.contract.functions.FEE_DENOMINATOR().call()),
        )

    def resolve_identity_owner(self, *, agent_registry: str, agent_id: int) -> str:
        registry = self.web3.eth.contract(
            address=Web3.to_checksum_address(agent_registry),
            abi=self._IDENTITY_REGISTRY_ABI,
        )
        owner = registry.functions.ownerOf(agent_id).call()
        return Web3.to_checksum_address(owner)

    def submit_audit_request_claim(
        self,
        *,
        request_id: int,
        agent_registry: str,
        agent_id: int,
        report_hash: str,
        metadata_hash: str,
        max_severity: int,
        finding_count: int,
        stake_wei: int,
    ) -> AuditRequestClaimResult:
        runtime_chain_id = int(self.web3.eth.chain_id)
        claim_call = self.contract.functions.submitAuditRequestClaim(
            request_id,
            Web3.to_checksum_address(agent_registry),
            agent_id,
            HexBytes(self._ensure_hex(report_hash)),
            HexBytes(self._ensure_hex(metadata_hash)),
            max_severity,
            finding_count,
        )
        receipt = self._submit_transaction(
            claim_call,
            value_wei=stake_wei,
            chain_id=runtime_chain_id,
            action_label="submit audit request claim",
            error_cls=OnchainRequestError,
        )
        if receipt["status"] != 1:
            raise OnchainRequestError("Audit request claim transaction reverted on-chain.")
        events = self.contract.events.AuditRequestClaimSubmitted().process_receipt(receipt)
        if not events:
            raise OnchainRequestError(
                "Audit request claim transaction succeeded but AuditRequestClaimSubmitted event was missing."
            )
        event = events[0]["args"]
        claim_id = int(event["claimId"])
        onchain_claim = self.get_audit_request_claim(claim_id)
        if onchain_claim.request_id != request_id:
            raise OnchainRequestError(
                "On-chain request claim request id did not match claim input."
            )
        return AuditRequestClaimResult(
            request_id=request_id,
            claim_id=claim_id,
            tx_hash=Web3.to_hex(receipt["transactionHash"]),
            chain_id=runtime_chain_id,
        )

    def get_audit_request_claim(self, claim_id: int) -> OnchainAuditRequestClaim:
        record = self.contract.functions.getAuditRequestClaim(claim_id).call()
        return OnchainAuditRequestClaim(
            claim_id=claim_id,
            request_id=int(record[0]),
            auditor_address=Web3.to_checksum_address(record[1]),
            agent_registry=Web3.to_checksum_address(record[2]),
            agent_id=int(record[3]),
            submitted_at=int(record[4]),
            challenged_at=int(record[5]),
            stake_wei=int(record[6]),
            challenge_bond_wei=int(record[7]),
            report_hash=Web3.to_hex(record[8]),
            metadata_hash=Web3.to_hex(record[9]),
            max_severity=int(record[10]),
            finding_count=int(record[11]),
            state=self._request_claim_state_label(int(record[12])),
            resolution=self._resolution_label(int(record[13])),
            challenger_address=(
                None
                if int(record[14], 16) == 0
                else Web3.to_checksum_address(record[14])
            ),
            evidence_hash=(
                None
                if Web3.to_hex(record[15]) == "0x0000000000000000000000000000000000000000000000000000000000000000"
                else Web3.to_hex(record[15])
            ),
        )

    def preview_audit_request_claim_settlement(
        self, claim_id: int
    ) -> OnchainAuditRequestClaimSettlementPreview:
        record = self.contract.functions.previewAuditRequestClaimSettlement(claim_id).call()
        return OnchainAuditRequestClaimSettlementPreview(
            claim_id=claim_id,
            eligible=bool(record[0]),
            withdrawn=bool(record[1]),
            bounty_share_wei=int(record[2]),
            payout_wei=int(record[3]),
        )

    def preview_audit_request_refund(
        self, request_id: int
    ) -> OnchainAuditRequestRefundPreview:
        record = self.contract.functions.previewAuditRequestRefund(request_id).call()
        return OnchainAuditRequestRefundPreview(
            request_id=request_id,
            available=bool(record[0]),
            refund_wei=int(record[1]),
        )

    def classify_audit_request_claims(
        self, *, request_id: int, max_claims: int
    ) -> AuditRequestSettlementResult:
        runtime_chain_id = int(self.web3.eth.chain_id)
        classify_call = self.contract.functions.classifyAuditRequestClaims(
            request_id,
            max_claims,
        )
        receipt = self._submit_transaction(
            classify_call,
            value_wei=0,
            chain_id=runtime_chain_id,
            action_label="classify audit request claims",
            error_cls=OnchainRequestError,
        )
        if receipt["status"] != 1:
            raise OnchainRequestError("Audit request claim classification reverted on-chain.")
        return AuditRequestSettlementResult(
            request_id=request_id,
            tx_hash=Web3.to_hex(receipt["transactionHash"]),
            chain_id=runtime_chain_id,
        )

    def finalize_audit_request_settlement(
        self, *, request_id: int
    ) -> AuditRequestSettlementResult:
        runtime_chain_id = int(self.web3.eth.chain_id)
        finalize_call = self.contract.functions.finalizeAuditRequestSettlement(request_id)
        receipt = self._submit_transaction(
            finalize_call,
            value_wei=0,
            chain_id=runtime_chain_id,
            action_label="finalize audit request settlement",
            error_cls=OnchainRequestError,
        )
        if receipt["status"] != 1:
            raise OnchainRequestError("Audit request settlement finalization reverted on-chain.")
        return AuditRequestSettlementResult(
            request_id=request_id,
            tx_hash=Web3.to_hex(receipt["transactionHash"]),
            chain_id=runtime_chain_id,
        )

    def withdraw_audit_request_claim_settlement(
        self, *, claim_id: int
    ) -> AuditRequestClaimSettlementWithdrawalResult:
        runtime_chain_id = int(self.web3.eth.chain_id)
        withdrawal_call = self.contract.functions.withdrawAuditRequestClaimSettlement(
            claim_id
        )
        receipt = self._submit_transaction(
            withdrawal_call,
            value_wei=0,
            chain_id=runtime_chain_id,
            action_label="withdraw audit request claim settlement",
            error_cls=OnchainRequestError,
        )
        if receipt["status"] != 1:
            raise OnchainRequestError(
                "Audit request claim settlement withdrawal reverted on-chain."
            )
        events = self.contract.events.AuditRequestClaimSettlementWithdrawn().process_receipt(
            receipt
        )
        if not events:
            raise OnchainRequestError(
                "Audit request claim settlement withdrawal succeeded but "
                "AuditRequestClaimSettlementWithdrawn event was missing."
            )
        event = events[0]["args"]
        return AuditRequestClaimSettlementWithdrawalResult(
            request_id=int(event["requestId"]),
            claim_id=int(event["claimId"]),
            tx_hash=Web3.to_hex(receipt["transactionHash"]),
            chain_id=runtime_chain_id,
            beneficiary_address=Web3.to_checksum_address(event["auditor"]),
            returned_stake_wei=int(event["returnedStakeAmount"]),
            bounty_share_wei=int(event["bountyShareAmount"]),
            payout_wei=int(event["payoutAmount"]),
        )

    def withdraw_audit_request_refund(
        self, *, request_id: int
    ) -> AuditRequestRefundWithdrawalResult:
        runtime_chain_id = int(self.web3.eth.chain_id)
        refund_call = self.contract.functions.withdrawAuditRequestRefund(request_id)
        receipt = self._submit_transaction(
            refund_call,
            value_wei=0,
            chain_id=runtime_chain_id,
            action_label="withdraw audit request refund",
            error_cls=OnchainRequestError,
        )
        if receipt["status"] != 1:
            raise OnchainRequestError("Audit request refund withdrawal reverted on-chain.")
        events = self.contract.events.AuditRequestRefunded().process_receipt(receipt)
        if not events:
            raise OnchainRequestError(
                "Audit request refund withdrawal succeeded but AuditRequestRefunded event was missing."
            )
        event = events[0]["args"]
        return AuditRequestRefundWithdrawalResult(
            request_id=int(event["requestId"]),
            tx_hash=Web3.to_hex(receipt["transactionHash"]),
            chain_id=runtime_chain_id,
            beneficiary_address=Web3.to_checksum_address(event["requester"]),
            refund_wei=int(event["bountyAmount"]),
        )

    def challenge_audit_request_claim(
        self,
        *,
        claim_id: int,
        agent_registry: str,
        agent_id: int,
        evidence_hash: str,
        challenge_bond_wei: int,
    ) -> AuditRequestClaimChallengeResult:
        runtime_chain_id = int(self.web3.eth.chain_id)
        challenge_call = self.contract.functions.challengeAuditRequestClaim(
            claim_id,
            Web3.to_checksum_address(agent_registry),
            agent_id,
            HexBytes(evidence_hash),
        )
        receipt = self._submit_transaction(
            challenge_call,
            value_wei=challenge_bond_wei,
            chain_id=runtime_chain_id,
            action_label="open audit request claim challenge",
            error_cls=OnchainChallengeError,
        )
        if receipt["status"] != 1:
            raise OnchainChallengeError(
                "Audit request claim challenge transaction reverted on-chain."
            )
        events = self.contract.events.AuditRequestClaimChallengeOpened().process_receipt(
            receipt
        )
        if not events:
            raise OnchainChallengeError(
                "Audit request claim challenge transaction succeeded but "
                "AuditRequestClaimChallengeOpened event was missing."
            )
        event = events[0]["args"]
        event_claim_id = int(event["claimId"])
        if event_claim_id != claim_id:
            raise OnchainChallengeError(
                "Audit request claim challenge transaction emitted an unexpected claim id."
            )
        event_challenger = Web3.to_checksum_address(event["challenger"])
        event_evidence_hash = Web3.to_hex(event["evidenceHash"])
        event_bond = int(event["challengeBond"])
        if event_evidence_hash != evidence_hash:
            raise OnchainChallengeError(
                "Audit request claim challenge emitted an unexpected evidence hash."
            )
        if event_bond != challenge_bond_wei:
            raise OnchainChallengeError(
                "Audit request claim challenge emitted an unexpected challenge bond."
            )

        onchain_claim = self.get_audit_request_claim(claim_id)
        self._verify_onchain_request_claim_challenge(
            claim_id=claim_id,
            challenger_address=event_challenger,
            evidence_hash=evidence_hash,
            challenge_bond_wei=challenge_bond_wei,
        )
        return AuditRequestClaimChallengeResult(
            request_id=onchain_claim.request_id,
            claim_id=claim_id,
            tx_hash=Web3.to_hex(receipt["transactionHash"]),
            chain_id=runtime_chain_id,
            evidence_hash=evidence_hash,
            challenger_address=event_challenger,
            challenge_bond_wei=challenge_bond_wei,
        )

    def resolve_audit_request_claim_challenge(
        self,
        *,
        claim_id: int,
        upheld: bool,
    ) -> AuditRequestClaimResolutionResult:
        runtime_chain_id = int(self.web3.eth.chain_id)
        resolution = "upheld" if upheld else "rejected"
        resolve_call = self.contract.functions.resolveAuditRequestClaimChallenge(
            claim_id,
            upheld,
        )
        receipt = self._submit_transaction(
            resolve_call,
            value_wei=0,
            chain_id=runtime_chain_id,
            action_label="resolve audit request claim challenge",
            error_cls=OnchainResolveError,
        )
        if receipt["status"] != 1:
            raise OnchainResolveError(
                "Audit request claim resolution transaction reverted on-chain."
            )
        events = self.contract.events.AuditRequestClaimChallengeResolved().process_receipt(
            receipt
        )
        if not events:
            raise OnchainResolveError(
                "Audit request claim resolution transaction succeeded but "
                "AuditRequestClaimChallengeResolved event was missing."
            )
        event = events[0]["args"]
        event_claim_id = int(event["claimId"])
        if event_claim_id != claim_id:
            raise OnchainResolveError(
                "Audit request claim resolution transaction emitted an unexpected claim id."
            )
        event_resolution = self._resolution_label(int(event["resolution"]))
        if event_resolution != resolution:
            raise OnchainResolveError(
                "Audit request claim resolution emitted an unexpected resolution."
            )
        beneficiary_address = Web3.to_checksum_address(event["beneficiary"])
        gross_payout_wei = int(event["grossPayout"])
        resolution_fee_wei = int(event["resolutionFeeAmount"])
        payout_wei = int(event["payoutAmount"])
        onchain_claim = self.get_audit_request_claim(claim_id)
        self._verify_onchain_request_claim_resolution(
            claim_id=claim_id,
            resolution=resolution,
        )
        return AuditRequestClaimResolutionResult(
            request_id=onchain_claim.request_id,
            claim_id=claim_id,
            tx_hash=Web3.to_hex(receipt["transactionHash"]),
            chain_id=runtime_chain_id,
            resolution=resolution,
            beneficiary_address=beneficiary_address,
            gross_payout_wei=gross_payout_wei,
            resolution_fee_wei=resolution_fee_wei,
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

    def _verify_onchain_request_claim_challenge(
        self,
        *,
        claim_id: int,
        challenger_address: str,
        evidence_hash: str,
        challenge_bond_wei: int,
    ) -> None:
        claim = self.get_audit_request_claim(claim_id)
        if claim.state != "challenged":
            raise OnchainChallengeError("On-chain audit request claim state is not Challenged.")
        if claim.challenge_bond_wei != challenge_bond_wei:
            raise OnchainChallengeError(
                "On-chain audit request claim challenge bond did not match challenge input."
            )
        if claim.challenger_address != challenger_address:
            raise OnchainChallengeError(
                "On-chain audit request claim challenger did not match challenge input."
            )
        if claim.evidence_hash != evidence_hash:
            raise OnchainChallengeError(
                "On-chain audit request claim evidence hash did not match challenge input."
            )

    def _verify_onchain_request_claim_resolution(
        self,
        *,
        claim_id: int,
        resolution: str,
    ) -> None:
        claim = self.get_audit_request_claim(claim_id)
        if claim.resolution != resolution:
            raise OnchainResolveError(
                "On-chain audit request claim resolution did not match transaction output."
            )
        expected_state = "slashed" if resolution == "upheld" else "resolved"
        if claim.state != expected_state:
            raise OnchainResolveError(
                "On-chain audit request claim state did not match transaction output."
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

    def _allowlist_commitment(self, allowlisted_auditors: list[str]) -> str:
        encoded = self.web3.codec.encode(
            ["address[]"],
            [[Web3.to_checksum_address(value) for value in allowlisted_auditors]],
        )
        return Web3.to_hex(Web3.keccak(encoded))

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
        account: Any = None,
    ) -> Any:
        account = account if account is not None else self.account
        transaction = {
            "from": account.address,
            "nonce": self.web3.eth.get_transaction_count(account.address),
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
                account.key,
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

    def _request_state_label(self, state: int) -> str:
        if state == 1:
            return "open"
        if state == 2:
            return "closed"
        if state == 3:
            return "expired"
        if state == 4:
            return "settled"
        return "none"

    def _request_claim_state_label(self, state: int) -> str:
        if state == 1:
            return "submitted"
        if state == 2:
            return "challenged"
        if state == 3:
            return "slashed"
        if state == 4:
            return "resolved"
        return "none"
