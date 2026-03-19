"use client";

import type { PublicContractConfig } from "../lib/types";

type NavbarProps = {
  config: PublicContractConfig | null;
};

export function Navbar({ config }: NavbarProps) {
  return (
    <nav className="navbar">
      <div style={{ display: "flex", alignItems: "center", gap: 32 }}>
        <div className="navbar-brand">
          <span className="navbar-logo">◈</span>
          <span>Proof of Audit</span>
        </div>
        <div className="navbar-links">
          <button type="button" className="navbar-link">Explorer</button>
          <button type="button" className="navbar-link">Protocols</button>
          <button type="button" className="navbar-link">Governance</button>
        </div>
      </div>

      <div className="navbar-actions">
        <div className="navbar-search">
          <span className="search-icon">🔍</span>
          <input type="text" placeholder="Search hash, address..." />
        </div>
        <button type="button" className="navbar-icon-btn">🔔</button>
        <button type="button" className="navbar-icon-btn">⚙</button>
        <button type="button" className="connect-wallet-btn">Connect Wallet</button>
      </div>
    </nav>
  );
}
