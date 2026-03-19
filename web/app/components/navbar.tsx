"use client";

import { useState } from "react";
import type { PublicContractConfig } from "../lib/types";
import { shortenHex } from "../lib/format";

type NavbarProps = {
  config: PublicContractConfig | null;
};

const TABS = [
  { id: "dashboard", label: "Dashboard", target: "dashboard-top" },
  { id: "audit",     label: "Audit",     target: "audit-section" },
  { id: "claims",    label: "Claims",    target: "claims-section" },
  { id: "explorer",  label: "Explorer",  target: "explorer-section" },
] as const;

export function Navbar({ config }: NavbarProps) {
  const [activeTab, setActiveTab] = useState("dashboard");

  function handleTab(tab: typeof TABS[number]) {
    setActiveTab(tab.id);
    const el = document.getElementById(tab.target);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  return (
    <nav className="navbar">
      <div className="navbar-brand">
        <span className="navbar-logo">◈</span>
        <span className="navbar-title">Proof of Audit</span>
        <div className="navbar-tabs">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              className="navbar-tab"
              data-active={activeTab === tab.id}
              onClick={() => handleTab(tab)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>
      <div className="navbar-meta">
        <button className="wallet-btn" type="button">Wallet Connect</button>
        {config?.contract_address ? (
          <span className="network-badge" data-tone="confirmed">
            <span className="network-dot" />
            {config.network} · {config.chain_id}
          </span>
        ) : (
          <span className="network-badge" data-tone="neutral">
            <span className="network-dot network-dot-dim" />
            Connecting…
          </span>
        )}
        {config?.contract_address ? (
          <span className="contract-pill" title={config.contract_address}>
            {shortenHex(config.contract_address, 6, 4)}
          </span>
        ) : null}
      </div>
    </nav>
  );
}
