from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from catalog import CATEGORY_CODES
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
    force_reevaluate: bool = False  # readability and SEO for unchanged pages too
    focus: str = Field("", max_length=5000)
    integrity_categories: list[str] | None = None  # this run's content-integrity checks; None = the site's

    @model_validator(mode="after")
    def _categories(self):
        if self.integrity_categories is None:
            return self
        if unknown := set(self.integrity_categories) - set(CATEGORY_CODES):
            raise ValueError(f"unknown categories: {', '.join(sorted(unknown))}")
        if "content_integrity" in self.analyses and not self.integrity_categories:
            raise ValueError("content integrity needs at least one category")
        self.integrity_categories = [c for c in CATEGORY_CODES if c in self.integrity_categories]
        return self


class AnalyzeIn(BaseModel):
    force: bool = False  # re-evaluate pages whose checksum hasn't changed


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
    metrics: dict = {}

    @computed_field
    @property
    def progress(self) -> int:
        """Percent of the work done, each stage that runs counting equally."""
        if self.status == "completed":
            return 100
        active = [s for s in self.stages if s.status != "skipped"]
        if not active:
            return 0

        def share(s: Stage) -> float:
            if s.status in ("done", "failed"):
                return 1.0
            return s.done / s.total if s.status == "running" and s.total else 0.0

        return min(99, round(100 * sum(share(s) for s in active) / len(active)))


class RunListItem(RunSummary):
    site_name: str


class RunDetail(RunListItem):
    help_center_ids: list[UUID]
    reuse_crawl: bool
    recheck_external: bool
    force_reevaluate: bool
    focus: str
    integrity_categories: list[str] | None = None  # None: the site's
    tokens: dict[str, int]
    agent_stats: dict[str, dict]  # agent id -> name, model, provider, tokens, findings, errors, retries, status
    error: str | None


class LogEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
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
    last_completed: RunSummary | None = None  # its metrics fill the score and broken-link columns
