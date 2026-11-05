import { ApiError } from "../api/client";

/** Text to show for any thrown error: the API's {"detail": "..."} when present. */
export function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    const detail = (e.body as { detail?: unknown } | undefined)?.detail;
    // FastAPI validation errors: [{loc, msg}, ...]
    if (Array.isArray(detail)) {
      return detail
        .map((d: { loc?: unknown[]; msg?: string }) => {
          const field = Array.isArray(d.loc) ? d.loc.filter((x) => x !== "body").join(".") : "";
          return field ? `${field}: ${d.msg}` : (d.msg ?? "");
        })
        .join("; ");
    }
    if (e.status === 0) return "Could not reach the server. Please try again.";
    return e.message || `Request failed (${e.status})`;
  }
  if (e instanceof TypeError) return "Could not reach the server. Please try again.";
  return e instanceof Error ? e.message : String(e);
}

/** Government-style error box (red left border), announced to screen readers. */
export function ErrorBox({ error, title = "Error" }: { error: unknown; title?: string }) {
  if (!error) return null;
  return (
    <div className="notice notice-error" role="alert">
      <strong>{title}: </strong>
      {errorText(error)}
    </div>
  );
}

/** Green success box. */
export function SuccessBox({ children }: { children: React.ReactNode }) {
  return (
    <div className="notice notice-success" role="status">
      {children}
    </div>
  );
}
