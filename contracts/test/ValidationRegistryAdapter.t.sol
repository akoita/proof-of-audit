// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {AgentIdentityRegistry} from "../src/AgentIdentityRegistry.sol";
import {ValidationRegistryAdapter} from "../src/ValidationRegistryAdapter.sol";

contract ValidationRegistryAdapterTest is Test {
    AgentIdentityRegistry internal identityRegistry;
    ValidationRegistryAdapter internal validationRegistry;

    address internal admin = address(0xA11CE);
    address internal agentOwner = address(0xB0B);
    address internal validator = address(0xCA11);
    address internal outsider = address(0xD00D);

    uint256 internal agentId;
    bytes32 internal requestHash =
        keccak256("proof-of-audit.validation.request.v1");

    function setUp() public {
        identityRegistry = new AgentIdentityRegistry(admin);
        validationRegistry = new ValidationRegistryAdapter(
            address(identityRegistry)
        );

        vm.prank(admin);
        agentId = identityRegistry.registerAgent(
            agentOwner,
            "ipfs://proof-of-audit/registration.json"
        );
    }

    function testOwnerCanOpenValidationRequestAndValidatorCanRespond() public {
        vm.prank(agentOwner);
        validationRegistry.validationRequest(
            validator,
            agentId,
            "ipfs://proof-of-audit/validation/request.json",
            requestHash
        );

        bytes32[] memory agentValidations = validationRegistry.getAgentValidations(
            agentId
        );
        assertEq(agentValidations.length, 1);
        assertEq(agentValidations[0], requestHash);

        vm.prank(validator);
        validationRegistry.validationResponse(
            requestHash,
            100,
            "ipfs://proof-of-audit/validation/response.json",
            keccak256("response"),
            "claim-confirmed"
        );

        (
            address validatorAddress,
            uint256 recordedAgentId,
            uint8 response,
            bytes32 responseHash,
            string memory tag,
            uint256 lastUpdate
        ) = validationRegistry.getValidationStatus(requestHash);

        assertEq(validatorAddress, validator);
        assertEq(recordedAgentId, agentId);
        assertEq(response, 100);
        assertEq(responseHash, keccak256("response"));
        assertEq(tag, "claim-confirmed");
        assertGt(lastUpdate, 0);

        (uint64 count, uint8 avgResponse) = validationRegistry.getSummary(
            agentId,
            new address[](0),
            "claim-confirmed"
        );
        assertEq(count, 1);
        assertEq(avgResponse, 100);
    }

    function testNonOwnerCannotOpenValidationRequest() public {
        vm.prank(outsider);
        vm.expectRevert(ValidationRegistryAdapter.NotAuthorized.selector);
        validationRegistry.validationRequest(
            validator,
            agentId,
            "ipfs://proof-of-audit/validation/request.json",
            requestHash
        );
    }

    function testOnlyRequestedValidatorCanRespond() public {
        vm.prank(agentOwner);
        validationRegistry.validationRequest(
            validator,
            agentId,
            "ipfs://proof-of-audit/validation/request.json",
            requestHash
        );

        vm.prank(outsider);
        vm.expectRevert(ValidationRegistryAdapter.NotAuthorized.selector);
        validationRegistry.validationResponse(
            requestHash,
            100,
            "ipfs://proof-of-audit/validation/response.json",
            keccak256("response"),
            "claim-confirmed"
        );
    }
}
