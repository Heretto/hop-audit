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

- [x] Models: `Site` (all fields from the data-model sketch, JSON columns
      for crawl rules / analyses / categories / agent assignments /
      schedule / prospect), `HelpCenter` (name, URL, language, `is_primary`,
      position). Migration.
- [x] Schemas with validation: URL fields http(s), exactly one primary help
      center, unique help-center URLs, known analyses and category codes,
      agent ids belong to the org, max pages / depth / delay / concurrency
      bounds, schedule shape
- [x] Routes: `GET/POST /sites/`, `GET/PUT/DELETE /sites/{id}`, org-scoped;
      list includes help-center summary and (until M3) empty last-audit stats
- [x] Discovery helpers: `POST /sites/detect` → sitemap auto-detect
      (robots.txt `Sitemap:` then `/sitemap.xml`), URL count, sections by
      first path segment, last modified; hreflang languages from the start
      URL. Blocked/unreachable reported, never worked around. HTTP mocked in
      tests.
- [x] Backend tests: CRUD normal path, validation errors, org isolation,
      delete cascade, detection parsing (sitemap, sitemap index, hreflang,
      blocked)
- [x] Frontend: `SitesService`, Sites list page (`/sites`) per `Main.dc.html`:
      `hop-data-table` in `mat-card`, filter, count, row actions (run,
      results, history, edit, delete with confirm), stat cards, empty state
- [x] Frontend: Site settings page (`/sites/new`, `/sites/:id/edit`) per
      `SiteSettings.dc.html`: sticky header with Cancel / Save and run / Save,
      Site, Help centers and languages (add/remove, primary, hreflang
      detection), Discovery and crawling (sitemap check), Analyses and
      focus (5 analyses + 10 categories + focus text), Agents (select per
      analysis from hop-core agents), Purpose, Last audit, Sections
      discovered, Schedule
- [x] Frontend tests: service, list page rendering/delete, settings form
      validation and payload mapping
- [x] Checks green (tests, lint, build, hop-doctor); commit with decisions

## Milestone 3: crawler, runs, stages and run log

- [x] Models + migration: `AuditRun` (number per site, scope, help centers,
      analyses, trigger, status, timings, stages, tokens by agent, reuse /
      re-check flags, run focus, error), `RunLogEntry` (time, stage, level,
      message: no keys, prompts or page text), `Page` (per run and help
      center: URL, path, section, title, status, content hash, lastmod,
      word count, extracted text and structure, links, reused-from)
- [x] Extraction (`extract.py`): main content text, title, description,
      canonical, robots, Open Graph, headings, images and alt, links with
      text, breadcrumb, `lang`; hash of the normalized text
- [x] Discovery per help center: sitemaps per host, each URL assigned to the
      help center with the longest matching prefix, sections relative to
      the help center root (path, sitemap file, or breadcrumb grouping)
- [x] Scope rules: include/exclude globs, max pages, depth, robots,
      sections / changed since last / listed pages, run-only focus
- [x] Crawler (`crawler.py`): concurrency + delay, retries on 5xx and
      timeouts (logged), follow links within help centers, reuse unchanged
      pages from the last completed run (lastmod, then content hash),
      blocked help centers reported and skipped, never worked around;
      pages that look like an empty JavaScript shell flagged
- [x] Runner (`runner.py`): in-process background task per run, stage
      progress, pause / resume / cancel, analyses not built yet marked
      skipped, runs interrupted by a restart marked failed at startup,
      one active run per site
- [x] Routes: preview (page counts, sections, changed count, help-center
      article counts, estimates), start, list per site and org, detail,
      log, pause, resume, cancel; Sites list carries the last run
- [x] Backend tests: extraction, globs and scope, discovery assignment,
      crawler against a mocked site (reuse, retries, blocked, robots,
      depth, max pages, follow links), runner stages and controls, routes
- [x] Frontend: Run audit page (`/sites/:id/run`) per `RunAudit.dc.html`
      with live page count and estimate; "Save and run audit" on settings
- [x] Frontend: Audit page (`/audits/:runId`) per `AuditRunning.dc.html`
      polling while active: progress, stages, agents, run log with copy,
      pause / resume / cancel
- [x] Frontend: Sites list run action, status chip, pages, last audit;
      Audits page lists runs (History and compare arrive in M4)
- [x] Frontend tests; checks green; smoke test; commit with decisions

## Milestone 4: mechanical analyses, dashboard, page detail, history

- [x] Extraction keeps element ids and named anchors (for #fragment checks)
- [x] `readability.py`: sentences, words, syllables; Flesch Reading Ease
      and Flesch–Kincaid grade, with the language's own formula where one
      exists (en, de Amstad, fr Kandel–Moles, es Fernández Huerta, it
      Flesch–Vacca, nl Douma), none for languages without one (ja, zh, ko…);
      words per sentence; passive sentences (English)
- [x] `seo.py`: title (present, 30–60, unique), description (present,
      70–160, unique), canonical, one H1, heading order, images without
      alt, Open Graph, indexable; ok / warn / error per check
- [x] `links.py`: every main-content link checked once per run: internal
      targets from the crawl, others by HEAD then GET; broken, redirect,
      anchor not found, blocked (couldn't check); external results cached
      7 days per organization unless the run asks to re-check
- [x] `scoring.py`: page score 0–100 from readability, links and SEO;
      section and site score as means; run metrics (score, pages, new,
      mean Flesch, under 50, broken, redirects, SEO issues)
- [x] Models + migration: page metrics columns, `LinkResult`, `LinkCache`,
      run `metrics`
- [x] Runner: readability, SEO and links stages do this work; overall
      progress across stages; `POST /runs/{id}/analyze` re-analyzes a
      finished run's stored pages (for runs crawled before analyses)
- [x] Routes: run dashboard (KPIs with deltas vs. the previous comparable
      run, sections), pages (light rows), pages CSV, page detail (metrics,
      checks, links, headings, text, previous score), compare two runs
      (metrics, most-changed pages); Sites list gets the last completed run
- [x] Backend tests for each module and route
- [x] Frontend: Dashboard (`/audits/:runId`) per `Dashboard.dc.html`: KPIs,
      section → page tree with filter, issue filter, sort, expand/collapse,
      CSV export; active runs go to the progress view
      (`/audits/:runId/progress`); "Analyze now" for unanalyzed runs
- [x] Frontend: Page detail (`/audits/:runId/pages/:pageId`) per
      `PageDetail.dc.html`: readability, links, SEO cards, headings
      outline, crawled text, raw metrics tabs
- [x] Frontend: Audits page becomes History per `History.dc.html`: site
      picker, score over time (whole-site runs), runs table with select-two
      compare, metric deltas, most-changed pages, CSV export
- [x] Frontend: Sites list score and broken links; `/sites/:id` opens the
      latest dashboard
- [x] Frontend tests; checks green; smoke test against a local site; commit

## Milestone 5: agent review (readability, SEO, links)

- [x] Model + migration: `AgentFinding` (run, page or pages, agent, model,
      analysis, severity, title, body, quote, suggestion, on_focus,
      review key, dismissed + reason); run `agent_stats` (tokens, errors,
      retries, findings per agent)
- [x] `review.py`: build the agent from its hop-core row and AI
      configuration (as hop-core's chat route does), batches (readability
      12 pages, SEO 20, link targets 25), the site's and the run's focus on
      every batch, JSON output parsed and validated, quotes checked against
      the page (unmatched quotes removed), retries on rate limits and
      server errors, an agent stopped after 3 failed batches, tokens counted
- [x] Reuse: a page unchanged since the last audit, reviewed by the same
      agent with the same focus, copies its findings instead of asking again
- [x] No agent assigned or no AI configuration: metrics only, said plainly
      in the stage and log; the run still completes
- [x] Link Validator gets targets grouped across pages, with candidate
      replacement paths from the crawl for broken internal links
- [x] Dismissing a finding (with a reason) appends to the agent's feedback
      memory
- [x] Routes: findings for a run and a page, dismiss; run metrics gain
      agent and focus findings and tokens; compare rows for them
- [x] Backend tests with a fake provider registered in hop-core's registry
- [x] Frontend: Page detail "Agent findings" tab (severity, site focus tag,
      agent · model, body, quote, suggestion, dismiss); dashboard findings
      column and "Focus findings" filter; progress page agent cards with
      tokens, errors and findings; history compare rows
- [x] Frontend tests; checks green; smoke test with a fake model; commit

## Milestone 6: content integrity, findings and triage

- [x] Model + migration: `IntegrityFinding` (run, site, stable code, category,
      severity, help centers, locale label, title, quotes `[{label, text,
      slug, note, page_id, verified}]`, why, proposed tier + reason, tier,
      triage note, example rank, first seen run, carried from, agent);
      run `triage` (status, confirmed at / by)
- [x] `integrity.py`: batches per help center by section (character
      budget), translation pairs (non-primary vs primary by relative path;
      two versions of one language with each other), the site's enabled
      categories and both focuses, JSON parsed and validated, quotes checked
      against their pages (an unverified quote sends the finding to review
      with a note), duplicates merged, articles in only one language listed
      mechanically (for review)
- [x] Stable IDs: match a candidate to the last run's findings by category
      and a shared quote; keep the code and first-seen run; carry tier and
      note from a confirmed triage; new codes continue the site's numbering;
      unmatched earlier findings on reviewed pages are resolved
- [x] Triage routes: list (with recount and help-center article counts),
      update tier / note / example (examples only from firm; leaving firm
      clears it; any change reopens a confirmed triage), confirm (feedback
      memory gets every tier the user changed), CSV
- [x] Metrics: confirmed, High/Medium/Low, for review, dropped, candidates,
      by category, resolved; shown only once triage is confirmed (Dashboard,
      Sites list, History compare)
- [x] Backend tests (fake model): batching, pairing, verification, IDs
      across runs, carry-over, resolve, triage rules, confirm and memory
- [x] Frontend: Findings and triage page (`/audits/:runId/findings`) per
      `Findings.dc.html`: filters, tier toggle, example star, triage note,
      live recount, severity bar, by category, articles per help center,
      one-sheet examples with hints, export CSV, confirm
- [x] Frontend: Dashboard integrity KPI and card; Page detail "Content
      integrity findings involving this page"; Sites list integrity column;
      progress card candidates count
- [x] Frontend tests; checks green; smoke test with a fake model; commit

## Later milestones (from the handoff)

- [ ] 7 Full findings report + exports
- [ ] 8 Deliverables (one-sheets, overflow check, hand-off)
- [ ] 9 Scheduling, rerun subsets, polish
