// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script} from "forge-std/Script.sol";
import {AgentIdentityRegistry} from "../src/AgentIdentityRegistry.sol";

contract RegisterAuditorIdentity is Script {
    struct RegistrationParams {
        address registry;
        address owner;
        string registrationURI;
    }

    function run() external returns (uint256 agentId) {
        RegistrationParams memory params = _paramsFromEnv();

        vm.startBroadcast();
        agentId = AgentIdentityRegistry(params.registry).registerAgent(
            params.owner,
            params.registrationURI
        );
        vm.stopBroadcast();
    }

    function preview() external view returns (RegistrationParams memory) {
        return _paramsFromEnv();
    }

    function _paramsFromEnv()
        internal
        view
        returns (RegistrationParams memory)
    {
        address owner = vm.envOr(
            "PROOF_OF_AUDIT_AUDITOR_OWNER",
            vm.envAddress("PROOF_OF_AUDIT_ARBITER")
        );
        return
            RegistrationParams({
                registry: vm.envAddress("PROOF_OF_AUDIT_AGENT_REGISTRY_ADDRESS"),
                owner: owner,
                registrationURI: vm.envString(
                    "PROOF_OF_AUDIT_AUDITOR_REGISTRATION_URI"
                )
            });
    }
}
