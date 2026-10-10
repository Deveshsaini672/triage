from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import Category, pg_enum


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    # NULL = fallback/triage team (receives tickets when classification fails)
    handles_category: Mapped[Category | None] = mapped_column(
        pg_enum(Category, "team_category"), unique=True, nullable=True
    )
