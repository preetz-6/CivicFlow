import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { get } from "../api/client";
import l from "./lively.module.css";

const reduced = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** A number that counts up to its value (and animates again when the value changes). */
export function CountUp({ value, suffix = "", locale = "en-IN" }: { value: number; suffix?: string; locale?: string }) {
  const [shown, setShown] = useState(reduced() ? value : 0);
  const from = useRef(0);
  useEffect(() => {
    if (reduced()) {
      setShown(value);
      return;
    }
    const start = performance.now();
    const a = from.current;
    let raf = 0;
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / 900);
      const eased = 1 - Math.pow(1 - p, 3);
      setShown(a + (value - a) * eased);
      if (p < 1) raf = requestAnimationFrame(tick);
      else from.current = value;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value]);
  const decimals = Number.isInteger(value) ? 0 : 1;
  return (
    <>
      {shown.toLocaleString(locale, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}
      {suffix}
    </>
  );
}

/** GET /public/agent-activity */
export interface Activity {
  last_hour: number;
  latest: { id: number; agent: string; agent_label: string; subject_id: string | null; text: string; at: string; ago_s: number; autonomous: boolean }[];
}

export function useActivity(everyMs = 5000): Activity | null {
  const [a, setA] = useState<Activity | null>(null);
  useEffect(() => {
    let alive = true;
    const load = () =>
      get<Activity>("/public/agent-activity?limit=4")
        .then((x) => alive && setA(x))
        .catch(() => undefined);
    load();
    const id = window.setInterval(load, everyMs);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, [everyMs]);
  return a;
}

const AGENT_COLOR: Record<string, string> = {
  investigator: "var(--navy)",
  auditor: "var(--purple)",
  sensing: "var(--teal)",
  followup: "var(--amber)",
  surge: "var(--danger)",
};

const ago = (s: number) => {
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
};

/** Home page "Live now" card: pulsing dot, last-hour count, the latest agent actions. */
export function LiveNow() {
  const { t } = useTranslation();
  const a = useActivity();
  return (
    <section className={l.live} aria-labelledby="live-h" aria-live="polite">
      <h2 id="live-h" className={l.liveTitle}>
        <span className="live-dot" aria-hidden="true" /> {t("live.title")}
      </h2>
      <p className={l.liveCount}>{a ? t("live.hour", { n: a.last_hour }) : "…"}</p>
      {a && a.latest.length === 0 ? <p className={l.muted}>{t("live.empty")}</p> : null}
      <ul className={l.liveList}>
        {a?.latest.map((x) => (
          <li key={x.id} className={l.liveItem}>
            <span className={l.agentChip} style={{ background: AGENT_COLOR[x.agent] ?? "var(--navy)" }}>
              {x.agent_label}
            </span>
            <span className={l.liveText}>{x.text}</span>
            <span className={l.muted}>
              {ago(x.ago_s)}
              {x.autonomous ? ` · ${t("live.auto")}` : ""}
            </span>
          </li>
        ))}
      </ul>
      <Link to="/agents" className={l.liveLink}>
        {t("live.see")} →
      </Link>
    </section>
  );
}

/** Staff screens: a small notice slides in whenever an agent finishes something. */
export function AgentToasts() {
  const a = useActivity(4000);
  const seen = useRef<Set<number> | null>(null);
  const [toasts, setToasts] = useState<(Activity["latest"][number] & { k: number })[]>([]);
  useEffect(() => {
    if (!a) return;
    if (seen.current === null) {
      seen.current = new Set(a.latest.map((x) => x.id)); // nothing on first load
      return;
    }
    const fresh = a.latest.filter((x) => !seen.current!.has(x.id)).reverse();
    fresh.forEach((x) => seen.current!.add(x.id));
    if (fresh.length === 0) return;
    const now = Date.now();
    setToasts((cur) => [...cur, ...fresh.map((x, i) => ({ ...x, k: now + i }))].slice(-4));
    fresh.forEach((_, i) => window.setTimeout(() => setToasts((cur) => cur.filter((t) => t.k !== now + i)), 7000));
  }, [a]);
  if (toasts.length === 0) return null;
  return (
    <div className={l.toasts} role="status" aria-live="polite">
      {toasts.map((x) => (
        <div key={x.k} className={l.toast} style={{ borderLeftColor: AGENT_COLOR[x.agent] ?? "var(--navy)" }}>
          <strong>{x.agent_label}</strong>
          <span>
            {x.subject_id ? `${x.subject_id}: ` : ""}
            {x.text}
          </span>
        </div>
      ))}
    </div>
  );
}
