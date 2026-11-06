import { Link } from "react-router-dom";
import u from "./duplicatebox.module.css";

export interface DuplicateInfo {
  merged: boolean;
  parent: string;
  confidence: number | null;
  reason: string | null;
  decided_by: "rules" | "model" | "officer" | null;
  by: string | null;
  at: string | null;
}

const WHO: Record<string, string> = {
  rules: "Decided by the duplicate rule (place, time, category, wording)",
  model: "Decided by the AI agent: the rule alone was not sure, the agent read both reports and confirmed",
  officer: "Merged by an officer",
};

/** Why this grievance was merged into another one (or may be the same as another one). */
export function DuplicateBox({ info, base }: { info: DuplicateInfo; base: string }) {
  const parts = (info.reason ?? "").split(" Agent's reading: ");
  return (
    <section className={`${u.box} ${info.merged ? u.merged : u.maybe}`} aria-labelledby="dup-h">
      <h2 id="dup-h" className={u.title}>
        {info.merged ? "Merged as a duplicate of " : "Possible duplicate of "}
        <Link to={`${base}/complaints/${encodeURIComponent(info.parent)}`}>{info.parent}</Link>
        {info.confidence !== null ? <span className={u.conf}>confidence {info.confidence.toFixed(2)}</span> : null}
      </h2>
      <dl className={u.facts}>
        {parts[0] ? (
          <>
            <dt>Why</dt>
            <dd>{parts[0]}</dd>
          </>
        ) : null}
        {parts[1] ? (
          <>
            <dt>Agent's reading</dt>
            <dd>{parts[1]}</dd>
          </>
        ) : null}
        <dt>Decision</dt>
        <dd>
          {info.merged
            ? `${WHO[info.decided_by ?? "rules"]}${info.decided_by === "officer" && info.by ? ` (${info.by})` : ""}.`
            : "Below 0.9, so it was not merged automatically. Use Merge if it is the same problem."}
        </dd>
      </dl>
    </section>
  );
}
