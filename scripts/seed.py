"""Idempotent dev seed. Run from project root:  python -m scripts.seed"""
from sqlalchemy import select

import app.models  # noqa: F401
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import Agent, Team
from app.models.enums import Category

DEV_PASSWORD = "password123"  # dev only

TEAMS: list[tuple[str, Category | None]] = [
    ("Billing", Category.BILLING),
    ("Technical", Category.TECHNICAL),
    ("General", Category.GENERAL),
    ("Triage", None),  # fallback team for failed classifications
]

AGENTS = [
    ("billing@example.com", "Billing"),
    ("tech@example.com", "Technical"),
    ("general@example.com", "General"),
    ("triage@example.com", "Triage"),
]


def main() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        teams: dict[str, Team] = {}
        for name, category in TEAMS:
            team = db.scalar(select(Team).where(Team.name == name))
            if team is None:
                team = Team(name=name, handles_category=category)
                db.add(team)
                db.flush()
            teams[name] = team

        for email, team_name in AGENTS:
            if db.scalar(select(Agent).where(Agent.email == email)) is None:
                db.add(
                    Agent(
                        email=email,
                        password_hash=hash_password(DEV_PASSWORD),
                        team_id=teams[team_name].id,
                    )
                )
        db.commit()
    print(f"Seeded teams and agents. Dev password: {DEV_PASSWORD}")


if __name__ == "__main__":
    main()
