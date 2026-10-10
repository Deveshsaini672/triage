import logging
import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_agent
from app.core.config import settings
from app.db.session import get_db
from app.models import Agent, RoutingHistory, Team, Ticket
from app.models.enums import RoutingReason, TicketStatus
from app.schemas.ticket import (
    ReassignRequest,
    TicketAccepted,
    TicketCreate,
    TicketDetail,
    TicketOut,
)
from app.services.text import content_hash
from app.tasks import classify_ticket

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tickets", tags=["tickets"])


def require_api_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
    """Ingest is for upstream systems (email gateway, web form), not agents."""
    if not x_api_key or not secrets.compare_digest(
        x_api_key.encode(), settings.ingest_api_key.encode()
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")


def _enqueue(ticket_id: uuid.UUID) -> None:
    try:
        classify_ticket.delay(str(ticket_id))
    except Exception:
        # The ticket is already committed. Don't fail the request; the periodic
        # sweeper re-enqueues anything left pending.
        logger.exception("failed to enqueue ticket %s", ticket_id)


def _team_ticket_stmt(ticket_id: uuid.UUID, agent: Agent):
    # Ownership lives in the query: someone else's ticket == a missing ticket.
    return select(Ticket).where(Ticket.id == ticket_id, Ticket.team_id == agent.team_id)


@router.post(
    "",
    response_model=TicketAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_api_key)],
)
def create_ticket(payload: TicketCreate, db: Session = Depends(get_db)):
    ticket = Ticket(
        subject=payload.subject,
        body=payload.body,
        customer_email=payload.customer_email,
        content_hash=content_hash(payload.subject, payload.body),
    )
    db.add(ticket)
    db.commit()
    _enqueue(ticket.id)  # strictly AFTER commit: the worker must be able to see the row
    return ticket


@router.get("", response_model=list[TicketOut])
def list_tickets(
    status_filter: TicketStatus | None = Query(None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    stmt = (
        select(Ticket)
        .where(Ticket.team_id == agent.team_id)
        .options(selectinload(Ticket.classifications))
    )
    if status_filter is not None:
        stmt = stmt.where(Ticket.status == status_filter)
    stmt = (
        stmt.order_by(Ticket.created_at.desc(), Ticket.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return db.scalars(stmt).all()


@router.get("/{ticket_id}", response_model=TicketDetail)
def get_ticket(
    ticket_id: uuid.UUID,
    agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    ticket = db.scalar(
        _team_ticket_stmt(ticket_id, agent).options(
            selectinload(Ticket.classifications),
            selectinload(Ticket.routing_history),
        )
    )
    if ticket is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    return ticket


@router.patch("/{ticket_id}/reassign", response_model=TicketDetail)
def reassign_ticket(
    ticket_id: uuid.UUID,
    payload: ReassignRequest,
    agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    ticket = db.scalar(_team_ticket_stmt(ticket_id, agent).with_for_update())
    if ticket is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    if payload.team_id == ticket.team_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ticket is already on that team")
    if db.get(Team, payload.team_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found")

    db.add(
        RoutingHistory(
            ticket_id=ticket.id,
            from_team_id=ticket.team_id,
            to_team_id=payload.team_id,
            reason=RoutingReason.MANUAL,
            actor_agent_id=agent.id,
        )
    )
    ticket.team_id = payload.team_id
    db.commit()
    db.refresh(ticket)
    return ticket
