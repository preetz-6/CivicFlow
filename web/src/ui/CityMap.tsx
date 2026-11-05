import type { ReactNode } from "react";
import { LayerGroup, LayersControl, MapContainer, TileLayer } from "react-leaflet";
import "leaflet/dist/leaflet.css";

/** Corporation area: Kengeri / RR Nagar, Bengaluru. */
export const CITY_CENTER: [number, number] = [12.915, 77.505];

const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services";

/** Base map for staff screens, with a Map / Satellite switch (top right). */
export function CityMap({
  children,
  height = 420,
  label,
  center = CITY_CENTER,
  zoom = 13,
  satellite = false,
}: {
  children?: ReactNode;
  height?: number;
  label: string;
  center?: [number, number];
  zoom?: number;
  /** start in satellite view */
  satellite?: boolean;
}) {
  return (
    <div role="region" aria-label={label} style={{ border: "1px solid var(--border-strong)" }}>
      <MapContainer center={center} zoom={zoom} style={{ height }} scrollWheelZoom={false}>
        <LayersControl position="topright">
          <LayersControl.BaseLayer checked={!satellite} name="Map">
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
          </LayersControl.BaseLayer>
          <LayersControl.BaseLayer checked={satellite} name="Satellite">
            <LayerGroup>
              <TileLayer
                attribution="Imagery &copy; Esri, Maxar, Earthstar Geographics"
                url={`${ESRI}/World_Imagery/MapServer/tile/{z}/{y}/{x}`}
                maxZoom={19}
              />
              {/* road names and places on top of the photo */}
              <TileLayer url={`${ESRI}/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}`} maxZoom={19} />
              <TileLayer url={`${ESRI}/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}`} maxZoom={19} />
            </LayerGroup>
          </LayersControl.BaseLayer>
        </LayersControl>
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
