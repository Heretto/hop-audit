from fastapi import APIRouter, Depends
from hop_core.api.dependencies import CurrentUserContext, get_current_active_user_with_org
from hop_core.db import get_db
from pydantic import BaseModel
from sqlalchemy.orm import Session

from seed import ensure_setup

router = APIRouter(prefix="/setup", tags=["setup"])


class SetupResponse(BaseModel):
    agents_seeded_at: str
    seeded_agents: dict[str, str]


@router.post("", response_model=SetupResponse)
def setup(
    ctx: CurrentUserContext = Depends(get_current_active_user_with_org),
    db: Session = Depends(get_db),
):
    """Called by the app shell on load; seeds the organization's agents once."""
    row = ensure_setup(db, ctx.organization_id, ctx.user.id, ctx.user.email)
    return SetupResponse(agents_seeded_at=row.agents_seeded_at.isoformat(), seeded_agents=row.seeded_agents)
