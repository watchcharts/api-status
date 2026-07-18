#!/usr/bin/env python3
"""WatchCharts API uptime checker.

Pings a small set of endpoints, records status + latency into
docs/data/history.json (pruned to RETENTION_DAYS). Designed to run from
GitHub Actions on a cron schedule.

Credit cost per run: 5 (brand/list=1, search/watch=1, watch/info=3).
At a 10-minute cadence that's 720 credits per rolling 24h - use a
dedicated API key with a per-key cap (https://watchcharts.com/api/keys).

Env:
  WATCHCHARTS_API_KEY  required (unless --mock)
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_URL = "https://api.watchcharts.com/v3"
TIMEOUT_S = 15
SLOW_MS = 3000          # slower than this => degraded
RETENTION_DAYS = 90
REQUEST_GAP_S = 1.1     # API allows 1 req/sec per key

# Known-stable target: Rolex Daytona 116500LN
DAYTONA_UUID = "7901c9d7-22f9-4783-b5ce-48ee079a62ab"

CHECKS = [
    {"id": "brand_list", "name": "Brand catalog", "path": "/brand/list", "params": {}},
    {"id": "search_watch", "name": "Watch search", "path": "/search/watch",
     "params": {"brand_name": "rolex", "reference": "116500"}},
    {"id": "watch_info", "name": "Watch info", "path": "/watch/info",
     "params": {"uuid": DAYTONA_UUID}},
]

HISTORY_PATH = Path(__file__).resolve().parent.parent / "docs" / "data" / "history.json"


def run_check(check: dict, api_key: str) -> dict:
    from urllib.parse import urlencode
    url = f"{BASE_URL}{check['path']}"
    if check["params"]:
        url += "?" + urlencode(check["params"])
    req = urllib.request.Request(url, headers={"x-api-key": api_key})
    start = time.monotonic()
    code, err = None, None
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            resp.read()
            code = resp.status
    except urllib.error.HTTPError as e:
        code = e.code
        try:
            err = json.loads(e.read().decode()).get("message")
        except Exception:
            err = str(e)
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
    latency_ms = round((time.monotonic() - start) * 1000)

    if code == 200:
        status = "degraded" if latency_ms > SLOW_MS else "up"
    elif code == 429 or (code == 403 and err and "credit" in err.lower()):
        # Monitor hit its own rate/credit limits - API itself isn't down.
        status = "monitor_limited"
    elif code is not None and 400 <= code < 500:
        status = "warn"      # likely monitor misconfig (bad key/param)
    else:
        status = "down"      # 5xx, timeout, DNS, connection refused

    return {"id": check["id"], "status": status, "code": code,
            "latency_ms": latency_ms, "error": err}


def mock_results() -> list:
    import random
    return [{"id": c["id"], "status": "up", "code": 200,
             "latency_ms": random.randint(120, 900), "error": None}
            for c in CHECKS]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="write fake results (no API calls)")
    args = ap.parse_args()

    if args.mock:
        results = mock_results()
    else:
        api_key = os.environ.get("WATCHCHARTS_API_KEY")
        if not api_key:
            print("WATCHCHARTS_API_KEY is not set", file=sys.stderr)
            return 1
        results = []
        for i, check in enumerate(CHECKS):
            if i:
                time.sleep(REQUEST_GAP_S)
            results.append(run_check(check, api_key))

    now = datetime.now(timezone.utc)
    entry = {"ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "checks": results}

    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    history = {"endpoints": [{"id": c["id"], "name": c["name"], "path": c["path"]}
                             for c in CHECKS],
               "entries": []}
    if HISTORY_PATH.exists():
        try:
            history = json.loads(HISTORY_PATH.read_text())
        except json.JSONDecodeError:
            pass
    history["endpoints"] = [{"id": c["id"], "name": c["name"], "path": c["path"]}
                            for c in CHECKS]

    cutoff = (now - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    history["entries"] = [e for e in history.get("entries", []) if e["ts"] >= cutoff]
    history["entries"].append(entry)
    HISTORY_PATH.write_text(json.dumps(history, separators=(",", ":")) + "\n")

    worst = max((r["status"] for r in results),
                key=["up", "monitor_limited", "degraded", "warn", "down"].index)
    print(f"{entry['ts']} overall={worst} " +
          " ".join(f"{r['id']}={r['status']}({r['latency_ms']}ms)" for r in results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
