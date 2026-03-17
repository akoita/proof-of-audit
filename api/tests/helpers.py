from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from eth_tester import EthereumTester, PyEVMBackend
from web3 import EthereumTesterProvider, Web3
from web3.contract import Contract

from proof_of_audit_api.config import ContractConfig
from proof_of_audit_api.publisher import (
    ProofOfAuditPublisher,
    load_contract_abi,
    load_contract_bytecode,
)
from proof_of_audit_api.reputation_bridge import (
    ReputationRegistryBridge,
    load_reputation_bridge_abi,
)
from proof_of_audit_api.validation_bridge import (
    ValidationRegistryBridge,
    load_validation_bridge_abi,
)


ROOT_DIR = Path(__file__).resolve().parents[2]
AGENT_IDENTITY_ARTIFACT = (
    ROOT_DIR / "contracts" / "out" / "AgentIdentityRegistry.sol" / "AgentIdentityRegistry.json"
)
VALIDATION_REGISTRY_ARTIFACT = (
    ROOT_DIR / "contracts" / "out" / "ValidationRegistryAdapter.sol" / "ValidationRegistryAdapter.json"
)
REPUTATION_REGISTRY_ARTIFACT = (
    ROOT_DIR
    / "contracts"
    / "out"
    / "ReputationRegistryAdapter.sol"
    / "ReputationRegistryAdapter.json"
)


def load_agent_identity_artifact() -> dict[str, object]:
    return json.loads(AGENT_IDENTITY_ARTIFACT.read_text(encoding="utf-8"))


def load_agent_identity_abi() -> list[dict[str, object]]:
    return load_agent_identity_artifact()["abi"]  # type: ignore[index]


def load_agent_identity_bytecode() -> str:
    return load_agent_identity_artifact()["bytecode"]["object"]  # type: ignore[index]


def load_validation_registry_bytecode() -> str:
    return json.loads(VALIDATION_REGISTRY_ARTIFACT.read_text(encoding="utf-8"))["bytecode"][
        "object"
    ]


def load_reputation_registry_bytecode() -> str:
    return json.loads(REPUTATION_REGISTRY_ARTIFACT.read_text(encoding="utf-8"))["bytecode"][
        "object"
    ]


@dataclass(frozen=True)
class OnchainTestContext:
    web3: Web3
    contract: Contract
    identity_registry: Contract
    validation_registry: Contract
    reputation_registry: Contract
    contract_config: ContractConfig
    publisher: ProofOfAuditPublisher
    arbiter_client: ProofOfAuditPublisher
    validation_bridge: ValidationRegistryBridge
    reputation_bridge: ReputationRegistryBridge


def build_onchain_test_context() -> OnchainTestContext:
    tester = EthereumTester(backend=PyEVMBackend())
    web3 = Web3(EthereumTesterProvider(tester))
    backend = tester.backend
    deployer_key = backend.account_keys[0]
    deployer_address = web3.eth.account.from_key(deployer_key).address
    arbiter_address = tester.get_accounts()[1]
    arbiter_key = backend.account_keys[1]
    validator_address = tester.get_accounts()[2]
    validator_key = backend.account_keys[2]

    contract_factory = web3.eth.contract(
        abi=load_contract_abi(),
        bytecode=load_contract_bytecode(),
    )
    deployment_transaction = contract_factory.constructor(
        arbiter_address,
        10**16,
        5 * 10**15,
        86400,
    ).build_transaction(
        {
            "from": deployer_address,
            "nonce": web3.eth.get_transaction_count(deployer_address),
            "gas": 3_000_000,
            "maxFeePerGas": web3.to_wei(2, "gwei"),
            "maxPriorityFeePerGas": web3.to_wei(1, "gwei"),
            "chainId": web3.eth.chain_id,
        }
    )
    signed = web3.eth.account.sign_transaction(
        deployment_transaction,
        deployer_key.to_hex(),
    )
    tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

    identity_factory = web3.eth.contract(
        abi=load_agent_identity_abi(),
        bytecode=load_agent_identity_bytecode(),
    )
    identity_deployment = identity_factory.constructor(
        deployer_address
    ).build_transaction(
        {
            "from": deployer_address,
            "nonce": web3.eth.get_transaction_count(deployer_address),
            "gas": 3_000_000,
            "maxFeePerGas": web3.to_wei(2, "gwei"),
            "maxPriorityFeePerGas": web3.to_wei(1, "gwei"),
            "chainId": web3.eth.chain_id,
        }
    )
    signed_identity = web3.eth.account.sign_transaction(
        identity_deployment,
        deployer_key.to_hex(),
    )
    identity_tx_hash = web3.eth.send_raw_transaction(signed_identity.raw_transaction)
    identity_receipt = web3.eth.wait_for_transaction_receipt(identity_tx_hash)
    identity_registry = web3.eth.contract(
        address=identity_receipt["contractAddress"],
        abi=load_agent_identity_abi(),
    )
    register_identity = identity_registry.functions.registerAgent(
        deployer_address,
        "https://example.invalid/auditor-registration.json",
    ).build_transaction(
        {
            "from": deployer_address,
            "nonce": web3.eth.get_transaction_count(deployer_address),
            "gas": 3_000_000,
            "maxFeePerGas": web3.to_wei(2, "gwei"),
            "maxPriorityFeePerGas": web3.to_wei(1, "gwei"),
            "chainId": web3.eth.chain_id,
        }
    )
    signed_register_identity = web3.eth.account.sign_transaction(
        register_identity,
        deployer_key.to_hex(),
    )
    register_identity_hash = web3.eth.send_raw_transaction(
        signed_register_identity.raw_transaction
    )
    web3.eth.wait_for_transaction_receipt(register_identity_hash)

    validation_factory = web3.eth.contract(
        abi=load_validation_bridge_abi(),
        bytecode=load_validation_registry_bytecode(),
    )
    validation_deployment = validation_factory.constructor(
        identity_receipt["contractAddress"]
    ).build_transaction(
        {
            "from": deployer_address,
            "nonce": web3.eth.get_transaction_count(deployer_address),
            "gas": 3_000_000,
            "maxFeePerGas": web3.to_wei(2, "gwei"),
            "maxPriorityFeePerGas": web3.to_wei(1, "gwei"),
            "chainId": web3.eth.chain_id,
        }
    )
    signed_validation = web3.eth.account.sign_transaction(
        validation_deployment,
        deployer_key.to_hex(),
    )
    validation_tx_hash = web3.eth.send_raw_transaction(signed_validation.raw_transaction)
    validation_receipt = web3.eth.wait_for_transaction_receipt(validation_tx_hash)
    validation_registry = web3.eth.contract(
        address=validation_receipt["contractAddress"],
        abi=load_validation_bridge_abi(),
    )
    reputation_factory = web3.eth.contract(
        abi=load_reputation_bridge_abi(),
        bytecode=load_reputation_registry_bytecode(),
    )
    reputation_deployment = reputation_factory.constructor(
        identity_receipt["contractAddress"],
        validator_address,
    ).build_transaction(
        {
            "from": deployer_address,
            "nonce": web3.eth.get_transaction_count(deployer_address),
            "gas": 3_000_000,
            "maxFeePerGas": web3.to_wei(2, "gwei"),
            "maxPriorityFeePerGas": web3.to_wei(1, "gwei"),
            "chainId": web3.eth.chain_id,
        }
    )
    signed_reputation = web3.eth.account.sign_transaction(
        reputation_deployment,
        deployer_key.to_hex(),
    )
    reputation_tx_hash = web3.eth.send_raw_transaction(signed_reputation.raw_transaction)
    reputation_receipt = web3.eth.wait_for_transaction_receipt(reputation_tx_hash)
    reputation_registry = web3.eth.contract(
        address=reputation_receipt["contractAddress"],
        abi=load_reputation_bridge_abi(),
    )

    contract_config = ContractConfig.from_env(
        {
            "PROOF_OF_AUDIT_NETWORK": "eth-tester",
            "PROOF_OF_AUDIT_CHAIN_ID": str(web3.eth.chain_id),
            "PROOF_OF_AUDIT_CONTRACT_ADDRESS": receipt["contractAddress"],
            "PROOF_OF_AUDIT_EXPLORER_BASE_URL": "http://127.0.0.1:8545",
            "PROOF_OF_AUDIT_ARBITER": arbiter_address,
            "PROOF_OF_AUDIT_PRIVATE_KEY": deployer_key.to_hex(),
            "PROOF_OF_AUDIT_ARBITER_PRIVATE_KEY": arbiter_key.to_hex(),
            "PROOF_OF_AUDIT_AUDITOR_OWNER_PRIVATE_KEY": deployer_key.to_hex(),
            "PROOF_OF_AUDIT_VALIDATOR_PRIVATE_KEY": validator_key.to_hex(),
            "PROOF_OF_AUDIT_VALIDATOR_ADDRESS": validator_address,
            "PROOF_OF_AUDIT_REQUIRED_STAKE_WEI": str(10**16),
            "PROOF_OF_AUDIT_REQUIRED_CHALLENGE_BOND_WEI": str(5 * 10**15),
            "PROOF_OF_AUDIT_CHALLENGE_WINDOW_SECONDS": "86400",
            "PROOF_OF_AUDIT_AUDITOR_AGENT_ID": "1",
            "PROOF_OF_AUDIT_AUDITOR_AGENT_REGISTRY": identity_receipt["contractAddress"],
            "PROOF_OF_AUDIT_AUDITOR_IDENTITY_SOURCE": "project-local-custom",
            "PROOF_OF_AUDIT_VALIDATION_REGISTRY_ADDRESS": validation_receipt["contractAddress"],
            "PROOF_OF_AUDIT_VALIDATION_BRIDGE_SOURCE": "project-local-custom",
            "PROOF_OF_AUDIT_REPUTATION_REGISTRY_ADDRESS": reputation_receipt["contractAddress"],
            "PROOF_OF_AUDIT_REPUTATION_BRIDGE_SOURCE": "project-local-custom",
            "PROOF_OF_AUDIT_REPUTATION_OPERATOR_PRIVATE_KEY": validator_key.to_hex(),
            "PROOF_OF_AUDIT_REPUTATION_OPERATOR_ADDRESS": validator_address,
            "PROOF_OF_AUDIT_RUNTIME_API_URL": "http://127.0.0.1:8080",
        }
    )
    publisher = ProofOfAuditPublisher(contract_config, web3=web3)
    arbiter_client = ProofOfAuditPublisher(
        contract_config,
        web3=web3,
        private_key=arbiter_key.to_hex(),
    )
    validation_bridge = ValidationRegistryBridge(contract_config, web3=web3)
    reputation_bridge = ReputationRegistryBridge(contract_config, web3=web3)
    return OnchainTestContext(
        web3=web3,
        contract=publisher.contract,
        identity_registry=identity_registry,
        validation_registry=validation_registry,
        reputation_registry=reputation_registry,
        contract_config=contract_config,
        publisher=publisher,
        arbiter_client=arbiter_client,
        validation_bridge=validation_bridge,
        reputation_bridge=reputation_bridge,
    )
