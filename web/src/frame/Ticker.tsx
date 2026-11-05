import { useEffect, useState, type CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import { get } from "../api/client";
import type { TickerItem } from "../api/types";
import s from "./frame.module.css";

/**
 * "What's New" ticker. Shows published notices and Surge Commander advisories
 * from GET /public/ticker. If the endpoint is unavailable or has nothing
 * published, the ticker is not rendered at all.
 */
export function Ticker() {
  const { t, i18n } = useTranslation();
  const kn = i18n.language === "kn";
  const [items, setItems] = useState<TickerItem[]>([]);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    let alive = true;
    const load = () =>
      get<TickerItem[]>("/public/ticker")
        .then((data) => alive && setItems(Array.isArray(data) ? data : []))
        .catch(() => alive && setItems([]));
    void load();
    // Advisories are published live during the demo, so refresh periodically.
    const timer = window.setInterval(load, 30_000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);

  if (items.length === 0) return null;

  const totalChars = items.reduce((n, i) => n + (kn && i.text_kn ? i.text_kn : i.text).length, 0);
  const duration = `${Math.max(20, Math.round(totalChars / 6))}s`;

  return (
    <section className={`${s.ticker} no-print`} aria-label={t("ticker.title")}>
      <div className={`container ${s.tickerInner} ${paused ? s.paused : ""}`}>
        <span className={s.tickerTitle}>
          <span className={s.newLabel}>{t("ticker.new")}</span>
          {t("ticker.title")}
        </span>
        <div className={s.tickerViewport} tabIndex={0}>
          <div className={s.tickerTrack} style={{ "--ticker-duration": duration } as CSSProperties}>
            {items.map((item) => (
              <span key={item.id} className={s.tickerItem}>
                {item.new ? <span className={s.newLabel}>{t("ticker.new")}</span> : null}{" "}
                {kn && item.text_kn ? item.text_kn : item.text}
              </span>
            ))}
          </div>
        </div>
        <button
          type="button"
          className={s.tickerBtn}
          aria-pressed={paused}
          aria-label={paused ? t("ticker.playLabel") : t("ticker.pauseLabel")}
          onClick={() => setPaused((v) => !v)}
        >
          {paused ? t("ticker.play") : t("ticker.pause")}
        </button>
      </div>
    </section>
  );
}
