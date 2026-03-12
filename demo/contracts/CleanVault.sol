// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

contract CleanVault {
    address public immutable owner;
    mapping(address => uint256) public balances;

    constructor() {
        owner = msg.sender;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "not owner");
        _;
    }

    function deposit() external payable {
        balances[msg.sender] += msg.value;
    }

    function sweep(address payable to, uint256 amount) external onlyOwner {
        require(address(this).balance >= amount, "insufficient");
        (bool ok, ) = to.call{value: amount}("");
        require(ok, "send failed");
    }
}
