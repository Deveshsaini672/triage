import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import Agent

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_agent(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Agent:
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        agent_id = int(payload["sub"])
    except (jwt.PyJWTError, ValueError):
        raise unauthorized

    # Loaded fresh every request: team changes and deactivation apply immediately.
    agent = db.get(Agent, agent_id)
    if agent is None or not agent.is_active:
        raise unauthorized
    return agent
