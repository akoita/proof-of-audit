// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script} from "forge-std/Script.sol";
import {ValidationRegistryAdapter} from "../src/ValidationRegistryAdapter.sol";

contract DeployValidationRegistryAdapter is Script {
    struct DeployParams {
        address identityRegistry;
    }

    function _params() internal view returns (DeployParams memory) {
        return DeployParams({
            identityRegistry: vm.envAddress(
                "PROOF_OF_AUDIT_VALIDATION_IDENTITY_REGISTRY"
            )
        });
    }

    function run() external returns (ValidationRegistryAdapter deployed) {
        DeployParams memory params = _params();
        vm.startBroadcast();
        deployed = new ValidationRegistryAdapter(params.identityRegistry);
        vm.stopBroadcast();
    }
}
