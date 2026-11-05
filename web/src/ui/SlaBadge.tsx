import { useTranslation } from "react-i18next";
import u from "./ui.module.css";

export type SlaState = "ON_TRACK" | "AT_RISK" | "BREACHED" | "PAUSED";

/** "2d 4h", "6h", "35m". Minutes are dropped once a day or more is left. */
export function formatDuration(ms: number): string {
  const totalMin = Math.max(0, Math.round(Math.abs(ms) / 60_000));
  const d = Math.floor(totalMin / 1440);
  const h = Math.floor((totalMin % 1440) / 60);
  const m = totalMin % 60;
  if (d > 0) return h > 0 ? `${d}d ${h}h` : `${d}d`;
  if (h > 0) return m > 0 ? `${h}h ${m}m` : `${h}h`;
  return `${m}m`;
}

/**
 * SLA countdown cell: "2d 4h left" (green), amber when AT_RISK,
 * "Breached by 6h" (red), "Paused". `now` must be the backend's simulated
 * clock (GET /clock), not the browser clock, because of TIME_SCALE.
 */
export function SlaBadge({ state, dueAt, now }: { state: SlaState | string; dueAt: string; now: string | Date }) {
  const { t } = useTranslation();
  if (state === "PAUSED") return <span className={`${u.sla} ${u.sla_paused}`}>{t("sla.paused")}</span>;

  const diff = new Date(dueAt).getTime() - new Date(now).getTime();
  const breached = state === "BREACHED" || diff < 0;
  const text = breached
    ? t("sla.breachedBy", { t: formatDuration(diff) })
    : t("sla.left", { t: formatDuration(diff) });
  const tone = breached ? u.sla_breached : state === "AT_RISK" ? u.sla_risk : u.sla_ok;

  return (
    <span className={`${u.sla} ${tone}`} title={new Date(dueAt).toLocaleString("en-IN")}>
      {text}
      {!breached && state === "AT_RISK" ? <span className="visually-hidden"> ({t("sla.atRisk")})</span> : null}
    </span>
  );
}
