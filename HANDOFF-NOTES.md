# Handoff notes: state of work (2026-11-07)

For an agent picking this project up in a new session. Read `CLAUDE.md`,
then `AGENTS.md` (how the project is wired; the source of truth for
behavior), then `TODO.md` (every step taken, by section). This note covers
only what those files don't: where things stand and what's open.

## Where things stand

- Milestones 1–8 of `design/HANDOFF.md` are done: scaffold, sites, crawler
  and runs, mechanical analyses, agent review, content integrity and
  triage, the full findings report and its exports, and deliverables
  (one-sheets).
- Last commit: `a8063b1` (Audit history: one site's page, back to that
  site). `./dev.sh check` passed on it: 235 backend tests, 156 frontend
  tests, build, and `hop-doctor --strict` (9 passed).
- Pinned to hop-core **v0.1.18** (Python package and `@heretto/hop-ui`
  tarball).

## Recent changes (this session, newest first)

0. **Lead one-sheet** (2026-11-08): "What we found" is never blank (picks,
   then the most severe confirmed issues; `cc781f2`), and a second page lists
   up to seven more issues with links to their pages (`aae42e6`). Neither has
   been rendered to PDF or seen in a browser.

All are in `TODO.md` and `AGENTS.md`. They're listed here so you know
what's fresh and has had no use in a browser yet.

1. **Audit history is per site** (`/sites/:site/history`). The heading
   reads "Audit history for <site>", the back link goes to the site, and
   there is no site dropdown. `/audits?site=x` redirects there, and
   `/audits` redirects to Sites.
2. **Model timeouts don't fail the audit** (`review.py`, `runner.py`).
   hop-core's 120 s generation timeout is raised to 600 s. An
   `httpx.TransportError` (which hop-core doesn't wrap) is retried, then
   the page is skipped. A run that still fails names the error type and
   host. This was caused by a real ReadTimeout on a full audit of
   help.heretto.com.
3. **No hover underline on buttons or button-like links.** This is a global
   rule in `frontend/src/app/shared/_page.scss`. Text links in tables and
   sentences keep the underline.
4. **The sidebar has no Audits item.** Its items are Sites, Agents and
   Credentials.
5. **The Content Integrity card** has no "Full findings report" or "Reports"
   buttons.
6. **Navigation renames.** The dashboard header has Audit History, Reports
   and Run audit. The Deliverables page is called **Reports** in the UI
   (its route is still `/audits/:runId/deliverables`). The Assess, Triage,
   Build and Hand off step boxes are removed, in the UI and the API. Own-docs
   sites see only the full findings report card. The run log is opened from
   a row action in Audit History.
7. **Section detection** (`scope.detect_prefix`) looks past a leading
   language segment, such as `/en/` on Heretto portals, or past a base folder
   every page shares.

## Not verified

- **No browser check** of any of the recent UI changes; they were checked
  by unit tests only. Start the app with `./dev.sh` and look at the
  dashboard, Audit history, Reports and the sidebar.
- **No live audit** after the timeout fix. In this sandbox every outbound
  site returns 403 from the egress proxy, so discovery reads as blocked.
  The real Anthropic API is also untested here. Ask the user to re-run the
  help.heretto.com audit.
- **No PDF output** has been produced here. Chromium couldn't be installed
  because `cdn.playwright.dev` is pending firewall approval.

## Open work

**Next milestone, 9 (from `design/HANDOFF.md`):** scheduling, rerun subsets
(changed since last run) and polish. What already exists:

- `Site.schedule` is a JSON column, but nothing reads it.
- `AuditRun.trigger` can be `manual` or `schedule`.
- `AGENTS.md` says the scheduler runs in-process (single replica).

**Offered to the user but not requested (ask before doing):**

- Move the `/audits/:runId/...` pages under `/sites/:id/...`. Today no
  sidebar item is highlighted on audit pages, because hop-ui highlights by
  route prefix.
- Rename the `/deliverables` URL to `/reports` to match the UI name.
- Allow a failed audit whose crawl finished to be analyzed again. Today
  `POST /runs/{id}/analyze` requires a completed run.
- Remove underlines from prose links too.

## Practical notes

- **Linux sandbox tools:**
  - The backend venv is `backend/.venv-linux-arm64`. Run `ruff` and
    `pytest` from its `bin/`.
  - Run frontend tests through `./dev.sh check`, not `npx ng test`
    directly. The checkout is shared with a Mac, and dev.sh swaps the
    esbuild native packages.
- **Don't commit `_reference/` changes.** The user has deleted and added
  reference files there (`_reference/new_screens/`); those changes are
  theirs.
- **Commits:**
  - Each commit lists the decisions made and ends with the
    `Co-Authored-By` line from the session's attribution reminder.
  - Update `TODO.md` and `AGENTS.md` with each change.
