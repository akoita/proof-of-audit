"use client";

import { useState, useEffect, useRef } from "react";

/* ─── Table of Contents data ─── */
const TOC = [
  { id: "overview", label: "Overview" },
  { id: "getting-started", label: "Getting Started" },
  { id: "workbench", label: "Audit Workbench" },
  { id: "fixtures", label: "Demo Fixtures" },
  { id: "submission", label: "Artifact Submission" },
  { id: "analysis", label: "Security Analysis" },
  { id: "findings", label: "Findings & Severity" },
  { id: "publishing", label: "Publishing On-Chain" },
  { id: "challenges", label: "Challenges & Disputes" },
  { id: "multi-agent", label: "Multi-Agent Comparison" },
  { id: "views", label: "Navigation Views" },
  { id: "cli", label: "CLI Agent Workflow" },
  { id: "contracts", label: "Smart Contracts" },
  { id: "troubleshooting", label: "Troubleshooting" },
] as const;

/* ─── Callout component ─── */
function Callout({ type, children }: { type: "tip" | "warning" | "info" | "important"; children: React.ReactNode }) {
  const config = {
    tip:       { icon: "💡", bg: "rgba(52,168,83,0.08)",  border: "rgba(52,168,83,0.25)",  label: "TIP" },
    warning:   { icon: "⚠️", bg: "rgba(251,188,4,0.08)",  border: "rgba(251,188,4,0.25)",  label: "WARNING" },
    info:      { icon: "ℹ️", bg: "rgba(66,133,244,0.08)", border: "rgba(66,133,244,0.20)", label: "INFO" },
    important: { icon: "🔴", bg: "rgba(234,67,53,0.08)",  border: "rgba(234,67,53,0.25)",  label: "IMPORTANT" },
  }[type];
  return (
    <div className="docs-callout" style={{ background: config.bg, borderLeft: `4px solid ${config.border}` }}>
      <div className="docs-callout-header">
        <span>{config.icon}</span>
        <span className="docs-callout-label">{config.label}</span>
      </div>
      <div className="docs-callout-body">{children}</div>
    </div>
  );
}

/* ─── Code block component ─── */
function CodeBlock({ children, lang }: { children: string; lang?: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(children).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };
  return (
    <div className="docs-code-block">
      <div className="docs-code-header">
        <span className="docs-code-lang">{lang ?? "shell"}</span>
        <button type="button" className="docs-code-copy" onClick={copy}>
          {copied ? "✓ Copied" : "Copy"}
        </button>
      </div>
      <pre><code>{children}</code></pre>
    </div>
  );
}

/* ─── Screenshot component ─── */
function Screenshot({ src, caption }: { src: string; caption: string }) {
  return (
    <figure className="docs-screenshot">
      <img src={src} alt={caption} loading="lazy" />
      <figcaption>{caption}</figcaption>
    </figure>
  );
}

/* ─── Main docs view ─── */
export function DocsView() {
  const [activeSection, setActiveSection] = useState("overview");
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = contentRef.current;
    if (!container) return;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActiveSection(entry.target.id);
            break;
          }
        }
      },
      { root: container, rootMargin: "-20% 0px -60% 0px", threshold: 0 }
    );
    for (const item of TOC) {
      const el = document.getElementById(item.id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, []);

  const scrollTo = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className="docs-view">
      {/* Sticky TOC sidebar */}
      <nav className="docs-toc">
        <div className="docs-toc-header">
          <span style={{ fontSize: "1.1rem" }}>📖</span>
          <span>User Manual</span>
        </div>
        {TOC.map((item) => (
          <button
            key={item.id}
            type="button"
            className="docs-toc-item"
            data-active={activeSection === item.id}
            onClick={() => scrollTo(item.id)}
          >
            {item.label}
          </button>
        ))}
        <div className="docs-toc-footer">
          <span className="muted" style={{ fontSize: "0.6rem" }}>v0.1.0 · Proof-of-Audit</span>
        </div>
      </nav>

      {/* Scrollable content */}
      <div className="docs-content" ref={contentRef}>

        {/* ─── Overview ─── */}
        <section id="overview" className="docs-section">
          <h1>Proof-of-Audit Documentation</h1>
          <p className="docs-subtitle">
            Proof-of-Audit is an autonomous smart-contract security platform that enables AI agents to
            produce <strong>deterministic, reproducible forensic audit claims</strong> and publish them
            on-chain with economic accountability through staking.
          </p>
          <div className="docs-feature-card" style={{ marginBottom: 20 }}>
            <span className="docs-feature-icon">🧭</span>
            <h4>Canonical Technical Reference</h4>
            <p>
              The primary engineering reference now lives in
              {" "}
              <a
                href="https://github.com/akoita/proof-of-audit/blob/main/docs/TECHNICAL_DOCUMENTATION.md"
                target="_blank"
                rel="noopener noreferrer"
              >
                TECHNICAL_DOCUMENTATION.md
              </a>
              . Use it for architecture, protocol, contracts, agent integration, frontend behavior,
              standards alignment, deployment, and testing.
            </p>
          </div>
          <div className="docs-feature-grid">
            <div className="docs-feature-card">
              <span className="docs-feature-icon">🔬</span>
              <h4>Automated Analysis</h4>
              <p>AI agents run deterministic security analysis on Solidity contracts and produce structured findings.</p>
            </div>
            <div className="docs-feature-card">
              <span className="docs-feature-icon">⛓️</span>
              <h4>On-Chain Claims</h4>
              <p>Audit reports are published as on-chain claims with ETH staked behind the auditor&apos;s judgment.</p>
            </div>
            <div className="docs-feature-card">
              <span className="docs-feature-icon">⚖️</span>
              <h4>Challenge System</h4>
              <p>Anyone can challenge a claim by posting a bond and providing counter-evidence for review or executable verification.</p>
            </div>
            <div className="docs-feature-card">
              <span className="docs-feature-icon">🛡️</span>
              <h4>Reputation Tracking</h4>
              <p>Auditor reputation scores are computed from challenge outcomes — upheld, rejected, or contested.</p>
            </div>
          </div>
        </section>

        {/* ─── Getting Started ─── */}
        <section id="getting-started" className="docs-section">
          <h2>Getting Started</h2>
          <h3>Prerequisites</h3>
          <ul className="docs-list">
            <li><strong>Node.js</strong> ≥ 18 and <strong>pnpm</strong> for the web frontend</li>
            <li><strong>Python</strong> ≥ 3.11 for the agent runtime</li>
            <li><strong>Foundry</strong> (forge, anvil, cast) for local blockchain simulation</li>
          </ul>

          <h3>Quick Start</h3>
          <Callout type="tip">
            The fastest way to run the full stack is the <code>run-e2e-stack.sh</code> script, which
            starts Anvil, deploys contracts, seeds fixtures, and launches the web server. It uses
            isolated temp config and does not overwrite your local <code>api/.env.local</code> or{" "}
            <code>web/.env.local</code>.
          </Callout>
          <CodeBlock>{`# Clone and install
git clone https://github.com/akoita/proof-of-audit.git
cd proof-of-audit

# Run the full end-to-end stack
./scripts/run-e2e-stack.sh`}</CodeBlock>

          <p>This will start:</p>
          <ol className="docs-list">
            <li><strong>Anvil</strong> — local Ethereum node on port 8545</li>
            <li><strong>Contract deployment</strong> — AuditRegistry, ReputationOracle</li>
            <li><strong>Demo fixtures</strong> — 5 pre-deployed vulnerable contracts</li>
            <li><strong>Web workbench</strong> — Next.js app on <code>localhost:3000</code></li>
          </ol>

          <h3>Environment Configuration</h3>
          <CodeBlock lang="env">{`# web/.env.local
NEXT_PUBLIC_API_BASE=http://localhost:8000
NEXT_PUBLIC_CHAIN_ID=31337
NEXT_PUBLIC_REGISTRY_ADDRESS=0x...
NEXT_PUBLIC_REPUTATION_ADDRESS=0x...`}</CodeBlock>
        </section>

        {/* ─── Audit Workbench ─── */}
        <section id="workbench" className="docs-section">
          <h2>Audit Workbench</h2>
          <p>
            The Workbench is the primary workspace. It shows the current audit context, the agent
            profile, and all the data panels for a claim.
          </p>
          <Screenshot src="/docs/workbench.png" caption="The Audit Workbench — main workspace showing fixtures, submission panel, and analysis results" />

          <h3>Layout Overview</h3>
          <ul className="docs-list">
            <li><strong>Left column</strong> — Artifact Submission panel, audit metadata, agent profile with reputation score</li>
            <li><strong>Right column</strong> — Security analysis summary, detailed findings, evidence hashes, and action cards</li>
            <li><strong>Phase stepper</strong> — Shows the audit lifecycle: Submit → Audit → Publish → Challenge</li>
          </ul>
        </section>

        {/* ─── Fixtures ─── */}
        <section id="fixtures" className="docs-section">
          <h2>Demo Fixtures</h2>
          <p>
            The fixtures panel provides 5 pre-deployed contracts for testing. Click any fixture card
            to load it into the submission panel and run an analysis.
          </p>
          <div className="docs-table-wrapper">
            <table className="docs-table">
              <thead>
                <tr>
                  <th>Fixture</th>
                  <th>Contract</th>
                  <th>Description</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td><strong>🏦 Vulnerable Bank</strong></td>
                  <td><code>VulnerableBank</code></td>
                  <td>Classic reentrancy vulnerability for high-confidence finding</td>
                </tr>
                <tr>
                  <td><strong>🔑 Admin Setter</strong></td>
                  <td><code>AdminSetter</code></td>
                  <td>Access control issues — missing role verification</td>
                </tr>
                <tr>
                  <td><strong>✅ Clean Vault</strong></td>
                  <td><code>CleanVault</code></td>
                  <td>Benchmark clean contract — should produce zero findings</td>
                </tr>
                <tr>
                  <td><strong>⚠️ Dual Risk Vault</strong></td>
                  <td><code>DualRiskVault</code></td>
                  <td>Multi-finding benchmark with access control and payout issues</td>
                </tr>
                <tr>
                  <td><strong>💸 Unchecked Treasury</strong></td>
                  <td><code>UncheckedTreasury</code></td>
                  <td>Unchecked external call return value</td>
                </tr>
              </tbody>
            </table>
          </div>
          <Callout type="info">
            Click a fixture card to auto-populate the deployed address and entry contract name. Then click
            <strong> Run Security Analysis</strong> to generate an audit claim.
          </Callout>
        </section>

        {/* ─── Submission ─── */}
        <section id="submission" className="docs-section">
          <h2>Artifact Submission</h2>
          <p>The submission panel supports three input modes:</p>
          <div className="docs-feature-grid" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
            <div className="docs-feature-card">
              <h4>🧪 Demo Fixture</h4>
              <p>Select a pre-deployed demo contract from the fixtures panel.</p>
            </div>
            <div className="docs-feature-card">
              <h4>📍 Deployed Address</h4>
              <p>Provide an on-chain contract address and entry contract name.</p>
            </div>
            <div className="docs-feature-card">
              <h4>📦 Source Bundle</h4>
              <p>Upload a Solidity source bundle for local analysis.</p>
            </div>
          </div>
          <Callout type="warning">
            When using <strong>Deployed Address</strong> mode, make sure the contract is deployed on the
            configured network (Anvil local or Base Sepolia).
          </Callout>
        </section>

        {/* ─── Analysis ─── */}
        <section id="analysis" className="docs-section">
          <h2>Security Analysis</h2>
          <p>
            After clicking <strong>Run Security Analysis</strong>, the AI agent analyzes the contract
            and produces a structured report with:
          </p>
          <ul className="docs-list">
            <li><strong>Executive Summary</strong> — one-line description of the audit outcome</li>
            <li><strong>Security Score</strong> — 0–100 score based on finding severity</li>
            <li><strong>Severity Breakdown</strong> — counts of Critical, High, Medium, and Low findings</li>
            <li><strong>Detailed Findings</strong> — individual vulnerability cards with descriptions</li>
            <li><strong>Evidence Hashes</strong> — SHA-256 report and metadata hashes for integrity</li>
          </ul>
        </section>

        {/* ─── Findings ─── */}
        <section id="findings" className="docs-section">
          <h2>Findings &amp; Severity</h2>
          <p>
            Each finding is displayed as a <strong>severity-colored expandable card</strong>. Click a
            card to expand it and see the full details.
          </p>
          <Screenshot src="/docs/findings.png" caption="Findings section with severity-colored cards, expandable details, and the Recent Forensic Claims list" />
          <div className="docs-table-wrapper">
            <table className="docs-table">
              <thead>
                <tr>
                  <th>Severity</th>
                  <th>Color</th>
                  <th>Description</th>
                </tr>
              </thead>
              <tbody>
                <tr><td><strong>Critical</strong></td><td style={{ color: "#EA4335" }}>● Red</td><td>Exploitable vulnerabilities with direct fund loss</td></tr>
                <tr><td><strong>High</strong></td><td style={{ color: "#FBBC04" }}>● Yellow</td><td>Significant security risks requiring immediate attention</td></tr>
                <tr><td><strong>Medium</strong></td><td style={{ color: "#4285F4" }}>● Blue</td><td>Notable issues that could become exploitable</td></tr>
                <tr><td><strong>Low</strong></td><td style={{ color: "#34A853" }}>● Green</td><td>Best practice violations and informational items</td></tr>
              </tbody>
            </table>
          </div>
          <Callout type="tip">
            Each finding shows the <strong>category</strong>, <strong>confidence</strong> level, and
            optionally the <strong>affected function name</strong>. Expand a finding to see the full
            impact analysis, recommendation, and source location.
          </Callout>
        </section>

        {/* ─── Publishing ─── */}
        <section id="publishing" className="docs-section">
          <h2>Publishing On-Chain</h2>
          <p>
            Once an audit is complete, you can publish the claim on-chain by staking ETH behind the
            judgment. The staking step transitions the claim from <strong>DRAFT</strong> to{" "}
            <strong>PUBLISHED</strong>.
          </p>
          <h3>Publication Flow</h3>
          <ol className="docs-list">
            <li>Complete the security analysis (claim is in <strong>DRAFT</strong> state)</li>
            <li>Click <strong>Prepare for Publication</strong> in the action panel</li>
            <li>Review the stake amount (default: 0.010 ETH)</li>
            <li>Confirm the transaction — the claim is now <strong>PUBLISHED</strong> on-chain</li>
          </ol>
          <Callout type="important">
            Publishing requires a connected wallet with sufficient ETH for the stake. The stake amount
            is locked until the challenge window closes or a challenge is resolved.
          </Callout>
        </section>

        {/* ─── Challenges ─── */}
        <section id="challenges" className="docs-section">
          <h2>Challenges &amp; Disputes</h2>
          <p>
            Any party can challenge a published claim by posting a <strong>challenge bond</strong> and
            providing counter-evidence (e.g., a PoC exploit or alternative analysis).
          </p>
          <Screenshot src="/docs/disputed.png" caption="Disputed view — active challenges with resolution status and economic details" />
          <h3>Resolution Paths</h3>
          <div className="docs-feature-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
            <div className="docs-feature-card">
              <h4>⚡ Deterministic</h4>
              <p>Challenge evidence is recorded, and executable evidence can provide advisory output before arbiter resolution.</p>
            </div>
            <div className="docs-feature-card">
              <h4>🙋 Manual Review</h4>
              <p>Falls back to qualified human reviewers unless a non-advisory verifier path is introduced.</p>
            </div>
          </div>
          <h3>Outcomes</h3>
          <ul className="docs-list">
            <li><strong>Upheld</strong> — Challenge succeeds. Auditor&apos;s stake is slashed, challenger receives payout.</li>
            <li><strong>Rejected</strong> — Challenge fails. Challenger&apos;s bond is forfeited to the auditor.</li>
          </ul>
        </section>

        {/* ─── Multi-Agent Comparison ─── */}
        <section id="multi-agent" className="docs-section">
          <h2>Multi-Agent Comparison</h2>
          <p>
            The <strong>Agent Comparison</strong> view enables side-by-side analysis of audit claims
            from multiple AI agents on the same smart contract. Each agent may specialize in different
            vulnerability categories — producing intentional <strong>divergence</strong> that highlights
            gaps in coverage and surfaces findings that only certain auditors detect.
          </p>
          <Screenshot src="/docs/agent-comparison.png" caption="Agent Comparison — side-by-side audit lanes with divergence highlighting and agreement matrix" />

          <h3>Key Features</h3>
          <div className="docs-feature-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
            <div className="docs-feature-card">
              <span className="docs-feature-icon">🎯</span>
              <h4>Contract Selector</h4>
              <p>
                Switch between audited contracts using the target contract chips at the top.
                Each chip shows the number of agents that audited that contract.
              </p>
            </div>
            <div className="docs-feature-card">
              <span className="docs-feature-icon">🔍</span>
              <h4>Agent Lanes</h4>
              <p>
                Each agent is displayed in its own lane showing the reputation ring, finding count,
                max severity, and individual finding cards with severity badges.
              </p>
            </div>
            <div className="docs-feature-card">
              <span className="docs-feature-icon">⚡</span>
              <h4>Divergence Badges</h4>
              <p>
                Findings are tagged with agreement ratios (e.g. <strong>4/5</strong> or <strong>3/5</strong>).
                A finding reported by all agents shows <em>All Agree</em>; one reported by only a
                single agent shows <em>Unique</em>.
              </p>
            </div>
            <div className="docs-feature-card">
              <span className="docs-feature-icon">📊</span>
              <h4>Agreement Matrix</h4>
              <p>
                The matrix table at the bottom cross-references every finding against every agent,
                showing checkmarks for agents that reported it and dashes for those that did not.
              </p>
            </div>
          </div>

          <h3>Agent Specializations</h3>
          <p>
            Divergence arises because each agent persona is scoped to a specific set of
            vulnerability detectors:
          </p>
          <div className="docs-table-wrapper">
            <table className="docs-table">
              <thead>
                <tr>
                  <th>Agent</th>
                  <th>Detector Scope</th>
                  <th>Example Behavior</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td><strong>Reentrancy Hawk</strong></td>
                  <td><code>reentrancy</code></td>
                  <td>Finds reentrancy in VulnerableBank but misses access control issues</td>
                </tr>
                <tr>
                  <td><strong>Access Control Sentinel</strong></td>
                  <td><code>access_control</code></td>
                  <td>Finds missing role checks in AdminSetter but ignores unchecked calls</td>
                </tr>
                <tr>
                  <td><strong>Full Spectrum Auditor</strong></td>
                  <td>All detectors</td>
                  <td>Reports every finding across all categories</td>
                </tr>
                <tr>
                  <td><strong>Gemini / OpenAI Deep Analysis</strong></td>
                  <td>All detectors (LLM)</td>
                  <td>Full coverage — mirrors the full spectrum profile</td>
                </tr>
              </tbody>
            </table>
          </div>

          <h3>Running the Multi-Agent Demo</h3>
          <Callout type="tip">
            The multi-agent demo script starts Anvil, deploys contracts, and submits audits from all
            agent personas against all demo fixtures — producing real divergence in one command.
          </Callout>
          <CodeBlock>{`# Run the full multi-agent demo
./scripts/run-multi-agent-demo.sh --skip-watchers

# View results in the web dashboard
cd web && npm run dev
# Navigate to the "Agents" tab in the sidebar`}</CodeBlock>

          <Callout type="info">
            On <strong>Dual Risk Vault</strong>, you will see the Full Spectrum Auditor report 2 findings,
            Access Control Sentinel report 1, and Reentrancy Hawk report 0 — clearly illustrating how
            detector scope produces divergence across agents.
          </Callout>
        </section>

        {/* ─── Views ─── */}
        <section id="views" className="docs-section">
          <h2>Navigation Views</h2>
          <p>
            The sidebar provides 6 views to navigate the audit lifecycle:
          </p>
          <div className="docs-feature-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
            <div className="docs-feature-card">
              <h4>📝 Workbench</h4>
              <p>Primary workspace for submitting contracts and viewing analysis.</p>
            </div>
            <div className="docs-feature-card">
              <h4>✓ Published</h4>
              <p>On-chain claims with executive summaries and related claims.</p>
            </div>
            <div className="docs-feature-card">
              <h4>⚖ Disputed</h4>
              <p>Active challenges, resolution paths, and dispute outcomes.</p>
            </div>
            <div className="docs-feature-card">
              <h4>🤖 Agents</h4>
              <p>Multi-agent comparison view with side-by-side audit lanes and divergence analysis.</p>
            </div>
            <div className="docs-feature-card">
              <h4>🛡 Reputation</h4>
              <p>Auditor trust scores, activity timelines, and reputation metrics.</p>
            </div>
            <div className="docs-feature-card">
              <h4>📦 Archive</h4>
              <p>Historical audit records and past claim data.</p>
            </div>
          </div>
          <Screenshot src="/docs/published.png" caption="Published view — on-chain claims with executive summaries" />
          <Screenshot src="/docs/reputation.png" caption="Reputation view — auditor trust scores and challenge history" />
        </section>

        {/* ─── CLI ─── */}
        <section id="cli" className="docs-section">
          <h2>CLI Agent Workflow</h2>
          <p>
            The audit agent can also be run from the command line for automated pipelines.
          </p>
          <h3>Running an Audit</h3>
          <CodeBlock>{`cd agent
python -m proof_of_audit_agent \\
  --address 0x5FbDB2315678afecb367f032d93F642f64180aa3 \\
  --entry VulnerableBank \\
  --mode demo-fixture`}</CodeBlock>

          <h3>Agent Output</h3>
          <p>The agent produces:</p>
          <ul className="docs-list">
            <li><code>report.json</code> — structured findings with severity, category, confidence</li>
            <li><code>metadata.json</code> — audit context, contract info, evidence hashes</li>
            <li><code>claim.json</code> — the full audit claim ready for on-chain publishing</li>
          </ul>

          <h3>Publishing from CLI</h3>
          <CodeBlock>{`# Publish the claim on-chain (requires funded wallet)
python -m proof_of_audit_agent publish \\
  --claim claim.json \\
  --stake 0.01`}</CodeBlock>

          <h3>Challenging from CLI</h3>
          <CodeBlock>{`# Challenge an existing claim with counter-evidence
python -m proof_of_audit_agent challenge \\
  --audit-id 2 \\
  --evidence ipfs://... \\
  --bond 0.005`}</CodeBlock>
        </section>

        {/* ─── Contracts ─── */}
        <section id="contracts" className="docs-section">
          <h2>Smart Contract Architecture</h2>
          <div className="docs-table-wrapper">
            <table className="docs-table">
              <thead>
                <tr>
                  <th>Contract</th>
                  <th>Purpose</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td><strong>AuditRegistry</strong></td>
                  <td>Stores claims, manages staking, and handles challenge lifecycle</td>
                </tr>
                <tr>
                  <td><strong>ReputationOracle</strong></td>
                  <td>Computes auditor reputation scores from challenge outcomes</td>
                </tr>
              </tbody>
            </table>
          </div>
          <h3>Economic Parameters</h3>
          <div className="docs-table-wrapper">
            <table className="docs-table">
              <thead>
                <tr>
                  <th>Parameter</th>
                  <th>Value</th>
                  <th>Description</th>
                </tr>
              </thead>
              <tbody>
                <tr><td>Stake</td><td><code>0.010 ETH</code></td><td>Minimum stake to publish a claim</td></tr>
                <tr><td>Challenge Bond</td><td><code>0.005 ETH</code></td><td>Counter-party bond to dispute a claim</td></tr>
                <tr><td>Challenge Window</td><td><code>86400s (24h)</code></td><td>Time window for challenges post-publication</td></tr>
              </tbody>
            </table>
          </div>
        </section>

        {/* ─── Troubleshooting ─── */}
        <section id="troubleshooting" className="docs-section">
          <h2>Troubleshooting</h2>

          <h3>Dev Server Not Loading</h3>
          <CodeBlock>{`# Kill existing processes and restart with clean cache
kill $(lsof -ti:3000) 2>/dev/null
cd web && rm -rf .next && npm run dev`}</CodeBlock>

          <h3>Module Not Found Errors</h3>
          <p>
            If you see <code>Cannot find module &apos;./63.js&apos;</code> or similar errors, the <code>.next</code>{" "}
            build cache is stale. Delete it and restart:
          </p>
          <CodeBlock>{`rm -rf web/.next && cd web && npm run dev`}</CodeBlock>

          <h3>Anvil Connection Issues</h3>
          <Callout type="warning">
            Make sure Anvil is running on port 8545 before starting the web app. The E2E script handles
            this automatically, but if running manually, start Anvil first.
          </Callout>
          <CodeBlock>{`# Start Anvil manually
anvil --port 8545 --chain-id 31337`}</CodeBlock>

          <h3>Wallet Connection</h3>
          <p>
            The workbench connects to MetaMask or any injected wallet. For local development,
            import one of Anvil&apos;s test accounts using the private key shown in the Anvil startup log.
          </p>
        </section>

        {/* Footer */}
        <div className="docs-footer">
          <p>
            <strong>Proof-of-Audit</strong> · v0.1.0 ·{" "}
            <a href="https://github.com/akoita/proof-of-audit" target="_blank" rel="noopener noreferrer">
              GitHub Repository
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
