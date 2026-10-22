from hop_core.db import Base
from sqlalchemy import JSON, Column, DateTime, ForeignKey, Uuid


class OrgSetup(Base):
    """One-time setup per organization.

    A row means the analysis agents were seeded, so an agent someone deletes
    stays deleted. ``seeded_agents`` maps each analysis to the agent seeded
    for it: the default assignment for a new site.
    """

    __tablename__ = "org_setup"

    organization_id = Column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    agents_seeded_at = Column(DateTime(timezone=True), nullable=False)
    seeded_agents = Column(JSON, nullable=False, default=dict)
