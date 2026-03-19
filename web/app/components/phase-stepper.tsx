"use client";

import type { AuditRecord } from "../lib/types";

type PhaseStepperProps = {
  audit: AuditRecord | null;
};

const PHASES = [
  { key: "submit", label: "Submit", icon: "1" },
  { key: "audit", label: "Audit", icon: "2" },
  { key: "publish", label: "Publish", icon: "3" },
  { key: "challenge", label: "Challenge", icon: "4" },
] as const;

function resolvePhase(audit: AuditRecord | null): number {
  if (!audit) return -1;
  if (audit.status === "resolved") return 4;
  if (audit.challenge) return 3;
  if (audit.onchain) return 2;
  if (audit.status === "draft") return 1;
  return 0;
}

export function PhaseStepper({ audit }: PhaseStepperProps) {
  const currentPhase = resolvePhase(audit);

  return (
    <div className="phase-stepper">
      {PHASES.map((phase, index) => {
        const completed = index < currentPhase;
        const active = index === currentPhase;
        return (
          <div
            key={phase.key}
            className="phase-step"
            data-completed={completed}
            data-active={active}
          >
            <div className="phase-icon">
              {completed ? (
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M3 8.5L6.5 12L13 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              ) : (
                <span>{phase.icon}</span>
              )}
            </div>
            <span className="phase-label">{phase.label}</span>
            {index < PHASES.length - 1 && <div className="phase-connector" />}
          </div>
        );
      })}
    </div>
  );
}
