"use client";

import type { DemoFixture } from "../lib/types";
import { shortenHex } from "../lib/format";

type FixtureStripProps = {
  fixtures: DemoFixture[];
  selectedId: string;
  isLoaded: boolean;
  onSelect: (fixture: DemoFixture) => void;
};

export function FixtureStrip({ fixtures, selectedId, isLoaded, onSelect }: FixtureStripProps) {
  return (
    <section className="fixture-section">
      <div className="section-heading section-heading-wide">
        <div>
          <p>Demo fixtures</p>
          <strong className="section-subtitle">
            Pick a live contract to drive the trust flow
          </strong>
        </div>
        <span className="count-badge">{isLoaded ? `${fixtures.length} loaded` : "loading"}</span>
      </div>
      {!isLoaded ? (
        <article className="benchmark-empty">
          <p>Loading local fixtures and audit activity.</p>
        </article>
      ) : fixtures.length === 0 ? (
        <article className="benchmark-empty">
          <p>No local demo fixtures detected.</p>
          <span>
            Run <code>./scripts/deploy-demo-fixtures.sh</code> after local deployment.
          </span>
        </article>
      ) : (
        <div className="benchmark-strip">
          {fixtures.map((fixture) => (
            <button
              key={fixture.address}
              className="benchmark-card"
              data-selected={fixture.id === selectedId}
              type="button"
              onClick={() => onSelect(fixture)}
            >
              <div className="benchmark-card-topline">
                <span>{fixture.label}</span>
                <em>{fixture.entry_contract}</em>
              </div>
              <strong title={fixture.address}>
                {shortenHex(fixture.address, 8, 6)}
              </strong>
              <p>{fixture.note}</p>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
