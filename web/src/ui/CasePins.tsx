import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import L from "leaflet";
import { Marker, Popup, Tooltip } from "react-leaflet";
import { get } from "../api/client";
import type { QueueItem } from "../api/types";
import { Legend } from "./CityMap";
import s from "./casepins.module.css";

/** GET /officer/map: open cases + cases fixed in the last few days. */
export type MapCase = Omit<QueueItem, "description"> & { fixed: boolean; photo_url: string | null };

export const PIN_COLORS = {
  ON_TRACK: "#1f6fd1",
  AT_RISK: "#e8a317",
  BREACHED: "#d32f2f",
  PAUSED: "#8c8c8c",
  FIXED: "#2e9e4f",
};

function colorOf(c: MapCase): string {
  if (c.fixed) return PIN_COLORS.FIXED;
  return PIN_COLORS[(c.sla.state ?? "ON_TRACK") as keyof typeof PIN_COLORS] ?? PIN_COLORS.ON_TRACK;
}

function iconOf(c: MapCase): L.DivIcon {
  const big = c.priority === "P1";
  const size = big ? 24 : 16;
  const html = `<span class="${s.pin} ${big ? s.p1 : ""}" style="background:${colorOf(c)};width:${size}px;height:${size}px">${
    c.source === "VEHICLE_FEED" ? "V" : ""
  }</span>`;
  return L.divIcon({ html, className: s.wrap, iconSize: [size, size], iconAnchor: [size / 2, size / 2] });
}

const plain = (t: string) => t.replace(/_/g, " ").toLowerCase();

function Card({ c, links }: { c: MapCase; links?: boolean }) {
  return (
    <div className={s.card}>
      {c.photo_url ? (
        <img src={c.photo_url} alt={`Photo for ${c.id}`} className={s.photo} />
      ) : (
        <div className={s.noPhoto}>{c.category_label}</div>
      )}
      <div className={s.body}>
        <strong>{c.id}</strong>
        <div>
          {c.category_label} · {c.ward_id ?? "-"} · {c.priority}
        </div>
        <div>
          <span className={s.dot} style={{ background: colorOf(c) }} />
          {c.fixed ? "Fixed" : plain(c.status)}
          {!c.fixed ? ` · ${c.sla.label}` : ""}
        </div>
        {c.source === "VEHICLE_FEED" ? <div className={s.muted}>Found by the vehicle feed</div> : null}
        {c.analysis_decision ? <div className={s.agent}>Agent: {c.analysis_decision.replace(/->/g, "→")}</div> : null}
        {links ? (
          <div className={s.links}>
            <Link to={`/control/complaints/${encodeURIComponent(c.id)}`}>Open case</Link>
            {" · "}
            <a href={`/agents?sr=${encodeURIComponent(c.id)}`}>How the agents handled it</a>
          </div>
        ) : (
          <div className={s.muted}>Click the pin for links</div>
        )}
      </div>
    </div>
  );
}

/** Case pins for a CityMap. Hover: photo + status card. Click: same card with links. Refreshes every 10 s. */
export function CasePins({ onLoad }: { onLoad?: (cases: MapCase[]) => void }) {
  const [cases, setCases] = useState<MapCase[]>([]);
  useEffect(() => {
    let alive = true;
    const load = () =>
      get<MapCase[]>("/officer/map")
        .then((c) => {
          if (!alive) return;
          setCases(c);
          onLoad?.(c);
        })
        .catch(() => undefined);
    load();
    const id = window.setInterval(load, 10000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, [onLoad]);
  // draw fixed first so open cases sit on top; P1 last
  const ordered = useMemo(
    () => [...cases].sort((a, b) => Number(!a.fixed) - Number(!b.fixed) || Number(a.priority === "P1") - Number(b.priority === "P1")),
    [cases],
  );
  return (
    <>
      {ordered.map((c) => (
        <Marker key={c.id} position={[c.lat, c.lon]} icon={iconOf(c)} title={`${c.id} ${c.category_label}`}>
          <Tooltip direction="top" offset={[0, -10]} opacity={1} className={s.tip}>
            <Card c={c} />
          </Tooltip>
          <Popup>
            <Card c={c} links />
          </Popup>
        </Marker>
      ))}
    </>
  );
}

export function CaseLegend() {
  return (
    <Legend
      items={[
        { color: PIN_COLORS.ON_TRACK, label: "On track" },
        { color: PIN_COLORS.AT_RISK, label: "At risk" },
        { color: PIN_COLORS.BREACHED, label: "Breached" },
        { color: PIN_COLORS.PAUSED, label: "Paused" },
        { color: PIN_COLORS.FIXED, label: "Fixed (last 3 days)" },
        { color: "#555", label: "Big pin = P1 emergency · V = found by vehicles", hollow: true },
      ]}
    />
  );
}
