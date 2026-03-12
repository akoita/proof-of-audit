// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

abstract contract OperatorRegistry {
    address public owner;
    mapping(address => bool) public operators;

    constructor() {
        owner = msg.sender;
        operators[msg.sender] = true;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "not owner");
        _;
    }

    modifier onlyOperator() {
        require(operators[msg.sender], "not operator");
        _;
    }

    function setOperator(address operator, bool allowed) external onlyOwner {
        operators[operator] = allowed;
    }
}
