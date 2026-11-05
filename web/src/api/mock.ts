/**
 * Mock answers for `npm run dev:mock` (VITE_USE_MOCKS=1). Only for endpoints
 * Machine A has not shipped. Shapes follow BUILD_PLAN §10 and ./pending.ts.
 */
import { ApiError } from "./client";
import type { TickerItem, UserOut } from "./pending";

const ticker: TickerItem[] = [
  {
    id: "N-1",
    text: "Monsoon preparedness: storm water drain desilting in Kengeri and RR Nagar wards till 30 Nov.",
    published_at: "2026-11-04T10:00:00+05:30",
  },
  {
    id: "N-2",
    text: "Streetlight complaints can now be tracked with the Grievance No. on the Track Grievance page.",
    published_at: "2026-11-03T09:00:00+05:30",
  },
];

let session: UserOut | null = null;

export async function mockFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const [route] = path.split("?");
  await new Promise((r) => setTimeout(r, 150));

  if (method === "GET" && route === "/public/ticker") return ticker as T;
  if (method === "GET" && route === "/auth/me") {
    if (!session) throw new ApiError(401, "Not logged in");
    return session as T;
  }
  if (method === "POST" && route === "/auth/logout") {
    session = null;
    return { ok: true } as T;
  }
  throw new ApiError(404, `No mock for ${method} ${route}`);
}
