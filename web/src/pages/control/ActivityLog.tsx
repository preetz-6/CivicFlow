import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { get } from "../../api/client";
import { fmtDateTime } from "../../api/public";
import type { AgentRunRow, AgentStat, Page } from "../../api/types";
import { ErrorBox } from "../../ui/ErrorBox";
import { Table } from "../../ui/Table";
import o from "../officer/officer.module.css";

const AGENTS: [string, string][] = [
  ["investigator", "Case Investigator"],
  ["followup", "Follow-up & Escalation"],
  ["sensing", "Road Hazard Sensing"],
  ["auditor", "Evidence Auditor"],
  ["surge", "Surge Commander"],
];
const PAGE_SIZE = 20;

interface Filters {
  agent: string;
  overridden: string;
  subject_id: string;
}
const EMPTY: Filters = { agent: "", overridden: "", subject_id: "" };

function qs(f: Filters, page: number, size: number) {
  const p = new URLSearchParams({ page: String(page), page_size: String(size) });
  if (f.agent) p.set("agent", f.agent);
  if (f.overridden) p.set("overridden", f.overridden);
  if (f.subject_id.trim()) p.set("subject_id", f.subject_id.trim().toUpperCase());
  return p.toString();
}

/** Columns shared by the city-wide log and the per-grievance list. */
export function runColumns(base: string) {
  return [
    { key: "at", header: "Time", render: (r: AgentRunRow) => fmtDateTime(r.at), csv: (r: AgentRunRow) => r.at },
    { key: "agent_label", header: "Agent" },
    { key: "trigger", header: "Trigger" },
    {
      key: "decision",
      header: "Decision",
      render: (r: AgentRunRow) => (
        <Link to={`${base}/${r.id}`} onClick={(e) => e.stopPropagation()}>
          {r.decision ?? "(no decision)"}
        </Link>
      ),
      csv: (r: AgentRunRow) => r.decision ?? "",
    },
    {
      key: "confidence",
      header: "Confidence",
      numeric: true,
      render: (r: AgentRunRow) => (r.confidence === null ? "-" : `${Math.round(r.confidence * 100)}%`),
    },
    {
      key: "model",
      header: "Model / Rules",
      render: (r: AgentRunRow) => (r.model === "rules" ? "Rules" : r.model),
    },
    {
      key: "overridden",
      header: "Human decision",
      render: (r: AgentRunRow) =>
        r.overridden ? (
          <span title={r.override_reason ?? undefined}>
            <strong style={{ color: "var(--danger)" }}>Overridden</strong>
            {r.overridden_by ? ` by ${r.overridden_by}` : ""}
          </span>
        ) : r.accepted ? (
          <span style={{ color: "var(--ok)", fontWeight: 700 }}>Accepted</span>
        ) : (
          "-"
        ),
      csv: (r: AgentRunRow) => (r.overridden ? `Overridden: ${r.override_reason ?? ""}` : r.accepted ? "Accepted" : ""),
    },
  ];
}

/** Agent Activity Log (Control Room): every agent run, city-wide, with drill-down. */
export function ActivityLog() {
  const navigate = useNavigate();
  const [draft, setDraft] = useState<Filters>(EMPTY);
  const [filters, setFilters] = useState<Filters>(EMPTY);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Page<AgentRunRow> | null>(null);
  const [stats, setStats] = useState<AgentStat[]>([]);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    document.title = "Agent Activity Log | Control Room";
  }, []);

  const load = useCallback(async () => {
    // The per-agent summary is optional: if it fails, the log itself still shows.
    get<AgentStat[]>("/agent-stats")
      .then(setStats)
      .catch(() => setStats([]));
    try {
      setData(await get<Page<AgentRunRow>>(`/agent-runs?${qs(filters, page, PAGE_SIZE)}`));
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, [filters, page]);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 15_000);
    return () => window.clearInterval(timer);
  }, [load]);

  async function fetchAll() {
    const out: AgentRunRow[] = [];
    for (let p = 1; p <= 50; p++) {
      const r = await get<Page<AgentRunRow>>(`/agent-runs?${qs(filters, p, 100)}`);
      out.push(...r.items);
      if (out.length >= r.total || r.items.length === 0) break;
    }
    return out;
  }

  function apply(e: FormEvent) {
    e.preventDefault();
    setPage(1);
    setFilters(draft);
  }

  return (
    <>
      <h1>Agent Activity Log</h1>
      <p className="muted">
        Every decision the system agents took: what triggered it, the tools they used, and whether an officer accepted
        or overrode it. Select a decision to see each step.
      </p>

      {stats.length ? (
        <Table<AgentStat>
          caption="Runs by agent"
          rows={stats}
          rowKey={(s) => s.agent}
          columns={[
            { key: "agent_label", header: "Agent" },
            { key: "runs", header: "Runs", numeric: true },
            { key: "rules_runs", header: "Rule-based", numeric: true },
            { key: "overridden", header: "Overridden by humans", numeric: true },
            {
              key: "avg_latency_ms",
              header: "Avg. time",
              numeric: true,
              render: (s) => (s.avg_latency_ms >= 1000 ? `${(s.avg_latency_ms / 1000).toFixed(1)} s` : `${s.avg_latency_ms} ms`),
            },
          ]}
        />
      ) : null}

      <form className={o.filters} onSubmit={apply} aria-label="Filter agent runs">
        <label>
          Agent
          <select value={draft.agent} onChange={(e) => setDraft({ ...draft, agent: e.target.value })}>
            <option value="">All</option>
            {AGENTS.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </label>
        <label>
          Human decision
          <select value={draft.overridden} onChange={(e) => setDraft({ ...draft, overridden: e.target.value })}>
            <option value="">All</option>
            <option value="true">Overridden</option>
            <option value="false">Not overridden</option>
          </select>
        </label>
        <label>
          Grievance / object No.
          <input
            value={draft.subject_id}
            onChange={(e) => setDraft({ ...draft, subject_id: e.target.value })}
            placeholder="SR-2026-000123"
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
        <Table<AgentRunRow>
          caption="Agent runs"
          rows={data.items}
          total={data.total}
          page={page}
          pageSize={PAGE_SIZE}
          onPageChange={setPage}
          fetchAll={fetchAll}
          exportName="agent-activity-log"
          rowKey={(r) => r.id}
          onRowClick={(r) => navigate(`/control/activity/${r.id}`)}
          columns={[
            ...runColumns("/control/activity"),
            { key: "subject_id", header: "Object", render: (r) => r.subject_id ?? "-" },
          ]}
        />
      ) : null}
    </>
  );
}
