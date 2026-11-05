"""All enum values are stored as plain strings (no PG enums -> painless migrations)."""
from enum import StrEnum


class Role(StrEnum):
    CITIZEN = "CITIZEN"
    WARD_OFFICER = "WARD_OFFICER"
    FIELD_TEAM = "FIELD_TEAM"
    CONTROL_ROOM = "CONTROL_ROOM"


class ActorKind(StrEnum):
    HUMAN = "HUMAN"
    AGENT = "AGENT"
    SYSTEM = "SYSTEM"


class SRStatus(StrEnum):
    SUBMITTED = "SUBMITTED"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    WORK_COMPLETED = "WORK_COMPLETED"
    VERIFIED = "VERIFIED"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    MERGED = "MERGED"
    REJECTED = "REJECTED"
    ON_HOLD = "ON_HOLD"
    REOPENED = "REOPENED"


SR_OPEN = {
    SRStatus.SUBMITTED, SRStatus.ASSIGNED, SRStatus.IN_PROGRESS, SRStatus.WORK_COMPLETED,
    SRStatus.VERIFIED, SRStatus.ON_HOLD, SRStatus.REOPENED,
}
SR_TERMINAL = {SRStatus.CLOSED, SRStatus.REJECTED, SRStatus.MERGED}


class WOStatus(StrEnum):
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    VERIFIED = "VERIFIED"
    REWORK = "REWORK"
    ON_HOLD = "ON_HOLD"


class Priority(StrEnum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class Source(StrEnum):
    CITIZEN_WEB = "CITIZEN_WEB"
    VEHICLE_FEED = "VEHICLE_FEED"
    HELPDESK = "HELPDESK"


class Category(StrEnum):
    POTHOLE = "POTHOLE"
    DAMAGED_ROAD = "DAMAGED_ROAD"
    STREETLIGHT = "STREETLIGHT"
    GARBAGE = "GARBAGE"
    WATER_LEAK = "WATER_LEAK"
    DRAIN_BLOCKED = "DRAIN_BLOCKED"
    WATERLOGGING = "WATERLOGGING"
    OPEN_MANHOLE = "OPEN_MANHOLE"
    TREE_FALL = "TREE_FALL"
    OTHER = "OTHER"


SURGE_CATEGORIES = {Category.WATERLOGGING, Category.DRAIN_BLOCKED, Category.TREE_FALL}


class SLAState(StrEnum):
    ON_TRACK = "ON_TRACK"
    AT_RISK = "AT_RISK"
    BREACHED = "BREACHED"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"


class HoldReason(StrEnum):
    MATERIAL = "MATERIAL"
    AGENCY = "AGENCY"
    WEATHER = "WEATHER"
    ACCESS = "ACCESS"
    CITIZEN = "CITIZEN"


# Only these pause the SLA clock (brief 5.3). MATERIAL / ACCESS are on hold but the clock runs.
SLA_PAUSE_REASONS = {HoldReason.AGENCY, HoldReason.WEATHER, HoldReason.CITIZEN}


class AssetOwner(StrEnum):
    MUNICIPAL = "MUNICIPAL"
    BESCOM = "BESCOM"
    BWSSB = "BWSSB"


class AttachmentKind(StrEnum):
    CITIZEN = "CITIZEN"
    BEFORE = "BEFORE"
    AFTER = "AFTER"


class ClosureType(StrEnum):
    CITIZEN = "CITIZEN"
    AUTO = "AUTO"


class AuditVerdict(StrEnum):
    PASS = "PASS"
    FLAG = "FLAG"
    FAIL = "FAIL"


class HazardType(StrEnum):
    POTHOLE = "POTHOLE"
    DAMAGED_ROAD = "DAMAGED_ROAD"
    ROUGH_SURFACE = "ROUGH_SURFACE"


class ClusterStatus(StrEnum):
    NEW = "NEW"
    CREATED = "CREATED"
    CORROBORATED = "CORROBORATED"
    REPAIR_FAILURE = "REPAIR_FAILURE"
    FILTERED = "FILTERED"
    REVIEW = "REVIEW"
    IGNORED = "IGNORED"
