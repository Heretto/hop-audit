from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from deliverables import Copy
from schemas.run import RunDetail


class SpotCheck(BaseModel):
    code: str
    slug: str
    page_id: str | None
    verified: bool


class CheckItem(BaseModel):
    key: str
    ok: bool
    text: str
    toggle: bool = False  # a person ticks it (spot-check done, marketing cleared)
    quotes: list[SpotCheck] = []


class ProspectOut(BaseModel):
    company: str
    sender_name: str
    sender_title: str
    sender_email: str
    logo: str | None  # data URI


class BuildLogEntry(BaseModel):
    at: datetime
    level: Literal["info", "warn", "error"]
    message: str


class DeliverablesView(BaseModel):
    run: RunDetail
    purpose: str
    available: bool  # a prospect review with a confirmed triage
    reason: str
    built_at: datetime | None
    built_by: str | None
    agent_name: str
    copy_: Copy | None = Field(alias="copy", serialization_alias="copy")
    budgets: dict[str, int]
    problems: list[str]  # copy over budget, "you" in the executive headline
    prospect: ProspectOut
    checklist: list[CheckItem]
    heights: dict[str, int]
    counts: dict[str, int]
    examples: list[str]  # codes of the one-sheet examples, in order
    internal_note: str
    report_ready: bool  # content integrity has run, so the full report can be built
    status: Literal["idle", "building", "failed"]  # the latest build (it runs in the background)
    started_at: datetime | None
    error: str | None
    log: list[BuildLogEntry]

    model_config = {"populate_by_name": True}


class ProspectIn(BaseModel):
    company: str | None = Field(None, max_length=200)
    sender_name: str | None = Field(None, max_length=200)
    sender_title: str | None = Field(None, max_length=200)
    sender_email: str | None = Field(None, max_length=320)


class DeliverablesUpdate(BaseModel):
    copy_: Copy | None = Field(None, alias="copy")
    prospect: ProspectIn | None = None
    spot_checked: bool | None = None
    marketing_ok: bool | None = None
    heights: dict[Literal["lead", "exec"], int] | None = None


LOGO_TYPES = ("image/png", "image/jpeg", "image/svg+xml")
MAX_LOGO = 512 * 1024  # bytes, decoded


class LogoIn(BaseModel):
    data_uri: str = Field(max_length=MAX_LOGO * 4 // 3 + 100)

    @field_validator("data_uri")
    @classmethod
    def _image(cls, v: str) -> str:
        head, _, body = v.partition(",")
        if not any(head == f"data:{t};base64" for t in LOGO_TYPES) or not body:
            raise ValueError("a PNG, JPEG or SVG image is needed")
        return v
