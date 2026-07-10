// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {ProofOfAudit} from "../src/ProofOfAudit.sol";

/// @dev Minimal identity registry mirroring the production interface so the
///      handler can register the two auditors and the challenger.
contract InvariantIdentityRegistry {
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

/// @notice Bounded, precondition-tolerant driver over both settlement flows.
/// @dev Every fuzzed input is squeezed through `bound`, and every call whose
///      preconditions the fuzzer may violate is wrapped in try/catch. Ghost
///      accounting is updated ONLY on success paths: deposits from observed
///      `msg.value`, withdrawals from the observed balance delta of the actual
///      recipient (independent of the contract's own balance).
contract InvariantHandler is Test {
    ProofOfAudit public immutable poa;
    InvariantIdentityRegistry internal immutable identityRegistry;

    address internal immutable requester;
    address internal immutable auditorA; // agent 1
    address internal immutable auditorB; // agent 2
    address internal immutable challengerC; // agent 3
    address internal immutable arbiter;
    address internal immutable treasury;
    address internal immutable auditTarget;

    uint256 internal constant STAKE = 0.01 ether;
    uint256 internal constant BOND = 0.005 ether;
    uint256 internal constant WINDOW = 1 days;
    uint256 internal constant RESOLUTION_WINDOW = 2 days;

    // Ghost accounting.
    uint256 public totalDeposited;
    uint256 public totalWithdrawn;

    uint256[] internal auditIds;
    uint256[] internal requestIds;
    uint256[] internal claimIds;

    constructor(
        ProofOfAudit _poa,
        InvariantIdentityRegistry _identityRegistry,
        address _requester,
        address _auditorA,
        address _auditorB,
        address _challengerC,
        address _arbiter,
        address _treasury,
        address _auditTarget
    ) {
        poa = _poa;
        identityRegistry = _identityRegistry;
        requester = _requester;
        auditorA = _auditorA;
        auditorB = _auditorB;
        challengerC = _challengerC;
        arbiter = _arbiter;
        treasury = _treasury;
        auditTarget = _auditTarget;
    }

    function _openEligibility()
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

    // ----- Direct flow -----------------------------------------------------

    function publish(uint256 actorSeed) external {
        address auditor = (actorSeed % 2 == 0) ? auditorA : auditorB;
        vm.prank(auditor);
        try
            poa.publishAudit{value: STAKE}(
                auditTarget,
                keccak256("report"),
                keccak256("metadata"),
                3,
                2
            )
        returns (uint256 auditId) {
            auditIds.push(auditId);
            totalDeposited += STAKE;
        } catch {}
    }

    function challengeDirect(uint256 auditSeed) external {
        if (auditIds.length == 0) return;
        uint256 auditId = auditIds[bound(auditSeed, 0, auditIds.length - 1)];
        // challengerC never publishes, so the self-challenge guard is honored.
        vm.prank(challengerC);
        try poa.challengeAudit{value: BOND}(auditId, keccak256("evidence")) {
            totalDeposited += BOND;
        } catch {}
    }

    function resolveDirect(uint256 auditSeed, bool upheld) external {
        if (auditIds.length == 0) return;
        uint256 auditId = auditIds[bound(auditSeed, 0, auditIds.length - 1)];
        ProofOfAudit.AuditRecord memory audit = poa.getAudit(auditId);
        address recipient = upheld ? audit.challenger : audit.auditor;
        uint256 balBefore = recipient.balance;
        vm.prank(arbiter);
        try poa.resolveChallenge(auditId, upheld) {
            totalWithdrawn += recipient.balance - balBefore;
        } catch {}
    }

    function release(uint256 auditSeed) external {
        if (auditIds.length == 0) return;
        uint256 auditId = auditIds[bound(auditSeed, 0, auditIds.length - 1)];
        address recipient = poa.getAudit(auditId).auditor;
        uint256 balBefore = recipient.balance;
        try poa.releaseStake(auditId) {
            totalWithdrawn += recipient.balance - balBefore;
        } catch {}
    }

    // ----- Request flow ----------------------------------------------------

    function createRequest(uint256 bountySeed, uint256 windowSeed) external {
        uint256 bounty = bound(bountySeed, 0.01 ether, 1 ether);
        uint64 window = uint64(bound(windowSeed, 1, 30 days));
        vm.prank(requester);
        try
            poa.createAuditRequest{value: bounty}(
                auditTarget,
                uint96(bounty),
                window,
                _openEligibility(),
                new address[](0)
            )
        returns (uint256 requestId) {
            requestIds.push(requestId);
            totalDeposited += bounty;
        } catch {}
    }

    function submitClaim(
        uint256 requestSeed,
        uint256 auditorSeed,
        uint256 stakeSeed
    ) external {
        if (requestIds.length == 0) return;
        uint256 requestId = requestIds[bound(requestSeed, 0, requestIds.length - 1)];
        (address auditor, uint256 agentId) = (auditorSeed % 2 == 0)
            ? (auditorA, uint256(1))
            : (auditorB, uint256(2));
        uint256 stake = bound(stakeSeed, STAKE, STAKE * 10);
        vm.prank(auditor);
        try
            poa.submitAuditRequestClaim{value: stake}(
                requestId,
                address(identityRegistry),
                agentId,
                keccak256("report"),
                keccak256("metadata"),
                3,
                2
            )
        returns (uint256 claimId) {
            claimIds.push(claimId);
            totalDeposited += stake;
        } catch {}
    }

    function challengeClaim(uint256 claimSeed) external {
        if (claimIds.length == 0) return;
        uint256 claimId = claimIds[bound(claimSeed, 0, claimIds.length - 1)];
        // challengerC (agent 3) never submits claims, so no self-challenge.
        vm.prank(challengerC);
        try
            poa.challengeAuditRequestClaim{value: BOND}(
                claimId,
                address(identityRegistry),
                3,
                keccak256("evidence")
            )
        {
            totalDeposited += BOND;
        } catch {}
    }

    function resolveClaim(uint256 claimSeed, bool upheld) external {
        if (claimIds.length == 0) return;
        uint256 claimId = claimIds[bound(claimSeed, 0, claimIds.length - 1)];
        ProofOfAudit.AuditRequestClaim memory claim = poa.getAuditRequestClaim(claimId);
        address recipient = upheld ? claim.challenger : claim.auditor;
        uint256 balBefore = recipient.balance;
        vm.prank(arbiter);
        try poa.resolveAuditRequestClaimChallenge(claimId, upheld) {
            totalWithdrawn += recipient.balance - balBefore;
        } catch {}
    }

    function expireClaim(uint256 claimSeed) external {
        if (claimIds.length == 0) return;
        uint256 claimId = claimIds[bound(claimSeed, 0, claimIds.length - 1)];
        // Bond is credited to a pull-refund balance (no external send here).
        try poa.expireAuditRequestClaimChallenge(claimId) {} catch {}
    }

    function withdrawExpiredBond(uint256 actorSeed) external {
        address[4] memory actors = [auditorA, auditorB, challengerC, requester];
        address actor = actors[bound(actorSeed, 0, 3)];
        uint256 balBefore = actor.balance;
        vm.prank(actor);
        try poa.withdrawExpiredChallengeBond() {
            totalWithdrawn += actor.balance - balBefore;
        } catch {}
    }

    function expireRequest(uint256 requestSeed) external {
        if (requestIds.length == 0) return;
        uint256 requestId = requestIds[bound(requestSeed, 0, requestIds.length - 1)];
        try poa.expireAuditRequest(requestId) {} catch {}
    }

    function refundExpiredRequest(uint256 requestSeed) external {
        if (requestIds.length == 0) return;
        uint256 requestId = requestIds[bound(requestSeed, 0, requestIds.length - 1)];
        uint256 balBefore = requester.balance;
        vm.prank(requester);
        try poa.refundExpiredAuditRequest(requestId) {
            totalWithdrawn += requester.balance - balBefore;
        } catch {}
    }

    function classify(uint256 requestSeed, uint256 maxSeed) external {
        if (requestIds.length == 0) return;
        uint256 requestId = requestIds[bound(requestSeed, 0, requestIds.length - 1)];
        uint256 maxClaims = bound(maxSeed, 1, 10);
        try poa.classifyAuditRequestClaims(requestId, maxClaims) {} catch {}
    }

    function finalize(uint256 requestSeed) external {
        if (requestIds.length == 0) return;
        uint256 requestId = requestIds[bound(requestSeed, 0, requestIds.length - 1)];
        // Protocol fee accrues in-contract; no external send here.
        try poa.finalizeAuditRequestSettlement(requestId) {} catch {}
    }

    function withdrawClaimSettlement(uint256 claimSeed) external {
        if (claimIds.length == 0) return;
        uint256 claimId = claimIds[bound(claimSeed, 0, claimIds.length - 1)];
        address recipient = poa.getAuditRequestClaim(claimId).auditor;
        uint256 balBefore = recipient.balance;
        try poa.withdrawAuditRequestClaimSettlement(claimId) {
            totalWithdrawn += recipient.balance - balBefore;
        } catch {}
    }

    function withdrawRefund(uint256 requestSeed) external {
        if (requestIds.length == 0) return;
        uint256 requestId = requestIds[bound(requestSeed, 0, requestIds.length - 1)];
        uint256 balBefore = requester.balance;
        vm.prank(requester);
        try poa.withdrawAuditRequestRefund(requestId) {
            totalWithdrawn += requester.balance - balBefore;
        } catch {}
    }

    function withdrawFees() external {
        uint256 balBefore = treasury.balance;
        vm.prank(treasury);
        try poa.withdrawFees() {
            totalWithdrawn += treasury.balance - balBefore;
        } catch {}
    }

    function warp(uint256 delta) external {
        vm.warp(block.timestamp + bound(delta, 1, RESOLUTION_WINDOW + 2));
    }

    /// @notice Sum of the pull-refund liabilities the handler's known actors are
    ///         owed; used by the solvency invariant.
    function sumExpiredRefunds() external view returns (uint256 total) {
        total += poa.expiredChallengeBondRefunds(auditorA);
        total += poa.expiredChallengeBondRefunds(auditorB);
        total += poa.expiredChallengeBondRefunds(challengerC);
        total += poa.expiredChallengeBondRefunds(requester);
    }
}

contract ProofOfAuditInvariant is Test {
    ProofOfAudit internal poa;
    InvariantIdentityRegistry internal identityRegistry;
    InvariantHandler internal handler;

    address internal arbiter = address(0xA11CE);
    address internal treasury = address(0xFEE);
    address internal requester = address(0x9E51);
    address internal auditorA = address(0xB0B);
    address internal auditorB = address(0xC0DE);
    address internal challengerC = address(0xCA11);
    address internal auditTarget = address(0xD00D);

    uint256 internal constant STAKE = 0.01 ether;
    uint256 internal constant BOND = 0.005 ether;
    uint256 internal constant WINDOW = 1 days;
    uint256 internal constant RESOLUTION_WINDOW = 2 days;
    uint256 internal constant PROTOCOL_FEE_BPS = 500;
    uint256 internal constant RESOLUTION_FEE_BPS = 1000;

    function setUp() public {
        poa = new ProofOfAudit(
            arbiter,
            treasury,
            STAKE,
            BOND,
            WINDOW,
            RESOLUTION_WINDOW,
            PROTOCOL_FEE_BPS,
            RESOLUTION_FEE_BPS
        );
        identityRegistry = new InvariantIdentityRegistry();
        identityRegistry.setOwner(1, auditorA);
        identityRegistry.setOwner(2, auditorB);
        identityRegistry.setOwner(3, challengerC);

        handler = new InvariantHandler(
            poa,
            identityRegistry,
            requester,
            auditorA,
            auditorB,
            challengerC,
            arbiter,
            treasury,
            auditTarget
        );

        // Fund actors and the handler generously so that neither the pranked
        // sender nor the handler ever runs out of ETH mid-run.
        uint256 funds = 1_000_000 ether;
        vm.deal(address(handler), funds);
        vm.deal(requester, funds);
        vm.deal(auditorA, funds);
        vm.deal(auditorB, funds);
        vm.deal(challengerC, funds);
        vm.deal(arbiter, funds);
        vm.deal(treasury, funds);

        bytes4[] memory selectors = new bytes4[](18);
        selectors[0] = InvariantHandler.publish.selector;
        selectors[1] = InvariantHandler.challengeDirect.selector;
        selectors[2] = InvariantHandler.resolveDirect.selector;
        selectors[3] = InvariantHandler.release.selector;
        selectors[4] = InvariantHandler.createRequest.selector;
        selectors[5] = InvariantHandler.submitClaim.selector;
        selectors[6] = InvariantHandler.challengeClaim.selector;
        selectors[7] = InvariantHandler.resolveClaim.selector;
        selectors[8] = InvariantHandler.expireClaim.selector;
        selectors[9] = InvariantHandler.withdrawExpiredBond.selector;
        selectors[10] = InvariantHandler.expireRequest.selector;
        selectors[11] = InvariantHandler.refundExpiredRequest.selector;
        selectors[12] = InvariantHandler.classify.selector;
        selectors[13] = InvariantHandler.finalize.selector;
        selectors[14] = InvariantHandler.withdrawClaimSettlement.selector;
        selectors[15] = InvariantHandler.withdrawRefund.selector;
        selectors[16] = InvariantHandler.withdrawFees.selector;
        selectors[17] = InvariantHandler.warp.selector;

        targetContract(address(handler));
        targetSelector(FuzzSelector({addr: address(handler), selectors: selectors}));
    }

    /// @notice ETH is conserved: the escrow holds exactly what entered minus
    ///         what has been paid out to recipients.
    function invariant_conservation() public view {
        assertEq(
            address(poa).balance,
            handler.totalDeposited() - handler.totalWithdrawn()
        );
    }

    /// @notice The escrow always holds at least its accrued fees plus the
    ///         outstanding pull-refund liabilities for expired challenge bonds.
    function invariant_solvency() public view {
        uint256 liabilities = poa.accruedProtocolFees() +
            poa.accruedResolutionFees() +
            handler.sumExpiredRefunds();
        assertGe(address(poa).balance, liabilities);
    }
}
