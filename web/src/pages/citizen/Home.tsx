import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { get } from "../../api/client";
import type { PublicStats } from "../../api/types";
import h from "./home.module.css";

/* Simple 1.5px line icons (no emoji, no fills), 32x32 */
const Icon = ({ children }: { children: ReactNode }) => (
  <svg width="32" height="32" viewBox="0 0 32 32" aria-hidden="true" focusable="false" className={h.icon}>
    <g fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      {children}
    </g>
  </svg>
);

const ICONS: Record<string, ReactNode> = {
  lodge: (
    <Icon>
      <path d="M8 4h12l5 5v19H8z" />
      <path d="M20 4v5h5M12 15h9M12 19h9M12 23h6" />
    </Icon>
  ),
  track: (
    <Icon>
      <circle cx="14" cy="14" r="8" />
      <path d="M20 20l7 7M14 10v4l3 2" />
    </Icon>
  ),
  pothole: (
    <Icon>
      <path d="M3 22h26M6 26h20" />
      <ellipse cx="16" cy="22" rx="7" ry="2.5" />
      <path d="M16 5l6 11H10z M16 9v3M16 14v.5" />
    </Icon>
  ),
  charter: (
    <Icon>
      <path d="M7 5h18v22H7z" />
      <path d="M11 11h10M11 15h10M11 19h6" />
      <path d="M19 23l2 2 4-4" />
    </Icon>
  ),
  wards: (
    <Icon>
      <circle cx="16" cy="10" r="4" />
      <path d="M8 26c0-5 3.5-8 8-8s8 3 8 8" />
    </Icon>
  ),
};

const TILES = [
  { key: "lodge", to: "/lodge" },
  { key: "track", to: "/track" },
  { key: "pothole", to: "/lodge?category=POTHOLE" },
  { key: "charter", to: "/citizen-charter" },
  { key: "wards", to: "/wards" },
];

export function Home() {
  const { t, i18n } = useTranslation();
  const [stats, setStats] = useState<PublicStats | null>(null);

  useEffect(() => {
    document.title = `${t("header.nameEn")} | ${t("header.subtitle")}`;
  }, [t]);

  useEffect(() => {
    get<PublicStats>("/public/stats")
      .then(setStats)
      .catch(() => setStats(null));
  }, []);

  const num = (n: number | null | undefined, suffix = "") =>
    n === null || n === undefined ? "-" : `${n.toLocaleString(i18n.language === "kn" ? "kn-IN" : "en-IN")}${suffix}`;

  return (
    <>
      <div className={h.grid}>
        <section>
          <h1 style={{ marginTop: 24 }}>{t("home.title")}</h1>
          <p>{t("home.intro")}</p>
          <Link to="/agents" className={h.agentsBtn}>
            <strong>{t("homeX.agents")} →</strong>
            <span>{t("homeX.agentsSub")}</span>
          </Link>

          <h2>{t("homeX.services")}</h2>
          <ul className={h.tiles}>
            {TILES.map((tile) => (
              <li key={tile.key}>
                <Link to={tile.to} className={h.tile}>
                  {ICONS[tile.key]}
                  <span>{t(`homeX.${tile.key}`)}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
        <aside className={h.box} aria-labelledby="notices-h">
          <h2 id="notices-h" className={h.boxTitle}>
            {t("home.notices")}
          </h2>
          <ul className={h.boxList}>
            <li>
              <Link to="/citizen-charter">{t("nav.charter")}</Link>
            </li>
            <li>
              <Link to="/faqs">{t("nav.faqs")}</Link>
            </li>
            <li>
              <Link to="/wards">{t("nav.wards")}</Link>
            </li>
          </ul>
        </aside>
      </div>

      {stats ? (
        <section className={h.statsWrap} aria-labelledby="stats-h">
          <h2 id="stats-h">{t("homeX.stats")}</h2>
          <dl className={h.stats}>
            <div>
              <dt>{t("homeX.total")}</dt>
              <dd>{num(stats.total)}</dd>
            </div>
            <div>
              <dt>{t("homeX.resolved")}</dt>
              <dd>{num(stats.resolved)}</dd>
            </div>
            <div>
              <dt>{t("homeX.withinSla")}</dt>
              <dd>{num(stats.within_sla_pct, "%")}</dd>
            </div>
            <div>
              <dt>{t("homeX.avgDays")}</dt>
              <dd>{num(stats.avg_days)}</dd>
            </div>
          </dl>
          <p className="muted" style={{ fontSize: "var(--fs-sm)" }}>
            {t("homeX.statsNote", { auto: stats.resolved_auto_closed })}
          </p>
        </section>
      ) : null}
    </>
  );
}
