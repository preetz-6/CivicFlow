/**
 * Hand-mirrored API shapes, TEMPORARY. Copied from backend/app/schemas/*.py and
 * the routers because the API cannot start yet (docs/REQUESTS_FOR_A.md B-4), so
 * `npm run gen:api` cannot run. Once it can, these become aliases of the
 * generated types in schema.d.ts.
 */

export type Role = "CITIZEN" | "WARD_OFFICER" | "FIELD_TEAM" | "CONTROL_ROOM";

export interface UserOut {
  id: number;
  username: string;
  name: string;
  role: Role | string;
  designation?: string | null;
  ward_id?: string | null;
  zone?: string | null;
  department_id?: string | null;
  crew_id?: string | null;
  language: string;
}

export interface DemoUser {
  username: string;
  name: string;
  role: string;
  designation: string | null;
  ward_id: string | null;
}

export interface LoginOut {
  sent_to: string;
  otp_demo: string | null;
}

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
export interface AttachmentOut {
  id: number;
  kind: string;
  url: string;
  uploaded_at: string;
  exif_lat?: number | null;
  exif_lon?: number | null;
  exif_time?: string | null;
  wo_id?: string | null;
}

export interface SlaOut {
  state: string | null;
  due_at: string | null;
  remaining_s: number | null;
  fraction: number | null;
  label: string;
}

export interface AckSlip {
  grievance_no: string;
  tracking_code: string;
  submitted_at: string;
  category: string;
  category_label: string;
  category_label_kn: string;
  ward_id: string | null;
  ward_name: string | null;
  department_id: string | null;
  department_name: string | null;
  expected_resolution: string | null;
  status: string;
}

export interface TimelineEntryOut {
  at: string;
  stage: string;
  remarks: string;
  remarks_kn?: string | null;
  actor_type: string;
}

export interface TrackView {
  grievance_no: string;
  status: string;
  category: string;
  category_label: string;
  category_label_kn: string;
  description: string;
  submitted_at: string;
  ward_name: string | null;
  department_name: string | null;
  priority: string;
  expected_resolution: string | null;
  reporter_count: number;
  escalation_level: number;
  merged_into: string | null;
  lat: number;
  lon: number;
  landmark: string | null;
  timeline: TimelineEntryOut[];
  citizen_photos: AttachmentOut[];
  before_photos: AttachmentOut[];
  after_photos: AttachmentOut[];
  can_confirm: boolean;
  can_reopen: boolean;
  feedback_rating?: number | null;
}

export interface QueueItem {
  id: string;
  category: string;
  category_label: string;
  description: string;
  status: string;
  priority: string;
  ward_id: string | null;
  department_id: string | null;
  source: string;
  reporter_count: number;
  corroboration_count: number;
  escalation_level: number;
  emergency: boolean;
  created_at: string;
  sla: SlaOut;
  owner_name: string | null;
  analysis_decision?: string | null;
  lat: number;
  lon: number;
}

export interface WorkOrderOut {
  id: string;
  sr_id: string;
  crew_id: string;
  status: string;
  scope: string;
  root_cause: string | null;
  est_cost_inr: number | null;
  asset_id: string | null;
  assigned_at: string;
  started_at: string | null;
  completed_at: string | null;
  verified_at: string | null;
  rework_reason: string | null;
  rework_count: number;
  audit_verdict: string | null;
  audit_score: number | null;
  audit_run_id: number | null;
  photos: AttachmentOut[];
}

export interface StatusEventOut {
  at: string;
  object_type: string;
  object_id: string;
  from_state: string | null;
  to_state: string;
  actor_type: string;
  actor_label: string | null;
  reason: string | null;
}

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

export interface ComplaintDetail extends QueueItem {
  address: string | null;
  landmark: string | null;
  asset_id: string | null;
  parent_sr_id: string | null;
  incident_id: number | null;
  hold_reason: string | null;
  prev_status: string | null;
  contact_name: string | null;
  contact_phone: string | null;
  tracking_code: string | null;
  citizen_category: string | null;
  photos: AttachmentOut[];
  work_orders: WorkOrderOut[];
  timeline: TimelineEntryOut[];
  status_events: StatusEventOut[];
  allowed_actions: string[];
  analysis: Analysis | null;
  duplicates: string[];
  referrals: Record<string, unknown>[];
  escalations: Record<string, unknown>[];
}

export interface CrewOut {
  id: string;
  name: string;
  ward_id: string;
  skills: string[];
  capacity: number;
  open_jobs: number;
  contractor: string | null;
  audit_priority: string | boolean | null;
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
