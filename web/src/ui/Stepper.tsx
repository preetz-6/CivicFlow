import { useTranslation } from "react-i18next";
import u from "./stepper.module.css";

const STAGES = ["SUBMITTED", "ASSIGNED", "IN_PROGRESS", "RESOLVED", "CLOSED"] as const;
/** where each status sits on the bar */
const POS: Record<string, number> = {
  SUBMITTED: 0, MERGED: 0, REJECTED: 0, ASSIGNED: 1, REOPENED: 1, ON_HOLD: 2, IN_PROGRESS: 2, RESOLVED: 3, CLOSED: 4,
};

/** Grievance progress: Submitted → Assigned → Work in progress → Resolved → Closed. */
export function Stepper({ status }: { status: string }) {
  const { t } = useTranslation();
  const at = POS[status] ?? 0;
  const done = status === "CLOSED";
  return (
    <ol className={u.stepper} aria-label={t("stepper.label")}>
      {STAGES.map((s, i) => {
        const state = i < at || (done && i === at) ? u.done : i === at ? u.current : u.todo;
        return (
          <li key={s} className={`${u.step} ${state}`} style={{ animationDelay: `${i * 90}ms` }}
              aria-current={i === at ? "step" : undefined}>
            <span className={u.dot} aria-hidden="true">
              {i < at || (done && i === at) ? "✓" : i + 1}
            </span>
            <span className={u.label}>{t(`stepper.${s}`)}</span>
          </li>
        );
      })}
    </ol>
  );
}
