import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import Category, ClassificationSource, Urgency

_WS = re.compile(r"\s+")


class ClassificationResult(BaseModel):
    """What the LLM must return. Also the value stored in the Redis cache."""

    category: Category
    urgency: Urgency
    summary: str = Field(min_length=1, max_length=300)

    @field_validator("summary", mode="before")
    @classmethod
    def _one_line(cls, v):
        if not isinstance(v, str):
            return v
        v = _WS.sub(" ", v).strip()
        return v if len(v) <= 300 else v[:297] + "..."


class ClassificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category: Category
    urgency: Urgency
    summary: str
    source: ClassificationSource
    model: str | None
    created_at: datetime
