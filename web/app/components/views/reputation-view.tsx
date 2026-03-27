"use client";

import type { AuditRecord, AuditorServiceRecord, PublicContractConfig } from "../../lib/types";
import { shortenHex, formatEth, formatIdentitySource, formatValidationSource, relativeTimeLabel, titleCase } from "../../lib/format";

type ReputationViewProps = {
  config: PublicContractConfig | null;
  audits: AuditRecord[];
  auditorService: AuditorServiceRecord | null;
};

export function ReputationView({ config, audits, auditorService }: ReputationViewProps) {
  const reputation = auditorService?.reputation ?? config?.auditor?.reputation ?? null;
  const agentName = auditorService?.name ?? config?.auditor?.name ?? "Auditor unavailable";
  const agentVersion = config?.auditor?.version ?? "Unavailable";
  const agentVersionLabel = agentVersion === "Unavailable" ? agentVersion : `v${agentVersion}`;
  const agentAddress = config?.contract_address ?? null;
  const totalClaims = audits.length;
  const publishedCount = audits.filter((a) => a.onchain).length;
  const openChallenges = audits.filter((a) => a.status === "challenged").length;
  const resolvedCount = audits.filter((a) => a.status === "resolved").length;
  const totalStakeWei = audits.reduce((sum, audit) => sum + (audit.onchain?.stake_wei ?? 0), 0);
  const lastClaimAt = audits[0]?.created_at ?? null;
  const trustScore = reputation?.score ?? null;
  const trustBand = reputation?.band ?? null;
  const opennessScore = reputation?.challenge_openness_score ?? null;
  const opennessBand = reputation?.challenge_openness_band ?? null;
  const accuracyScore = reputation?.challenge_accuracy_score ?? null;
  const accuracyBand = reputation?.challenge_accuracy_band ?? null;
  const circumference = 2 * Math.PI * 42;
  const dashArray =
    trustScore === null ? `0 ${circumference}` : `${(trustScore / 100) * circumference} ${circumference}`;
  const activityBuckets = Array.from({ length: 6 }, (_, offset) => {
    const date = new Date();
    date.setUTCDate(1);
    date.setUTCHours(0, 0, 0, 0);
    date.setUTCMonth(date.getUTCMonth() - (5 - offset));
    const key = `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}`;
    return {
      key,
      label: new Intl.DateTimeFormat("en", { month: "short" }).format(date),
      claims: 0,
      challenges: 0,
    };
  });
  const bucketMap = new Map(activityBuckets.map((bucket) => [bucket.key, bucket]));
  for (const audit of audits) {
    const created = new Date(audit.created_at);
    if (!Number.isNaN(created.getTime())) {
      const key = `${created.getUTCFullYear()}-${String(created.getUTCMonth() + 1).padStart(2, "0")}`;
      const bucket = bucketMap.get(key);
      if (bucket) bucket.claims += 1;
    }
    if (audit.challenge?.submitted_at) {
      const challenged = new Date(audit.challenge.submitted_at);
      if (!Number.isNaN(challenged.getTime())) {
        const key = `${challenged.getUTCFullYear()}-${String(challenged.getUTCMonth() + 1).padStart(2, "0")}`;
        const bucket = bucketMap.get(key);
        if (bucket) bucket.challenges += 1;
      }
    }
  }
  const maxVal = Math.max(...activityBuckets.map((bucket) => Math.max(bucket.claims, bucket.challenges)), 1);

  return (
    <div className="view-reputation">
      {/* ── Profile Header ── */}
      <div className="reputation-header">
        <div className="reputation-profile">
          <div className="reputation-avatar">
            <div className="avatar-large">{agentName.charAt(0).toUpperCase()}</div>
            <span className="verified-badge">{config?.contract_address ? "REGISTERED AUDITOR" : "AUDITOR PROFILE"}</span>
          </div>
          <div className="reputation-bio">
            <h1 style={{ fontSize: "1.5rem", fontWeight: 800 }}>
              {agentName}
              <span className="mono" style={{ fontSize: "0.7rem", marginLeft: 10, color: "var(--on-surface-variant)" }}>
                {agentAddress ? shortenHex(agentAddress, 6, 4) : "Unavailable"}
              </span>
              <span className="mono" style={{ fontSize: "0.7rem", marginLeft: 10, color: "var(--on-surface-variant)" }}>
                {agentVersionLabel}
              </span>
            </h1>
            <p className="muted" style={{ fontSize: "0.82rem", marginTop: 6, maxWidth: 500, lineHeight: 1.6 }}>
              {config?.auditor?.description ?? "Auditor profile metadata is not available for this deployment."}
            </p>
            <div style={{ display: "flex", gap: 16, marginTop: 10 }}>
              <span className="pill" style={{ fontSize: "0.65rem" }}>
                Identity: {formatIdentitySource(auditorService?.identity_source)}
              </span>
              <span className="pill" style={{ fontSize: "0.65rem" }}>
                Validation: {formatValidationSource(auditorService?.validation_source)}
              </span>
            </div>
          </div>
        </div>
        <div className="trust-score-large">
          <div className="score-ring-large">
            <svg viewBox="0 0 96 96">
              <circle className="ring-bg" cx="48" cy="48" r="42" />
              <circle
                className="ring-fill"
                cx="48" cy="48" r="42"
                strokeDasharray={dashArray}
                transform="rotate(-90 48 48)"
                style={{ stroke: "var(--secondary)" }}
              />
            </svg>
            <div className="score-number-large">
              <strong>{trustScore ?? "—"}</strong>
            </div>
          </div>
          <div style={{ fontSize: "0.65rem", color: "var(--on-surface-variant)", textAlign: "center", marginTop: 4 }}>
            {trustBand ? `${titleCase(trustBand)} reputation band` : "Reputation score unavailable"}
          </div>
        </div>
      </div>

      {/* ── Stats Banner ── */}
      <div className="reputation-stats">
        <div className="stat-card">
          <div className="stat-big-value">{totalClaims}</div>
          <div className="stat-big-label">TOTAL CLAIMS</div>
          <div className="muted" style={{ fontSize: "0.6rem", marginTop: 4 }}>
            {lastClaimAt ? `Last claim ${relativeTimeLabel(lastClaimAt)}` : "No claims yet"}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-big-value">{formatEth(totalStakeWei)}</div>
          <div className="stat-big-label">TOTAL STAKE LOCKED</div>
          <div className="muted" style={{ fontSize: "0.6rem", marginTop: 4 }}>
            Across {publishedCount} published claims
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-big-value">{openChallenges}</div>
          <div className="stat-big-label">OPEN CHALLENGES</div>
          <div className="muted" style={{ fontSize: "0.6rem", marginTop: 4 }}>
            {resolvedCount} resolved
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-big-value">
            {reputation
              ? `${reputation.admissible_challenge_rejected_count}/${reputation.admissible_resolved_challenge_count}`
              : `${resolvedCount}`}
          </div>
          <div className="stat-big-label">DISPUTE RESOLUTION</div>
          <div className="muted" style={{ fontSize: "0.6rem", marginTop: 4 }}>
            {reputation ? "Rejected / admissible resolved challenges" : "Historical challenge data unavailable"}
          </div>
        </div>
      </div>

      {/* ── Activity Timeline + Peer Alignment ── */}
      <div className="reputation-charts">
        <div className="card" style={{ flex: 2 }}>
          <div className="card-body">
            <h3 style={{ fontSize: "0.95rem", fontWeight: 700, display: "flex", alignItems: "center", gap: 8 }}>
              <span>📊</span> Audit Activity Timeline
              <span style={{ marginLeft: "auto", display: "flex", gap: 10, fontSize: "0.6rem" }}>
                <span style={{ display: "flex", alignItems: "center", gap: 4 }}><span style={{ width: 8, height: 8, borderRadius: 2, background: "var(--secondary)", display: "inline-block" }} /> Claims</span>
                <span style={{ display: "flex", alignItems: "center", gap: 4 }}><span style={{ width: 8, height: 8, borderRadius: 2, background: "var(--error)", display: "inline-block" }} /> Challenges</span>
              </span>
            </h3>
            <div className="bar-chart" style={{ marginTop: 16 }}>
              {activityBuckets.map((bucket) => (
                <div key={bucket.key} className="bar-group">
                  <div className="bar-container">
                    <div className="bar bar-success" style={{ height: `${(bucket.claims / maxVal) * 100}%` }} />
                    {bucket.challenges > 0 ? (
                      <div className="bar bar-dispute" style={{ height: `${(bucket.challenges / maxVal) * 100}%` }} />
                    ) : null}
                  </div>
                  <div className="bar-label">{bucket.label}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="card" style={{ flex: 1 }}>
          <div className="card-body">
            <h3 style={{ fontSize: "0.95rem", fontWeight: 700 }}>Reputation Details</h3>

            <div style={{ marginTop: 16 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.72rem", marginBottom: 6 }}>
                <span className="section-label">OPENNESS SCORE</span>
                <span style={{ color: "var(--secondary)", fontWeight: 600 }}>
                  {opennessScore !== null
                    ? `${opennessScore}/100 ${titleCase(opennessBand ?? "provisional")}`
                    : "Unavailable"}
                </span>
              </div>
            </div>

            <div style={{ marginTop: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.72rem", marginBottom: 6 }}>
                <span className="section-label">ACCURACY SCORE</span>
                <span style={{ color: "var(--primary)", fontWeight: 600 }}>
                  {accuracyScore !== null
                    ? `${accuracyScore}/100 ${titleCase(accuracyBand ?? "provisional")}`
                    : "Unavailable"}
                </span>
              </div>
            </div>

            <div style={{ marginTop: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.72rem", marginBottom: 6 }}>
                <span className="section-label">REPUTATION BAND</span>
                <span style={{ color: "var(--secondary)", fontWeight: 600 }}>
                  {trustBand ? titleCase(trustBand) : "Unavailable"}
                </span>
              </div>
            </div>

            <div style={{ marginTop: 20 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.72rem", marginBottom: 6 }}>
                <span className="section-label">INADMISSIBLE CHALLENGES</span>
                <span style={{ color: "var(--tertiary)", fontWeight: 600 }}>
                  {reputation?.inadmissible_challenge_count ?? "Unavailable"}
                </span>
              </div>
            </div>

            <div style={{ marginTop: 20 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.72rem", marginBottom: 6 }}>
                <span className="section-label">LAST RESOLUTION</span>
                <span style={{ color: "var(--primary)", fontWeight: 600 }}>
                  {reputation?.last_resolved_at ? relativeTimeLabel(reputation.last_resolved_at) : "Unavailable"}
                </span>
              </div>
            </div>

            <p className="muted" style={{ fontSize: "0.7rem", marginTop: 20, lineHeight: 1.6 }}>
              {reputation?.formula ?? "The backend did not provide a published reputation formula for this deployment."}
            </p>
            <p className="muted" style={{ fontSize: "0.7rem", marginTop: 12, lineHeight: 1.6 }}>
              {reputation?.challenge_openness_formula ?? "The backend did not provide an openness formula for this deployment."}
            </p>
            <p className="muted" style={{ fontSize: "0.7rem", marginTop: 12, lineHeight: 1.6 }}>
              {reputation?.challenge_accuracy_formula ?? "The backend did not provide an accuracy formula for this deployment."}
            </p>
          </div>
        </div>
      </div>

      {/* ── Recent Forensic Claims ── */}
      <div className="card" style={{ marginTop: 20 }}>
        <div className="card-body">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h3 style={{ fontSize: "1rem", fontWeight: 700 }}>Recent Forensic Claims</h3>
            <span className="muted" style={{ fontSize: "0.65rem" }}>
              {publishedCount} published claims loaded
            </span>
          </div>
          <div className="forensic-table" style={{ marginTop: 16 }}>
            {audits.slice(0, 5).map((a) => {
              const maxSev = a.report.max_severity;
              const sevLabel = maxSev >= 4 ? "CRITICAL" : maxSev >= 3 ? "HIGH" : maxSev >= 2 ? "MEDIUM" : "LOW";
              const sevClass = maxSev >= 4 ? "badge-challenged" : maxSev >= 3 ? "badge-draft" : maxSev >= 2 ? "badge-resolved" : "badge-published";
              return (
                <div key={a.id} className="forensic-row">
                  <div style={{ display: "flex", alignItems: "center", gap: 12, flex: 2 }}>
                    <span style={{ width: 8, height: 8, borderRadius: "50%", background: a.status === "resolved" ? "var(--secondary)" : "var(--tertiary)" }} />
                    <div>
                      <div style={{ fontWeight: 600, fontSize: "0.82rem" }}>
                        {a.report.summary || shortenHex(a.contract_address, 8, 6)}
                      </div>
                      <div className="mono" style={{ fontSize: "0.6rem", color: "var(--on-surface-variant)" }}>
                        CLAIM-ID: #{a.id.slice(0, 8).toUpperCase()}
                      </div>
                    </div>
                  </div>
                  <div style={{ flex: 1, textAlign: "center" }}>
                    <div className="section-label" style={{ fontSize: "0.55rem" }}>IMPACT</div>
                    <span className={`badge ${sevClass}`} style={{ fontSize: "0.55rem" }}>{sevLabel}</span>
                  </div>
                  <div style={{ flex: 1, textAlign: "center" }}>
                    <div className="section-label" style={{ fontSize: "0.55rem" }}>STATUS</div>
                    <span style={{ fontSize: "0.7rem" }}>● {titleCase(a.status)}</span>
                  </div>
                  <div style={{ flex: 1, textAlign: "right" }}>
                  <div style={{ fontSize: "0.82rem", fontWeight: 600 }}>
                      {a.onchain ? `${(a.onchain.stake_wei / 1e18).toFixed(2)} ETH` : "—"}
                    </div>
                    <div className="muted" style={{ fontSize: "0.55rem" }}>
                      {a.challenge?.payout_wei ? `Payout ${formatEth(a.challenge.payout_wei)}` : titleCase(a.status)}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
