import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import RoutingReason, TicketStatus
from app.schemas.classification import ClassificationOut


class TicketCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1, max_length=10_000)
    customer_email: EmailStr | None = None


class TicketAccepted(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: TicketStatus


class RoutingHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_team_id: int | None
    to_team_id: int
    reason: RoutingReason
    actor_agent_id: int | None
    created_at: datetime


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subject: str
    body: str
    customer_email: str | None
    status: TicketStatus
    team_id: int | None
    created_at: datetime
    classification: ClassificationOut | None = Field(
        default=None, validation_alias="latest_classification"
    )


class TicketDetail(TicketOut):
    routing_history: list[RoutingHistoryOut]


class ReassignRequest(BaseModel):
    team_id: int
