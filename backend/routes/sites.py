"""Sites and their help centers, scoped to the caller's organization."""

from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from hop_core.api.dependencies import CurrentUserContext, get_current_active_user_with_org
from hop_core.db import get_db
from hop_core.models.agent import Agent
from sqlalchemy.orm import Session, selectinload

import discovery
from models import HelpCenter, OrgSetup, Site
from schemas.site import DetectRequest, SiteIn, SiteOut, SiteSummary

router = APIRouter(prefix="/sites", tags=["sites"])
Ctx = Depends(get_current_active_user_with_org)


def get_site(db: Session, ctx: CurrentUserContext, site_id: UUID) -> Site:
    site = db.get(Site, site_id)
    if site is None or site.organization_id != ctx.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")
    return site


def check_agents(db: Session, ctx: CurrentUserContext, data: SiteIn) -> None:
    """Assigned agents must exist in the caller's organization."""
    wanted = {a for a in data.agent_assignments.values() if a}
    if not wanted:
        return
    found = {
        row.id for row in db.query(Agent.id).filter(Agent.organization_id == ctx.organization_id, Agent.id.in_(wanted))
    }
    if missing := wanted - found:
        raise HTTPException(422, f"Unknown agent: {', '.join(map(str, missing))}")


def apply(site: Site, data: SiteIn) -> None:
    """Copy settings onto the row; help centers keep their ids when sent back."""
    fields = data.model_dump(mode="json", exclude={"help_centers"})
    for key, value in fields.items():
        setattr(site, key, value)
    existing = {hc.id: hc for hc in site.help_centers}
    centers = []
    for position, hc in enumerate(data.help_centers):
        row = existing.get(hc.id) or HelpCenter()
        row.name, row.url, row.language, row.is_primary = hc.name, hc.url, hc.language, hc.is_primary
        row.position = position
        centers.append(row)
    site.help_centers = centers


@router.get("", response_model=list[SiteSummary])
def list_sites(ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    return (
        db.query(Site)
        .options(selectinload(Site.help_centers))
        .filter(Site.organization_id == ctx.organization_id)
        .order_by(Site.name)
        .all()
    )


@router.get("/defaults")
def defaults(ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)) -> dict:
    """A new site's settings (a SiteIn, not yet valid): everything on, each
    analysis on the agent seeded for it, if that agent still exists."""
    setup = db.get(OrgSetup, ctx.organization_id)
    seeded = {k: UUID(v) for k, v in (setup.seeded_agents if setup else {}).items()}
    live = {row.id for row in db.query(Agent.id).filter(Agent.organization_id == ctx.organization_id)}
    draft = SiteIn.model_construct(
        name="", start_url="", help_centers=[], agent_assignments={k: v for k, v in seeded.items() if v in live}
    )
    return draft.model_dump(mode="json")


@router.post("/detect", response_model=dict)
async def detect(body: DetectRequest, ctx: CurrentUserContext = Ctx):
    """Sitemap, sections and hreflang languages for a start URL (nothing is saved)."""
    return asdict(await discovery.detect(body.start_url, body.sitemap_url, body.respect_robots))


@router.post("", response_model=SiteOut, status_code=status.HTTP_201_CREATED)
def create_site(data: SiteIn, ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    check_agents(db, ctx, data)
    site = Site(organization_id=ctx.organization_id, created_by=ctx.user.email)
    apply(site, data)
    db.add(site)
    db.commit()
    db.refresh(site)
    return site


@router.get("/{site_id}", response_model=SiteOut)
def read_site(site_id: UUID, ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    return get_site(db, ctx, site_id)


@router.put("/{site_id}", response_model=SiteOut)
def update_site(site_id: UUID, data: SiteIn, ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    site = get_site(db, ctx, site_id)
    check_agents(db, ctx, data)
    apply(site, data)
    db.commit()
    db.refresh(site)
    return site


@router.delete("/{site_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_site(site_id: UUID, ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    db.delete(get_site(db, ctx, site_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
