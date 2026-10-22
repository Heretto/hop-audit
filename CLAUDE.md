# Agent Instructions: HOP Audit

HOP Audit audits documentation websites and help centers: it crawls every
language version, runs analysis agents (readability, links, SEO, content
integrity), keeps a dashboard and history per site, and, for prospect
reviews, builds Heretto-branded collateral from triaged findings.

Built on [hop-core](https://github.com/Heretto/hop-core) (FastAPI backend,
Angular 22 frontend using `@heretto/hop-ui`), the same way as
`~/dev/hop-docsite-analytics`. Borrow that project's structure, patterns and
tooling (`dev.sh`, tests layout, `hop-doctor`, Docker files) wherever they fit;
read its `CLAUDE.md` and `AGENTS.md` first.

## Start here

1. `design/HANDOFF.md`: the product spec, screen-by-screen, with the data
   model, agents, workflow rules and suggested build order.
2. `design/project/*.dc.html`: the approved UI mockups, one file per screen
   (self-contained HTML; `canvas.json` is the index). Match them.
3. `_reference/audit-asset-maker (1).skill`: a zip of the skill whose
   analysis this tool productizes. Unzip it to a scratch folder and read
   `SKILL.md` and `references/*.md`; its `references/audit-prompt.md`,
   `taxonomy-and-triage.md`, `report-structure.md`, `onesheet-data.md` and
   `business-imperatives.md` are the source of truth for the content-integrity
   analysis, triage, report and one-sheets. Its `assets/` hold the approved
   one-sheet templates and the Heretto wordmarks.
4. hop-core's `AGENTS.md` and `DESIGN-SYSTEM.md` (pin the current release per
   its Step 0, Python package and `@heretto/hop-ui` tarball together).

## Working style

Keep working until the task is complete. Do not stop to ask whether to
continue or to report a plan. Make a reasonable assumption, note it in the
commit message, and proceed.

After each set of work, pause and re-evaluate: does it cover the complete
capability, and is it written in the most concise but still readable way?
Before a large change, look for a smaller set of changes that would do.

## Definition of done

1. The change is implemented and matches the mockup for that screen.
2. Every primary function has tests, and the full suite passes.
3. Lint and type checks pass; the build succeeds; `hop-doctor` passes.
4. A git commit exists with a detailed list of the decisions made.

If any check fails, fix it and run again. Never report success with a
failing check.

## Testing

Write tests for every primary function as you add it, and run them after each
new piece of functionality. Cover the normal path, edge cases and errors.
If something cannot be tested here (a live site, a real model key), say so
at the end and name what is untested.

## Task tracking

Before starting, write every step to `TODO.md` as a checklist. Mark each step
done as you finish it; re-read `TODO.md` before starting a new step.

## Non-negotiables from the design

- UI uses `@heretto/hop-ui` components and tokens; never hard-coded hex.
  Agents, Credentials, Administration and Account are hop-core's pages,
  mounted as-is.
- Analyses are run by hop-core Agents; one agent per analysis, assigned per
  site. Model keys are hop-core credentials (Claude, OpenAI, Gemini).
- Content-integrity findings are never counted or built into deliverables
  until a person confirms triage (firm / for review / dropped).
- A help center that blocks the crawler is reported, never worked around.

## hop-core integration notes

`AGENTS.md` records how this project is wired onto hop-core (pinned release,
layout, settings, migrations, seeding, commands). Read it before changing the
backend or frontend setup, and run `./dev.sh check` before committing.
