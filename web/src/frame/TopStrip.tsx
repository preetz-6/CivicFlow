import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import s from "./frame.module.css";
import { usePrefs, type FontSize } from "./prefs";

const SIZES: { value: FontSize; label: string; titleKey: string }[] = [
  { value: "small", label: "A-", titleKey: "strip.decrease" },
  { value: "normal", label: "A", titleKey: "strip.reset" },
  { value: "large", label: "A+", titleKey: "strip.increase" },
];

function ContrastIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true" focusable="false">
      <circle cx="7" cy="7" r="6" fill="none" stroke="currentColor" strokeWidth="1.6" />
      <path d="M7 1 A6 6 0 0 0 7 13 Z" fill="currentColor" />
    </svg>
  );
}

export function TopStrip() {
  const { t, i18n } = useTranslation();
  const { fontSize, setFontSize, highContrast, toggleContrast } = usePrefs();

  return (
    <div className={`${s.strip} no-print`}>
      <div className={`container ${s.stripInner}`}>
        <span>{t("strip.gov")}</span>
        <div className={s.stripRight}>
          <span className={s.stripItem}>
            <a className={s.stripLink} href="#main">
              {t("strip.skip")}
            </a>
          </span>
          <span className={s.stripItem}>
            <Link className={s.stripLink} to="/screen-reader-access">
              {t("strip.screenReader")}
            </Link>
          </span>
          <span className={s.stripItem} role="group" aria-label={t("strip.textSize")}>
            {SIZES.map((size) => (
              <button
                key={size.value}
                type="button"
                className={s.stripBtn}
                aria-pressed={fontSize === size.value}
                aria-label={t(size.titleKey)}
                title={t(size.titleKey)}
                onClick={() => setFontSize(size.value)}
              >
                {size.label}
              </button>
            ))}
          </span>
          <span className={s.stripItem}>
            <button
              type="button"
              className={`${s.stripBtn} ${s.stripBtnWide}`}
              aria-pressed={highContrast}
              title={highContrast ? t("strip.contrastOff") : t("strip.contrastOn")}
              onClick={toggleContrast}
            >
              <ContrastIcon />
              {t("strip.contrast")}
            </button>
          </span>
          <span className={s.stripItem} role="group" aria-label={t("strip.language")}>
            <button
              type="button"
              lang="en"
              className={s.stripBtn}
              aria-pressed={i18n.language === "en"}
              onClick={() => void i18n.changeLanguage("en")}
            >
              English
            </button>
            <button
              type="button"
              lang="kn"
              className={s.stripBtn}
              aria-pressed={i18n.language === "kn"}
              onClick={() => void i18n.changeLanguage("kn")}
            >
              ಕನ್ನಡ
            </button>
          </span>
        </div>
      </div>
    </div>
  );
}
