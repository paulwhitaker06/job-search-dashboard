"""
Sox + Pats sports feed refresh, every 30 minutes.

Runs in GHA. Uses Claude with web_search to:
  1. Look up today's Sox first pitch and Pats kickoff (if any)
  2. Apply the reset rule: if now >= first_pitch, purge stale game-tagged items
  3. Find fresh headlines from a rotating outlet set
  4. Write Barstool-adjacent bar-stool-podcast snark
  5. Cap each team at 14 items, drop anything older than 48h

Voice: crass, cocky, horny-ish, zero filler. Punch sideways (media, front
offices, rival fanbases) and up (ownership). Keep it Boston. No slurs, no
fabricated quotes from real people.

Touches `sports_feed.sox.items` and `sports_feed.pats.items` in
dashboard-data.json. Also bumps `sports_feed.updated`.

Cost: ~$0.10-0.15 per call. At every-30-min cadence ≈ $5-7/day.

Public API:
  refresh_sports_feed(today=None, dry_run=False) -> RefreshResult
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from pipeline.commit_and_push import clone_dashboard, commit_and_push


REFRESH_MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 6000
WEB_SEARCH_MAX_USES = 8
DASHBOARD_REPO_DIR = Path("/tmp/dashboard-sports")

MAX_ITEMS_PER_TEAM = 14
MIN_ITEMS_PER_TEAM = 6
ITEM_AGE_LIMIT_HOURS = 24  # 2026-04-27: tightened from 48 — Paul wants stale items dropped more aggressively


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class RefreshResult:
    status: str
    sox_purged_count: int = 0
    pats_purged_count: int = 0
    sox_added_count: int = 0
    pats_added_count: int = 0
    sox_total_after: int = 0
    pats_total_after: int = 0
    sox_first_pitch_utc: str = ""
    pats_kickoff_utc: str = ""
    purge_reason_sox: str = ""
    purge_reason_pats: str = ""
    reason: str = ""


# ---------------------------------------------------------------------------
# Item shape and helpers
# ---------------------------------------------------------------------------

ALLOWED_GAME_TAGS = {"preview", "recap", None}

ITEM_SCHEMA_DESC = (
    "Each item: {headline (under 90 chars), url, source (short outlet name), "
    "published (ISO 8601 UTC), snark (one sentence, Barstool voice), "
    "game_tag (one of 'preview', 'recap', or null)}."
)


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(s: str) -> datetime | None:
    if not s:
        return None
    try:
        # Handle "Z" suffix and offsets
        if s.endswith("Z"):
            return datetime.fromisoformat(s[:-1] + "+00:00")
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _classify_legacy_item(item: dict) -> str | None:
    """Heuristic for items missing game_tag. Returns 'preview', 'recap', or None."""
    headline = (item.get("headline") or "").lower()
    url = (item.get("url") or "").lower()

    # Preview indicators
    preview_words = ["lineup", "lineups", "tonight", "matchup", "probable pitcher",
                     "odds", "prediction", "picks", "preview"]
    if any(w in headline for w in preview_words):
        return "preview"

    # Recap indicators
    recap_words = ["shut out", "blank", "walk-off", "drives in", "homers",
                   "beat ", "defeat", "edge "]
    if any(w in headline for w in recap_words):
        return "recap"
    if re.search(r"\b\d+\s*[-,]\s*\d+\b", headline):
        return "recap"
    if any(s in url for s in ["/recap/", "/game-information/", "/final/"]):
        return "recap"

    return None


def _normalize_items(items: list[dict]) -> list[dict]:
    """Ensure every item has game_tag (auto-classify legacy items missing it)."""
    out = []
    for it in items:
        if "game_tag" not in it:
            it = {**it, "game_tag": _classify_legacy_item(it)}
        out.append(it)
    return out


def _drop_stale_by_age(items: list[dict], hours: int = ITEM_AGE_LIMIT_HOURS) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    kept = []
    for it in items:
        pub = _parse_iso(it.get("published", ""))
        if pub is None or pub >= cutoff:
            kept.append(it)
    return kept


def _apply_reset_rule(items: list[dict], game_start_utc: datetime | None,
                      now_utc: datetime) -> tuple[list[dict], list[dict]]:
    """If now >= game_start, purge items where game_tag in {preview, recap}
    AND published < game_start. Returns (kept, purged)."""
    if game_start_utc is None or now_utc < game_start_utc:
        return items, []
    kept, purged = [], []
    for it in items:
        if it.get("game_tag") in ("preview", "recap"):
            pub = _parse_iso(it.get("published", ""))
            if pub is not None and pub < game_start_utc:
                purged.append(it)
                continue
        kept.append(it)
    return kept, purged


# ---------------------------------------------------------------------------
# Tool schema
# ---------------------------------------------------------------------------

SPORTS_TOOL = {
    "name": "submit_sports_refresh",
    "description": (
        "Submit fresh Sox + Pats headlines, classify each with game_tag, and "
        "report today's game schedule for the reset rule. Call exactly once."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sox_first_pitch_utc": {
                "type": "string",
                "description": (
                    "Today's Red Sox first pitch in ISO 8601 UTC (e.g. "
                    "'2026-04-27T19:10:00Z'), or empty string if no Sox game today."
                ),
            },
            "pats_kickoff_utc": {
                "type": "string",
                "description": (
                    "Today's Patriots kickoff in ISO 8601 UTC, or empty string "
                    "if no Pats game today (offseason or non-game-day)."
                ),
            },
            "new_sox_items": {
                "type": "array",
                "minItems": 6, "maxItems": 14,
                "description": (
                    "6-14 fresh Red Sox items from a DIVERSE outlet rotation "
                    "(Pats Pulpit, WEEI, BSJ, MassLive, Boston Globe, NESN, "
                    "The Ringer, B/R, Over the Monster, The Athletic, "
                    "Sons of Sam Horn, OTM Pod, Section 10 Pod, Barstool, "
                    "Patriots Wire). " + ITEM_SCHEMA_DESC
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "headline": {"type": "string"},
                        "url": {"type": "string"},
                        "source": {"type": "string"},
                        "published": {"type": "string"},
                        "snark": {"type": "string"},
                        "game_tag": {"type": "string", "enum": ["preview", "recap", "null"],
                                     "description": "Use literal string 'null' for evergreen items."},
                    },
                    "required": ["headline", "url", "source", "published", "snark", "game_tag"],
                },
            },
            "new_pats_items": {
                "type": "array",
                "minItems": 6, "maxItems": 14,
                "description": (
                    "6-14 fresh Patriots items, same outlet rotation. " + ITEM_SCHEMA_DESC
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "headline": {"type": "string"},
                        "url": {"type": "string"},
                        "source": {"type": "string"},
                        "published": {"type": "string"},
                        "snark": {"type": "string"},
                        "game_tag": {"type": "string", "enum": ["preview", "recap", "null"]},
                    },
                    "required": ["headline", "url", "source", "published", "snark", "game_tag"],
                },
            },
            "notes": {
                "type": "string",
                "description": "1-2 sentences on what's happening today (game state, breaking news, notable absence of news).",
            },
        },
        "required": ["sox_first_pitch_utc", "pats_kickoff_utc",
                     "new_sox_items", "new_pats_items", "notes"],
    },
}


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

SNARK_VOICE_GUIDE = """\
# Snark voice (HARD RULES)

Barstool-adjacent bar-stool-podcast voice. Crass, cocky, horny-ish, ZERO
filler. ONE sentence per item. Punch sideways (media, front offices, rival
fanbases) and up (ownership). Keep it Boston. NO slurs. NO targeted
punching down at specific real people in harmful ways. NO fabricated
quotes from real journalists.

Calibration examples:

  - "This bullpen couldn't find the plate with two hands, a flashlight,
    and a lap dance."
  - "Jets fans celebrating their draft like a guy finishing before the
    date takes her coat off."
  - "Fire the manager. Fire the GM. Real hot take: fire John Henry into
    the sun."
  - "CHB has been having this same heart attack since '86. EMTs stopped
    coming."
  - "Trade targets: a bat, an arm, and a front office that drinks less at
    the deadline."

Length: roughly 12-25 words per snark. If your snark exceeds 30 words,
cut. If it sounds like a LinkedIn post, rewrite. If it sounds like Bill
Simmons trying too hard, rewrite.
"""


def _build_system_prompt() -> str:
    return f"""\
You are refreshing Paul Whitaker's Sox + Pats sports feed on his Job Search
Command Center dashboard. This fires every 30 minutes. Keep it tight.

# Your job (in this order)

1. Use web_search to look up TODAY'S schedule:
   - Red Sox first pitch (search "red sox today schedule" or "BOS first pitch
     YYYY-MM-DD"). Format as ISO 8601 UTC. Empty string if no game today.
   - Patriots kickoff (search "patriots schedule today" — only relevant on
     in-season Sun/Mon/Thu). Empty string if no game today (likely most days
     since you're refreshing year-round).

2. Find FRESH headlines from a DIVERSE outlet rotation. Use web_search
   against named outlets. Don't let one outlet dominate. Try Over the
   Monster, Pats Pulpit, MassLive, Boston Globe, NESN, BSJ, WEEI, The
   Ringer, B/R, Boston Herald, Patriots Wire, Sons of Sam Horn, Section 10
   Pod, OTM Pod. RSS feeds work too.

3. For each headline, write ONE sentence of Barstool-voice snark.

4. Classify each item with game_tag: 'preview' (lineups, matchups,
   probable pitchers, odds, picks, predictions), 'recap' (final scores,
   game wraps, "X shut out Y", walk-off stories), or 'null' (everything
   else: roster moves, injuries, columnist takes, trade rumors, prospect
   news, draft analysis).

5. Return 6-14 items per team. If you can't find that many fresh items
   today, return what you have plus evergreen takes (columnist opinions,
   trade rumors, prospect notes, season-state takes).

# Hard rules

- Don't invent facts. Headlines must reflect something you actually
  read.
- Don't fabricate quotes from real journalists.
- NO em-dashes, en-dashes, or " -- " anywhere.
- Snark in YOUR voice, not the columnist's voice.
- Use literal string "null" for game_tag on evergreen items (the JSON
  schema enforces enum, so don't return null/None).

{SNARK_VOICE_GUIDE}

# Today's date

{date.today().isoformat()}
"""


def _build_user_prompt(current_sox: list[dict], current_pats: list[dict]) -> str:
    sox_titles = "\n".join(f"  - [{i.get('game_tag')}] {i.get('headline', '')[:80]}" for i in current_sox)
    pats_titles = "\n".join(f"  - [{i.get('game_tag')}] {i.get('headline', '')[:80]}" for i in current_pats)
    return f"""\
Refresh both feeds.

Currently in sox feed ({len(current_sox)} items):
{sox_titles or '  (empty)'}

Currently in pats feed ({len(current_pats)} items):
{pats_titles or '  (empty)'}

Find fresh items, classify with game_tag, write Barstool-voice snark, and
report today's first pitch / kickoff.

You don't need to return EVERY item that's currently in the feeds — just
fresh content. The pipeline will merge your new items with the existing
items, dedupe by headline, apply the reset rule based on the schedule you
report, and cap at 14 per team.

Call submit_sports_refresh exactly once.
"""


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------

def _call_refresh(client, model: str, current_sox: list[dict],
                  current_pats: list[dict]) -> dict | None:
    msg = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=_build_system_prompt(),
        tools=[
            {"type": "web_search_20250305", "name": "web_search", "max_uses": WEB_SEARCH_MAX_USES},
            SPORTS_TOOL,
        ],
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": _build_user_prompt(current_sox, current_pats)}],
    )
    submission = None
    for block in msg.content:
        if block.type == "tool_use" and block.name == "submit_sports_refresh":
            submission = dict(block.input)
    return submission


def _normalize_game_tag(t: str) -> str | None:
    """Tool returns string 'null' for evergreen; convert to actual None."""
    if isinstance(t, str) and t.lower() == "null":
        return None
    return t


def _merge_team(existing: list[dict], new: list[dict],
                game_start_utc: datetime | None,
                now_utc: datetime) -> tuple[list[dict], int, int]:
    """Apply reset rule + age limit + dedupe + add new + cap. Returns (final, purged_count, added_count)."""
    # Step 1: normalize legacy items to have game_tag
    existing = _normalize_items(existing)

    # Step 2: drop stale by age (>48h old)
    kept_age = _drop_stale_by_age(existing)

    # Step 3: apply reset rule
    kept_after_reset, purged_reset = _apply_reset_rule(kept_age, game_start_utc, now_utc)

    purged_total = (len(existing) - len(kept_age)) + len(purged_reset)

    # Step 4: dedupe new items by headline (against kept and against each other)
    seen = {it.get("headline", "").strip().lower() for it in kept_after_reset}
    fresh_new = []
    for n in new:
        n = {**n, "game_tag": _normalize_game_tag(n.get("game_tag"))}
        h = n.get("headline", "").strip().lower()
        if h and h not in seen:
            fresh_new.append(n)
            seen.add(h)

    # Step 5: combine, sort by published desc, cap at MAX_ITEMS_PER_TEAM
    combined = kept_after_reset + fresh_new

    def _pub_key(it):
        d = _parse_iso(it.get("published", ""))
        return d if d else datetime.min.replace(tzinfo=timezone.utc)

    combined.sort(key=_pub_key, reverse=True)
    final = combined[:MAX_ITEMS_PER_TEAM]
    added = len(fresh_new)

    return final, purged_total, added


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------

def refresh_sports_feed(today: date | None = None, dry_run: bool = False,
                         anthropic_client=None) -> RefreshResult:
    if today is None:
        today = date.today()
    if anthropic_client is None:
        import anthropic
        anthropic_client = anthropic.Anthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY", "").strip()
        )

    print(f"[refresh-sports] Run for {_now_utc_iso()}")

    print(f"[1/4] Cloning dashboard repo...")
    repo = clone_dashboard(DASHBOARD_REPO_DIR)
    json_path = repo / "dashboard-data.json"
    with json_path.open() as f:
        data = json.load(f)

    sf = data.setdefault("sports_feed", {"sox": {"items": []}, "pats": {"items": []}})
    sf.setdefault("sox", {"items": []})
    sf.setdefault("pats", {"items": []})
    current_sox = list(sf["sox"].get("items") or [])
    current_pats = list(sf["pats"].get("items") or [])
    print(f"  Current: {len(current_sox)} Sox, {len(current_pats)} Pats")

    print(f"[2/4] Calling Claude (web_search + generate)...")
    submission = _call_refresh(anthropic_client, REFRESH_MODEL, current_sox, current_pats)
    if submission is None:
        return RefreshResult(status="error", reason="no_tool_call_returned")
    print(f"  Got: {len(submission.get('new_sox_items', []))} new Sox, "
          f"{len(submission.get('new_pats_items', []))} new Pats")
    print(f"  Sox first pitch UTC: {submission.get('sox_first_pitch_utc') or '(none)'}")
    print(f"  Pats kickoff UTC:    {submission.get('pats_kickoff_utc') or '(none)'}")
    print(f"  Notes: {submission.get('notes', '')[:200]}")

    print(f"[3/4] Applying reset rule + dedupe + cap...")
    now_utc = datetime.now(timezone.utc)
    sox_start = _parse_iso(submission.get("sox_first_pitch_utc", ""))
    pats_start = _parse_iso(submission.get("pats_kickoff_utc", ""))

    sox_final, sox_purged, sox_added = _merge_team(
        current_sox, submission.get("new_sox_items", []), sox_start, now_utc,
    )
    pats_final, pats_purged, pats_added = _merge_team(
        current_pats, submission.get("new_pats_items", []), pats_start, now_utc,
    )

    sf["sox"]["items"] = sox_final
    sf["pats"]["items"] = pats_final
    sf["updated"] = _now_utc_iso()

    print(f"  Sox: purged {sox_purged}, added {sox_added}, total now {len(sox_final)}")
    print(f"  Pats: purged {pats_purged}, added {pats_added}, total now {len(pats_final)}")

    result = RefreshResult(
        status="ok",
        sox_purged_count=sox_purged, pats_purged_count=pats_purged,
        sox_added_count=sox_added, pats_added_count=pats_added,
        sox_total_after=len(sox_final), pats_total_after=len(pats_final),
        sox_first_pitch_utc=submission.get("sox_first_pitch_utc", "") or "",
        pats_kickoff_utc=submission.get("pats_kickoff_utc", "") or "",
    )

    if dry_run:
        print(f"[4/4] DRY RUN: skipping save / build / push")
        return result

    print(f"[4/4] Saving + rebuilding HTML + pushing...")
    with json_path.open("w") as f:
        json.dump(data, f, indent=2)

    # Run the build script (also rebuilds sports-feed.json sidecar)
    import subprocess
    script = Path(__file__).parent / "build_dashboard.py"
    canonical_html = repo / "job-search-command-center.html"
    env = os.environ.copy()
    env.setdefault("REAL_HOME", "/home/runner")
    proc = subprocess.run(
        [sys.executable, str(script), str(json_path), str(canonical_html), "--no-publish"],
        capture_output=True, text=True, cwd=str(repo), env=env,
    )
    if proc.returncode != 0:
        return RefreshResult(status="error",
                             reason=f"build_failed: {proc.stderr[:200]}")

    pushed = commit_and_push(
        repo, f"Sports feed refresh {_now_utc_iso()}",
        files=["dashboard-data.json", "index.html",
               "job-search-command-center.html", "sports-feed.json"],
        pull_before_push=True,
    )
    print(f"  {'Pushed' if pushed else 'No changes'}")

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        result = refresh_sports_feed(dry_run=args.dry_run)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\n[refresh-sports] ABORT: {type(e).__name__}: {e}")
        return 1

    print()
    if result.status == "ok":
        print(f"[refresh-sports] OK. Sox: {result.sox_added_count}+/{result.sox_purged_count}- "
              f"= {result.sox_total_after}. Pats: {result.pats_added_count}+/{result.pats_purged_count}- "
              f"= {result.pats_total_after}.")
        return 0
    print(f"[refresh-sports] FAILED: {result.reason}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
