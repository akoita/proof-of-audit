// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

interface IReputationIdentityRegistry {
    function ownerOf(uint256 tokenId) external view returns (address);
    function getApproved(uint256 tokenId) external view returns (address);
    function isApprovedForAll(address owner, address operator) external view returns (bool);
}

// Local reputation sidecar with an ERC-8004-aligned interaction surface.
// It accumulates per-agent claim and resolution counts without replacing
// ProofOfAudit as the settlement source of truth.
contract ReputationRegistryAdapter {
    event ClaimRecorded(
        uint256 indexed agentId,
        bytes32 indexed claimHash,
        uint256 stakeWei,
        string claimURI
    );

    event ResolutionRecorded(
        uint256 indexed agentId,
        bytes32 indexed claimHash,
        bool claimConfirmed,
        string resolutionURI
    );

    error InvalidIdentityRegistry();
    error InvalidOperator();
    error InvalidClaim();
    error ExistingClaim();
    error UnknownClaim();
    error ResolutionAlreadyRecorded();
    error NotAuthorized();

    struct ReputationStats {
        uint64 totalClaims;
        uint64 resolvedChallenges;
        uint64 rejectedCount;
        uint64 upheldCount;
        uint256 totalStakeWei;
        uint256 lastUpdate;
    }

    struct ClaimStatus {
        uint256 agentId;
        uint256 stakeWei;
        bool claimRecorded;
        bool resolutionRecorded;
        bool claimConfirmed;
        uint256 lastUpdate;
    }

    address public immutable identityRegistry;
    address public immutable reputationOperator;

    mapping(uint256 => ReputationStats) private _reputationByAgent;
    mapping(bytes32 => ClaimStatus) private _claimStatus;
    mapping(uint256 => bytes32[]) private _agentClaims;

    constructor(address identityRegistry_, address reputationOperator_) {
        if (identityRegistry_ == address(0)) revert InvalidIdentityRegistry();
        if (reputationOperator_ == address(0)) revert InvalidOperator();
        identityRegistry = identityRegistry_;
        reputationOperator = reputationOperator_;
    }

    function getIdentityRegistry() external view returns (address) {
        return identityRegistry;
    }

    function recordClaim(
        uint256 agentId,
        bytes32 claimHash,
        uint256 stakeWei,
        string calldata claimURI
    ) external {
        if (claimHash == bytes32(0)) revert InvalidClaim();
        if (_claimStatus[claimHash].claimRecorded) revert ExistingClaim();

        IReputationIdentityRegistry registry = IReputationIdentityRegistry(
            identityRegistry
        );
        address owner = registry.ownerOf(agentId);
        if (
            msg.sender != owner
                && !registry.isApprovedForAll(owner, msg.sender)
                && registry.getApproved(agentId) != msg.sender
        ) {
            revert NotAuthorized();
        }

        _claimStatus[claimHash] = ClaimStatus({
            agentId: agentId,
            stakeWei: stakeWei,
            claimRecorded: true,
            resolutionRecorded: false,
            claimConfirmed: false,
            lastUpdate: block.timestamp
        });

        ReputationStats storage stats = _reputationByAgent[agentId];
        stats.totalClaims += 1;
        stats.totalStakeWei += stakeWei;
        stats.lastUpdate = block.timestamp;
        _agentClaims[agentId].push(claimHash);

        emit ClaimRecorded(agentId, claimHash, stakeWei, claimURI);
    }

    function recordResolution(
        bytes32 claimHash,
        bool claimConfirmed,
        string calldata resolutionURI
    ) external {
        if (msg.sender != reputationOperator) revert NotAuthorized();
        ClaimStatus storage status_ = _claimStatus[claimHash];
        if (!status_.claimRecorded) revert UnknownClaim();
        if (status_.resolutionRecorded) revert ResolutionAlreadyRecorded();

        status_.resolutionRecorded = true;
        status_.claimConfirmed = claimConfirmed;
        status_.lastUpdate = block.timestamp;

        ReputationStats storage stats = _reputationByAgent[status_.agentId];
        stats.resolvedChallenges += 1;
        if (claimConfirmed) {
            stats.rejectedCount += 1;
        } else {
            stats.upheldCount += 1;
        }
        stats.lastUpdate = block.timestamp;

        emit ResolutionRecorded(
            status_.agentId,
            claimHash,
            claimConfirmed,
            resolutionURI
        );
    }

    function getReputation(
        uint256 agentId
    )
        external
        view
        returns (
            uint64 totalClaims,
            uint64 resolvedChallenges,
            uint64 rejectedCount,
            uint64 upheldCount,
            uint256 totalStakeWei,
            uint256 lastUpdate,
            uint8 score
        )
    {
        ReputationStats memory stats = _reputationByAgent[agentId];
        totalClaims = stats.totalClaims;
        resolvedChallenges = stats.resolvedChallenges;
        rejectedCount = stats.rejectedCount;
        upheldCount = stats.upheldCount;
        totalStakeWei = stats.totalStakeWei;
        lastUpdate = stats.lastUpdate;
        score = resolvedChallenges == 0
            ? 50
            : uint8((uint256(rejectedCount) * 100) / uint256(resolvedChallenges));
    }

    function getClaimStatus(
        bytes32 claimHash
    )
        external
        view
        returns (
            uint256 agentId,
            uint256 stakeWei,
            bool claimRecorded,
            bool resolutionRecorded,
            bool claimConfirmed,
            uint256 lastUpdate
        )
    {
        ClaimStatus memory status_ = _claimStatus[claimHash];
        if (!status_.claimRecorded) revert UnknownClaim();
        return (
            status_.agentId,
            status_.stakeWei,
            status_.claimRecorded,
            status_.resolutionRecorded,
            status_.claimConfirmed,
            status_.lastUpdate
        );
    }

    function getAgentClaims(
        uint256 agentId
    ) external view returns (bytes32[] memory) {
        return _agentClaims[agentId];
    }
}
