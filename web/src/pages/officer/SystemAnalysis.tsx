import { useState, type FormEvent } from "react";
import { post } from "../../api/client";
import type { Analysis, Category, ComplaintDetail } from "../../api/types";
import { ErrorBox } from "../../ui/ErrorBox";
import o from "./officer.module.css";

interface Dept {
  id: string;
  name: string;
}

function modelLabel(model: string): string {
  if (model === "rules") return "Rule-based analysis";
  if (model.startsWith("replay:")) return `Recorded analysis (${model.slice(7)})`;
  return `Model: ${model}`;
}

function bullets(a: Analysis): string[] {
  if (a.output?.rationale?.length) return a.output.rationale;
  return (a.rationale ?? "")
    .split("\n")
    .map((l) => l.replace(/^\s*-\s*/, "").trim())
    .filter(Boolean);
}

function short(v: unknown): string {
  const s = typeof v === "string" ? v : JSON.stringify(v, null, 2);
  return s.length > 1500 ? `${s.slice(0, 1500)}\n...` : s;
}

/**
 * "System Analysis" panel: the Case Investigator's triage brief, its rationale,
 * the steps (tool calls) it took, and Accept / Override for the ward officer.
 */
export function SystemAnalysis({
  sr,
  categories,
  departments,
  onDone,
}: {
  sr: ComplaintDetail;
  categories: Category[];
  departments: Dept[];
  onDone: (message: string) => Promise<void>;
}) {
  const a = sr.analysis;
  const canDecide = sr.allowed_actions.includes("ASSIGNED") && ["SUBMITTED", "REOPENED"].includes(sr.status);
  const [mode, setMode] = useState<"none" | "override">("none");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [reason, setReason] = useState("");
  const [category, setCategory] = useState("");
  const [priority, setPriority] = useState("");
  const [department, setDepartment] = useState("");
  const [mergeInto, setMergeInto] = useState("");

  const out = a?.output ?? null;
  const deptName = (id?: string | null) => departments.find((d) => d.id === id)?.name ?? id ?? "-";
  const catName = (id?: string | null) => categories.find((c) => c.id === id)?.label ?? id ?? "-";

  async function accept() {
    setBusy(true);
    setError(null);
    try {
      await post(`/complaints/${encodeURIComponent(sr.id)}/accept`, {});
      await onDone("System suggestion accepted. The grievance is now assigned.");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  async function override(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await post(`/complaints/${encodeURIComponent(sr.id)}/override`, {
        reason: reason.trim(),
        category: category || null,
        priority: priority || null,
        department_id: department || null,
        merge_into: mergeInto.trim().toUpperCase() || null,
      });
      setMode("none");
      await onDone(mergeInto.trim() ? "Override recorded; grievance merged." : "Override recorded. The grievance is now assigned.");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={o.panel} aria-labelledby="sa-title">
      <h2 id="sa-title" className={o.panelTitle}>
        System Analysis
        {a ? <span className={o.panelMeta}>{modelLabel(a.model)}</span> : null}
      </h2>
      <div className={o.panelBody}>
        {!a ? (
          <p className="muted">
            System Analysis is not available yet for this grievance. It normally appears within a few seconds of
            submission; use Refresh to check again. You can still accept or override.
          </p>
        ) : (
          <>
            <p style={{ marginBottom: 8 }}>
              <strong>System Suggestion:</strong> {a.decision ?? "-"}
              {a.confidence !== null && a.confidence !== undefined ? (
                <span className="muted"> (confidence {Math.round(a.confidence * 100)}%)</span>
              ) : null}
            </p>
            {a.status === "FALLBACK" ? (
              <p className="notice" style={{ marginBottom: 8 }}>
                The model was not available, so this analysis was produced by the rule-based fallback.
              </p>
            ) : null}
            <ul className={o.rationale}>
              {bullets(a).map((b, i) => (
                <li key={i}>{b}</li>
              ))}
            </ul>
            {out ? (
              <table className="kv">
                <tbody>
                  <tr>
                    <th scope="row">Category</th>
                    <td>
                      {catName(out.category)}
                      {sr.citizen_category && out.category && sr.citizen_category !== out.category ? (
                        <span className="muted"> (citizen chose {catName(sr.citizen_category)})</span>
                      ) : null}
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">Priority</th>
                    <td>{out.priority ?? "-"}</td>
                  </tr>
                  <tr>
                    <th scope="row">Department / Ward</th>
                    <td>
                      {deptName(out.department_id)} / {out.ward_id ?? "-"}
                    </td>
                  </tr>
                  {out.asset_id ? (
                    <tr>
                      <th scope="row">Asset</th>
                      <td>{out.asset_id}</td>
                    </tr>
                  ) : null}
                  {out.duplicate_of ? (
                    <tr>
                      <th scope="row">Possible duplicate of</th>
                      <td>
                        {out.duplicate_of}
                        {out.duplicate_confidence ? ` (${Math.round(out.duplicate_confidence * 100)}%)` : ""}
                      </td>
                    </tr>
                  ) : null}
                  {out.repeat_failure ? (
                    <tr>
                      <th scope="row">Repeat failure</th>
                      <td>{out.repeat_failure_note ?? "Yes"}</td>
                    </tr>
                  ) : null}
                  {out.planned_work_conflict ? (
                    <tr>
                      <th scope="row">Planned work nearby</th>
                      <td>{String(out.planned_work_conflict)}</td>
                    </tr>
                  ) : null}
                  {out.interagency_referral ? (
                    <tr>
                      <th scope="row">Refer to agency</th>
                      <td>
                        <strong>{out.interagency_referral.agency}</strong>: {out.interagency_referral.reason}
                        <div className="muted">The referral is sent when you accept.</div>
                      </td>
                    </tr>
                  ) : null}
                  {out.vehicle_corroboration ? (
                    <tr>
                      <th scope="row">Connected vehicles (Simulated)</th>
                      <td>{String(out.vehicle_corroboration)}</td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            ) : null}
            {a.accepted ? <p className="notice notice-success">Accepted by the ward officer.</p> : null}
            {a.overridden ? (
              <p className="notice">
                Overridden by the ward officer{a.override_reason ? `: ${a.override_reason}` : "."}
              </p>
            ) : null}
            <details className={o.steps}>
              <summary>Steps taken ({a.steps.length})</summary>
              <ol>
                {a.steps.map((s) => (
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
            </details>
          </>
        )}

        {canDecide ? (
          <>
            <ErrorBox error={error} />
            <div className="actions">
              <button type="button" className="btn" disabled={busy} onClick={() => void accept()}>
                Accept
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                disabled={busy}
                aria-expanded={mode === "override"}
                onClick={() => setMode(mode === "override" ? "none" : "override")}
              >
                Override
              </button>
            </div>
            {mode === "override" ? (
              <form className={o.formBox} onSubmit={(e) => void override(e)}>
                <p className="muted" style={{ marginTop: 0 }}>
                  Change only what is wrong. Fields left blank keep the system suggestion.
                </p>
                <label>
                  <span className="required">Reason for override</span>
                  <textarea value={reason} onChange={(e) => setReason(e.target.value)} minLength={5} required />
                </label>
                <label>
                  Category
                  <select value={category} onChange={(e) => setCategory(e.target.value)}>
                    <option value="">Keep</option>
                    {categories.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Priority
                  <select value={priority} onChange={(e) => setPriority(e.target.value)}>
                    <option value="">Keep</option>
                    {["P1", "P2", "P3", "P4"].map((p) => (
                      <option key={p}>{p}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Department
                  <select value={department} onChange={(e) => setDepartment(e.target.value)}>
                    <option value="">Keep</option>
                    {departments.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Merge into grievance (optional)
                  <input
                    value={mergeInto}
                    onChange={(e) => setMergeInto(e.target.value)}
                    placeholder="SR-2026-000123"
                  />
                </label>
                <div className="actions">
                  <button type="submit" className="btn" disabled={busy || reason.trim().length < 5}>
                    Save override
                  </button>
                  <button type="button" className="btn btn-secondary" onClick={() => setMode("none")}>
                    Cancel
                  </button>
                </div>
              </form>
            ) : null}
          </>
        ) : null}
      </div>
    </section>
  );
}
