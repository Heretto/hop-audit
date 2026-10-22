import uuid

from hop_core.db import Base
from sqlalchemy import JSON, Boolean, Column, Float, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from models.types import UTCDateTime

ACTIVE_STATUSES = ("queued", "running", "paused")


class AuditRun(Base):
    """One audit of a site: what was asked for, how far it got, what it cost.

    ``stages`` is a list of ``{key, label, status, done, total, detail}``,
    rewritten as the run progresses; ``tokens`` maps agent id to tokens used.
    """

    __tablename__ = "audit_runs"
    __table_args__ = (UniqueConstraint("site_id", "number"),)

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id = Column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    site_id = Column(Uuid, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(Integer, nullable=False)
    scope = Column(JSON, nullable=False)  # {mode, sections, pages}
    help_center_ids = Column(JSON, nullable=False, default=list)  # reviewed for content integrity
    analyses = Column(JSON, nullable=False, default=list)
    trigger = Column(String(16), nullable=False, default="manual")  # manual | schedule
    created_by = Column(String(255), nullable=True)
    status = Column(String(16), nullable=False, default="queued")  # queued running paused completed failed cancelled
    reuse_crawl = Column(Boolean, nullable=False, default=True)
    recheck_external = Column(Boolean, nullable=False, default=False)
    focus = Column(Text, nullable=False, default="")
    stages = Column(JSON, nullable=False, default=list)
    tokens = Column(JSON, nullable=False, default=dict)
    page_count = Column(Integer, nullable=False, default=0)
    metrics = Column(JSON, nullable=False, default=dict, server_default="{}")  # see scoring.run_metrics
    error = Column(Text, nullable=True)
    created_at = Column(UTCDateTime, server_default=func.now())
    started_at = Column(UTCDateTime, nullable=True)
    finished_at = Column(UTCDateTime, nullable=True)

    site = relationship("Site")
    log = relationship("RunLogEntry", cascade="all, delete-orphan", order_by="RunLogEntry.id")


class RunLogEntry(Base):
    """One step of a run. Never holds keys, prompts or page text."""

    __tablename__ = "run_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Uuid, ForeignKey("audit_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    at = Column(UTCDateTime, nullable=False)
    stage = Column(String(32), nullable=False)
    level = Column(String(8), nullable=False, default="info")  # info | warn | error
    message = Column(Text, nullable=False)


class Page(Base):
    """A page as one run saw it, in one help center.

    ``content`` is the extraction (see ``extract.PageContent``): text,
    headings, links, images and metadata, which the analyses read.
    """

    __tablename__ = "pages"
    __table_args__ = (UniqueConstraint("run_id", "url"),)

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id = Column(Uuid, ForeignKey("audit_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    help_center_id = Column(Uuid, ForeignKey("help_centers.id", ondelete="CASCADE"), nullable=False, index=True)
    url = Column(String(2048), nullable=False)
    path = Column(String(2048), nullable=False)
    section = Column(String(512), nullable=False)
    title = Column(Text, nullable=False, default="")
    http_status = Column(Integer, nullable=True)
    content_hash = Column(String(64), nullable=True)
    lastmod = Column(UTCDateTime, nullable=True)
    word_count = Column(Integer, nullable=False, default=0)
    content = Column(JSON, nullable=False, default=dict)
    error = Column(Text, nullable=True)
    reused_from_id = Column(Uuid, ForeignKey("pages.id", ondelete="SET NULL"), nullable=True)
    fetched_at = Column(UTCDateTime, nullable=True)

    # Analyses (None until measured, or when not measurable)
    flesch = Column(Float, nullable=True)
    grade = Column(Float, nullable=True)
    words_per_sentence = Column(Float, nullable=True)
    passive_pct = Column(Float, nullable=True)
    sentences = Column(Integer, nullable=True)
    seo = Column(JSON, nullable=True)  # [{key, label, status, detail}]
    seo_issues = Column(Integer, nullable=True)
    links_internal = Column(Integer, nullable=True)
    links_external = Column(Integer, nullable=True)
    broken_links = Column(Integer, nullable=True)
    redirects = Column(Integer, nullable=True)
    anchor_issues = Column(Integer, nullable=True)
    score = Column(Integer, nullable=True)


class LinkResult(Base):
    """One link on one page and what its target answered."""

    __tablename__ = "link_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Uuid, ForeignKey("audit_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    page_id = Column(Uuid, ForeignKey("pages.id", ondelete="CASCADE"), nullable=False, index=True)
    url = Column(String(2048), nullable=False)
    text = Column(Text, nullable=False, default="")
    internal = Column(Boolean, nullable=False)
    outcome = Column(String(16), nullable=False)  # ok | redirect | broken | blocked | anchor
    status = Column(Integer, nullable=True)
    final_url = Column(String(2048), nullable=True)
    note = Column(Text, nullable=False, default="")


class LinkCache(Base):
    """External link outcomes, per organization, reused for a week."""

    __tablename__ = "link_cache"

    organization_id = Column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    url = Column(String(2048), primary_key=True)
    outcome = Column(String(16), nullable=False)
    status = Column(Integer, nullable=True)
    final_url = Column(String(2048), nullable=True)
    note = Column(Text, nullable=False, default="")
    checked_at = Column(UTCDateTime, nullable=False)
