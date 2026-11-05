import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { get, post } from "../../api/client";
import { fmtDateTime, useCategories } from "../../api/public";
import type { AgentRunRow, ComplaintDetail, CrewOut, Page, StatusEventOut, WorkOrderOut } from "../../api/types";
import { runColumns } from "../control/ActivityLog";
import { ErrorBox } from "../../ui/ErrorBox";
import { MapView } from "../../ui/MapPicker";
import { SlaLabel } from "../../ui/SlaBadge";
import { EscalationBadge, PriorityTag, StatusTag } from "../../ui/StatusTag";
import { Table } from "../../ui/Table";
import { Timeline } from "../../ui/Timeline";
import { SystemAnalysis } from "./SystemAnalysis";
import { useConsoleBase } from "../consoleBase";
import o from "./officer.module.css";

interface Dept {
  id: string;
  name: string;
}

const HOLD_REASONS: [string, string][] = [
  ["MATERIAL", "Material not available (SLA clock keeps running)"],
  ["ACCESS", "Site not accessible (SLA clock keeps running)"],
  ["AGENCY", "Waiting for another agency (pauses SLA)"],
  ["WEATHER", "Weather (pauses SLA)"],
  ["CITIZEN", "Waiting for citizen information (pauses SLA)"],
];

const REJECT_REASONS: [string, string][] = [
  ["NOT_CIVIC_ISSUE", "Not a civic issue"],
  ["OUT_OF_JURISDICTION", "Outside the Corporation's jurisdiction"],
  ["PRIVATE_PROPERTY", "On private property"],
  ["INSUFFICIENT_INFO", "Insufficient information to act"],
  ["DUPLICATE", "Duplicate of another grievance"],
];

type Panel = "none" | "hold" | "reject" | "merge" | "unmerge";

/** Shows a field from a loosely typed record (referrals, escalations). */
const val = (r: Record<string, unknown>, k: string) => {
  const v = r[k];
  if (v === null || v === undefined || v === "") return "-";
  if (typeof v === "string" && /^\d{4}-\d\d-\d\dT/.test(v)) return fmtDateTime(v);
  return String(v);
};

export function CaseDetail() {
  const { id = "" } = useParams();
  const base = useConsoleBase();
  const queueHref = base === "/control" ? "/control/complaints" : "/officer";
  const categories = useCategories();
  const [sr, setSr] = useState<ComplaintDetail | null>(null);
  const [departments, setDepartments] = useState<Dept[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [panel, setPanel] = useState<Panel>("none");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);
  // action form fields
  const [holdReason, setHoldReason] = useState("MATERIAL");
  const [holdNote, setHoldNote] = useState("");
  const [rejectCode, setRejectCode] = useState("NOT_CIVIC_ISSUE");
  const [rejectText, setRejectText] = useState("");
  const [parentId, setParentId] = useState("");
  const [unmergeReason, setUnmergeReason] = useState("");

  const load = useCallback(async () => {
    try {
      setSr(await get<ComplaintDetail>(`/complaints/${encodeURIComponent(id)}`));
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, [id]);

  useEffect(() => {
    document.title = `${id} | ${base === "/control" ? "Control Room" : "Officer Console"}`;
    void load();
  }, [id, load]);

  useEffect(() => {
    get<Dept[]>("/public/departments")
      .then(setDepartments)
      .catch(() => setDepartments([]));
  }, []);

  const done = useCallback(
    async (message: string) => {
      setNotice(message);
      setPanel("none");
      await load();
      window.scrollTo(0, 0);
    },
    [load],
  );

  async function act(path: string, body: unknown, message: string) {
    setBusy(true);
    setActionError(null);
    try {
      await post(`/complaints/${encodeURIComponent(id)}${path}`, body);
      await done(message);
    } catch (e) {
      setActionError(e);
    } finally {
      setBusy(false);
    }
  }

  if (error && !sr) {
    return (
      <>
        <p>
          <Link to={queueHref}>Back to complaints</Link>
        </p>
        <ErrorBox error={error} />
      </>
    );
  }
  if (!sr) return <p className="muted">Loading...</p>;

  const allowed = sr.allowed_actions;
  const canHold = allowed.includes("ON_HOLD");
  const canResume = sr.status === "ON_HOLD" && allowed.some((a) => a === "ASSIGNED" || a === "IN_PROGRESS");
  const canReject = allowed.includes("REJECTED");
  const canMerge = allowed.includes("MERGED");
  const canUnmerge = sr.status === "MERGED" && allowed.includes("SUBMITTED");
  const canCreateWo = ["ASSIGNED", "IN_PROGRESS"].includes(sr.status);
  const deptName = departments.find((d) => d.id === sr.department_id)?.name ?? sr.department_id ?? "-";

  return (
    <>
      <p className="no-print" style={{ marginTop: 0 }}>
        <Link to={queueHref}>Complaints</Link> &raquo; {sr.id}
      </p>
      <div className={o.head}>
        <h1>{sr.id}</h1>
        <StatusTag status={sr.status} />
        <PriorityTag priority={sr.priority} />
        {sr.emergency ? <span className={o.emergency}>EMERGENCY</span> : null}
        <EscalationBadge level={sr.escalation_level} />
        <SlaLabel sla={sr.sla} />
        <button type="button" className="btn btn-secondary" onClick={() => void load()}>
          Refresh
        </button>
      </div>

      {notice ? (
        <p className="notice notice-success" role="status">
          {notice}
        </p>
      ) : null}
      <ErrorBox error={error} />

      <div className={o.cols}>
        <div>
          <SystemAnalysis sr={sr} categories={categories} departments={departments} onDone={done} />

          {canHold || canResume || canReject || canMerge || canUnmerge ? (
            <section className={o.panel} aria-labelledby="actions-h">
              <h2 id="actions-h" className={o.panelTitle}>
                Other Actions
              </h2>
              <div className={o.panelBody}>
                <ErrorBox error={actionError} />
                <div className="actions" style={{ marginTop: 0 }}>
                  {canHold ? (
                    <button type="button" className="btn btn-secondary" onClick={() => setPanel("hold")}>
                      Put on hold
                    </button>
                  ) : null}
                  {canResume ? (
                    <button
                      type="button"
                      className="btn"
                      disabled={busy}
                      onClick={() => void act("/resume", undefined, "Work resumed.")}
                    >
                      Resume
                    </button>
                  ) : null}
                  {canMerge ? (
                    <button type="button" className="btn btn-secondary" onClick={() => setPanel("merge")}>
                      Merge into another
                    </button>
                  ) : null}
                  {canUnmerge ? (
                    <button type="button" className="btn btn-secondary" onClick={() => setPanel("unmerge")}>
                      Unmerge
                    </button>
                  ) : null}
                  {canReject ? (
                    <button type="button" className="btn btn-danger" onClick={() => setPanel("reject")}>
                      Reject
                    </button>
                  ) : null}
                </div>

                {panel === "hold" ? (
                  <form
                    className={o.formBox}
                    onSubmit={(e: FormEvent) => {
                      e.preventDefault();
                      void act("/hold", { reason_code: holdReason, note: holdNote.trim() || null }, "Grievance put on hold.");
                    }}
                  >
                    <label htmlFor="casedetail-reason">
                      <span className="required">Reason</span>
                      <select
                        id="casedetail-reason" value={holdReason} onChange={(e) => setHoldReason(e.target.value)}>
                        {HOLD_REASONS.map(([v, l]) => (
                          <option key={v} value={v}>
                            {l}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label htmlFor="casedetail-note">
                      Note
                      <input
                        id="casedetail-note" value={holdNote} onChange={(e) => setHoldNote(e.target.value)} />
                    </label>
                    <div className="actions">
                      <button type="submit" className="btn" disabled={busy}>
                        Put on hold
                      </button>
                      <button type="button" className="btn btn-secondary" onClick={() => setPanel("none")}>
                        Cancel
                      </button>
                    </div>
                  </form>
                ) : null}

                {panel === "reject" ? (
                  <form
                    className={o.formBox}
                    onSubmit={(e: FormEvent) => {
                      e.preventDefault();
                      void act(
                        "/reject",
                        { reason_code: rejectCode, explanation: rejectText.trim() },
                        "Grievance rejected. The citizen has been told why.",
                      );
                    }}
                  >
                    <label htmlFor="casedetail-reason-code">
                      <span className="required">Reason code</span>
                      <select
                        id="casedetail-reason-code" value={rejectCode} onChange={(e) => setRejectCode(e.target.value)}>
                        {REJECT_REASONS.map(([v, l]) => (
                          <option key={v} value={v}>
                            {l}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label htmlFor="casedetail-explanation-for-the-citizen-plain-langua">
                      <span className="required">Explanation for the citizen (plain language)</span>
                      <textarea
                        id="casedetail-explanation-for-the-citizen-plain-langua"
                        value={rejectText}
                        onChange={(e) => setRejectText(e.target.value)}
                        minLength={10}
                        required
                      />
                    </label>
                    <div className="actions">
                      <button type="submit" className="btn btn-danger" disabled={busy || rejectText.trim().length < 10}>
                        Reject grievance
                      </button>
                      <button type="button" className="btn btn-secondary" onClick={() => setPanel("none")}>
                        Cancel
                      </button>
                    </div>
                  </form>
                ) : null}

                {panel === "merge" ? (
                  <form
                    className={o.formBox}
                    onSubmit={(e: FormEvent) => {
                      e.preventDefault();
                      const p = parentId.trim().toUpperCase();
                      void act(`/merge/${encodeURIComponent(p)}`, undefined, `Merged into ${p}.`);
                    }}
                  >
                    {sr.duplicates.length ? (
                      <p style={{ marginTop: 0 }}>
                        Possible duplicates:{" "}
                        {sr.duplicates.map((d) => (
                          <button
                            key={d}
                            type="button"
                            className="btn btn-secondary"
                            style={{ marginRight: 4 }}
                            onClick={() => setParentId(d)}
                          >
                            {d}
                          </button>
                        ))}
                      </p>
                    ) : null}
                    <label htmlFor="casedetail-parent-grievance-no">
                      <span className="required">Parent grievance No.</span>
                      <input
                        id="casedetail-parent-grievance-no"
                        value={parentId}
                        onChange={(e) => setParentId(e.target.value)}
                        placeholder="SR-2026-000123"
                        required
                      />
                    </label>
                    <div className="actions">
                      <button type="submit" className="btn" disabled={busy || !parentId.trim()}>
                        Merge
                      </button>
                      <button type="button" className="btn btn-secondary" onClick={() => setPanel("none")}>
                        Cancel
                      </button>
                    </div>
                  </form>
                ) : null}

                {panel === "unmerge" ? (
                  <form
                    className={o.formBox}
                    onSubmit={(e: FormEvent) => {
                      e.preventDefault();
                      void act("/unmerge", { reason: unmergeReason.trim() }, "Grievance unmerged.");
                    }}
                  >
                    <label htmlFor="casedetail-reason-2">
                      <span className="required">Reason</span>
                      <textarea
                        id="casedetail-reason-2"
                        value={unmergeReason}
                        onChange={(e) => setUnmergeReason(e.target.value)}
                        minLength={3}
                        required
                      />
                    </label>
                    <div className="actions">
                      <button type="submit" className="btn" disabled={busy || unmergeReason.trim().length < 3}>
                        Unmerge
                      </button>
                      <button type="button" className="btn btn-secondary" onClick={() => setPanel("none")}>
                        Cancel
                      </button>
                    </div>
                  </form>
                ) : null}
              </div>
            </section>
          ) : null}

          <WorkOrders sr={sr} canCreate={canCreateWo} onDone={done} />
        </div>

        <div>
          <section className={o.panel} aria-labelledby="details-h">
            <h2 id="details-h" className={o.panelTitle}>
              Grievance Details
            </h2>
            <div className={o.panelBody}>
              <table className="kv">
                <tbody>
                  <tr>
                    <th scope="row">Category</th>
                    <td>{sr.category_label}</td>
                  </tr>
                  <tr>
                    <th scope="row">Description</th>
                    <td>{sr.description}</td>
                  </tr>
                  <tr>
                    <th scope="row">Location</th>
                    <td>
                      {[sr.landmark, sr.address].filter(Boolean).join(", ") || "-"}
                      <div className="muted">
                        {sr.lat.toFixed(5)}, {sr.lon.toFixed(5)}
                      </div>
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">Ward / Department</th>
                    <td>
                      {sr.ward_id ?? "-"} / {deptName}
                    </td>
                  </tr>
                  {sr.asset_id ? (
                    <tr>
                      <th scope="row">Asset</th>
                      <td>{sr.asset_id}</td>
                    </tr>
                  ) : null}
                  {sr.parent_sr_id ? (
                    <tr>
                      <th scope="row">Merged into</th>
                      <td>
                        <Link to={`${base}/complaints/${encodeURIComponent(sr.parent_sr_id)}`}>{sr.parent_sr_id}</Link>
                      </td>
                    </tr>
                  ) : null}
                  <tr>
                    <th scope="row">Source</th>
                    <td>
                      {sr.source === "VEHICLE_FEED" ? "Connected vehicles (Simulated)" : sr.source.replace(/_/g, " ")}
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">Reports</th>
                    <td>
                      {sr.reporter_count} citizen{sr.reporter_count === 1 ? "" : "s"}
                      {sr.corroboration_count ? `, confirmed by ${sr.corroboration_count} vehicles` : ""}
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">Received</th>
                    <td>{fmtDateTime(sr.created_at)}</td>
                  </tr>
                  <tr>
                    <th scope="row">Owner</th>
                    <td>{sr.owner_name ?? "-"}</td>
                  </tr>
                  {sr.hold_reason ? (
                    <tr>
                      <th scope="row">On hold because</th>
                      <td>{sr.hold_reason}</td>
                    </tr>
                  ) : null}
                  <tr>
                    <th scope="row">Citizen contact</th>
                    <td>
                      {sr.contact_name || sr.contact_phone
                        ? [sr.contact_name, sr.contact_phone].filter(Boolean).join(", ")
                        : "Anonymous"}
                    </td>
                  </tr>
                </tbody>
              </table>
              <MapView lat={sr.lat} lon={sr.lon} label={`Location of ${sr.id}`} />
              {sr.photos.length ? (
                <div className="photo-grid" style={{ marginTop: 12 }}>
                  {sr.photos.map((p) => (
                    <figure key={p.id}>
                      <a href={p.url} target="_blank" rel="noreferrer">
                        <img src={p.url} alt={`${p.kind} photo`} loading="lazy" />
                      </a>
                      <figcaption>
                        {p.kind}
                        {p.wo_id ? ` (${p.wo_id})` : ""} - {fmtDateTime(p.exif_time ?? p.uploaded_at)}
                      </figcaption>
                    </figure>
                  ))}
                </div>
              ) : null}
            </div>
          </section>

          {sr.referrals.length ? (
            <section className={o.panel}>
              <h2 className={o.panelTitle}>Inter-agency Referrals</h2>
              <div className={o.panelBody}>
                <Table<Record<string, unknown>>
                  rows={sr.referrals}
                  rowKey={(r) => String(r.id)}
                  columns={[
                    { key: "agency", header: "Agency", render: (r) => val(r, "agency") },
                    { key: "status", header: "Status", render: (r) => val(r, "status") },
                    { key: "reason", header: "Reason", render: (r) => val(r, "reason") },
                    { key: "sent_at", header: "Sent", render: (r) => val(r, "sent_at") },
                    { key: "followups_sent", header: "Follow-ups", render: (r) => val(r, "followups_sent") },
                    { key: "agency_status", header: "Agency status", render: (r) => val(r, "agency_status") },
                    { key: "agency_reply", header: "Agency reply", render: (r) => val(r, "agency_reply") },
                  ]}
                />
              </div>
            </section>
          ) : null}

          {sr.escalations.length ? (
            <section className={o.panel}>
              <h2 className={o.panelTitle}>Escalations</h2>
              <div className={o.panelBody}>
                <Table<Record<string, unknown>>
                  rows={sr.escalations}
                  rowKey={(r) => `${val(r, "level")}-${val(r, "created_at")}`}
                  columns={[
                    { key: "level", header: "Level", render: (r) => `L${val(r, "level")}` },
                    { key: "trigger", header: "Trigger", render: (r) => val(r, "trigger") },
                    { key: "reason_summary", header: "Reason", render: (r) => val(r, "reason_summary") },
                    { key: "created_at", header: "At", render: (r) => val(r, "created_at") },
                  ]}
                />
              </div>
            </section>
          ) : null}

          <AgentActivity srId={sr.id} refreshKey={sr.status_events.length} />

          <section className={o.panel}>
            <h2 className={o.panelTitle}>Citizen Timeline</h2>
            <div className={o.panelBody}>
              <Timeline entries={sr.timeline.map((e) => ({ at: e.at, stage: e.stage, remarks: e.remarks, actor: e.actor_type }))} />
            </div>
          </section>

          <section className={o.panel}>
            <h2 className={o.panelTitle}>Status History (audit)</h2>
            <div className={o.panelBody}>
              <Table<StatusEventOut>
                rows={sr.status_events}
                rowKey={(e) => `${e.at}-${e.object_id}-${e.to_state}`}
                pageSize={10}
                columns={[
                  { key: "at", header: "At", render: (e) => fmtDateTime(e.at) },
                  { key: "object_id", header: "Object" },
                  { key: "change", header: "Change", render: (e) => `${e.from_state ?? "-"} → ${e.to_state}` },
                  {
                    key: "actor",
                    header: "By",
                    render: (e) => `${e.actor_label ?? e.actor_type}${e.actor_type === "AGENT" ? " (System)" : ""}`,
                  },
                  { key: "reason", header: "Reason", render: (e) => e.reason ?? "-" },
                ]}
              />
            </div>
          </section>
        </div>
      </div>
    </>
  );
}

function WorkOrders({
  sr,
  canCreate,
  onDone,
}: {
  sr: ComplaintDetail;
  canCreate: boolean;
  onDone: (m: string) => Promise<void>;
}) {
  const [crews, setCrews] = useState<CrewOut[]>([]);
  const [open, setOpen] = useState(false);
  const [crewId, setCrewId] = useState("");
  const [scope, setScope] = useState("");
  const [rootCause, setRootCause] = useState("");
  const [cost, setCost] = useState("");
  const [assetId, setAssetId] = useState(sr.asset_id ?? "");
  const [photo, setPhoto] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    if (!open || !sr.ward_id) return;
    get<CrewOut[]>(`/crews?ward=${encodeURIComponent(sr.ward_id)}`)
      .then((c) => {
        setCrews(c);
        if (c.length && !crewId) setCrewId(c[0].id);
      })
      .catch((e) => setError(e));
  }, [open, sr.ward_id, crewId]);

  async function create(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const fd = new FormData();
    fd.append("crew_id", crewId);
    fd.append("scope", scope.trim());
    if (rootCause.trim()) fd.append("root_cause", rootCause.trim());
    if (cost.trim()) fd.append("est_cost_inr", cost.trim());
    if (assetId.trim()) fd.append("asset_id", assetId.trim());
    if (photo) fd.append("before_photo", photo, photo.name);
    try {
      const wo = await post<WorkOrderOut>(`/complaints/${encodeURIComponent(sr.id)}/work-orders`, fd);
      setOpen(false);
      setScope("");
      setRootCause("");
      setCost("");
      setPhoto(null);
      await onDone(`Work order ${wo.id} created and assigned to crew ${wo.crew_id}.`);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={o.panel} aria-labelledby="wo-h">
      <h2 id="wo-h" className={o.panelTitle}>
        Work Orders
      </h2>
      <div className={o.panelBody}>
        {sr.work_orders.length ? (
          <Table<WorkOrderOut>
            rows={sr.work_orders}
            rowKey={(w) => w.id}
            columns={[
              { key: "id", header: "Work Order" },
              { key: "crew_id", header: "Crew" },
              { key: "status", header: "Status", render: (w) => <StatusTag status={w.status} /> },
              { key: "scope", header: "Scope" },
              {
                key: "audit",
                header: "Auto-check result",
                render: (w) =>
                  w.audit_verdict ? `${w.audit_verdict}${w.audit_score !== null ? ` (${w.audit_score}/100)` : ""}` : "-",
              },
              { key: "rework_reason", header: "Rework reason", render: (w) => w.rework_reason ?? "-" },
            ]}
          />
        ) : (
          <p className="muted">No work order yet.</p>
        )}

        {canCreate ? (
          <>
            {!open ? (
              <button type="button" className="btn" onClick={() => setOpen(true)}>
                Create work order
              </button>
            ) : (
              <form className={o.formBox} onSubmit={(e) => void create(e)}>
                <ErrorBox error={error} />
                <label htmlFor="casedetail-crew">
                  <span className="required">Crew</span>
                  <select
                    id="casedetail-crew" value={crewId} onChange={(e) => setCrewId(e.target.value)} required>
                    {crews.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name && !c.name.includes(c.id) ? `${c.id} - ${c.name}` : (c.name ?? c.id)} ({c.open_jobs}/
                        {c.capacity} jobs{c.open_jobs >= c.capacity ? ", full" : ""})
                        {c.audit_priority && c.audit_priority !== "NORMAL" ? ` - audit priority ${c.audit_priority}` : ""}
                      </option>
                    ))}
                  </select>
                </label>
                <label htmlFor="casedetail-scope-of-work">
                  <span className="required">Scope of work</span>
                  <textarea
                    id="casedetail-scope-of-work" value={scope} onChange={(e) => setScope(e.target.value)} required />
                </label>
                <label htmlFor="casedetail-root-cause">
                  Root cause
                  <input
                    id="casedetail-root-cause" value={rootCause} onChange={(e) => setRootCause(e.target.value)} />
                </label>
                <label htmlFor="casedetail-estimated-cost-inr">
                  Estimated cost (INR)
                  <input
                    id="casedetail-estimated-cost-inr"
                    inputMode="decimal"
                    value={cost}
                    onChange={(e) => setCost(e.target.value.replace(/[^0-9.]/g, ""))}
                  />
                </label>
                <label htmlFor="casedetail-asset-id">
                  Asset ID
                  <input
                    id="casedetail-asset-id" value={assetId} onChange={(e) => setAssetId(e.target.value)} />
                </label>
                <label htmlFor="casedetail-before-photo-optional-uploaded-unchanged">
                  Before photo (optional, uploaded unchanged)
                  <input
                    id="casedetail-before-photo-optional-uploaded-unchanged" type="file" accept="image/jpeg,image/png" onChange={(e) => setPhoto(e.target.files?.[0] ?? null)} />
                </label>
                <div className="actions">
                  <button type="submit" className="btn" disabled={busy || !crewId || !scope.trim()}>
                    Create and assign
                  </button>
                  <button type="button" className="btn btn-secondary" onClick={() => setOpen(false)}>
                    Cancel
                  </button>
                </div>
              </form>
            )}
          </>
        ) : null}
      </div>
    </section>
  );
}

/** Every agent run on this grievance (GET /agent-runs?subject_id=), newest first. */
function AgentActivity({ srId, refreshKey }: { srId: string; refreshKey: number }) {
  const base = useConsoleBase();
  const [runs, setRuns] = useState<AgentRunRow[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    get<Page<AgentRunRow>>(`/agent-runs?subject_id=${encodeURIComponent(srId)}&page_size=50`)
      .then((r) => {
        setRuns(r.items);
        setError(null);
      })
      .catch((e) => setError(e));
  }, [srId, refreshKey]);
  return (
    <section className={o.panel} aria-labelledby="aa-h">
      <h2 id="aa-h" className={o.panelTitle}>
        Agent Activity on this Grievance
      </h2>
      <div className={o.panelBody}>
        <ErrorBox error={error} />
        {runs ? (
          <Table<AgentRunRow> rows={runs} rowKey={(r) => r.id} pageSize={5} columns={runColumns(`${base}/activity`)} />
        ) : null}
      </div>
    </section>
  );
}
