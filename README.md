# WatchCharts API Status Page

Public uptime monitor for `api.watchcharts.com/v3`. A GitHub Actions cron runs
`scripts/check.py` every 10 minutes, records status + latency to
`docs/data/history.json`, and GitHub Pages serves `docs/index.html` as the
status page. No servers, no database.

## What it checks (7 credits/run, ~1,008/rolling 24h)

| Check | Endpoint | Credits |
|---|---|---|
| Watch search | `GET /search/watch` (Rolex 116500) | 1 |
| Watch info | `GET /watch/info` (Daytona UUID) | 3 |
| Price history (1y) | `GET /watch/price_1y` (Daytona UUID) | 3 |

Status classification: `200` fast → **up**; `200` >3s → **degraded**; `429` or
credit-limit `403` → **monitor_limited** (not counted as downtime); other 4xx →
**warn** (monitor misconfig); 5xx/timeout/connection failure → **down**.

## Setup

Repo: https://github.com/watchcharts/api-status · Live: https://status.api.watchcharts.com

1. Create a **dedicated API key** at https://watchcharts.com/api/keys and set a
   per-key credit cap (e.g. 1,200) so monitoring can never starve production keys.
2. Add it as repo secret `WATCHCHARTS_API_KEY`
   (Settings → Secrets and variables → Actions).
3. Enable GitHub Pages: Settings → Pages → Deploy from branch → `main` / `/docs`.
4. Custom domain (Cloudflare):
   - In Cloudflare DNS for `watchcharts.com`, add a **CNAME** record:
     name `status.api`, target `watchcharts.github.io`, proxy **DNS only**
     (grey cloud) until the cert issues.
   - In repo Settings → Pages, set custom domain `status.api.watchcharts.com`
     (matches `docs/CNAME`), wait for the DNS check + certificate, then tick
     **Enforce HTTPS**.
   - Optionally flip the Cloudflare record to **Proxied** afterwards
     (SSL/TLS mode must be **Full (strict)** to avoid redirect loops).
5. Trigger the workflow once manually (Actions → Uptime check → Run workflow)
   to seed `history.json`.

## Local test

```bash
python3 scripts/check.py --mock       # no API calls, writes fake entry
python3 -m http.server -d docs 8000   # view at http://localhost:8000
```

## Tuning

- **Cadence:** edit the cron in `.github/workflows/uptime.yml`. Every 5 min
  doubles credit usage to ~1,440/24h.
- **Checks:** edit `CHECKS` in `scripts/check.py`. Mind credit costs
  (Level 2 endpoints cost 5–10 each).
- **Retention:** `RETENTION_DAYS` in `check.py` (default 90).

## Downtime email notifications

When any check transitions to **down**, the workflow opens a GitHub issue
labelled `incident`; on recovery it closes the issue with a comment. GitHub
emails these to everyone **watching** the repo (Watch → Custom → Issues) — the
status page has subscribe instructions, and open incidents render at the top
of the page via the GitHub API. No email service, list management, or
unsubscribe handling needed. Note: repo collaborators are auto-subscribed to
their own activity; external subscribers must have a GitHub account.

## Notes

- GitHub cron isn't exact; runs can be delayed a few minutes under load. Fine
  for a status page, not for paging/alerting. To add alerting, append a
  Slack-webhook step to the workflow that fires when the script prints
  `overall=down`.
- History is committed to the repo — that's the "database". At 144 runs/day the
  file stays small (<2 MB for 90 days).
