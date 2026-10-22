"""Bring the database schema up to date before hop-core's startup runs.

hop-core's startup calls ``create_all``, which would create this app's tables
outside Alembic's knowledge. Migrating first means those tables already exist
(and are versioned) by then, so ``create_all`` only ever creates hop-core's.
"""

from pathlib import Path

import hop_core.models  # noqa: F401
from alembic import command
from alembic.config import Config
from hop_core import db as hop_db
from hop_core.db import Base

from models import our_tables

BACKEND = Path(__file__).resolve().parent


def alembic_config() -> Config:
    return Config(str(BACKEND / "alembic.ini"))


def migrate() -> None:
    ours = our_tables()
    # hop-core's tables first: our foreign keys point at them.
    hop_tables = [t for t in Base.metadata.sorted_tables if t.name not in ours]
    Base.metadata.create_all(bind=hop_db.get_engine(), tables=hop_tables)
    command.upgrade(alembic_config(), "head")
