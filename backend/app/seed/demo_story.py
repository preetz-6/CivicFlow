"""The exact demo inputs. Recording (AGENT_MODE=record) and the live demo (AGENT_MODE=replay) must use the same
texts, pins and simulator seeds for replay to hit; anything else falls back to rule-based analysis (still correct)."""

SCHOOL_PIN = (12.9099, 77.4855)
STREETLIGHT_PIN = (12.9079, 77.4828)

POTHOLE_REPORTS = [
    # (citizen description, mobile, lat offset) - first is citizen1 in the Kannada UI, then two more citizens
    ("ಶಾಲೆಯ ಗೇಟಿನ ಮುಂದೆ ದೊಡ್ಡ ರಸ್ತೆ ಗುಂಡಿ, ಮಕ್ಕಳು ಸುತ್ತಿ ನಡೆಯಬೇಕಾಗಿದೆ. Big pothole at the school gate.", "9845000001", 0.0),
    ("Huge pothole near the school gate, kids at risk", "9845000002", 0.00003),
    ("Pothole at the school gate, two wheelers falling", "9845000003", -0.00002),
]

STREETLIGHT_REPORT = ("Streetlight not working at Kengeri bus stand, very dark at night, women feel unsafe", "9845000002")

SIM_ONCE_SEED = 7
SIM_RAIN_SEED = 3
