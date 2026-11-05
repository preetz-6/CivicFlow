import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Crest } from "./Crest";
import s from "./frame.module.css";

export function Header() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [q, setQ] = useState("");

  function search(e: FormEvent) {
    e.preventDefault();
    const no = q.trim().toUpperCase();
    if (no) navigate(`/track?no=${encodeURIComponent(no)}`);
  }

  return (
    <header className={`${s.header} no-print`}>
      <div className={`container ${s.headerInner}`}>
        <Link to="/" className={s.brand} aria-label={`${t("header.nameEn")} - ${t("nav.home")}`}>
          <Crest label={t("header.crestAlt")} />
          <span className={s.names}>
            <span className={s.nameEn} lang="en">
              {t("header.nameEn")}
            </span>
            <span className={s.nameKn} lang="kn">
              {t("header.nameKn")}
            </span>
            <span className={s.subtitle}>{t("header.subtitle")}</span>
          </span>
        </Link>
        <div className={s.headerRight}>
          <div>{t("header.helpline")}</div>
          <div className={s.helpline}>
            1800-000-0000 ({t("header.demo")})
          </div>
          <form className={s.search} role="search" onSubmit={search}>
            <label htmlFor="header-search" className="visually-hidden">
              {t("search.label")}
            </label>
            <input
              id="header-search"
              type="search"
              placeholder={t("search.placeholder")}
              title={t("search.label")}
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
            <button type="submit" className="btn">
              {t("search.go")}
            </button>
          </form>
        </div>
      </div>
    </header>
  );
}
