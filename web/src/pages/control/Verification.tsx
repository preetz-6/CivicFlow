import { useCallback, useEffect, useState } from "react";
import { get, post } from "../../api/client";
import { fmtDateTime } from "../../api/public";
import type { Analysis, AttachmentOut, FieldJob } from "../../api/types";
import { ErrorBox } from "../../ui/ErrorBox";
import { PriorityTag } from "../../ui/StatusTag";
import o from "../officer/officer.module.css";
import c from "./control.module.css";

interface AuditCheck {
  name: string;
  passed: boolean | null;
  detail: string;
}

interface AuditOutput {
  verdict?: "PASS" | "FLAG" | "FAIL";
  score?: number;
  checks?: AuditCheck[];
  rationale?: string[];
}

type VerificationItem = FieldJob & {
  audit: (Omit<Analysis, "output"> & { output: AuditOutput | null }) | null;
  crew_audit_priority: string | null;
};

const VERDICT_CLASS: Record<string, string> = { PASS: c.pass, FLAG: c.flag, FAIL: c.fail };

function Photo({ p, label }: { p: AttachmentOut | undefined; label: string }) {
  return (
    <figure className={c.photo}>
      <figcaption>
        <strong>{label}</strong>
      </figcaption>
      {p ? (
        <>
          <a href={p.url} target="_blank" rel="noreferrer">
            <img src={p.url} alt={label} />
          </a>
          <div className="muted">
            {p.exif_time ? `Taken ${fmtDateTime(p.exif_time)}` : "No time in photo"}
            {p.exif_lat !== null && p.exif_lat !== undefined && p.exif_lon !== null && p.exif_lon !== undefined
              ? `, GPS ${p.exif_lat.toFixed(5)}, ${p.exif_lon.toFixed(5)}`
              : ", no GPS"}
          </div>
        </>
      ) : (
        <p className="muted">Not available</p>
      )}
    </figure>
  );
}

/** Control Room verification queue: completed work orders with the auto-check result, Approve / Reject. */
export function Verification() {
  const [items, setItems] = useState<VerificationItem[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<{ id: string; e: unknown } | null>(null);
  const [rejecting, setRejecting] = useState<string | null>(null);
  const [reason, setReason] = useState("");

  const load = useCallback(async () => {
    try {
      setItems(await get<VerificationItem[]>("/control/verification"));
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, []);

  useEffect(() => {
    document.title = "Verification Queue | Control Room";
    void load();
    const timer = window.setInterval(() => void load(), 20_000);
    return () => window.clearInterval(timer);
  }, [load]);

  async function decide(id: string, path: string, body: unknown, message: string) {
    setBusyId(id);
    setActionError(null);
    try {
      await post(`/work-orders/${encodeURIComponent(id)}${path}`, body);
      setNotice(message);
      setRejecting(null);
      setReason("");
      await load();
    } catch (e) {
      setActionError({ id, e });
    } finally {
      setBusyId(null);
    }
  }

  return (
    <>
      <h1>Verification Queue</h1>
      <p className="muted">
        Work orders marked completed by field teams. The auto-check result is advisory; your approval is final.
      </p>
      {notice ? (
        <p className="notice notice-success" role="status">
          {notice}
        </p>
      ) : null}
      <ErrorBox error={error} />
      {items && items.length === 0 ? <p className="notice">Nothing is waiting for verification.</p> : null}

      {(items ?? []).map((w) => {
        const out = w.audit?.output ?? null;
        const verdict = out?.verdict ?? w.audit_verdict ?? null;
        const before = w.photos.filter((p) => p.kind === "BEFORE").at(-1) ?? w.citizen_photos.at(-1);
        const after = w.photos.filter((p) => p.kind === "AFTER").at(-1);
        return (
          <section key={w.id} className={o.panel} aria-labelledby={`v-${w.id}`}>
            <h2 id={`v-${w.id}`} className={o.panelTitle}>
              <span>
                {w.id} - {w.category_label} ({w.sr_id})
              </span>
              <span className={o.panelMeta}>
                Crew {w.crew_id}
                {w.crew_audit_priority && w.crew_audit_priority !== "NORMAL" ? ` - audit priority ${w.crew_audit_priority}` : ""}
              </span>
            </h2>
            <div className={o.panelBody}>
              <p style={{ marginTop: 0 }}>
                <PriorityTag priority={w.priority} /> {w.description}
              </p>
              <div className={c.photos}>
                <Photo p={before} label={before?.kind === "CITIZEN" ? "Citizen photo" : "Before"} />
                <Photo p={after} label="After" />
              </div>

              <h3>
                Auto-check result:{" "}
                {verdict ? <span className={`${c.verdict} ${VERDICT_CLASS[verdict] ?? ""}`}>{verdict}</span> : "pending"}
                {out?.score !== undefined ? <span className="muted"> ({out.score}/100)</span> : null}
                {w.audit?.model === "rules" ? <span className="muted"> - rule-based checks</span> : null}
              </h3>
              {out?.checks?.length ? (
                <table className="kv">
                  <tbody>
                    {out.checks.map((ch) => (
                      <tr key={ch.name}>
                        <th scope="row">{ch.name.replace(/_/g, " ")}</th>
                        <td>
                          <strong className={ch.passed === true ? c.pass : ch.passed === false ? c.fail : c.flag}>
                            {ch.passed === true ? "Passed" : ch.passed === false ? "Failed" : "Cannot verify"}
                          </strong>{" "}
                          - {ch.detail}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : null}
              {out?.rationale?.length ? (
                <ul className={o.rationale}>
                  {out.rationale.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
              ) : null}

              {actionError?.id === w.id ? <ErrorBox error={actionError.e} /> : null}
              <div className="actions">
                <button
                  type="button"
                  className="btn"
                  disabled={busyId === w.id}
                  onClick={() => void decide(w.id, "/approve", undefined, `${w.id} approved. The citizen has been sent the before/after photos.`)}
                >
                  Approve
                </button>
                <button
                  type="button"
                  className="btn btn-danger"
                  disabled={busyId === w.id}
                  aria-expanded={rejecting === w.id}
                  onClick={() => {
                    setRejecting(rejecting === w.id ? null : w.id);
                    setReason("");
                  }}
                >
                  Reject (send for rework)
                </button>
              </div>
              {rejecting === w.id ? (
                <form
                  className={o.formBox}
                  onSubmit={(e) => {
                    e.preventDefault();
                    void decide(w.id, "/reject", { reason: reason.trim() }, `${w.id} sent back for rework.`);
                  }}
                >
                  <label>
                    <span className="required">Reason for rework (shown to the field team)</span>
                    <textarea value={reason} onChange={(e) => setReason(e.target.value)} minLength={5} required />
                  </label>
                  <button type="submit" className="btn btn-danger" disabled={busyId === w.id || reason.trim().length < 5}>
                    Send for rework
                  </button>
                </form>
              ) : null}
            </div>
          </section>
        );
      })}
    </>
  );
}
