export const API_BASE_URL =
  process.env.NEXT_PUBLIC_PROOF_OF_AUDIT_API_URL ?? "http://127.0.0.1:8080";

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
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
