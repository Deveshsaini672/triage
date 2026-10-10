import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import Category, ClassificationSource, Urgency, pg_enum


class Classification(Base):
    __tablename__ = "classifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[Category] = mapped_column(pg_enum(Category, "classification_category"))
    urgency: Mapped[Urgency] = mapped_column(pg_enum(Urgency, "classification_urgency"))
    summary: Mapped[str] = mapped_column(Text)
    source: Mapped[ClassificationSource] = mapped_column(
        pg_enum(ClassificationSource, "classification_source")
    )
    model: Mapped[str | None] = mapped_column(String(100))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    ticket = relationship("Ticket", back_populates="classifications")
