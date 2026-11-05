import u from "./ui.module.css";

export interface TimelineEntry {
  at: string;
  stage: string;
  remarks?: string | null;
  /** HUMAN / AGENT / SYSTEM; AGENT entries are labelled "System" for citizens. */
  actor?: string | null;
}

/** Vertical timeline: date | stage | remarks, newest last. */
export function Timeline({ entries, locale = "en-IN" }: { entries: TimelineEntry[]; locale?: string }) {
  return (
    <ol className={u.timeline}>
      {entries.map((e, i) => (
        <li key={`${e.at}-${i}`} className={u.tlItem}>
          <span className={u.tlDot} aria-hidden="true" />
          <div className={u.tlBody}>
            <time dateTime={e.at} className={u.tlTime}>
              {new Date(e.at).toLocaleString(locale, { dateStyle: "medium", timeStyle: "short" })}
            </time>
            <div className={u.tlStage}>{e.stage}</div>
            {e.remarks ? <div className={u.tlRemarks}>{e.remarks}</div> : null}
          </div>
        </li>
      ))}
    </ol>
  );
}
