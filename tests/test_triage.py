import httpx
import pytest
from google.genai import errors
from sqlalchemy import select

import app.tasks as tasks
from app.models import Classification, RoutingHistory, Ticket
from app.models.enums import ClassificationSource, RoutingReason, TicketStatus
from app.schemas.classification import ClassificationResult
from app.services import llm as llm_mod
from app.services.cache import ClassificationCache
from app.services.errors import LLMPermanentError, LLMRetryableError, RateLimited
from app.services.ratelimit import LLMRateLimiter
from app.services.text import normalize
from app.services.triage import process_ticket, route_to_fallback
from tests.conftest import FakeLLM


def run(db, ticket, llm, redis_client, limit=100):
    return process_ticket(
        db,
        ticket.id,
        llm=llm,
        cache=ClassificationCache(redis_client, ttl=60),
        limiter=LLMRateLimiter(redis_client, limit=limit, window_seconds=60),
    )


def test_classifies_and_routes(db, redis_client, seeded, make_ticket):
    t = make_ticket()
    llm = FakeLLM()
    assert run(db, t, llm, redis_client) == "classified"

    db.expire_all()
    t = db.get(Ticket, t.id)
    assert t.status == TicketStatus.CLASSIFIED
    assert t.team_id == seeded["Billing"]
    c = db.scalars(select(Classification)).one()
    assert (c.category.value, c.urgency.value, c.source) == ("billing", "high", ClassificationSource.LLM)
    h = db.scalars(select(RoutingHistory)).one()
    assert h.reason == RoutingReason.AUTO and h.from_team_id is None


def test_near_duplicate_hits_cache_without_llm_call(db, redis_client, seeded, make_ticket):
    llm = FakeLLM()
    a = make_ticket("Order 1234567 not delivered", "Where is my order #1234567?")
    b = make_ticket("Order 7654321 not delivered", "Where is my order #7654321?")
    assert a.content_hash == b.content_hash

    run(db, a, llm, redis_client)
    run(db, b, llm, redis_client)

    assert llm.calls == 1
    sources = {c.source for c in db.scalars(select(Classification))}
    assert sources == {ClassificationSource.LLM, ClassificationSource.CACHE}


def test_processing_is_idempotent(db, redis_client, seeded, make_ticket):
    t = make_ticket()
    llm = FakeLLM()
    assert run(db, t, llm, redis_client) == "classified"
    assert run(db, t, llm, redis_client) == "skipped"
    assert len(db.scalars(select(Classification)).all()) == 1


def test_rate_limit_defers_and_does_not_call_llm(db, redis_client, seeded, make_ticket):
    llm = FakeLLM()
    run(db, make_ticket("one", "first"), llm, redis_client, limit=1)
    t2 = make_ticket("two", "second")
    with pytest.raises(RateLimited) as exc:
        run(db, t2, llm, redis_client, limit=1)
    assert 1 <= exc.value.retry_after <= 65
    assert llm.calls == 1
    db.expire_all()
    assert db.get(Ticket, t2.id).status == TicketStatus.PENDING


def test_llm_errors_propagate_and_leave_ticket_pending(db, redis_client, seeded, make_ticket):
    t = make_ticket()
    with pytest.raises(LLMRetryableError):
        run(db, t, FakeLLM(error=LLMRetryableError("boom")), redis_client)
    db.expire_all()
    assert db.get(Ticket, t.id).status == TicketStatus.PENDING


def test_route_to_fallback(db, seeded, make_ticket):
    t = make_ticket()
    route_to_fallback(db, t.id, "test")
    db.expire_all()
    t = db.get(Ticket, t.id)
    assert t.status == TicketStatus.FAILED and t.team_id == seeded["Triage"]
    assert db.scalars(select(RoutingHistory)).one().reason == RoutingReason.FALLBACK


def test_limiter_fails_closed_when_redis_down():
    import redis as redis_lib

    class Down:
        def pipeline(self, **_):
            raise redis_lib.exceptions.ConnectionError("down")

    allowed, retry = LLMRateLimiter(Down(), limit=10).acquire()
    assert allowed is False and retry > 0


def test_cache_fails_open_when_redis_down():
    import redis as redis_lib

    class Down:
        def get(self, *_, **__):
            raise redis_lib.exceptions.ConnectionError("down")

        def set(self, *_, **__):
            raise redis_lib.exceptions.ConnectionError("down")

    cache = ClassificationCache(Down())
    assert cache.get("x") is None
    cache.set("x", ClassificationResult(category="general", urgency="low", summary="s"))


def test_normalize_masks_volatile_tokens():
    a = normalize("Refund!!", "Order 123456 see https://x.io/a?b=1 or me@x.com")
    b = normalize("refund", "order 999999 see https://y.io/z or you@y.org")
    assert a == b


# ---- LLM client: response parsing and error mapping ----

class _Resp:
    def __init__(self, text):
        self.text = text


def test_parse_response_ok():
    r = llm_mod.parse_response(
        _Resp('{"category": "technical", "urgency": "critical", "summary": "API down\\nfor all users"}')
    )
    assert r.category.value == "technical" and r.summary == "API down for all users"


@pytest.mark.parametrize(
    "text",
    [None, "", "not json", '{"category": "weird", "urgency": "low", "summary": "x"}', '{"category": "billing"}'],
)
def test_parse_response_bad_output_is_retryable(text):
    with pytest.raises(LLMRetryableError):
        llm_mod.parse_response(_Resp(text))


def _classifier_raising(exc):
    c = llm_mod.GeminiClassifier("k", "m")

    class Models:
        def generate_content(self, **_):
            raise exc

    c._client = type("C", (), {"models": Models()})()
    return c


def test_error_mapping():
    rate = errors.ClientError(
        429, {"error": {"code": 429, "message": "quota", "details": [{"retryDelay": "12s"}]}}, None
    )
    with pytest.raises(RateLimited) as e:
        _classifier_raising(rate).classify("s", "b")
    assert e.value.retry_after == 12

    with pytest.raises(RateLimited) as e:  # no RetryInfo -> default
        _classifier_raising(errors.ClientError(429, {"error": {"message": "quota"}}, None)).classify("s", "b")
    assert e.value.retry_after == 30

    with pytest.raises(LLMRetryableError):
        _classifier_raising(errors.ServerError(503, {"error": {"message": "overloaded"}}, None)).classify("s", "b")
    with pytest.raises(LLMPermanentError):  # Gemini reports a bad API key as 400
        _classifier_raising(errors.ClientError(400, {"error": {"message": "API key not valid"}}, None)).classify("s", "b")
    with pytest.raises(LLMPermanentError):
        _classifier_raising(errors.ClientError(404, {"error": {"message": "model not found"}}, None)).classify("s", "b")
    with pytest.raises(LLMRetryableError):
        _classifier_raising(httpx.ReadTimeout("slow")).classify("s", "b")


# ---- Celery task wrapper ----

@pytest.fixture()
def wired_tasks(monkeypatch, SessionFactory, redis_client):
    monkeypatch.setattr(tasks, "SessionLocal", SessionFactory)
    monkeypatch.setattr(tasks, "cache_client", redis_client)
    monkeypatch.setattr(tasks, "ratelimit_client", redis_client)


def test_task_falls_back_after_retries_exhausted(monkeypatch, wired_tasks, db, seeded, make_ticket):
    t = make_ticket()
    monkeypatch.setattr(tasks, "get_llm_client", lambda: FakeLLM(error=LLMRetryableError("boom")))
    monkeypatch.setattr(tasks.settings, "llm_max_retries", 0)
    tasks.classify_ticket.run(str(t.id))
    db.expire_all()
    got = db.get(Ticket, t.id)
    assert got.status == TicketStatus.FAILED and got.team_id == seeded["Triage"]


def test_task_permanent_error_goes_straight_to_fallback(monkeypatch, wired_tasks, db, seeded, make_ticket):
    t = make_ticket()
    monkeypatch.setattr(tasks, "get_llm_client", lambda: FakeLLM(error=LLMPermanentError("401")))
    tasks.classify_ticket.run(str(t.id))
    db.expire_all()
    assert db.get(Ticket, t.id).status == TicketStatus.FAILED


def test_task_rate_limited_requeues_with_countdown(monkeypatch, wired_tasks, db, seeded, make_ticket):
    t = make_ticket()
    monkeypatch.setattr(tasks, "get_llm_client", lambda: FakeLLM(error=RateLimited(17)))
    calls = []
    monkeypatch.setattr(tasks.classify_ticket, "apply_async", lambda **kw: calls.append(kw))
    # provider-side 429 surfaces as RateLimited from llm.classify
    tasks.classify_ticket.run(str(t.id), 3)
    assert calls == [{"args": [str(t.id), 4], "countdown": 17}]
    db.expire_all()
    assert db.get(Ticket, t.id).status == TicketStatus.PENDING


def test_task_happy_path(monkeypatch, wired_tasks, db, seeded, make_ticket):
    t = make_ticket()
    monkeypatch.setattr(tasks, "get_llm_client", lambda: FakeLLM())
    tasks.classify_ticket.run(str(t.id))
    db.expire_all()
    assert db.get(Ticket, t.id).status == TicketStatus.CLASSIFIED
