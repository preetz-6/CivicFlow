"""External agency adapter. SIMULATED: messages land in the agency_messages table, which the
'External Agency Inbox (Simulated)' page shows; a presenter types the agency's reply."""
from app.core.clock import now
from app.models import AgencyMessage


class SimulatedAgencyAdapter:
    simulated = True

    def send(self, db, referral, body: str) -> AgencyMessage:
        m = AgencyMessage(referral_id=referral.id, direction="OUT", body=body, at=now())
        db.add(m)
        db.flush()
        return m

    def receive(self, db, referral, body: str) -> AgencyMessage:
        m = AgencyMessage(referral_id=referral.id, direction="IN", body=body, at=now())
        db.add(m)
        db.flush()
        return m


agency_adapter = SimulatedAgencyAdapter()
