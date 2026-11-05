"""Shared API schemas. These ARE the contract with the web app (Machine B)."""
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserOut(ORM):
    id: int
    username: str
    name: str
    role: str
    designation: str | None = None
    ward_id: str | None = None
    zone: str | None = None
    department_id: str | None = None
    crew_id: str | None = None
    language: str = "en"


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class LatLon(BaseModel):
    lat: float
    lon: float


class ClockOut(BaseModel):
    now: datetime
    scale: float
    frozen: bool
