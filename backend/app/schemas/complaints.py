from datetime import datetime

from pydantic import BaseModel, Field


class AttachmentOut(BaseModel):
    id: int
    kind: str
    url: str
    uploaded_at: datetime
    exif_lat: float | None = None
    exif_lon: float | None = None
    exif_time: datetime | None = None
    wo_id: str | None = None


class SlaOut(BaseModel):
    state: str | None
    due_at: datetime | None
    remaining_s: float | None
    fraction: float | None
    label: str


class AckSlip(BaseModel):
    grievance_no: str
    tracking_code: str
    submitted_at: datetime
    category: str
    category_label: str
    category_label_kn: str
    ward_id: str | None
    ward_name: str | None
    department_id: str | None
    department_name: str | None
    expected_resolution: datetime | None
    status: str
    ward_name_kn: str | None = None
    department_name_kn: str | None = None


class TimelineEntry(BaseModel):
    at: datetime
    stage: str
    stage_kn: str | None = None
    remarks: str
    remarks_kn: str | None = None
    actor_type: str


class TrackView(BaseModel):
    grievance_no: str
    status: str
    category: str
    category_label: str
    category_label_kn: str
    description: str
    submitted_at: datetime
    ward_name: str | None
    department_name: str | None
    ward_name_kn: str | None = None
    department_name_kn: str | None = None
    priority: str
    expected_resolution: datetime | None
    reporter_count: int
    escalation_level: int
    merged_into: str | None
    lat: float
    lon: float
    landmark: str | None
    timeline: list[TimelineEntry]
    citizen_photos: list[AttachmentOut]
    before_photos: list[AttachmentOut]
    after_photos: list[AttachmentOut]
    can_confirm: bool
    can_reopen: bool
    feedback_rating: int | None = None


class QueueItem(BaseModel):
    id: str
    category: str
    category_label: str
    description: str
    status: str
    priority: str
    ward_id: str | None
    department_id: str | None
    source: str
    reporter_count: int
    corroboration_count: int
    escalation_level: int
    emergency: bool
    created_at: datetime
    sla: SlaOut
    owner_name: str | None
    analysis_decision: str | None = None  # one line from the latest System Analysis
    lat: float
    lon: float


class WorkOrderOut(BaseModel):
    id: str
    sr_id: str
    crew_id: str
    status: str
    scope: str
    root_cause: str | None
    est_cost_inr: float | None
    asset_id: str | None
    assigned_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    verified_at: datetime | None
    rework_reason: str | None
    rework_count: int
    audit_verdict: str | None
    audit_score: int | None
    audit_run_id: int | None
    photos: list[AttachmentOut] = []


class StatusEventOut(BaseModel):
    at: datetime
    object_type: str
    object_id: str
    from_state: str | None
    to_state: str
    actor_type: str
    actor_label: str | None
    reason: str | None


class ComplaintDetail(QueueItem):
    address: str | None
    landmark: str | None
    asset_id: str | None
    parent_sr_id: str | None
    incident_id: int | None
    hold_reason: str | None
    prev_status: str | None
    contact_name: str | None  # hidden from field teams
    contact_phone: str | None  # hidden from field teams
    tracking_code: str | None
    citizen_category: str | None
    photos: list[AttachmentOut]
    work_orders: list[WorkOrderOut]
    timeline: list[TimelineEntry]
    status_events: list[StatusEventOut]
    allowed_actions: list[str]
    analysis: dict | None = None  # latest Case Investigator run (C2)
    duplicates: list[str] = []
    referrals: list[dict] = []
    escalations: list[dict] = []


class AcceptIn(BaseModel):
    owner_id: int | None = None
    department_id: str | None = None
    note: str | None = None


class OverrideIn(BaseModel):
    reason: str = Field(min_length=5)
    category: str | None = None
    priority: str | None = None
    department_id: str | None = None
    owner_id: int | None = None
    merge_into: str | None = None


class HoldIn(BaseModel):
    reason_code: str
    note: str | None = None


class RejectIn(BaseModel):
    reason_code: str
    explanation: str = Field(min_length=10)


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3)


class ConfirmIn(BaseModel):
    code: str | None = None  # tracking code or phone, for anonymous citizens
    rating: int | None = Field(default=None, ge=1, le=5)
    comment: str | None = None


class ReopenIn(BaseModel):
    code: str | None = None
    reason: str = Field(min_length=5)
