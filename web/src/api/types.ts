/**
 * API types. Generated ones come from schema.d.ts (`npm run gen:api`, never edit
 * that file by hand). Endpoints whose backend response is an untyped dict
 * (public/*, crews, field jobs, analysis) get small hand-written types here,
 * mirrored from the backend routers.
 */
import type { components } from "./schema";

type S = components["schemas"];

export type UserOut = S["UserOut"];
export type DemoUser = S["DemoUser"];
export type LoginOut = S["LoginOut"];
export type AttachmentOut = S["AttachmentOut"];
export type SlaOut = S["SlaOut"];
export type AckSlip = S["AckSlip"];
export type TimelineEntryOut = S["TimelineEntry"];
export type TrackView = S["TrackView"];
export type QueueItem = S["QueueItem"];
export type WorkOrderOut = S["WorkOrderOut"];
export type StatusEventOut = S["StatusEventOut"];

export type Role = "CITIZEN" | "WARD_OFFICER" | "FIELD_TEAM" | "CONTROL_ROOM";

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// ---------------------------------------------------------------- public
export interface TickerItem {
  id: string;
  text: string;
  text_kn?: string | null;
  new?: boolean;
  published_at: string;
}

export interface Category {
  id: string;
  label: string;
  label_kn: string;
}

export interface PublicStats {
  total: number;
  unique_issues: number;
  resolved: number;
  resolved_citizen_confirmed: number;
  resolved_auto_closed: number;
  within_sla_pct: number | null;
  avg_days: number | null;
  reopen_rate_pct: number | null;
  visits: number;
  as_of: string;
}

export interface SlaPolicy {
  category: string;
  category_label: string;
  priority: string;
  resolution_hours: number;
  verification_hours: number;
}

export interface WardOut {
  id: string;
  name: string;
  name_kn: string | null;
  zone: string | null;
  officer: { name: string; designation: string | null; phone: string } | null;
}

// ---------------------------------------------------------------- complaints
export interface AnalysisStep {
  idx: number;
  tool: string;
  args: unknown;
  result: unknown;
  error: string | null;
}

export interface TriageBrief {
  category?: string;
  priority?: string;
  department_id?: string | null;
  ward_id?: string | null;
  asset_id?: string | null;
  duplicate_of?: string | null;
  duplicate_confidence?: number | null;
  repeat_failure?: boolean;
  repeat_failure_note?: string | null;
  planned_work_conflict?: string | null;
  interagency_referral?: { agency: string; reason: string } | null;
  vehicle_corroboration?: unknown;
  rationale?: string[];
  citizen_summary?: string | null;
  confidence?: number;
}

/** GET /complaints/{id} → analysis (latest Case Investigator run) */
export interface Analysis {
  run_id: number;
  agent: string;
  status: string; // OK | FALLBACK
  model: string; // claude-... | rules | replay:...
  confidence: number | null;
  decision: string | null;
  rationale: string | null; // "- bullet\n- bullet"
  output: TriageBrief | null;
  steps: AnalysisStep[];
  overridden: boolean | string | null;
  override_reason: string | null;
  accepted: boolean | null;
}

/** Generated ComplaintDetail, with `analysis` typed (the backend declares it as a dict). */
export type ComplaintDetail = Omit<S["ComplaintDetail"], "analysis" | "referrals" | "escalations"> & {
  analysis: Analysis | null;
  referrals: Record<string, unknown>[];
  escalations: Record<string, unknown>[];
};

export interface CrewOut {
  id: string;
  name: string;
  ward_id: string;
  skills: string[];
  capacity: number;
  open_jobs: number;
  contractor: string | null;
  audit_priority: string | null; // NORMAL | HIGH
  lat: number;
  lon: number;
}

/** GET /field/jobs and /field/jobs/{id}: WorkOrderOut plus complaint context, never citizen contact. */
export interface FieldJob extends WorkOrderOut {
  category: string;
  category_label: string;
  description: string;
  address: string | null;
  landmark: string | null;
  lat: number;
  lon: number;
  priority: string;
  sr_status: string;
  ward_id: string | null;
  citizen_photos: AttachmentOut[];
}
