from __future__ import annotations

from dataclasses import dataclass

from eth_tester import EthereumTester, PyEVMBackend
from web3 import EthereumTesterProvider, Web3
from web3.contract import Contract

from proof_of_audit_api.config import ContractConfig
from proof_of_audit_api.publisher import (
    ProofOfAuditPublisher,
    load_contract_abi,
    load_contract_bytecode,
)


@dataclass(frozen=True)
class OnchainTestContext:
    web3: Web3
    contract: Contract
    contract_config: ContractConfig
    publisher: ProofOfAuditPublisher


def build_onchain_test_context() -> OnchainTestContext:
    tester = EthereumTester(backend=PyEVMBackend())
    web3 = Web3(EthereumTesterProvider(tester))
    backend = tester.backend
    deployer_key = backend.account_keys[0]
    deployer_address = web3.eth.account.from_key(deployer_key).address
    arbiter_address = tester.get_accounts()[1]

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

    contract_config = ContractConfig.from_env(
        {
            "PROOF_OF_AUDIT_NETWORK": "eth-tester",
            "PROOF_OF_AUDIT_CHAIN_ID": str(web3.eth.chain_id),
            "PROOF_OF_AUDIT_CONTRACT_ADDRESS": receipt["contractAddress"],
            "PROOF_OF_AUDIT_EXPLORER_BASE_URL": "http://127.0.0.1:8545",
            "PROOF_OF_AUDIT_ARBITER": arbiter_address,
            "PROOF_OF_AUDIT_PRIVATE_KEY": deployer_key.to_hex(),
            "PROOF_OF_AUDIT_REQUIRED_STAKE_WEI": str(10**16),
            "PROOF_OF_AUDIT_REQUIRED_CHALLENGE_BOND_WEI": str(5 * 10**15),
            "PROOF_OF_AUDIT_CHALLENGE_WINDOW_SECONDS": "86400",
        }
    )
    publisher = ProofOfAuditPublisher(contract_config, web3=web3)
    return OnchainTestContext(
        web3=web3,
        contract=publisher.contract,
        contract_config=contract_config,
        publisher=publisher,
    )
