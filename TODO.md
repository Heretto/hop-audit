# HOP Audit: TODO

## Audit dashboard v2 (user: `_reference/Audit dashboard-html-v2`; "see the button changes and confirm all the form elements are the proper size and alignment")
v2 vs the approved mockup: the header loses Export and "Summary report" is "Report"; the pages table's toolbar gains Export CSV beside Expand all / Collapse all. The toolbar's fields are 36px (8px corners, strong border, 0 10px, 14px text; the filter 280px wide with a search icon and a placeholder; Show and Sort with their name inside the field), its buttons 32px / 13px, and it has 14px 16px padding.
- [x] `design/project/Dashboard.dc.html` carries the v2 changes (content only; the reference copy keeps its viewer scripts)
- [x] Header: Export moves to the toolbar as Export CSV. "Report" links to the report page, which isn't built yet (`/audits/:runId/report`, HANDOFF): left out until it is. Run log and Re-evaluate stay (not in the mockup; functional)
- [x] Toolbar fields and buttons at the mockup's sizes through Material's tokens; filter 280px with placeholder; Show / Sort with the name inside the field
- [x] Spec: the toolbar's buttons and fields; `./dev.sh check`: all checks passed

## Dashboard: Content integrity bars in severity colours (user: "not grey")
Before triage the bars were grey (`.proposed`), and confirmed they were one accent fill. Now each category's bar is segments by severity, High (tertiary) · Medium (accent) · Low (info), the Findings mockup's severity colours, with a key dot beside each count in the severity line; proposed or confirmed alike. Audits analyzed before the split was recorded keep one accent fill.
- [x] Backend: `severity_by_category` in the run's integrity metrics; test
- [x] Frontend: `CategoryCard` with the split, segmented bar, key dots; spec
- [x] `./dev.sh check`: all checks passed

## Findings: the "Use as example" button (user: star too high, padding wrong; match the mockup)
Cause: two `.example` rules in findings-page.scss. The second, meant for the picked-examples list in the side panel (`display: flex; align-items: baseline`), also hit the button, so its star sat on the text baseline and Material's button layout was overridden.
- [x] The picked list gets its own class (`.pick`); the button keeps `.example`
- [x] The button matches the mockup's `.ex` exactly: 30px, 0 10px padding, 6px gap, 8px radius, strong border, 500 12px secondary text, 16px star; on: accent border, background and text
- [x] Spec covers the button's classes and icon; `./dev.sh check` (5f13988)

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

## Content integrity in three passes

- [x] Models + migration: `Page.integrity` (pass 1 issues and claims),
      `Page.integrity_pair` (pass 2 result with the original's URL and
      checksum), `ClaimGroupReview` (pass 3 verdict by group key, per site),
      `Site.claim_matching` (auto | keywords | an OpenAI/Gemini credential)
- [x] Pass 1, per article (one request each, 4 at a time): issues inside the
      article plus its checkable claims (subject + exact statement); claims
      not found on the page dropped; kept for unchanged pages (checksum)
      unless forced
- [x] Pass 2, per translation pair: original vs. translation, one request
      each; kept when the translation is unchanged and the original's
      checksum matches
- [x] Pass 3, across articles: claims grouped by subject within each help
      center, by embeddings (OpenAI or Gemini key) or by keywords (no extra
      service; also the fallback when embeddings fail); groups whose
      statements all agree skipped; one request per group; a group seen
      before with the same statements reuses its verdict
- [x] Code-only findings: duplicate titles, links into another language's
      help center, broken links (when links ran), missing translations
- [x] `embeddings.py` (OpenAI, Gemini; batched); `claims.py` (keyword and
      embedding grouping, group keys)
- [x] Site settings: "Match statements across articles" select; the stage
      says which method ran
- [x] Tests: each pass and its reuse, grouping both ways, embedding
      fallback, code-only findings, force; frontend setting
- [x] Checks green; smoke test with a fake model; commit

## Claims view

- [x] `AuditRun.claim_groups` (migration 0010): the run's matching method and
      every group of 2+ statements with its status (agree, compared, kept,
      failed), verdict count and members
- [x] `GET /runs/{id}/claims` and `claims.csv`: every claim with subject,
      statement, page, help center and group
- [x] Claims page (`/audits/:runId/claims`): search, help center, "matched
      only" filters; groups with their status; links to pages; CSV export;
      linked from the dashboard and the findings page
- [x] Tests (backend + frontend); checks green; commit

## Optional checks per run

- [x] Run audit offers all five analyses; the site's are ticked to start
- [x] Content-integrity categories chosen per run (`AuditRun.integrity_categories`,
      migration 0011; null = the site's), at least one when integrity runs
- [x] Reuse respects categories: earlier answers are kept only when they
      were asked for every category this run checks (`categories` stored on
      `Page.integrity`, `Page.integrity_pair`, `ClaimGroupReview`)
- [x] Tests; checks green; commit

## Dashboard: content-integrity summary cards

- [x] Five category cards (largest first, the rest sharing the last) with
      accent bars, and the severity line with the top finding, per
      `_reference/Audit dashboard-html/Dashboard.dc.html`
- [x] Shown before triage as the reviewer's proposal (muted, labelled);
      the KPI stays "—" until triage is confirmed
- [x] `metrics.top`; tests; checks green; commit

## Findings page: updated row layout

- [x] One column per finding (title; severity, ID, tier and example on one
      line; summary; quotes; triage note), per
      `_reference/Findings and triage-html/Findings.dc.html`
- [x] "Confirm issue" replaces "Firm" on the tier control
- [x] Per quote: open the article on the site (new tab) and Details in
      HOP Audit; quotes carry their page URL from the API
- [x] Tests; checks green; commit

## Dashboard header

- [x] Report button (disabled until the report page is built, next)
- [x] "Re-evaluate everything" removed; re-evaluating is the Run audit toggle

## Milestone 7: full findings report (`_reference/new_screens/Full findings report-html`)

- [x] `report.py`: the report's data from a confirmed triage, in the skill's
      section order (summary + help centers, by category, contradictions,
      translation, instructions, remaining categories, items for review,
      site-health appendix); plain leads written in code from the counts
- [x] `GET /runs/{id}/report` (409 until triage is confirmed)
- [x] Exports: Letter PDF (HTML template rendered by Chromium via
      Playwright; 503 with a reason when the browser isn't installed),
      Word (.docx, python-docx), findings CSV (existing), full audit JSON;
      "Claude Doc" shown but unavailable (no Docs connection in the app)
- [x] Heretto wordmarks from the skill's assets (backend for exports,
      frontend public for the page)
- [x] Report page `/audits/:runId/report`: back link (Deliverables for
      prospect sites, dashboard otherwise), Copy link, Export menu, the
      article; a "confirm triage first" state
- [x] Links: dashboard Report button and integrity card "Full findings
      report"; Findings header "Full report"
- [x] Dockerfile installs Chromium for Playwright
- [x] Tests; checks green; commit

## Milestone 8: deliverables (`Deliverables-html`, `Lead one-sheet`, `Executive brief`)

- [x] `Deliverable` model (run, kind lead | exec, copy JSON, built_at,
      counts at build) + `Site.prospect_logo` (data URI, PNG/JPEG/SVG,
      ≤ 512 KB) + marketing sign-off flag; migration
- [x] Collateral Writer request: headlines, subhead, exec lead sentence,
      three why-it-matters lines (imperative + finding codes), three impact
      cards; counts, categories, severity, mix, examples (the triage's
      picks), review sentence, eyebrow and footnote computed in code so
      they always match the triage
- [x] The skill's two Jinja templates ported; `GET .../deliverables/{kind}.html`
      and `.pdf` (PDF fails on overflow, 409 with the excess)
- [x] `GET /runs/{id}/deliverables` (steps, cards, copy, prospect,
      checklist), `POST .../build`, `PATCH` copy, prospect and sign-off,
      logo upload / removal; prospect-review sites only, confirmed triage only
- [x] Internal summary note (`internal-summary.md`) built in code; Copy note
- [x] Deliverables page `/audits/:runId/deliverables`: steps, four cards
      with live thumbnails, copy and business case with budgets, prepared
      for and sender, before-sending checklist (placeholders, quotes to
      spot-check, marketing sign-off, overflow measured in the preview,
      counts match)
- [x] Preview page `/audits/:runId/deliverables/:kind`: the Letter page,
      its measured height, PDF
- [x] Findings header: "Confirm triage and build deliverables" on prospect
      sites
- [x] Tests; checks green; commit

## Report from the current tiers

- [x] No confirmed triage needed: firm counted, review listed, drop left
      out; the page notes an unconfirmed triage
- [x] Deliverables' report card depends on content integrity having run
- [x] Deliverables build from the current tiers too; an unconfirmed triage is a
      hand-off checklist item; Deliverables linked from Findings and the dashboard

## Deliverables build progress

- [x] Build runs in the background with a status, an error and a step log
      (also in the server log); one build at a time; interrupted or stalled
      builds read as failed
- [x] The page polls while building: elapsed time, progress bar, the log as
      it grows; the error and log when it fails; the last build's log after

## Sections below a language segment

- [x] Detect leading segments that aren't sections per help center (language
      codes, a shared base folder); planner, link-following and site discovery
      group by the segment after them; the run log says so

## Navigation: Audit History and Reports

- [x] Dashboard: "History" is "Audit History"; "Run log" removed (each run's
      log is a row action under Audit History); "Report" is "Reports" and opens
      the Deliverables page, renamed Reports
- [x] Reports: no Assess / Triage / Build / Hand off boxes (removed from the
      API too); own-docs sites see only the full findings report

- [x] Content Integrity card: no Full findings report or Reports buttons
      (Reports is opened from the dashboard header)
## Audits under sites

- [x] Sidebar: no Audits item; Audit history is per site at
      `/sites/:site/history` (named for the site, back to it, no switcher); old `/audits`
      links redirect; every history link points there

## No hover underlines on buttons

- [x] Buttons, back links, icon links, card and chart links don't underline
      on hover (global rule in `shared/_page.scss`); text links in tables and
      sentences keep hop-ui's underline

## Model timeouts don't fail the audit

- [x] Timeouts and dropped connections to the model are retried, then the
      page is skipped (was: the whole run failed with "ReadTimeout")
- [x] Wait up to 600 s for a reply (hop-core's default is 120 s)
- [x] A failed run names the error, the host and the timeout; traceback in
      the server log

## One-sheet examples never blank (user: "select issues blank … include the next highest severity issues")

- [x] `Facts.examples`: the triage's picks (in order), then the most severe
      confirmed issues not picked (High → Low, then code), up to three;
      `Facts.picked` keeps the picks alone
- [x] Checklist: still unticked until three are picked, and names the
      issues filled in; the Collateral Writer is told which were picked
- [x] Tests: the fill order, and a build with no picks; `./dev.sh check`

## Lead one-sheet: a second page of issues (user: "two pages … more issues on the second page … links to the example pages")

- [x] Page two of `onesheet_lead.html`: the confirmed issues not on page
      one, most severe first, up to `MORE` (7), each with severity, where,
      title, its first quote (clipped) and links to up to two of its pages;
      a line counts the rest, which are in the full findings report.
      Left out when there's nothing more to list
- [x] Page URLs from the quotes' `page_id`s (`Facts.urls`)
- [x] Overflow is measured per page, tallest kept (Chromium and the frame);
      the frame shows every page; the preview's links open in a new tab
- [x] Wording: checklist, preview page, lead card
- [x] Tests: the list, links, clipping, one page when there's nothing
      more; frame measuring two pages; `./dev.sh check`
- [x] Both quotes of a contradiction or translation on page two (was only
      the first), each clipped to 150 characters; six issues instead of seven
      to leave room

## Later milestones (from the handoff)

- [x] 7 Full findings report + exports (see milestone 7 above)
- [x] 8 Deliverables (see milestone 8 above)
- [ ] 9 Scheduling, rerun subsets, polish
