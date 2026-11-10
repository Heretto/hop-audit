# HOP Audit

HOP Audit audits documentation websites and help centers. It crawls every
language version of a site, runs analysis agents over the pages
(readability, links, SEO and content integrity), and keeps a dashboard and
an audit history for each site. It turns triaged findings into
Heretto-branded reports: a full findings report, a lead
one-sheet and an executive brief.

It's built on [hop-core](https://github.com/Heretto/hop-core): a FastAPI
backend and an Angular frontend using `@heretto/hop-ui`.

## What it does

- **Sites and help centers:** each site has one or more help centers (one
  per language), discovered from sitemaps and `hreflang`, with include and
  exclude rules. A help center that blocks the crawler is reported, never
  worked around.
- **Audits:** a crawl, then the analyses. Pages that haven't changed since
  the last audit reuse its results, so no model tokens are spent on them.
- **Analyses:** readability scores and a Readability Reviewer agent, SEO
  checks and an SEO Analyst agent, link checking with proposed fixes, and
  content integrity: contradictions, translation mismatches and other
  issues, found within articles, across language versions and across
  related articles.
- **Triage:** content-integrity findings are sorted into firm, for review
  and dropped. Counts appear on the dashboard, history and comparisons once
  a person confirms the triage.
- **Reports:** the full findings report (page, PDF, Word), a lead one-sheet
  and an executive brief as Letter PDFs, for every site.

Each analysis is run by a hop-core agent, assigned per site. Model keys
(Claude, OpenAI or Gemini) are stored as hop-core credentials.

## Running it

You need Python 3.11+ and Node 22.22.3+ (or 24.15+).

```bash
./dev.sh          # set up on first run, then start the backend and frontend
./dev.sh test     # backend and frontend tests
./dev.sh check    # lint, types, tests, production build and hop-doctor
```

`./dev.sh` creates `.env` from `.env.example` with generated secrets and
prints the URL to open. Sign up, add a model key under **Credentials**, then
add a site.

PDFs need Chromium on the server: `./dev.sh` tries
`playwright install chromium`, and the Docker image includes it.

### Docker

```bash
cp .env.example .env    # fill in the three secrets; see the comments
docker compose up -d --build
```

The app is then on http://localhost:8080 (set `PUBLIC_URL` in `.env` to
that for a local run). Data lives in the `audit-data` volume.

## Deployment

HOP Audit runs on the shared HOP VM behind Caddy at
https://audit.herettoopenprojects.ai. See
[deploy/shared-vm/README.md](deploy/shared-vm/README.md).

## For contributors

- [`AGENTS.md`](AGENTS.md): how the project is wired onto hop-core, and
  the rules each part follows.
- [`CLAUDE.md`](CLAUDE.md): working style and the definition of done.
- [`design/HANDOFF.md`](design/HANDOFF.md): the product spec, screen by
  screen; `design/project/` holds the approved mockups.
- [`TODO.md`](TODO.md): progress, change by change.

## License

Copyright 2026 Jorsek Inc. D.B.A. Heretto.

HOP Audit is licensed under the [Elastic License 2.0](LICENSE). You may
use, copy, modify and distribute it, but you may not offer it to others as
a hosted or managed service. See [LICENSE](LICENSE) for the full terms.
