import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, get, post } from "../../api/client";
import { fmtDateTime } from "../../api/public";
import { ErrorBox } from "../../ui/ErrorBox";
import { Table } from "../../ui/Table";
import o from "./officer.module.css";

/**
 * Follow-up agent's reassignment proposals (BUILD_PLAN §10 / docs/REQUESTS_FOR_A.md B-8):
 * GET /reassignments?status=PENDING, POST /reassignments/{id}/approve, /reject {reason}.
 * The panel is not rendered until the backend serves that endpoint.
 */
interface Proposal {
  id: number;
  wo_id: string;
  sr_id?: string | null;
  from_crew_id: string | null;
  to_crew_id: string;
  reason: string;
  distance_km: number | null;
  status: string;
  agent_run_id: number | null;
  created_at: string;
}

export function ReassignmentsPanel({ onChanged }: { onChanged?: () => void }) {
  const [items, setItems] = useState<Proposal[] | null>(null);
  const [available, setAvailable] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [rejecting, setRejecting] = useState<number | null>(null);
  const [reason, setReason] = useState("");
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setItems(await get<Proposal[]>("/reassignments?status=PENDING"));
      setAvailable(true);
      setError(null);
    } catch (e) {
      // 404/405: the endpoint has not shipped yet, so render nothing.
      if (e instanceof ApiError && (e.status === 404 || e.status === 405)) setAvailable(false);
      else {
        setAvailable(true);
        setError(e);
      }
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 30_000);
    return () => window.clearInterval(timer);
  }, [load]);

  async function decide(p: Proposal, approve: boolean) {
    setBusy(p.id);
    setError(null);
    try {
      await post(`/reassignments/${p.id}/${approve ? "approve" : "reject"}`, approve ? undefined : { reason: reason.trim() });
      setNotice(
        approve
          ? `${p.wo_id} reassigned to crew ${p.to_crew_id}. The citizen has been told the reason for the delay.`
          : `Proposal for ${p.wo_id} rejected.`,
      );
      setRejecting(null);
      setReason("");
      await load();
      onChanged?.();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  }

  if (!available) return null;

  return (
    <section className={o.panel} aria-labelledby="ra-h">
      <h2 id="ra-h" className={o.panelTitle}>
        Pending Reassignment Proposals (System Suggestion)
        <span className={o.panelMeta}>{items?.length ?? 0} pending</span>
      </h2>
      <div className={o.panelBody}>
        {notice ? (
          <p className="notice notice-success" role="status">
            {notice}
          </p>
        ) : null}
        <ErrorBox error={error} />
        {items && items.length === 0 ? <p className="muted">No proposals waiting for approval.</p> : null}
        {items && items.length > 0 ? (
          <Table<Proposal>
            rows={items}
            rowKey={(p) => p.id}
            columns={[
              {
                key: "wo_id",
                header: "Work order",
                render: (p) =>
                  p.sr_id ? (
                    <>
                      {p.wo_id}
                      <div>
                        <Link to={`/officer/complaints/${encodeURIComponent(p.sr_id)}`}>{p.sr_id}</Link>
                      </div>
                    </>
                  ) : (
                    p.wo_id
                  ),
              },
              {
                key: "crew",
                header: "Crew change",
                render: (p) => `${p.from_crew_id ?? "-"} → ${p.to_crew_id}`,
              },
              {
                key: "distance_km",
                header: "Distance",
                render: (p) => (p.distance_km === null ? "-" : `${p.distance_km.toFixed(1)} km`),
              },
              {
                key: "reason",
                header: "Why",
                render: (p) => (
                  <>
                    {p.reason}
                    {p.agent_run_id ? (
                      <div>
                        <Link to={`/officer/activity/${p.agent_run_id}`}>Steps taken</Link>
                      </div>
                    ) : null}
                  </>
                ),
              },
              { key: "created_at", header: "Proposed", render: (p) => fmtDateTime(p.created_at) },
              {
                key: "act",
                header: "Decision",
                csv: () => "",
                render: (p) => (
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    <button type="button" className="btn" disabled={busy === p.id} onClick={() => void decide(p, true)}>
                      Approve
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      disabled={busy === p.id}
                      onClick={() => {
                        setRejecting(rejecting === p.id ? null : p.id);
                        setReason("");
                      }}
                    >
                      Reject
                    </button>
                  </div>
                ),
              },
            ]}
          />
        ) : null}
        {rejecting !== null && items?.some((p) => p.id === rejecting) ? (
          <form
            className={o.formBox}
            onSubmit={(e) => {
              e.preventDefault();
              const p = items.find((x) => x.id === rejecting);
              if (p) void decide(p, false);
            }}
          >
            <label>
              <span className="required">Reason for rejecting the proposal</span>
              <textarea value={reason} onChange={(e) => setReason(e.target.value)} minLength={5} required />
            </label>
            <button type="submit" className="btn btn-secondary" disabled={reason.trim().length < 5}>
              Reject proposal
            </button>
          </form>
        ) : null}
      </div>
    </section>
  );
}
