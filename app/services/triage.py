"""Core triage pipeline. Plain functions, no Celery: easy to unit test."""
import logging
import time
import uuid
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Classification, RoutingHistory, Team, Ticket
from app.models.enums import Category, ClassificationSource, RoutingReason, TicketStatus
from app.schemas.classification import ClassificationResult
from app.services.cache import ClassificationCache
from app.services.errors import RateLimited
from app.services.llm import LLMClient
from app.services.ratelimit import LLMRateLimiter

logger = logging.getLogger(__name__)


def _lock_pending_ticket(db: Session, ticket_id: uuid.UUID) -> Ticket | None:
    """Row-lock the ticket and return it only if it is still pending.

    Makes the final write idempotent: a duplicate/redelivered task (acks_late,
    sweeper) finds the ticket already handled and does nothing.
    """
    ticket = db.scalar(
        select(Ticket)
        .where(Ticket.id == ticket_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if ticket is None or ticket.status != TicketStatus.PENDING:
        db.rollback()
        return None
    return ticket


def _team_for_category(db: Session, category: Category) -> Team | None:
    return db.scalar(select(Team).where(Team.handles_category == category))


def _fallback_team(db: Session) -> Team | None:
    return db.scalar(select(Team).where(Team.name == settings.fallback_team_name))


def _route(db: Session, ticket: Ticket, team: Team, reason: RoutingReason) -> None:
    db.add(
        RoutingHistory(
            ticket_id=ticket.id,
            from_team_id=ticket.team_id,
            to_team_id=team.id,
            reason=reason,
        )
    )
    ticket.team_id = team.id


def process_ticket(
    db: Session,
    ticket_id: uuid.UUID,
    *,
    llm: LLMClient,
    cache: ClassificationCache,
    limiter: LLMRateLimiter,
) -> Literal["classified", "skipped"]:
    """cache -> rate limit -> LLM -> persist + route.

    Raises RateLimited / LLMRetryableError / LLMPermanentError for the caller
    (the Celery task) to turn into defer / retry / fallback.
    """
    ticket = db.get(Ticket, ticket_id)
    if ticket is None or ticket.status != TicketStatus.PENDING:
        db.rollback()
        return "skipped"
    subject, body, content_hash = ticket.subject, ticket.body, ticket.content_hash
    # Release the connection/transaction BEFORE the slow network call.
    db.rollback()

    started = time.monotonic()
    result = cache.get(content_hash)
    source, model = ClassificationSource.CACHE, None

    if result is None:
        allowed, retry_after = limiter.acquire()
        if not allowed:
            raise RateLimited(retry_after)
        result = llm.classify(subject, body)
        cache.set(content_hash, result)
        source, model = ClassificationSource.LLM, llm.model

    latency_ms = int((time.monotonic() - started) * 1000)
    return _persist(db, ticket_id, result, source, model, latency_ms)


def _persist(
    db: Session,
    ticket_id: uuid.UUID,
    result: ClassificationResult,
    source: ClassificationSource,
    model: str | None,
    latency_ms: int,
) -> Literal["classified", "skipped"]:
    ticket = _lock_pending_ticket(db, ticket_id)
    if ticket is None:
        return "skipped"

    team = _team_for_category(db, result.category)
    reason = RoutingReason.AUTO
    if team is None:
        logger.error("no team handles category %s, using fallback", result.category.value)
        team, reason = _fallback_team(db), RoutingReason.FALLBACK
    if team is None:
        # Misconfiguration. Leave the ticket pending; the sweeper retries after a fix.
        db.rollback()
        raise RuntimeError("no team available to route ticket (run scripts.seed)")

    db.add(
        Classification(
            ticket_id=ticket.id,
            category=result.category,
            urgency=result.urgency,
            summary=result.summary,
            source=source,
            model=model,
            latency_ms=latency_ms,
        )
    )
    _route(db, ticket, team, reason)
    ticket.status = TicketStatus.CLASSIFIED
    db.commit()
    logger.info(
        "ticket %s classified category=%s urgency=%s source=%s latency_ms=%d",
        ticket.id, result.category.value, result.urgency.value, source.value, latency_ms,
    )
    return "classified"


def route_to_fallback(db: Session, ticket_id: uuid.UUID, reason: str) -> None:
    """Last resort: a human triages it. Nothing is ever silently lost."""
    ticket = _lock_pending_ticket(db, ticket_id)
    if ticket is None:
        return
    ticket.status = TicketStatus.FAILED
    team = _fallback_team(db)
    if team is None:
        logger.critical("ticket %s failed and no fallback team exists", ticket_id)
    else:
        _route(db, ticket, team, RoutingReason.FALLBACK)
    db.commit()
    logger.warning("ticket %s routed to fallback: %s", ticket_id, reason)
