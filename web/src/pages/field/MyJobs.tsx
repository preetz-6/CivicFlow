import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get } from "../../api/client";
import { fmtDateTime } from "../../api/public";
import type { FieldJob } from "../../api/types";
import { ErrorBox } from "../../ui/ErrorBox";
import { PriorityTag, StatusTag } from "../../ui/StatusTag";
import f from "./field.module.css";

/** Field Team: my work orders, rework first. Large touch targets for phones. */
export function MyJobs() {
  const [jobs, setJobs] = useState<FieldJob[] | null>(null);
  const [includeDone, setIncludeDone] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    document.title = "My Jobs | Field Team";
  }, []);

  const load = useCallback(async () => {
    try {
      setJobs(await get<FieldJob[]>(`/field/jobs${includeDone ? "?include_done=true" : ""}`));
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, [includeDone]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <>
      <h1>My Jobs</h1>
      <div className={f.toolbar}>
        <label className={f.check}>
          <input type="checkbox" checked={includeDone} onChange={(e) => setIncludeDone(e.target.checked)} />
          Show verified jobs
        </label>
        <button type="button" className={`btn btn-secondary ${f.big}`} onClick={() => void load()}>
          Refresh
        </button>
      </div>
      <ErrorBox error={error} />
      {jobs && jobs.length === 0 ? <p className="notice">No jobs assigned to your crew right now.</p> : null}
      <ul className={f.list}>
        {(jobs ?? []).map((j) => (
          <li key={j.id}>
            <Link to={`/field/jobs/${encodeURIComponent(j.id)}`} className={`${f.job} ${j.status === "REWORK" ? f.rework : ""}`}>
              <div className={f.jobTop}>
                <strong>{j.id}</strong>
                <span>
                  <PriorityTag priority={j.priority} /> <StatusTag status={j.status} />
                </span>
              </div>
              <div className={f.jobCat}>{j.category_label}</div>
              <div>{j.landmark || j.address || `${j.lat.toFixed(5)}, ${j.lon.toFixed(5)}`}</div>
              {j.status === "REWORK" && j.rework_reason ? (
                <div className={f.reworkReason}>Sent back: {j.rework_reason}</div>
              ) : null}
              <div className="muted">Assigned {fmtDateTime(j.assigned_at)}</div>
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}
