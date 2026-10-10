import enum

from sqlalchemy import Enum as SAEnum


class TicketStatus(str, enum.Enum):
    PENDING = "pending"
    CLASSIFIED = "classified"
    FAILED = "failed"


class Category(str, enum.Enum):
    BILLING = "billing"
    TECHNICAL = "technical"
    GENERAL = "general"


class Urgency(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ClassificationSource(str, enum.Enum):
    LLM = "llm"
    CACHE = "cache"


class RoutingReason(str, enum.Enum):
    AUTO = "auto"
    MANUAL = "manual"
    FALLBACK = "fallback"


def pg_enum(enum_cls: type[enum.Enum], name: str) -> SAEnum:
    """VARCHAR + CHECK constraint, storing the lowercase *values*."""
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=20,
        values_callable=lambda e: [m.value for m in e],
    )
