import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get, post } from "../api/client";
import { useTranslation } from "react-i18next";
import s from "./frame.module.css";
import { FOOTER_HELP, FOOTER_POLICIES } from "./nav";

const BUILD_DATE = new Date(__BUILD_DATE__);

const VISIT_KEY = "cf.visited";

/** Counts this browser session once (POST /public/visit), otherwise reads the count. */
function useVisitors(): number | null {
  const [n, setN] = useState<number | null>(null);
  useEffect(() => {
    const req = sessionStorage.getItem(VISIT_KEY)
      ? get<{ visits: number }>("/public/stats")
      : post<{ visits: number }>("/public/visit").then((r) => {
          sessionStorage.setItem(VISIT_KEY, "1");
          return r;
        });
    req.then((r) => setN(r.visits)).catch(() => setN(null));
  }, []);
  return n;
}

/** Dark GIGW footer. The visitor count is hidden if the API cannot provide it. */
export function Footer() {
  const { t, i18n } = useTranslation();
  const visitors = useVisitors();
  const lastUpdated = BUILD_DATE.toLocaleDateString(i18n.language === "kn" ? "kn-IN" : "en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });

  return (
    <footer className={`${s.footer} no-print`}>
      <div className={`container ${s.footerCols}`}>
        <div>
          <h2 className={s.footerHeading}>{t("footer.policies")}</h2>
          <ul className={s.footerList}>
            {FOOTER_POLICIES.map((l) => (
              <li key={l.key}>
                <Link className={s.footerLink} to={l.to}>
                  {t(`footer.${l.key}`)}
                </Link>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h2 className={s.footerHeading}>{t("footer.help")}</h2>
          <ul className={s.footerList}>
            {FOOTER_HELP.map((l) => (
              <li key={l.key}>
                <Link className={s.footerLink} to={l.to}>
                  {t(`footer.${l.key}`)}
                </Link>
              </li>
            ))}
            <li>
              <Link className={s.footerLink} to="/screen-reader-access">
                {t("strip.screenReader")}
              </Link>
            </li>
          </ul>
        </div>
        <div>
          <h2 className={s.footerHeading}>{t("header.nameEn")}</h2>
          <p lang="kn">{t("header.nameKn")}</p>
          <p>{t("footer.contactLine")}</p>
        </div>
      </div>
      <div className={`container ${s.footerBottom}`}>
        <span>{t("footer.owned")}</span>
        <span>
          {t("footer.lastUpdated")}: {lastUpdated}
          {visitors !== null ? (
            <>
              {" | "}
              {t("footerX.visitors")}: {visitors.toLocaleString("en-IN")}
            </>
          ) : null}
        </span>
      </div>
    </footer>
  );
}
