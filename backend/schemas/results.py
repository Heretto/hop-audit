from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from schemas.run import RunDetail, RunSummary


class SectionRow(BaseModel):
    path: str
    pages: int
    flesch: float | None
    broken: int
    seo_issues: int
    score: int | None


class Dashboard(BaseModel):
    run: RunDetail
    compared: RunSummary | None
    sections: list[SectionRow]
    analyzed: bool  # False for runs crawled before the analyses existed


class PageRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    url: str
    path: str
    title: str
    section: str
    help_center_id: UUID
    http_status: int | None
    error: str | None
    word_count: int
    flesch: float | None
    broken_links: int | None
    redirects: int | None
    anchor_issues: int | None
    seo_issues: int | None
    score: int | None


class LinkRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    url: str
    text: str
    internal: bool
    outcome: str
    status: int | None
    final_url: str | None
    note: str


class PageDetail(PageRow):
    run_id: UUID
    run_number: int
    site_id: UUID
    site_name: str
    help_center_name: str
    language: str
    lastmod: datetime | None
    fetched_at: datetime | None
    reused_from_id: UUID | None
    grade: float | None
    words_per_sentence: float | None
    passive_pct: float | None
    sentences: int | None
    seo: list[dict] | None
    links_internal: int | None
    links_external: int | None
    content: dict
    links: list[LinkRow]
    section_flesch: float | None
    previous_score: int | None
    previous_run_number: int | None


class CompareRow(BaseModel):
    key: str
    label: str
    a: float | None
    b: float | None
    delta: float | None
    better: str  # up | down | flat: which direction is good for this metric


class ChangedPage(BaseModel):
    url: str
    path: str
    page_id: UUID
    a: int
    b: int
    delta: int


class Comparison(BaseModel):
    a: RunSummary
    b: RunSummary
    rows: list[CompareRow]
    changed_pages: list[ChangedPage]
