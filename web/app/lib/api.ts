const DEFAULT_API_BASE_URL = "http://127.0.0.1:8080";

type RuntimeConfigPayload = {
  apiBaseUrl?: string | null;
};

let apiBaseUrlPromise: Promise<string> | null = null;

function normalizeApiBaseUrl(value?: string | null): string {
  const trimmed = value?.trim();
  if (!trimmed) {
    return DEFAULT_API_BASE_URL;
  }
  return trimmed.replace(/\/+$/, "");
}

async function loadApiBaseUrl(): Promise<string> {
  if (typeof window === "undefined") {
    return normalizeApiBaseUrl(
      process.env.PROOF_OF_AUDIT_API_URL ??
        process.env.NEXT_PUBLIC_PROOF_OF_AUDIT_API_URL,
    );
  }

  const response = await fetch("/api/runtime-config", { cache: "no-store" });
  if (!response.ok) {
    throw new Error("Failed to load runtime API configuration");
  }

  const payload = (await response.json()) as RuntimeConfigPayload;
  return normalizeApiBaseUrl(payload.apiBaseUrl);
}

async function resolveApiBaseUrl(): Promise<string> {
  apiBaseUrlPromise ??= loadApiBaseUrl().catch((error) => {
    apiBaseUrlPromise = null;
    throw error;
  });
  return apiBaseUrlPromise;
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const apiBaseUrl = await resolveApiBaseUrl();
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  const payload = (await response.json()) as T & {
    error?: string;
    message?: string;
  };

  if (!response.ok) {
    throw new Error(payload.message ?? payload.error ?? "Request failed");
  }

  return payload;
}
