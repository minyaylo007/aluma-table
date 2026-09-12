#!/usr/bin/env python3
"""Daily read of the fx_* tables, then an AI second opinion on what it means.

    FX_DB_PATH=/opt/ihor/aluma-table/data/aluma.db python3 scripts/daily_report.py   # last 7 days
    python scripts/daily_report.py --days 3
    python scripts/daily_report.py --no-ai       # metrics only, no model call

Writes night/reports/REPORT-<date>.md.

Дані — з SQLite коробки через api/store.py, той самий файл і ті самі імена
таблиць, що в хендлера в режимі FX_STORAGE=sqlite (FX_DB_PATH, EVENTS_TABLE,
LEADS_TABLE). DynamoDB fx_* видалено разом зі старим AWS (docs/AWS-TEARDOWN.md),
тож boto3 тут більше не потрібен. Бази за FX_DB_PATH нема — вихід 2: порожню
базу скрипт не створює і нульовий звіт не пише.

It proposes. It changes nothing — not the site, not the price, not the ads.
On ten or twenty leads, an automated optimiser is a random number generator with
a confident voice; the decisions stay with the owner.

The model call uses ANTHROPIC_API_KEY from the environment. Without it the report
is still written, with the fully-rendered prompt at the bottom so it can be pasted
into any chat by hand. No key is read from the apartments system's secrets.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api import store  # noqa: E402

REPORTS = ROOT.parent / "night" / "reports"
PROMPT_FILE = ROOT / "prompts" / "daily-analysis.md"

FX_DB_PATH = os.environ.get("FX_DB_PATH", "data/aluma.db")
EVENTS_TABLE = os.environ.get("EVENTS_TABLE", "fx_events")
LEADS_TABLE = os.environ.get("LEADS_TABLE", "fx_leads")
SESSIONS_TABLE = os.environ.get("SESSIONS_TABLE", "fx_sessions")

MODEL = "claude-sonnet-5"
API_URL = "https://api.anthropic.com/v1/messages"


# ------------------------------------------------------------------ data


def key_eq(name: str, value: str):
    """Умова Key(name).eq(value) у формі, яку api/store.py розуміє без boto3."""
    return ("eq", name, value)


def open_tables(db_path: str):
    """(fx_events, fx_leads) з файлу бази. Нема файлу — FileNotFoundError, а не порожня база."""
    if db_path != ":memory:" and not os.path.exists(db_path):
        raise FileNotFoundError(db_path)
    events_t, leads_t, _sessions = store.tables(db_path, EVENTS_TABLE, LEADS_TABLE, SESSIONS_TABLE)
    return events_t, leads_t


def load(days: int, include_test: bool, tables=None):
    events_t, leads_t = tables or open_tables(FX_DB_PATH)

    events = []
    today = datetime.now(timezone.utc).date()
    for i in range(days):
        day = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        last = None
        while True:
            kw = {"KeyConditionExpression": key_eq("pk", f"D#{day}"), "Limit": 1000}
            if last:
                kw["ExclusiveStartKey"] = last
            r = events_t.query(**kw)
            events.extend(r.get("Items", []))
            last = r.get("LastEvaluatedKey")
            if not last:
                break

    leads, last = [], None
    while True:
        kw = {"KeyConditionExpression": key_eq("pk", "LEAD"), "ScanIndexForward": False, "Limit": 500}
        if last:
            kw["ExclusiveStartKey"] = last
        r = leads_t.query(**kw)
        leads.extend(r.get("Items", []))
        last = r.get("LastEvaluatedKey")
        if not last or len(leads) >= 2000:
            break

    if not include_test:
        events = [e for e in events if not e.get("is_test")]
        leads = [l for l in leads if not l.get("is_test")]

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    leads = [l for l in leads if l.get("ts", "") >= cutoff]
    return events, leads


def props(e):
    try:
        return json.loads(e.get("props_json") or "{}")
    except Exception:
        return {}


def analyse(events, leads, days):
    def sessions(pred):
        return {e.get("session_id") for e in events if pred(e) and e.get("session_id")}

    visits = sessions(lambda e: e.get("event_name") == "page_view")
    n = len(visits) or 0

    funnel = {
        "visits": n,
        "saw_price": len(sessions(lambda e: e.get("event_name") == "section_view"
                                  and props(e).get("section") in ("hero", "price"))),
        "configured": len(sessions(lambda e: e.get("event_name") in ("color_select", "size_toggle"))),
        "checked_fit": len(sessions(lambda e: e.get("event_name") == "room_fit_check")),
        "opened_faq": len(sessions(lambda e: e.get("event_name") == "faq_open")),
        "form_started": len(sessions(lambda e: e.get("event_name") == "form_start")),
        "lead": len(sessions(lambda e: e.get("event_name") == "lead_success")),
        "whatsapp": len(sessions(lambda e: e.get("event_name") == "whatsapp_click")),
    }

    def tally(key, where=lambda e: True, limit=12):
        c = collections.Counter()
        for e in events:
            if where(e):
                k = key(e)
                if k:
                    c[str(k)] += 1
        return c.most_common(limit)

    reached = collections.Counter()
    for e in events:
        if e.get("event_name", "").startswith("scroll_"):
            reached[e["event_name"]] += 1

    exits = [props(e) for e in events if e.get("event_name") == "exit"]
    times = sorted(int(p.get("seconds", 0)) for p in exits if p.get("seconds") is not None)
    median_time = times[len(times) // 2] if times else None

    return {
        "window_days": days,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "funnel": funnel,
        "by_source": tally(lambda e: f"{e.get('utm_source') or 'direct'}/{e.get('utm_campaign') or '-'}",
                           lambda e: e.get("event_name") == "page_view"),
        "by_device": tally(lambda e: e.get("device"), lambda e: e.get("event_name") == "page_view"),
        "by_colour": tally(lambda e: props(e).get("color"), lambda e: e.get("event_name") == "color_select"),
        "by_size": tally(lambda e: props(e).get("size"), lambda e: e.get("event_name") == "size_toggle"),
        "faq_opened": tally(lambda e: props(e).get("q"), lambda e: e.get("event_name") == "faq_open"),
        "room_fit_results": tally(lambda e: props(e).get("result"),
                                  lambda e: e.get("event_name") == "room_fit_check"),
        "room_lengths": sorted(int(props(e).get("room_length", 0))
                               for e in events if e.get("event_name") == "room_fit_check"),
        "form_errors": tally(lambda e: props(e).get("field"), lambda e: e.get("event_name") == "form_error"),
        "scroll_depth": dict(reached),
        "median_seconds_on_page": median_time,
        "leads": [
            {
                "ts": l.get("ts", "")[:16],
                "city": l.get("city", ""),
                "colour": l.get("color", ""),
                "size": l.get("size", ""),
                "lang": l.get("lang", ""),
                "comment": l.get("comment", ""),
                "status": l.get("status", "new"),
                "source": l.get("utm_source") or "direct",
                "marketing_opt_in": bool(l.get("consent_marketing")),
            }
            for l in leads
        ],
        "lead_status_counts": dict(collections.Counter(l.get("status", "new") for l in leads)),
    }


# ------------------------------------------------------------------ ai


def ask_model(prompt: str) -> str | None:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        return None
    payload = json.dumps({
        "model": MODEL,
        "max_tokens": 4000,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "content-type": "application/json",
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            body = json.load(r)
        return "".join(b.get("text", "") for b in body.get("content", []))
    except urllib.error.HTTPError as exc:
        return f"_The model call failed: HTTP {exc.code} — {exc.read()[:300].decode('utf-8', 'replace')}_"
    except Exception as exc:
        return f"_The model call failed: {exc!r}_"


# ------------------------------------------------------------------ main


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--no-ai", action="store_true")
    ap.add_argument("--include-test", action="store_true")
    args = ap.parse_args(argv)

    try:
        tables = open_tables(FX_DB_PATH)
    except FileNotFoundError:
        print(f"no database at FX_DB_PATH={FX_DB_PATH} — set FX_DB_PATH to the box database",
              file=sys.stderr)
        return 2
    events, leads = load(args.days, args.include_test, tables)
    data = analyse(events, leads, args.days)

    template = PROMPT_FILE.read_text(encoding="utf-8")
    prompt = template.replace("{{DATA}}", json.dumps(data, ensure_ascii=False, indent=2))

    verdict = None if args.no_ai else ask_model(prompt)

    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = REPORTS / f"REPORT-{stamp}.md"

    f = data["funnel"]
    lines = [
        f"# Report — {stamp}",
        "",
        f"Window: last {args.days} days · {len(events)} events · {len(leads)} leads"
        + ("  · **test rows included**" if args.include_test else ""),
        "",
        "## Funnel",
        "",
        "| step | sessions | of visits |",
        "|---|---:|---:|",
    ]
    base = f["visits"] or 1
    for label, key in [("visits", "visits"), ("saw the price", "saw_price"),
                       ("configured colour or size", "configured"),
                       ("used the room-fit tool", "checked_fit"),
                       ("opened an FAQ", "opened_faq"),
                       ("started the form", "form_started"),
                       ("left a lead", "lead"), ("tapped WhatsApp", "whatsapp")]:
        v = f[key]
        lines.append(f"| {label} | {v} | {100 * v / base:.0f}% |")

    lines += ["", "## Raw", "", "```json",
              json.dumps(data, ensure_ascii=False, indent=2)[:12000], "```", ""]

    if verdict:
        lines = lines[:4] + ["## What the model makes of it", "",
                             "_Proposals only. Nothing here was applied._", "",
                             verdict, ""] + lines[4:]
    else:
        lines += ["## AI analysis", "",
                  "_Skipped_ — set `ANTHROPIC_API_KEY` and re-run, or paste the prompt below "
                  "into any chat.", "", "<details><summary>prompt</summary>", "",
                  "````markdown", prompt, "````", "", "</details>", ""]

    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out}")
    print(f"  visits={f['visits']} leads={f['lead']} whatsapp={f['whatsapp']}")
    if not verdict and not args.no_ai:
        print("  (no ANTHROPIC_API_KEY — prompt embedded in the report instead)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
