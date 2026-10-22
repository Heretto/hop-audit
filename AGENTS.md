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
- **Agent review** (`backend/review.py`): each analysis's agent is built
  from its hop-core row and AI configuration the way hop-core's chat route
  does; pages go in batches with the site's and the run's focus; replies
  must be a JSON array (asked again once), quotes not found on the page are
  removed, 429/5xx are retried, three failed batches in a row stop the
  agent. Unchanged pages reviewed with the same review key (agent, model,
  system prompt, focus) copy their findings instead of asking again. With
  no usable agent the stage keeps HOP Audit's metrics and says why.
  Dismissing a finding appends to the agent's feedback memory in hop-core's
  `### heading` format. Tests register a fake provider in
  `AiProviderRegistry` (see `tests/test_review.py`).
- **Routes in the UI**: `/audits/:runId` is the dashboard (active runs
  redirect to `/audits/:runId/progress`), pages are
  `/audits/:runId/pages/:pageId`, `/sites/:id` opens the latest dashboard.
- **Timestamps**: use `models.types.UTCDateTime`, not `DateTime`. SQLite
  drops offsets, and naive values compare and serialize as local time.
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
