import type { ReactNode } from "react";
import u from "./ui.module.css";

/** Government-form fieldset with a legend (e.g. "Grievance Details"). */
export function Fieldset({ legend, children }: { legend: string; children: ReactNode }) {
  return (
    <fieldset className={u.fieldset}>
      <legend className={u.legend}>{legend}</legend>
      <div className={u.fieldGrid}>{children}</div>
    </fieldset>
  );
}

/**
 * One labelled form row. Pass the control as children with the same `id` as
 * `htmlFor`. `required` adds the red asterisk; `error` is announced.
 */
export function Field({
  label,
  htmlFor,
  required,
  hint,
  error,
  wide,
  children,
}: {
  label: string;
  htmlFor: string;
  required?: boolean;
  hint?: string;
  error?: string | null;
  wide?: boolean;
  children: ReactNode;
}) {
  return (
    <div className={`${u.field} ${wide ? u.wide : ""}`}>
      <label htmlFor={htmlFor} className={required ? "required" : undefined}>
        {label}
      </label>
      {children}
      {hint ? (
        <span id={`${htmlFor}-hint`} className={u.hint}>
          {hint}
        </span>
      ) : null}
      {error ? (
        <span id={`${htmlFor}-error`} className={u.error} role="alert">
          {error}
        </span>
      ) : null}
    </div>
  );
}
