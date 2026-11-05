import { useEffect } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import h from "./home.module.css";

/**
 * Home, step 1 version: welcome text and notices. Step 2 adds the quick-service
 * tiles (Lodge, Track, Report Pothole, Charter, Ward Officers) and the
 * statistics strip from GET /public/stats, once those pages and the endpoint exist.
 */
export function Home() {
  const { t } = useTranslation();
  useEffect(() => {
    document.title = `${t("header.nameEn")} | ${t("header.subtitle")}`;
  }, [t]);

  return (
    <div className={h.grid}>
      <section>
        <h1 style={{ marginTop: 24 }}>{t("home.title")}</h1>
        <p>{t("home.intro")}</p>
      </section>
      <aside className={h.box} aria-labelledby="notices-h">
        <h2 id="notices-h" className={h.boxTitle}>
          {t("home.notices")}
        </h2>
        <ul className={h.boxList}>
          <li>{t("home.noticeDemo")}</li>
          <li>
            <Link to="/citizen-charter">{t("nav.charter")}</Link>
          </li>
          <li>
            <Link to="/faqs">{t("nav.faqs")}</Link>
          </li>
        </ul>
      </aside>
    </div>
  );
}
