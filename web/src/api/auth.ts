import { useEffect, useState } from "react";
import { ApiError, get } from "./client";
import type { UserOut } from "./types";

/** Where each staff role lands after login. Citizens never log in. */
export function homeFor(role: string): string {
  switch (role) {
    case "WARD_OFFICER":
      return "/officer";
    case "FIELD_TEAM":
      return "/field";
    case "CONTROL_ROOM":
      return "/control";
    default:
      return "/";
  }
}

/** Current session user, or null when logged out. `undefined` while loading. */
export function useMe() {
  const [me, setMe] = useState<UserOut | null | undefined>(undefined);
  useEffect(() => {
    let alive = true;
    get<UserOut>("/auth/me")
      .then((u) => alive && setMe(u))
      .catch((e: unknown) => {
        if (!alive) return;
        // 401 = not logged in; any other failure also means "no usable session".
        if (e instanceof ApiError && e.status !== 401) console.warn("auth/me failed", e);
        setMe(null);
      });
    return () => {
      alive = false;
    };
  }, []);
  return me;
}
