from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_agent
from app.core.security import DUMMY_HASH, create_access_token, verify_password
from app.db.session import get_db
from app.models import Agent
from app.schemas.auth import Token
from app.schemas.team import AgentOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    # OAuth2 form field is called "username"; we use the agent's email there.
    agent = db.scalar(select(Agent).where(Agent.email == form.username.strip().lower()))

    password_ok = verify_password(form.password, agent.password_hash if agent else DUMMY_HASH)
    if agent is None or not password_ok or not agent.is_active:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(access_token=create_access_token(agent.id))


@router.get("/me", response_model=AgentOut)
def me(agent: Agent = Depends(get_current_agent)):
    return agent
