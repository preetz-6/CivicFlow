import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Crest } from "./Crest";
import s from "./frame.module.css";

export function Header() {
  const { t } = useTranslation();
  return (
    <header className={s.header}>
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
        </div>
      </div>
    </header>
  );
}
