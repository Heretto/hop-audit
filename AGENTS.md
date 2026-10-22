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
- **Schema**: Alembic in `backend/migrations`, run in-process at startup
  *before* hop-core's `create_all` (`backend/migrate.py`), so our tables are
  always versioned. Add a model to `backend/models/` and import it in
  `models/__init__.py`, then
  `cd backend && .venv/bin/alembic revision --autogenerate -m "..."` (with a
  scratch `DATABASE_URL`). `tests/test_app.py` fails if models and
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
- **Platform-specific installs**: `backend/.venv` and `frontend/node_modules`
  carry a `.platform` stamp; `./dev.sh` reinstalls when the checkout moves
  between macOS and a Linux container.
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
