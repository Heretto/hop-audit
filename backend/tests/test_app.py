"""App wiring: health, auth on our routes, hop-core routes mounted, migrations."""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from hop_core.db import Base, get_engine


def test_health_is_public(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_our_routes_require_auth(client):
    assert client.post("/api/v1/setup").status_code == 401


def test_hop_core_routes_mounted(client, user):
    for path in ("/api/v1/agents", "/api/v1/credentials", "/api/v1/organizations/current/members"):
        assert client.get(path, headers=user["headers"]).status_code == 200, path


def test_ai_credential_types_registered(client, user):
    r = client.get("/api/v1/credentials/types", headers=user["headers"])
    assert r.status_code == 200
    types = {t["type"] for t in r.json()}
    assert {"anthropic", "openai", "gemini", "heretto"} <= types


def test_migrations_match_models():
    """A model change without a migration fails here, not in production."""
    from models import our_tables

    ours = our_tables()
    with get_engine().connect() as conn:
        ctx = MigrationContext.configure(
            conn,
            opts={
                "include_object": lambda o, name, type_, *_: name in ours if type_ == "table" else True,
                "compare_type": True,
            },
        )
        assert compare_metadata(ctx, Base.metadata) == []
