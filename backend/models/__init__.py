"""HOP Audit's tables. They share hop-core's declarative Base.

Import every model module here: migrations and ``our_tables()`` see only what
this package has imported.
"""

from hop_core.db import Base

from models.run import (
    ACTIVE_STATUSES,
    AgentFinding,
    AuditRun,
    ClaimGroupReview,
    IntegrityFinding,
    LinkCache,
    LinkResult,
    Page,
    RunLogEntry,
)
from models.setup import OrgSetup
from models.site import HelpCenter, Site

__all__ = [
    "ACTIVE_STATUSES",
    "AgentFinding",
    "AuditRun",
    "ClaimGroupReview",
    "HelpCenter",
    "IntegrityFinding",
    "LinkCache",
    "LinkResult",
    "OrgSetup",
    "Page",
    "RunLogEntry",
    "Site",
    "our_tables",
]


def our_tables() -> set[str]:
    """Names of the tables this app owns, derived so a new model can't be missed."""
    return {m.class_.__tablename__ for m in Base.registry.mappers if m.class_.__module__.split(".")[0] == __name__}
