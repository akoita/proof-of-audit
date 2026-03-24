"use client";

import { useEffect, useRef, useState } from "react";
import type { PublicContractConfig } from "../lib/types";
import { shortenHex } from "../lib/format";

type NavbarProps = {
  config: PublicContractConfig | null;
  onScrollTo: (sectionId: string) => void;
};

type EthereumRequestArguments = {
  method: string;
  params?: unknown[] | Record<string, unknown>;
};

type InjectedEthereumProvider = {
  request: (args: EthereumRequestArguments) => Promise<unknown>;
  on?: (event: string, listener: (...args: unknown[]) => void) => void;
  removeListener?: (event: string, listener: (...args: unknown[]) => void) => void;
};

const MANUAL_DISCONNECT_KEY = "poa.wallet.manualDisconnect";

function getInjectedProvider(): InjectedEthereumProvider | null {
  if (typeof window === "undefined") return null;
  const candidate = (window as Window & { ethereum?: InjectedEthereumProvider }).ethereum;
  if (!candidate || typeof candidate.request !== "function") {
    return null;
  }
  return candidate;
}

function parseChainId(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) return null;
    const parsed = trimmed.startsWith("0x") ? Number.parseInt(trimmed, 16) : Number.parseInt(trimmed, 10);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function targetChainHex(chainId: number): string {
  return `0x${chainId.toString(16)}`;
}

export function Navbar({ config, onScrollTo }: NavbarProps) {
  const [walletAddress, setWalletAddress] = useState<string | null>(null);
  const [walletChainId, setWalletChainId] = useState<number | null>(null);
  const [walletError, setWalletError] = useState<string | null>(null);
  const [isConnecting, setIsConnecting] = useState(false);
  const manualDisconnectRef = useRef(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    manualDisconnectRef.current = window.sessionStorage.getItem(MANUAL_DISCONNECT_KEY) === "1";

    const provider = getInjectedProvider();

    if (!provider) {
      setWalletAddress(null);
      setWalletChainId(null);
      return;
    }

    const syncWalletState = async () => {
      try {
        const [accountsResult, chainIdResult] = await Promise.all([
          provider.request({ method: "eth_accounts" }),
          provider.request({ method: "eth_chainId" }),
        ]);
        const accounts = Array.isArray(accountsResult) ? accountsResult : [];
        const nextAddress = accounts.find((value): value is string => typeof value === "string") ?? null;
        setWalletChainId(parseChainId(chainIdResult));
        setWalletAddress(manualDisconnectRef.current ? null : nextAddress);
      } catch (error) {
        setWalletError(error instanceof Error ? error.message : "Failed to read wallet state.");
      }
    };

    const handleAccountsChanged = (accounts: unknown) => {
      if (!Array.isArray(accounts) || accounts.length === 0) {
        setWalletAddress(null);
        setWalletError(null);
        return;
      }
      if (manualDisconnectRef.current) return;
      const nextAddress = accounts.find((value): value is string => typeof value === "string") ?? null;
      setWalletAddress(nextAddress);
      setWalletError(null);
    };

    const handleChainChanged = (chainId: unknown) => {
      setWalletChainId(parseChainId(chainId));
      setWalletError(null);
    };

    void syncWalletState();
    provider.on?.("accountsChanged", handleAccountsChanged);
    provider.on?.("chainChanged", handleChainChanged);

    return () => {
      provider.removeListener?.("accountsChanged", handleAccountsChanged);
      provider.removeListener?.("chainChanged", handleChainChanged);
    };
  }, []);

  const isWrongNetwork =
    walletAddress !== null &&
    walletChainId !== null &&
    config !== null &&
    walletChainId !== config.chain_id;

  async function handleConnectWallet() {
    const provider = getInjectedProvider();
    if (!provider) {
      setWalletError("No injected wallet detected. Open the app in a wallet-enabled browser.");
      return;
    }

    setIsConnecting(true);
    setWalletError(null);
    manualDisconnectRef.current = false;
    window.sessionStorage.removeItem(MANUAL_DISCONNECT_KEY);

    try {
      const [accountsResult, chainIdResult] = await Promise.all([
        provider.request({ method: "eth_requestAccounts" }),
        provider.request({ method: "eth_chainId" }),
      ]);
      const accounts = Array.isArray(accountsResult) ? accountsResult : [];
      const nextAddress = accounts.find((value): value is string => typeof value === "string") ?? null;
      setWalletAddress(nextAddress);
      setWalletChainId(parseChainId(chainIdResult));
      if (!nextAddress) {
        setWalletError("Wallet did not return an account.");
      }
    } catch (error) {
      setWalletError(error instanceof Error ? error.message : "Wallet connection was rejected.");
    } finally {
      setIsConnecting(false);
    }
  }

  async function handleSwitchNetwork() {
    if (!config) return;
    const provider = getInjectedProvider();
    if (!provider) {
      setWalletError("No injected wallet detected. Open the app in a wallet-enabled browser.");
      return;
    }

    setWalletError(null);
    try {
      await provider.request({
        method: "wallet_switchEthereumChain",
        params: [{ chainId: targetChainHex(config.chain_id) }],
      });
      const chainIdResult = await provider.request({ method: "eth_chainId" });
      setWalletChainId(parseChainId(chainIdResult));
    } catch (error) {
      setWalletError(
        error instanceof Error
          ? error.message
          : `Failed to switch wallet to chain ${config.chain_id}.`,
      );
    }
  }

  function handleDisconnectWallet() {
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem(MANUAL_DISCONNECT_KEY, "1");
    }
    manualDisconnectRef.current = true;
    setWalletAddress(null);
    setWalletError(null);
  }

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
        <div className="wallet-actions">
          {walletAddress ? (
            <>
              <div
                className={`wallet-chip ${isWrongNetwork ? "wallet-chip-warning" : ""}`}
                data-testid="wallet-address-chip"
              >
                <span className="wallet-chip-address">{shortenHex(walletAddress, 8, 6)}</span>
                <span className="wallet-chip-network">
                  {walletChainId !== null ? `Chain ${walletChainId}` : "Network unknown"}
                </span>
              </div>
              {isWrongNetwork ? (
                <button
                  type="button"
                  className="connect-wallet-btn"
                  onClick={() => void handleSwitchNetwork()}
                  data-testid="switch-wallet-network-btn"
                >
                  Wrong Network
                </button>
              ) : (
                <button
                  type="button"
                  className="wallet-disconnect-btn"
                  onClick={handleDisconnectWallet}
                  data-testid="disconnect-wallet-btn"
                >
                  Disconnect
                </button>
              )}
            </>
          ) : (
            <button
              type="button"
              className="connect-wallet-btn"
              onClick={() => void handleConnectWallet()}
              disabled={isConnecting}
              data-testid="connect-wallet-btn"
            >
              {isConnecting ? "Connecting..." : "Connect Wallet"}
            </button>
          )}
          {walletError ? (
            <p className="wallet-inline-error" role="status" aria-live="polite">
              {walletError}
            </p>
          ) : null}
        </div>
      </div>
    </nav>
  );
}
