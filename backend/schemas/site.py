"""Site settings as the API reads and writes them.

``SiteIn`` is what the settings screen saves; the JSON columns on ``Site``
store its nested models with ``model_dump()``.
"""

import re
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from catalog import ANALYSIS_KEYS, CATEGORY_CODES

# Analyses a site can switch on; prospect deliverables follow from the purpose.
SITE_ANALYSES = tuple(k for k in ANALYSIS_KEYS if k != "deliverables")
LANGUAGE_TAG = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$")
TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def http_url(value: str) -> str:
    value = value.strip()
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError("must be an http(s) URL")
    return value


def _patterns(lines: list[str]) -> list[str]:
    return [p for p in (line.strip() for line in lines) if p]


class CrawlRules(BaseModel):
    sitemap_url: str = ""  # blank = auto-detect
    section_grouping: Literal["path", "sitemap", "breadcrumb"] = "path"
    include: list[str] = []
    exclude: list[str] = []
    max_pages: int = Field(2000, ge=1, le=100_000)
    max_depth: int = Field(8, ge=0, le=50)
    delay_ms: int = Field(250, ge=0, le=60_000)
    concurrency: int = Field(4, ge=1, le=16)
    respect_robots: bool = True
    follow_links: bool = True
    render_js: bool = False

    _clean_patterns = field_validator("include", "exclude")(_patterns)

    @field_validator("sitemap_url")
    @classmethod
    def _sitemap(cls, v: str) -> str:
        return http_url(v) if v.strip() else ""


class Schedule(BaseModel):
    frequency: Literal["manual", "weekly", "monthly"] = "manual"
    day: int = Field(1, ge=0, le=28)  # weekly: 0 = Monday … 6 = Sunday; monthly: 1–28
    time: str = "07:00"
    timezone: str = "UTC"

    @field_validator("time")
    @classmethod
    def _time(cls, v: str) -> str:
        if not TIME.match(v):
            raise ValueError("must be HH:MM, 24-hour")
        return v

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        if v not in available_timezones():
            raise ValueError("unknown time zone")
        return v

    @model_validator(mode="after")
    def _day(self):
        if self.frequency == "weekly" and self.day > 6:
            raise ValueError("weekly schedules take a day from 0 (Monday) to 6 (Sunday)")
        if self.frequency == "monthly" and self.day < 1:
            raise ValueError("monthly schedules take a day of the month from 1 to 28")
        return self


class Prospect(BaseModel):
    """Prepared-for and sender details for prospect deliverables."""

    company: str = ""
    prepared_for: str = ""
    sender_name: str = ""
    sender_title: str = ""
    sender_email: str = ""


class HelpCenterIn(BaseModel):
    id: UUID | None = None  # kept on update, so runs stay linked to it
    name: str = Field(min_length=1, max_length=255)
    url: str
    language: str
    is_primary: bool = False

    _url = field_validator("url")(lambda v: http_url(v))

    @field_validator("language")
    @classmethod
    def _language(cls, v: str) -> str:
        v = v.strip().replace("_", "-")
        if not LANGUAGE_TAG.match(v):
            raise ValueError("must be a language tag such as en, de or fr-CA")
        return v


class HelpCenterOut(HelpCenterIn):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


class SiteIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    start_url: str
    description: str = ""
    purpose: Literal["own", "prospect"] = "own"
    help_centers: list[HelpCenterIn] = Field(min_length=1)
    crawl: CrawlRules = CrawlRules()
    analyses: list[str] = list(SITE_ANALYSES)
    integrity_categories: list[str] = list(CATEGORY_CODES)
    focus: str = ""
    agent_assignments: dict[str, UUID | None] = {}
    schedule: Schedule = Schedule()
    prospect: Prospect = Prospect()

    _start_url = field_validator("start_url")(lambda v: http_url(v))

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("is required")
        return v.strip()

    @field_validator("analyses")
    @classmethod
    def _analyses(cls, v: list[str]) -> list[str]:
        unknown = set(v) - set(SITE_ANALYSES)
        if unknown:
            raise ValueError(f"unknown analyses: {', '.join(sorted(unknown))}")
        return [k for k in SITE_ANALYSES if k in v]

    @field_validator("integrity_categories")
    @classmethod
    def _categories(cls, v: list[str]) -> list[str]:
        unknown = set(v) - set(CATEGORY_CODES)
        if unknown:
            raise ValueError(f"unknown categories: {', '.join(sorted(unknown))}")
        return [c for c in CATEGORY_CODES if c in v]

    @field_validator("agent_assignments")
    @classmethod
    def _assignments(cls, v: dict[str, UUID | None]) -> dict[str, UUID | None]:
        unknown = set(v) - set(ANALYSIS_KEYS)
        if unknown:
            raise ValueError(f"unknown analyses: {', '.join(sorted(unknown))}")
        return v

    @model_validator(mode="after")
    def _consistent(self):
        if sum(hc.is_primary for hc in self.help_centers) != 1:
            raise ValueError("exactly one help center must be primary")
        urls = [hc.url.rstrip("/") for hc in self.help_centers]
        if len(set(urls)) != len(urls):
            raise ValueError("each help center needs its own URL")
        if "content_integrity" in self.analyses and not self.integrity_categories:
            raise ValueError("content integrity needs at least one category")
        return self


class SiteOut(SiteIn):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    help_centers: list[HelpCenterOut]
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SiteSummary(BaseModel):
    """A row on the Sites list. Audit columns arrive with audit runs."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    start_url: str
    purpose: str
    help_centers: list[HelpCenterOut]
    crawl: CrawlRules


class DetectRequest(BaseModel):
    start_url: str
    sitemap_url: str = ""
    respect_robots: bool = True

    _start_url = field_validator("start_url")(lambda v: http_url(v))
    _sitemap = field_validator("sitemap_url")(lambda v: http_url(v) if v.strip() else "")
