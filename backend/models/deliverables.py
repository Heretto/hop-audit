import uuid

from hop_core.db import Base
from sqlalchemy import JSON, Boolean, Column, ForeignKey, String, Uuid

from models.types import UTCDateTime


class Deliverables(Base):
    """A prospect review's collateral for one audit (deliverables.py): the
    Collateral Writer's copy as edited, the counts it was written against, the
    one-sheets' measured heights, and the hand-off checks someone ticked.

    One row per run rather than one per one-sheet: the two share their copy,
    and everything else they show is computed from the triage when rendered.
    """

    __tablename__ = "deliverables"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id = Column(Uuid, ForeignKey("audit_runs.id", ondelete="CASCADE"), nullable=False, unique=True)
    copy = Column(JSON, nullable=False, default=dict)  # deliverables.Copy
    counts = Column(JSON, nullable=False, default=dict)  # triaged totals when the copy was written
    heights = Column(JSON, nullable=False, default=dict)  # kind -> natural content height in px
    spot_checked = Column(Boolean, nullable=False, default=False)  # one-sheet quotes checked in a browser
    marketing_ok = Column(Boolean, nullable=False, default=False)  # logo use cleared with Heretto marketing
    agent_name = Column(String(255), nullable=False, default="")
    built_by = Column(String(255), nullable=True)
    built_at = Column(UTCDateTime, nullable=True)
