import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import TicketStatus, pg_enum


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (Index("ix_tickets_team_id_created_at", "team_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    customer_email: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[TicketStatus] = mapped_column(
        pg_enum(TicketStatus, "ticket_status"), default=TicketStatus.PENDING
    )
    team_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id", ondelete="RESTRICT")
    )
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


    classifications = relationship(
        "Classification",
        back_populates="ticket",
        order_by="Classification.id.desc()",
    )
    routing_history = relationship("RoutingHistory", order_by="RoutingHistory.id")

    @property
    def latest_classification(self):
        return self.classifications[0] if self.classifications else None
