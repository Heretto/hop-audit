# HOP Audit on the shared HOP VM

HOP Audit runs on the shared VM alongside HOP Chat, the Release Notes Agent
and HOP Doc Site Analytics. hop-server-tools owns the VM: Caddy (TLS, ports
80/443, routing) and the start/stop scripts. This folder holds only what
this repo needs to sit behind it.

Public URL: **https://audit.herettoopenprojects.ai**

## First run

```bash
git clone https://github.com/Heretto/hop-audit.git ~/hop-audit
cd ~/hop-audit
cp .env.example .env
```

Fill in `.env`:

| Variable | Value |
|---|---|
| `APP_SECRET_KEY`, `JWT_SECRET_KEY` | `openssl rand -hex 32`, one each |
| `ENCRYPTION_KEY` | `openssl rand -hex 32`. It encrypts stored model keys and **can't be rotated**: back it up, never regenerate it |
| `PUBLIC_URL` | `https://audit.herettoopenprojects.ai`, already in the template; leave it |
| `ALLOWED_EMAIL_DOMAINS` | `heretto.com`. Without it anyone on the internet can sign up |
| `SINGLE_ORG_MODE`, `SINGLE_ORG_SLUG`, `SINGLE_ORG_NAME` | `true`, `heretto`, `Heretto`, so the team shares one organization |
| `SSO_ONLY` and the OAuth settings | optional; preferred for production (hop-core `AGENTS.md` §11). Google needs `https://audit.herettoopenprojects.ai` as an authorized JavaScript origin; Microsoft's redirect URI is `https://audit.herettoopenprojects.ai/api/v1/auth/sso/microsoft/callback` |

Leave `COOKIE_DOMAIN` unset. `DATABASE_URL`, `FRONTEND_BASE_URL`,
`CORS_ORIGINS`, `OAUTH_REDIRECT_BASE_URL`, `COOKIE_SECURE` and `APP_ENV` are
set by `docker-compose.yml` (from `PUBLIC_URL`), so their `.env` values are
ignored in containers. No `--env-file` is needed beyond the repo's `.env`.

Then start it the way hop-server-tools does:

```bash
docker compose --project-directory ~/hop-audit \
  -f ~/hop-audit/docker-compose.yml \
  -f ~/hop-audit/deploy/shared-vm/docker-compose.override.yml up -d --build
```

### One-time steps

None to run by hand:

- **Migrations** run at backend startup (Alembic, then hop-core's tables).
- **Admin:** the first person to sign up becomes the organization's admin
  (with `SINGLE_ORG_MODE`; otherwise each sign-up gets its own organization
  and is its admin). Sign up yourself before sharing the URL.
- **Seeding:** the six analysis agents are created per organization the
  first time someone opens the app. Add a model key under **Credentials**
  (Claude, OpenAI or Gemini) and assign it to the agents.

## Containers

| Service | Role | Listens | Memory limit |
|---|---|---|---|
| `hop-audit-web` | nginx: the Angular app, `/api` proxied to the backend, `GET /health` | 8080, plain HTTP | 128 MB |
| `hop-audit-backend` | FastAPI (uvicorn, one process): API, audits, Chromium for PDFs | 8000, project network only | 1.5 GB |

- Only `hop-audit-web` joins `edge`, under the alias **`hop-audit`**. Caddy
  forwards to `hop-audit:8080`. The override removes the base file's local
  port (8080); nothing in this repo binds 80 or 443.
- `GET /health` answers 200 with `{"status":"ok"}` (or 503 if the database
  is unreachable), with no redirect. Both containers have healthchecks; the
  web container starts once the backend is healthy.
- The app speaks plain HTTP and never redirects to HTTPS. nginx trusts
  `X-Forwarded-For` / `X-Forwarded-Proto` from 10.0.0.0/8, 172.16.0.0/12
  and 192.168.0.0/16, and uvicorn trusts nginx, so rate limits see the
  visitor's address and cookies are `Secure`.
- Every service: `restart: unless-stopped`, json-file logs, 10 MB × 3.
- Idle use is about 120 MB (backend) and 20 MB (web). The backend grows
  while an audit runs, and by a few hundred MB while Chromium renders a PDF
  or, for a site with Render JavaScript on, its pages during the crawl
  (up to 3 tabs; Chromium closes before the analyses).

## Data

One named volume, **`audit-data`**, mounted at `/data` in the backend: the
SQLite database (`/data/audit.db`) with sites, audits, crawled pages,
findings and stored credentials. Back it up along with `ENCRYPTION_KEY`;
one without the other can't read the saved model keys.

## Background work

There's no cron and no separate worker. Audits (crawl, then the analyses and
model calls) and one-sheet builds run as background tasks inside the backend
process, so it must stay a single replica with one uvicorn worker. An audit
of a few hundred pages takes minutes to an hour, mostly waiting on the model.
A restart marks audits and builds that were running as failed; start them
again from the app. Site schedules are stored but not run yet.

## Requests to know about

- **No streaming:** no server-sent events and no websockets. The app polls
  every 2 s while an audit or build is running.
- **Long requests:** PDF downloads (full report, one-sheets) render in
  Chromium, typically a few seconds and up to about 30 s. nginx allows 300 s.
- **Uploads:** prospect logos only, up to 512 KB (sent as JSON); nginx
  accepts bodies up to 10 MB.

## Don't

- Don't run a host-level nginx, certbot or systemd unit for this app;
  Caddy and hop-server-tools cover all of it.
- This repo has no setup scripts for a dedicated VM. If any are added,
  they must never be run on the shared VM.
