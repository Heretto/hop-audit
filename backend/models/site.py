import uuid

from hop_core.db import Base
from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func


class Site(Base):
    """A documentation site or help center the organization audits.

    Settings that are only ever read and written whole (crawl rules, the
    enabled analyses and categories, agent assignments, schedule, prospect
    details) are JSON; their shapes are the schemas in ``schemas.site``.
    """

    __tablename__ = "sites"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id = Column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    start_url = Column(String(2048), nullable=False)
    description = Column(Text, nullable=False, default="")
    purpose = Column(String(16), nullable=False, default="own")  # own | prospect
    crawl = Column(JSON, nullable=False, default=dict)
    analyses = Column(JSON, nullable=False, default=list)
    integrity_categories = Column(JSON, nullable=False, default=list)
    focus = Column(Text, nullable=False, default="")
    agent_assignments = Column(JSON, nullable=False, default=dict)  # analysis -> agent id
    schedule = Column(JSON, nullable=False, default=dict)
    prospect = Column(JSON, nullable=False, default=dict)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    help_centers = relationship(
        "HelpCenter",
        back_populates="site",
        cascade="all, delete-orphan",
        order_by="HelpCenter.position",
    )


class HelpCenter(Base):
    """One locale or language version of a site.

    Non-primary help centers are compared against the primary; two versions
    of one language are compared with each other.
    """

    __tablename__ = "help_centers"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    site_id = Column(Uuid, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    url = Column(String(2048), nullable=False)
    language = Column(String(35), nullable=False)  # BCP 47 tag: en, fr-CA
    is_primary = Column(Boolean, nullable=False, default=False)
    position = Column(Integer, nullable=False, default=0)

    site = relationship("Site", back_populates="help_centers")
