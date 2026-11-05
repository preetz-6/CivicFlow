import { useCallback, useEffect, useState } from "react";
import { get, post } from "../../api/client";
import { fmtDateTime } from "../../api/public";
import type { AgencyReferral } from "../../api/types";
import { ErrorBox } from "../../ui/ErrorBox";
import o from "../officer/officer.module.css";

const STATUSES: [string, string][] = [
  ["ACKNOWLEDGED", "Acknowledged"],
  ["IN_PROGRESS", "Work in progress"],
  ["RESOLVED", "Resolved"],
];

/**
 * External Agency Inbox (Simulated). There is no real link to BESCOM or BWSSB:
 * during the demo the presenter plays the agency here and replies to referrals.
 */
export function AgencyInbox() {
  const [agency, setAgency] = useState("");
  const [items, setItems] = useState<AgencyReferral[] | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async () => {
    try {
      setItems(await get<AgencyReferral[]>(`/agency/inbox${agency ? `?agency=${encodeURIComponent(agency)}` : ""}`));
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, [agency]);

  useEffect(() => {
    document.title = "External Agency Inbox (Simulated)";
    void load();
    const timer = window.setInterval(() => void load(), 15_000);
    return () => window.clearInterval(timer);
  }, [load]);

  return (
    <>
      <h1>External Agency Inbox (Simulated)</h1>
      <p className="notice">
        <strong>Simulated.</strong> CivicFlow has no real connection to BESCOM or BWSSB. This page plays the agency side:
        it shows the referrals and follow-ups the Corporation sent, and lets you reply as the agency.
      </p>
      <div className={o.filters} style={{ marginBottom: 16 }}>
        <label htmlFor="inbox-agency">
          Agency
          <select
            id="inbox-agency" value={agency} onChange={(e) => setAgency(e.target.value)}>
            <option value="">All</option>
            <option value="BESCOM">BESCOM (electricity)</option>
            <option value="BWSSB">BWSSB (water and sewerage)</option>
          </select>
        </label>
      </div>
      <ErrorBox error={error} />
      {items && items.length === 0 ? <p className="notice">No referrals have been sent to this agency.</p> : null}
      {(items ?? []).map((r) => (
        <ReferralPanel key={r.id} r={r} onChanged={load} />
      ))}
    </>
  );
}

function ReferralPanel({ r, onChanged }: { r: AgencyReferral; onChanged: () => Promise<void> }) {
  const [status, setStatus] = useState("ACKNOWLEDGED");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const done = r.agency_status === "RESOLVED";

  async function reply() {
    setBusy(true);
    setError(null);
    try {
      await post(`/agency/referrals/${r.id}/reply`, { status, message: message.trim() });
      setNotice(`Reply sent as ${r.agency}.`);
      setMessage("");
      await onChanged();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={o.panel} aria-labelledby={`ref-${r.id}`}>
      <h2 id={`ref-${r.id}`} className={o.panelTitle}>
        {r.agency}: referral {r.id} ({r.sr_id})
        <span className={o.panelMeta}>
          {r.agency_status ? `Agency status: ${r.agency_status.replace(/_/g, " ")}` : "No reply yet"}
          {r.followups_sent ? `, ${r.followups_sent} follow-up${r.followups_sent > 1 ? "s" : ""} received` : ""}
        </span>
      </h2>
      <div className={o.panelBody}>
        <table className="kv">
          <tbody>
            <tr>
              <th scope="row">Problem</th>
              <td>
                {r.category.replace(/_/g, " ")}: {r.description}
              </td>
            </tr>
            <tr>
              <th scope="row">Why referred</th>
              <td>{r.reason ?? "-"}</td>
            </tr>
            <tr>
              <th scope="row">Sent</th>
              <td>{r.sent_at ? fmtDateTime(r.sent_at) : "-"}</td>
            </tr>
          </tbody>
        </table>
        {r.messages.length ? (
          <>
            <h3>Messages</h3>
            <ol className={o.rationale}>
              {r.messages.map((m, i) => (
                <li key={i}>
                  <strong>{m.direction === "OUT" ? "From the Corporation" : `From ${r.agency}`}</strong>{" "}
                  <span className="muted">({fmtDateTime(m.at)})</span>: {m.body}
                </li>
              ))}
            </ol>
          </>
        ) : null}
        {notice ? (
          <p className="notice notice-success" role="status">
            {notice}
          </p>
        ) : null}
        <ErrorBox error={error} />
        {!done ? (
          <form
            className={o.formBox}
            onSubmit={(e) => {
              e.preventDefault();
              void reply();
            }}
          >
            <label htmlFor={`inbox-reply-as-r-agency-status-${r.id}`}>
              <span className="required">Reply as {r.agency}: status</span>
              <select
                id={`inbox-reply-as-r-agency-status-${r.id}`} value={status} onChange={(e) => setStatus(e.target.value)}>
                {STATUSES.map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </select>
            </label>
            <label htmlFor={`inbox-message-${r.id}`}>
              <span className="required">Message</span>
              <textarea
                id={`inbox-message-${r.id}`}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="e.g. Feeder fault identified; repair crew will attend tomorrow by 11 am."
                required
              />
            </label>
            <button type="submit" className="btn" disabled={busy || !message.trim()}>
              Send reply as {r.agency}
            </button>
          </form>
        ) : (
          <p className="notice notice-success">The agency has reported this as resolved.</p>
        )}
      </div>
    </section>
  );
}
