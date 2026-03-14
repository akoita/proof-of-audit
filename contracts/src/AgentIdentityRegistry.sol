// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

// Local fallback registry used for localhost and test environments.
// Base Sepolia uses the official ERC-8004 IdentityRegistry instead.
contract AgentIdentityRegistry {
    struct AgentRecord {
        address owner;
        string registrationURI;
    }

    error InvalidOwner();
    error InvalidAgent();
    error NotAuthorized();

    event Transfer(address indexed from, address indexed to, uint256 indexed tokenId);
    event AgentRegistered(
        uint256 indexed agentId,
        address indexed owner,
        string registrationURI
    );
    event RegistrationURIUpdated(uint256 indexed agentId, string registrationURI);

    string public constant name = "Proof-of-Audit Agent Identity";
    string public constant symbol = "PAI";

    address public immutable admin;
    uint256 public nextAgentId;

    mapping(uint256 => AgentRecord) private _agents;
    mapping(address => uint256) private _balances;

    constructor(address _admin) {
        if (_admin == address(0)) revert InvalidOwner();
        admin = _admin;
    }

    function registerAgent(
        address owner,
        string calldata registrationURI
    ) external returns (uint256 agentId) {
        if (msg.sender != admin) revert NotAuthorized();
        if (owner == address(0)) revert InvalidOwner();

        agentId = ++nextAgentId;
        _agents[agentId] = AgentRecord({
            owner: owner,
            registrationURI: registrationURI
        });
        _balances[owner] += 1;

        emit Transfer(address(0), owner, agentId);
        emit AgentRegistered(agentId, owner, registrationURI);
    }

    function updateRegistrationURI(
        uint256 agentId,
        string calldata registrationURI
    ) external {
        AgentRecord storage agent = _agentRecord(agentId);
        if (msg.sender != admin && msg.sender != agent.owner) {
            revert NotAuthorized();
        }

        agent.registrationURI = registrationURI;
        emit RegistrationURIUpdated(agentId, registrationURI);
    }

    function ownerOf(uint256 agentId) external view returns (address) {
        return _agentRecord(agentId).owner;
    }

    function balanceOf(address owner) external view returns (uint256) {
        if (owner == address(0)) revert InvalidOwner();
        return _balances[owner];
    }

    function tokenURI(uint256 agentId) external view returns (string memory) {
        return _agentRecord(agentId).registrationURI;
    }

    function getAgent(
        uint256 agentId
    ) external view returns (address owner, string memory registrationURI) {
        AgentRecord storage agent = _agentRecord(agentId);
        return (agent.owner, agent.registrationURI);
    }

    function _agentRecord(
        uint256 agentId
    ) private view returns (AgentRecord storage agent) {
        agent = _agents[agentId];
        if (agent.owner == address(0)) revert InvalidAgent();
    }
}
