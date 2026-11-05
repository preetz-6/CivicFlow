import type { ReactNode } from "react";
import { MapContainer, TileLayer } from "react-leaflet";
import "leaflet/dist/leaflet.css";

/** Corporation area: Kengeri / RR Nagar, Bengaluru. */
export const CITY_CENTER: [number, number] = [12.915, 77.505];

/** Base map for staff screens (OpenStreetMap tiles). */
export function CityMap({
  children,
  height = 420,
  label,
  center = CITY_CENTER,
  zoom = 13,
}: {
  children?: ReactNode;
  height?: number;
  label: string;
  center?: [number, number];
  zoom?: number;
}) {
  return (
    <div role="region" aria-label={label} style={{ border: "1px solid var(--border-strong)" }}>
      <MapContainer center={center} zoom={zoom} style={{ height }} scrollWheelZoom={false}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {children}
      </MapContainer>
    </div>
  );
}

/** Small legend row under a map. */
export function Legend({ items }: { items: { color: string; label: string; hollow?: boolean }[] }) {
  return (
    <ul style={{ listStyle: "none", display: "flex", flexWrap: "wrap", gap: 16, padding: 0, margin: "6px 0 0", fontSize: "var(--fs-sm)" }}>
      {items.map((i) => (
        <li key={i.label} style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span
            aria-hidden="true"
            style={{
              width: 12,
              height: 12,
              borderRadius: "50%",
              border: `2px solid ${i.color}`,
              background: i.hollow ? "transparent" : i.color,
              display: "inline-block",
            }}
          />
          {i.label}
        </li>
      ))}
    </ul>
  );
}
