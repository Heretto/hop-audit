"""The report as Letter HTML (for the PDF) and as Word, plus the full audit as
JSON. All three come from `report.build`, so they say the same thing as the
page."""

from io import BytesIO

from docx import Document
from docx.enum.text import WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

import rendering
from report import Report, Run

NAVY = RGBColor(0x01, 0x16, 0x27)  # headings (report-structure.md)
MUTED = RGBColor(0x5B, 0x6B, 0x82)
HEADER_FILL = "EDF3FA"  # table header rows
FONT = "Poppins"  # falls back to the reader's sans when it isn't installed


def as_of(report: Report) -> str:
    return f"{report.as_of:%B} {report.as_of.day}, {report.as_of:%Y}" if report.as_of else ""


def html(report: Report) -> str:
    return rendering.render("report.html", report=report, as_of=as_of(report),
                            wordmark=rendering.asset("heretto-wordmark.png"))  # fmt: skip


def _runs(paragraph, runs: list[Run]) -> None:
    for r in runs:
        if r.kind == "br":
            paragraph.add_run().add_break(WD_BREAK.LINE)
        elif r.kind == "quote":
            paragraph.add_run(f"“{r.text}”").italic = True
        elif r.kind in ("slug", "code"):
            run = paragraph.add_run(f" {r.text}" if r.kind == "slug" else r.text)
            run.font.name = "Roboto Mono"
            run.font.size = Pt(7.5)
            if r.kind == "slug":
                run.font.color.rgb = MUTED
        elif r.kind == "note":
            paragraph.add_run(f" ({r.text})").font.color.rgb = MUTED
        elif r.kind == "sev":
            paragraph.add_run(r.text).bold = True
        else:
            paragraph.add_run(r.text)


def _shade(cell, fill: str) -> None:
    shading = OxmlElement("w:shd")
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:fill"), fill)
    cell._tc.get_or_add_tcPr().append(shading)


def _heading(doc, text: str, level: int) -> None:
    h = doc.add_heading(text, level=level)
    for run in h.runs:
        run.font.color.rgb = NAVY
        run.font.name = FONT


def docx(report: Report) -> bytes:
    doc = Document()
    doc.styles["Normal"].font.name = FONT
    doc.styles["Normal"].font.size = Pt(10)
    header = doc.sections[0].header.paragraphs[0]
    header.add_run().add_picture(str(rendering.ASSETS / "heretto-wordmark.png"), height=Pt(16))

    _heading(doc, report.title, 0)
    byline = doc.add_paragraph(f"As of {as_of(report)}" + (f" · {report.author}" if report.author else ""))
    byline.runs[0].font.color.rgb = MUTED
    for s in report.sections:
        _heading(doc, s.title, 1)
        doc.add_paragraph(s.lead)
        for t in s.tables:
            if t.heading:
                _heading(doc, t.heading, 2)
            rows = t.rows + ([t.total] if t.total else [])
            table = doc.add_table(rows=1 + len(rows), cols=len(t.columns))
            table.style = "Table Grid"
            for i, c in enumerate(t.columns):
                cell = table.rows[0].cells[i]
                cell.paragraphs[0].add_run(c.label).bold = True
                _shade(cell, HEADER_FILL)
            for r, row in enumerate(rows, 1):
                for i, runs in enumerate(row):
                    _runs(table.rows[r].cells[i].paragraphs[0], runs)
                    if t.total and row is t.total:
                        for run in table.rows[r].cells[i].paragraphs[0].runs:
                            run.bold = True
        if s.after:
            doc.add_paragraph(s.after).runs[0].font.color.rgb = MUTED
    if report.appendix:
        _heading(doc, "Appendix: site health", 1)
        doc.add_paragraph("Mechanical checks from the same crawl, reported separately from the "
                          "content-integrity findings above.")  # fmt: skip
        for m in report.appendix:
            p = doc.add_paragraph(style="List Bullet")
            p.add_run(f"{m.label}: ").bold = True
            p.add_run(m.value + (f" ({m.detail})" if m.detail else ""))
    out = BytesIO()
    doc.save(out)
    return out.getvalue()
