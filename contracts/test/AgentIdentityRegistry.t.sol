// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {AgentIdentityRegistry} from "../src/AgentIdentityRegistry.sol";

contract AgentIdentityRegistryTest is Test {
    AgentIdentityRegistry internal registry;

    address internal admin = address(0xA11CE);
    address internal auditorOwner = address(0xB0B);
    address internal outsider = address(0xCA11);

    function setUp() public {
        registry = new AgentIdentityRegistry(admin);
    }

    function testRegisterAgentStoresOwnerAndURI() public {
        vm.prank(admin);
        uint256 agentId = registry.registerAgent(
            auditorOwner,
            "ipfs://proof-of-audit/registration.json"
        );

        (address owner, string memory registrationURI) = registry.getAgent(agentId);

        assertEq(agentId, 1);
        assertEq(owner, auditorOwner);
        assertEq(registrationURI, "ipfs://proof-of-audit/registration.json");
        assertEq(registry.ownerOf(agentId), auditorOwner);
        assertEq(registry.balanceOf(auditorOwner), 1);
        assertEq(registry.tokenURI(agentId), "ipfs://proof-of-audit/registration.json");
    }

    function testOnlyAdminCanRegisterAgent() public {
        vm.prank(outsider);
        vm.expectRevert(AgentIdentityRegistry.NotAuthorized.selector);
        registry.registerAgent(
            auditorOwner,
            "ipfs://proof-of-audit/registration.json"
        );
    }

    function testOwnerCanUpdateRegistrationURI() public {
        vm.prank(admin);
        uint256 agentId = registry.registerAgent(
            auditorOwner,
            "ipfs://proof-of-audit/registration.json"
        );

        vm.prank(auditorOwner);
        registry.updateRegistrationURI(agentId, "ipfs://proof-of-audit/v2.json");

        assertEq(registry.tokenURI(agentId), "ipfs://proof-of-audit/v2.json");
    }

    function testAdminCanUpdateRegistrationURI() public {
        vm.prank(admin);
        uint256 agentId = registry.registerAgent(
            auditorOwner,
            "ipfs://proof-of-audit/registration.json"
        );

        vm.prank(admin);
        registry.updateRegistrationURI(agentId, "ipfs://proof-of-audit/v2.json");

        assertEq(registry.tokenURI(agentId), "ipfs://proof-of-audit/v2.json");
    }
}
