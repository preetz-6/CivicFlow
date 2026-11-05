import { useTranslation } from "react-i18next";
import u from "./ui.module.css";

const TONE: Record<string, "ok" | "warn" | "danger" | "info" | "neutral"> = {
  SUBMITTED: "info",
  ASSIGNED: "info",
  IN_PROGRESS: "info",
  WORK_COMPLETED: "warn",
  COMPLETED: "warn",
  VERIFIED: "ok",
  RESOLVED: "ok",
  CLOSED: "ok",
  MERGED: "neutral",
  REJECTED: "danger",
  ON_HOLD: "warn",
  REOPENED: "danger",
  REWORK: "danger",
};

/** Complaint or work-order status as a flat, bordered tag (UPPER_SNAKE in). */
export function StatusTag({ status }: { status: string }) {
  const { t } = useTranslation();
  const tone = TONE[status] ?? "neutral";
  return (
    <span className={`${u.tag} ${u[`tag_${tone}`]}`}>
      {t(`status.${status}`, { defaultValue: status.replace(/_/g, " ") })}
    </span>
  );
}

/** Escalation badge, e.g. "Escalated L2". Renders nothing at level 0. */
export function EscalationBadge({ level }: { level: number }) {
  if (!level) return null;
  return <span className={`${u.tag} ${u.tag_danger}`}>Escalated L{level}</span>;
}

/** Priority P1–P4. P1 is red. */
export function PriorityTag({ priority }: { priority: string }) {
  const tone = priority === "P1" ? "danger" : priority === "P2" ? "warn" : "neutral";
  return <span className={`${u.tag} ${u[`tag_${tone}`]}`}>{priority}</span>;
}
