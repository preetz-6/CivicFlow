import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import s from "./frame.module.css";

export interface Crumb {
  label: string;
  to?: string;
}

/** Breadcrumbs for every inner page. "Home" is added automatically. */
export function Breadcrumbs({ items }: { items: Crumb[] }) {
  const { t } = useTranslation();
  const all: Crumb[] = [{ label: t("breadcrumb.home"), to: "/" }, ...items];
  return (
    <nav className={`${s.crumbs} no-print`} aria-label={t("breadcrumb.label")}>
      <ol>
        {all.map((c, i) => {
          const last = i === all.length - 1;
          return (
            <li key={`${c.label}-${i}`}>
              {last || !c.to ? (
                <span aria-current={last ? "page" : undefined}>{c.label}</span>
              ) : (
                <Link to={c.to}>{c.label}</Link>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
