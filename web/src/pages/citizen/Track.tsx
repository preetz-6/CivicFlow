import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { get, post } from "../../api/client";
import { fmtDate, fmtDateTime } from "../../api/public";
import type { AttachmentOut, TrackView } from "../../api/types";
import { Breadcrumbs } from "../../frame/Breadcrumbs";
import { ErrorBox } from "../../ui/ErrorBox";
import { Field, Fieldset } from "../../ui/Fieldset";
import { MapView } from "../../ui/MapPicker";
import { StarRating } from "../../ui/StarRating";
import { EscalationBadge, PriorityTag, StatusTag } from "../../ui/StatusTag";
import { Stepper } from "../../ui/Stepper";
import { Timeline } from "../../ui/Timeline";

interface TrackState {
  no?: string;
  code?: string;
}

function Photos({ title, photos, lang }: { title: string; photos: AttachmentOut[]; lang: string }) {
  if (photos.length === 0) return null;
  return (
    <div>
      <h3>{title}</h3>
      <div className="photo-grid">
        {photos.map((p) => (
          <figure key={p.id}>
            <a href={p.url} target="_blank" rel="noreferrer">
              <img src={p.url} alt={title} loading="lazy" />
            </a>
            <figcaption className="muted">{fmtDateTime(p.exif_time ?? p.uploaded_at, lang)}</figcaption>
          </figure>
        ))}
      </div>
    </div>
  );
}

/**
 * Track Grievance: Grievance No. + mobile number or tracking code.
 * The code is never put in the URL; the acknowledgement slip passes it in
 * router state, and the header search passes only the Grievance No.
 */
export function Track() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const location = useLocation();
  const [params] = useSearchParams();
  const initial = (location.state as TrackState | null) ?? {};

  const [no, setNo] = useState(initial.no ?? params.get("no") ?? "");
  const [code, setCode] = useState(initial.code ?? "");
  const [view, setView] = useState<TrackView | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");
  const [reopenReason, setReopenReason] = useState("");
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);
  const autoRan = useRef(false);

  // Header search on this page: pick up the new Grievance No.
  const paramNo = params.get("no");
  useEffect(() => {
    if (paramNo) {
      setNo(paramNo);
      setView(null);
    }
  }, [paramNo]);

  useEffect(() => {
    document.title = `${t("track.title")} | ${t("header.nameEn")}`;
  }, [t]);

  const load = useCallback(async (grievanceNo: string, trackCode: string) => {
    setBusy(true);
    setError(null);
    try {
      const q = new URLSearchParams({ no: grievanceNo.trim().toUpperCase(), code: trackCode.trim() });
      setView(await get<TrackView>(`/complaints/track?${q.toString()}`));
    } catch (e) {
      setView(null);
      setError(e);
    } finally {
      setBusy(false);
    }
  }, []);

  // Arriving from the acknowledgement slip: look it up straight away.
  useEffect(() => {
    if (!autoRan.current && initial.no && initial.code) {
      autoRan.current = true;
      void load(initial.no, initial.code);
    }
  }, [initial.no, initial.code, load]);

  function submit(e: FormEvent) {
    e.preventDefault();
    setNotice(null);
    void load(no, code);
  }

  async function confirm(e: FormEvent) {
    e.preventDefault();
    if (!view) return;
    setActionBusy(true);
    setActionError(null);
    try {
      await post(`/complaints/${encodeURIComponent(view.grievance_no)}/confirm`, {
        code: code.trim(),
        rating: rating || null,
        comment: comment.trim() || null,
      });
      setNotice(t("track.confirmed"));
      await load(view.grievance_no, code);
    } catch (err) {
      setActionError(err);
    } finally {
      setActionBusy(false);
    }
  }

  async function reopen(e: FormEvent) {
    e.preventDefault();
    if (!view) return;
    setActionBusy(true);
    setActionError(null);
    try {
      await post(`/complaints/${encodeURIComponent(view.grievance_no)}/reopen`, {
        code: code.trim(),
        reason: reopenReason.trim(),
      });
      setNotice(t("track.reopened"));
      setReopenReason("");
      await load(view.grievance_no, code);
    } catch (err) {
      setActionError(err);
    } finally {
      setActionBusy(false);
    }
  }

  const kn = lang === "kn";

  return (
    <>
      <Breadcrumbs items={[{ label: t("track.title") }]} />
      <h1>{t("track.title")}</h1>

      <form onSubmit={submit} style={{ maxWidth: 760 }}>
        <Fieldset legend={t("track.legend")}>
          <Field label={t("track.no")} htmlFor="track-no" required hint={t("track.noHint")}>
            <input
              id="track-no"
              value={no}
              onChange={(e) => setNo(e.target.value)}
              autoComplete="off"
              aria-describedby="track-no-hint"
              required
            />
          </Field>
          <Field label={t("track.code")} htmlFor="track-code" required>
            <input
              id="track-code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              autoComplete="off"
              required
            />
          </Field>
        </Fieldset>
        <button type="submit" className="btn" disabled={busy || !no.trim() || !code.trim()}>
          {t("track.submit")}
        </button>
      </form>

      <div style={{ marginTop: 16 }}>
        <ErrorBox error={error} />
        {notice ? (
          <p className="notice notice-success" role="status">
            {notice}
          </p>
        ) : null}
      </div>

      {view ? (
        <>
          <section className="section">
            <h2>{t("track.status")}</h2>
            <Stepper status={view.status} />
            <table className="kv">
              <tbody>
                <tr>
                  <th scope="row">{t("track.no")}</th>
                  <td>
                    <strong>{view.grievance_no}</strong>
                  </td>
                </tr>
                <tr>
                  <th scope="row">{t("ack.status")}</th>
                  <td>
                    <StatusTag status={view.status} /> <EscalationBadge level={view.escalation_level} />
                  </td>
                </tr>
                {view.merged_into ? (
                  <tr>
                    <th scope="row">{t("track.mergedInto")}</th>
                    <td>
                      {view.merged_into}
                      {(view as { merge_reason?: string | null }).merge_reason ? (
                        <div className="muted" style={{ marginTop: 4 }}>
                          {t("track.mergeWhy")}: {(view as { merge_reason?: string | null }).merge_reason}
                        </div>
                      ) : null}
                    </td>
                  </tr>
                ) : null}
                <tr>
                  <th scope="row">{t("ack.category")}</th>
                  <td>{kn ? view.category_label_kn : view.category_label}</td>
                </tr>
                <tr>
                  <th scope="row">{t("track.description")}</th>
                  <td>{view.description}</td>
                </tr>
                <tr>
                  <th scope="row">{t("track.submitted")}</th>
                  <td>{fmtDateTime(view.submitted_at, lang)}</td>
                </tr>
                <tr>
                  <th scope="row">{t("ack.ward")}</th>
                  <td>{(kn && view.ward_name_kn) || view.ward_name || "-"}</td>
                </tr>
                <tr>
                  <th scope="row">{t("ack.department")}</th>
                  <td>{(kn && view.department_name_kn) || view.department_name || "-"}</td>
                </tr>
                <tr>
                  <th scope="row">{t("track.priority")}</th>
                  <td>
                    <PriorityTag priority={view.priority} />
                  </td>
                </tr>
                <tr>
                  <th scope="row">{t("ack.expected")}</th>
                  <td>{fmtDate(view.expected_resolution, lang)}</td>
                </tr>
                <tr>
                  <th scope="row">{t("track.reporters")}</th>
                  <td>{view.reporter_count}</td>
                </tr>
                {view.landmark ? (
                  <tr>
                    <th scope="row">{t("lodge.landmark")}</th>
                    <td>{view.landmark}</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
            <div style={{ maxWidth: 520 }}>
              <MapView lat={view.lat} lon={view.lon} label={t("lodge.location")} />
            </div>
          </section>

          <section className="section">
            <h2>{t("track.timeline")}</h2>
            <Timeline
              locale={kn ? "kn-IN" : "en-IN"}
              entries={view.timeline.map((e) => ({
                at: e.at,
                stage: kn && e.stage_kn ? e.stage_kn : e.stage,
                remarks: kn && e.remarks_kn ? e.remarks_kn : e.remarks,
                actor: e.actor_type,
              }))}
            />
          </section>

          <section className="section">
            <h2>{t("track.photos")}</h2>
            {view.citizen_photos.length + view.before_photos.length + view.after_photos.length === 0 ? (
              <p className="muted">{t("track.noPhotos")}</p>
            ) : (
              <>
                <Photos title={t("track.citizenPhotos")} photos={view.citizen_photos} lang={lang} />
                <Photos title={t("track.before")} photos={view.before_photos} lang={lang} />
                <Photos title={t("track.after")} photos={view.after_photos} lang={lang} />
              </>
            )}
          </section>

          {view.feedback_rating ? <p className="notice">{t("track.rated", { n: view.feedback_rating })}</p> : null}

          {view.can_confirm || view.can_reopen ? (
            <section className="section" style={{ maxWidth: 760 }}>
              <ErrorBox error={actionError} />
              <p>{t("track.confirmText")}</p>
              {view.can_confirm ? (
                <form onSubmit={(e) => void confirm(e)}>
                  <Fieldset legend={t("track.confirmLegend")}>
                    <div style={{ gridColumn: "1 / -1" }}>
                      <StarRating
                        value={rating}
                        onChange={setRating}
                        label={t("track.rating")}
                        starLabel={(n) => t("track.stars", { n })}
                      />
                    </div>
                    <Field label={t("track.comment")} htmlFor="comment" wide>
                      <textarea
                        id="comment"
                        value={comment}
                        onChange={(e) => setComment(e.target.value)}
                        maxLength={1000}
                      />
                    </Field>
                  </Fieldset>
                  <button type="submit" className="btn" disabled={actionBusy}>
                    {t("track.confirm")}
                  </button>
                </form>
              ) : null}
              {view.can_reopen ? (
                <form onSubmit={(e) => void reopen(e)} style={{ marginTop: 24 }}>
                  <Fieldset legend={t("track.reopenLegend")}>
                    <Field label={t("track.reopenReason")} htmlFor="reopen-reason" required wide>
                      <textarea
                        id="reopen-reason"
                        value={reopenReason}
                        onChange={(e) => setReopenReason(e.target.value)}
                        minLength={5}
                        maxLength={1000}
                        required
                      />
                    </Field>
                  </Fieldset>
                  <button
                    type="submit"
                    className="btn btn-danger"
                    disabled={actionBusy || reopenReason.trim().length < 5}
                  >
                    {t("track.reopen")}
                  </button>
                </form>
              ) : null}
            </section>
          ) : null}

          <p className="no-print">
            <Link to="/lodge">{t("ack.another")}</Link>
          </p>
        </>
      ) : null}
    </>
  );
}
