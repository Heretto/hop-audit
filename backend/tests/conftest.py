"""App and client fixtures against a throwaway SQLite database.

Environment variables are set before ``main`` is imported, and they take
precedence over any developer .env at the repo root.
"""

import os
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_DB = Path(tempfile.mkdtemp(prefix="hop-audit-test-")) / "test.db"
os.environ.update(
    APP_ENV="test",
    APP_SECRET_KEY="test-app-secret-key-0123456789abcdef",
    JWT_SECRET_KEY="test-jwt-secret-key-0123456789abcdef",
    ENCRYPTION_KEY="test-encryption-key-0123456789",
    DATABASE_URL=f"sqlite:///{_DB}",
    CORS_ORIGINS="http://localhost:4200",
)

import hop_core.core.security as _security  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def app():
    _security._fernet = None
    _security._legacy_fernet = None
    from main import app

    return app


@pytest.fixture(scope="session")
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _isolate(client):
    from hop_core.core.rate_limit import limiter

    limiter.reset()
    yield
    client.cookies.clear()


@pytest.fixture
def db(client):
    from hop_core.db import get_session_factory

    session = get_session_factory()()
    yield session
    session.close()


def make_user(client) -> dict:
    """Register and log in a fresh user (with their own organization)."""
    email = f"test-{uuid.uuid4().hex[:8]}@example.com"
    password = "SecurePass123!"
    r = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    client.cookies.clear()  # authenticate by header only, as the SPA's interceptor does
    return {"email": email, "headers": {"Authorization": f"Bearer {r.json()['access_token']}"}}


@pytest.fixture
def user(client):
    return make_user(client)
