"""HOP Audit's tables. They share hop-core's declarative Base.

Import every model module here: migrations and ``our_tables()`` see only what
this package has imported.
"""

from hop_core.db import Base

from models.setup import OrgSetup

__all__ = ["OrgSetup", "our_tables"]


def our_tables() -> set[str]:
    """Names of the tables this app owns, derived so a new model can't be missed."""
    return {m.class_.__tablename__ for m in Base.registry.mappers if m.class_.__module__.split(".")[0] == __name__}
