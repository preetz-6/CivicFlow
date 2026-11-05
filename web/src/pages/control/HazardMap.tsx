import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CircleMarker, Popup, Tooltip } from "react-leaflet";
import { get, post } from "../../api/client";
import { fmtDateTime } from "../../api/public";
import type { DataSourceOut, HazardCluster, HazardMapData } from "../../api/types";
import { CityMap, Legend } from "../../ui/CityMap";
import { ErrorBox } from "../../ui/ErrorBox";
import { Table } from "../../ui/Table";
import o from "../officer/officer.module.css";
import c from "./control.module.css";

/** Cluster colour by Sensing decision. Filtered clusters are grey. */
const STATUS_STYLE: Record<string, { color: string; label: string }> = {
  CREATED: { color: "#b3261e", label: "New complaint created" },
  CORROBORATED: { color: "#1e7b34", label: "Confirms a citizen complaint" },
  REPAIR_FAILURE: { color: "#7a1fa2", label: "Possible repair failure" },
  REVIEW: { color: "#b06a00", label: "Needs officer review" },
  NEW: { color: "#1b3a6b", label: "Not yet assessed" },
  FILTERED: { color: "#8c8c8c", label: "Filtered (speed breaker, rail crossing, single vehicle)" },
  IGNORED: { color: "#bdbdbd", label: "Dismissed" },
};
const style = (s: string) => STATUS_STYLE[s] ?? { color: "#1b3a6b", label: s };

/** Road Hazard Map (connected-vehicle feed): raw detections, clusters, complaints, review queue, data sources. */
export function HazardMap() {
  const [data, setData] = useState<HazardMapData | null>(null);
  const [sources, setSources] = useState<DataSourceOut[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [showRaw, setShowRaw] = useState(true);
  const [showClusters, setShowClusters] = useState(true);
  const [showFiltered, setShowFiltered] = useState(true);
  const [showComplaints, setShowComplaints] = useState(true);
  const [busy, setBusy] = useState<number | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [dismissing, setDismissing] = useState<number | null>(null);
  const [reason, setReason] = useState("");

  const load = useCallback(async () => {
    try {
      const [m, s] = await Promise.all([get<HazardMapData>("/hazards/map?raw=true"), get<DataSourceOut[]>("/data-sources")]);
      setData(m);
      setSources(s);
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, []);

  useEffect(() => {
    document.title = "Road Hazard Map | Control Room";
    void load();
    const timer = window.setInterval(() => void load(), 15_000);
    return () => window.clearInterval(timer);
  }, [load]);

  async function act(id: number, path: string, body: unknown, message: string) {
    setBusy(id);
    setActionError(null);
    try {
      await post(`/hazards/clusters/${id}/${path}`, body);
      setNotice(message);
      setDismissing(null);
      setReason("");
      await load();
    } catch (e) {
      setActionError(e);
    } finally {
      setBusy(null);
    }
  }

  const clusters = data?.clusters ?? [];
  const review = clusters.filter((h) => h.status === "REVIEW");
  const counts = clusters.reduce<Record<string, number>>((m, h) => ({ ...m, [h.status]: (m[h.status] ?? 0) + 1 }), {});

  return (
    <>
      <h1>Road Hazard Map</h1>
      <ErrorBox error={error} />
      {notice ? (
        <p className="notice notice-success" role="status">
          {notice}
        </p>
      ) : null}

      <div className={c.layers} role="group" aria-label="Map layers">
        <label>
          <input type="checkbox" checked={showRaw} onChange={(e) => setShowRaw(e.target.checked)} />
          Raw detections ({data?.raw.length ?? 0})
        </label>
        <label>
          <input type="checkbox" checked={showClusters} onChange={(e) => setShowClusters(e.target.checked)} />
          Clusters ({clusters.length - (counts.FILTERED ?? 0)})
        </label>
        <label>
          <input type="checkbox" checked={showFiltered} onChange={(e) => setShowFiltered(e.target.checked)} />
          Filtered clusters ({counts.FILTERED ?? 0})
        </label>
        <label>
          <input type="checkbox" checked={showComplaints} onChange={(e) => setShowComplaints(e.target.checked)} />
          Complaints from / confirmed by vehicles ({data?.complaints.length ?? 0})
        </label>
      </div>

      <CityMap label="Road hazard map" height={520}>
        {showRaw
          ? (data?.raw ?? []).map((r, i) => (
              <CircleMarker
                key={`r${i}`}
                center={[r.lat, r.lon]}
                radius={2}
                pathOptions={{ color: "#444", weight: 0, fillColor: "#444", fillOpacity: 0.55 }}
              />
            ))
          : null}
        {clusters
          .filter((h) => (h.status === "FILTERED" ? showFiltered : showClusters))
          .map((h) => {
            const st = style(h.status);
            return (
              <CircleMarker
                key={`c${h.id}`}
                center={[h.lat, h.lon]}
                radius={6 + Math.min(14, h.distinct_vehicles * 1.6)}
                pathOptions={{
                  color: st.color,
                  weight: 2,
                  fillColor: st.color,
                  fillOpacity: h.status === "FILTERED" || h.status === "IGNORED" ? 0.12 : 0.35,
                  dashArray: h.status === "FILTERED" ? "4 3" : undefined,
                }}
              >
                <Tooltip>
                  {st.label}: {h.distinct_vehicles} vehicles
                </Tooltip>
                <Popup>
                  <strong>Cluster {h.id}</strong> ({st.label})
                  <br />
                  {h.distinct_vehicles} distinct vehicles, {h.detections} detections
                  {h.avg_confidence !== null ? `, avg confidence ${h.avg_confidence.toFixed(2)}` : ""}
                  <br />
                  {h.filter_reason ?? h.decision_reason ?? ""}
                  {h.sr_id ? (
                    <>
                      <br />
                      <Link to={`/control/complaints/${encodeURIComponent(h.sr_id)}`}>{h.sr_id}</Link>
                    </>
                  ) : null}
                  {h.agent_run_id ? (
                    <>
                      <br />
                      <Link to={`/control/activity/${h.agent_run_id}`}>Steps taken</Link>
                    </>
                  ) : null}
                </Popup>
              </CircleMarker>
            );
          })}
        {showComplaints
          ? (data?.complaints ?? []).map((s) => (
              <CircleMarker
                key={s.id}
                center={[s.lat, s.lon]}
                radius={5}
                pathOptions={{ color: "#000", weight: 2, fillColor: "#fff", fillOpacity: 1 }}
              >
                <Popup>
                  <Link to={`/control/complaints/${encodeURIComponent(s.id)}`}>{s.id}</Link>
                  <br />
                  {s.source === "VEHICLE_FEED" ? "Created from vehicle data" : `Citizen complaint, confirmed by ${s.vehicles} vehicles`}
                  <br />
                  {s.priority}, {s.status.replace(/_/g, " ")}
                </Popup>
              </CircleMarker>
            ))
          : null}
      </CityMap>
      <Legend
        items={[
          ...["CREATED", "CORROBORATED", "REPAIR_FAILURE", "REVIEW", "FILTERED"].map((s) => ({
            color: style(s).color,
            label: `${style(s).label} (${counts[s] ?? 0})`,
            hollow: s === "FILTERED",
          })),
          { color: "#000", label: "Complaint", hollow: true },
          { color: "#444", label: "Raw detection" },
        ]}
      />
      <p className="muted">Circle size grows with the number of distinct vehicles.</p>

      <section className={o.panel} style={{ marginTop: 16 }}>
        <h2 className={o.panelTitle}>
          Review queue
          <span className={o.panelMeta}>{review.length} waiting</span>
        </h2>
        <div className={o.panelBody}>
          <ErrorBox error={actionError} />
          {review.length === 0 ? <p className="muted">No ambiguous clusters waiting for review.</p> : null}
          {review.length ? (
            <Table<HazardCluster>
              rows={review}
              rowKey={(h) => h.id}
              columns={[
                { key: "id", header: "Cluster" },
                { key: "distinct_vehicles", header: "Vehicles", numeric: true },
                {
                  key: "avg_confidence",
                  header: "Avg. confidence",
                  numeric: true,
                  render: (h) => (h.avg_confidence === null ? "-" : h.avg_confidence.toFixed(2)),
                },
                { key: "decision_reason", header: "System Analysis", render: (h) => h.decision_reason ?? "-" },
                {
                  key: "act",
                  header: "Decision",
                  csv: () => "",
                  render: (h) => (
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      <button
                        type="button"
                        className="btn"
                        disabled={busy === h.id}
                        onClick={() => void act(h.id, "confirm", undefined, `Cluster ${h.id} confirmed; a complaint was created.`)}
                      >
                        Confirm
                      </button>
                      <button
                        type="button"
                        className="btn btn-secondary"
                        disabled={busy === h.id}
                        onClick={() => {
                          setDismissing(dismissing === h.id ? null : h.id);
                          setReason("");
                        }}
                      >
                        Dismiss
                      </button>
                    </div>
                  ),
                },
              ]}
            />
          ) : null}
          {dismissing !== null ? (
            <form
              className={o.formBox}
              onSubmit={(e) => {
                e.preventDefault();
                void act(dismissing, "dismiss", { reason: reason.trim() }, `Cluster ${dismissing} dismissed.`);
              }}
            >
              <label htmlFor="hazardmap-reason-for-dismissing-cluster-dismissing">
                <span className="required">Reason for dismissing cluster {dismissing}</span>
                <input
                  id="hazardmap-reason-for-dismissing-cluster-dismissing" value={reason} onChange={(e) => setReason(e.target.value)} minLength={3} required />
              </label>
              <button type="submit" className="btn btn-secondary" disabled={reason.trim().length < 3}>
                Dismiss cluster
              </button>
            </form>
          ) : null}
        </div>
      </section>

      <section className={o.panel}>
        <h2 className={o.panelTitle}>Clusters</h2>
        <div className={o.panelBody}>
          <Table<HazardCluster>
            rows={clusters}
            rowKey={(h) => h.id}
            pageSize={10}
            exportName="hazard-clusters"
            columns={[
              { key: "id", header: "Cluster", numeric: true },
              { key: "status", header: "Decision", render: (h) => style(h.status).label, csv: (h) => h.status },
              { key: "distinct_vehicles", header: "Vehicles", numeric: true },
              { key: "detections", header: "Detections", numeric: true },
              {
                key: "reason",
                header: "Why",
                render: (h) => h.filter_reason ?? h.decision_reason ?? "-",
                csv: (h) => h.filter_reason ?? h.decision_reason ?? "",
              },
              {
                key: "sr_id",
                header: "Complaint",
                render: (h) =>
                  h.sr_id ? <Link to={`/control/complaints/${encodeURIComponent(h.sr_id)}`}>{h.sr_id}</Link> : "-",
                csv: (h) => h.sr_id ?? "",
              },
              { key: "flagged_wo_id", header: "Flagged repair", render: (h) => h.flagged_wo_id ?? "-" },
            ]}
          />
        </div>
      </section>

      <section className={o.panel}>
        <h2 className={o.panelTitle}>Data Sources</h2>
        <div className={o.panelBody}>
          <Table<DataSourceOut>
            rows={sources}
            rowKey={(s) => s.id}
            columns={[
              { key: "name", header: "Source", render: (s) => s.name },
              { key: "kind", header: "Type" },
              {
                key: "last_ingested_at",
                header: "Last ingestion",
                render: (s) => (s.last_ingested_at ? fmtDateTime(s.last_ingested_at) : "Never"),
              },
              { key: "accepted", header: "Accepted", numeric: true },
              { key: "rejected", header: "Rejected", numeric: true },
              {
                key: "recent",
                header: "Recent rejections (dead letter)",
                csv: (s) => s.recent_rejections.map((r) => r.reason).join("; "),
                render: (s) =>
                  s.recent_rejections.length ? (
                    <ul style={{ margin: 0, paddingLeft: 18 }}>
                      {s.recent_rejections.map((r, i) => (
                        <li key={i}>
                          {r.reason}
                          {r.source_record_id ? <span className="muted"> ({r.source_record_id})</span> : null}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    "-"
                  ),
              },
            ]}
          />
        </div>
      </section>
    </>
  );
}
