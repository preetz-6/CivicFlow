from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import JSON, DateTime
from sqlalchemy.dialects.postgresql import JSONB

from app.core.clock import now

TZ = DateTime(timezone=True)
Json = JSON().with_variant(JSONB(), "postgresql")


def Point():  # noqa: N802
    return Geometry("POINT", srid=4326, spatial_index=True)


def AnyGeom():  # noqa: N802
    return Geometry("GEOMETRY", srid=4326, spatial_index=True)


def ts_default() -> datetime:
    return now()


JsonDict = dict[str, Any]
