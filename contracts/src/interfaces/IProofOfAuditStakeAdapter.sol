// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

interface IProofOfAuditStakeAdapter {
    struct PublishRequest {
        address target;
        bytes32 reportHash;
        bytes32 metadataHash;
        uint8 maxSeverity;
        uint8 findingCount;
        uint256 stakeWei;
        bytes32 claimKey;
    }

    struct PublishResult {
        uint256 auditId;
        address settlementContract;
    }

    function publishStakedAudit(
        PublishRequest calldata request
    ) external payable returns (PublishResult memory);

    function releaseStake(uint256 auditId) external;

    function settlementContract() external view returns (address);
}
