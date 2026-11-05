import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { get } from "../../api/client";
import { fmtDateTime, useCategories } from "../../api/public";
import type { Page, QueueItem } from "../../api/types";
import { ErrorBox } from "../../ui/ErrorBox";
import { SlaLabel } from "../../ui/SlaBadge";
import { EscalationBadge, PriorityTag, StatusTag } from "../../ui/StatusTag";
import { Table } from "../../ui/Table";
import { ReassignmentsPanel } from "./Reassignments";
import { useConsoleBase } from "../consoleBase";
import o from "./officer.module.css";

interface OfficerStats {
  open: number;
  submitted: number;
  at_risk: number;
  breached: number;
  escalated: number;
  p1: number;
  awaiting_verification: number;
}

const STATUSES = ["SUBMITTED", "REOPENED", "ASSIGNED", "IN_PROGRESS", "ON_HOLD", "WORK_COMPLETED", "VERIFIED", "RESOLVED"];
const PAGE_SIZE = 10;

interface Filters {
  status: string;
  priority: string;
  category: string;
  sla: string;
  q: string;
}
const EMPTY: Filters = { status: "", priority: "", category: "", sla: "", q: "" };

function queryString(f: Filters, page: number, pageSize: number) {
  const p = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  (Object.keys(f) as (keyof Filters)[]).forEach((k) => {
    if (f[k].trim()) p.set(k, f[k].trim());
  });
  return p.toString();
}

/** Ward-scoped complaint queue (GET /officer/queue), newest and most urgent first. */
export function Queue() {
  const navigate = useNavigate();
  const base = useConsoleBase();
  const categories = useCategories();
  const [draft, setDraft] = useState<Filters>(EMPTY);
  const [filters, setFilters] = useState<Filters>(EMPTY);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Page<QueueItem> | null>(null);
  const [stats, setStats] = useState<OfficerStats | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    document.title = "Complaint Queue | Officer Console";
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [q, s] = await Promise.all([
        get<Page<QueueItem>>(`/officer/queue?${queryString(filters, page, PAGE_SIZE)}`),
        get<OfficerStats>("/officer/stats"),
      ]);
      setData(q);
      setStats(s);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [filters, page]);

  useEffect(() => {
    void load();
    // SLA countdowns move with the simulated clock; refresh every 30 s.
    const timer = window.setInterval(() => void load(), 30_000);
    return () => window.clearInterval(timer);
  }, [load]);

  function apply(e: FormEvent) {
    e.preventDefault();
    setPage(1);
    setFilters(draft);
  }

  function quick(f: Partial<Filters>) {
    const next = { ...EMPTY, ...f };
    setDraft(next);
    setFilters(next);
    setPage(1);
  }

  async function fetchAll(): Promise<QueueItem[]> {
    const out: QueueItem[] = [];
    for (let p = 1; p <= 50; p++) {
      const r = await get<Page<QueueItem>>(`/officer/queue?${queryString(filters, p, 100)}`);
      out.push(...r.items);
      if (out.length >= r.total || r.items.length === 0) break;
    }
    return out;
  }

  return (
    <>
      <h1>{base === "/control" ? "All Complaints (city-wide)" : "Complaint Queue"}</h1>
      {stats ? (
        <div className={o.statRow} role="group" aria-label="Queue summary">
          <button type="button" className={o.stat} onClick={() => quick({})}>
            <span>Open</span>
            <strong>{stats.open}</strong>
          </button>
          <button type="button" className={o.stat} onClick={() => quick({ status: "SUBMITTED" })}>
            <span>Awaiting acceptance</span>
            <strong>{stats.submitted}</strong>
          </button>
          <button type="button" className={o.stat} onClick={() => quick({ sla: "AT_RISK" })}>
            <span>At risk</span>
            <strong className={o.warn}>{stats.at_risk}</strong>
          </button>
          <button type="button" className={o.stat} onClick={() => quick({ sla: "BREACHED" })}>
            <span>Breached</span>
            <strong className={o.danger}>{stats.breached}</strong>
          </button>
          <button type="button" className={o.stat} onClick={() => quick({ priority: "P1" })}>
            <span>P1</span>
            <strong className={o.danger}>{stats.p1}</strong>
          </button>
          <div className={o.stat}>
            <span>Escalated</span>
            <strong>{stats.escalated}</strong>
          </div>
        </div>
      ) : null}

      <ReassignmentsPanel onChanged={() => void load()} />

      <form className={o.filters} onSubmit={apply} aria-label="Filter complaints">
        <label>
          Status
          <select value={draft.status} onChange={(e) => setDraft({ ...draft, status: e.target.value })}>
            <option value="">All open</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </label>
        <label>
          Priority
          <select value={draft.priority} onChange={(e) => setDraft({ ...draft, priority: e.target.value })}>
            <option value="">All</option>
            {["P1", "P2", "P3", "P4"].map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
        </label>
        <label>
          Category
          <select value={draft.category} onChange={(e) => setDraft({ ...draft, category: e.target.value })}>
            <option value="">All</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          SLA
          <select value={draft.sla} onChange={(e) => setDraft({ ...draft, sla: e.target.value })}>
            <option value="">All</option>
            <option value="ON_TRACK">On track</option>
            <option value="AT_RISK">At risk</option>
            <option value="BREACHED">Breached</option>
            <option value="PAUSED">Paused</option>
          </select>
        </label>
        <label>
          Search
          <input
            type="search"
            placeholder="Grievance No. or text"
            value={draft.q}
            onChange={(e) => setDraft({ ...draft, q: e.target.value })}
          />
        </label>
        <div className={o.filterBtns}>
          <button type="submit" className="btn">
            Apply
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => {
              setDraft(EMPTY);
              setFilters(EMPTY);
              setPage(1);
            }}
          >
            Clear
          </button>
        </div>
      </form>

      <ErrorBox error={error} />
      {data ? (
        <Table<QueueItem>
          caption="Complaint queue"
          rows={data.items}
          total={data.total}
          page={page}
          pageSize={PAGE_SIZE}
          onPageChange={setPage}
          fetchAll={fetchAll}
          exportName="complaint-queue"
          rowKey={(r) => r.id}
          onRowClick={(r) => navigate(`${base}/complaints/${encodeURIComponent(r.id)}`)}
          columns={[
            {
              key: "id",
              header: "Grievance No.",
              render: (r) => (
                <Link to={`${base}/complaints/${encodeURIComponent(r.id)}`} onClick={(e) => e.stopPropagation()}>
                  {r.id}
                </Link>
              ),
            },
            { key: "category_label", header: "Category" },
            {
              key: "description",
              header: "Description",
              render: (r) => (r.description.length > 70 ? `${r.description.slice(0, 70)}...` : r.description),
            },
            {
              key: "priority",
              header: "Priority",
              render: (r) => (
                <>
                  <PriorityTag priority={r.priority} />
                  {r.emergency ? (
                    <>
                      {" "}
                      <span className={o.emergency}>EMERGENCY</span>
                    </>
                  ) : null}
                </>
              ),
            },
            {
              key: "status",
              header: "Status",
              render: (r) => (
                <>
                  <StatusTag status={r.status} /> <EscalationBadge level={r.escalation_level} />
                </>
              ),
            },
            {
              key: "reporter_count",
              header: "Reports",
              numeric: true,
              render: (r) => (
                <>
                  {r.reporter_count}
                  {r.corroboration_count ? <div className="muted">+{r.corroboration_count} vehicles</div> : null}
                </>
              ),
            },
            { key: "sla", header: "SLA", render: (r) => <SlaLabel sla={r.sla} />, csv: (r) => r.sla.label },
            {
              key: "analysis_decision",
              header: "System Suggestion",
              render: (r) => r.analysis_decision ?? <span className="muted">-</span>,
              csv: (r) => r.analysis_decision ?? "",
            },
            {
              key: "created_at",
              header: "Received",
              render: (r) => fmtDateTime(r.created_at),
              csv: (r) => r.created_at,
            },
          ]}
        />
      ) : loading ? (
        <p className="muted">Loading...</p>
      ) : null}
    </>
  );
}
