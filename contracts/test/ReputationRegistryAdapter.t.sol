// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "forge-std/Test.sol";

import {AgentIdentityRegistry} from "../src/AgentIdentityRegistry.sol";
import {ReputationRegistryAdapter} from "../src/ReputationRegistryAdapter.sol";

contract ReputationRegistryAdapterTest is Test {
    AgentIdentityRegistry internal identityRegistry;
    ReputationRegistryAdapter internal reputationRegistry;

    address internal admin = address(0xA11CE);
    address internal auditorOwner = address(0xB0B);
    address internal validator = address(0xC0DE);

    uint256 internal agentId;

    function setUp() external {
        vm.prank(admin);
        identityRegistry = new AgentIdentityRegistry(admin);

        vm.prank(admin);
        agentId = identityRegistry.registerAgent(
            auditorOwner,
            "ipfs://proof-of-audit/registration.json"
        );

        reputationRegistry = new ReputationRegistryAdapter(
            address(identityRegistry),
            validator
        );
    }

    function testRecordClaimUpdatesAgentStats() external {
        bytes32 claimHash = keccak256("claim");

        vm.prank(auditorOwner);
        reputationRegistry.recordClaim(
            agentId,
            claimHash,
            0.01 ether,
            "ipfs://proof-of-audit/reputation/claim.json"
        );

        (
            uint64 totalClaims,
            uint64 resolvedChallenges,
            uint64 rejectedCount,
            uint64 upheldCount,
            uint256 totalStakeWei,
            ,
            uint8 score
        ) = reputationRegistry.getReputation(agentId);

        assertEq(totalClaims, 1);
        assertEq(resolvedChallenges, 0);
        assertEq(rejectedCount, 0);
        assertEq(upheldCount, 0);
        assertEq(totalStakeWei, 0.01 ether);
        assertEq(score, 50);
    }

    function testRecordResolutionUpdatesOutcomeCounts() external {
        bytes32 claimHash = keccak256("claim");

        vm.prank(auditorOwner);
        reputationRegistry.recordClaim(
            agentId,
            claimHash,
            0.01 ether,
            "ipfs://proof-of-audit/reputation/claim.json"
        );

        vm.prank(validator);
        reputationRegistry.recordResolution(
            claimHash,
            true,
            "ipfs://proof-of-audit/reputation/resolution.json"
        );

        (
            uint64 totalClaims,
            uint64 resolvedChallenges,
            uint64 rejectedCount,
            uint64 upheldCount,
            ,
            ,
            uint8 score
        ) = reputationRegistry.getReputation(agentId);

        assertEq(totalClaims, 1);
        assertEq(resolvedChallenges, 1);
        assertEq(rejectedCount, 1);
        assertEq(upheldCount, 0);
        assertEq(score, 100);
    }

    function testRejectsResolutionFromWrongOperator() external {
        bytes32 claimHash = keccak256("claim");

        vm.prank(auditorOwner);
        reputationRegistry.recordClaim(
            agentId,
            claimHash,
            0.01 ether,
            "ipfs://proof-of-audit/reputation/claim.json"
        );

        vm.expectRevert(ReputationRegistryAdapter.NotAuthorized.selector);
        vm.prank(auditorOwner);
        reputationRegistry.recordResolution(
            claimHash,
            false,
            "ipfs://proof-of-audit/reputation/resolution.json"
        );
    }
}
