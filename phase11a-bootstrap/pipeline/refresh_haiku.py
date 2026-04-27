"""
Daily haiku + intros + Company-of-the-Day roast refresh.

Runs in GHA daily (noon MDT cron). Calls Claude with web_search to gather
current events, then generates fresh haiku, intro lines, and Company-of-the-
Day roasts in Paul's voice. Writes back to dashboard-data.json + the dashboard
repo's index.html, commits, pushes.

Three Claude API calls in one tool-use response:
  1. Generate 12-15 new haiku (strict 5-7-5)
  2. Refresh 2-3 intro lines
  3. Discover 1-3 new companies + write Bourdain-acidic roasts; refresh 2-3 stale roasts

Touches:
  - dashboard-data.json: adds/updates `haiku` array, `intros` array,
    watch_list[].roast for Company-of-the-Day spotlight
  - index.html: post-processed to swap inline haiku/intros with fresh ones

Cost: ~$0.40 per refresh (Claude Sonnet 4.5 + web_search). Daily so ~$12/month.

Public API:
  refresh_haiku_and_roasts(today=None) -> RefreshResult
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from pipeline.commit_and_push import clone_dashboard, commit_and_push


REFRESH_MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 8000
WEB_SEARCH_MAX_USES = 6
DASHBOARD_REPO_DIR = Path("/tmp/dashboard-haiku")

CONTEXT_DIR = Path(__file__).parent / "context"


def _load_optional(name: str) -> str:
    p = CONTEXT_DIR / name
    return p.read_text() if p.exists() else ""


_STARTUP_CONTEXT = _load_optional("startup_context.md")


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class RefreshResult:
    status: str                     # 'ok' | 'no_changes' | 'error'
    new_haiku: list[str] = field(default_factory=list)
    haiku_removed: list[str] = field(default_factory=list)
    intros_replaced: list[dict] = field(default_factory=list)
    new_companies: list[dict] = field(default_factory=list)
    roasts_refreshed: list[dict] = field(default_factory=list)
    haiku_total_after: int = 0
    intros_total_after: int = 0
    watchlist_total_after: int = 0
    reason: str = ""


# ---------------------------------------------------------------------------
# Syllable counter (rough heuristic)
# ---------------------------------------------------------------------------

_VOWEL_GROUP = re.compile(r"[aeiouy]+", re.IGNORECASE)
_TRAILING_E = re.compile(r"e$", re.IGNORECASE)


def count_syllables(word: str) -> int:
    """Rough syllable count heuristic. Good enough for 5-7-5 validation
    on simple English. Counts vowel groups, subtracts silent trailing e,
    enforces minimum of 1."""
    word = word.strip().lower()
    if not word:
        return 0
    word = re.sub(r"[^a-z]", "", word)
    if not word:
        return 0
    groups = _VOWEL_GROUP.findall(word)
    n = len(groups)
    if word.endswith("e") and n > 1 and not word.endswith(("le", "se", "re")):
        n -= 1
    return max(1, n)


def line_syllables(line: str) -> int:
    return sum(count_syllables(w) for w in re.split(r"\s+", line.strip()) if w)


def is_valid_haiku(text: str, target=(5, 7, 5)) -> tuple[bool, list[int]]:
    """Returns (ok, [syllables_per_line]). Allows ±1 wiggle on each line because
    English syllable counting is hard and Paul's existing haiku also occasionally
    cheat by a syllable for sound."""
    lines = [l for l in text.split("\n") if l.strip()]
    if len(lines) != 3:
        return (False, [line_syllables(l) for l in lines])
    counts = [line_syllables(l) for l in lines]
    ok = all(abs(c - t) <= 1 for c, t in zip(counts, target))
    return (ok, counts)


# ---------------------------------------------------------------------------
# Tool schema for the unified refresh call
# ---------------------------------------------------------------------------

REFRESH_TOOL = {
    "name": "submit_dashboard_refresh",
    "description": (
        "Submit the new haiku, intro lines, Company-of-the-Day roasts, and "
        "discoveries for Paul's dashboard. Call exactly once."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "new_haiku": {
                "type": "array",
                "minItems": 12, "maxItems": 15,
                "description": (
                    "12-15 NEW haiku, strict 5-7-5 syllable count. Format each as a "
                    "single string with newlines between lines (use literal \\n in JSON). "
                    "Voice: Taos/NM ground-sense, telemark skiing, Cormac McCarthy / "
                    "Ed Abbey / Simon Ortiz literary register, Norwegian Arctic memory, "
                    "EO/satellite work, climate/space industry, Sox/Pats interest, "
                    "redhead women + dating, dashboard self-aware humor, current events "
                    "from your web search. Mix in 4-6 absurdly funny ones."
                ),
                "items": {"type": "string"},
            },
            "haiku_to_remove": {
                "type": "array",
                "description": (
                    "8-12 OLDEST or stalest existing haiku to retire. Must match "
                    "EXACT existing text. KEEP timeless favorites about Taos, the "
                    "gorge, McCarthy, Abbey, skiing, Wheeler, the Rio Grande."
                ),
                "items": {"type": "string"},
            },
            "intros_to_replace": {
                "type": "array",
                "minItems": 0, "maxItems": 4,
                "description": "0-3 intro lines to swap. Each item: {old, new}. Skip if all current intros still feel fresh.",
                "items": {
                    "type": "object",
                    "properties": {
                        "old": {"type": "string", "description": "exact existing intro"},
                        "new": {"type": "string", "description": "punchy 5-15 word replacement"},
                    },
                    "required": ["old", "new"],
                },
            },
            "new_companies": {
                "type": "array",
                "minItems": 0, "maxItems": 3,
                "description": "0-3 NEW companies to add to watch_list. Climate-adjacent, EO/maritime/satellite/carbon/MRV. Fresh, not already on dashboard. Each needs a Bourdain-acidic roast.",
                "items": {
                    "type": "object",
                    "properties": {
                        "company": {"type": "string"},
                        "category": {"type": "string", "description": "e.g. 'Carbon Removal / DAC', 'Hyperspectral EO'"},
                        "why": {"type": "string", "description": "one-line serious fit note"},
                        "roast": {"type": "string", "description": "Bourdain-with-two-drinks paragraph: acidic, raw, references Paul's KSAT/Tromso/ENI/carbon/EO/Taos/skiing background, brutally honest about the company. Makes a real case in a funny package. NEVER corporate or generic. NEVER em-dashes."},
                        "careers_url": {"type": "string"},
                    },
                    "required": ["company", "category", "why", "roast", "careers_url"],
                },
            },
            "roasts_to_refresh": {
                "type": "array",
                "minItems": 0, "maxItems": 3,
                "description": "0-3 EXISTING company roasts to rewrite for freshness or news-update. Each: {company, new_roast}.",
                "items": {
                    "type": "object",
                    "properties": {
                        "company": {"type": "string", "description": "exact existing company name in watch_list"},
                        "new_roast": {"type": "string"},
                    },
                    "required": ["company", "new_roast"],
                },
            },
            "current_events_summary": {
                "type": "string",
                "description": "1-2 sentence summary of what current events you wove into the haiku, for the morning brief log.",
            },
        },
        "required": ["new_haiku", "haiku_to_remove", "intros_to_replace", "new_companies", "roasts_to_refresh", "current_events_summary"],
    },
}


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_system_prompt() -> str:
    return f"""\
You are refreshing the personal-section reward content on Paul Whitaker's
Job Search Command Center dashboard. The reward section opens by default
when his Ranked Opportunities is empty (priority on serious work; reward
when the queue is clean).

You produce three things in one tool call:
  1. Fresh haiku (12-15 new, 5-7-5 strict)
  2. Refreshed intro lines (0-3)
  3. Company of the Day roasts (0-3 new companies + 0-3 roast refreshes)

# Voice for the HAIKU

Strict 5-7-5 syllable count per line. Three lines per haiku. Voice:
  - Taos/Northern New Mexico ground-sense (gorge, mesa, Sangre de Cristo,
    pinyon, sage, Wheeler Peak, Rio Grande, monsoon, mud season)
  - Telemark skiing (Taos Ski Valley, Kachina Peak, untracked lines)
  - Literary register: Cormac McCarthy, Ed Abbey, Simon Ortiz
  - Norwegian Arctic memory (Tromso, Svalbard, midnight sun, KSAT ground stations)
  - EO / satellite / climate / space industry from his career
  - Sox / Pats personal interest
  - Redhead women, dating, post-divorce single life
  - Dashboard self-aware humor (the inbox, the ATS, the wire)
  - Current events you found via web_search, woven WITH wit not just
    headlines

Mix in 4-6 that are absurdly funny or deeply Taos-specific. The whole point
is that he refreshes the dashboard many times a day and these surprise him.

# Voice for the ROASTS

Anthony Bourdain reviewing a restaurant, but it's a climate tech company.
Acidic, raw, genuinely funny. Self-deprecating about the job search where
appropriate. References Paul's specific background: KSAT, Tromso, ENI/NOPSEMA
negotiations, GFW commercial licensing program, Planet Labs three-party deal,
ASN subsea infrastructure, carbon markets, satellite data licensing, telemark
skiing, Taos. Brutally honest about the company's business model, funding
stage, market position. But ultimately makes a real case for why Paul should
check them out. NEVER corporate. NEVER generic. NEVER safe. NEVER em-dashes
or en-dashes (banned characters in his system).

# Hard rules (zero tolerance)

  - NO em dashes or en dashes anywhere ("\u2014", "\u2013", " -- ")
  - NO sycophantic openers
  - NO consultant-speak
  - NO "delve", "leverage" (as verb), "passionate", "synergy", or any
    obvious AI tells
  - Strict 5-7-5 on haiku (each line within 1 syllable of target)

# Paul's full context

{_STARTUP_CONTEXT}
"""


def _build_user_prompt(current_haiku: list[str], current_intros: list[str],
                       current_watchlist: list[dict],
                       applied_companies: list[str], today: date,
                       retired_haiku: list[str] | None = None) -> str:
    haiku_sample = "\n\n".join(f"- {h}" for h in current_haiku[:8])
    intros_sample = "\n".join(f"- {i}" for i in current_intros[:8])
    watchlist_companies = ", ".join(w.get("company", "") for w in current_watchlist[:30])

    # Cap retired-haiku context at the most recent 500 to keep the prompt sane
    # (~25k chars). All retired entries remain in dashboard-data.json["retired_haiku"];
    # only the prompt is capped.
    retired_haiku = retired_haiku or []
    retired_recent = retired_haiku[-500:]
    if retired_recent:
        retired_block = "\n\n".join(f"- {h}" for h in retired_recent)
        retired_section = f"""

# PERMANENTLY RETIRED haiku (do NOT regenerate, paraphrase, or echo these)

These haiku have been shown to Paul before and retired. Generating anything
substantially similar to any line below is a hard failure. Different image,
different angle, different specific noun. There are {len(retired_haiku)}
retired in total; the {len(retired_recent)} most recent are listed:

{retired_block}
"""
    else:
        retired_section = ""

    return f"""\
Today is {today.isoformat()}.

# Your job

1. Use web_search to find 3-5 current events from the past 24 hours. Focus on:
   US politics (progressive lens), climate/environment, space and EO news,
   Patriots and Red Sox (check scores, trades, standings if active season),
   New Mexico / Taos news or seasonal happenings, major cultural moments.

2. Generate 12-15 NEW haiku weaving in the current events with wit, plus the
   evergreen Paul-life themes. Each strict 5-7-5. Do NOT echo anything in the
   retired list below.

3. Pick 8-12 EXISTING haiku to retire. Match exact text from the current
   list. KEEP timeless favorites about Taos, the gorge, McCarthy, Abbey,
   skiing, Wheeler, the Rio Grande.

4. Optionally refresh 0-3 intro lines that feel stale.

5. Discover 0-3 NEW climate-tech / EO / carbon / satellite companies for the
   watch_list (use web_search). Avoid companies already on the watch_list and
   avoid companies Paul has already applied to. Write a Bourdain-acidic roast
   for each.

6. Optionally refresh 0-3 EXISTING roasts that feel stale or whose news has
   moved.

# Current state

Haiku count: {len(current_haiku)} (target: maintain 55-65 after refresh).

Sample of current haiku (first 8 of {len(current_haiku)}):

{haiku_sample}

Sample of current intros (first 8 of {len(current_intros)}):

{intros_sample}

Watch list companies (do NOT duplicate; refresh existing roasts if needed):

{watchlist_companies}

Companies Paul has already applied to (do NOT add to watch_list):

{', '.join(applied_companies[:50])}{retired_section}

# Output

Call submit_dashboard_refresh exactly once. Validate your haiku 5-7-5 counts
mentally before submitting (each line within 1 syllable of target).
"""


# ---------------------------------------------------------------------------
# The refresh
# ---------------------------------------------------------------------------

def _call_refresh(client, model: str, current_haiku: list[str], current_intros: list[str],
                  current_watchlist: list[dict], applied_companies: list[str],
                  today: date, retired_haiku: list[str] | None = None) -> dict | None:
    msg = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=_build_system_prompt(),
        tools=[
            {"type": "web_search_20250305", "name": "web_search", "max_uses": WEB_SEARCH_MAX_USES},
            REFRESH_TOOL,
        ],
        tool_choice={"type": "any"},
        messages=[{"role": "user",
                   "content": _build_user_prompt(current_haiku, current_intros,
                                                  current_watchlist, applied_companies, today,
                                                  retired_haiku or [])}],
    )
    # The model might do multiple turns of web_search before submitting.
    # Walk all tool_use blocks; the LAST submit_dashboard_refresh wins.
    submission = None
    for block in msg.content:
        if block.type == "tool_use" and block.name == "submit_dashboard_refresh":
            submission = dict(block.input)
    return submission


def _apply_refresh(data: dict, refresh: dict, today: date) -> RefreshResult:
    """Apply the refresh to the in-memory dashboard data dict."""
    result = RefreshResult(status="ok")

    current_haiku = list(data.get("haiku") or [])
    current_intros = list(data.get("intros") or [])

    # Validate new haiku 5-7-5; drop any that fail
    valid_new = []
    for h in refresh.get("new_haiku", []):
        ok, counts = is_valid_haiku(h)
        if ok:
            valid_new.append(h)
        else:
            print(f"  [reject 5-7-5] counts={counts}: {h[:60]}...")
    result.new_haiku = valid_new

    # Remove the haiku to_remove (only if exact match)
    to_remove_set = set(refresh.get("haiku_to_remove", []))
    kept = [h for h in current_haiku if h not in to_remove_set]
    actually_removed = [h for h in current_haiku if h in to_remove_set]
    result.haiku_removed = actually_removed

    # Archive retired haikus permanently. This list is fed back to Claude on the
    # next refresh as a "do NOT regenerate" reference, and the dashboard uses it
    # via content-hash tracking to ensure Paul never sees the same haiku twice.
    # Also archive any active haiku that already appears in retired (defensive).
    retired_archive = list(data.get("retired_haiku") or [])
    retired_set = set(retired_archive)
    for h in actually_removed:
        if h not in retired_set:
            retired_archive.append(h)
            retired_set.add(h)
    data["retired_haiku"] = retired_archive

    # Combine: kept + valid_new, cap at 65. Drop any new haiku that duplicates
    # a retired one (Claude was instructed not to, but enforce it here).
    valid_new = [h for h in valid_new if h not in retired_set]
    new_haiku = kept + valid_new
    if len(new_haiku) > 65:
        # Drop oldest from the kept portion
        excess = len(new_haiku) - 65
        new_haiku = new_haiku[excess:]
    elif len(new_haiku) < 50:
        # If we ended up under 50 because too many got rejected, fall back to keeping all current
        print(f"  WARN: only {len(new_haiku)} haiku after refresh, restoring all current to maintain min 50")
        new_haiku = current_haiku + valid_new
    data["haiku"] = new_haiku

    # Apply intro replacements
    for swap in refresh.get("intros_to_replace", []):
        old, new = swap.get("old", ""), swap.get("new", "")
        if old in current_intros:
            i = current_intros.index(old)
            current_intros[i] = new
            result.intros_replaced.append({"old": old, "new": new})
    data["intros"] = current_intros

    # Add new companies to watch_list
    watchlist = list(data.get("watch_list") or [])
    existing_names = {w.get("company", "").lower() for w in watchlist}
    for newco in refresh.get("new_companies", []):
        if newco.get("company", "").lower() in existing_names:
            continue
        watchlist.append({
            "company": newco["company"],
            "category": newco["category"],
            "why": newco["why"],
            "roast": newco["roast"],
            "careers_url": newco["careers_url"],
        })
        result.new_companies.append({"company": newco["company"], "category": newco["category"]})

    # Refresh roasts
    for upd in refresh.get("roasts_to_refresh", []):
        co_name = upd.get("company", "").lower()
        for entry in watchlist:
            if entry.get("company", "").lower() == co_name:
                entry["roast"] = upd["new_roast"]
                result.roasts_refreshed.append({"company": entry["company"]})
                break

    # Cap watch_list at 35
    if len(watchlist) > 35:
        watchlist = watchlist[-35:]
    data["watch_list"] = watchlist

    result.haiku_total_after = len(data["haiku"])
    result.intros_total_after = len(data["intros"])
    result.watchlist_total_after = len(data["watch_list"])
    return result


# ---------------------------------------------------------------------------
# HTML post-processing: inject fresh haiku/intros into rendered index.html
# ---------------------------------------------------------------------------

_HAIKU_BLOCK_RE = re.compile(r'(const haiku\s*=\s*\[)[^\]]*?(\];)', re.DOTALL)
_INTROS_BLOCK_RE = re.compile(r'(const intros\s*=\s*\[)[^\]]*?(\];)', re.DOTALL)


def _format_js_array(items: list[str]) -> str:
    """Format a Python list of strings as a JS array literal (one per line)."""
    parts = []
    for it in items:
        # Convert real newlines in haiku to JS \n escapes; escape quotes and backslashes
        escaped = it.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        parts.append(f'    "{escaped}"')
    return "\n" + ",\n".join(parts) + "\n  "


def inject_into_html(html_path: Path, haiku: list[str], intros: list[str]) -> None:
    html = html_path.read_text()
    if haiku:
        html = _HAIKU_BLOCK_RE.sub(
            lambda m: m.group(1) + _format_js_array(haiku) + m.group(2),
            html, count=1,
        )
    if intros:
        html = _INTROS_BLOCK_RE.sub(
            lambda m: m.group(1) + _format_js_array(intros) + m.group(2),
            html, count=1,
        )
    html_path.write_text(html)


# ---------------------------------------------------------------------------
# Build script invoker (same pattern as morning brief)
# ---------------------------------------------------------------------------

def _run_build_script(repo: Path) -> None:
    json_path = repo / "dashboard-data.json"
    canonical_html = repo / "job-search-command-center.html"
    script = Path(__file__).parent / "build_dashboard.py"
    env = os.environ.copy()
    env.setdefault("REAL_HOME", "/home/runner")
    result = subprocess.run(
        [sys.executable, str(script), str(json_path), str(canonical_html), "--no-publish"],
        capture_output=True, text=True, cwd=str(repo), env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"build_dashboard.py failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
    print(f"  build: {result.stdout.strip()[:160]}")


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def refresh_haiku_and_roasts(today: date | None = None, anthropic_client=None,
                              dry_run: bool = False) -> RefreshResult:
    """Daily refresh entry point. Clones dashboard, calls Claude, writes back, pushes."""
    if today is None:
        today = date.today()

    if anthropic_client is None:
        import anthropic
        anthropic_client = anthropic.Anthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY", "").strip()
        )

    print(f"[refresh-haiku] Run for {today.isoformat()}")

    # ---- Clone ----
    print(f"[1/5] Cloning dashboard repo...")
    repo = clone_dashboard(DASHBOARD_REPO_DIR)
    json_path = repo / "dashboard-data.json"
    with json_path.open() as f:
        data = json.load(f)

    current_haiku = list(data.get("haiku") or [])
    current_intros = list(data.get("intros") or [])
    current_watchlist = list(data.get("watch_list") or [])
    applied = [a.get("company", "") for a in data.get("applications", [])]
    retired = list(data.get("retired_haiku") or [])
    print(f"  Loaded: {len(current_haiku)} haiku, {len(current_intros)} intros, "
          f"{len(current_watchlist)} watch_list, {len(applied)} applications, "
          f"{len(retired)} retired_haiku")

    # If haiku/intros aren't yet seeded into dashboard-data.json, bootstrap
    # from the seed file in this repo.
    if not current_haiku or not current_intros:
        seed_path = CONTEXT_DIR / "dashboard-haiku.json"
        if seed_path.exists():
            with seed_path.open() as f:
                seed = json.load(f)
            if not current_haiku:
                current_haiku = seed.get("haiku", [])
                data["haiku"] = current_haiku
                print(f"  Seeded {len(current_haiku)} haiku from sidecar")
            if not current_intros:
                current_intros = seed.get("intros", [])
                data["intros"] = current_intros
                print(f"  Seeded {len(current_intros)} intros from sidecar")

    # ---- Call Claude ----
    print(f"[2/5] Calling Claude (web_search + generate)...")
    submission = _call_refresh(
        anthropic_client, REFRESH_MODEL,
        current_haiku, current_intros, current_watchlist, applied, today,
        retired_haiku=retired,
    )
    if submission is None:
        return RefreshResult(status="error", reason="no_tool_call_returned")
    print(f"  Got submission: {len(submission.get('new_haiku', []))} new haiku, "
          f"{len(submission.get('haiku_to_remove', []))} to remove, "
          f"{len(submission.get('new_companies', []))} new companies, "
          f"{len(submission.get('roasts_to_refresh', []))} roast refreshes.")
    print(f"  Current events woven: {submission.get('current_events_summary', '')[:200]}")

    # ---- Apply ----
    print(f"[3/5] Applying refresh to dashboard data...")
    result = _apply_refresh(data, submission, today)
    print(f"  After: {result.haiku_total_after} haiku, {result.intros_total_after} intros, "
          f"{result.watchlist_total_after} watch_list")

    # ---- Save + rebuild ----
    if dry_run:
        print(f"[4/5] DRY RUN: skipping save / build / push.")
        return result

    print(f"[4/5] Saving dashboard-data.json + rebuilding HTML...")
    with json_path.open("w") as f:
        json.dump(data, f, indent=2)
    _run_build_script(repo)
    inject_into_html(repo / "index.html", data["haiku"], data["intros"])
    inject_into_html(repo / "job-search-command-center.html", data["haiku"], data["intros"])

    # ---- Push ----
    print(f"[5/5] Committing + pushing...")
    pushed = commit_and_push(
        repo,
        f"Daily haiku + roast refresh {today.isoformat()}",
        files=["dashboard-data.json", "index.html",
               "job-search-command-center.html", "sports-feed.json"],
        pull_before_push=True,
    )
    if pushed:
        print(f"  Pushed.")
    else:
        print(f"  No changes to push.")

    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        result = refresh_haiku_and_roasts(dry_run=args.dry_run)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\n[refresh-haiku] ABORT: {type(e).__name__}: {e}")
        return 1

    print()
    if result.status == "ok":
        print(f"[refresh-haiku] Complete. {len(result.new_haiku)} new haiku, "
              f"{len(result.haiku_removed)} retired, "
              f"{len(result.new_companies)} new companies, "
              f"{len(result.roasts_refreshed)} roast refreshes.")
        return 0
    print(f"[refresh-haiku] FAILED: {result.reason}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
