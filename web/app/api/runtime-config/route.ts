import { NextResponse } from "next/server";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8080";

export const dynamic = "force-dynamic";

function resolveApiBaseUrl(): string {
  const value =
    process.env.PROOF_OF_AUDIT_API_URL ??
    process.env.NEXT_PUBLIC_PROOF_OF_AUDIT_API_URL ??
    DEFAULT_API_BASE_URL;

  const normalized = value.trim().replace(/\/+$/, "");
  return normalized || DEFAULT_API_BASE_URL;
}

export function GET() {
  return NextResponse.json(
    { apiBaseUrl: resolveApiBaseUrl() },
    {
      headers: {
        "Cache-Control": "no-store, max-age=0",
      },
    },
  );
}
