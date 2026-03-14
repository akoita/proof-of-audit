// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

interface IValidationIdentityRegistry {
    function ownerOf(uint256 tokenId) external view returns (address);
    function getApproved(uint256 tokenId) external view returns (address);
    function isApprovedForAll(address owner, address operator) external view returns (bool);
}

// Local validation sidecar with an ERC-8004-compatible interface.
// Base Sepolia uses the official ValidationRegistry deployment.
contract ValidationRegistryAdapter {
    event ValidationRequest(
        address indexed validatorAddress,
        uint256 indexed agentId,
        string requestURI,
        bytes32 indexed requestHash
    );

    event ValidationResponse(
        address indexed validatorAddress,
        uint256 indexed agentId,
        bytes32 indexed requestHash,
        uint8 response,
        string responseURI,
        bytes32 responseHash,
        string tag
    );

    error InvalidIdentityRegistry();
    error InvalidValidator();
    error ExistingRequest();
    error NotAuthorized();
    error UnknownRequest();
    error InvalidResponse();

    struct ValidationStatus {
        address validatorAddress;
        uint256 agentId;
        uint8 response;
        bytes32 responseHash;
        string tag;
        uint256 lastUpdate;
        bool hasResponse;
    }

    address public immutable identityRegistry;

    mapping(bytes32 => ValidationStatus) private _validations;
    mapping(uint256 => bytes32[]) private _agentValidations;
    mapping(address => bytes32[]) private _validatorRequests;

    constructor(address identityRegistry_) {
        if (identityRegistry_ == address(0)) revert InvalidIdentityRegistry();
        identityRegistry = identityRegistry_;
    }

    function getIdentityRegistry() external view returns (address) {
        return identityRegistry;
    }

    function validationRequest(
        address validatorAddress,
        uint256 agentId,
        string calldata requestURI,
        bytes32 requestHash
    ) external {
        if (validatorAddress == address(0)) revert InvalidValidator();
        if (_validations[requestHash].validatorAddress != address(0)) {
            revert ExistingRequest();
        }

        IValidationIdentityRegistry registry = IValidationIdentityRegistry(
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

        _validations[requestHash] = ValidationStatus({
            validatorAddress: validatorAddress,
            agentId: agentId,
            response: 0,
            responseHash: bytes32(0),
            tag: "",
            lastUpdate: block.timestamp,
            hasResponse: false
        });

        _agentValidations[agentId].push(requestHash);
        _validatorRequests[validatorAddress].push(requestHash);

        emit ValidationRequest(validatorAddress, agentId, requestURI, requestHash);
    }

    function validationResponse(
        bytes32 requestHash,
        uint8 response,
        string calldata responseURI,
        bytes32 responseHash,
        string calldata tag
    ) external {
        ValidationStatus storage status_ = _validations[requestHash];
        if (status_.validatorAddress == address(0)) revert UnknownRequest();
        if (msg.sender != status_.validatorAddress) revert NotAuthorized();
        if (response > 100) revert InvalidResponse();

        status_.response = response;
        status_.responseHash = responseHash;
        status_.tag = tag;
        status_.lastUpdate = block.timestamp;
        status_.hasResponse = true;

        emit ValidationResponse(
            status_.validatorAddress,
            status_.agentId,
            requestHash,
            response,
            responseURI,
            responseHash,
            tag
        );
    }

    function getValidationStatus(
        bytes32 requestHash
    )
        external
        view
        returns (
            address validatorAddress,
            uint256 agentId,
            uint8 response,
            bytes32 responseHash,
            string memory tag,
            uint256 lastUpdate
        )
    {
        ValidationStatus memory status_ = _validations[requestHash];
        if (status_.validatorAddress == address(0)) revert UnknownRequest();
        return (
            status_.validatorAddress,
            status_.agentId,
            status_.response,
            status_.responseHash,
            status_.tag,
            status_.lastUpdate
        );
    }

    function getSummary(
        uint256 agentId,
        address[] calldata validatorAddresses,
        string calldata tag
    ) external view returns (uint64 count, uint8 avgResponse) {
        uint256 totalResponse;
        bytes32[] storage requestHashes = _agentValidations[agentId];

        for (uint256 i; i < requestHashes.length; i++) {
            ValidationStatus storage status_ = _validations[requestHashes[i]];
            bool matchValidator = validatorAddresses.length == 0;
            if (!matchValidator) {
                for (uint256 j; j < validatorAddresses.length; j++) {
                    if (status_.validatorAddress == validatorAddresses[j]) {
                        matchValidator = true;
                        break;
                    }
                }
            }

            bool matchTag = bytes(tag).length == 0
                || keccak256(bytes(status_.tag)) == keccak256(bytes(tag));

            if (matchValidator && matchTag && status_.hasResponse) {
                totalResponse += status_.response;
                count++;
            }
        }

        avgResponse = count > 0 ? uint8(totalResponse / count) : 0;
    }

    function getAgentValidations(
        uint256 agentId
    ) external view returns (bytes32[] memory) {
        return _agentValidations[agentId];
    }

    function getValidatorRequests(
        address validatorAddress
    ) external view returns (bytes32[] memory) {
        return _validatorRequests[validatorAddress];
    }
}
