// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script} from "forge-std/Script.sol";
import {ProofOfAudit} from "../src/ProofOfAudit.sol";

contract DeployProofOfAudit is Script {
    struct DeploymentParams {
        address arbiter;
        address treasury;
        uint256 requiredStake;
        uint256 requiredChallengeBond;
        uint256 challengeWindow;
        uint256 challengeResolutionWindow;
        uint256 protocolFeeBps;
        uint256 resolutionFeeBps;
    }

    function run() external returns (ProofOfAudit deployed) {
        DeploymentParams memory params = _paramsFromEnv();

        vm.startBroadcast();
        deployed = new ProofOfAudit(
            params.arbiter,
            params.treasury,
            params.requiredStake,
            params.requiredChallengeBond,
            params.challengeWindow,
            params.challengeResolutionWindow,
            params.protocolFeeBps,
            params.resolutionFeeBps
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
                treasury: vm.envAddress("PROOF_OF_AUDIT_TREASURY_ADDRESS"),
                requiredStake: vm.envUint("PROOF_OF_AUDIT_REQUIRED_STAKE_WEI"),
                requiredChallengeBond: vm.envUint(
                    "PROOF_OF_AUDIT_REQUIRED_CHALLENGE_BOND_WEI"
                ),
                challengeWindow: vm.envUint(
                    "PROOF_OF_AUDIT_CHALLENGE_WINDOW_SECONDS"
                ),
                challengeResolutionWindow: vm.envOr(
                    "PROOF_OF_AUDIT_CHALLENGE_RESOLUTION_WINDOW_SECONDS",
                    uint256(172800)
                ),
                protocolFeeBps: vm.envUint("PROOF_OF_AUDIT_PROTOCOL_FEE_BPS"),
                resolutionFeeBps: vm.envUint("PROOF_OF_AUDIT_RESOLUTION_FEE_BPS")
            });
    }
}
