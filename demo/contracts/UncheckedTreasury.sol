// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "./shared/OperatorRegistry.sol";

contract UncheckedTreasury is OperatorRegistry {
    receive() external payable {}

    function payModule(address payable module, uint256 amount) external onlyOperator {
        require(address(this).balance >= amount, "insufficient");
        module.call{value: amount}("");
    }
}
