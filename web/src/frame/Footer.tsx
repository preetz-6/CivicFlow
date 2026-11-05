import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import s from "./frame.module.css";
import { FOOTER_HELP, FOOTER_POLICIES } from "./nav";

const BUILD_DATE = new Date(__BUILD_DATE__);

/**
 * Dark GIGW footer. "Visitors" is not shown until the backend exposes a real
 * counter (see docs/REQUESTS_FOR_A.md); a made-up number would be for show.
 */
export function Footer() {
  const { t, i18n } = useTranslation();
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
        </span>
      </div>
    </footer>
  );
}
