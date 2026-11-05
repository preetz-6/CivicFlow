import { useEffect, useState } from "react";
import { get } from "./client";
import type { Category } from "./types";

let categoriesCache: Promise<Category[]> | null = null;

/** GET /public/categories, fetched once per page load. */
export function useCategories(): Category[] {
  const [cats, setCats] = useState<Category[]>([]);
  useEffect(() => {
    categoriesCache ??= get<Category[]>("/public/categories").catch((e) => {
      categoriesCache = null;
      throw e;
    });
    let alive = true;
    categoriesCache.then((c) => alive && setCats(c)).catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);
  return cats;
}

/** Date and time in Indian format, e.g. "05 Nov 2026, 10:45 am". */
export function fmtDateTime(iso: string | null | undefined, lang = "en"): string {
  if (!iso) return "-";
  return new Date(iso).toLocaleString(lang === "kn" ? "kn-IN" : "en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Kolkata",
  });
}

export function fmtDate(iso: string | null | undefined, lang = "en"): string {
  if (!iso) return "-";
  return new Date(iso).toLocaleDateString(lang === "kn" ? "kn-IN" : "en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "Asia/Kolkata",
  });
}

/** Session storage key for an acknowledgement slip (never put the tracking code in the URL). */
export const ackKey = (no: string) => `cf.ack.${no}`;
