// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script} from "forge-std/Script.sol";
import {AgentIdentityRegistry} from "../src/AgentIdentityRegistry.sol";

contract DeployAgentIdentityRegistry is Script {
    struct DeploymentParams {
        address admin;
    }

    function run() external returns (AgentIdentityRegistry deployed) {
        DeploymentParams memory params = _paramsFromEnv();

        vm.startBroadcast();
        deployed = new AgentIdentityRegistry(params.admin);
        vm.stopBroadcast();
    }

    function preview() external view returns (DeploymentParams memory) {
        return _paramsFromEnv();
    }

    function _paramsFromEnv() internal view returns (DeploymentParams memory) {
        address admin = vm.envOr(
            "PROOF_OF_AUDIT_AGENT_REGISTRY_ADMIN",
            vm.envAddress("PROOF_OF_AUDIT_ARBITER")
        );
        return DeploymentParams({admin: admin});
    }
}
