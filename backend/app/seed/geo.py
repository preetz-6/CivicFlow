"""Demo geography around Kengeri / Rajarajeshwari Nagar (approximate, synthetic).

Coordinates are (lat, lon). Ward boundaries are APPROXIMATE DEMO BOUNDARIES, not BBMP wards.
Everything the demo story depends on is pinned here so the seed, the simulator and the
replay cache all see identical coordinates.
"""
from shapely.geometry import LineString, MultiPolygon, Polygon, box
from shapely.ops import unary_union

# ----- wards (lon/lat boxes) ---------------------------------------------------------------
_W12 = box(77.460, 12.900, 77.500, 12.925)
_W14 = box(77.460, 12.925, 77.500, 12.950)
_W13 = box(77.500, 12.915, 77.550, 12.950)
_W15 = unary_union([box(77.500, 12.880, 77.550, 12.915), box(77.460, 12.880, 77.500, 12.900)])

WARDS = [
    # id, name, name_kn, zone, geom
    ("W12", "Kengeri", "ಕೆಂಗೇರಿ", "West Zone", _W12),
    ("W13", "Rajarajeshwari Nagar", "ರಾಜರಾಜೇಶ್ವರಿ ನಗರ", "West Zone", _W13),
    ("W14", "Kengeri Satellite Town", "ಕೆಂಗೇರಿ ಉಪನಗರ", "West Zone", _W14),
    ("W15", "Hemmigepura", "ಹೆಮ್ಮಿಗೆಪುರ", "West Zone", _W15),
]
CITY_BOUNDARY = unary_union([w[4] for w in WARDS]).buffer(0.002)


def as_multi(g) -> MultiPolygon:
    return g if isinstance(g, MultiPolygon) else MultiPolygon([g])


def ward_of(lat: float, lon: float) -> str | None:
    from shapely.geometry import Point

    p = Point(lon, lat)
    for wid, *_rest, g in WARDS:
        if g.covers(p):
            return wid
    return None


# ----- roads ---------------------------------------------------------------------------------
MYSORE_ROAD = [(12.9005, 77.4700), (12.9080, 77.4830), (12.9170, 77.5000), (12.9260, 77.5180), (12.9350, 77.5340)]
UTTARAHALLI_ROAD = [(12.9050, 77.4900), (12.9052, 77.5100), (12.9048, 77.5300), (12.9050, 77.5450)]
ARTERIAL_ROADS = [("Mysore Road (NH-275)", MYSORE_ROAD), ("Uttarahalli Main Road", UTTARAHALLI_ROAD)]
LOCAL_ROADS = [
    ("Kengeri Satellite Town 1st Main", [(12.9150, 77.4650), (12.9150, 77.4980)]),
    ("Kengeri Satellite Town 4th Cross", [(12.9300, 77.4650), (12.9300, 77.4980)]),
    ("Kommaghatta Road", [(12.9190, 77.4620), (12.9440, 77.4750)]),
    ("Kengeri Main Road", [(12.9020, 77.4750), (12.9110, 77.4900)]),
    ("Valagerahalli Road", [(12.9100, 77.4700), (12.9250, 77.4700)]),
    ("Ideal Homes Road", [(12.9210, 77.5150), (12.9210, 77.5450)]),
    ("RR Nagar 5th Main", [(12.9300, 77.5050), (12.9300, 77.5450)]),
    ("BEML Layout Road", [(12.9400, 77.5050), (12.9400, 77.5450)]),
    ("Channasandra Main Road", [(12.8950, 77.5050), (12.8950, 77.5450)]),
    ("Hemmigepura Main Road", [(12.8850, 77.4700), (12.8850, 77.5400)]),
    ("SJBIT Road", [(12.8930, 77.4900), (12.9050, 77.5000)]),
    ("Gnanabharathi Link Road", [(12.9320, 77.5000), (12.9450, 77.5200)]),
    ("Pattanagere Road", [(12.9180, 77.5100), (12.9420, 77.5100)]),
    ("Halagevaderahalli Road", [(12.9250, 77.5300), (12.9450, 77.5300)]),
    ("Kengeri Hobli Road", [(12.8900, 77.4650), (12.8990, 77.4950)]),
]


def line(points) -> LineString:
    return LineString([(lon, lat) for lat, lon in points])


def interp(points, t: float) -> tuple[float, float]:
    ls = line(points)
    p = ls.interpolate(t, normalized=True)
    return (round(p.y, 6), round(p.x, 6))


# ----- named demo places -------------------------------------------------------------------
SCHOOL = (12.9102, 77.4851)          # Govt. Higher Primary School, Kengeri
BUS_STAND = (12.9077, 77.4826)       # Kengeri TTMC Bus Stand
POLE_00871 = (12.9080, 77.4830)      # repeat-failure streetlight (BESCOM feeder F-KGR-07)
STREETLIGHT_DEMO_SR = (12.9079, 77.4828)

# Citizen pothole the demo citizen files live (Kannada UI), 40-45 m from the school gate
POTHOLE_SCHOOL = (12.9099, 77.4855)

# Unreported pothole on Mysore Road (arterial), found only by vehicles
POTHOLE_ARTERIAL = interp(MYSORE_ROAD, 0.42)

# Spot repaired 10 days before the demo that starts getting hits again
POTHOLE_REPAIRED = (12.9052, 77.5205)

# Pre-seeded job that crosses 75% SLA a few minutes into the demo (crew W12-B overloaded)
ATRISK_JOB = (12.9165, 77.4920)

KENGERI_UNDERPASS = (12.9131, 77.4893)
RR_NAGAR_ARCH_DRAIN = (12.9274, 77.5155)

SPEED_BREAKERS = [
    ("Speed breaker near Kengeri Satellite Town bus stop", (12.9150, 77.4760)),
    ("Speed breaker, Kommaghatta Road school zone", (12.9255, 77.4655)),
    ("Speed breaker, Valagerahalli Road", (12.9190, 77.4700)),
    ("Speed breaker, Ideal Homes Road", (12.9210, 77.5250)),
    ("Speed breaker, Channasandra Main Road", (12.8950, 77.5150)),
]
RAIL_CROSSINGS = [("Kengeri railway level crossing", (12.9068, 77.4795))]

# True potholes the simulator hits. kind drives what Agent 3 should do with each.
#  school       -> corroborates the live citizen complaint
#  arterial     -> strong, no complaint -> system complaint
#  repaired     -> repaired 10 days ago -> repair-failure flag
#  seeded_open  -> an open seeded citizen complaint is within 25 m -> corroboration
#  unreported   -> strong, no complaint -> system complaint (local road)
#  weak         -> 2 vehicles / low confidence -> officer review queue
TRUE_POTHOLES = [
    ("PH-01", "school", POTHOLE_SCHOOL, 7),
    ("PH-02", "arterial", POTHOLE_ARTERIAL, 9),
    ("PH-03", "repaired", POTHOLE_REPAIRED, 5),
    ("PH-04", "seeded_open", (12.9302, 77.4800), 4),
    ("PH-05", "seeded_open", (12.9210, 77.5320), 5),
    ("PH-06", "seeded_open", (12.8952, 77.5320), 4),
    ("PH-07", "seeded_open", (12.9399, 77.5150), 3),
    ("PH-08", "seeded_open", (12.9150, 77.4900), 6),
    ("PH-09", "seeded_open", (12.8851, 77.5000), 3),
    ("PH-10", "unreported", (12.9301, 77.5400), 4),
    ("PH-11", "unreported", (12.9440, 77.5300), 3),
    ("PH-12", "unreported", (12.8990, 77.4930), 5),
    ("PH-13", "weak", (12.9420, 77.5100), 2),
    ("PH-14", "weak", (12.8870, 77.4720), 2),
    ("PH-15", "weak", (12.9230, 77.4700), 1),
]


def demo_points() -> dict:
    """Shared with the simulator (served at GET /api/v1/demo/points)."""
    return {
        "bbox": {"lat_min": 12.88, "lat_max": 12.95, "lon_min": 77.46, "lon_max": 77.55},
        "potholes": [
            {"id": pid, "kind": kind, "lat": lat, "lon": lon, "vehicles": n}
            for pid, kind, (lat, lon), n in TRUE_POTHOLES
        ],
        "speed_breakers": [{"name": n, "lat": la, "lon": lo} for n, (la, lo) in SPEED_BREAKERS],
        "rail_crossings": [{"name": n, "lat": la, "lon": lo} for n, (la, lo) in RAIL_CROSSINGS],
        "rain_areas": [
            {"name": "Kengeri Underpass", "lat": KENGERI_UNDERPASS[0], "lon": KENGERI_UNDERPASS[1], "reports": 17},
            {"name": "RR Nagar Arch", "lat": RR_NAGAR_ARCH_DRAIN[0], "lon": RR_NAGAR_ARCH_DRAIN[1], "reports": 8},
        ],
        "school_pothole": {"lat": POTHOLE_SCHOOL[0], "lon": POTHOLE_SCHOOL[1]},
        "streetlight_demo": {"lat": STREETLIGHT_DEMO_SR[0], "lon": STREETLIGHT_DEMO_SR[1]},
    }


def polygon_from_line(points, width_deg: float = 0.0006) -> Polygon:
    return line(points).buffer(width_deg)
