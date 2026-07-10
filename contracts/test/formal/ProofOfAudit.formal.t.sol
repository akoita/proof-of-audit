// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {SymTest} from "halmos-cheatcodes/SymTest.sol";
import {ProofOfAudit} from "../../src/ProofOfAudit.sol";

/// @dev Minimal identity registry mirroring the production `ownerOf` interface,
///      kept local to the formal suite (mirrors `InvariantIdentityRegistry` in
///      ProofOfAuditInvariant.t.sol) so the request-claim flow can resolve
///      identity ownership without a cross-file import.
contract FormalIdentityRegistry {
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

/// @title Halmos symbolic property tests for ProofOfAudit escrow accounting.
/// @notice Formal (symbolic) verification of the ProofOfAudit escrow's
///         value-conservation and access-control invariants, authored for
///         issue #314. Each `check_` function is a universally-quantified
///         property over its symbolic parameters.
/// @dev Run with: halmos --contract ProofOfAuditFormalTest
/// @dev Revert-path ("must always revert") properties use low-level `.call`
///      and assert `!ok`, because halmos 0.3.x does not support
///      `vm.expectRevert`. Heavier protocol-wide rules (multi-claim bounty
///      distribution, fee conservation across the full settlement lifecycle)
///      are intentionally out of scope here and deferred to the Certora spec
///      tracked in #316; this suite pins the escrow's core stake/bond money
///      flows that a symbolic solver can discharge quickly.
contract ProofOfAuditFormalTest is Test, SymTest {
    ProofOfAudit internal poa;
    FormalIdentityRegistry internal identityRegistry;

    // Concrete, distinct actors — symbolic addresses explode the path space.
    address internal constant ARBITER = address(0xA11CE);
    address internal constant TREASURY = address(0xFEE);
    address internal constant REQUESTER = address(0x9E51);
    address internal constant AUDITOR = address(0xB0B);
    address internal constant CHALLENGER = address(0xCA11);
    address internal constant TARGET = address(0xD00D);

    // Agent ids registered in the mock identity registry.
    uint256 internal constant AUDITOR_AGENT_ID = 1;
    uint256 internal constant CHALLENGER_AGENT_ID = 3;

    // Concrete economic parameters (symbolic constructor args explode paths).
    uint256 internal constant STAKE = 0.01 ether;
    uint256 internal constant BOND = 0.005 ether;
    uint256 internal constant WINDOW = 1 days;
    uint256 internal constant RESOLUTION_WINDOW = 2 days;
    uint256 internal constant PROTOCOL_FEE_BPS = 500;
    uint256 internal constant RESOLUTION_FEE_BPS = 1000;
    uint96 internal constant BOUNTY = 0.1 ether;

    /// @dev Runs concretely under halmos; symbolic values arrive via the
    ///      `check_` function parameters, not from setUp.
    function setUp() public {
        poa = new ProofOfAudit(
            ARBITER,
            TREASURY,
            STAKE,
            BOND,
            WINDOW,
            RESOLUTION_WINDOW,
            PROTOCOL_FEE_BPS,
            RESOLUTION_FEE_BPS
        );

        identityRegistry = new FormalIdentityRegistry();
        identityRegistry.setOwner(AUDITOR_AGENT_ID, AUDITOR);
        identityRegistry.setOwner(CHALLENGER_AGENT_ID, CHALLENGER);

        // The test contract is the concrete caller for every value-bearing
        // call (vm.prank only spoofs msg.sender, not the funding source), so
        // fund it generously alongside the pranked actors.
        uint256 funds = 1_000 ether;
        vm.deal(address(this), funds);
        vm.deal(REQUESTER, funds);
        vm.deal(AUDITOR, funds);
        vm.deal(CHALLENGER, funds);
        vm.deal(ARBITER, funds);
        vm.deal(TREASURY, funds);
    }

    // ----- Direct audit flow ----------------------------------------------

    /// @notice Publishing escrows exactly the required stake; any other value
    ///         (bounded below 1 ether) reverts.
    function check_publishEscrowsExactStake(uint256 wrongValue) public {
        vm.assume(wrongValue < 1 ether);
        vm.assume(wrongValue != STAKE);

        uint256 balBefore = address(poa).balance;
        vm.prank(AUDITOR);
        poa.publishAudit{value: STAKE}(TARGET, bytes32(0), bytes32(0), 3, 2);
        assert(address(poa).balance == balBefore + STAKE);

        // Any msg.value != requiredStake must revert (IncorrectStake).
        vm.prank(AUDITOR);
        (bool ok, ) = address(poa).call{value: wrongValue}(
            abi.encodeCall(
                poa.publishAudit,
                (TARGET, bytes32(0), bytes32(0), 3, 2)
            )
        );
        assert(!ok);
    }

    /// @notice The auditor can never challenge their own published audit, for
    ///         any evidence hash, even with the exact bond inside the window.
    function check_selfChallengeAlwaysReverts(bytes32 evidenceHash) public {
        vm.prank(AUDITOR);
        uint256 auditId = poa.publishAudit{value: STAKE}(
            TARGET,
            bytes32(0),
            bytes32(0),
            3,
            2
        );

        vm.prank(AUDITOR);
        (bool ok, ) = address(poa).call{value: BOND}(
            abi.encodeCall(poa.challengeAudit, (auditId, evidenceHash))
        );
        assert(!ok);
    }

    /// @notice A non-auditor challenge with the exact bond succeeds anywhere
    ///         inside the challenge window and escrows exactly the bond.
    function check_nonAuditorChallengeSucceedsInsideWindow(
        uint64 delta,
        bytes32 evidenceHash
    ) public {
        vm.assume(delta <= WINDOW);

        vm.prank(AUDITOR);
        uint256 auditId = poa.publishAudit{value: STAKE}(
            TARGET,
            bytes32(0),
            bytes32(0),
            3,
            2
        );

        vm.warp(block.timestamp + delta);

        uint256 balBefore = address(poa).balance;
        vm.prank(CHALLENGER);
        poa.challengeAudit{value: BOND}(auditId, evidenceHash);
        assert(address(poa).balance == balBefore + BOND);
    }

    /// @notice Any challenge strictly after the window (bounded) reverts.
    function check_challengeAfterWindowAlwaysReverts(uint64 delta) public {
        vm.assume(delta > WINDOW);
        vm.assume(delta <= 3650 days);

        vm.prank(AUDITOR);
        uint256 auditId = poa.publishAudit{value: STAKE}(
            TARGET,
            bytes32(0),
            bytes32(0),
            3,
            2
        );

        vm.warp(block.timestamp + delta);

        vm.prank(CHALLENGER);
        (bool ok, ) = address(poa).call{value: BOND}(
            abi.encodeCall(poa.challengeAudit, (auditId, bytes32(0)))
        );
        assert(!ok);
    }

    /// @notice Resolving a challenge moves exactly stake+bond from the escrow
    ///         to the winner (challenger if upheld, else auditor); the direct
    ///         flow charges no resolution fee.
    function check_resolveMovesExactlyStakePlusBond(bool upheld) public {
        vm.prank(AUDITOR);
        uint256 auditId = poa.publishAudit{value: STAKE}(
            TARGET,
            bytes32(0),
            bytes32(0),
            3,
            2
        );

        vm.prank(CHALLENGER);
        poa.challengeAudit{value: BOND}(auditId, bytes32(0));

        address winner = upheld ? CHALLENGER : AUDITOR;
        uint256 winnerBefore = winner.balance;
        uint256 poaBefore = address(poa).balance;

        vm.prank(ARBITER);
        poa.resolveChallenge(auditId, upheld);

        assert(winner.balance == winnerBefore + STAKE + BOND);
        assert(address(poa).balance == poaBefore - STAKE - BOND);
    }

    /// @notice Releasing an unchallenged audit's stake after the window pays
    ///         the auditor exactly the stake.
    function check_releaseStakeReturnsExactStake(uint64 delta) public {
        vm.assume(delta > WINDOW);
        vm.assume(delta <= 3650 days);

        vm.prank(AUDITOR);
        uint256 auditId = poa.publishAudit{value: STAKE}(
            TARGET,
            bytes32(0),
            bytes32(0),
            3,
            2
        );

        vm.warp(block.timestamp + delta);

        uint256 auditorBefore = AUDITOR.balance;
        uint256 poaBefore = address(poa).balance;
        poa.releaseStake(auditId);

        assert(AUDITOR.balance == auditorBefore + STAKE);
        assert(address(poa).balance == poaBefore - STAKE);
    }

    // ----- Request-claim flow ---------------------------------------------

    /// @notice Expiring an unresolved claim challenge (after the resolution
    ///         window) neutrally unwinds it: the claim returns to Submitted,
    ///         the bond is credited to the challenger's pull-refund balance,
    ///         and the escrow balance is unchanged by the expiry call.
    function check_expiryNeutrallyUnwinds(uint64 delta) public {
        vm.assume(delta > RESOLUTION_WINDOW);
        vm.assume(delta <= 3650 days);

        uint256 claimId = _submitAndChallengeClaim();

        vm.warp(block.timestamp + delta);

        uint256 poaBefore = address(poa).balance;
        poa.expireAuditRequestClaimChallenge(claimId);

        ProofOfAudit.AuditRequestClaim memory claim = poa.getAuditRequestClaim(
            claimId
        );
        assert(claim.state == ProofOfAudit.AuditRequestClaimState.Submitted);
        assert(poa.expiredChallengeBondRefunds(CHALLENGER) == BOND);
        assert(address(poa).balance == poaBefore);
    }

    /// @notice After expiry, the challenger withdraws exactly the bond and the
    ///         pull-refund credit is zeroed.
    function check_withdrawExpiredBondPaysExactBond() public {
        uint256 claimId = _submitAndChallengeClaim();

        vm.warp(block.timestamp + RESOLUTION_WINDOW + 1);
        poa.expireAuditRequestClaimChallenge(claimId);

        uint256 challengerBefore = CHALLENGER.balance;
        uint256 poaBefore = address(poa).balance;

        vm.prank(CHALLENGER);
        poa.withdrawExpiredChallengeBond();

        assert(CHALLENGER.balance == challengerBefore + BOND);
        assert(poa.expiredChallengeBondRefunds(CHALLENGER) == 0);
        assert(address(poa).balance == poaBefore - BOND);
    }

    // ----- Helpers ---------------------------------------------------------

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

    /// @dev Opens a request, submits one eligible claim (auditor / agent 1),
    ///      and challenges it with an eligible non-claim identity
    ///      (challenger / agent 3). Concrete throughout.
    function _submitAndChallengeClaim() internal returns (uint256 claimId) {
        vm.prank(REQUESTER);
        uint256 requestId = poa.createAuditRequest{value: BOUNTY}(
            TARGET,
            BOUNTY,
            7 days,
            _openEligibility(),
            new address[](0)
        );

        vm.prank(AUDITOR);
        claimId = poa.submitAuditRequestClaim{value: STAKE}(
            requestId,
            address(identityRegistry),
            AUDITOR_AGENT_ID,
            bytes32(0),
            bytes32(0),
            3,
            2
        );

        vm.prank(CHALLENGER);
        poa.challengeAuditRequestClaim{value: BOND}(
            claimId,
            address(identityRegistry),
            CHALLENGER_AGENT_ID,
            bytes32(0)
        );
    }
}
