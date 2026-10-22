"""Alembic environment, in the shape hop-core AGENTS.md §6 prescribes.

Runs from the CLI (``alembic upgrade head`` in backend/) and in-process at
app startup (``migrate.migrate()``).
"""

import sys
from pathlib import Path

from alembic import context

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so `import models` works from the CLI

import hop_core.models  # noqa: E402,F401  register hop-core's tables so foreign keys resolve
from hop_core import db as hop_db  # noqa: E402
from hop_core.db import Base  # noqa: E402

from models import our_tables  # noqa: E402

OUR_TABLES = our_tables()


def include_object(obj, name, type_, reflected, compare_to):
    return name in OUR_TABLES if type_ == "table" else True


def engine():
    """The CLI has no app startup to initialise hop-core's engine."""
    try:
        return hop_db.get_engine()
    except RuntimeError:
        from settings import get_settings

        hop_db.init_engine(get_settings().database_url)
        return hop_db.get_engine()


with engine().connect() as connection:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        include_object=include_object,
        compare_type=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()
    connection.commit()
