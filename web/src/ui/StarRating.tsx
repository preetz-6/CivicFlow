import u from "./ui.module.css";

/** 1–5 star rating as a radio group (keyboard: arrow keys). */
export function StarRating({
  value,
  onChange,
  label,
  starLabel,
}: {
  value: number;
  onChange: (n: number) => void;
  label: string;
  /** e.g. n => "3 of 5" */
  starLabel: (n: number) => string;
}) {
  return (
    <fieldset className={u.stars}>
      <legend className={u.starsLegend}>{label}</legend>
      {[1, 2, 3, 4, 5].map((n) => (
        <label key={n} className={`${u.star} ${n <= value ? u.starOn : ""}`} title={starLabel(n)}>
          <input
            type="radio"
            name="rating"
            value={n}
            checked={value === n}
            onChange={() => onChange(n)}
            className="visually-hidden"
          />
          <span aria-hidden="true">{"★"}</span>
          <span className="visually-hidden">{starLabel(n)}</span>
        </label>
      ))}
      <span className="muted" style={{ marginLeft: 8 }}>
        {value ? starLabel(value) : ""}
      </span>
    </fieldset>
  );
}
