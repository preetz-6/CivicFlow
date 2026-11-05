import { useEffect, useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ackKey, fmtDate, fmtDateTime } from "../../api/public";
import type { AckSlip } from "../../api/types";
import { Breadcrumbs } from "../../frame/Breadcrumbs";
import { Crest } from "../../frame/Crest";
import { StatusTag } from "../../ui/StatusTag";
import a from "./ack.module.css";

/**
 * Acknowledgement Slip. The slip (with the tracking code) is kept in this
 * browser session only, never in the URL.
 */
export function Ack() {
  const { t, i18n } = useTranslation();
  const { no = "" } = useParams();
  const ack = useMemo<AckSlip | null>(() => {
    const raw = sessionStorage.getItem(ackKey(no));
    try {
      return raw ? (JSON.parse(raw) as AckSlip) : null;
    } catch {
      return null;
    }
  }, [no]);
  const lang = i18n.language;

  useEffect(() => {
    document.title = `${t("ack.title")} ${no} | ${t("header.nameEn")}`;
  }, [t, no]);

  return (
    <>
      <Breadcrumbs items={[{ label: t("lodge.title"), to: "/lodge" }, { label: t("ack.title") }]} />
      <h1 className="no-print">{t("ack.title")}</h1>
      {!ack ? (
        <p className="notice">
          {t("ack.missing")} <Link to="/track">{t("track.title")}</Link>
        </p>
      ) : (
        <>
          <div className={a.slip}>
            <div className={a.slipHead}>
              <Crest size={56} label={t("header.crestAlt")} />
              <div>
                <div className={a.org}>{t("header.nameEn")}</div>
                <div className={a.org} lang="kn">
                  {t("header.nameKn")}
                </div>
                <div className={a.slipTitle}>{t("ack.heading")}</div>
              </div>
            </div>
            <p className="notice notice-success">{t("ack.thanks")}</p>
            <table className="kv">
              <tbody>
                <tr>
                  <th scope="row">{t("ack.no")}</th>
                  <td className={a.big}>{ack.grievance_no}</td>
                </tr>
                <tr>
                  <th scope="row">{t("ack.code")}</th>
                  <td>
                    <span className={a.big}>{ack.tracking_code}</span>
                    <div className="muted">{t("ack.codeNote")}</div>
                  </td>
                </tr>
                <tr>
                  <th scope="row">{t("ack.date")}</th>
                  <td>{fmtDateTime(ack.submitted_at, lang)}</td>
                </tr>
                <tr>
                  <th scope="row">{t("ack.category")}</th>
                  <td>{lang === "kn" ? ack.category_label_kn : ack.category_label}</td>
                </tr>
                <tr>
                  <th scope="row">{t("ack.ward")}</th>
                  <td>{ack.ward_name ?? t("ack.pending")}</td>
                </tr>
                <tr>
                  <th scope="row">{t("ack.department")}</th>
                  <td>{ack.department_name ?? t("ack.pending")}</td>
                </tr>
                <tr>
                  <th scope="row">{t("ack.expected")}</th>
                  <td>{ack.expected_resolution ? fmtDate(ack.expected_resolution, lang) : t("ack.pending")}</td>
                </tr>
                <tr>
                  <th scope="row">{t("ack.status")}</th>
                  <td>
                    <StatusTag status={ack.status} />
                  </td>
                </tr>
              </tbody>
            </table>
            <p className={`muted ${a.printOnly}`}>{t("banner.prototype")}</p>
          </div>
          <div className="actions no-print">
            <button type="button" className="btn" onClick={() => window.print()}>
              {t("ack.print")}
            </button>
            <Link
              className="btn btn-secondary"
              to="/track"
              state={{ no: ack.grievance_no, code: ack.tracking_code }}
            >
              {t("ack.track")}
            </Link>
            <Link className="btn btn-secondary" to="/lodge">
              {t("ack.another")}
            </Link>
          </div>
        </>
      )}
    </>
  );
}
