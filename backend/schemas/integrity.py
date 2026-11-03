from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from schemas.run import RunDetail


class Quote(BaseModel):
    label: str
    text: str
    slug: str
    note: str
    page_id: str | None = None
    verified: bool = True
    url: str | None = None  # the article on the site; added when the findings are read


class IntegrityRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    code: str
    category: str
    severity: str
    locale: str
    help_center_ids: list[str]
    title: str
    quotes: list[Quote]
    why: str
    proposed_tier: str
    proposed_reason: str
    tier: str
    triage_note: str
    example_rank: int | None
    first_seen: int
    carried_from: int | None
    agent_name: str


class CenterCount(BaseModel):
    id: UUID
    name: str
    language: str
    is_primary: bool
    articles: int  # distinct articles reviewed
    pages: int  # pages read, failed ones included


class IntegrityView(BaseModel):
    run: RunDetail
    purpose: str  # own | prospect: prospect reviews go on to Deliverables
    triage: dict
    findings: list[IntegrityRow]
    help_centers: list[CenterCount]
    resolved: list[str]


class IntegrityUpdate(BaseModel):
    tier: Literal["firm", "review", "drop"] | None = None
    triage_note: str | None = Field(None, max_length=4000)
    example: bool | None = None


class ClaimRow(BaseModel):
    """A statement the reviewer took from an article, verified on the page."""

    page_id: UUID
    url: str
    slug: str
    title: str
    help_center_id: UUID
    subject: str
    statement: str
    group: int | None  # 1-based index into ClaimsView.groups


class ClaimGroup(BaseModel):
    number: int
    subject: str
    status: Literal["agree", "compared", "kept", "failed"]
    issues: int  # candidates the reviewer raised on this group
    claims: int
    articles: int


class ClaimCenter(BaseModel):
    id: UUID
    name: str


class ClaimsView(BaseModel):
    run: RunDetail
    method: str | None  # how statements were matched; None when pass 3 didn't run
    help_centers: list[ClaimCenter]
    claims: list[ClaimRow]
    groups: list[ClaimGroup]
