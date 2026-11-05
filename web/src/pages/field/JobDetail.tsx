import { useCallback, useEffect, useState, type ChangeEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { get, post } from "../../api/client";
import { fmtDateTime } from "../../api/public";
import type { AttachmentOut, FieldJob } from "../../api/types";
import { ErrorBox } from "../../ui/ErrorBox";
import { MapView } from "../../ui/MapPicker";
import { PriorityTag, StatusTag } from "../../ui/StatusTag";
import f from "./field.module.css";

const DEMO_VARIANTS: [string, string][] = [
  ["before", "Before photo"],
  ["after_good", "After photo (correct)"],
  ["after_far", "After photo (taken 2 km away)"],
  ["after_old", "After photo (taken before assignment)"],
  ["after_noexif", "After photo (no EXIF)"],
  ["after_reused", "After photo (reused from another job)"],
];

function PhotoList({ photos }: { photos: AttachmentOut[] }) {
  if (!photos.length) return <p className="muted">None yet.</p>;
  return (
    <div className="photo-grid">
      {photos.map((p) => (
        <figure key={p.id}>
          <a href={p.url} target="_blank" rel="noreferrer">
            <img src={p.url} alt={`${p.kind} photo`} loading="lazy" />
          </a>
          <figcaption>
            <strong>{p.kind}</strong> uploaded {fmtDateTime(p.uploaded_at)}
            <br />
            {p.exif_time ? `Taken ${fmtDateTime(p.exif_time)}` : "No time in photo"}
            {", "}
            {p.exif_lat !== null && p.exif_lat !== undefined && p.exif_lon !== null && p.exif_lon !== undefined
              ? `GPS ${p.exif_lat.toFixed(5)}, ${p.exif_lon.toFixed(5)}`
              : "no GPS in photo"}
          </figcaption>
        </figure>
      ))}
    </div>
  );
}

/** One work order for the field team. Never shows citizen contact details. */
export function JobDetail() {
  const { id = "" } = useParams();
  const [job, setJob] = useState<FieldJob | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [demoPhotos, setDemoPhotos] = useState(false);

  const load = useCallback(async () => {
    try {
      setJob(await get<FieldJob>(`/field/jobs/${encodeURIComponent(id)}`));
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, [id]);

  useEffect(() => {
    document.title = `${id} | Field Team`;
    void load();
  }, [id, load]);

  // The auto-check runs in the background after "Mark completed"; poll until it has a result.
  const waitingForAudit = job?.status === "COMPLETED" && !job.audit_verdict;
  useEffect(() => {
    if (!waitingForAudit) return;
    const timer = window.setInterval(() => void load(), 3000);
    return () => window.clearInterval(timer);
  }, [waitingForAudit, load]);

  // Demo-mode test photos exist only when the backend serves them; check once.
  useEffect(() => {
    let alive = true;
    fetch(`/api/v1/demo/photos/before.jpg?wo_id=${encodeURIComponent(id)}`, { credentials: "include" })
      .then((r) => alive && setDemoPhotos(r.ok))
      .catch(() => alive && setDemoPhotos(false));
    return () => {
      alive = false;
    };
  }, [id]);

  async function run(path: string, message: string) {
    setBusy(true);
    setActionError(null);
    setNotice(null);
    try {
      setJob(await post<FieldJob>(`/field/jobs/${encodeURIComponent(id)}${path}`));
      setNotice(message);
    } catch (e) {
      setActionError(e);
    } finally {
      setBusy(false);
    }
  }

  async function upload(kind: "BEFORE" | "AFTER", e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setBusy(true);
    setActionError(null);
    setNotice(null);
    const fd = new FormData();
    fd.append("kind", kind);
    fd.append("photo", file, file.name); // original file, unchanged, so EXIF time/GPS survive
    try {
      await post<AttachmentOut>(`/field/jobs/${encodeURIComponent(id)}/photos`, fd);
      await load();
      setNotice(`${kind === "BEFORE" ? "Before" : "After"} photo uploaded.`);
    } catch (err) {
      setActionError(err);
    } finally {
      setBusy(false);
    }
  }

  if (error && !job) {
    return (
      <>
        <p>
          <Link to="/field">My Jobs</Link>
        </p>
        <ErrorBox error={error} />
      </>
    );
  }
  if (!job) return <p className="muted">Loading...</p>;

  const before = job.photos.filter((p) => p.kind === "BEFORE");
  const after = job.photos.filter((p) => p.kind === "AFTER");
  const started = job.started_at ? new Date(job.started_at).getTime() : null;
  const afterSinceStart = after.some((p) => started === null || new Date(p.uploaded_at).getTime() >= started);
  const osm = `https://www.openstreetmap.org/?mlat=${job.lat}&mlon=${job.lon}#map=18/${job.lat}/${job.lon}`;

  return (
    <>
      <p style={{ marginTop: 0 }}>
        <Link to="/field">My Jobs</Link> &raquo; {job.id}
      </p>
      <h1>{job.id}</h1>
      <p>
        <PriorityTag priority={job.priority} /> <StatusTag status={job.status} />
      </p>

      {job.status === "REWORK" ? (
        <div className="notice notice-error" role="alert">
          <strong>Sent back for rework{job.rework_count > 1 ? ` (${job.rework_count} times)` : ""}:</strong>{" "}
          {job.rework_reason ?? "See the auto-check result."}
          <div>Restart the job, fix the issue, and upload a new after-photo taken at the site.</div>
        </div>
      ) : null}
      {notice ? (
        <p className="notice notice-success" role="status">
          {notice}
        </p>
      ) : null}
      <ErrorBox error={actionError} />

      <div className={f.actions}>
        {job.status === "ASSIGNED" ? (
          <button type="button" className={`btn ${f.big}`} disabled={busy} onClick={() => void run("/start", "Job started.")}>
            Start job
          </button>
        ) : null}
        {job.status === "REWORK" ? (
          <button
            type="button"
            className={`btn ${f.big}`}
            disabled={busy}
            onClick={() => void run("/resume", "Job restarted.")}
          >
            Restart job
          </button>
        ) : null}
        {["ASSIGNED", "IN_PROGRESS"].includes(job.status) ? (
          <label className={`btn btn-secondary ${f.big} ${f.fileBtn}`}>
            Upload before photo
            <input
              type="file"
              accept="image/jpeg,image/png"
              capture="environment"
              className="visually-hidden"
              disabled={busy}
              onChange={(e) => void upload("BEFORE", e)}
            />
          </label>
        ) : null}
        {job.status === "IN_PROGRESS" ? (
          <>
            <label className={`btn btn-secondary ${f.big} ${f.fileBtn}`}>
              Upload after photo
              <input
                type="file"
                accept="image/jpeg,image/png"
                capture="environment"
                className="visually-hidden"
                disabled={busy}
                onChange={(e) => void upload("AFTER", e)}
              />
            </label>
            <button
              type="button"
              className={`btn ${f.big}`}
              disabled={busy || !afterSinceStart}
              title={afterSinceStart ? undefined : "Upload an after-photo first"}
              onClick={() => void run("/complete", "Marked completed. The completion photo is being auto-checked.")}
            >
              Mark completed
            </button>
          </>
        ) : null}
      </div>
      {job.status === "IN_PROGRESS" && !afterSinceStart ? (
        <p className="muted">Upload an after-photo taken at the site before marking the job completed.</p>
      ) : null}
      {job.status === "COMPLETED" ? (
        <p className="notice">
          Completed. Waiting for the auto-check and Control Room verification.
          {job.audit_verdict ? (
            <>
              {" "}
              Auto-check result: <strong>{job.audit_verdict}</strong>
              {job.audit_score !== null ? ` (${job.audit_score}/100)` : ""}.
            </>
          ) : null}
        </p>
      ) : null}
      {job.status === "ON_HOLD" ? <p className="notice">This job is on hold. Your ward officer will resume it.</p> : null}

      <h2>Job details</h2>
      <table className="kv">
        <tbody>
          <tr>
            <th scope="row">Grievance</th>
            <td>
              {job.sr_id} ({job.category_label})
            </td>
          </tr>
          <tr>
            <th scope="row">Problem</th>
            <td>{job.description}</td>
          </tr>
          <tr>
            <th scope="row">Scope of work</th>
            <td>{job.scope}</td>
          </tr>
          {job.root_cause ? (
            <tr>
              <th scope="row">Root cause</th>
              <td>{job.root_cause}</td>
            </tr>
          ) : null}
          <tr>
            <th scope="row">Location</th>
            <td>
              {[job.landmark, job.address].filter(Boolean).join(", ") || "-"}
              <div>
                <a href={osm} target="_blank" rel="noreferrer">
                  Open in map ({job.lat.toFixed(5)}, {job.lon.toFixed(5)})
                </a>
              </div>
            </td>
          </tr>
          <tr>
            <th scope="row">Assigned</th>
            <td>{fmtDateTime(job.assigned_at)}</td>
          </tr>
          {job.started_at ? (
            <tr>
              <th scope="row">Started</th>
              <td>{fmtDateTime(job.started_at)}</td>
            </tr>
          ) : null}
        </tbody>
      </table>
      <MapView lat={job.lat} lon={job.lon} label={`Location of ${job.id}`} height={200} />

      <h2 style={{ marginTop: 24 }}>Photos</h2>
      <h3>From the citizen</h3>
      <PhotoList photos={job.citizen_photos} />
      <h3>Before</h3>
      <PhotoList photos={before} />
      <h3>After</h3>
      <PhotoList photos={after} />

      {demoPhotos ? (
        <details className={f.demo}>
          <summary>Demo test photos (Simulated)</summary>
          <p className="muted">
            Download one, then upload it with the buttons above so the real auto-check runs on it.
          </p>
          <ul>
            {DEMO_VARIANTS.map(([v, label]) => (
              <li key={v}>
                <a href={`/api/v1/demo/photos/${v}.jpg?wo_id=${encodeURIComponent(job.id)}`} download={`${job.id}-${v}.jpg`}>
                  {label}
                </a>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </>
  );
}
