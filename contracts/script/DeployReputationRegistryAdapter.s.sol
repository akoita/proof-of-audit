// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "forge-std/Script.sol";

import {ReputationRegistryAdapter} from "../src/ReputationRegistryAdapter.sol";

contract DeployReputationRegistryAdapter is Script {
    function run() external returns (ReputationRegistryAdapter adapter) {
        address identityRegistry = vm.envAddress("PROOF_OF_AUDIT_AUDITOR_AGENT_REGISTRY");
        address reputationOperator = vm.envAddress("PROOF_OF_AUDIT_REPUTATION_OPERATOR");

        vm.startBroadcast();
        adapter = new ReputationRegistryAdapter(identityRegistry, reputationOperator);
        vm.stopBroadcast();
    }
}
