import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { get, post } from "../../api/client";
import { fmtDateTime } from "../../api/public";
import type { AgentRunDetail } from "../../api/types";
import { modelLabel, rationaleLines, short, StepsList } from "../../ui/AgentSteps";
import { ErrorBox } from "../../ui/ErrorBox";
import o from "../officer/officer.module.css";

/**
 * One agent run: trigger, input, decision, rationale, output, every step, and
 * whether a human overrode it. Used by the Control Room (/control/activity/:id)
 * and by officers for runs on their own ward's grievances (/officer/activity/:id).
 */
export function RunDetail({ backTo, backLabel, srBase }: { backTo: string; backLabel: string; srBase?: string }) {
  const { id = "" } = useParams();
  const [run, setRun] = useState<AgentRunDetail | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [overriding, setOverriding] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);

  const load = useCallback(async () => {
    try {
      setRun(await get<AgentRunDetail>(`/agent-runs/${encodeURIComponent(id)}`));
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, [id]);

  useEffect(() => {
    document.title = `Agent run ${id}`;
    void load();
  }, [id, load]);

  async function override(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setActionError(null);
    try {
      await post(`/agent-runs/${encodeURIComponent(id)}/override`, { reason: reason.trim() });
      setOverriding(false);
      setReason("");
      await load();
    } catch (err) {
      setActionError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <p style={{ marginTop: 0 }}>
        <Link to={backTo}>{backLabel}</Link> &raquo; Run {id}
      </p>
      <ErrorBox error={error} />
      {run ? (
        <>
          <h1>
            {run.agent_label}: run {run.run_id}
          </h1>
          <section className={o.panel}>
            <h2 className={o.panelTitle}>
              System Suggestion
              <span className={o.panelMeta}>{modelLabel(run.model)}</span>
            </h2>
            <div className={o.panelBody}>
              <table className="kv">
                <tbody>
                  <tr>
                    <th scope="row">Decision</th>
                    <td>
                      <strong>{run.decision ?? "(no decision)"}</strong>
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">Time</th>
                    <td>
                      {fmtDateTime(run.started_at)}
                      {run.latency_ms !== null ? <span className="muted"> (took {run.latency_ms} ms)</span> : null}
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">Trigger</th>
                    <td>{run.trigger}</td>
                  </tr>
                  <tr>
                    <th scope="row">Object</th>
                    <td>
                      {run.subject_type === "SR" && run.subject_id && srBase ? (
                        <Link to={`${srBase}/${encodeURIComponent(run.subject_id)}`}>{run.subject_id}</Link>
                      ) : (
                        `${run.subject_type ?? ""} ${run.subject_id ?? "-"}`
                      )}
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">Status</th>
                    <td>
                      {run.status === "FALLBACK" ? "Rule-based fallback (model unavailable or answer rejected)" : run.status}
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">Confidence</th>
                    <td>{run.confidence === null ? "-" : `${Math.round(run.confidence * 100)}%`}</td>
                  </tr>
                  <tr>
                    <th scope="row">Human decision</th>
                    <td>
                      {run.overridden ? (
                        <strong style={{ color: "var(--danger)" }}>
                          Overridden{run.override_reason ? `: ${run.override_reason}` : ""}
                        </strong>
                      ) : run.accepted ? (
                        <strong style={{ color: "var(--ok)" }}>Accepted</strong>
                      ) : (
                        "None yet"
                      )}
                    </td>
                  </tr>
                  {run.error ? (
                    <tr>
                      <th scope="row">Error</th>
                      <td>{run.error}</td>
                    </tr>
                  ) : null}
                </tbody>
              </table>

              <h3>Rationale</h3>
              <ul className={o.rationale}>
                {rationaleLines((run.output as { rationale?: unknown } | null)?.rationale, run.rationale).map((l, i) => (
                  <li key={i}>{l}</li>
                ))}
              </ul>

              <StepsList steps={run.steps} open />

              <details className={o.steps}>
                <summary>Input given to the agent</summary>
                <pre className={o.code}>{short(run.input, 6000)}</pre>
              </details>
              <details className={o.steps}>
                <summary>Structured output</summary>
                <pre className={o.code}>{short(run.output, 6000)}</pre>
              </details>

              {!run.overridden ? (
                <>
                  <ErrorBox error={actionError} />
                  {!overriding ? (
                    <button type="button" className="btn btn-secondary" onClick={() => setOverriding(true)}>
                      Record disagreement (override)
                    </button>
                  ) : (
                    <form className={o.formBox} onSubmit={(e) => void override(e)}>
                      <p className="muted" style={{ marginTop: 0 }}>
                        This records that you disagree with this suggestion and why. It does not change the
                        grievance; use the grievance's own actions for that.
                      </p>
                      <label>
                        <span className="required">Reason</span>
                        <textarea value={reason} onChange={(e) => setReason(e.target.value)} minLength={5} required />
                      </label>
                      <div className="actions">
                        <button type="submit" className="btn" disabled={busy || reason.trim().length < 5}>
                          Save
                        </button>
                        <button type="button" className="btn btn-secondary" onClick={() => setOverriding(false)}>
                          Cancel
                        </button>
                      </div>
                    </form>
                  )}
                </>
              ) : null}
            </div>
          </section>
        </>
      ) : null}
    </>
  );
}
