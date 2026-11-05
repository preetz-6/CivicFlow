"""Configuration tables (brief: 'configuration in seed/config files, no admin UI').
Used by the seed, the SLA engine and every agent's rule-based fallback."""

CATEGORY_DEPARTMENT = {
    "POTHOLE": "ROADS",
    "DAMAGED_ROAD": "ROADS",
    "STREETLIGHT": "LIGHTING",
    "GARBAGE": "SWM",
    "WATER_LEAK": "WATER",
    "DRAIN_BLOCKED": "SWD",
    "WATERLOGGING": "SWD",
    "OPEN_MANHOLE": "SWD",
    "TREE_FALL": "PARKS",
    "OTHER": "ROADS",
}

CATEGORY_SKILL = {
    "POTHOLE": "ROADS", "DAMAGED_ROAD": "ROADS", "STREETLIGHT": "ELECTRICAL", "GARBAGE": "SWM",
    "WATER_LEAK": "DRAINS", "DRAIN_BLOCKED": "DRAINS", "WATERLOGGING": "DRAINS", "OPEN_MANHOLE": "DRAINS",
    "TREE_FALL": "TREES", "OTHER": "ROADS",
}

CATEGORY_LABELS = {
    "POTHOLE": ("Pothole", "ರಸ್ತೆ ಗುಂಡಿ"),
    "DAMAGED_ROAD": ("Damaged Road", "ಹಾಳಾದ ರಸ್ತೆ"),
    "STREETLIGHT": ("Streetlight Not Working", "ಬೀದಿ ದೀಪ ಕೆಟ್ಟಿದೆ"),
    "GARBAGE": ("Garbage Not Collected", "ಕಸ ಸಂಗ್ರಹಿಸಿಲ್ಲ"),
    "WATER_LEAK": ("Water Pipeline Leak", "ನೀರಿನ ಪೈಪ್ ಸೋರಿಕೆ"),
    "DRAIN_BLOCKED": ("Blocked Drain", "ಚರಂಡಿ ಕಟ್ಟಿದೆ"),
    "WATERLOGGING": ("Waterlogging / Flooding", "ನೀರು ನಿಂತಿದೆ / ಪ್ರವಾಹ"),
    "OPEN_MANHOLE": ("Open Manhole", "ತೆರೆದ ಮ್ಯಾನ್‌ಹೋಲ್"),
    "TREE_FALL": ("Fallen Tree", "ಮರ ಬಿದ್ದಿದೆ"),
    "OTHER": ("Other", "ಇತರೆ"),
}

# Base resolution hours by priority, with per-category overrides (brief §6.3).
DEFAULT_RESOLUTION_HOURS = {"P1": 24, "P2": 72, "P3": 168, "P4": 336}
RESOLUTION_OVERRIDES = {
    ("OPEN_MANHOLE", "P1"): 4, ("OPEN_MANHOLE", "P2"): 12,
    ("POTHOLE", "P1"): 24, ("POTHOLE", "P2"): 120, ("POTHOLE", "P3"): 168,
    ("STREETLIGHT", "P2"): 72, ("STREETLIGHT", "P3"): 168,
    ("WATERLOGGING", "P1"): 6, ("WATERLOGGING", "P2"): 24,
    ("TREE_FALL", "P1"): 6, ("TREE_FALL", "P2"): 24,
    ("GARBAGE", "P3"): 48, ("GARBAGE", "P4"): 72,
}
VERIFICATION_HOURS = {"P1": 24, "P2": 168, "P3": 168, "P4": 168}

# Default priority before any analysis
DEFAULT_PRIORITY = {
    "OPEN_MANHOLE": "P1", "WATERLOGGING": "P2", "TREE_FALL": "P2", "WATER_LEAK": "P2",
    "POTHOLE": "P3", "DAMAGED_ROAD": "P3", "STREETLIGHT": "P3", "DRAIN_BLOCKED": "P3",
    "GARBAGE": "P3", "OTHER": "P4",
}

# Duplicate-detection radius per category, metres (brief: 25-100 m)
DUPLICATE_RADIUS_M = {
    "POTHOLE": 25, "DAMAGED_ROAD": 50, "STREETLIGHT": 40, "GARBAGE": 50, "WATER_LEAK": 50,
    "DRAIN_BLOCKED": 50, "WATERLOGGING": 100, "OPEN_MANHOLE": 25, "TREE_FALL": 50, "OTHER": 50,
}
DUPLICATE_WINDOW_HOURS = 72

# Auditor: after-photo must be within this distance of the complaint
AUDIT_RADIUS_M = {"POTHOLE": 50, "DAMAGED_ROAD": 75, "STREETLIGHT": 50, "OPEN_MANHOLE": 50}
AUDIT_RADIUS_DEFAULT_M = 100

EMERGENCY_KEYWORDS = [
    "live wire", "electric shock", "open manhole", "child fell", "kid fell", "fell into", "electrocut",
    "sparking", "gas leak", "collapsed", "drowning",
    # Kannada
    "ಲೈವ್ ವೈರ್", "ವಿದ್ಯುತ್ ತಂತಿ", "ತೆರೆದ ಮ್ಯಾನ್‌ಹೋಲ್", "ಮ್ಯಾನ್‌ಹೋಲ್ ತೆರೆದ", "ಮಗು ಬಿದ್ದ", "ಕರೆಂಟ್ ಶಾಕ್",
]

# Material each category usually needs (Agent 2 checks stock)
CATEGORY_MATERIAL = {
    "POTHOLE": ("cold_mix_bitumen", 0.5), "DAMAGED_ROAD": ("cold_mix_bitumen", 1.0),
    "STREETLIGHT": ("led_driver_40w", 1), "OPEN_MANHOLE": ("manhole_cover_ci", 1),
    "DRAIN_BLOCKED": ("desilting_kit", 1),
}

SLA_AT_RISK_FRACTION = 0.75
AGENCY_FOLLOWUP_EVERY_H = 24
AGENCY_ESCALATE_AFTER_FOLLOWUPS = 2


def resolution_hours(category: str, priority: str) -> float:
    return RESOLUTION_OVERRIDES.get((category, priority), DEFAULT_RESOLUTION_HOURS[priority])
