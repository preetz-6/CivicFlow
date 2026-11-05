/**
 * Fetch client for /api/v1. Cookie session, so credentials are always included.
 * With VITE_USE_MOCKS=1 (`npm run dev:mock`) requests are answered by ./mock.ts
 * instead, for endpoints Machine A has not shipped yet.
 */
export const API_BASE = "/api/v1";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public body?: unknown,
  ) {
    super(message);
  }
}

const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === "1";

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (USE_MOCKS) {
    const { mockFetch } = await import("./mock");
    return mockFetch<T>(path, init);
  }
  const isForm = init.body instanceof FormData;
  const res = await fetch(API_BASE + path, {
    credentials: "include",
    ...init,
    headers: {
      Accept: "application/json",
      ...(init.body && !isForm ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
  });
  if (!res.ok) {
    let body: unknown;
    try {
      body = await res.json();
    } catch {
      body = undefined;
    }
    const detail = (body as { detail?: unknown } | undefined)?.detail;
    throw new ApiError(res.status, typeof detail === "string" ? detail : res.statusText, body);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const get = <T>(path: string) => api<T>(path);
export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, {
    method: "POST",
    body: body instanceof FormData ? body : body === undefined ? undefined : JSON.stringify(body),
  });
