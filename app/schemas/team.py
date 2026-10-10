from pydantic import BaseModel, ConfigDict

from app.models.enums import Category


class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    handles_category: Category | None


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    team_id: int
