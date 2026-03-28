// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

interface IAgentIdentityRegistry {
    function ownerOf(uint256 agentId) external view returns (address);
}

contract ProofOfAudit {
    enum AuditState {
        None,
        Published,
        Challenged,
        Resolved
    }

    enum AuditRequestState {
        None,
        Open,
        Closed,
        Expired,
        Settled
    }

    enum Resolution {
        None,
        ChallengeUpheld,
        ChallengeRejected
    }

    enum AuditRequestClaimState {
        None,
        Submitted,
        Challenged,
        Slashed,
        Resolved
    }

    struct EligibilityConfig {
        uint96 minimumStakeAmount;
        bool allowlistEnabled;
        address identityRegistry;
        uint256 requiredAgentId;
    }

    struct AuditRecord {
        address auditor;
        address target;
        bytes32 reportHash;
        bytes32 metadataHash;
        uint64 publishedAt;
        uint64 challengedAt;
        uint96 stakeAmount;
        uint96 challengeBond;
        uint8 maxSeverity;
        uint8 findingCount;
        AuditState state;
        Resolution resolution;
        address challenger;
        bytes32 evidenceHash;
    }

    struct AuditRequest {
        address requester;
        address target;
        uint64 createdAt;
        uint64 responseWindowEnd;
        uint96 bountyAmount;
        uint32 claimCount;
        AuditRequestState state;
        EligibilityConfig eligibility;
    }

    struct AuditRequestClaim {
        uint256 requestId;
        address auditor;
        address agentRegistry;
        uint256 agentId;
        uint64 submittedAt;
        uint64 challengedAt;
        uint96 stakeAmount;
        uint96 challengeBond;
        bytes32 reportHash;
        bytes32 metadataHash;
        uint8 maxSeverity;
        uint8 findingCount;
        AuditRequestClaimState state;
        Resolution resolution;
        address challenger;
        bytes32 evidenceHash;
    }

    error IncorrectStake();
    error IncorrectChallengeBond();
    error IncorrectRequestBounty();
    error InvalidAudit();
    error InvalidAuditRequest();
    error InvalidState();
    error InvalidRequestState();
    error InvalidResponseWindow();
    error InvalidRequestAllowlist();
    error IdentityOwnerMismatch();
    error DuplicateRequestClaim();
    error InsufficientRequestClaimStake();
    error RequestClaimWindowClosed();
    error RequestClaimNotAllowlisted();
    error RequestClaimIdentityRegistryMismatch();
    error RequestClaimAgentIdMismatch();
    error InvalidAuditRequestClaim();
    error RequestClaimSelfChallengeNotAllowed();
    error ChallengeWindowClosed();
    error ChallengeWindowOpen();
    error ResponseWindowOpen();
    error RequestHasClaims();
    error NotRequester();
    error NotArbiter();
    error TransferFailed();

    event AuditPublished(
        uint256 indexed auditId,
        address indexed auditor,
        address indexed target,
        bytes32 reportHash,
        uint256 stakeAmount,
        uint8 maxSeverity,
        uint8 findingCount
    );

    event ChallengeOpened(
        uint256 indexed auditId,
        address indexed challenger,
        bytes32 evidenceHash,
        uint256 challengeBond
    );

    event ChallengeResolved(
        uint256 indexed auditId,
        Resolution resolution,
        address indexed beneficiary,
        uint256 payout
    );

    event StakeReleased(
        uint256 indexed auditId,
        address indexed auditor,
        uint256 amount
    );

    event AuditRequested(
        uint256 indexed requestId,
        address indexed requester,
        address indexed target,
        uint256 bountyAmount,
        uint64 responseWindowEnd,
        uint256 minimumStakeAmount,
        bool allowlistEnabled,
        bytes32 allowlistRoot,
        address identityRegistry,
        uint256 requiredAgentId
    );

    event AuditRequestExpired(
        uint256 indexed requestId,
        address indexed requester,
        uint256 bountyAmount
    );

    event AuditRequestRefunded(
        uint256 indexed requestId,
        address indexed requester,
        uint256 bountyAmount
    );

    event AuditRequestClaimSubmitted(
        uint256 indexed requestId,
        uint256 indexed claimId,
        address indexed auditor,
        address agentRegistry,
        uint256 agentId,
        uint256 stakeAmount,
        bytes32 reportHash,
        bytes32 metadataHash,
        uint8 maxSeverity,
        uint8 findingCount
    );

    event AuditRequestClaimChallengeOpened(
        uint256 indexed requestId,
        uint256 indexed claimId,
        address indexed challenger,
        address agentRegistry,
        uint256 agentId,
        bytes32 evidenceHash,
        uint256 challengeBond
    );

    event AuditRequestClaimChallengeResolved(
        uint256 indexed requestId,
        uint256 indexed claimId,
        Resolution resolution,
        address indexed beneficiary,
        uint256 payout
    );

    uint256 public immutable requiredStake;
    uint256 public immutable requiredChallengeBond;
    uint256 public immutable challengeWindow;
    address public immutable arbiter;

    uint256 public nextAuditId;
    uint256 public nextRequestId;
    uint256 public nextRequestClaimId;
    mapping(uint256 => AuditRecord) private audits;
    mapping(uint256 => AuditRequest) private auditRequests;
    mapping(uint256 => AuditRequestClaim) private auditRequestClaims;
    mapping(uint256 => uint256[]) private auditRequestClaimIds;
    mapping(uint256 => mapping(bytes32 => bool)) private requestClaimIdentityUsed;
    mapping(uint256 => mapping(address => bool)) private requestClaimAllowlistedAuditors;
    mapping(uint256 => address[]) private requestClaimAllowlistEntries;

    constructor(
        address _arbiter,
        uint256 _requiredStake,
        uint256 _requiredChallengeBond,
        uint256 _challengeWindow
    ) {
        arbiter = _arbiter;
        requiredStake = _requiredStake;
        requiredChallengeBond = _requiredChallengeBond;
        challengeWindow = _challengeWindow;
    }

    function publishAudit(
        address target,
        bytes32 reportHash,
        bytes32 metadataHash,
        uint8 maxSeverity,
        uint8 findingCount
    ) external payable returns (uint256 auditId) {
        if (msg.value != requiredStake) revert IncorrectStake();

        auditId = ++nextAuditId;
        audits[auditId] = AuditRecord({
            auditor: msg.sender,
            target: target,
            reportHash: reportHash,
            metadataHash: metadataHash,
            publishedAt: uint64(block.timestamp),
            challengedAt: 0,
            stakeAmount: uint96(msg.value),
            challengeBond: 0,
            maxSeverity: maxSeverity,
            findingCount: findingCount,
            state: AuditState.Published,
            resolution: Resolution.None,
            challenger: address(0),
            evidenceHash: bytes32(0)
        });

        emit AuditPublished(
            auditId,
            msg.sender,
            target,
            reportHash,
            msg.value,
            maxSeverity,
            findingCount
        );
    }

    function createAuditRequest(
        address target,
        uint96 bountyAmount,
        uint64 responseWindow,
        EligibilityConfig calldata eligibility,
        address[] calldata allowlistedAuditors
    ) external payable returns (uint256 requestId) {
        if (responseWindow == 0) revert InvalidResponseWindow();
        if (bountyAmount == 0 || msg.value != bountyAmount) {
            revert IncorrectRequestBounty();
        }
        if (eligibility.allowlistEnabled && allowlistedAuditors.length == 0) {
            revert InvalidRequestAllowlist();
        }

        requestId = ++nextRequestId;
        auditRequests[requestId] = AuditRequest({
            requester: msg.sender,
            target: target,
            createdAt: uint64(block.timestamp),
            responseWindowEnd: uint64(block.timestamp) + responseWindow,
            bountyAmount: bountyAmount,
            claimCount: 0,
            state: AuditRequestState.Open,
            eligibility: EligibilityConfig({
                minimumStakeAmount: eligibility.minimumStakeAmount,
                allowlistEnabled: eligibility.allowlistEnabled,
                identityRegistry: eligibility.identityRegistry,
                requiredAgentId: eligibility.requiredAgentId
            })
        });
        if (eligibility.allowlistEnabled) {
            for (uint256 i; i < allowlistedAuditors.length; i++) {
                address auditor = allowlistedAuditors[i];
                if (auditor == address(0)) revert InvalidRequestAllowlist();
                if (!requestClaimAllowlistedAuditors[requestId][auditor]) {
                    requestClaimAllowlistedAuditors[requestId][auditor] = true;
                    requestClaimAllowlistEntries[requestId].push(auditor);
                }
            }
        }

        emit AuditRequested(
            requestId,
            msg.sender,
            target,
            bountyAmount,
            uint64(block.timestamp) + responseWindow,
            eligibility.minimumStakeAmount,
            eligibility.allowlistEnabled,
            _allowlistCommitment(requestId),
            eligibility.identityRegistry,
            eligibility.requiredAgentId
        );
    }

    function challengeAudit(
        uint256 auditId,
        bytes32 evidenceHash
    ) external payable {
        AuditRecord storage audit = audits[auditId];
        if (audit.state != AuditState.Published) revert InvalidState();
        if (audit.publishedAt == 0) revert InvalidAudit();
        if (block.timestamp > audit.publishedAt + challengeWindow) {
            revert ChallengeWindowClosed();
        }
        if (msg.value != requiredChallengeBond) revert IncorrectChallengeBond();

        audit.state = AuditState.Challenged;
        audit.challengedAt = uint64(block.timestamp);
        audit.challengeBond = uint96(msg.value);
        audit.challenger = msg.sender;
        audit.evidenceHash = evidenceHash;

        emit ChallengeOpened(auditId, msg.sender, evidenceHash, msg.value);
    }

    function submitAuditRequestClaim(
        uint256 requestId,
        address agentRegistry,
        uint256 agentId,
        bytes32 reportHash,
        bytes32 metadataHash,
        uint8 maxSeverity,
        uint8 findingCount
    ) external payable returns (uint256 claimId) {
        AuditRequest storage auditRequest = auditRequests[requestId];
        if (auditRequest.createdAt == 0) revert InvalidAuditRequest();
        if (auditRequestState(requestId) != AuditRequestState.Open) {
            revert RequestClaimWindowClosed();
        }
        if (agentRegistry == address(0) || agentId == 0) {
            revert RequestClaimIdentityRegistryMismatch();
        }
        if (
            auditRequest.eligibility.allowlistEnabled &&
            !requestClaimAllowlistedAuditors[requestId][msg.sender]
        ) {
            revert RequestClaimNotAllowlisted();
        }
        if (
            auditRequest.eligibility.identityRegistry != address(0) &&
            auditRequest.eligibility.identityRegistry != agentRegistry
        ) {
            revert RequestClaimIdentityRegistryMismatch();
        }
        if (
            auditRequest.eligibility.requiredAgentId != 0 &&
            auditRequest.eligibility.requiredAgentId != agentId
        ) {
            revert RequestClaimAgentIdMismatch();
        }
        if (IAgentIdentityRegistry(agentRegistry).ownerOf(agentId) != msg.sender) {
            revert IdentityOwnerMismatch();
        }

        uint256 minimumStake = requiredStake;
        if (auditRequest.eligibility.minimumStakeAmount > minimumStake) {
            minimumStake = auditRequest.eligibility.minimumStakeAmount;
        }
        if (msg.value < minimumStake) revert InsufficientRequestClaimStake();

        bytes32 identityKey = keccak256(abi.encode(agentRegistry, agentId));
        if (requestClaimIdentityUsed[requestId][identityKey]) {
            revert DuplicateRequestClaim();
        }
        requestClaimIdentityUsed[requestId][identityKey] = true;

        claimId = ++nextRequestClaimId;
        auditRequestClaims[claimId] = AuditRequestClaim({
            requestId: requestId,
            auditor: msg.sender,
            agentRegistry: agentRegistry,
            agentId: agentId,
            submittedAt: uint64(block.timestamp),
            challengedAt: 0,
            stakeAmount: uint96(msg.value),
            challengeBond: 0,
            reportHash: reportHash,
            metadataHash: metadataHash,
            maxSeverity: maxSeverity,
            findingCount: findingCount,
            state: AuditRequestClaimState.Submitted,
            resolution: Resolution.None,
            challenger: address(0),
            evidenceHash: bytes32(0)
        });
        auditRequestClaimIds[requestId].push(claimId);
        auditRequest.claimCount += 1;

        emit AuditRequestClaimSubmitted(
            requestId,
            claimId,
            msg.sender,
            agentRegistry,
            agentId,
            msg.value,
            reportHash,
            metadataHash,
            maxSeverity,
            findingCount
        );
    }

    function challengeAuditRequestClaim(
        uint256 claimId,
        address agentRegistry,
        uint256 agentId,
        bytes32 evidenceHash
    ) external payable {
        AuditRequestClaim storage claim = auditRequestClaims[claimId];
        if (claim.requestId == 0) revert InvalidAuditRequestClaim();
        if (claim.state != AuditRequestClaimState.Submitted) revert InvalidState();
        if (claim.auditor == msg.sender) revert RequestClaimSelfChallengeNotAllowed();
        if (block.timestamp > claim.submittedAt + challengeWindow) {
            revert ChallengeWindowClosed();
        }
        if (msg.value != requiredChallengeBond) revert IncorrectChallengeBond();

        _requireRequestClaimAuditorEligibility(
            claim.requestId,
            agentRegistry,
            agentId
        );

        claim.state = AuditRequestClaimState.Challenged;
        claim.challengedAt = uint64(block.timestamp);
        claim.challengeBond = uint96(msg.value);
        claim.challenger = msg.sender;
        claim.evidenceHash = evidenceHash;

        emit AuditRequestClaimChallengeOpened(
            claim.requestId,
            claimId,
            msg.sender,
            agentRegistry,
            agentId,
            evidenceHash,
            msg.value
        );
    }

    function resolveChallenge(uint256 auditId, bool upheld) external {
        if (msg.sender != arbiter) revert NotArbiter();

        AuditRecord storage audit = audits[auditId];
        if (audit.state != AuditState.Challenged) revert InvalidState();

        audit.state = AuditState.Resolved;

        address beneficiary;
        uint256 payout;

        if (upheld) {
            audit.resolution = Resolution.ChallengeUpheld;
            beneficiary = audit.challenger;
            payout = uint256(audit.stakeAmount) + uint256(audit.challengeBond);
        } else {
            audit.resolution = Resolution.ChallengeRejected;
            beneficiary = audit.auditor;
            payout = uint256(audit.stakeAmount) + uint256(audit.challengeBond);
        }

        _sendValue(beneficiary, payout);
        emit ChallengeResolved(auditId, audit.resolution, beneficiary, payout);
    }

    function resolveAuditRequestClaimChallenge(
        uint256 claimId,
        bool upheld
    ) external {
        if (msg.sender != arbiter) revert NotArbiter();

        AuditRequestClaim storage claim = auditRequestClaims[claimId];
        if (claim.requestId == 0) revert InvalidAuditRequestClaim();
        if (claim.state != AuditRequestClaimState.Challenged) revert InvalidState();

        address beneficiary;
        uint256 payout;

        if (upheld) {
            claim.state = AuditRequestClaimState.Slashed;
            claim.resolution = Resolution.ChallengeUpheld;
            beneficiary = claim.challenger;
            payout = uint256(claim.stakeAmount) + uint256(claim.challengeBond);
        } else {
            claim.state = AuditRequestClaimState.Resolved;
            claim.resolution = Resolution.ChallengeRejected;
            beneficiary = claim.auditor;
            payout = uint256(claim.challengeBond);
        }

        _sendValue(beneficiary, payout);
        emit AuditRequestClaimChallengeResolved(
            claim.requestId,
            claimId,
            claim.resolution,
            beneficiary,
            payout
        );
    }

    function releaseStake(uint256 auditId) external {
        AuditRecord storage audit = audits[auditId];
        if (audit.publishedAt == 0) revert InvalidAudit();
        if (audit.state != AuditState.Published) revert InvalidState();
        if (block.timestamp <= audit.publishedAt + challengeWindow) {
            revert ChallengeWindowOpen();
        }

        audit.state = AuditState.Resolved;
        audit.resolution = Resolution.ChallengeRejected;

        uint256 payout = audit.stakeAmount;
        _sendValue(audit.auditor, payout);

        emit StakeReleased(auditId, audit.auditor, payout);
    }

    function getAudit(
        uint256 auditId
    ) external view returns (AuditRecord memory) {
        return audits[auditId];
    }

    function expireAuditRequest(uint256 requestId) external {
        AuditRequest storage auditRequest = auditRequests[requestId];
        if (auditRequest.createdAt == 0) revert InvalidAuditRequest();
        if (auditRequestState(requestId) != AuditRequestState.Closed) {
            revert InvalidRequestState();
        }
        if (auditRequest.claimCount != 0) revert RequestHasClaims();

        auditRequest.state = AuditRequestState.Expired;

        emit AuditRequestExpired(
            requestId,
            auditRequest.requester,
            auditRequest.bountyAmount
        );
    }

    function refundExpiredAuditRequest(uint256 requestId) external {
        AuditRequest storage auditRequest = auditRequests[requestId];
        if (auditRequest.createdAt == 0) revert InvalidAuditRequest();
        if (auditRequest.state != AuditRequestState.Expired) {
            revert InvalidRequestState();
        }
        if (msg.sender != auditRequest.requester) revert NotRequester();

        auditRequest.state = AuditRequestState.Settled;

        uint256 refundAmount = auditRequest.bountyAmount;
        _sendValue(auditRequest.requester, refundAmount);

        emit AuditRequestRefunded(requestId, auditRequest.requester, refundAmount);
    }

    function getAuditRequest(
        uint256 requestId
    ) external view returns (AuditRequest memory auditRequest) {
        auditRequest = auditRequests[requestId];
        auditRequest.state = auditRequestState(requestId);
    }

    function getAuditRequestClaim(
        uint256 claimId
    ) external view returns (AuditRequestClaim memory) {
        return auditRequestClaims[claimId];
    }

    function getAuditRequestClaimIds(
        uint256 requestId
    ) external view returns (uint256[] memory) {
        return auditRequestClaimIds[requestId];
    }

    function getAuditRequestAllowlistedAuditors(
        uint256 requestId
    ) external view returns (address[] memory) {
        return requestClaimAllowlistEntries[requestId];
    }

    function isAuditRequestAuditorAllowlisted(
        uint256 requestId,
        address auditor
    ) external view returns (bool) {
        return requestClaimAllowlistedAuditors[requestId][auditor];
    }

    function auditRequestState(
        uint256 requestId
    ) public view returns (AuditRequestState) {
        AuditRequest storage auditRequest = auditRequests[requestId];
        if (auditRequest.createdAt == 0) return AuditRequestState.None;
        if (
            auditRequest.state == AuditRequestState.Open &&
            block.timestamp > auditRequest.responseWindowEnd
        ) {
            return AuditRequestState.Closed;
        }
        return auditRequest.state;
    }

    function _sendValue(address to, uint256 amount) private {
        (bool ok, ) = payable(to).call{value: amount}("");
        if (!ok) revert TransferFailed();
    }

    function _requireRequestClaimAuditorEligibility(
        uint256 requestId,
        address agentRegistry,
        uint256 agentId
    ) private view {
        AuditRequest storage auditRequest = auditRequests[requestId];
        if (auditRequest.createdAt == 0) revert InvalidAuditRequest();
        if (agentRegistry == address(0) || agentId == 0) {
            revert RequestClaimIdentityRegistryMismatch();
        }
        if (
            auditRequest.eligibility.allowlistEnabled &&
            !requestClaimAllowlistedAuditors[requestId][msg.sender]
        ) {
            revert RequestClaimNotAllowlisted();
        }
        if (
            auditRequest.eligibility.identityRegistry != address(0) &&
            auditRequest.eligibility.identityRegistry != agentRegistry
        ) {
            revert RequestClaimIdentityRegistryMismatch();
        }
        if (
            auditRequest.eligibility.requiredAgentId != 0 &&
            auditRequest.eligibility.requiredAgentId != agentId
        ) {
            revert RequestClaimAgentIdMismatch();
        }
        if (IAgentIdentityRegistry(agentRegistry).ownerOf(agentId) != msg.sender) {
            revert IdentityOwnerMismatch();
        }
    }

    function _allowlistCommitment(uint256 requestId) private view returns (bytes32) {
        return keccak256(abi.encode(requestClaimAllowlistEntries[requestId]));
    }
}
