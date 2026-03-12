// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

contract DualRiskVault {
    address public owner;
    address payable public payoutSink;
    mapping(address => uint256) public balances;

    constructor(address payable initialPayoutSink) payable {
        owner = msg.sender;
        payoutSink = initialPayoutSink;
    }

    function deposit() external payable {
        balances[msg.sender] += msg.value;
    }

    function rotateOwner(address newOwner) external {
        owner = newOwner;
    }

    function emergencyPayout(uint256 amount) external {
        require(address(this).balance >= amount, "insufficient");
        payoutSink.call{value: amount}("");
    }
}
