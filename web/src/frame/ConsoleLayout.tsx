import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ApiError, get, post } from "../api/client";
import type { UserOut } from "../api/types";
import { AgentToasts } from "../ui/Lively";
import { Crest } from "./Crest";
import c from "./console.module.css";

export interface ConsoleMenuItem {
  to: string;
  label: string;
  end?: boolean;
}

/**
 * e-Office style layout for staff (officer, field team, control room):
 * top bar with name, designation, ward and Logout; left vertical menu.
 * Staff screens are English only (brief: Kannada on citizen pages only).
 * Redirects to /login when there is no session, or when the role is not allowed.
 */
export function ConsoleLayout({
  title,
  menu,
  roles,
}: {
  title: string;
  menu: ConsoleMenuItem[];
  roles: string[];
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [user, setUser] = useState<UserOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const rolesKey = roles.join(",");

  useEffect(() => {
    const allowed = rolesKey.split(",");
    let alive = true;
    get<UserOut>("/auth/me")
      .then((u) => {
        if (!alive) return;
        if (!allowed.includes(u.role)) navigate("/login", { replace: true });
        else setUser(u);
      })
      .catch((e: unknown) => {
        if (!alive) return;
        if (e instanceof ApiError && e.status === 401) navigate("/login", { replace: true });
        else setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      alive = false;
    };
  }, [navigate, rolesKey]);

  async function logout() {
    try {
      await post("/auth/logout");
    } finally {
      navigate("/login", { replace: true });
    }
  }

  if (error) {
    return (
      <div className="container" style={{ paddingTop: 24 }}>
        <p className="notice notice-error" role="alert">
          {error}
        </p>
      </div>
    );
  }
  if (!user) return null;

  return (
    <div className={c.shell}>
      <header className={c.topbar}>
        <div className={c.topLeft}>
          <Crest size={40} label={t("header.crestAlt")} />
          <div>
            <div className={c.org}>{t("header.nameEn")}</div>
            <div className={c.title}>{title}</div>
          </div>
        </div>
        <div className={c.topRight}>
          <div className={c.who}>
            <strong>{user.name}</strong>
            {user.designation ? <span>{user.designation}</span> : null}
            {user.ward_id ? (
              <span>
                {t("console.ward")}: {user.ward_id}
              </span>
            ) : user.zone ? (
              <span>{user.zone}</span>
            ) : null}
          </div>
          <button type="button" className="btn btn-secondary" onClick={() => void logout()}>
            {t("console.logout")}
          </button>
        </div>
      </header>
      <div className={c.body}>
        <nav className={c.side} aria-label={t("console.menu")}>
          <ul>
            {menu.map((m) => (
              <li key={m.to}>
                <NavLink
                  to={m.to}
                  end={m.end}
                  className={({ isActive }) => (isActive ? `${c.sideLink} ${c.sideActive}` : c.sideLink)}
                >
                  {m.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <main id="main" tabIndex={-1} className={c.content}>
          <div className="fade-up" key={pathname}>
            <Outlet context={user} />
          </div>
        </main>
      </div>
      <AgentToasts />
    </div>
  );
}
