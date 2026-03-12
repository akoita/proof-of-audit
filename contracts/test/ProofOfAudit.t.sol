// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {ProofOfAudit} from "../src/ProofOfAudit.sol";

contract ProofOfAuditTest is Test {
    ProofOfAudit internal registry;

    address internal arbiter = address(0xA11CE);
    address internal auditor = address(0xB0B);
    address internal challenger = address(0xCA11);
    address internal target = address(0xD00D);

    uint256 internal constant STAKE = 0.01 ether;
    uint256 internal constant BOND = 0.005 ether;
    uint256 internal constant WINDOW = 1 days;

    function setUp() public {
        registry = new ProofOfAudit(arbiter, STAKE, BOND, WINDOW);
        vm.deal(auditor, 1 ether);
        vm.deal(challenger, 1 ether);
    }

    function testPublishAuditStoresRecord() public {
        vm.prank(auditor);
        uint256 auditId = registry.publishAudit{value: STAKE}(
            target,
            keccak256("report"),
            keccak256("metadata"),
            3,
            2
        );

        ProofOfAudit.AuditRecord memory audit = registry.getAudit(auditId);

        assertEq(audit.auditor, auditor);
        assertEq(audit.target, target);
        assertEq(audit.reportHash, keccak256("report"));
        assertEq(audit.metadataHash, keccak256("metadata"));
        assertEq(uint256(audit.publishedAt), block.timestamp);
        assertEq(uint256(audit.stakeAmount), STAKE);
        assertEq(audit.maxSeverity, 3);
        assertEq(audit.findingCount, 2);
        assertEq(uint256(audit.state), uint256(ProofOfAudit.AuditState.Published));
    }

    function testChallengeCanBeResolvedInFavorOfChallenger() public {
        uint256 auditId = _publishDefaultAudit();
        uint256 challengerBalanceBefore = challenger.balance;

        vm.prank(challenger);
        registry.challengeAudit{value: BOND}(auditId, keccak256("poc"));

        vm.prank(arbiter);
        registry.resolveChallenge(auditId, true);

        assertEq(challenger.balance, challengerBalanceBefore + STAKE);
        ProofOfAudit.AuditRecord memory audit = registry.getAudit(auditId);
        assertEq(uint256(audit.state), uint256(ProofOfAudit.AuditState.Resolved));
        assertEq(
            uint256(audit.resolution),
            uint256(ProofOfAudit.Resolution.ChallengeUpheld)
        );
        assertEq(audit.challenger, challenger);
    }

    function testRejectedChallengeRewardsAuditor() public {
        uint256 auditId = _publishDefaultAudit();
        uint256 auditorBalanceBeforeChallenge = auditor.balance;

        vm.prank(challenger);
        registry.challengeAudit{value: BOND}(auditId, keccak256("weak-poc"));

        vm.prank(arbiter);
        registry.resolveChallenge(auditId, false);

        assertEq(auditor.balance, auditorBalanceBeforeChallenge + STAKE + BOND);
    }

    function testReleaseStakeAfterWindow() public {
        uint256 auditId = _publishDefaultAudit();
        uint256 auditorBalanceAfterPublish = auditor.balance;

        vm.warp(block.timestamp + WINDOW + 1);
        registry.releaseStake(auditId);

        assertEq(auditor.balance, auditorBalanceAfterPublish + STAKE);
    }

    function testCannotChallengeAfterWindow() public {
        uint256 auditId = _publishDefaultAudit();
        vm.warp(block.timestamp + WINDOW + 1);

        vm.prank(challenger);
        vm.expectRevert(ProofOfAudit.ChallengeWindowClosed.selector);
        registry.challengeAudit{value: BOND}(auditId, keccak256("late-poc"));
    }

    function _publishDefaultAudit() internal returns (uint256 auditId) {
        vm.prank(auditor);
        auditId = registry.publishAudit{value: STAKE}(
            target,
            keccak256("report"),
            keccak256("metadata"),
            3,
            2
        );
    }
}
