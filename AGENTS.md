# HOP Audit: agent notes

Built on [hop-core](https://github.com/Heretto/hop-core), pinned at **v0.1.18**
(`backend/requirements.txt` and the `@heretto/hop-ui` tarball in
`frontend/package.json`). Product spec and build order: `CLAUDE.md` and
`design/HANDOFF.md`; progress: `TODO.md`.

## Before changing anything

Run `./dev.sh check`. It runs lint, type checks, both test suites, the
production build and `hop-doctor --strict`, which is the definition of done.

## hop-core references: a different repository, not loaded here

- Integration rules, failure modes, upgrade steps: hop-core `AGENTS.md`
- Design system, components, tokens, app skeleton: hop-core `DESIGN-SYSTEM.md`

Read those instead of inferring from this project's code. Do not copy them here.

## What is specific to this project

- **Layout**: `backend/` (FastAPI on `create_hop_app`, run from that
  directory: modules import as `models`, `routes`, `settings`) and
  `frontend/` (Angular 22, zoneless, Vitest via `ng test`).
- **Settings**: one `.env` at the repo root for local runs and compose.
  `./dev.sh setup` creates it from `.env.example` with generated secrets and
  never overwrites it. `ENCRYPTION_KEY` cannot be rotated.
- **Start**: `./dev.sh` (free ports, generated proxy config, backend with
  `--reload`). `docker compose up --build` serves on :8080.
- **Schema**: new NOT NULL columns need a `server_default` so existing
  databases upgrade. Alembic in `backend/migrations`, run in-process at startup
  *before* hop-core's `create_all` (`backend/migrate.py`), so our tables are
  always versioned. Add a model to `backend/models/` and import it in
  `models/__init__.py`, then
  `./dev.sh alembic revision --autogenerate -m "..."` (with a scratch
  `DATABASE_URL` that is already at head). `tests/test_app.py` fails if models and
  migrations disagree.
- **Routes**: our routers live in `backend/routes/` and are mounted under
  `/api/v1`. Collections have no trailing slash, matching hop-core's own
  routes (`/api/v1/agents`); `/api/health` is public and outside the prefix.
- **Agents**: the six analysis agents are ordinary hop-core agents, seeded
  once per organization by `POST /api/v1/setup` (the shell calls it on load;
  `org_setup` records it so deleted agents stay deleted). Their context files
  are `backend/agent_context/<slug>/*.md`, mostly from the audit-asset-maker
  skill in `_reference/`. Model keys are hop-core credentials (Claude, OpenAI,
  Gemini, registered in `backend/main.py`).
- **Discovery** (`backend/discovery.py`): sitemap, sections and hreflang for
  a start URL, reused by the crawler. It sends an honest user agent and
  reports 401/403/429 and robots.txt refusals as `blocked`; never add retries
  with another agent. In this sandbox every outbound site returns 403 from the
  egress proxy, so live detection reads as blocked here.
- **Runs** (`backend/runner.py`): each audit is an asyncio task in this
  process with a pause/resume/cancel `Control`; active runs left by a
  restart are marked failed at startup. `crawler.plan()` reads sitemaps per
  host and checks each help center's root; `Crawler` fetches, reuses
  unchanged pages from the last completed run (sitemap `lastmod`, then
  content hash) and follows links within help centers. Paths, sections and
  include/exclude globs are relative to each help center's root
  (`backend/scope.py`), so `/de/authoring/x` is in section `/authoring`.
  Pages keep the extraction (`backend/extract.py`), not raw HTML.
- **Analyses** (`backend/analysis.py`): readability (`readability.py`, a
  Flesch formula per language, none for ja/zh/ko…), SEO (`seo.py`) and links
  (`links.py`, external results cached a week per organization) run on the
  stored pages, so `POST /runs/{id}/analyze` can redo them without a crawl.
  Scores and run metrics are in `scoring.py`; the dashboard footnote states
  the same scoring rules, so change both together.
- **Checksum** (`extract.checksum`, stored as `Page.content_hash`): SHA-256
  of every extraction field the analyses read. A page whose checksum matches
  the last completed audit's (`Page.reused_from_id` set) keeps that audit's
  readability metrics, SEO checks and Readability Reviewer / SEO Analyst
  findings: nothing is recomputed and no tokens are spent. Only
  `run.force_reevaluate` (the Run audit toggle "Re-evaluate unchanged
  pages") evaluates them again. Links always run; content integrity reuses
  by its own rules (below).
  Add a field to `CHECKSUM_FIELDS` when an analysis starts reading it.
- **Agent review** (`backend/review.py`): the Readability Reviewer and SEO
  Analyst review one page per request, `AGENT_CONCURRENCY` at a time, with
  the site's and the run's focus. Each agent is built from its hop-core row
  and AI configuration the way hop-core's chat route does. Replies must be a
  JSON array (asked again once); a reply that runs out of `max_tokens`
  (reasoning models think inside it) is asked again with double the budget
  up to 65,536 (`REPLY_BUDGET`); quotes not found on the page are removed;
  429/5xx are retried; three failed requests in a row stop the agent and
  fail its stage. With no usable agent the stage keeps HOP Audit's metrics
  and says why. Dismissing a finding appends to the agent's feedback memory
  in hop-core's `### heading` format. Tests register a fake provider in
  `AiProviderRegistry` (see `tests/test_review.py`).
- **Links have no agent.** `links.py` checks every target (HTTP, redirects,
  fragment ids) and `propose_fix` writes the fix (relink, anchor, restore,
  remove) from the crawl. Organizations seeded before this keep a Link
  Validator agent that nothing uses; it can be deleted.
- **Content integrity** (`backend/integrity.py`) runs three passes, one
  request each, 4 at a time: (1) each article for issues inside it plus its
  checkable claims (`Page.integrity`; claims not on the page are dropped);
  (2) each (original, translation) pair (`Page.integrity_pair`, kept while
  both checksums match); (3) claims grouped by subject within a help center
  (`claims.py`), only groups whose statements differ, verdicts cached per
  site in `ClaimGroupReview` by group key. Grouping uses embeddings
  (`embeddings.py`, calling OpenAI `text-embedding-3-small` or Gemini
  `gemini-embedding-001` directly with the org's API key; hop-core has no
  embeddings) or keywords; `Site.claim_matching` is auto | keywords | a
  credential id, and keywords is also the fallback when embedding fails.
  A run may choose its own categories (`AuditRun.integrity_categories`; null
  means the site's). Unchanged articles, pairs and groups are reused unless
  forced, and only when their stored `categories` cover this run's (answers
  stored without them count as asked for the site's categories). Duplicate
  titles, links into another language's help center, broken links and
  missing translations are found in code. Quotes must be on their page or
  the finding goes to review. Codes are stable per site: a candidate
  sharing a category and a quote with the previous run's finding keeps its
  code and, if that triage was confirmed, its tier. Integrity counts show
  anywhere only once `run.triage.status == "confirmed"`; any change reopens
  it. Re-analysis never re-runs the integrity review over an existing
  triage.
- **Report and PDFs** (`report.py`, `report_export.py`, `pdf.py`): the
  full findings report is built from the tiers as they stand, confirmed or
  not (firm counted, review listed, drop left out; the page notes an
  unconfirmed triage, the exported document doesn't), in the skill's
  section order, as one table model (columns, rows of cells, each
  cell a list of runs: text, quote, slug, note, sev, code, br) that the
  page, the Jinja print template (`templates/report.html`) and the Word
  export all render. Letter PDFs come from Chromium through Playwright, as
  the skill renders them; the browser is installed apart from the package
  (`./dev.sh` tries `playwright install chromium`; the Dockerfile does it)
  and a missing browser answers 503 with how to install it. Brand assets
  (`assets/`) are embedded as data URIs by `rendering.asset`.
- **Deliverables** (`deliverables.py`, `routes/deliverables.py`): prospect
  reviews where content integrity has run; the triage needn't be confirmed
  (the checklist flags it until it is). A one-sheet's numbers (stats,
  categories, severity, issue mix, the triage's three example picks,
  eyebrow, review sentences, footnote) are computed from the triage each
  time it's rendered; only the copy (headlines, subhead opening, executive
  lead sentence, why-it-matters lines, impact cards) comes from the
  Collateral Writer and is edited by people. One `Deliverables` row per run
  keeps the copy, the counts it was written against (a mismatch shows on
  the checklist), the heights the page measured, and the two hand-off
  ticks. The templates are the skill's, unchanged (`templates/onesheet_*`);
  their hex colors are the approved print design. The page shows each
  sheet in a sandboxed `srcdoc` frame (`SheetFrame`) and measures its
  natural height the skill's way; the PDF route measures again in Chromium
  and refuses an overflow (409).
  A build runs in the background (`deliverables.start_build`, `spawn`):
  the row carries its status (idle | building | failed), error and a step
  log that also goes to the server log; the page polls every 2 s while it
  runs. Startup marks interrupted builds failed, and one stuck over 15
  minutes reads as failed. Tests replace `deliverables.spawn` to await
  the job.
- **Routes in the UI**: `/audits/:runId` is the dashboard (active runs
  redirect to `/audits/:runId/progress`), pages are
  `/audits/:runId/pages/:pageId`, triage is `/audits/:runId/findings`, the claims the integrity reviewer took
  from articles (and how pass 3 grouped them, `AuditRun.claim_groups`) are
  `/audits/:runId/claims`,
  `/sites/:id` opens the latest dashboard.
- **Timestamps**: use `models.types.UTCDateTime`, not `DateTime`. SQLite
  drops offsets, and naive values compare and serialize as local time.
- **Frontend tests** run Vitest in worker threads (`frontend/vitest.config.mts`,
  wired via `runnerConfig`). If `ng test` ends with "Worker exited
  unexpectedly … during stopping state" and no summary, a test probably
  failed and its report was lost: run again and read the full output.
- **Platform-specific installs**: the checkout may be shared between a Mac
  and a Linux container. Each platform has its own venv
  (`backend/.venv-<os>-<cpu>`); `frontend/node_modules` swaps its native
  packages (`npm install --no-save --os --cpu`, under a second) when the
  platform changes, falling back to a clean install. On the shared folder a
  stale entry can leave `node_modules` undeletable from the sandbox; dev.sh
  then moves it to `frontend/.node_modules-stale-*`, which the Mac side can
  delete. Both reinstall when their requirements or lockfile change.
- **UI**: hop-ui components and tokens only. Shared page patterns from the
  mockups (header, subtitle, empty state) are in
  `frontend/src/app/shared/_page.scss`. The top-bar mark
  (`frontend/public/hop-audit-mark.svg`) is the mockup's navy tile with the
  Material Symbols `fact_check` glyph.
- **Single replica**: the scheduler (milestone 9) will run in-process.

## Upgrading hop-core

Resolve the current release (hop-core `AGENTS.md`, Step 0), bump the Python
requirement and the `@heretto/hop-ui` asset URL **together**, regenerate the
npm lock, rebuild, then re-run `./dev.sh check`.
