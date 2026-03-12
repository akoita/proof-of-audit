// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script} from "forge-std/Script.sol";
import {ProofOfAudit} from "../src/ProofOfAudit.sol";

contract DeployProofOfAudit is Script {
    struct DeploymentParams {
        address arbiter;
        uint256 requiredStake;
        uint256 requiredChallengeBond;
        uint256 challengeWindow;
    }

    function run() external returns (ProofOfAudit deployed) {
        DeploymentParams memory params = _paramsFromEnv();

        vm.startBroadcast();
        deployed = new ProofOfAudit(
            params.arbiter,
            params.requiredStake,
            params.requiredChallengeBond,
            params.challengeWindow
        );
        vm.stopBroadcast();
    }

    function preview() external view returns (DeploymentParams memory) {
        return _paramsFromEnv();
    }

    function _paramsFromEnv() internal view returns (DeploymentParams memory) {
        return
            DeploymentParams({
                arbiter: vm.envAddress("PROOF_OF_AUDIT_ARBITER"),
                requiredStake: vm.envUint("PROOF_OF_AUDIT_REQUIRED_STAKE_WEI"),
                requiredChallengeBond: vm.envUint(
                    "PROOF_OF_AUDIT_REQUIRED_CHALLENGE_BOND_WEI"
                ),
                challengeWindow: vm.envUint(
                    "PROOF_OF_AUDIT_CHALLENGE_WINDOW_SECONDS"
                )
            });
    }
}
