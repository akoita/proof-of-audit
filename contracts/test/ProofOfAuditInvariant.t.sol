// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {StdInvariant} from "forge-std/StdInvariant.sol";
import {ProofOfAudit} from "../src/ProofOfAudit.sol";

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

contract ProofOfAuditSettlementHandler is Test {
    ProofOfAudit internal registry;
    InvariantIdentityRegistry internal identityRegistry;

    address internal requester = address(0xA100);
    address internal auditorOne = address(0xA101);
    address internal auditorTwo = address(0xA102);
    address internal challenger = address(0xA103);
    address internal arbiter = address(0xA104);
    address internal treasury = address(0xA105);
    address internal target = address(0xA106);

    uint256 internal constant STAKE = 0.01 ether;
    uint256 internal constant BOND = 0.005 ether;
    uint256 internal constant BOUNTY = 0.2 ether;
    uint256 internal constant WINDOW = 1 days;

    uint256 public escrowedBounty;
    uint256 public escrowedClaimStake;
    uint256 public escrowedChallengeBond;
    uint256 public requesterRefunds;
    uint256 public claimantPayouts;
    uint256 public challengePayouts;
    uint256 public feesPaid;

    uint256[] internal requestIds;
    uint256[] internal claimIds;

    constructor(ProofOfAudit _registry, InvariantIdentityRegistry _identityRegistry) {
        registry = _registry;
        identityRegistry = _identityRegistry;
    }

    function createRequest(uint96 bounty, uint64 responseWindow) external {
        bounty = uint96(bound(bounty, 0.01 ether, BOUNTY));
        responseWindow = uint64(bound(responseWindow, 1 hours, WINDOW));
        ProofOfAudit.EligibilityConfig memory eligibility = ProofOfAudit.EligibilityConfig({
            minimumStakeAmount: uint96(STAKE),
            allowlistEnabled: false,
            identityRegistry: address(identityRegistry),
            requiredAgentId: 0
        });

        uint256 balanceBefore = requester.balance;
        vm.prank(requester);
        uint256 requestId =
            registry.createAuditRequest{value: bounty}(target, bounty, responseWindow, eligibility, new address[](0));

        requestIds.push(requestId);
        escrowedBounty += balanceBefore - requester.balance;
    }

    function submitClaim(uint256 requestSeed, bool secondAuditor, uint96 stake) external {
        if (requestIds.length == 0) return;

        uint256 requestId = requestIds[bound(requestSeed, 0, requestIds.length - 1)];
        address auditor = secondAuditor ? auditorTwo : auditorOne;
        uint256 agentId = secondAuditor ? 2 : 1;
        stake = uint96(bound(stake, STAKE, 3 * STAKE));

        uint256 balanceBefore = auditor.balance;
        vm.prank(auditor);
        try registry.submitAuditRequestClaim{value: stake}(
            requestId,
            address(identityRegistry),
            agentId,
            keccak256(abi.encode("report", requestId, agentId)),
            keccak256(abi.encode("metadata", requestId, agentId)),
            3,
            2
        ) returns (
            uint256 claimId
        ) {
            claimIds.push(claimId);
            escrowedClaimStake += balanceBefore - auditor.balance;
        } catch {}
    }

    function challengeClaim(uint256 claimSeed) external {
        if (claimIds.length == 0) return;

        uint256 claimId = claimIds[bound(claimSeed, 0, claimIds.length - 1)];
        uint256 balanceBefore = challenger.balance;
        vm.prank(challenger);
        try registry.challengeAuditRequestClaim{value: BOND}(
            claimId, address(identityRegistry), 3, keccak256(abi.encode("challenge", claimId))
        ) {
            escrowedChallengeBond += balanceBefore - challenger.balance;
        } catch {}
    }

    function resolveClaimChallenge(uint256 claimSeed, bool upheld) external {
        if (claimIds.length == 0) return;

        uint256 claimId = claimIds[bound(claimSeed, 0, claimIds.length - 1)];
        uint256 balanceBefore = _claimChallengeBeneficiaryBalance(claimId, upheld);
        vm.prank(arbiter);
        try registry.resolveAuditRequestClaimChallenge(claimId, upheld) {
            uint256 balanceAfter = _claimChallengeBeneficiaryBalance(claimId, upheld);
            if (balanceAfter > balanceBefore) {
                challengePayouts += balanceAfter - balanceBefore;
            }
        } catch {}
    }

    function closeAndClassify(uint256 requestSeed, uint256 maxClaims) external {
        if (requestIds.length == 0) return;

        uint256 requestId = requestIds[bound(requestSeed, 0, requestIds.length - 1)];
        vm.warp(block.timestamp + WINDOW + 1);
        maxClaims = bound(maxClaims, 1, 8);

        try registry.classifyAuditRequestClaims(requestId, maxClaims) {} catch {}
        try registry.finalizeAuditRequestSettlement(requestId) {} catch {}
    }

    function withdrawClaim(uint256 claimSeed) external {
        if (claimIds.length == 0) return;

        uint256 claimId = claimIds[bound(claimSeed, 0, claimIds.length - 1)];
        ProofOfAudit.AuditRequestClaim memory claim = registry.getAuditRequestClaim(claimId);
        uint256 balanceBefore = claim.auditor.balance;

        try registry.withdrawAuditRequestClaimSettlement(claimId) {
            claimantPayouts += claim.auditor.balance - balanceBefore;
        } catch {}
    }

    function withdrawRefund(uint256 requestSeed) external {
        if (requestIds.length == 0) return;

        uint256 requestId = requestIds[bound(requestSeed, 0, requestIds.length - 1)];
        uint256 balanceBefore = requester.balance;

        vm.prank(requester);
        try registry.withdrawAuditRequestRefund(requestId) {
            requesterRefunds += requester.balance - balanceBefore;
        } catch {}
    }

    function withdrawFees() external {
        uint256 balanceBefore = treasury.balance;

        vm.prank(treasury);
        try registry.withdrawFees() {
            feesPaid += treasury.balance - balanceBefore;
        } catch {}
    }

    function accountedEth() external view returns (uint256) {
        return address(registry).balance + requesterRefunds + claimantPayouts + challengePayouts + feesPaid;
    }

    function depositedEth() external view returns (uint256) {
        return escrowedBounty + escrowedClaimStake + escrowedChallengeBond;
    }

    function _claimChallengeBeneficiaryBalance(uint256 claimId, bool upheld) internal view returns (uint256) {
        if (upheld) {
            return challenger.balance;
        }
        ProofOfAudit.AuditRequestClaim memory claim = registry.getAuditRequestClaim(claimId);
        return claim.auditor.balance;
    }
}

contract ProofOfAuditInvariantTest is StdInvariant, Test {
    ProofOfAudit internal registry;
    InvariantIdentityRegistry internal identityRegistry;
    ProofOfAuditSettlementHandler internal handler;

    address internal arbiter = address(0xA104);
    address internal treasury = address(0xA105);
    address internal requester = address(0xA100);
    address internal auditorOne = address(0xA101);
    address internal auditorTwo = address(0xA102);
    address internal challenger = address(0xA103);

    uint256 internal constant STAKE = 0.01 ether;
    uint256 internal constant BOND = 0.005 ether;
    uint256 internal constant WINDOW = 1 days;
    uint256 internal constant PROTOCOL_FEE_BPS = 500;
    uint256 internal constant RESOLUTION_FEE_BPS = 1000;

    function setUp() public {
        registry = new ProofOfAudit(arbiter, treasury, STAKE, BOND, WINDOW, PROTOCOL_FEE_BPS, RESOLUTION_FEE_BPS);
        identityRegistry = new InvariantIdentityRegistry();
        identityRegistry.setOwner(1, auditorOne);
        identityRegistry.setOwner(2, auditorTwo);
        identityRegistry.setOwner(3, challenger);

        vm.deal(requester, 100 ether);
        vm.deal(auditorOne, 100 ether);
        vm.deal(auditorTwo, 100 ether);
        vm.deal(challenger, 100 ether);
        vm.deal(treasury, 100 ether);

        handler = new ProofOfAuditSettlementHandler(registry, identityRegistry);
        targetContract(address(handler));
    }

    function invariant_requestSettlementConservesEth() public view {
        assertEq(handler.accountedEth(), handler.depositedEth());
    }
}
