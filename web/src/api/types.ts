/**
 * API types. Generated ones come from schema.d.ts (`npm run gen:api`, never edit
 * that file by hand). Endpoints whose backend response is an untyped dict
 * (public/*, crews, field jobs, analysis) get small hand-written types here,
 * mirrored from the backend routers.
 */
import type { components } from "./schema";

type S = components["schemas"];

export type UserOut = S["UserOut"];
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
  started_at?: string;
  latency_ms?: number | null;
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

// ---------------------------------------------------------------- agent activity log
/** GET /agent-runs items */
export interface AgentRunRow {
  id: number;
  at: string;
  agent: string;
  agent_label: string;
  trigger: string;
  subject_type: string | null;
  subject_id: string | null;
  decision: string | null;
  confidence: number | null;
  model: string;
  mode: "rules" | "model";
  status: string;
  latency_ms: number | null;
  overridden: boolean;
  overridden_by: string | null;
  override_reason: string | null;
  accepted: boolean;
}

/** GET /agent-runs/{id} */
export interface AgentRunDetail {
  run_id: number;
  agent: string;
  agent_label: string;
  status: string;
  model: string;
  confidence: number | null;
  decision: string | null;
  rationale: string | null;
  output: Record<string, unknown> | null;
  started_at: string;
  latency_ms: number | null;
  overridden: boolean;
  override_reason: string | null;
  accepted: boolean;
  steps: AnalysisStep[];
  trigger: string;
  subject_type: string | null;
  subject_id: string | null;
  input: unknown;
  error: string | null;
}

/** GET /agent-stats */
export interface AgentStat {
  agent: string;
  agent_label: string;
  runs: number;
  overridden: number;
  rules_runs: number;
  avg_latency_ms: number;
}

// ---------------------------------------------------------------- control room
export interface Escalation {
  id: number;
  sr_id: string;
  level: number;
  trigger: string;
  reason_summary: string | null;
  authority: string | null;
  created_at: string;
  deadline: string | null;
  agent_run_id: number | null;
}

export interface WeatherAlert {
  id: number;
  title: string;
  severity: string;
  area_name: string | null;
  active: boolean;
  issued_at: string;
  expires_at: string | null;
}

export interface Incident {
  id: number;
  name: string;
  display_name: string;
  category: string | null;
  severity: string;
  status: string;
  report_count: number;
  unique_issues: number;
  resolved_count: number;
  lat: number;
  lon: number;
  crew_suggestion: string | null;
  advisory_draft: string | null;
  advisory_draft_kn: string | null;
  advisory_published: boolean;
  published_at: string | null;
  summary: string | null;
  summary_at: string | null;
  agent_run_id: number | null;
  created_at: string;
  sr_ids: string[];
}

export interface HazardCluster {
  id: number;
  lat: number;
  lon: number;
  status: string; // NEW | FILTERED | CORROBORATED | CREATED | REPAIR_FAILURE | REVIEW | IGNORED
  hazard_type: string | null;
  detections: number;
  distinct_vehicles: number;
  avg_confidence: number | null;
  avg_jolt_g: number | null;
  days_seen: number | null;
  first_seen: string | null;
  last_seen: string | null;
  filter_reason: string | null;
  decision_reason: string | null;
  sr_id: string | null;
  flagged_wo_id: string | null;
  agent_run_id: number | null;
}

export interface HazardMapData {
  clusters: HazardCluster[];
  known_features: { type: string; name: string; lat: number; lon: number }[];
  complaints: { id: string; lat: number; lon: number; source: string; status: string; priority: string; vehicles: number; category: string }[];
  raw: { lat: number; lon: number; c: number; cluster_id: number | null }[];
}

export interface DataSourceOut {
  id: number;
  name: string;
  kind: string;
  last_ingested_at: string | null;
  accepted: number;
  rejected: number;
  recent_rejections: { at: string; source_record_id: string | null; reason: string }[];
}

export interface AgencyReferral {
  id: number;
  agency: string;
  sr_id: string;
  category: string;
  description: string;
  reason: string | null;
  status: string;
  sent_at: string | null;
  followups_sent: number;
  agency_status: string | null;
  agency_reply: string | null;
  messages: { direction: string; body: string; at: string }[];
}

export interface ClockOut {
  now: string;
  scale: number;
  frozen: boolean;
}
