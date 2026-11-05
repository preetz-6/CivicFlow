import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CircleMarker, Tooltip } from "react-leaflet";
import { get, post } from "../../api/client";
import { fmtDateTime } from "../../api/public";
import type { Incident, WeatherAlert } from "../../api/types";
import { CityMap } from "../../ui/CityMap";
import { ErrorBox } from "../../ui/ErrorBox";
import o from "../officer/officer.module.css";

const SEVERITY_COLOR: Record<string, string> = { HIGH: "#b3261e", CRITICAL: "#b3261e", MEDIUM: "#b06a00", LOW: "#1b3a6b" };

/** Incidents from the Surge Commander: grouped reports, crew suggestion, advisory (edit + Publish), situation summary. */
export function Incidents() {
  const [items, setItems] = useState<Incident[] | null>(null);
  const [alerts, setAlerts] = useState<WeatherAlert[]>([]);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async () => {
    try {
      const [inc, w] = await Promise.all([get<Incident[]>("/incidents"), get<WeatherAlert[]>("/weather/alerts")]);
      setItems(inc);
      setAlerts(w.filter((a) => a.active));
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, []);

  useEffect(() => {
    document.title = "Incidents | Control Room";
    void load();
    const timer = window.setInterval(() => void load(), 15_000);
    return () => window.clearInterval(timer);
  }, [load]);

  const open = (items ?? []).filter((i) => i.status !== "CLOSED");
  const summary = open.find((i) => i.summary)?.summary ?? null;

  return (
    <>
      <h1>Incidents</h1>
      <p className="muted">
        When many flood, drain or tree-fall reports arrive in one area, the System groups them into incidents and
        drafts a public advisory. Publishing the advisory is your decision.
      </p>
      <ErrorBox error={error} />
      {alerts.map((a) => (
        <p key={a.id} className="notice notice-error" role="alert">
          <strong>Weather alert (Simulated):</strong> {a.title}
          {a.area_name ? ` - ${a.area_name}` : ""}, issued {fmtDateTime(a.issued_at)}
        </p>
      ))}
      {items && items.length === 0 ? <p className="notice">No incidents. Individual grievances are handled normally.</p> : null}

      {open.length ? (
        <>
          {summary ? (
            <section className={o.panel}>
              <h2 className={o.panelTitle}>
                Situation summary for the Commissioner
                <span className={o.panelMeta}>
                  System write-up{open[0]?.summary_at ? `, ${fmtDateTime(open[0].summary_at)}` : ""}
                </span>
              </h2>
              <div className={o.panelBody} style={{ whiteSpace: "pre-wrap" }}>
                {summary}
              </div>
            </section>
          ) : null}
          <CityMap label="Incident locations" height={300} center={[open[0].lat, open[0].lon]} zoom={13}>
            {open.map((i) => (
              <CircleMarker
                key={i.id}
                center={[i.lat, i.lon]}
                radius={10 + Math.min(20, i.report_count)}
                pathOptions={{
                  color: SEVERITY_COLOR[i.severity] ?? "#1b3a6b",
                  fillColor: SEVERITY_COLOR[i.severity] ?? "#1b3a6b",
                  fillOpacity: 0.3,
                }}
              >
                <Tooltip permanent direction="top">
                  {i.name}
                </Tooltip>
              </CircleMarker>
            ))}
          </CityMap>
        </>
      ) : null}

      {(items ?? []).map((i) => (
        <IncidentPanel key={i.id} inc={i} onChanged={load} />
      ))}
    </>
  );
}

function IncidentPanel({ inc, onChanged }: { inc: Incident; onChanged: () => Promise<void> }) {
  const [en, setEn] = useState(inc.advisory_draft ?? "");
  const [kn, setKn] = useState(inc.advisory_draft_kn ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Keep the editable text in step with the draft until the officer edits it.
  const [dirty, setDirty] = useState(false);
  useEffect(() => {
    if (!dirty) {
      setEn(inc.advisory_draft ?? "");
      setKn(inc.advisory_draft_kn ?? "");
    }
  }, [inc.advisory_draft, inc.advisory_draft_kn, dirty]);

  async function act(path: string, body: unknown, message: string) {
    setBusy(true);
    setError(null);
    try {
      await post(`/incidents/${inc.id}/${path}`, body);
      setNotice(message);
      setDirty(false);
      await onChanged();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  const closed = inc.status === "CLOSED";
  return (
    <section className={o.panel} aria-labelledby={`inc-${inc.id}`}>
      <h2 id={`inc-${inc.id}`} className={o.panelTitle}>
        {inc.display_name}
        <span className={o.panelMeta}>
          Severity {inc.severity} - {inc.status}
        </span>
      </h2>
      <div className={o.panelBody}>
        {notice ? (
          <p className="notice notice-success" role="status">
            {notice}
          </p>
        ) : null}
        <ErrorBox error={error} />
        <table className="kv">
          <tbody>
            <tr>
              <th scope="row">Reports</th>
              <td>
                {inc.report_count} citizen reports, {inc.unique_issues} grievances, {inc.resolved_count} resolved
              </td>
            </tr>
            <tr>
              <th scope="row">Crew suggestion (System Suggestion)</th>
              <td>{inc.crew_suggestion ?? "-"}</td>
            </tr>
            <tr>
              <th scope="row">Started</th>
              <td>{fmtDateTime(inc.created_at)}</td>
            </tr>
            <tr>
              <th scope="row">Linked grievances</th>
              <td>
                {inc.sr_ids.slice(0, 30).map((id, n) => (
                  <span key={id}>
                    {n ? ", " : ""}
                    <Link to={`/control/complaints/${encodeURIComponent(id)}`}>{id}</Link>
                  </span>
                ))}
                {inc.sr_ids.length > 30 ? ` and ${inc.sr_ids.length - 30} more` : ""}
              </td>
            </tr>
            {inc.agent_run_id ? (
              <tr>
                <th scope="row">System Analysis</th>
                <td>
                  <Link to={`/control/activity/${inc.agent_run_id}`}>Steps taken</Link>
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>

        <h3>Public advisory</h3>
        {inc.advisory_published ? (
          <p className="notice notice-success">
            Published {inc.published_at ? fmtDateTime(inc.published_at) : ""}. It is shown in the "What's New" ticker on
            the public portal.
          </p>
        ) : (
          <p className="muted">Draft written by the System. Edit if needed, then Publish. It goes to the public "What's New" ticker.</p>
        )}
        <div className={o.formBox}>
          <label>
            English (max 300 characters)
            <textarea
              value={en}
              maxLength={300}
              disabled={inc.advisory_published || closed}
              onChange={(e) => {
                setEn(e.target.value);
                setDirty(true);
              }}
            />
          </label>
          <label lang="kn">
            ಕನ್ನಡ (max 300 characters)
            <textarea
              value={kn}
              maxLength={300}
              disabled={inc.advisory_published || closed}
              onChange={(e) => {
                setKn(e.target.value);
                setDirty(true);
              }}
            />
          </label>
          <div className="actions">
            {!inc.advisory_published && !closed ? (
              <button
                type="button"
                className="btn"
                disabled={busy || !en.trim()}
                onClick={() =>
                  void act(
                    "publish",
                    { advisory: en.trim() || null, advisory_kn: kn.trim() || null },
                    "Advisory published to the public ticker.",
                  )
                }
              >
                Publish advisory
              </button>
            ) : null}
            {!closed ? (
              <button
                type="button"
                className="btn btn-secondary"
                disabled={busy}
                onClick={() => void act("close", {}, "Incident closed.")}
              >
                Close incident
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </section>
  );
}
