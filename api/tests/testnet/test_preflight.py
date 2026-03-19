from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from api.tests.testnet.conftest import TestnetContext


@pytest.mark.testnet_smoke
def test_base_sepolia_preflight_validates_configured_environment(
    testnet_context: TestnetContext,
) -> None:
    assert testnet_context.client.get("/health").json() == {"status": "ok"}
    assert testnet_context.config["network"] == "base-sepolia"
    assert int(testnet_context.config["chain_id"]) == testnet_context.chain_id
    assert testnet_context.web3.eth.chain_id == testnet_context.chain_id
    assert int(testnet_context.web3.eth.get_balance(testnet_context.operator_address)) > 0
    assert testnet_context.smoke_fixture["id"] == "clean-vault"

    for address in testnet_context.verified_addresses.values():
        code = testnet_context.web3.eth.get_code(
            testnet_context.web3.to_checksum_address(address)
        )
        assert code and code != b"\x00"
