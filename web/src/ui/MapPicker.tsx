import { useEffect, useMemo, useRef } from "react";
import L from "leaflet";
import { MapContainer, Marker, useMap, useMapEvents } from "react-leaflet";
import { BaseLayers } from "./CityMap";
import "leaflet/dist/leaflet.css";
import iconUrl from "leaflet/dist/images/marker-icon.png";
import iconRetinaUrl from "leaflet/dist/images/marker-icon-2x.png";
import shadowUrl from "leaflet/dist/images/marker-shadow.png";

// Bundlers break Leaflet's default icon paths; point them at the packaged images.
L.Icon.Default.mergeOptions({ iconUrl, iconRetinaUrl, shadowUrl });

export interface LatLon {
  lat: number;
  lon: number;
}

function ClickToMove({ onChange }: { onChange: (p: LatLon) => void }) {
  useMapEvents({
    click(e) {
      onChange({ lat: e.latlng.lat, lon: e.latlng.lng });
    },
  });
  return null;
}

function Recenter({ value }: { value: LatLon }) {
  const map = useMap();
  useEffect(() => {
    if (!map.getBounds().contains([value.lat, value.lon])) map.setView([value.lat, value.lon]);
  }, [map, value.lat, value.lon]);
  return null;
}

/** Leaflet map with one draggable pin. Click the map or drag the pin to move it. */
export function MapPicker({
  value,
  onChange,
  height = 320,
  label,
}: {
  value: LatLon;
  onChange: (p: LatLon) => void;
  height?: number;
  label: string;
}) {
  const markerRef = useRef<L.Marker | null>(null);
  const handlers = useMemo(
    () => ({
      dragend() {
        const m = markerRef.current;
        if (m) {
          const p = m.getLatLng();
          onChange({ lat: p.lat, lon: p.lng });
        }
      },
    }),
    [onChange],
  );

  return (
    <div role="group" aria-label={label} style={{ border: "1px solid var(--border-strong)" }}>
      <MapContainer center={[value.lat, value.lon]} zoom={17} style={{ height }} scrollWheelZoom={false}>
        <BaseLayers />
        <Marker
          position={[value.lat, value.lon]}
          draggable
          eventHandlers={handlers}
          ref={markerRef}
          keyboard
          title={label}
        />
        <ClickToMove onChange={onChange} />
        <Recenter value={value} />
      </MapContainer>
    </div>
  );
}

/** Read-only small map with a pin, for detail pages. */
export function MapView({ lat, lon, height = 220, label }: { lat: number; lon: number; height?: number; label: string }) {
  return (
    <div role="img" aria-label={label} style={{ border: "1px solid var(--border-strong)" }}>
      <MapContainer
        center={[lat, lon]}
        zoom={16}
        style={{ height }}
        scrollWheelZoom={false}
        dragging={false}
        zoomControl={false}
        attributionControl
      >
        <BaseLayers />
        <Marker position={[lat, lon]} />
      </MapContainer>
    </div>
  );
}
