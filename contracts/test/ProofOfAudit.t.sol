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

contract RevertingReceiver {
    receive() external payable {
        revert("RevertingReceiver: rejected");
    }
}

/// @dev A recipient that rejects plain ETH transfers but can still initiate
///      calls to the escrow (publish, challenge, submit, withdraw) via `exec`.
///      Used to drive pull-based payout paths where the reverting party must
///      trigger its own withdrawal.
contract RevertingCaller {
    function exec(
        address callTarget,
        uint256 value,
        bytes calldata data
    ) external returns (bytes memory ret) {
        bool ok;
        (ok, ret) = callTarget.call{value: value}(data);
        if (!ok) {
            assembly {
                revert(add(ret, 0x20), mload(ret))
            }
        }
    }

    receive() external payable {
        revert("RevertingCaller: rejected");
    }
}

contract ProofOfAuditTest is Test {
    ProofOfAudit internal registry;
    MockIdentityRegistry internal identityRegistry;

    address internal arbiter = address(0xA11CE);
    address internal treasury = address(0xFEE);
    address internal auditor = address(0xB0B);
    address internal challenger = address(0xCA11);
    address internal secondAuditor = address(0xC0DE);
    address internal target = address(0xD00D);

    uint256 internal constant STAKE = 0.01 ether;
    uint256 internal constant BOND = 0.005 ether;
    uint256 internal constant WINDOW = 1 days;
    uint256 internal constant RESOLUTION_WINDOW = 2 days;
    uint256 internal constant BOUNTY = 0.2 ether;
    uint256 internal constant FEE_BPS = 500;
    uint256 internal constant RESOLUTION_FEE_BPS = 1000;

    function setUp() public {
        registry = new ProofOfAudit(arbiter, treasury, STAKE, BOND, WINDOW, RESOLUTION_WINDOW, 0, 0);
        identityRegistry = new MockIdentityRegistry();
        identityRegistry.setOwner(1, auditor);
        identityRegistry.setOwner(2, secondAuditor);
        vm.deal(auditor, 1 ether);
        vm.deal(challenger, 1 ether);
        vm.deal(secondAuditor, 1 ether);
        vm.deal(treasury, 1 ether);
    }

    function testConstructorRejectsZeroArbiter() public {
        vm.expectRevert(ProofOfAudit.InvalidArbiter.selector);
        new ProofOfAudit(address(0), treasury, STAKE, BOND, WINDOW, RESOLUTION_WINDOW, 0, 0);
    }

    function testConstructorRejectsZeroStake() public {
        vm.expectRevert(ProofOfAudit.InvalidRequiredStake.selector);
        new ProofOfAudit(arbiter, treasury, 0, BOND, WINDOW, RESOLUTION_WINDOW, 0, 0);
    }

    function testConstructorRejectsZeroChallengeBond() public {
        vm.expectRevert(ProofOfAudit.InvalidRequiredChallengeBond.selector);
        new ProofOfAudit(arbiter, treasury, STAKE, 0, WINDOW, RESOLUTION_WINDOW, 0, 0);
    }

    function testConstructorRejectsZeroChallengeWindow() public {
        vm.expectRevert(ProofOfAudit.InvalidChallengeWindow.selector);
        new ProofOfAudit(arbiter, treasury, STAKE, BOND, 0, RESOLUTION_WINDOW, 0, 0);
    }

    function testConstructorRejectsZeroChallengeResolutionWindow() public {
        vm.expectRevert(ProofOfAudit.InvalidChallengeResolutionWindow.selector);
        new ProofOfAudit(arbiter, treasury, STAKE, BOND, WINDOW, 0, 0, 0);
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

    function testChallengeAuditRejectsSelfChallenge() public {
        uint256 auditId = _publishDefaultAudit();

        vm.prank(auditor);
        vm.expectRevert(ProofOfAudit.SelfChallengeNotAllowed.selector);
        registry.challengeAudit{value: BOND}(auditId, keccak256("poc"));
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
        assertEq(uint256(claim.challengeBond), 0);
        assertEq(uint256(claim.resolution), uint256(ProofOfAudit.Resolution.None));
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

    function testEligibleAgentCanChallengeAuditRequestClaimAndSlashIt() public {
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

        uint256 challengerBalanceBefore = secondAuditor.balance;
        bytes32 evidenceHash = keccak256("claim-poc");

        vm.prank(secondAuditor);
        registry.challengeAuditRequestClaim{value: BOND}(
            claimId,
            address(identityRegistry),
            2,
            evidenceHash
        );

        ProofOfAudit.AuditRequestClaim memory challengedClaim = registry
            .getAuditRequestClaim(claimId);
        assertEq(
            uint256(challengedClaim.state),
            uint256(ProofOfAudit.AuditRequestClaimState.Challenged)
        );
        assertEq(challengedClaim.challenger, secondAuditor);
        assertEq(challengedClaim.evidenceHash, evidenceHash);
        assertEq(uint256(challengedClaim.challengeBond), BOND);

        vm.prank(arbiter);
        registry.resolveAuditRequestClaimChallenge(claimId, true);

        ProofOfAudit.AuditRequestClaim memory slashedClaim = registry
            .getAuditRequestClaim(claimId);
        assertEq(
            uint256(slashedClaim.state),
            uint256(ProofOfAudit.AuditRequestClaimState.Slashed)
        );
        assertEq(
            uint256(slashedClaim.resolution),
            uint256(ProofOfAudit.Resolution.ChallengeUpheld)
        );
        assertEq(secondAuditor.balance, challengerBalanceBefore + STAKE);
    }

    function testRejectedAuditRequestClaimChallengeOnlyTransfersBond() public {
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

        uint256 auditorBalanceBeforeChallenge = auditor.balance;

        vm.prank(secondAuditor);
        registry.challengeAuditRequestClaim{value: BOND}(
            claimId,
            address(identityRegistry),
            2,
            keccak256("weak-claim-poc")
        );

        vm.prank(arbiter);
        registry.resolveAuditRequestClaimChallenge(claimId, false);

        ProofOfAudit.AuditRequestClaim memory resolvedClaim = registry
            .getAuditRequestClaim(claimId);
        assertEq(
            uint256(resolvedClaim.state),
            uint256(ProofOfAudit.AuditRequestClaimState.Resolved)
        );
        assertEq(
            uint256(resolvedClaim.resolution),
            uint256(ProofOfAudit.Resolution.ChallengeRejected)
        );
        assertEq(auditor.balance, auditorBalanceBeforeChallenge + BOND);
    }

    function testAuditRequestClaimChallengeRejectsSelfChallenge() public {
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

        vm.prank(auditor);
        vm.expectRevert(ProofOfAudit.RequestClaimSelfChallengeNotAllowed.selector);
        registry.challengeAuditRequestClaim{value: BOND}(
            claimId,
            address(identityRegistry),
            1,
            keccak256("self-poc")
        );
    }

    function testFinalizeAuditRequestSettlementForSingleEligibleClaim() public {
        uint256 requestId = _createAuditRequestFor(challenger);

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

        vm.warp(block.timestamp + WINDOW + 1);
        registry.classifyAuditRequestClaims(requestId, 1);
        registry.finalizeAuditRequestSettlement(requestId);

        ProofOfAudit.AuditRequestSettlement memory settlement = registry
            .getAuditRequestSettlement(requestId);
        assertTrue(settlement.finalized);
        assertEq(uint256(settlement.classifiedClaimCount), 1);
        assertEq(uint256(settlement.eligibleClaimCount), 1);
        assertEq(uint256(settlement.eligibleStakeTotal), STAKE);
        assertEq(uint256(settlement.distributableBountyAmount), BOUNTY);

        uint256 auditorBalanceBefore = auditor.balance;
        registry.withdrawAuditRequestClaimSettlement(claimId);

        assertEq(auditor.balance, auditorBalanceBefore + STAKE + BOUNTY);

        (bool refundAvailable, uint256 refundAmount) = registry.previewAuditRequestRefund(
            requestId
        );
        assertTrue(refundAvailable);
        assertEq(refundAmount, 0);
    }

    function testProRataSettlementSplitsBountyByEligibleStakeWeight() public {
        uint256 requestId = _createAuditRequestFor(challenger);

        vm.prank(auditor);
        uint256 firstClaimId = registry.submitAuditRequestClaim{value: STAKE}(
            requestId,
            address(identityRegistry),
            1,
            keccak256("report-1"),
            keccak256("metadata-1"),
            3,
            2
        );

        vm.prank(secondAuditor);
        uint256 secondClaimId = registry.submitAuditRequestClaim{value: 2 * STAKE}(
            requestId,
            address(identityRegistry),
            2,
            keccak256("report-2"),
            keccak256("metadata-2"),
            2,
            1
        );

        vm.warp(block.timestamp + WINDOW + 1);
        registry.classifyAuditRequestClaims(requestId, 1);
        registry.classifyAuditRequestClaims(requestId, 1);
        registry.finalizeAuditRequestSettlement(requestId);

        uint256 firstShare = BOUNTY / 3;
        uint256 secondShare = (BOUNTY * 2) / 3;
        uint256 requesterDust = BOUNTY - firstShare - secondShare;

        uint256 firstAuditorBalanceBefore = auditor.balance;
        uint256 secondAuditorBalanceBefore = secondAuditor.balance;
        uint256 requesterBalanceBefore = challenger.balance;

        registry.withdrawAuditRequestClaimSettlement(firstClaimId);
        registry.withdrawAuditRequestClaimSettlement(secondClaimId);

        vm.prank(challenger);
        registry.withdrawAuditRequestRefund(requestId);

        assertEq(auditor.balance, firstAuditorBalanceBefore + STAKE + firstShare);
        assertEq(
            secondAuditor.balance,
            secondAuditorBalanceBefore + (2 * STAKE) + secondShare
        );
        assertEq(challenger.balance, requesterBalanceBefore + requesterDust);
    }

    function testSlashedClaimsAreExcludedAndRequesterReceivesRefund() public {
        uint256 requestId = _createAuditRequestFor(challenger);

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

        vm.prank(secondAuditor);
        registry.challengeAuditRequestClaim{value: BOND}(
            claimId,
            address(identityRegistry),
            2,
            keccak256("claim-poc")
        );

        vm.prank(arbiter);
        registry.resolveAuditRequestClaimChallenge(claimId, true);

        vm.warp(block.timestamp + WINDOW + 1);
        registry.classifyAuditRequestClaims(requestId, 1);
        registry.finalizeAuditRequestSettlement(requestId);

        vm.expectRevert(ProofOfAudit.RequestClaimNotEligible.selector);
        registry.withdrawAuditRequestClaimSettlement(claimId);

        uint256 requesterBalanceBefore = challenger.balance;
        vm.prank(challenger);
        registry.withdrawAuditRequestRefund(requestId);

        assertEq(challenger.balance, requesterBalanceBefore + BOUNTY);
    }

    function testCannotClassifyRequestSettlementWhileClaimChallengeWindowIsStillOpen() public {
        vm.prank(challenger);
        uint256 requestId = registry.createAuditRequest{value: BOUNTY}(
            target,
            uint96(BOUNTY),
            uint64(1 hours),
            _defaultEligibility(),
            new address[](0)
        );

        vm.prank(auditor);
        registry.submitAuditRequestClaim{value: STAKE}(
            requestId,
            address(identityRegistry),
            1,
            keccak256("report"),
            keccak256("metadata"),
            3,
            2
        );

        vm.warp(block.timestamp + 1 hours + 1);

        vm.expectRevert(ProofOfAudit.RequestSettlementPending.selector);
        registry.classifyAuditRequestClaims(requestId, 1);
    }

    function testProtocolFeeIsDeductedFromBountyDistributionAndWithdrawable() public {
        ProofOfAudit feeRegistry = _newFeeRegistry(FEE_BPS, 0);
        uint256 requestId = _createAuditRequestForWithRegistry(feeRegistry, challenger);

        vm.prank(auditor);
        uint256 claimId = feeRegistry.submitAuditRequestClaim{value: STAKE}(
            requestId,
            address(identityRegistry),
            1,
            keccak256("report"),
            keccak256("metadata"),
            3,
            2
        );

        vm.warp(block.timestamp + WINDOW + 1);
        feeRegistry.classifyAuditRequestClaims(requestId, 1);
        feeRegistry.finalizeAuditRequestSettlement(requestId);

        ProofOfAudit.AuditRequestSettlement memory settlement = feeRegistry
            .getAuditRequestSettlement(requestId);
        uint256 expectedProtocolFee = (BOUNTY * FEE_BPS) / feeRegistry.FEE_DENOMINATOR();
        assertEq(uint256(settlement.protocolFeeAmount), expectedProtocolFee);
        assertEq(
            uint256(settlement.distributableBountyAmount),
            BOUNTY - expectedProtocolFee
        );
        assertEq(feeRegistry.accruedProtocolFees(), expectedProtocolFee);

        uint256 auditorBalanceBefore = auditor.balance;
        feeRegistry.withdrawAuditRequestClaimSettlement(claimId);
        assertEq(
            auditor.balance,
            auditorBalanceBefore + STAKE + (BOUNTY - expectedProtocolFee)
        );

        uint256 treasuryBalanceBefore = treasury.balance;
        vm.prank(treasury);
        feeRegistry.withdrawFees();
        assertEq(treasury.balance, treasuryBalanceBefore + expectedProtocolFee);
        assertEq(feeRegistry.accruedProtocolFees(), 0);
    }

    function testResolutionFeeIsDeductedFromRequestClaimChallengePayout() public {
        ProofOfAudit feeRegistry = _newFeeRegistry(0, RESOLUTION_FEE_BPS);
        uint256 requestId = _createAuditRequestForWithRegistry(feeRegistry, challenger);

        vm.prank(auditor);
        uint256 claimId = feeRegistry.submitAuditRequestClaim{value: STAKE}(
            requestId,
            address(identityRegistry),
            1,
            keccak256("report"),
            keccak256("metadata"),
            3,
            2
        );

        vm.prank(secondAuditor);
        feeRegistry.challengeAuditRequestClaim{value: BOND}(
            claimId,
            address(identityRegistry),
            2,
            keccak256("claim-poc")
        );

        uint256 challengerBalanceBefore = secondAuditor.balance;
        vm.prank(arbiter);
        feeRegistry.resolveAuditRequestClaimChallenge(claimId, true);

        uint256 grossPayout = STAKE + BOND;
        uint256 expectedResolutionFee =
            (grossPayout * RESOLUTION_FEE_BPS) / feeRegistry.FEE_DENOMINATOR();
        assertEq(
            secondAuditor.balance,
            challengerBalanceBefore + grossPayout - expectedResolutionFee
        );
        assertEq(feeRegistry.accruedResolutionFees(), expectedResolutionFee);

        uint256 treasuryBalanceBefore = treasury.balance;
        vm.prank(treasury);
        feeRegistry.withdrawFees();
        assertEq(treasury.balance, treasuryBalanceBefore + expectedResolutionFee);
        assertEq(feeRegistry.accruedResolutionFees(), 0);
    }

    function testZeroEligibleRefundDoesNotAccrueProtocolFee() public {
        ProofOfAudit feeRegistry = _newFeeRegistry(FEE_BPS, 0);
        uint256 requestId = _createAuditRequestForWithRegistry(feeRegistry, challenger);

        vm.prank(auditor);
        uint256 claimId = feeRegistry.submitAuditRequestClaim{value: STAKE}(
            requestId,
            address(identityRegistry),
            1,
            keccak256("report"),
            keccak256("metadata"),
            3,
            2
        );

        vm.prank(secondAuditor);
        feeRegistry.challengeAuditRequestClaim{value: BOND}(
            claimId,
            address(identityRegistry),
            2,
            keccak256("claim-poc")
        );

        vm.prank(arbiter);
        feeRegistry.resolveAuditRequestClaimChallenge(claimId, true);

        vm.warp(block.timestamp + WINDOW + 1);
        feeRegistry.classifyAuditRequestClaims(requestId, 1);
        feeRegistry.finalizeAuditRequestSettlement(requestId);

        ProofOfAudit.AuditRequestSettlement memory settlement = feeRegistry
            .getAuditRequestSettlement(requestId);
        assertEq(uint256(settlement.protocolFeeAmount), 0);
        assertEq(feeRegistry.accruedProtocolFees(), 0);

        uint256 requesterBalanceBefore = challenger.balance;
        vm.prank(challenger);
        feeRegistry.withdrawAuditRequestRefund(requestId);
        assertEq(challenger.balance, requesterBalanceBefore + BOUNTY);
    }

    function testExpireAuditRequestClaimChallengeUnfreezesSettlement() public {
        uint256 requestId = _createAuditRequestFor(challenger);

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

        vm.prank(secondAuditor);
        registry.challengeAuditRequestClaim{value: BOND}(
            claimId,
            address(identityRegistry),
            2,
            keccak256("stuck-poc")
        );

        // Arbiter never resolves. Warp past both the claim challenge window and
        // the challenge resolution window so the challenge can be expired and
        // the claim can settle.
        vm.warp(block.timestamp + RESOLUTION_WINDOW + 1);

        registry.expireAuditRequestClaimChallenge(claimId);

        ProofOfAudit.AuditRequestClaim memory unwound = registry
            .getAuditRequestClaim(claimId);
        assertEq(
            uint256(unwound.state),
            uint256(ProofOfAudit.AuditRequestClaimState.Submitted)
        );
        assertEq(unwound.challenger, address(0));
        assertEq(uint256(unwound.challengeBond), 0);
        assertEq(uint256(unwound.challengedAt), 0);
        assertEq(unwound.evidenceHash, bytes32(0));

        registry.classifyAuditRequestClaims(requestId, 1);
        registry.finalizeAuditRequestSettlement(requestId);

        ProofOfAudit.AuditRequestSettlement memory settlement = registry
            .getAuditRequestSettlement(requestId);
        assertTrue(settlement.finalized);
        assertEq(uint256(settlement.eligibleClaimCount), 1);
        assertEq(uint256(settlement.eligibleStakeTotal), STAKE);
        assertEq(uint256(settlement.distributableBountyAmount), BOUNTY);

        uint256 auditorBalanceBefore = auditor.balance;
        registry.withdrawAuditRequestClaimSettlement(claimId);
        assertEq(auditor.balance, auditorBalanceBefore + STAKE + BOUNTY);
    }

    function testExpireChallengeRevertsWhileResolutionWindowOpen() public {
        uint256 requestId = _createAuditRequestFor(challenger);

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

        vm.prank(secondAuditor);
        registry.challengeAuditRequestClaim{value: BOND}(
            claimId,
            address(identityRegistry),
            2,
            keccak256("stuck-poc")
        );

        // Past the challenge window but still inside the resolution window.
        vm.warp(block.timestamp + WINDOW + 1);

        vm.expectRevert(ProofOfAudit.ChallengeResolutionWindowOpen.selector);
        registry.expireAuditRequestClaimChallenge(claimId);
    }

    function testExpiredChallengeBondIsWithdrawableByChallenger() public {
        uint256 requestId = _createAuditRequestFor(challenger);

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

        vm.prank(secondAuditor);
        registry.challengeAuditRequestClaim{value: BOND}(
            claimId,
            address(identityRegistry),
            2,
            keccak256("stuck-poc")
        );

        vm.warp(block.timestamp + RESOLUTION_WINDOW + 1);
        registry.expireAuditRequestClaimChallenge(claimId);

        assertEq(registry.expiredChallengeBondRefunds(secondAuditor), BOND);

        uint256 challengerBalanceBefore = secondAuditor.balance;
        vm.prank(secondAuditor);
        registry.withdrawExpiredChallengeBond();
        assertEq(secondAuditor.balance, challengerBalanceBefore + BOND);
        assertEq(registry.expiredChallengeBondRefunds(secondAuditor), 0);

        vm.prank(secondAuditor);
        vm.expectRevert(ProofOfAudit.NoExpiredChallengeBond.selector);
        registry.withdrawExpiredChallengeBond();
    }

    function testResolveRevertsAfterChallengeExpired() public {
        uint256 requestId = _createAuditRequestFor(challenger);

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

        vm.prank(secondAuditor);
        registry.challengeAuditRequestClaim{value: BOND}(
            claimId,
            address(identityRegistry),
            2,
            keccak256("stuck-poc")
        );

        vm.warp(block.timestamp + RESOLUTION_WINDOW + 1);
        registry.expireAuditRequestClaimChallenge(claimId);

        vm.prank(arbiter);
        vm.expectRevert(ProofOfAudit.InvalidState.selector);
        registry.resolveAuditRequestClaimChallenge(claimId, true);
    }

    function testExpireRevertsAfterResolve() public {
        uint256 requestId = _createAuditRequestFor(challenger);

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

        vm.prank(secondAuditor);
        registry.challengeAuditRequestClaim{value: BOND}(
            claimId,
            address(identityRegistry),
            2,
            keccak256("stuck-poc")
        );

        vm.prank(arbiter);
        registry.resolveAuditRequestClaimChallenge(claimId, false);

        vm.warp(block.timestamp + RESOLUTION_WINDOW + 1);
        vm.expectRevert(ProofOfAudit.InvalidState.selector);
        registry.expireAuditRequestClaimChallenge(claimId);
    }

    function testExpiryWithRevertingChallengerReceiverStillUnfreezes() public {
        RevertingReceiver revertingChallenger = new RevertingReceiver();
        identityRegistry.setOwner(3, address(revertingChallenger));
        vm.deal(address(revertingChallenger), 1 ether);

        uint256 requestId = _createAuditRequestFor(challenger);

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

        vm.prank(address(revertingChallenger));
        registry.challengeAuditRequestClaim{value: BOND}(
            claimId,
            address(identityRegistry),
            3,
            keccak256("stuck-poc")
        );

        vm.warp(block.timestamp + RESOLUTION_WINDOW + 1);

        // Expiry must succeed even though the challenger receiver reverts on
        // ETH receipt, because the bond is credited to a pull-refund balance.
        registry.expireAuditRequestClaimChallenge(claimId);
        assertEq(
            registry.expiredChallengeBondRefunds(address(revertingChallenger)),
            BOND
        );

        registry.classifyAuditRequestClaims(requestId, 1);
        registry.finalizeAuditRequestSettlement(requestId);

        uint256 auditorBalanceBefore = auditor.balance;
        registry.withdrawAuditRequestClaimSettlement(claimId);
        assertEq(auditor.balance, auditorBalanceBefore + STAKE + BOUNTY);

        // The reverting challenger cannot pull its bond because its receive()
        // reverts, but that no longer blocks anyone else.
        vm.prank(address(revertingChallenger));
        vm.expectRevert(ProofOfAudit.TransferFailed.selector);
        registry.withdrawExpiredChallengeBond();
    }

    // ---------------------------------------------------------------------
    // Malicious-recipient coverage for every _sendValue payout path.
    // ---------------------------------------------------------------------

    // _sendValue @ resolveChallenge (direct flow): payout to the challenger.
    function testResolveChallengeRevertsWhenRecipientRejectsPayout() public {
        RevertingCaller badChallenger = new RevertingCaller();
        vm.deal(address(badChallenger), 1 ether);

        uint256 auditId = _publishDefaultAudit();
        badChallenger.exec(
            address(registry),
            BOND,
            abi.encodeCall(registry.challengeAudit, (auditId, keccak256("poc")))
        );

        vm.prank(arbiter);
        vm.expectRevert(ProofOfAudit.TransferFailed.selector);
        registry.resolveChallenge(auditId, true);
    }

    // _sendValue @ resolveAuditRequestClaimChallenge: payout to the challenger.
    function testResolveAuditRequestClaimChallengeRevertsWhenRecipientRejectsPayout()
        public
    {
        RevertingCaller badChallenger = new RevertingCaller();
        vm.deal(address(badChallenger), 1 ether);
        identityRegistry.setOwner(3, address(badChallenger));

        uint256 requestId = _createAuditRequestFor(challenger);

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

        badChallenger.exec(
            address(registry),
            BOND,
            abi.encodeCall(
                registry.challengeAuditRequestClaim,
                (claimId, address(identityRegistry), 3, keccak256("poc"))
            )
        );

        vm.prank(arbiter);
        vm.expectRevert(ProofOfAudit.TransferFailed.selector);
        registry.resolveAuditRequestClaimChallenge(claimId, true);
    }

    // _sendValue @ releaseStake: payout to the auditor.
    function testReleaseStakeRevertsWhenRecipientRejectsPayout() public {
        RevertingCaller badAuditor = new RevertingCaller();
        vm.deal(address(badAuditor), 1 ether);

        bytes memory ret = badAuditor.exec(
            address(registry),
            STAKE,
            abi.encodeCall(
                registry.publishAudit,
                (target, keccak256("report"), keccak256("metadata"), 3, 2)
            )
        );
        uint256 auditId = abi.decode(ret, (uint256));

        vm.warp(block.timestamp + WINDOW + 1);
        vm.expectRevert(ProofOfAudit.TransferFailed.selector);
        registry.releaseStake(auditId);
    }

    // _sendValue @ refundExpiredAuditRequest: refund to the requester.
    function testRefundExpiredAuditRequestRevertsWhenRecipientRejectsPayout()
        public
    {
        RevertingCaller badRequester = new RevertingCaller();
        vm.deal(address(badRequester), 1 ether);

        bytes memory ret = badRequester.exec(
            address(registry),
            BOUNTY,
            abi.encodeCall(
                registry.createAuditRequest,
                (
                    target,
                    uint96(BOUNTY),
                    uint64(WINDOW),
                    _defaultEligibility(),
                    new address[](0)
                )
            )
        );
        uint256 requestId = abi.decode(ret, (uint256));

        vm.warp(block.timestamp + WINDOW + 1);
        registry.expireAuditRequest(requestId);

        vm.expectRevert(ProofOfAudit.TransferFailed.selector);
        badRequester.exec(
            address(registry),
            0,
            abi.encodeCall(registry.refundExpiredAuditRequest, (requestId))
        );
    }

    // _sendValue @ withdrawExpiredChallengeBond is already covered by
    // testExpiryWithRevertingChallengerReceiverStillUnfreezes.

    // _sendValue @ withdrawAuditRequestClaimSettlement: payout to the auditor.
    function testWithdrawAuditRequestClaimSettlementRevertsWhenRecipientRejectsPayout()
        public
    {
        RevertingCaller badAuditor = new RevertingCaller();
        vm.deal(address(badAuditor), 1 ether);
        identityRegistry.setOwner(3, address(badAuditor));

        uint256 requestId = _createAuditRequestFor(challenger);

        bytes memory ret = badAuditor.exec(
            address(registry),
            STAKE,
            abi.encodeCall(
                registry.submitAuditRequestClaim,
                (
                    requestId,
                    address(identityRegistry),
                    3,
                    keccak256("report"),
                    keccak256("metadata"),
                    3,
                    2
                )
            )
        );
        uint256 claimId = abi.decode(ret, (uint256));

        vm.warp(block.timestamp + WINDOW + 1);
        registry.classifyAuditRequestClaims(requestId, 1);
        registry.finalizeAuditRequestSettlement(requestId);

        vm.expectRevert(ProofOfAudit.TransferFailed.selector);
        registry.withdrawAuditRequestClaimSettlement(claimId);
    }

    // _sendValue @ withdrawAuditRequestRefund: refund to the requester.
    function testWithdrawAuditRequestRefundRevertsWhenRecipientRejectsPayout()
        public
    {
        RevertingCaller badRequester = new RevertingCaller();
        vm.deal(address(badRequester), 1 ether);

        bytes memory ret = badRequester.exec(
            address(registry),
            BOUNTY,
            abi.encodeCall(
                registry.createAuditRequest,
                (
                    target,
                    uint96(BOUNTY),
                    uint64(WINDOW),
                    _defaultEligibility(),
                    new address[](0)
                )
            )
        );
        uint256 requestId = abi.decode(ret, (uint256));

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

        // Slash the only claim so no auditor is eligible and the full bounty is
        // refundable to the requester.
        vm.prank(secondAuditor);
        registry.challengeAuditRequestClaim{value: BOND}(
            claimId,
            address(identityRegistry),
            2,
            keccak256("claim-poc")
        );
        vm.prank(arbiter);
        registry.resolveAuditRequestClaimChallenge(claimId, true);

        vm.warp(block.timestamp + WINDOW + 1);
        registry.classifyAuditRequestClaims(requestId, 1);
        registry.finalizeAuditRequestSettlement(requestId);

        vm.expectRevert(ProofOfAudit.TransferFailed.selector);
        badRequester.exec(
            address(registry),
            0,
            abi.encodeCall(registry.withdrawAuditRequestRefund, (requestId))
        );
    }

    // _sendValue @ withdrawFees: payout to the treasury.
    function testWithdrawFeesRevertsWhenRecipientRejectsPayout() public {
        RevertingCaller badTreasury = new RevertingCaller();
        ProofOfAudit feeRegistry = new ProofOfAudit(
            arbiter,
            address(badTreasury),
            STAKE,
            BOND,
            WINDOW,
            RESOLUTION_WINDOW,
            FEE_BPS,
            0
        );

        uint256 requestId = _createAuditRequestForWithRegistry(feeRegistry, challenger);

        vm.prank(auditor);
        feeRegistry.submitAuditRequestClaim{value: STAKE}(
            requestId,
            address(identityRegistry),
            1,
            keccak256("report"),
            keccak256("metadata"),
            3,
            2
        );

        vm.warp(block.timestamp + WINDOW + 1);
        feeRegistry.classifyAuditRequestClaims(requestId, 1);
        feeRegistry.finalizeAuditRequestSettlement(requestId);
        assertGt(feeRegistry.accruedProtocolFees(), 0);

        vm.prank(address(badTreasury));
        vm.expectRevert(ProofOfAudit.TransferFailed.selector);
        feeRegistry.withdrawFees();
    }

    // ---------------------------------------------------------------------
    // Targeted fuzz tests.
    // ---------------------------------------------------------------------

    function testFuzz_publishRejectsWrongStake(uint256 value) public {
        value = bound(value, 0, 1 ether);
        if (value == STAKE) {
            value = STAKE + 1;
        }
        vm.deal(auditor, value);

        vm.prank(auditor);
        vm.expectRevert(ProofOfAudit.IncorrectStake.selector);
        registry.publishAudit{value: value}(
            target,
            keccak256("report"),
            keccak256("metadata"),
            3,
            2
        );
    }

    function testFuzz_challengeWindowBoundary(uint64 delta) public {
        uint256 auditId = _publishDefaultAudit();
        uint256 publishedAt = block.timestamp;
        uint256 offset = bound(delta, 0, 2 * WINDOW);
        vm.warp(publishedAt + offset);

        vm.prank(challenger);
        if (offset <= WINDOW) {
            // At or before publishedAt + challengeWindow the challenge is valid.
            registry.challengeAudit{value: BOND}(auditId, keccak256("poc"));
            ProofOfAudit.AuditRecord memory audit = registry.getAudit(auditId);
            assertEq(
                uint256(audit.state),
                uint256(ProofOfAudit.AuditState.Challenged)
            );
        } else {
            vm.expectRevert(ProofOfAudit.ChallengeWindowClosed.selector);
            registry.challengeAudit{value: BOND}(auditId, keccak256("poc"));
        }
    }

    function testFuzz_proRataSharesNeverExceedBounty(
        uint96 stakeA,
        uint96 stakeB
    ) public {
        ProofOfAudit feeRegistry = _newFeeRegistry(FEE_BPS, 0);

        uint256 sA = bound(stakeA, STAKE, 1 ether);
        uint256 sB = bound(stakeB, STAKE, 1 ether);
        if (sB == sA) {
            sB = sA == 1 ether ? sA - 1 : sA + 1;
        }
        vm.deal(auditor, 2 ether);
        vm.deal(secondAuditor, 2 ether);

        vm.prank(challenger);
        uint256 requestId = feeRegistry.createAuditRequest{value: BOUNTY}(
            target,
            uint96(BOUNTY),
            uint64(WINDOW),
            _defaultEligibility(),
            new address[](0)
        );

        vm.prank(auditor);
        uint256 firstClaimId = feeRegistry.submitAuditRequestClaim{value: sA}(
            requestId,
            address(identityRegistry),
            1,
            keccak256("report-1"),
            keccak256("metadata-1"),
            3,
            2
        );

        vm.prank(secondAuditor);
        uint256 secondClaimId = feeRegistry.submitAuditRequestClaim{value: sB}(
            requestId,
            address(identityRegistry),
            2,
            keccak256("report-2"),
            keccak256("metadata-2"),
            2,
            1
        );

        vm.warp(block.timestamp + WINDOW + 1);
        feeRegistry.classifyAuditRequestClaims(requestId, 2);
        feeRegistry.finalizeAuditRequestSettlement(requestId);

        ProofOfAudit.AuditRequestSettlement memory settlement = feeRegistry
            .getAuditRequestSettlement(requestId);

        uint256 firstBalanceBefore = auditor.balance;
        uint256 secondBalanceBefore = secondAuditor.balance;
        uint256 requesterBalanceBefore = challenger.balance;

        feeRegistry.withdrawAuditRequestClaimSettlement(firstClaimId);
        feeRegistry.withdrawAuditRequestClaimSettlement(secondClaimId);

        vm.prank(challenger);
        feeRegistry.withdrawAuditRequestRefund(requestId);

        uint256 firstShare = (auditor.balance - firstBalanceBefore) - sA;
        uint256 secondShare = (secondAuditor.balance - secondBalanceBefore) - sB;
        uint256 requesterRefund = challenger.balance - requesterBalanceBefore;

        // The bounty is split exactly: auditor shares + protocol fee + refund.
        assertEq(
            firstShare + secondShare + settlement.protocolFeeAmount + requesterRefund,
            BOUNTY
        );
        // No auditor share may exceed the distributable bounty.
        assertLe(firstShare + secondShare, uint256(settlement.distributableBountyAmount));
    }

    function testFuzz_expiryBoundary(uint64 delta) public {
        uint256 requestId = _createAuditRequestFor(challenger);

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

        vm.prank(secondAuditor);
        registry.challengeAuditRequestClaim{value: BOND}(
            claimId,
            address(identityRegistry),
            2,
            keccak256("stuck-poc")
        );
        uint256 challengedAt = block.timestamp;

        uint256 offset = bound(delta, 0, 2 * RESOLUTION_WINDOW);
        vm.warp(challengedAt + offset);

        if (offset <= RESOLUTION_WINDOW) {
            // At or before challengedAt + resolutionWindow expiry is not allowed.
            vm.expectRevert(ProofOfAudit.ChallengeResolutionWindowOpen.selector);
            registry.expireAuditRequestClaimChallenge(claimId);
        } else {
            registry.expireAuditRequestClaimChallenge(claimId);
            ProofOfAudit.AuditRequestClaim memory claim = registry
                .getAuditRequestClaim(claimId);
            assertEq(
                uint256(claim.state),
                uint256(ProofOfAudit.AuditRequestClaimState.Submitted)
            );
        }
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
        return _createAuditRequestFor(auditor);
    }

    function _createAuditRequestFor(address requester) internal returns (uint256 requestId) {
        return _createAuditRequestForWithRegistry(registry, requester);
    }

    function _createAuditRequestForWithRegistry(
        ProofOfAudit targetRegistry,
        address requester
    ) internal returns (uint256 requestId) {
        vm.prank(requester);
        requestId = targetRegistry.createAuditRequest{value: BOUNTY}(
            target,
            uint96(BOUNTY),
            uint64(WINDOW),
            _defaultEligibility(),
            new address[](0)
        );
    }

    function _newFeeRegistry(
        uint256 protocolFeeBps,
        uint256 resolutionFeeBps
    ) internal returns (ProofOfAudit feeRegistry) {
        feeRegistry = new ProofOfAudit(
            arbiter,
            treasury,
            STAKE,
            BOND,
            WINDOW,
            RESOLUTION_WINDOW,
            protocolFeeBps,
            resolutionFeeBps
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
