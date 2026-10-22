# HOP Audit: TODO

Build order from `design/HANDOFF.md`. Mark each step `[x]` when done and
re-read this file before starting the next.

## Milestone 1: scaffold on hop-core

- [x] Resolve the current hop-core release (Step 0) and pin it in both
      `backend/requirements.txt` and `frontend/package.json`
- [x] `git init`, `.gitignore` (`.env`, `node_modules`, `data/`, `.DS_Store`, `dist`, venv)
- [x] Backend: `backend/settings.py` (`AuditSettings(HopCoreSettings)`, env file
      at repo root, Redis optional), `backend/main.py` (`create_hop_app`,
      register Claude/OpenAI/Gemini + Heretto credential types, unauthenticated
      `/api/health` outside the prefix)
- [x] Backend: Alembic in the AGENTS.md §6 shape (`OUR_TABLES` derived from
      `models`, hop-core models imported, engine init from the CLI, batch mode)
      and a first migration
- [x] Backend: `org_setup` table + idempotent `POST /api/v1/setup/` that seeds
      the six analysis agents (Readability Reviewer, Link Validator, SEO
      Analyst, Content Integrity Reviewer, Summary Writer, Collateral Writer)
      once per organization, with context files from the skill's references
      (and short written ones where the skill has none). Deleted agents are
      not re-created.
- [x] Backend tests: pytest + TestClient against a temp SQLite DB; health,
      auth-required on our routes, seeding (creates six, idempotent, does not
      resurrect deleted, org isolation), context files present
- [x] Frontend: Angular 22 app in `frontend/` consuming the pinned
      `@heretto/hop-ui` tarball; `styles.scss` = the one mixin; fonts in
      `index.html`; `inlineCritical: false` in production; zoneless
- [x] Frontend: routes (`HOP_ROUTES`-equivalent auth pages, shell with
      `/sites`, `/audits`, `/agents` → `HOP_AGENT_ROUTES`, `/credentials` →
      `hop-credentials`, `/account`, `/admin`), shell = `hop-main-layout`
      with nav Sites / Audits / Agents / Credentials (Nav mockup), seeding
      call on shell load
- [x] Frontend: placeholder Sites and Audits pages (`.hop-page`, heading and
      subtitle from the mockups) so the routes resolve
- [x] Frontend tests (Vitest via `ng test`): routes table, shell nav items,
      setup service call
- [x] `dev.sh`: create venv + install, generate `.env` if missing, run
      migrations, free ports, start uvicorn + `ng serve` with a generated
      proxy config, `./dev.sh test` runs both suites, `./dev.sh doctor`
- [x] Docker: `backend/Dockerfile`, `frontend/Dockerfile` (nginx),
      `docker-compose.yml` with secret guards, `.env.example`
- [x] `AGENTS.md` (hop-core notes per Step 4: pinned tag, hop-doctor,
      links, project specifics); pointer added to `CLAUDE.md`
- [x] Checks: backend tests, `ruff`, frontend tests, `ng build` (prod),
      `tsc` via build, `hop-doctor --strict` green; smoke test the running
      stack (`/api/health` 200, `/api/v1/sites/` 401)
- [x] Commit with decisions

## Milestone 2: sites, help centers, settings screen

- [ ] Models: `Site` (all fields from the data-model sketch, JSON columns
      for crawl rules / analyses / categories / agent assignments /
      schedule / prospect), `HelpCenter` (name, URL, language, `is_primary`,
      position). Migration.
- [ ] Schemas with validation: URL fields http(s), exactly one primary help
      center, unique help-center URLs, known analyses and category codes,
      agent ids belong to the org, max pages / depth / delay / concurrency
      bounds, schedule shape
- [ ] Routes: `GET/POST /sites/`, `GET/PUT/DELETE /sites/{id}`, org-scoped;
      list includes help-center summary and (until M3) empty last-audit stats
- [ ] Discovery helpers: `POST /sites/detect` → sitemap auto-detect
      (robots.txt `Sitemap:` then `/sitemap.xml`), URL count, sections by
      first path segment, last modified; hreflang languages from the start
      URL. Blocked/unreachable reported, never worked around. HTTP mocked in
      tests.
- [ ] Backend tests: CRUD normal path, validation errors, org isolation,
      delete cascade, detection parsing (sitemap, sitemap index, hreflang,
      blocked)
- [ ] Frontend: `SitesService`, Sites list page (`/sites`) per `Main.dc.html`:
      `hop-data-table` in `mat-card`, filter, count, row actions (run,
      results, history, edit, delete with confirm), stat cards, empty state
- [ ] Frontend: Site settings page (`/sites/new`, `/sites/:id/edit`) per
      `SiteSettings.dc.html`: sticky header with Cancel / Save and run / Save,
      Site, Help centers and languages (add/remove, primary, hreflang
      detection), Discovery and crawling (sitemap check), Analyses and
      focus (5 analyses + 10 categories + focus text), Agents (select per
      analysis from hop-core agents), Purpose, Last audit, Sections
      discovered, Schedule
- [ ] Frontend tests: service, list page rendering/delete, settings form
      validation and payload mapping
- [ ] Checks green (tests, lint, build, hop-doctor); commit with decisions

## Later milestones (from the handoff)

- [ ] 3 Crawler + run model with stages and run log
- [ ] 4 Mechanical analyses, dashboard, page detail, history and compare
- [ ] 5 Agent batching + Readability/SEO/Link agents
- [ ] 6 Content integrity reviewer, findings, triage screen
- [ ] 7 Full findings report + exports
- [ ] 8 Deliverables (one-sheets, overflow check, hand-off)
- [ ] 9 Scheduling, rerun subsets, polish
