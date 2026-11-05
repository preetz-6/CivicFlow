from __future__ import annotations

from dataclasses import dataclass

from app.models.enums import ActorKind, Role


@dataclass(frozen=True)
class Actor:
    kind: ActorKind
    id: str  # "user:12" | "agent:investigator" | "system:sla"
    label: str
    role: Role | None = None
    user_id: int | None = None
    ward_id: str | None = None
    zone: str | None = None
    crew_id: str | None = None

    @classmethod
    def from_user(cls, u) -> Actor:
        return cls(
            kind=ActorKind.HUMAN, id=f"user:{u.id}", label=f"{u.name} ({u.designation or u.role})",
            role=Role(u.role), user_id=u.id, ward_id=u.ward_id, zone=u.zone, crew_id=u.crew_id,
        )

    @classmethod
    def agent(cls, name: str) -> Actor:
        return cls(kind=ActorKind.AGENT, id=f"agent:{name}", label="System (automated analysis)")

    @classmethod
    def system(cls, name: str = "workflow") -> Actor:
        return cls(kind=ActorKind.SYSTEM, id=f"system:{name}", label="System")

    @property
    def is_human(self) -> bool:
        return self.kind == ActorKind.HUMAN
