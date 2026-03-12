import unittest

from proof_of_audit_api.config import ContractConfig


class ContractConfigTest(unittest.TestCase):
    def test_defaults_match_base_sepolia_profile(self) -> None:
        config = ContractConfig.from_env({})

        self.assertEqual(config.network, "base-sepolia")
        self.assertEqual(config.chain_id, 84532)
        self.assertEqual(config.explorer_base_url, "https://sepolia.basescan.org")
        self.assertEqual(config.required_stake_wei, 10**16)
        self.assertEqual(config.required_challenge_bond_wei, 5 * 10**15)
        self.assertEqual(config.challenge_window_seconds, 86400)
        self.assertFalse(config.deployment_ready)

    def test_reads_environment_overrides(self) -> None:
        config = ContractConfig.from_env(
            {
                "PROOF_OF_AUDIT_NETWORK": "base-sepolia",
                "PROOF_OF_AUDIT_CHAIN_ID": "84532",
                "PROOF_OF_AUDIT_CONTRACT_ADDRESS": "0xabc",
                "PROOF_OF_AUDIT_EXPLORER_BASE_URL": "https://sepolia.basescan.org/",
                "PROOF_OF_AUDIT_ARBITER": "0xarbiter",
                "PROOF_OF_AUDIT_RPC_URL": "https://rpc.example",
                "PROOF_OF_AUDIT_PRIVATE_KEY": "secret",
                "PROOF_OF_AUDIT_REQUIRED_STAKE_WEI": "123",
                "PROOF_OF_AUDIT_REQUIRED_CHALLENGE_BOND_WEI": "45",
                "PROOF_OF_AUDIT_CHALLENGE_WINDOW_SECONDS": "67",
            }
        )

        self.assertEqual(config.contract_address, "0xabc")
        self.assertEqual(config.arbiter, "0xarbiter")
        self.assertEqual(config.rpc_url, "https://rpc.example")
        self.assertEqual(config.publisher_private_key, "secret")
        self.assertEqual(config.required_stake_wei, 123)
        self.assertEqual(config.required_challenge_bond_wei, 45)
        self.assertEqual(config.challenge_window_seconds, 67)
        self.assertTrue(config.deployment_ready)
        self.assertEqual(
            config.transaction_url("0x123"),
            "https://sepolia.basescan.org/tx/0x123",
        )
