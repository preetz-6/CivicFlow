import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get, post } from "../api/client";
import { useTranslation } from "react-i18next";
import s from "./frame.module.css";

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

/** One-line GIGW footer: copyright · Accessibility · Visitors. The count is hidden if the API cannot provide it. */
export function Footer() {
  const { t } = useTranslation();
  const visitors = useVisitors();

  return (
    <footer className={`${s.footer} no-print`}>
      <div className={`container ${s.footerRow}`}>
        <span>{t("footer.copyrightLine")}</span>
        <span aria-hidden="true">·</span>
        <Link className={s.footerLink} to="/accessibility-statement">
          {t("footer.accessibilityLink")}
        </Link>
        {visitors !== null ? (
          <>
            <span aria-hidden="true">·</span>
            <span>
              {t("footerX.visitors")}: {visitors.toLocaleString("en-IN")}
            </span>
          </>
        ) : null}
      </div>
    </footer>
  );
}
