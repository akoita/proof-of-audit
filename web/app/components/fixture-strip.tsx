"use client";

import type { DemoFixture } from "../lib/types";
import { shortenHex } from "../lib/format";

type FixtureStripProps = {
  fixtures: DemoFixture[];
  selectedId: string;
  isLoaded: boolean;
  onSelect: (fixture: DemoFixture) => void;
};

const FIXTURE_ICONS: Record<string, string> = {
  "vulnerable-bank": "🏦",
  "admin-setter": "🔑",
  "clean-vault": "🛡",
  "dual-risk-vault": "⚠️",
  "unchecked-treasury": "💰",
};

export function FixtureStrip({ fixtures, selectedId, isLoaded, onSelect }: FixtureStripProps) {
  return (
    <div className="card" style={{ marginBottom: 0 }}>
      <div className="card-body" style={{ padding: "16px 20px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <h3 style={{ fontSize: "0.88rem", fontWeight: 700, display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: "1rem" }}>🧪</span>
            Demo Fixtures
          </h3>
          <span style={{
            background: isLoaded ? "var(--secondary-container)" : "var(--surface-container-high)",
            color: "white",
            borderRadius: 20,
            padding: "3px 10px",
            fontSize: "0.6rem",
            fontWeight: 600,
          }}>
            {isLoaded ? `${fixtures.length} loaded` : "loading…"}
          </span>
        </div>

        {!isLoaded ? (
          <div style={{ padding: "16px 0", textAlign: "center" }}>
            <p className="muted" style={{ fontSize: "0.78rem" }}>Loading local fixtures and audit activity…</p>
          </div>
        ) : fixtures.length === 0 ? (
          <div style={{ padding: "16px 0", textAlign: "center" }}>
            <p className="muted" style={{ fontSize: "0.78rem" }}>No local demo fixtures detected.</p>
            <code className="mono" style={{ fontSize: "0.65rem", color: "var(--primary)", marginTop: 4, display: "inline-block" }}>
              ./scripts/deploy-demo-fixtures.sh
            </code>
          </div>
        ) : (
          <div style={{
            display: "grid",
            gridTemplateColumns: `repeat(${Math.min(fixtures.length, 5)}, 1fr)`,
            gap: 10,
          }}>
            {fixtures.map((fixture) => {
              const isActive = fixture.id === selectedId;
              const icon = FIXTURE_ICONS[fixture.id] ?? "📄";
              return (
                <button
                  key={fixture.address}
                  type="button"
                  onClick={() => onSelect(fixture)}
                  style={{
                    background: isActive
                      ? "linear-gradient(135deg, var(--primary-container), var(--surface-container-highest))"
                      : "var(--surface-container-high)",
                    border: isActive ? "1px solid var(--primary)" : "1px solid transparent",
                    borderRadius: 10,
                    padding: "12px 14px",
                    cursor: "pointer",
                    textAlign: "left",
                    color: "var(--on-surface)",
                    transition: "all 0.2s",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
                    <span style={{ fontSize: "0.9rem" }}>{icon}</span>
                    <span style={{ fontWeight: 700, fontSize: "0.72rem" }}>
                      {fixture.label}
                    </span>
                  </div>
                  <div className="mono" style={{ fontSize: "0.6rem", color: "var(--primary)", marginBottom: 4 }}>
                    {fixture.entry_contract}
                  </div>
                  <div className="mono" style={{ fontSize: "0.55rem", color: "var(--on-surface-variant)" }}>
                    {shortenHex(fixture.address, 8, 6)}
                  </div>
                  <p style={{
                    fontSize: "0.6rem",
                    color: "var(--on-surface-variant)",
                    marginTop: 6,
                    lineHeight: 1.4,
                    overflow: "hidden",
                    display: "-webkit-box",
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: "vertical",
                  }}>
                    {fixture.note}
                  </p>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
