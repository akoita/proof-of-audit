"use client";

import type { PublicContractConfig } from "../lib/types";
import { shortenHex } from "../lib/format";

type NavbarProps = {
  config: PublicContractConfig | null;
};

export function Navbar({ config }: NavbarProps) {
  return (
    <nav className="navbar">
      <div className="navbar-brand">
        <span className="navbar-logo">◈</span>
        <span className="navbar-title">Proof of Audit</span>
      </div>
      <div className="navbar-meta">
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
