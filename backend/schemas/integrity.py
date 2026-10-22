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
