import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import RoutingReason, pg_enum


class RoutingHistory(Base):
    __tablename__ = "routing_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), index=True
    )
    from_team_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id", ondelete="RESTRICT")
    )
    to_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="RESTRICT"))
    reason: Mapped[RoutingReason] = mapped_column(pg_enum(RoutingReason, "routing_reason"))
    actor_agent_id: Mapped[int | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
