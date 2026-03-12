// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

contract AdminSetter {
    address public admin;

    function setAdmin(address newAdmin) external {
        admin = newAdmin;
    }
}

