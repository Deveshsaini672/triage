from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_agent
from app.db.session import get_db
from app.models import Agent, Team
from app.schemas.team import TeamOut

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("", response_model=list[TeamOut])
def list_teams(_: Agent = Depends(get_current_agent), db: Session = Depends(get_db)):
    return db.scalars(select(Team).order_by(Team.id)).all()
