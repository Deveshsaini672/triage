import logging
import random
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.celery_app import celery_app
from app.core.config import settings
from app.core.redis import cache_client, ratelimit_client
from app.db.session import SessionLocal
from app.models import Ticket
from app.models.enums import TicketStatus
from app.services.cache import ClassificationCache
from app.services.errors import LLMPermanentError, LLMRetryableError, RateLimited
from app.services.llm import get_llm_client
from app.services.ratelimit import LLMRateLimiter
from app.services.triage import process_ticket, route_to_fallback

logger = logging.getLogger(__name__)


def _backoff(attempt: int) -> float:
    return min(5 * 2**attempt, 120) + random.uniform(0, 3)


@celery_app.task(
    bind=True,
    name="triage.classify_ticket",
    acks_late=True,
    soft_time_limit=45,
    time_limit=60,
)
def classify_ticket(self, ticket_id: str, deferrals: int = 0) -> None:
    tid = uuid.UUID(ticket_id)
    with SessionLocal() as db:
        try:
            process_ticket(
                db,
                tid,
                llm=get_llm_client(),
                cache=ClassificationCache(cache_client),
                limiter=LLMRateLimiter(ratelimit_client),
            )
        except RateLimited as exc:
            db.rollback()
          
            if deferrals >= settings.max_rate_limit_deferrals:
                route_to_fallback(db, tid, "rate-limit deferrals exhausted")
                return
            logger.info("ticket %s deferred %ss (%d)", tid, exc.retry_after, deferrals + 1)
            classify_ticket.apply_async(
                args=[ticket_id, deferrals + 1], countdown=exc.retry_after
            )
        except LLMRetryableError as exc:
            db.rollback()
            if self.request.retries >= settings.llm_max_retries:
                route_to_fallback(db, tid, f"retries exhausted: {exc}")
                return
            raise self.retry(exc=exc, countdown=_backoff(self.request.retries))
        except LLMPermanentError as exc:
            db.rollback()
            route_to_fallback(db, tid, f"permanent LLM error: {exc}")


@celery_app.task(name="triage.sweep_pending")
def sweep_pending() -> int:
    """Safety net: re-enqueue tickets stuck in 'pending'.

    Covers a broker outage at ingest time, lost messages, and tasks that
    crashed on unexpected errors. Safe to over-enqueue because processing is
    idempotent; the Redis NX key stops one ticket being re-enqueued every minute.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(
        seconds=settings.sweeper_pending_after_seconds
    )
    with SessionLocal() as db:
        ids = db.scalars(
            select(Ticket.id)
            .where(Ticket.status == TicketStatus.PENDING, Ticket.created_at < cutoff)
            .order_by(Ticket.created_at)
            .limit(100)
        ).all()

    enqueued = 0
    for tid in ids:
        if ratelimit_client.set(
            f"sweep:{tid}", 1, nx=True, ex=settings.sweeper_pending_after_seconds
        ):
            classify_ticket.delay(str(tid))
            enqueued += 1
    if enqueued:
        logger.info("sweeper re-enqueued %d pending tickets", enqueued)
    return enqueued
