"use client";

import type { PublicContractConfig } from "../lib/types";

type NavbarProps = {
  config: PublicContractConfig | null;
  onScrollTo: (sectionId: string) => void;
};

export function Navbar({ config, onScrollTo }: NavbarProps) {
  return (
    <nav className="navbar">
      <div style={{ display: "flex", alignItems: "center", gap: 32 }}>
        <div className="navbar-brand">
          <span className="navbar-logo">◈</span>
          <span>Proof of Audit</span>
        </div>
        <div className="navbar-links">
          <button type="button" className="navbar-link" onClick={() => onScrollTo("audit-report")}>
            Explorer
          </button>
          <button type="button" className="navbar-link" onClick={() => onScrollTo("agent-info")}>
            Protocols
          </button>
          <button type="button" className="navbar-link" onClick={() => onScrollTo("fixture-strip")}>
            Governance
          </button>
        </div>
      </div>

      <div className="navbar-actions">
        <div className="navbar-search">
          <span className="search-icon">🔍</span>
          <input type="text" placeholder="Search hash, address..." />
        </div>
        <button type="button" className="navbar-icon-btn">🔔</button>
        <button type="button" className="navbar-icon-btn">⚙</button>
        <button
          type="button"
          className="connect-wallet-btn"
          onClick={() => alert("Wallet connection will be available when the app is deployed on-chain. For now, use demo fixtures to explore the workbench.")}
        >
          Connect Wallet
        </button>
      </div>
    </nav>
  );
}
