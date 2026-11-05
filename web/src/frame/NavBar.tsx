import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import s from "./frame.module.css";
import { NAV } from "./nav";

export function NavBar() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const location = useLocation();

  // Close the mobile menu after navigating.
  useEffect(() => {
    setOpen(false);
  }, [location.pathname]);

  return (
    <nav className={`${s.nav} ${open ? s.navOpen : ""} no-print`} aria-label={t("nav.label")}>
      <div className="container" style={{ padding: 0 }}>
        <button
          type="button"
          className={s.menuBtn}
          aria-expanded={open}
          aria-controls="cf-main-menu"
          onClick={() => setOpen((v) => !v)}
        >
          <svg width="18" height="14" viewBox="0 0 18 14" aria-hidden="true" focusable="false">
            <rect y="0" width="18" height="2" fill="currentColor" />
            <rect y="6" width="18" height="2" fill="currentColor" />
            <rect y="12" width="18" height="2" fill="currentColor" />
          </svg>
          {t("nav.menu")}
        </button>
        <ul className={s.navList} id="cf-main-menu">
          {NAV.map((item) => (
            <li key={item.key}>
              <NavLink
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) => (isActive ? `${s.navLink} ${s.navLinkActive}` : s.navLink)}
              >
                {t(`nav.${item.key}`)}
              </NavLink>
            </li>
          ))}
        </ul>
      </div>
    </nav>
  );
}
