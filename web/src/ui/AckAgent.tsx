import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { get } from "../api/client";
import u from "./ackagent.module.css";

interface Step {
  n: number;
  kind: string;
  label: string;
  summary: string;
}
interface Box {
  key: string;
  kind: string;
  title: string;
  running?: boolean;
  detail?: { steps: Step[]; result: string; how: string | null };
}

/**
 * Right after lodging: the Case Investigator's steps appear one by one (from the public agent-flow view).
 * Polls until the agent has finished, then reveals the steps with a short delay each.
 */
export function AckAgent({ sr }: { sr: string }) {
  const { t } = useTranslation();
  const [box, setBox] = useState<Box | null>(null);
  const [shown, setShown] = useState(0);

  useEffect(() => {
    let alive = true;
    let id = 0;
    const load = () =>
      get<{ boxes: Box[] }>(`/public/agent-flow?sr=${encodeURIComponent(sr)}`)
        .then((f) => {
          if (!alive) return;
          const b = f.boxes.find((x) => x.title === "Case Investigator");
          if (b) setBox(b);
          if (b && !b.running) window.clearInterval(id);
        })
        .catch(() => undefined);
    load();
    id = window.setInterval(load, 1500);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, [sr]);

  const steps = box?.detail?.steps ?? [];
  useEffect(() => {
    if (shown >= steps.length) return;
    const id = window.setTimeout(() => setShown((n) => n + 1), shown === 0 ? 300 : 450);
    return () => window.clearTimeout(id);
  }, [shown, steps.length]);

  const finished = box && !box.running && shown >= steps.length;
  return (
    <section className={u.panel} aria-live="polite">
      <h2 className={u.title}>
        {finished ? <span className={u.tick}>✓</span> : <span className={u.spinner} aria-hidden="true" />}
        {finished ? t("ackAgent.done") : t("ackAgent.title")}
      </h2>
      <ol className={u.steps}>
        {steps.slice(0, shown).map((s) => (
          <li key={s.n} className={s.kind === "action" ? u.action : undefined}>
            <span className={u.label}>{s.label}</span>
            <span className={u.summary}>{s.summary}</span>
          </li>
        ))}
        {!finished ? <li className={u.wait}>{steps.length ? "…" : t("ackAgent.wait")}</li> : null}
      </ol>
      {finished && box?.detail?.result ? <p className={u.result}>{box.detail.result}</p> : null}
      <p className={u.note}>
        {t("ackAgent.note")} <Link to={`/agents?sr=${encodeURIComponent(sr)}`}>{t("ackAgent.more")} →</Link>
      </p>
    </section>
  );
}
