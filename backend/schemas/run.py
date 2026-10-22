from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from schemas.site import SITE_ANALYSES, SiteSummary


class RunScope(BaseModel):
    mode: Literal["site", "sections", "changed", "pages"] = "site"
    sections: list[str] = []
    pages: list[str] = []

    @model_validator(mode="after")
    def _needs(self):
        self.pages = [p.strip() for p in self.pages if p.strip()]
        if self.mode == "sections" and not self.sections:
            raise ValueError("choose at least one section")
        if self.mode == "pages" and not self.pages:
            raise ValueError("list at least one page")
        return self


class RunIn(BaseModel):
    scope: RunScope = RunScope()
    analyses: list[Literal[SITE_ANALYSES]] = list(SITE_ANALYSES)  # type: ignore[valid-type]
    help_center_ids: list[UUID] = []  # reviewed for content integrity; empty = all
    reuse_crawl: bool = True
    recheck_external: bool = False
    focus: str = Field("", max_length=5000)


class Stage(BaseModel):
    key: str
    label: str
    status: Literal["pending", "running", "done", "skipped", "failed"]
    done: int = 0
    total: int = 0
    detail: str = ""


class RunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    site_id: UUID
    number: int
    status: str
    trigger: str
    scope: RunScope
    analyses: list[str]
    page_count: int
    created_by: str | None
    created_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    stages: list[Stage]

    @computed_field
    @property
    def progress(self) -> int:
        """Percent of the crawl done; analyses join the measure as they arrive."""
        crawl = next((s for s in self.stages if s.key == "crawl"), None)
        if self.status == "completed":
            return 100
        if crawl is None or not crawl.total:
            return 0
        return min(99, round(100 * crawl.done / crawl.total))


class RunListItem(RunSummary):
    site_name: str


class RunDetail(RunListItem):
    help_center_ids: list[UUID]
    reuse_crawl: bool
    recheck_external: bool
    focus: str
    tokens: dict[str, int]
    error: str | None


class LogEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    at: datetime
    stage: str
    level: str
    message: str


class PreviewSection(BaseModel):
    path: str
    count: int


class PreviewHelpCenter(BaseModel):
    id: UUID
    name: str
    language: str
    is_primary: bool
    pages: int
    blocked: str | None


class Preview(BaseModel):
    site_pages: int  # whole site, after the site's rules
    changed: int  # sitemap pages new or changed since the last completed run, by lastmod
    sections: list[PreviewSection]
    help_centers: list[PreviewHelpCenter]
    last_run_number: int | None
    last_run_at: datetime | None
    seconds_per_page: float  # from the last run, else from the crawl settings
    tokens_per_page: int  # all five analyses together
    notes: list[str]  # help centers blocked, sitemaps missing, pages left out


class SiteListItem(SiteSummary):
    """A row on the Sites list: the site and its latest run, if any."""

    last_run: RunSummary | None = None
