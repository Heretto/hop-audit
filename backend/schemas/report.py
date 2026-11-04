from datetime import datetime

from pydantic import BaseModel

from schemas.run import RunDetail


class RunPart(BaseModel):
    """A piece of a table cell: text, quote, slug, note, sev, code or br (report.Run)."""

    kind: str
    text: str = ""


class ReportColumn(BaseModel):
    label: str
    num: bool = False


class ReportTable(BaseModel):
    columns: list[ReportColumn]
    rows: list[list[list[RunPart]]]
    heading: str = ""
    total: list[list[RunPart]] | None = None
    more: str = ""


class ReportSection(BaseModel):
    id: str
    title: str
    lead: str
    tables: list[ReportTable]
    after: str = ""


class ReportMetric(BaseModel):
    label: str
    value: str
    detail: str


class ReportView(BaseModel):
    run: RunDetail
    purpose: str
    ready: bool  # False until triage is confirmed; ``reason`` says why
    reason: str
    title: str
    subject: str
    as_of: datetime | None
    author: str
    sections: list[ReportSection]
    appendix: list[ReportMetric]
    counts: dict[str, int]
