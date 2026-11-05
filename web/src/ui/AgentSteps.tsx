import type { AnalysisStep } from "../api/types";
import o from "../pages/officer/officer.module.css";

/** How a run was produced, in plain words. */
export function modelLabel(model: string): string {
  if (model === "rules") return "Rule-based analysis";
  if (model.startsWith("replay:")) return `Recorded analysis (${model.slice(7)})`;
  return `Model: ${model}`;
}

/** Short pretty JSON for tool inputs/results. */
export function short(v: unknown, max = 1500): string {
  const s = typeof v === "string" ? v : JSON.stringify(v, null, 2);
  if (s === undefined) return "-";
  return s.length > max ? `${s.slice(0, max)}\n...` : s;
}

/** Rationale as bullet lines: from a list, or from "- a\n- b" text. */
export function rationaleLines(list: unknown, text: string | null | undefined): string[] {
  if (Array.isArray(list) && list.length) return list.map(String);
  return (text ?? "")
    .split("\n")
    .map((l) => l.replace(/^\s*-\s*/, "").trim())
    .filter(Boolean);
}

/** Expandable "Steps taken" list: every tool call with its input and result. */
export function StepsList({ steps, open = false }: { steps: AnalysisStep[]; open?: boolean }) {
  return (
    <details className={o.steps} open={open}>
      <summary>Steps taken ({steps.length})</summary>
      {steps.length === 0 ? (
        <p className="muted">No tool calls were recorded for this run.</p>
      ) : (
        <ol>
          {steps.map((s) => (
            <li key={s.idx}>
              <strong>{s.tool.replace(/^rule:/, "")}</strong>
              {s.tool.startsWith("rule:") ? <span className="muted"> (rule)</span> : null}
              <div className="muted">Input</div>
              <pre className={o.code}>{short(s.args)}</pre>
              <div className="muted">Result</div>
              <pre className={o.code}>{s.error ? `Error: ${s.error}` : short(s.result)}</pre>
            </li>
          ))}
        </ol>
      )}
    </details>
  );
}
