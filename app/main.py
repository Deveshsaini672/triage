
from contextlib import asynccontextmanager

from fastapi import FastAPI

import app.models 
from app.api import auth, health, teams, tickets
from app.core.logging import configure_logging
from app.db.base import Base
from app.db.session import engine

configure_logging()


@asynccontextmanager
async def lifespan(_: FastAPI):
   
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Support Ticket Triage", lifespan=lifespan)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(tickets.router)
app.include_router(teams.router)
