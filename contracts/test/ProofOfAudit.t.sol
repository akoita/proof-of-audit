// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {ProofOfAudit} from "../src/ProofOfAudit.sol";

contract MockIdentityRegistry {
    mapping(uint256 => address) internal owners;

    function setOwner(uint256 agentId, address owner) external {
        owners[agentId] = owner;
    }

    function ownerOf(uint256 agentId) external view returns (address) {
        address owner = owners[agentId];
        require(owner != address(0), "missing agent");
        return owner;
    }
}

contract ProofOfAuditTest is Test {
    ProofOfAudit internal registry;
    MockIdentityRegistry internal identityRegistry;

    address internal arbiter = address(0xA11CE);
    address internal auditor = address(0xB0B);
    address internal challenger = address(0xCA11);
    address internal secondAuditor = address(0xC0DE);
    address internal target = address(0xD00D);

    uint256 internal constant STAKE = 0.01 ether;
    uint256 internal constant BOND = 0.005 ether;
    uint256 internal constant WINDOW = 1 days;
    uint256 internal constant BOUNTY = 0.2 ether;

    function setUp() public {
        registry = new ProofOfAudit(arbiter, STAKE, BOND, WINDOW);
        identityRegistry = new MockIdentityRegistry();
        identityRegistry.setOwner(1, auditor);
        identityRegistry.setOwner(2, secondAuditor);
        vm.deal(auditor, 1 ether);
        vm.deal(challenger, 1 ether);
        vm.deal(secondAuditor, 1 ether);
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
        bytes32 evidenceHash = keccak256("poc");

        vm.prank(challenger);
        registry.challengeAudit{value: BOND}(auditId, evidenceHash);

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
        assertEq(audit.evidenceHash, evidenceHash);
    }

    function testRejectedChallengeRewardsAuditor() public {
        uint256 auditId = _publishDefaultAudit();
        uint256 auditorBalanceBeforeChallenge = auditor.balance;
        bytes32 evidenceHash = keccak256("weak-poc");

        vm.prank(challenger);
        registry.challengeAudit{value: BOND}(auditId, evidenceHash);

        vm.prank(arbiter);
        registry.resolveChallenge(auditId, false);

        assertEq(auditor.balance, auditorBalanceBeforeChallenge + STAKE + BOND);
        ProofOfAudit.AuditRecord memory audit = registry.getAudit(auditId);
        assertEq(audit.evidenceHash, evidenceHash);
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

    function testCreateAuditRequestStoresEscrowedRequest() public {
        ProofOfAudit.EligibilityConfig memory eligibility = _defaultEligibility();

        vm.prank(auditor);
        uint256 requestId = registry.createAuditRequest{value: BOUNTY}(
            target,
            uint96(BOUNTY),
            uint64(WINDOW),
            eligibility,
            new address[](0)
        );

        ProofOfAudit.AuditRequest memory requestRecord = registry.getAuditRequest(
            requestId
        );

        assertEq(requestRecord.requester, auditor);
        assertEq(requestRecord.target, target);
        assertEq(uint256(requestRecord.createdAt), block.timestamp);
        assertEq(uint256(requestRecord.responseWindowEnd), block.timestamp + WINDOW);
        assertEq(uint256(requestRecord.bountyAmount), BOUNTY);
        assertEq(uint256(requestRecord.claimCount), 0);
        assertEq(
            uint256(requestRecord.state),
            uint256(ProofOfAudit.AuditRequestState.Open)
        );
        assertEq(
            uint256(requestRecord.eligibility.minimumStakeAmount),
            STAKE
        );
        assertFalse(requestRecord.eligibility.allowlistEnabled);
    }

    function testAuditRequestDerivesClosedStateAfterResponseWindow() public {
        uint256 requestId = _createDefaultAuditRequest();

        vm.warp(block.timestamp + WINDOW + 1);

        ProofOfAudit.AuditRequest memory requestRecord = registry.getAuditRequest(
            requestId
        );

        assertEq(
            uint256(requestRecord.state),
            uint256(ProofOfAudit.AuditRequestState.Closed)
        );
    }

    function testExpiredAuditRequestCanBeRefundedByRequester() public {
        uint256 requestId = _createDefaultAuditRequest();
        uint256 requesterBalanceAfterCreate = auditor.balance;

        vm.warp(block.timestamp + WINDOW + 1);
        registry.expireAuditRequest(requestId);

        vm.prank(auditor);
        registry.refundExpiredAuditRequest(requestId);

        ProofOfAudit.AuditRequest memory requestRecord = registry.getAuditRequest(
            requestId
        );
        assertEq(
            uint256(requestRecord.state),
            uint256(ProofOfAudit.AuditRequestState.Settled)
        );
        assertEq(auditor.balance, requesterBalanceAfterCreate + BOUNTY);
    }

    function testCannotExpireAuditRequestWhileWindowIsOpen() public {
        uint256 requestId = _createDefaultAuditRequest();

        vm.expectRevert(ProofOfAudit.InvalidRequestState.selector);
        registry.expireAuditRequest(requestId);
    }

    function testOnlyRequesterCanRefundExpiredAuditRequest() public {
        uint256 requestId = _createDefaultAuditRequest();

        vm.warp(block.timestamp + WINDOW + 1);
        registry.expireAuditRequest(requestId);

        vm.prank(challenger);
        vm.expectRevert(ProofOfAudit.NotRequester.selector);
        registry.refundExpiredAuditRequest(requestId);
    }

    function testSubmitAuditRequestClaimStoresRecordAndIncrementsCount() public {
        uint256 requestId = _createDefaultAuditRequest();

        vm.prank(auditor);
        uint256 claimId = registry.submitAuditRequestClaim{value: STAKE}(
            requestId,
            address(identityRegistry),
            1,
            keccak256("report"),
            keccak256("metadata"),
            3,
            2
        );

        ProofOfAudit.AuditRequestClaim memory claim = registry.getAuditRequestClaim(
            claimId
        );
        ProofOfAudit.AuditRequest memory requestRecord = registry.getAuditRequest(
            requestId
        );

        assertEq(claim.requestId, requestId);
        assertEq(claim.auditor, auditor);
        assertEq(claim.agentRegistry, address(identityRegistry));
        assertEq(claim.agentId, 1);
        assertEq(uint256(claim.stakeAmount), STAKE);
        assertEq(uint256(claim.state), uint256(ProofOfAudit.AuditRequestClaimState.Submitted));
        assertEq(uint256(requestRecord.claimCount), 1);

        uint256[] memory claimIds = registry.getAuditRequestClaimIds(requestId);
        assertEq(claimIds.length, 1);
        assertEq(claimIds[0], claimId);
    }

    function testSubmitAuditRequestClaimRejectsDuplicateCanonicalIdentity() public {
        uint256 requestId = _createDefaultAuditRequest();

        vm.prank(auditor);
        registry.submitAuditRequestClaim{value: STAKE}(
            requestId,
            address(identityRegistry),
            1,
            keccak256("report-1"),
            keccak256("metadata-1"),
            3,
            2
        );

        vm.prank(auditor);
        vm.expectRevert(ProofOfAudit.DuplicateRequestClaim.selector);
        registry.submitAuditRequestClaim{value: STAKE}(
            requestId,
            address(identityRegistry),
            1,
            keccak256("report-2"),
            keccak256("metadata-2"),
            2,
            1
        );
    }

    function testSubmitAuditRequestClaimRejectsStakeBelowMinimum() public {
        ProofOfAudit.EligibilityConfig memory eligibility = _defaultEligibility();
        eligibility.minimumStakeAmount = uint96(2 * STAKE);

        vm.prank(auditor);
        uint256 requestId = registry.createAuditRequest{value: BOUNTY}(
            target,
            uint96(BOUNTY),
            uint64(WINDOW),
            eligibility,
            new address[](0)
        );

        vm.prank(auditor);
        vm.expectRevert(ProofOfAudit.InsufficientRequestClaimStake.selector);
        registry.submitAuditRequestClaim{value: STAKE}(
            requestId,
            address(identityRegistry),
            1,
            keccak256("report"),
            keccak256("metadata"),
            3,
            2
        );
    }

    function testSubmitAuditRequestClaimRejectsAfterWindowClosed() public {
        uint256 requestId = _createDefaultAuditRequest();

        vm.warp(block.timestamp + WINDOW + 1);

        vm.prank(auditor);
        vm.expectRevert(ProofOfAudit.RequestClaimWindowClosed.selector);
        registry.submitAuditRequestClaim{value: STAKE}(
            requestId,
            address(identityRegistry),
            1,
            keccak256("report"),
            keccak256("metadata"),
            3,
            2
        );
    }

    function testSubmitAuditRequestClaimRequiresIdentityOwner() public {
        uint256 requestId = _createDefaultAuditRequest();

        vm.prank(challenger);
        vm.expectRevert(ProofOfAudit.IdentityOwnerMismatch.selector);
        registry.submitAuditRequestClaim{value: STAKE}(
            requestId,
            address(identityRegistry),
            1,
            keccak256("report"),
            keccak256("metadata"),
            3,
            2
        );
    }

    function testSubmitAuditRequestClaimRejectsAuditorOutsideAllowlist() public {
        ProofOfAudit.EligibilityConfig memory eligibility = _defaultEligibility();
        eligibility.allowlistEnabled = true;
        address[] memory allowlistedAuditors = new address[](1);
        allowlistedAuditors[0] = auditor;

        vm.prank(auditor);
        uint256 requestId = registry.createAuditRequest{value: BOUNTY}(
            target,
            uint96(BOUNTY),
            uint64(WINDOW),
            eligibility,
            allowlistedAuditors
        );

        vm.prank(secondAuditor);
        vm.expectRevert(ProofOfAudit.RequestClaimNotAllowlisted.selector);
        registry.submitAuditRequestClaim{value: STAKE}(
            requestId,
            address(identityRegistry),
            2,
            keccak256("report"),
            keccak256("metadata"),
            2,
            1
        );
    }

    function testSubmitAuditRequestClaimRejectsWrongRequiredIdentity() public {
        ProofOfAudit.EligibilityConfig memory eligibility = _defaultEligibility();
        eligibility.identityRegistry = address(identityRegistry);
        eligibility.requiredAgentId = 1;

        vm.prank(auditor);
        uint256 requestId = registry.createAuditRequest{value: BOUNTY}(
            target,
            uint96(BOUNTY),
            uint64(WINDOW),
            eligibility,
            new address[](0)
        );

        vm.prank(secondAuditor);
        vm.expectRevert(ProofOfAudit.RequestClaimAgentIdMismatch.selector);
        registry.submitAuditRequestClaim{value: STAKE}(
            requestId,
            address(identityRegistry),
            2,
            keccak256("report"),
            keccak256("metadata"),
            2,
            1
        );
    }

    function testCreateAuditRequestStoresAllowlistedAuditors() public {
        ProofOfAudit.EligibilityConfig memory eligibility = _defaultEligibility();
        eligibility.allowlistEnabled = true;
        address[] memory allowlistedAuditors = new address[](2);
        allowlistedAuditors[0] = auditor;
        allowlistedAuditors[1] = secondAuditor;

        vm.prank(auditor);
        uint256 requestId = registry.createAuditRequest{value: BOUNTY}(
            target,
            uint96(BOUNTY),
            uint64(WINDOW),
            eligibility,
            allowlistedAuditors
        );

        address[] memory stored = registry.getAuditRequestAllowlistedAuditors(requestId);
        assertEq(stored.length, 2);
        assertEq(stored[0], auditor);
        assertEq(stored[1], secondAuditor);
        assertTrue(registry.isAuditRequestAuditorAllowlisted(requestId, auditor));
        assertTrue(registry.isAuditRequestAuditorAllowlisted(requestId, secondAuditor));
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

    function _createDefaultAuditRequest() internal returns (uint256 requestId) {
        vm.prank(auditor);
        requestId = registry.createAuditRequest{value: BOUNTY}(
            target,
            uint96(BOUNTY),
            uint64(WINDOW),
            _defaultEligibility(),
            new address[](0)
        );
    }

    function _defaultEligibility()
        internal
        pure
        returns (ProofOfAudit.EligibilityConfig memory eligibility)
    {
        eligibility = ProofOfAudit.EligibilityConfig({
            minimumStakeAmount: uint96(STAKE),
            allowlistEnabled: false,
            identityRegistry: address(0),
            requiredAgentId: 0
        });
    }
}
