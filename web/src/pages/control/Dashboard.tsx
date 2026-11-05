import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CircleMarker, Popup } from "react-leaflet";
import { get } from "../../api/client";
import { fmtDateTime } from "../../api/public";
import type { Escalation, Page, PublicStats, QueueItem, WeatherAlert } from "../../api/types";
import { CityMap, Legend } from "../../ui/CityMap";
import { ErrorBox } from "../../ui/ErrorBox";
import { SlaLabel } from "../../ui/SlaBadge";
import { EscalationBadge, PriorityTag, StatusTag } from "../../ui/StatusTag";
import { Table } from "../../ui/Table";
import o from "../officer/officer.module.css";
import c from "./control.module.css";

interface CityStats {
  open: number;
  submitted: number;
  at_risk: number;
  breached: number;
  escalated: number;
  p1: number;
  awaiting_verification: number;
}

const SLA_COLOR: Record<string, string> = { BREACHED: "#b3261e", AT_RISK: "#b06a00", PAUSED: "#6b6b6b" };

function complaintColumns() {
  return [
    {
      key: "id",
      header: "Grievance No.",
      render: (r: QueueItem) => <Link to={`/control/complaints/${encodeURIComponent(r.id)}`}>{r.id}</Link>,
    },
    { key: "category_label", header: "Category" },
    { key: "ward_id", header: "Ward", render: (r: QueueItem) => r.ward_id ?? "-" },
    {
      key: "status",
      header: "Status",
      render: (r: QueueItem) => (
        <>
          <StatusTag status={r.status} /> <EscalationBadge level={r.escalation_level} />
        </>
      ),
    },
    { key: "sla", header: "SLA", render: (r: QueueItem) => <SlaLabel sla={r.sla} />, csv: (r: QueueItem) => r.sla.label },
  ];
}

/** Control Room overview: KPIs, live map, P1 queue, SLA breaches, escalations. */
export function Dashboard() {
  const [kpi, setKpi] = useState<PublicStats | null>(null);
  const [city, setCity] = useState<CityStats | null>(null);
  const [open, setOpen] = useState<QueueItem[]>([]);
  const [p1, setP1] = useState<QueueItem[]>([]);
  const [breached, setBreached] = useState<QueueItem[]>([]);
  const [escalations, setEscalations] = useState<Escalation[]>([]);
  const [alerts, setAlerts] = useState<WeatherAlert[]>([]);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async () => {
    try {
      const [k, s, q, qp1, qb, esc, w] = await Promise.all([
        get<PublicStats>("/public/stats"),
        get<CityStats>("/officer/stats"),
        get<Page<QueueItem>>("/officer/queue?page_size=100"),
        get<Page<QueueItem>>("/officer/queue?priority=P1&page_size=50"),
        get<Page<QueueItem>>("/officer/queue?sla=BREACHED&page_size=50"),
        get<Escalation[]>("/escalations"),
        get<WeatherAlert[]>("/weather/alerts"),
      ]);
      setKpi(k);
      setCity(s);
      setOpen(q.items);
      setP1(qp1.items);
      setBreached(qb.items);
      setEscalations(esc);
      setAlerts(w.filter((a) => a.active));
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, []);

  useEffect(() => {
    document.title = "Dashboard | Control Room";
    void load();
    const timer = window.setInterval(() => void load(), 20_000);
    return () => window.clearInterval(timer);
  }, [load]);

  const pct = (n: number | null | undefined) => (n === null || n === undefined ? "-" : `${n}%`);

  return (
    <>
      <h1>Control Room Dashboard</h1>
      <ErrorBox error={error} />

      {alerts.map((a) => (
        <p key={a.id} className="notice notice-error" role="alert">
          <strong>Weather alert:</strong> {a.title}
          {a.area_name ? ` - ${a.area_name}` : ""} (issued {fmtDateTime(a.issued_at)}
          {a.expires_at ? `, until ${fmtDateTime(a.expires_at)}` : ""}). See <Link to="/control/incidents">Incidents</Link>.
        </p>
      ))}

      {kpi && city ? (
        <>
          <h2>Key figures</h2>
          <div className={o.statRow}>
            <div className={o.stat}>
              <span>Total reports</span>
              <strong>{kpi.total}</strong>
            </div>
            <div className={o.stat}>
              <span>Unique issues</span>
              <strong>{kpi.unique_issues}</strong>
            </div>
            <div className={o.stat}>
              <span>Closed: citizen-confirmed</span>
              <strong>{kpi.resolved_citizen_confirmed}</strong>
            </div>
            <div className={o.stat}>
              <span>Closed: automatically</span>
              <strong>{kpi.resolved_auto_closed}</strong>
            </div>
            <div className={o.stat}>
              <span>Within SLA</span>
              <strong>{pct(kpi.within_sla_pct)}</strong>
            </div>
            <div className={o.stat}>
              <span>Reopen rate</span>
              <strong>{pct(kpi.reopen_rate_pct)}</strong>
            </div>
          </div>
          <div className={o.statRow}>
            <div className={o.stat}>
              <span>Open now</span>
              <strong>{city.open}</strong>
            </div>
            <div className={o.stat}>
              <span>Awaiting acceptance</span>
              <strong>{city.submitted}</strong>
            </div>
            <div className={o.stat}>
              <span>At risk</span>
              <strong className={o.warn}>{city.at_risk}</strong>
            </div>
            <div className={o.stat}>
              <span>Breached</span>
              <strong className={o.danger}>{city.breached}</strong>
            </div>
            <div className={o.stat}>
              <span>Escalated</span>
              <strong>{city.escalated}</strong>
            </div>
            <Link to="/control/verification" className={o.stat}>
              <span>Awaiting verification</span>
              <strong>{city.awaiting_verification}</strong>
            </Link>
          </div>
        </>
      ) : null}

      <div className={c.grid2}>
        <section className={o.panel}>
          <h2 className={o.panelTitle}>Live map: open grievances</h2>
          <div className={o.panelBody}>
            <CityMap label="Open grievances map" height={380}>
              {open.map((q) => (
                <CircleMarker
                  key={q.id}
                  center={[q.lat, q.lon]}
                  radius={q.priority === "P1" ? 9 : 6}
                  pathOptions={{
                    color: SLA_COLOR[q.sla.state ?? ""] ?? "#1b3a6b",
                    fillColor: SLA_COLOR[q.sla.state ?? ""] ?? "#1b3a6b",
                    fillOpacity: 0.7,
                    weight: 2,
                  }}
                >
                  <Popup>
                    <strong>
                      <Link to={`/control/complaints/${encodeURIComponent(q.id)}`}>{q.id}</Link>
                    </strong>
                    <br />
                    {q.category_label}, {q.priority}, {q.status.replace(/_/g, " ")}
                    <br />
                    {q.sla.label}
                  </Popup>
                </CircleMarker>
              ))}
            </CityMap>
            <Legend
              items={[
                { color: "#1b3a6b", label: "On track" },
                { color: "#b06a00", label: "At risk" },
                { color: "#b3261e", label: "Breached" },
                { color: "#6b6b6b", label: "Paused" },
              ]}
            />
            {open.length >= 100 ? <p className="muted">Showing the 100 most urgent open grievances.</p> : null}
          </div>
        </section>

        <div>
          <section className={o.panel}>
            <h2 className={o.panelTitle}>P1 queue</h2>
            <div className={o.panelBody}>
              <Table<QueueItem> rows={p1} rowKey={(r) => r.id} pageSize={5} columns={complaintColumns()} />
            </div>
          </section>
        </div>
      </div>

      <section className={o.panel}>
        <h2 className={o.panelTitle}>SLA breaches</h2>
        <div className={o.panelBody}>
          <Table<QueueItem>
            rows={breached}
            rowKey={(r) => r.id}
            pageSize={5}
            exportName="sla-breaches"
            columns={[
              ...complaintColumns(),
              { key: "priority", header: "Priority", render: (r) => <PriorityTag priority={r.priority} /> },
              { key: "owner_name", header: "Owner", render: (r) => r.owner_name ?? "-" },
            ]}
          />
        </div>
      </section>

      <section className={o.panel}>
        <h2 className={o.panelTitle}>Escalations</h2>
        <div className={o.panelBody}>
          <Table<Escalation>
            rows={escalations}
            rowKey={(e) => e.id}
            pageSize={8}
            exportName="escalations"
            columns={[
              { key: "created_at", header: "At", render: (e) => fmtDateTime(e.created_at), csv: (e) => e.created_at },
              {
                key: "sr_id",
                header: "Grievance No.",
                render: (e) => <Link to={`/control/complaints/${encodeURIComponent(e.sr_id)}`}>{e.sr_id}</Link>,
                csv: (e) => e.sr_id,
              },
              { key: "level", header: "Level", render: (e) => `L${e.level}` },
              { key: "authority", header: "Escalated to", render: (e) => e.authority ?? "-" },
              { key: "trigger", header: "Trigger" },
              {
                key: "reason_summary",
                header: "Reason (System write-up)",
                render: (e) => (
                  <>
                    {e.reason_summary ?? "-"}
                    {e.agent_run_id ? (
                      <div>
                        <Link to={`/control/activity/${e.agent_run_id}`}>Steps taken</Link>
                      </div>
                    ) : null}
                  </>
                ),
                csv: (e) => e.reason_summary ?? "",
              },
            ]}
          />
        </div>
      </section>
    </>
  );
}
