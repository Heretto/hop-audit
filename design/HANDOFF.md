# HOP Audit: design handoff

Approved mockups live in `project/` (one `.dc.html` per screen; `canvas.json`
indexes them). Each file is plain HTML with inline styles, hop-core tokens as
CSS variables, Material Symbols icons by ligature name, and a small JS class at
the bottom that holds the sample data and any interactive state. Open them in a
browser to see the screen; read the JS block for the data shapes.

The sidebar (`Nav.dc.html`) is `hop-main-layout` with nav items Sites, Audits,
Agents, Credentials; hop-core appends Account and Administration itself.

## Screens → routes

| Mockup | Route | What it is | Build from |
| --- | --- | --- | --- |
| `Main.dc.html` | `/sites` | Site list: pages, last audit, score, integrity issues (· High), broken links, status, row actions | `hop-data-table` in a `mat-card`, `.hop-status-chip`, `.hop-stat-card`. Pattern: analytics `pages/sites` |
| `SiteSettings.dc.html` | `/sites/new`, `/sites/:id/edit` | Site, help centers and languages (primary + others, hreflang detection), discovery and crawl rules, analyses + 10 content-integrity categories + standing focus text, agent per analysis, purpose (own docs / prospect review), schedule | Pattern: analytics `pages/analysis-edit` (card sections, sticky header with Cancel / Save and run / Save) |
| `RunAudit.dc.html` | `/sites/:id/run` | Scope (whole site / sections / changed since last / listed pages), analyses to run, help centers to review, reuse-crawl toggles, run-only focus; live page count and estimate; Start | Interactive in mockup: section picks drive the estimate |
| `AuditRunning.dc.html` | `/audits/:runId` (while running) | Progress %, stages (discover, crawl, readability, links, SEO, content integrity per help center, summary), agent cards with tokens, run log | `.hop-shimmer` on the progress card; run log = analytics `shared/run-log` |
| `Dashboard.dc.html` | `/sites/:id` (or `/audits/:runId`) | KPIs (score, pages, Flesch, broken links, SEO issues, confirmed integrity issues), content-integrity summary card, expandable section → page tree with per-row metrics | Tree expand/collapse is interactive in the mockup |
| `PageDetail.dc.html` | `/sites/:id/pages?path=` | Readability (Flesch, grade, sentence length, passive), links table (internal/external/broken/redirect/anchor), SEO checks, integrity findings involving this page, agent findings tabs | |
| `Findings.dc.html` | `/sites/:id/findings` | Content-integrity candidates: ID, severity, locale, title, exact quotes + slugs, why; per-row tier (Firm / For review / Drop) and one-sheet-example star; live recount by tier, severity, category; articles per locale; example picker (3 + backup) | The core new screen; interactive in mockup |
| `Report.dc.html` | `/audits/:runId/report` | Full findings report in the skill's structure (summary table, by-category table, contradictions, translation mismatches, instructions, remaining categories, items for review) + site-health appendix; export PDF / Doc / docx / CSV / JSON | Heretto wordmark at top (`_reference` skill assets) |
| `History.dc.html` | `/audits` | All runs for a site (scope, trigger, pages, duration, score, status), score-over-time, compare two runs (metric deltas incl. integrity issues, High, items for review; most-changed pages) | Pattern: analytics `pages/analysis-detail` runs table |
| `Deliverables.dc.html` | `/sites/:id/deliverables` | Assess → Triage → Build → Hand off; four deliverable cards (lead one-sheet, executive brief, full report, internal summary); editable headlines and "why it matters" lines with length budgets and imperative tags; prepared-for and sender; pre-send checklist (placeholders, spot-check quotes, marketing sign-off, no overflow, counts match) | Prospect-review sites only |
| `OneSheetLead.dc.html` | PDF output (Letter) | Content Integrity Snapshot for the documentation lead | Port of the skill's `assets/onesheet_template.html` |
| `ExecBrief.dc.html` | PDF output (Letter) | Executive brief for a CIO | Port of the skill's `assets/exec_template.html` |
| `Agents.dc.html` | `/agents` | hop-core `HOP_AGENT_ROUTES`, unchanged. Seed six agents (see below) | |
| `Credentials.dc.html` | `/credentials` | hop-core `hop-credentials`; AI configurations tab (Claude, OpenAI, Gemini); Add opens `hop-credential-editor-dialog` | |
| `Admin.dc.html` | `/admin` | hop-core `hop-admin`, unchanged | |

## Data model (sketch)

- **Site**: name, start URL, description, purpose (`own` | `prospect`),
  crawl rules (sitemap URL, section grouping, include/exclude globs, max pages,
  depth, delay, concurrency, robots, follow links, render JS), analyses
  enabled, integrity categories enabled, standing focus text, agent
  assignments (analysis → agent id), schedule, prospect/sender details.
- **HelpCenter** (per site): name, URL, language, `is_primary`. Non-primary
  centers are compared against the primary; two versions of one language are
  compared with each other.
- **AuditRun**: site, number, scope (`site` | `sections[]` | `changed` |
  `pages[]`), help centers, analyses, trigger, started/finished, status,
  duration, tokens by agent, stage progress, run log events (no keys, prompts
  or page text), reuse-crawl flags, run-only focus.
- **Page** (per run, per help center): URL, path, section, title, HTTP
  status, content hash, lastmod, word count, Flesch Reading Ease, FK grade,
  words/sentence, passive %, links (target, kind, status), SEO checks (title
  length, description, canonical, H1 count, heading order, images without
  alt, OG, indexable), score.
- **Finding** (content integrity): ID with category prefix
  (`C` contradictions, `U` instructions, `T` translation, `TM` terminology,
  `D` disclosure, `L` retired products, `S` scope, `O` outdated, `N` links and
  duplicates, `X` structure/publishing), severity High/Medium/Low, locale(s),
  title, quotes `[{label, text, slug, note}]`, why, tier
  (`firm` | `review` | `drop`), triage note, `is_example`, first-seen run,
  resolved run. IDs are stable across runs so fixed issues show as resolved.
- **AgentFinding** (readability/SEO/focus): page, agent, severity, title, body,
  quote, `on_focus`.
- **Deliverable**: run, kind (`lead` | `exec` | `report` | `internal`), data
  JSON (the skill's `example_affirm*.json` shapes), rendered file, overflow
  check result, placeholders remaining.

Counts shown anywhere use triaged numbers: confirmed = firm only; items for
review listed separately; firm + review + dropped = candidates.

## Agents (hop-core Agents, seeded)

| Agent | Analysis | Context files from the skill |
| --- | --- | --- |
| Readability Reviewer | readability | style guide, plain-language checklist |
| Link Validator | links | URL conventions |
| SEO Analyst | SEO and metadata | SEO checklist |
| Content Integrity Reviewer | content integrity | `audit-prompt.md` (categories, output format), counting rule + severity, triage tiers |
| Summary Writer | summary report | report template |
| Collateral Writer | prospect deliverables | `onesheet-data.md` (headline rules, budgets), `business-imperatives.md`, `value-prop-library.md`, `brand.md` |

Each agent's feedback memory grows from the user's triage calls and rejected
headlines. Pages go to agents in batches; the site's standing focus and the
run's focus are attached to every batch.

## Workflow rules carried over from the skill

1. Assess: read every article in every help center; expand collapsed
   sections; count articles per locale; exclude differences where both
   versions are accurate; record ID, locale, severity, exact quotes trimmed to
   the clause that matters, slug per quote, one sentence on why.
2. Triage: firm (counted), for review (listed, not counted; depends on policy
   you can't see), drop (petty or not an error). Recount after triage; the
   one-sheets and report use triaged numbers only. Pick three one-sheet
   examples plus a backup: a customer-impact reversal, something concrete and
   checkable, something a documentation head will feel; nothing from the
   review tier. The user's judgment wins.
3. Report: the section order and table columns in `report-structure.md`;
   exact quotes, slugs, no product mention, no internal notes.
4. One-sheets: headline rules (not critical of the prospect; never implies
   Heretto audits content; exec headline has no "you"); field length budgets;
   one-page overflow check (fail the build on overflow); Poppins; labelled
   logo placeholder unless a file is supplied.
5. Hand off: list remaining placeholders; require a live-browser spot-check of
   every one-sheet quote when the site blocked fetching; remind about
   marketing approval for the prospect's logo.

## Suggested build order

1. Scaffold on hop-core (routes, shell, auth, Agents/Credentials/Admin
   mounted), `dev.sh`, tests, `hop-doctor` green. Commit.
2. Sites + help centers CRUD and settings screen. Commit.
3. Crawler: sitemap discovery, include/exclude, depth, robots, content hash,
   reuse unchanged pages; run model with stages and run log. Commit.
4. Mechanical analyses: readability, links, SEO; dashboard tree, page detail,
   history and compare. Commit.
5. Agent batching + Readability/SEO/Link agents; agent findings on pages.
   Commit.
6. Content integrity: reviewer agent, findings model, Findings and triage
   screen with live recount. Commit.
7. Full findings report + exports. Commit.
8. Deliverables: Collateral Writer, one-sheet data JSON, Letter PDF render with
   overflow check, hand-off checklist. Commit.
9. Scheduling, rerun subsets (changed-since-last), polish. Commit.

## Decisions already made in the design

- Prospect-review sites get the Deliverables flow; own-docs sites don't.
- The report has a site-health appendix after the content-integrity sections.
- The sample prospect in the mockups is fictional ("Lumen Financial"); the
  skill's Affirm example data is the model for the one-sheet JSON shapes.
- Where the skill required Claude in Chrome to read pages, HOP Audit's own
  crawler reads them and reports a blocked help center instead.
