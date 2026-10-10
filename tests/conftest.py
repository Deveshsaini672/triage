import os

# Must be set before any `app` import (Settings loads at import time).
os.environ.update(
    DATABASE_URL="postgresql+psycopg://test:test@localhost:5432/test",
    REDIS_BROKER_URL="redis://localhost:6379/0",
    REDIS_CACHE_URL="redis://localhost:6379/1",
    REDIS_RATELIMIT_URL="redis://localhost:6379/2",
    JWT_SECRET="test-secret",
    INGEST_API_KEY="test-key",
    GEMINI_API_KEY="test",
)

import fakeredis  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.models  # noqa: E402,F401
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.models import Agent, Team, Ticket  # noqa: E402
from app.models.enums import Category  # noqa: E402
from app.schemas.classification import ClassificationResult  # noqa: E402
from app.services.text import content_hash  # noqa: E402

PASSWORD = "password123"
_PASSWORD_HASH = hash_password(PASSWORD)  # bcrypt is slow; do it once


class FakeLLM:
    model = "fake-model"

    def __init__(self, result=None, error=None):
        self.result = result or ClassificationResult(
            category="billing", urgency="high", summary="Customer was charged twice."
        )
        self.error = error
        self.calls = 0

    def classify(self, subject, body):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


@pytest.fixture()
def SessionFactory():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture()
def db(SessionFactory):
    with SessionFactory() as session:
        yield session


@pytest.fixture()
def redis_client():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture()
def seeded(db):
    teams = {}
    for name, cat in [
        ("Billing", Category.BILLING),
        ("Technical", Category.TECHNICAL),
        ("General", Category.GENERAL),
        ("Triage", None),
    ]:
        team = Team(name=name, handles_category=cat)
        db.add(team)
        db.flush()
        teams[name] = team.id
    for email, team in [
        ("billing@example.com", "Billing"),
        ("tech@example.com", "Technical"),
        ("triage@example.com", "Triage"),
    ]:
        db.add(Agent(email=email, password_hash=_PASSWORD_HASH, team_id=teams[team]))
    db.commit()
    return teams


@pytest.fixture()
def client(SessionFactory, seeded):
    def _get_db():
        with SessionFactory() as session:
            yield session

    fastapi_app.dependency_overrides[get_db] = _get_db
    yield TestClient(fastapi_app)
    fastapi_app.dependency_overrides.clear()


@pytest.fixture()
def auth(client):
    def _auth(email: str) -> dict:
        r = client.post("/auth/login", data={"username": email, "password": PASSWORD})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return _auth


@pytest.fixture()
def make_ticket(db):
    def _make(subject="Charged twice", body="I was billed twice.", team_id=None):
        t = Ticket(
            subject=subject,
            body=body,
            content_hash=content_hash(subject, body),
            team_id=team_id,
        )
        db.add(t)
        db.commit()
        return t

    return _make
