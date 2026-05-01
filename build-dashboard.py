#!/usr/bin/env python3
"""
Build the Job Search Command Center HTML from dashboard-data.json.
Called by: morning deep dive scheduled task, /job-evaluate skill, or manually.
Usage: python3 build-dashboard.py [path-to-json] [path-to-output-html]
Defaults: ./dashboard-data.json -> ./job-search-command-center.html
"""
import json, sys, os, subprocess, shutil
from pathlib import Path
from datetime import datetime, timedelta, timezone


def _next_cron_fire(now: datetime, day_pattern, hour: int, minute: int = 0) -> datetime:
    """Return the next datetime after `now` matching the given cron pattern.

    day_pattern: list of valid day-of-month values (1-31), or None for daily.
    hour, minute: UTC hour/minute the cron fires.

    Doesn't try to be a full cron parser. Handles the patterns we actually use:
      - daily (day_pattern=None) for sports/morning brief
      - day_pattern=[1, 22] for `*/21 * *` (personal feeds, ~3-week cadence)
      - day_pattern=list(range(1,32,3)) for `*/3 * *` (haiku, every 3 days)
    """
    candidates = []
    for offset in range(0, 90):
        d = now + timedelta(days=offset)
        try:
            candidate = d.replace(hour=hour, minute=minute, second=0, microsecond=0)
        except ValueError:
            continue
        if candidate <= now:
            continue
        if day_pattern is None or candidate.day in day_pattern:
            return candidate
    raise ValueError("no candidate found within 90 days")


def _format_next_fire(dt: datetime) -> str:
    """Format a UTC datetime as a short human-readable date for the dashboard tag."""
    return dt.strftime("%b %-d") if hasattr(dt, "strftime") else str(dt)


def compute_next_refresh_strings(now=None) -> dict:
    """Pre-compute the 'next refresh' display string for each feed cadence.

    Returns dict keyed by feed name. Values are strings like 'May 1'.
    Used by the build to inject into JS / HTML so users see when fresh content
    arrives, without anyone needing to look up cron expressions.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    haiku = _next_cron_fire(now, list(range(1, 32, 3)), hour=18, minute=0)
    personal = _next_cron_fire(now, [1, 22], hour=19, minute=0)
    return {
        "haiku":    _format_next_fire(haiku),
        "industry": _format_next_fire(personal),
        "outdoor":  _format_next_fire(personal),
        "recipe":   _format_next_fire(personal),
    }


def resolve_path(p):
    """Convert ~/... paths to file:// URLs for browser linking."""
    if not p: return None
    # Expand ~ to the real user home (may be overridden in sandbox)
    home = os.environ.get("REAL_HOME", str(Path.home()))
    expanded = p.replace("~/", home + "/") if p.startswith("~/") else p
    return "file://" + expanded

def load_data(json_path):
    with open(json_path) as f:
        return json.load(f)

def is_new(added_date_str):
    if not added_date_str:
        return False
    try:
        added = datetime.strptime(added_date_str, "%Y-%m-%d")
        return (datetime.now() - added).days <= 2
    except:
        return False

def score_color(score):
    if score is None: return "var(--text-muted)"
    if score >= 75: return "var(--green)"
    if score >= 60: return "var(--amber)"
    return "var(--text-muted)"

def pill(text, cls):
    return f'<span class="pill pill-{cls}">{text}</span>'

def fit_bar(fit):
    pct = fit * 10
    color = "var(--green)" if fit >= 8 else "var(--amber)" if fit >= 6 else "var(--red)"
    return f'<div class="fit-bar"><div class="bar"><div class="bar-fill" style="width:{pct}%;background:{color}"></div></div> {fit}</div>'

def build_ranked_cards(opportunities):
    cards = []
    for i, d in enumerate(opportunities):
        new_badge = '<span class="new-badge">NEW</span>' if (d.get("is_new") or is_new(d.get("added"))) else ""
        has_dd = d.get("has_deep_dive", False)

        # Score display
        eff = d.get("effective_score") or d.get("score")
        if eff:
            score_display = f'{eff}/100'
            score_c = score_color(eff)
        else:
            score_display = "—"
            score_c = "var(--text-muted)"

        # Deep dive badge
        dd_badge = pill("Deep Dive", "purple") if has_dd else pill("Scored", "muted")

        # Domain + location line
        meta_parts = []
        if d.get("domain"):
            meta_parts.append(d["domain"])
        if d.get("location"):
            meta_parts.append(d["location"])
        meta_line = f'<div class="meta-line">{" · ".join(meta_parts)}</div>' if meta_parts else ""

        # Blocker tags (geographic residency, work auth, clearance, language, narrow experience)
        blockers = d.get("blockers") or []
        if blockers:
            tags = []
            for b in blockers:
                if isinstance(b, dict):
                    btype = b.get("type", "blocker").replace("_", " ")
                    bdetail = b.get("detail", "")
                    bsev = b.get("severity", "hard")
                    cls = "blocker-tag-hard" if bsev == "hard" else "blocker-tag-soft"
                    label = btype.upper()
                    tags.append(f'<span class="blocker-tag {cls}" title="{bdetail}">&#9888; {label}</span>')
                else:
                    # Fallback for simple string blockers
                    tags.append(f'<span class="blocker-tag blocker-tag-hard">&#9888; {b}</span>')
            blockers_html = f'<div class="blockers-row">{"".join(tags)}</div>'
        else:
            blockers_html = ""

        links_html = ""
        if d.get("job_urls"):
            for j, url in enumerate(d.get("job_urls", [])):
                label = "Job Posting" if len(d.get("job_urls", [])) == 1 else f"Job {j+1}"
                links_html += f'<a href="{url}" target="_blank" rel="noopener">{label}</a> '
        else:
            links_html += '<span class="doc-missing">No posting link yet</span> '
        if d.get("resume_path"):
            rpath = d["resume_path"].replace("~", "/Users/paulwhitaker")
            links_html += f'<a href="#" class="copy-path-link" onclick="copyFilePath(this, \'{rpath.replace(chr(39), chr(92)+chr(39))}\'); return false;">Resume</a> '
        if d.get("cover_letter_path"):
            cpath = d["cover_letter_path"].replace("~", "/Users/paulwhitaker")
            links_html += f'<a href="#" class="copy-path-link" onclick="copyFilePath(this, \'{cpath.replace(chr(39), chr(92)+chr(39))}\'); return false;">Cover Letter</a> '
        if d.get("essay_path"):
            epath = d["essay_path"].replace("~", "/Users/paulwhitaker")
            links_html += f'<a href="#" class="copy-path-link" onclick="copyFilePath(this, \'{epath.replace(chr(39), chr(92)+chr(39))}\'); return false;">Essay</a> '
        if d.get("doc_path"):
            dpath = d["doc_path"].replace("~", "/Users/paulwhitaker")
            links_html += f'<a href="#" class="copy-path-link" onclick="copyFilePath(this, \'{dpath.replace(chr(39), chr(92)+chr(39))}\'); return false;">Deep Dive Doc</a> '

        dismiss_btn = f'<button class="dismiss-btn" onclick="dismissCard(this, \'{d["company"].replace(chr(39), chr(92)+chr(39))}\')" title="Remove from active list">&times;</button>'

        current_status = d.get("status", "not_applied")
        status_options = [
            ("not_applied", "Not Applied"),
            ("applied", "Applied"),
            ("awaiting", "Awaiting Response"),
            ("1st_interview_scheduled", "1st Interview Scheduled"),
            ("1st_interview_held", "1st Interview Held"),
            ("2nd_interview_scheduled", "2nd Interview Scheduled"),
            ("2nd_interview_held", "2nd Interview Held"),
            ("3rd_interview_scheduled", "3rd Interview Scheduled"),
            ("3rd_interview_held", "3rd Interview Held"),
            ("final_round_scheduled", "Final Round Scheduled"),
            ("final_round_held", "Final Round Held"),
            ("offer", "Offer"),
            ("cold_outreach", "Cold Outreach"),
            ("rejected", "Rejected"),
            ("pass", "Pass"),
        ]
        select_opts = "".join(f'<option value="{v}"{" selected" if v == current_status else ""}>{lbl}</option>' for v, lbl in status_options)
        status_html = f'<select class="status-select" onchange="changeStatus(this, \'{d["company"].replace(chr(39), chr(92)+chr(39))}\')">{select_opts}</select>'

        cards.append(f'''
  <div class="dd-card{" dd-new" if new_badge else ""}" data-company="{d["company"]}" data-status="{current_status}">
    <div class="rank">#{i+1}</div>
    {new_badge}
    {dismiss_btn}
    <div class="company">{d["company"]}</div>
    <div class="role">{d["role"]}</div>
    {meta_line}
    {blockers_html}
    <div class="score-row">
      <span style="color:{score_c}">Score: {score_display}</span>
      <span>Fit: {d.get("fit","—")}/10</span>
      {dd_badge}
    </div>
    <div class="verdict">{d.get("verdict","")}</div>
    <div class="links">{links_html}</div>
    <div style="margin-top:6px">{status_html}</div>
  </div>''')
    return "\n".join(cards)

def build_app_rows(apps, include=None):
    """Render application rows. include=None shows all; 'active' excludes rejected/filled/retired;
    'closed' shows only rejected/filled; 'retired' shows only retired."""
    if include == 'active':
        apps = [a for a in apps if a.get('status') not in ('rejected', 'filled', 'retired')]
    elif include == 'closed':
        apps = [a for a in apps if a.get('status') in ('rejected', 'filled')]
    elif include == 'retired':
        apps = [a for a in apps if a.get('status') == 'retired']
    status_order = {
        "offer": 0,
        "final_round_held": 1,
        "final_round_scheduled": 2,
        "3rd_interview_held": 3,
        "3rd_interview_scheduled": 4,
        "2nd_interview_held": 5,
        "2nd_interview_scheduled": 6,
        "1st_interview_held": 7,
        "1st_interview_scheduled": 8,
        # Legacy aliases (treated as held for sort purposes)
        "2nd_interview": 5,
        "1st_interview": 7,
        "awaiting": 9,
        "applied": 10,
        "rejected": 11,
        "filled": 12,
        "retired": 12,
        "pass": 13,
    }
    if include == 'closed':
        # For the closed table, sort by most recent applied date first (most recent rejection at top)
        apps = sorted(apps, key=lambda a: a.get("applied", ""), reverse=True)
    else:
        # Sort by status category first, then by descending score within each category
        apps = sorted(apps, key=lambda a: (status_order.get(a.get("status", ""), 99), -(a.get("score") or 0)))
    rows = []
    for a in apps:
        opacity = ' style="opacity:0.5"' if a["status"] in ("rejected","filled") else ""
        status_map = {
            "offer": ("Offer", "green"),
            "final_round_held": ("Final Round Held", "green"),
            "final_round_scheduled": ("Final Round Scheduled", "green"),
            "3rd_interview_held": ("3rd Interview Held", "cyan"),
            "3rd_interview_scheduled": ("3rd Interview Scheduled", "cyan"),
            "2nd_interview_held": ("2nd Interview Held", "cyan"),
            "2nd_interview_scheduled": ("2nd Interview Scheduled", "cyan"),
            "1st_interview_held": ("1st Interview Held", "cyan"),
            "1st_interview_scheduled": ("1st Interview Scheduled", "cyan"),
            "awaiting": ("Awaiting", "amber"),
            "applied": ("Applied", "amber"),
            "rejected": ("Rejected", "muted"),
            "filled": ("Filled", "muted"),
            "retired": ("Retired", "muted"),
            "pass": ("Pass", "muted"),
            "speculative": ("Speculative", "blue"),
            "cold_outreach": ("Speculative", "blue"),
            # Legacy aliases
            "1st_interview": ("1st Interview", "cyan"),
            "2nd_interview": ("2nd Interview", "cyan"),
        }
        st_text, st_cls = status_map.get(a["status"], ("—","muted"))
        # Score column: the score the opportunity had when Paul applied
        score = a.get("score")
        if score:
            score_cls = "green" if score >= 75 else "amber" if score >= 60 else "muted"
            score_col = pill(str(score), score_cls)
        else:
            score_col = pill("—", "muted")
        # Applied date and Days column (days computed live via JS)
        applied_str = a.get("applied", "")
        followed_up = a.get("followed_up") or a.get("follow_up_sent") or ""
        applied_col = applied_str or "—"
        if applied_str:
            fu_attr = f' data-followed-up="{followed_up}"' if followed_up else ""
            days_col = f'<span class="days-since" data-applied="{applied_str}" data-status="{a["status"]}"{fu_attr}>—</span>'
        else:
            days_col = "—"
        # Link column: real URL from job_url field (only real verified URLs)
        job_url = a.get("job_url")
        link_col = f'<a href="{job_url}" target="_blank" style="color:var(--cyan);text-decoration:none">View</a>' if job_url else "—"
        rows.append(f'''    <tr{opacity}>
      <td class="company-name">{a["company"]}</td><td>{a["role"]}</td><td>{score_col}</td><td>{applied_col}</td><td>{days_col}</td>
      <td>{a["domain"]}</td><td>{a["location"]}</td><td>{a["comp"]}</td>
      <td>{pill(st_text, st_cls)}</td><td>{link_col}</td><td class="next-action">{a["next_action"]}</td>
    </tr>''')
    return "\n".join(rows)

def build_pipeline_rows(items):
    """Build pipeline table rows from ranked_opportunity entries.

    Rows carry data-sort attributes so the client-side table-sort JS can
    sort by the raw value (number, ISO date string, lowercased text) rather
    than by the rendered cell contents (which include HTML for fit bars,
    score pills, etc).
    """
    rows = []
    for i, p in enumerate(items):
        score = p.get("effective_score") or p.get("score")
        score_color_cls = "green" if score and score >= 75 else "amber" if score and score >= 60 else "muted"
        score_col = f'<td data-sort="{score or 0}">{pill(str(score), score_color_cls)}</td>' if score else f'<td data-sort="0">{pill("—", "muted")}</td>'
        verdict_short = (p.get("hook") or p.get("verdict") or "")[:80]
        job_urls = p.get("job_urls") or []
        job_url = job_urls[0] if job_urls else None
        link_col = f'<a href="{job_url}" target="_blank" style="color:var(--cyan);text-decoration:none">Apply</a>' if job_url else "—"
        added = p.get("added") or p.get("date") or ""
        fit_val = p.get("fit") or 0
        company = p.get("company", "")
        role = p.get("role", "")
        domain = p.get("domain", "")
        location = p.get("location", "")
        rows.append(f'''    <tr><td data-sort="{i+1}">{i+1}</td><td class="company-name" data-sort="{company.lower()}">{company}</td><td data-sort="{role.lower()}">{role}</td><td data-sort="{fit_val}">{fit_bar(p["fit"])}</td>{score_col}<td data-sort="{added}">{added}</td><td data-sort="{domain.lower()}">{domain}</td><td data-sort="{location.lower()}">{location}</td><td>{link_col}</td><td class="next-action">{verdict_short}</td></tr>''')
    return "\n".join(rows)

def compute_stat_cards(data):
    """Build stat cards dynamically from the actual data."""
    apps = data.get("applications", [])
    ranked = data.get("ranked_opportunities", [])

    # Worth Applying: ranked entries with pursue/pursue_with_caveats, not yet applied, Tier 1 & 2 only (score 60+)
    waiting_app = [d for d in ranked if d.get("recommendation") in ("pursue", "pursue_with_caveats") and d.get("status") == "not_applied" and (d.get("effective_score") or 0) >= 60]
    # Sent: applications with any status (total sent)
    sent = [a for a in apps if a.get("applied")]
    # Active Interviews
    active_interviews = [a for a in apps if a.get("status") in ("1st_interview_scheduled", "1st_interview_held", "2nd_interview_scheduled", "2nd_interview_held", "3rd_interview_scheduled", "3rd_interview_held", "final_round_scheduled", "final_round_held", "1st_interview", "2nd_interview")]
    # Awaiting Response
    awaiting = [a for a in apps if a.get("status") == "awaiting"]
    # Rejected / Closed
    rejected = [a for a in apps if a.get("status") in ("rejected", "filled")]

    def names(items, key="company"):
        return [item.get(key, "?") for item in items]

    return [
        {"number": len(waiting_app), "label": "Worth Applying", "color": "var(--amber)", "names": names(waiting_app)},
        {"number": len(sent), "label": "Sent", "color": "var(--green)", "names": names(sent)},
        {"number": len(active_interviews), "label": "Active Interviews", "color": "var(--cyan)", "names": names(active_interviews)},
        {"number": len(awaiting), "label": "Awaiting Response", "color": "var(--blue)", "names": names(awaiting)},
        {"number": len(rejected), "label": "Rejected / Closed", "color": "var(--text-muted)", "names": names(rejected)},
    ]

def build_stat_cards_html(stat_cards):
    html = ""
    for sc in stat_cards:
        tooltip_items = "".join(f'<div class="tt-item">{n}</div>' for n in sc["names"]) if sc["names"] else '<div class="tt-empty">None</div>'
        html += f'''  <div class="stat-card">
    <div class="number" style="color:{sc["color"]}">{sc["number"]}</div>
    <div class="label">{sc["label"]}</div>
    <div class="tooltip">{tooltip_items}</div>
  </div>\n'''
    return html


def compute_cost_summary(repo_dir=None):
    """Read cost-feed.json (from cwd or repo_dir). Return None if missing."""
    import json as _cost_json
    import pathlib as _cost_path
    base = _cost_path.Path(repo_dir) if repo_dir else _cost_path.Path(".")
    p = base / "cost-feed.json"
    if not p.exists():
        return None
    try:
        return _cost_json.loads(p.read_text())
    except Exception:
        return None


def build_cost_section_html(summary):
    """Build the Pipeline Cost <details> section. Empty-state aware."""
    if not summary:
        return (
            '''<details>
<summary class="section-header">Pipeline Cost <span class="badge pill-muted" style="font-size:10px;">monitoring active</span></summary>
<p style="color:var(--text-muted); font-size:14px; margin:10px 0;">Cost monitoring is wired. After workflow runs and the Sunday rollup fires, this populates with weekly totals.</p>
</details>'''
        )

    this_week = summary.get("this_week", {}) or {}
    weekly = summary.get("weekly", []) or []
    by_workflow_4w = summary.get("by_workflow_4w", {}) or {}
    updated = summary.get("updated", "")

    week_total = float(this_week.get("total_usd", 0) or 0)
    week_calls = int(this_week.get("calls", 0) or 0)
    week_in = int(this_week.get("tokens_in", 0) or 0)
    week_out = int(this_week.get("tokens_out", 0) or 0)

    if week_calls == 0 and not weekly:
        return (
            f'''<details>
<summary class="section-header">Pipeline Cost <span class="badge pill-muted" style="font-size:10px;">$0.00 this week</span></summary>
<p style="color:var(--text-muted); font-size:14px; margin:10px 0;">No API calls logged this week yet.</p>
<p style="color:var(--text-muted); font-size:11px;">Last updated {updated}</p>
</details>'''
        )

    weekly_chrono = list(reversed(weekly))[-12:]
    if not weekly_chrono:
        weekly_chrono = [{"week_start": "?", "total_usd": 0}]
    max_usd = max((float(w.get("total_usd", 0) or 0) for w in weekly_chrono), default=1) or 1
    n = len(weekly_chrono)
    sparkline_w, sparkline_h = 220, 50
    points = []
    for i, w in enumerate(weekly_chrono):
        x = (i / max(n - 1, 1)) * sparkline_w
        v = float(w.get("total_usd", 0) or 0)
        y = sparkline_h - (v / max_usd) * (sparkline_h - 4) - 2
        points.append(f"{x:.1f},{y:.1f}")
    sparkline = " ".join(points)

    workflow_rows = ""
    for wf, total in sorted(by_workflow_4w.items(), key=lambda x: -float(x[1] or 0)):
        workflow_rows += f'    <tr><td>{wf}</td><td style="text-align:right;">${float(total or 0):.2f}</td></tr>\n'
    if not workflow_rows:
        workflow_rows = '    <tr><td colspan="2" style="color:var(--text-muted);">No data in past 4 weeks.</td></tr>\n'

    first_week = weekly_chrono[0].get("week_start", "")
    last_week = weekly_chrono[-1].get("week_start", "")

    return (
        f'''<details>
<summary class="section-header">Pipeline Cost <span class="badge pill-muted" style="font-size:10px;">${week_total:.2f} this week</span></summary>
<div style="display:grid; grid-template-columns: 1fr 2fr; gap:14px; margin-top:14px;">
  <div style="background:var(--card); border:1px solid var(--border); border-radius:8px; padding:16px;">
    <div style="font-size:11px; text-transform:uppercase; letter-spacing:0.08em; color:var(--text-muted); margin-bottom:8px;">This week</div>
    <div style="font-size:30px; font-weight:700; color:var(--text); line-height:1;">${week_total:.2f}</div>
    <div style="font-size:12px; color:var(--text-muted); margin-top:6px;">{week_calls} calls &middot; {week_in:,} in / {week_out:,} out tokens</div>
  </div>
  <div style="background:var(--card); border:1px solid var(--border); border-radius:8px; padding:16px;">
    <div style="font-size:11px; text-transform:uppercase; letter-spacing:0.08em; color:var(--text-muted); margin-bottom:8px;">12-week trend</div>
    <svg viewBox="0 0 {sparkline_w} {sparkline_h}" width="100%" height="{sparkline_h}" style="display:block;">
      <polyline points="{sparkline}" stroke="#6366f1" fill="none" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
    </svg>
    <div style="display:flex; justify-content:space-between; font-size:10px; color:var(--text-muted); margin-top:4px;">
      <span>{first_week}</span>
      <span>{last_week}</span>
    </div>
  </div>
</div>
<div style="margin-top:16px;">
  <div style="font-size:13px; font-weight:600; color:var(--text); margin-bottom:8px;">4-week totals by workflow</div>
  <div class="table-wrapper">
    <table>
      <thead><tr><th>Workflow</th><th style="text-align:right;">4-week total</th></tr></thead>
      <tbody>
{workflow_rows}      </tbody>
    </table>
  </div>
</div>
<div style="font-size:11px; color:var(--text-muted); margin-top:10px;">Last updated {updated}</div>
</details>'''
    )


def compute_stats(data):
    """Derive all stats from the actual data — no hardcoded values."""
    apps = data.get("applications", [])
    ranked = data.get("ranked_opportunities", [])
    archived = data.get("archived_deep_dives", [])

    applications_sent = len(apps)
    awaiting_response = len([a for a in apps if a.get("status") == "awaiting"])
    active_interviews = len([a for a in apps if a.get("status") in ("1st_interview_scheduled", "1st_interview_held", "2nd_interview_scheduled", "2nd_interview_held", "3rd_interview_scheduled", "3rd_interview_held", "final_round_scheduled", "final_round_held", "1st_interview", "2nd_interview")])
    rejected_closed = len([a for a in apps if a.get("status") in ("rejected", "filled")])
    retired = len([a for a in apps if a.get("status") == "retired"])
    active_pipeline = len(ranked)
    deep_dives_done = len([r for r in ranked if r.get("doc_path")]) + len([a for a in archived if a.get("doc_path")])
    resumes_built = len(set(r.get("company") for r in ranked if r.get("resume_path")))

    return {
        "applications_sent": applications_sent,
        "awaiting_response": awaiting_response,
        "active_interviews": active_interviews,
        "rejected_closed": rejected_closed,
        "retired": retired,
        "active_pipeline": active_pipeline,
        "deep_dives_done": deep_dives_done,
        "resumes_built": resumes_built,
    }

import re as _re

def parse_interview_datetime(text):
    """Parse a future interview datetime from next_action text like
    '1st Interview Tue Apr 21, 2:00-2:45 PM MDT'. Returns naive datetime in Taos local time."""
    if not text:
        return None
    months = {'Jan':1,'Feb':2,'Mar':3,'Apr':4,'May':5,'Jun':6,
              'Jul':7,'Aug':8,'Sep':9,'Oct':10,'Nov':11,'Dec':12}
    m = _re.search(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+(\d{1,2})', text)
    if not m:
        return None
    month = months[m.group(1)]
    day = int(m.group(2))
    tm = _re.search(r'(\d{1,2}):(\d{2})\s*(?:-\s*\d{1,2}:\d{2})?\s*(AM|PM|am|pm)', text)
    hour, minute = 10, 0
    if tm:
        hour = int(tm.group(1)); minute = int(tm.group(2))
        ampm = tm.group(3).upper()
        if ampm == 'PM' and hour < 12: hour += 12
        elif ampm == 'AM' and hour == 12: hour = 0
    now = datetime.now()
    year = now.year
    try:
        dt = datetime(year, month, day, hour, minute)
    except ValueError:
        return None
    if (now - dt).days > 30:
        dt = dt.replace(year=year + 1)
    return dt

def extract_interviewers(text):
    """Extract likely interviewer names (First Last [Last]) from next_action text."""
    if not text:
        return []
    month_prefixes = ('Jan ','Feb ','Mar ','Apr ','May ','Jun ','Jul ','Aug ','Sep ','Oct ','Nov ','Dec ')
    names = _re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b', text)
    out = []
    skip_words = {'1st Interview','2nd Interview','Chief Staff','Zoom Princeton','New Jersey','New Mexico'}
    for n in names:
        if any(n.startswith(p) for p in month_prefixes):
            continue
        if n in skip_words:
            continue
        if n not in out:
            out.append(n)
    return out

def get_interviews(apps):
    """Apps in interview status, enriched with parsed dt + interviewers, sorted by imminence."""
    ivs = []
    for a in apps:
        if a.get('status') not in ('1st_interview_scheduled','1st_interview_held','2nd_interview_scheduled','2nd_interview_held','3rd_interview_scheduled','3rd_interview_held','final_round_scheduled','final_round_held','1st_interview','2nd_interview'):
            continue
        dt = parse_interview_datetime(a.get('next_action'))
        ivs.append({**a, '_parsed_dt': dt, '_interviewers': extract_interviewers(a.get('next_action',''))})
    def sort_key(iv):
        dt = iv['_parsed_dt']
        now = datetime.now()
        if dt is None: return (1, datetime.max)
        if dt < now: return (2, now - dt)
        return (0, dt)
    ivs.sort(key=sort_key)
    return ivs

def build_next_interview_banner(interviews):
    """Top banner for the most imminent upcoming interview with a live countdown."""
    upcoming = [iv for iv in interviews if iv['_parsed_dt'] and iv['_parsed_dt'] > datetime.now()]
    if not upcoming:
        return ""
    iv = upcoming[0]
    dt = iv['_parsed_dt']
    iso = dt.strftime('%Y-%m-%dT%H:%M:%S')
    display = dt.strftime('%a %b %-d, %-I:%M %p') + ' MDT'
    company = iv['company']
    role = iv.get('role','')
    job_url = iv.get('job_url','#')
    people = ' &middot; '.join(iv['_interviewers']) if iv['_interviewers'] else 'Interviewer TBD'
    return f'''<div class="interview-banner">
  <div class="ib-left">
    <div class="ib-label">NEXT INTERVIEW</div>
    <div class="ib-company">{company}</div>
    <div class="ib-role">{role}</div>
  </div>
  <div class="ib-mid">
    <div class="ib-countdown" data-deadline="{iso}">calculating&hellip;</div>
    <div class="ib-time">{display}</div>
    <div class="ib-people">{people}</div>
  </div>
  <div class="ib-right">
    <a href="{job_url}" target="_blank" class="ib-link">Job Post &rarr;</a>
  </div>
</div>'''

def build_interview_prep_cards(interviews):
    """Row of interview prep cards — ONLY for interviews with a confirmed future datetime."""
    now = datetime.now()
    scheduled = [iv for iv in interviews if iv['_parsed_dt'] and iv['_parsed_dt'] > now]
    if not scheduled:
        return ""
    cards = ""
    for iv in scheduled:
        dt = iv['_parsed_dt']
        delta = dt - now
        days = delta.days; hrs = delta.seconds // 3600
        in_str = f'in {days}d {hrs}h' if days > 0 else f'in {hrs}h {(delta.seconds % 3600)//60}m'
        date_str = f'<span class="ip-upcoming">{dt.strftime("%a %b %-d, %-I:%M %p")} &middot; {in_str}</span>'
        s = iv.get('status', '')
        if s.startswith('1st_interview'):
            stage = '1st Round'
        elif s.startswith('2nd_interview'):
            stage = '2nd Round'
        elif s.startswith('3rd_interview'):
            stage = '3rd Round'
        elif s.startswith('final_round'):
            stage = 'Final Round'
        else:
            stage = 'Interview'
        people_html = ''.join(f'<span class="ip-person">{n}</span>' for n in iv['_interviewers']) if iv['_interviewers'] else '<span class="ip-tbd">TBD</span>'
        next_action = (iv.get('next_action','') or '')
        if len(next_action) > 280:
            next_action = next_action[:277] + '&hellip;'
        company = iv['company']
        role = iv.get('role','')
        job_url = iv.get('job_url','#')
        cards += f'''  <div class="ip-card">
    <div class="ip-head">
      <div class="ip-company">{company}</div>
      <div class="ip-stage">{stage}</div>
    </div>
    <div class="ip-role">{role}</div>
    <div class="ip-date">{date_str}</div>
    <div class="ip-people-row">{people_html}</div>
    <div class="ip-notes">{next_action}</div>
    <div class="ip-links">
      <a href="{job_url}" target="_blank">Job post &rarr;</a>
    </div>
  </div>
'''
    return f'<div class="section-header" style="margin-top:20px">Interview Prep <span class="badge pill-cyan">{len(scheduled)} scheduled</span></div><div class="ip-grid">{cards}</div>'

SEASON_ACCENTS = {
    'ski':     ('#7dd3fc', 'Ski Season'),
    'spring':  ('#f9a8d4', 'Spring'),
    'mud':     ('#c8a679', 'Mud Season'),
    'summer':  ('#fb923c', 'Summer'),
    'monsoon': ('#86efac', 'Monsoon'),
    'fall':    ('#fbbf24', 'Fall'),
}

def get_seasonal_accent():
    m, d = datetime.now().month, datetime.now().day
    if m == 12 or m <= 2: key = 'ski'
    elif m == 3: key = 'spring'
    elif m == 4 and d <= 10: key = 'spring'
    elif m in (4, 5): key = 'mud'
    elif m == 6 or (m == 7 and d < 15): key = 'summer'
    elif m in (7, 8, 9): key = 'monsoon'
    else: key = 'fall'
    color, label = SEASON_ACCENTS[key]
    return {'color': color, 'label': label, 'key': key}

def build_personal_section(data):
    """Five-tile Personal section: Red Sox, Patriots, Outdoors, Industry, Recipe.

    Wrapped in a collapsible <details>. Defaults open when there are zero
    Tier 1/2 ranked opportunities (job-search quiet, make room for fun);
    defaults collapsed when there is real work to do.

    Each tile is just a shell; inline JavaScript fetches live ESPN data for
    the sports tiles and curated feeds (industry-feed.json, outdoor-feed.json,
    recipe-feed.json) for the others, then paints rotating content."""
    sports = (data.get("sports_today") or {})
    ranked = data.get("ranked_opportunities", [])
    tier12_count = len([r for r in ranked if (r.get("effective_score") or 0) >= 60])
    default_open = "" if tier12_count > 0 else " open"

    import html as _html
    mlb_fallback = _html.escape((sports.get("mlb") or {}).get("label", "Loading Red Sox..."), quote=True)
    nfl_fallback = _html.escape((sports.get("nfl") or {}).get("label", "Loading Patriots..."), quote=True)

    tile = lambda cls, tid, label, fallback: (
        f'<div class="ne-team {cls}" id="{tid}" data-fallback="{fallback}">'
        f'<div class="ne-row1"><span class="ne-team-name">{label}</span>'
        '<span class="ne-state ne-state-loading"><span class="ne-spinner"></span>loading</span></div>'
        '<div class="ne-game">Pulling feed&hellip;</div>'
        '<div class="ne-snark">If this never updates, check your wifi.</div>'
        '</div>'
    )

    next_refresh = compute_next_refresh_strings()
    refresh_tag = lambda label: (
        f'<div class="ne-refresh-tag" style="margin-top:6px;font-size:9px;'
        f'color:var(--text-muted);opacity:0.55;letter-spacing:0.04em;">'
        f'next refresh: {label}</div>'
    )
    tile_with_tag = lambda cls, tid, label, fallback, refresh_label: (
        f'<div class="ne-team {cls}" id="{tid}" data-fallback="{fallback}">'
        f'<div class="ne-row1"><span class="ne-team-name">{label}</span>'
        '<span class="ne-state ne-state-loading"><span class="ne-spinner"></span>loading</span></div>'
        '<div class="ne-game">Pulling feed&hellip;</div>'
        '<div class="ne-snark">If this never updates, check your wifi.</div>'
        + refresh_tag(refresh_label) +
        '</div>'
    )

    sox_tile  = tile("ne-sox", "ne-sox", "&#9918; Red Sox", mlb_fallback)
    pats_tile = tile("ne-pats", "ne-pats", "&#127944; Patriots", nfl_fallback)
    ind_tile  = tile_with_tag("ne-industry", "ne-industry", "&#128752; Industry", "Loading industry feed...", next_refresh["industry"])
    out_tile  = tile_with_tag("ne-outdoor", "ne-outdoor", "&#127956; Outdoors", "Loading outdoor feed...", next_refresh["outdoor"])

    # Recipe tile is different: it has a scroll button (like the haiku) so Paul
    # can cycle through candidate recipes rather than autorotate. Shell it explicitly.
    rec_tile = (
        '<div class="ne-team ne-recipe" id="ne-recipe" data-fallback="Loading recipes...">'
        '<div class="ne-row1"><span class="ne-team-name">&#127869; Recipe</span>'
        '<span class="ne-state ne-state-loading"><span class="ne-spinner"></span>loading</span></div>'
        '<div class="ne-game">Pulling recipes&hellip;</div>'
        '<div class="ne-snark">Tonight\'s candidate will appear here.</div>'
        '<div class="ne-recipe-controls" style="margin-top:8px;display:flex;gap:8px;align-items:center;">'
        '<button id="ne-recipe-prev" style="background:transparent;border:1px solid var(--cyan);color:var(--cyan);font-size:10px;padding:3px 9px;border-radius:4px;cursor:pointer;font-family:inherit;">&laquo; prev</button>'
        '<button id="ne-recipe-next" style="background:transparent;border:1px solid var(--cyan);color:var(--cyan);font-size:10px;padding:3px 9px;border-radius:4px;cursor:pointer;font-family:inherit;">next &raquo;</button>'
        '<span id="ne-recipe-counter" style="margin-left:4px;color:var(--text-muted);font-size:10px;opacity:0.7;"></span>'
        '</div>'
        + refresh_tag(next_refresh["recipe"]) +
        '</div>'
    )

    grid = (
        '<div id="ne-sports" class="ne-sports">'
        + sox_tile + pats_tile + out_tile + ind_tile + rec_tile +
        '</div>'
    )

    return (
        f'<details{default_open} class="collapsible-section">'
        '<summary class="section-header">Personal '
        '<span class="badge pill-cyan" style="font-size:11px;">Sports + Feeds</span>'
        '</summary>'
        f'{grid}'
        '</details>'
    )

def build_html(data):
    # Compute stats dynamically from data (ignore hardcoded stats in JSON)
    s = compute_stats(data)
    today = datetime.now().strftime("%B %d, %Y")
    today_short = datetime.now().strftime("%B %-d, %Y")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%B %-d, %Y")

    stat_cards = compute_stat_cards(data)
    cost_section_html = build_cost_section_html(compute_cost_summary())

    ranked = data.get("ranked_opportunities", [])
    # Tier 1 & 2 only for the Ranked Opportunities card grid (score 60+)
    ranked_t12 = [d for d in ranked if (d.get("effective_score") or 0) >= 60]

    # Derive pipeline tiers from ranked_opportunities by score threshold
    # Only include entries that are still actionable (not applied/rejected/pass)
    active_ranked = [d for d in ranked if d.get("status") in ("not_applied", "cold_outreach")]
    tier1 = [d for d in active_ranked if (d.get("effective_score") or 0) >= 75]
    tier2 = [d for d in active_ranked if 60 <= (d.get("effective_score") or 0) < 75]
    tier3 = [d for d in active_ranked if (d.get("effective_score") or 0) < 60]
    actionable = [d for d in ranked if d.get("recommendation") in ("pursue","pursue_with_caveats") and d.get("status") == "not_applied" and (d.get("effective_score") or 0) >= 60]
    action_items = ""
    for i, d in enumerate(actionable[:5]):
        new_badge = f' {pill("New", "cyan")}' if (d.get("is_new") or is_new(d.get("added"))) else ""
        eff = d.get("effective_score", 0)
        score_str = f' <span style="color:{score_color(eff)};font-weight:600">{eff:.0f}/100</span>' if eff else ""
        hook = d.get("hook", d.get("verdict", "")[:120])
        action_items += f'''  <div class="action-item" data-company="{d["company"]}">
    <div class="priority">{i+1}</div>
    <div><strong>{d["company"]}</strong>{score_str} — {hook}{new_badge}</div>
  </div>\n'''

    # Morning brief rows (sort newest-first so appended entries don't get buried)
    brief_rows = ""
    sorted_briefs = sorted(data.get("morning_briefs", []), key=lambda b: b.get("date", ""), reverse=True)
    for b in sorted_briefs:
        brief_rows += f'    <tr><td>{b["date"]}</td><td>{b["jobs_processed"]}</td><td>{b["high_scores"]}</td><td>{b["deep_dives"]}</td><td>{b["result"]}</td></tr>\n'

    # Watch list as JSON for Company of the Day JS rotation
    import json as _json
    watch_list_json = _json.dumps(data.get("watch_list", []))

    # Cold outreach rows
    cold_outreach_rows = ""
    for c in sorted(data.get("cold_outreach", []), key=lambda x: x.get("date", ""), reverse=True):
        status = c.get("status", "sent")
        status_cls = {"sent": "pill-blue", "replied": "pill-green", "meeting": "pill-purple", "no_reply": "pill-muted", "declined": "pill-red"}.get(status, "pill-muted")
        status_label = {"sent": "Sent", "replied": "Replied", "meeting": "Meeting", "no_reply": "No Reply", "declined": "Declined"}.get(status, status.title())
        cold_outreach_rows += f'    <tr><td class="company-name">{c["company"]}</td><td>{c.get("contact","—")}</td><td>{c.get("method","—")}</td><td>{c.get("date","—")}</td><td><span class="pill {status_cls}">{status_label}</span></td><td style="max-width:260px;font-size:11px;color:var(--text-muted)">{c.get("notes","")}</td></tr>\n'

    # Interview prep + countdown
    interviews = get_interviews(data.get("applications", []))
    interview_banner_html = build_next_interview_banner(interviews)
    interview_prep_html = build_interview_prep_cards(interviews)

# Seasonal accent — shift --accent-light and add a top bar so the season is actually visible
    season = get_seasonal_accent()
    season_badge_html = f'<span class="season-badge" style="background:{season["color"]};color:#0f1117">{season["label"]}</span>'
    seasonal_override_html = f'''<style>
  :root {{ --accent-light: {season["color"]}; --season: {season["color"]}; }}

  /* Top bar: 8px, fully saturated, big glow, unmissable */
  body::before {{
    content:"";
    position:fixed; top:0; left:0; right:0;
    height:8px;
    background: linear-gradient(90deg, {season["color"]}88, {season["color"]}, {season["color"]}, {season["color"]}88);
    box-shadow: 0 2px 32px {season["color"]}aa, 0 0 8px {season["color"]};
    z-index:999;
  }}

  /* Page-wide tint: stronger warm wash, deeper drop */
  body::after {{
    content:"";
    position:fixed; top:0; left:0; right:0; bottom:0;
    background: radial-gradient(ellipse 140% 70% at 50% 0%, {season["color"]}3a, transparent 75%);
    pointer-events:none;
    z-index:-1;
  }}

  /* Header band: dark base so the tinted H1 actually contrasts; subtle border + glow */
  .header {{
    border-bottom: 3px solid {season["color"]}aa;
    background: linear-gradient(180deg, {season["color"]}0a, transparent 60%);
    border-radius: 8px 8px 0 0;
    padding: 16px 16px 14px 16px;
    box-shadow: 0 4px 24px {season["color"]}22;
  }}

  /* H1 span: tinted, very subtle glow (the big seasonal feel comes from the bar/wash/band, not the title) */
  .header h1 span {{
    color: {season["color"]};
    text-shadow: 0 0 12px {season["color"]}22;
  }}

  /* Every section header gets a season-color accent bar on the left */
  .section-header {{
    border-left: 3px solid {season["color"]}cc;
    padding-left: 12px;
    background: linear-gradient(90deg, {season["color"]}14, transparent 30%);
    border-radius: 0 4px 4px 0;
    padding-top: 6px;
    padding-bottom: 6px;
  }}

  /* Stat cards get a thin season-color top bar */
  .stat-card {{
    border-top: 2px solid {season["color"]}66;
  }}
</style>'''

    # Sports strip — live widget, shell HTML + embedded feed data for snark rotation
    personal_section_html = build_personal_section(data)
    # Bake all five feeds into the HTML at build time. The widget's FEED object
    # starts populated so tiles render content immediately, even when the page
    # is opened via file:// (where Chrome blocks fetch() from local files).
    # pollFeed() still runs in the background for live refreshes on GitHub Pages.
    def _read_feed(path, default_shape):
        try:
            return _json.loads(Path(path).read_text())
        except Exception:
            return default_shape
    # legacy: data.get("sports_feed") was the old in-JSON payload; prefer the
    # external sports-feed.json file which the scheduled task writes.
    _sports = _read_feed("sports-feed.json", {"sox": {"items": []}, "pats": {"items": []}})
    # If the sports file has no items (known intermittent empty-write bug in the
    # sports refresh task), fall back to the in-JSON sports_feed if present.
    if not (_sports.get("sox", {}).get("items") or _sports.get("pats", {}).get("items")):
        inline_sports = data.get("sports_feed")
        if inline_sports: _sports = inline_sports
    _initial_feed = {
        "updated": _sports.get("updated", ""),
        "sox":      _sports.get("sox",  {"items": []}),
        "pats":     _sports.get("pats", {"items": []}),
        "industry": _read_feed("industry-feed.json", {"items": []}),
        "outdoor":  _read_feed("outdoor-feed.json",  {"items": []}),
        "recipe":   _read_feed("recipe-feed.json",   {"items": []}),
    }
    sports_feed_json = _json.dumps(_initial_feed)

    # Pre-computed "next refresh" date strings, injected into JS for the
    # haiku exhausted message and the personal-feed footer tags.
    _next_refresh = compute_next_refresh_strings()
    haiku_next_refresh_js = _json.dumps(_next_refresh["haiku"])
    personal_next_refresh_js = _json.dumps(_next_refresh["industry"])  # industry/outdoor/recipe share the cron

    # Speculative outreach section (hidden when empty)
    cold_outreach_list = data.get("cold_outreach", [])
    if cold_outreach_list:
        speculative_outreach_html = f'''<div class="section-header">Speculative Outreach <span class="badge pill-blue">{len(cold_outreach_list)} sent</span></div>
<p style="font-size:12px;color:var(--text-muted);margin-bottom:14px;">Direct outbound emails tracked separately from form-submitted applications. Form-based speculative applications (no specific role posted) live at the bottom of Applications Sent with a "Speculative" status.</p>
<div class="table-wrapper">
<table>
  <thead><tr><th>Company</th><th>Contact</th><th>Method</th><th>Date</th><th>Status</th><th>Notes</th></tr></thead>
  <tbody>
{cold_outreach_rows}
  </tbody>
</table>
</div>'''
    else:
        speculative_outreach_html = ""

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
<title>Paul Whitaker — Job Search Command Center</title>
<style>
  :root {{
    --bg: #0f1117; --card: #1a1d27; --card-hover: #222531; --border: #2a2d3a;
    --text: #e4e4e7; --text-muted: #9ca3af; --accent: #6366f1; --accent-light: #818cf8;
    --green: #22c55e; --green-bg: rgba(34,197,94,0.12);
    --amber: #f59e0b; --amber-bg: rgba(245,158,11,0.12);
    --red: #ef4444; --red-bg: rgba(239,68,68,0.12);
    --blue: #3b82f6; --blue-bg: rgba(59,130,246,0.12);
    --purple: #a855f7; --purple-bg: rgba(168,85,247,0.12);
    --cyan: #06b6d4; --cyan-bg: rgba(6,182,212,0.12);
  }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:var(--bg); color:var(--text); line-height:1.5; padding:20px 24px; max-width:1440px; margin:0 auto; }}
  .header {{ display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:20px; padding-bottom:16px; border-bottom:1px solid var(--border); }}
  .header h1 {{ font-size:24px; font-weight:700; letter-spacing:-0.5px; }}
  .header h1 span {{ color:var(--accent-light); }}
  .header .meta {{ text-align:right; color:var(--text-muted); font-size:13px; }}
  .header .meta .updated {{ font-size:14px; color:var(--green); font-weight:500; }}
  .stats {{ display:grid; grid-template-columns:repeat(5, 1fr); gap:10px; margin-bottom:24px; }}
  @media (max-width:900px) {{ .stats {{ grid-template-columns:repeat(3, 1fr); }} }}
  .stat-card {{ background:var(--card); border:1px solid var(--border); border-radius:10px; padding:14px 10px; text-align:center; position:relative; cursor:default; }}
  .stat-card .number {{ font-size:30px; font-weight:700; line-height:1; }}
  .stat-card .label {{ font-size:10px; text-transform:uppercase; letter-spacing:0.8px; color:var(--text-muted); margin-top:5px; }}
  .stat-card .tooltip {{ display:none; position:absolute; top:100%; left:50%; transform:translateX(-50%); margin-top:8px; background:var(--card); border:1px solid var(--border); border-radius:8px; padding:10px 14px; font-size:12px; text-align:left; white-space:nowrap; z-index:50; box-shadow:0 8px 24px rgba(0,0,0,0.4); min-width:180px; }}
  .stat-card .tooltip::before {{ content:''; position:absolute; top:-6px; left:50%; transform:translateX(-50%); border-left:6px solid transparent; border-right:6px solid transparent; border-bottom:6px solid var(--border); }}
  .stat-card:hover .tooltip {{ display:block; }}
  .stat-card .tooltip .tt-item {{ padding:3px 0; color:var(--text); }}
  .stat-card .tooltip .tt-empty {{ color:var(--text-muted); font-style:italic; }}
  .section-header {{ display:flex; align-items:center; gap:10px; margin:28px 0 12px; font-size:16px; font-weight:600; }}
  details.collapsible-section > summary.section-header {{ cursor:pointer; list-style:none; }}
  details.collapsible-section > summary.section-header::before {{ content:"▼"; display:inline-block; font-size:10px; opacity:0.55; transition:transform 0.15s; width:10px; }}
  details.collapsible-section:not([open]) > summary.section-header::before {{ transform:rotate(-90deg); }}
  details.collapsible-section > summary.section-header::-webkit-details-marker {{ display:none; }}
  .section-header .badge {{ font-size:11px; padding:3px 9px; border-radius:20px; font-weight:500; }}
  .action-banner {{ background:linear-gradient(135deg, rgba(99,102,241,0.15), rgba(168,85,247,0.1)); border:1px solid rgba(99,102,241,0.3); border-radius:10px; padding:16px 20px; margin-bottom:24px; }}
  .action-banner h2 {{ font-size:15px; font-weight:600; margin-bottom:10px; color:var(--accent-light); }}
  .action-item {{ display:flex; align-items:flex-start; gap:10px; padding:5px 0; font-size:13px; }}
  .action-item .priority {{ flex-shrink:0; width:22px; height:22px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:11px; font-weight:700; background:var(--accent); color:white; }}
  .table-wrapper {{ overflow-x:auto; border-radius:10px; border:1px solid var(--border); margin-bottom:24px; }}
  /* Per-table search filter */
  .table-filter {{ width:100%; padding:7px 12px; margin:8px 0 6px 0; background:var(--card); border:1px solid var(--border); border-radius:6px; color:var(--text); font-size:12.5px; font-family:inherit; box-sizing:border-box; transition:border-color 0.15s, box-shadow 0.15s; }}
  .table-filter:focus {{ outline:none; border-color:var(--accent-light); box-shadow:0 0 0 3px rgba(255,255,255,0.04); }}
  .table-filter::placeholder {{ color:var(--text-muted); opacity:0.65; font-style:italic; }}
  .table-filter.has-active-filter {{ border-color:var(--accent-light); background:rgba(255,255,255,0.02); }}
  table {{ width:100%; border-collapse:collapse; font-size:12px; }}
  thead th {{ background:var(--card); padding:10px 12px; text-align:left; font-weight:600; font-size:10px; text-transform:uppercase; letter-spacing:0.8px; color:var(--text-muted); border-bottom:1px solid var(--border); white-space:nowrap; position:sticky; top:0; z-index:1; }}
  tbody td {{ padding:10px 12px; border-bottom:1px solid var(--border); vertical-align:top; }}
  tbody tr:hover {{ background:var(--card-hover); }}
  tbody tr:last-child td {{ border-bottom:none; }}
  .pill {{ display:inline-block; padding:3px 10px; border-radius:20px; font-size:11px; font-weight:600; white-space:nowrap; }}
  .pill-green {{ background:var(--green-bg); color:var(--green); }}
  .pill-amber {{ background:var(--amber-bg); color:var(--amber); }}
  .pill-red {{ background:var(--red-bg); color:var(--red); }}
  .pill-blue {{ background:var(--blue-bg); color:var(--blue); }}
  .pill-purple {{ background:var(--purple-bg); color:var(--purple); }}
  .pill-cyan {{ background:var(--cyan-bg); color:var(--cyan); }}
  .pill-muted {{ background:rgba(156,163,175,0.12); color:var(--text-muted); }}
  .fit-bar {{ display:flex; align-items:center; gap:6px; }}
  .fit-bar .bar {{ width:50px; height:6px; background:var(--border); border-radius:3px; overflow:hidden; }}
  .fit-bar .bar-fill {{ height:100%; border-radius:3px; }}
  a {{ color:var(--accent-light); text-decoration:none; }}
  a:hover {{ text-decoration:underline; }}
  .dd-grid {{ display:grid; grid-template-columns:repeat(3, 1fr); gap:12px; margin-bottom:32px; align-items:stretch; }}
  @media (max-width:1000px) {{ .dd-grid {{ grid-template-columns:repeat(2, 1fr); }} }}
  @media (max-width:640px) {{ .dd-grid {{ grid-template-columns:1fr; }} }}
  .dd-card {{ background:var(--card); border:1px solid var(--border); border-radius:10px; padding:14px 16px; position:relative; display:flex; flex-direction:column; }}
  .dd-card.dd-new {{ border:1px solid var(--cyan); box-shadow:0 0 12px rgba(6,182,212,0.25); animation:glow 2s ease-in-out infinite alternate; }}
  @keyframes glow {{ from {{ box-shadow:0 0 8px rgba(6,182,212,0.15); }} to {{ box-shadow:0 0 16px rgba(6,182,212,0.35); }} }}
  .dd-card .rank {{ position:absolute; top:10px; right:12px; font-size:24px; font-weight:800; color:var(--border); line-height:1; }}
  .dd-card .company {{ font-weight:600; font-size:14px; margin-bottom:2px; padding-right:36px; }}
  .dd-card .role {{ font-size:12px; color:var(--text-muted); margin-bottom:3px; line-height:1.3; }}
  .dd-card .meta-line {{ font-size:10px; color:var(--text-muted); margin-bottom:6px; opacity:0.7; }}
  .dd-card .score-row {{ display:flex; flex-wrap:wrap; gap:6px; font-size:11px; margin-bottom:8px; }}
  .dd-card .score-row span {{ padding:2px 7px; border-radius:6px; background:var(--card-hover); }}
  .dd-card .verdict {{ font-size:11px; margin-bottom:8px; padding:6px 10px; border-radius:8px; background:rgba(99,102,241,0.08); border-left:3px solid var(--accent); line-height:1.4; flex:1; }}
  .dd-card .blockers-row {{ display:flex; flex-wrap:wrap; gap:4px; margin-bottom:8px; }}
  .dd-card .blocker-tag {{ font-size:9px; font-weight:700; letter-spacing:0.5px; padding:3px 7px; border-radius:4px; cursor:help; text-transform:uppercase; line-height:1.2; }}
  .dd-card .blocker-tag-hard {{ background:rgba(239,68,68,0.15); color:#f87171; border:1px solid rgba(239,68,68,0.5); }}
  .dd-card .blocker-tag-soft {{ background:rgba(245,158,11,0.12); color:#fbbf24; border:1px solid rgba(245,158,11,0.4); }}
  .dd-card .links {{ display:flex; gap:8px; font-size:11px; flex-wrap:wrap; }}
  .dd-card .links a {{ padding:3px 8px; border-radius:6px; background:rgba(99,102,241,0.12); }}
  .new-badge {{ position:absolute; bottom:14px; right:14px; background:var(--cyan); color:#000; font-size:10px; font-weight:800; padding:2px 8px; border-radius:4px; text-transform:uppercase; letter-spacing:1px; animation:pulse 1.5s ease-in-out infinite; }}
  @keyframes pulse {{ 0%,100% {{ opacity:1; }} 50% {{ opacity:0.7; }} }}
  .cotd-card {{ background:var(--card); border:1px solid var(--border); border-radius:10px; padding:20px 24px; margin-bottom:24px; position:relative; overflow:hidden; }}
  .cotd-card::before {{ content:''; position:absolute; top:0; left:0; right:0; height:3px; background:linear-gradient(90deg, var(--cyan), var(--accent-light), var(--purple)); }}
  .cotd-company {{ font-size:20px; font-weight:700; margin-bottom:2px; }}
  .cotd-company a {{ color:var(--text); }}
  .cotd-company a:hover {{ color:var(--cyan); }}
  .cotd-category {{ font-size:12px; color:var(--cyan); font-weight:500; margin-bottom:10px; }}
  .cotd-why {{ font-size:13px; color:var(--text-muted); line-height:1.6; margin-bottom:14px; }}
  .cotd-actions {{ display:flex; gap:10px; align-items:center; }}
  .cotd-actions a {{ display:inline-block; padding:6px 14px; border-radius:6px; font-size:12px; font-weight:600; }}
  .cotd-actions .btn-primary {{ background:var(--accent); color:white; }}
  .cotd-actions .btn-primary:hover {{ background:var(--accent-light); text-decoration:none; }}
  .cotd-actions .btn-secondary {{ background:rgba(99,102,241,0.12); color:var(--accent-light); }}
  .cotd-actions .btn-secondary:hover {{ text-decoration:none; background:rgba(99,102,241,0.2); }}
  .cotd-counter {{ position:absolute; top:16px; right:20px; font-size:11px; color:var(--text-muted); }}
  .cotd-nav {{ display:flex; gap:6px; align-items:center; }}
  .cotd-nav button {{ background:rgba(99,102,241,0.12); border:1px solid var(--border); color:var(--text-muted); width:28px; height:28px; border-radius:6px; cursor:pointer; font-size:14px; display:flex; align-items:center; justify-content:center; }}
  .cotd-nav button:hover {{ background:var(--accent); color:white; border-color:var(--accent); }}
  .footer {{ text-align:center; color:var(--text-muted); font-size:12px; padding:24px 0; border-top:1px solid var(--border); margin-top:24px; }}
  .next-action {{ font-size:12px; color:var(--accent-light); font-style:italic; }}
  .notes {{ font-size:12px; color:var(--text-muted); max-width:220px; }}
  .company-name {{ font-weight:600; }}
  .doc-missing {{ color:var(--text-muted); font-style:italic; font-size:11px; }}
  .dismiss-btn {{ position:absolute; top:10px; right:40px; width:22px; height:22px; border-radius:50%; border:1px solid var(--border); background:transparent; color:var(--text-muted); font-size:14px; cursor:pointer; display:flex; align-items:center; justify-content:center; opacity:0; transition:all 0.2s; }}
  .dd-card:hover .dismiss-btn {{ opacity:0.6; }}
  .dismiss-btn:hover {{ opacity:1 !important; background:rgba(239,68,68,0.15); color:var(--text); border-color:rgba(239,68,68,0.4); }}
  .status-select {{ display:inline-block; padding:3px 8px; border-radius:20px; font-size:11px; font-weight:600; border:1px solid var(--border); background:var(--card-hover); color:var(--text); cursor:pointer; appearance:none; -webkit-appearance:none; background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%239ca3af'/%3E%3C/svg%3E"); background-repeat:no-repeat; background-position:right 8px center; padding-right:22px; }}
  .status-select:hover {{ border-color:var(--accent); }}
  .status-select option {{ background:var(--card); color:var(--text); }}
  .dd-card.dismissed {{ display:none; }}
  .toast {{ position:fixed; bottom:24px; right:24px; background:var(--card); border:1px solid var(--border); border-radius:10px; padding:14px 20px; font-size:13px; color:var(--text); z-index:100; display:flex; align-items:center; gap:12px; box-shadow:0 8px 24px rgba(0,0,0,0.4); animation:slideIn 0.3s ease-out; }}
  .toast button {{ background:var(--accent); color:white; border:none; padding:4px 12px; border-radius:6px; cursor:pointer; font-size:12px; font-weight:600; }}
  @keyframes slideIn {{ from {{ transform:translateY(20px); opacity:0; }} to {{ transform:translateY(0); opacity:1; }} }}
  details summary {{ cursor:pointer; list-style:none; display:flex; align-items:center; gap:8px; }}
  details summary::-webkit-details-marker {{ display:none; }}
  details summary::before {{ content:'\\25b8'; font-size:14px; transition:transform 0.2s; }}
  details[open] summary::before {{ transform:rotate(90deg); }}

  /* Interview countdown banner */
  .interview-banner {{ display:flex; align-items:center; gap:20px; background:linear-gradient(135deg, rgba(6,182,212,0.18), rgba(99,102,241,0.12)); border:1px solid rgba(6,182,212,0.4); border-radius:10px; padding:14px 20px; margin-bottom:16px; }}
  .interview-banner .ib-left {{ flex:1; min-width:0; }}
  .interview-banner .ib-label {{ font-size:9px; letter-spacing:1.5px; color:var(--cyan); font-weight:700; margin-bottom:4px; }}
  .interview-banner .ib-company {{ font-size:16px; font-weight:700; color:var(--text); }}
  .interview-banner .ib-role {{ font-size:12px; color:var(--text-muted); }}
  .interview-banner .ib-mid {{ flex:1.4; text-align:center; min-width:0; }}
  .interview-banner .ib-countdown {{ font-size:22px; font-weight:700; color:var(--cyan); font-variant-numeric:tabular-nums; letter-spacing:-0.5px; }}
  .interview-banner .ib-countdown.ib-live {{ color:var(--red); animation:pulse 1s ease-in-out infinite; }}
  .interview-banner .ib-time {{ font-size:11px; color:var(--text-muted); margin-top:2px; }}
  .interview-banner .ib-people {{ font-size:10px; color:var(--text-muted); opacity:0.8; margin-top:2px; }}
  .interview-banner .ib-right {{ flex:0 0 auto; }}
  .interview-banner .ib-link {{ font-size:11px; color:var(--cyan); padding:6px 12px; border:1px solid rgba(6,182,212,0.4); border-radius:6px; text-decoration:none; font-weight:600; }}
  .interview-banner .ib-link:hover {{ background:rgba(6,182,212,0.15); }}
  @keyframes pulse {{ 0%,100% {{ opacity:1; }} 50% {{ opacity:0.5; }} }}

  /* Interview prep cards */
  .ip-grid {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(300px, 1fr)); gap:12px; margin-bottom:24px; }}
  .ip-card {{ background:var(--card); border:1px solid var(--border); border-radius:10px; padding:14px 16px; }}
  .ip-head {{ display:flex; justify-content:space-between; align-items:baseline; margin-bottom:4px; gap:10px; }}
  .ip-company {{ font-size:14px; font-weight:700; }}
  .ip-stage {{ font-size:10px; color:var(--cyan); padding:2px 8px; border-radius:10px; background:var(--cyan-bg); white-space:nowrap; }}
  .ip-role {{ font-size:12px; color:var(--text-muted); margin-bottom:8px; }}
  .ip-date {{ margin:6px 0; font-size:12px; }}
  .ip-upcoming {{ color:var(--green); font-weight:600; }}
  .ip-past {{ color:var(--text-muted); }}
  .ip-tbd {{ color:var(--amber); font-style:italic; }}
  .ip-people-row {{ display:flex; flex-wrap:wrap; gap:4px; margin:6px 0; }}
  .ip-person {{ font-size:10px; padding:2px 7px; border-radius:10px; background:var(--card-hover); color:var(--text-muted); }}
  .ip-notes {{ font-size:11px; color:var(--text-muted); line-height:1.4; margin:8px 0; max-height:90px; overflow:auto; }}
  .ip-links {{ display:flex; gap:6px; font-size:11px; flex-wrap:wrap; }}
  .ip-links a {{ padding:3px 8px; border-radius:5px; background:rgba(99,102,241,0.12); color:var(--accent-light); text-decoration:none; }}
  .ip-links a:hover {{ background:rgba(99,102,241,0.22); }}

/* Sports strip (legacy fallback) */
  .sports-strip {{ display:flex; gap:8px; align-items:center; justify-content:flex-end; font-size:11px; flex-wrap:wrap; margin-top:4px; }}
  .sports-strip .sp-item {{ padding:3px 10px; border-radius:12px; background:var(--card); border:1px solid var(--border); text-decoration:none; color:var(--text-muted); transition:all 0.15s; }}
  .sports-strip .sp-item:hover {{ background:var(--card-hover); color:var(--text); border-color:var(--cyan); }}

  /* New England Sportsball — live widget (auto-fetches ESPN on load) */
  .ne-sports {{ display:grid; grid-template-columns:repeat(3, 1fr); gap:10px; margin:14px 0 8px 0; }}
  @media (max-width:1100px) {{ .ne-sports {{ grid-template-columns:1fr 1fr; }} }}
  .ne-team.ne-industry::before {{ background:#06b6d4; }}
  .ne-team.ne-outdoor::before {{ background:#10b981; }}
  .ne-team.ne-recipe::before {{ background:#f59e0b; }}
  @media (max-width:900px) {{ .ne-sports {{ grid-template-columns:1fr; }} }}
  /* Locked-size cards so the rotation never reflows layout. Fixed height + truncation. */
  .ne-team {{ background:var(--card); border:1px solid var(--border); border-radius:10px; padding:12px 16px 12px 20px; position:relative; overflow:hidden; height:128px; box-sizing:border-box; display:flex; flex-direction:column; transition:border-color 0.2s; }}
  .ne-team:hover {{ border-color:#3a3d4a; }}
  .ne-team::before {{ content:''; position:absolute; top:0; left:0; width:4px; height:100%; }}
  .ne-team.ne-sox::before {{ background:#BD3039; }}
  .ne-team.ne-pats::before {{ background:#002244; }}
  .ne-row1 {{ display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:5px; flex:0 0 auto; }}
  .ne-team-name {{ font-size:12px; font-weight:700; letter-spacing:0.3px; color:var(--text); white-space:nowrap; }}
  .ne-state {{ font-size:9px; letter-spacing:1.2px; text-transform:uppercase; padding:2px 8px; border-radius:4px; font-weight:800; display:inline-flex; align-items:center; gap:5px; white-space:nowrap; max-width:60%; overflow:hidden; text-overflow:ellipsis; }}
  .ne-state-live {{ background:rgba(239,68,68,0.16); color:#f87171; animation:pulse 1.2s ease-in-out infinite; }}
  .ne-state-final {{ background:rgba(156,163,175,0.14); color:var(--text-muted); }}
  .ne-state-scheduled {{ background:rgba(6,182,212,0.15); color:var(--cyan); }}
  .ne-state-news {{ background:rgba(99,102,241,0.14); color:var(--accent-light); }}
  .ne-state-quiet {{ background:rgba(156,163,175,0.1); color:var(--text-muted); opacity:0.8; }}
  .ne-state-loading {{ background:rgba(99,102,241,0.12); color:var(--accent-light); }}
  /* The two body lines get fixed line counts via -webkit-line-clamp so a long headline or snark can't push the card taller. */
  .ne-game {{ font-size:14px; font-weight:600; color:var(--text); line-height:1.3; margin-bottom:4px; flex:0 0 auto; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }}
  .ne-snark {{ font-size:12px; color:var(--text-muted); font-style:italic; line-height:1.4; opacity:0.92; flex:1 1 auto; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }}
    .ne-pitchers {{ font-size:10px; color:var(--text-muted); opacity:0.75; margin-top:4px; letter-spacing:0.02em; }}
  .ne-link {{ margin-top:6px; font-size:10px; opacity:0.55; flex:0 0 auto; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  .ne-link a {{ color:var(--text-muted); text-decoration:underline; text-decoration-style:dotted; text-underline-offset:3px; }}
  .ne-link a:hover {{ color:var(--cyan); }}
  .ne-spinner {{ display:inline-block; width:9px; height:9px; border:2px solid var(--border); border-top-color:var(--accent-light); border-radius:50%; animation:ne-spin 0.9s linear infinite; }}
  @keyframes ne-spin {{ to {{ transform:rotate(360deg); }} }}
  .ne-fade {{ animation:ne-fade 0.35s ease-out; }}
  @keyframes ne-fade {{ from {{ opacity:0.35; transform:translateY(2px); }} to {{ opacity:1; transform:translateY(0); }} }}

  /* Seasonal badge */
  .season-badge {{ display:inline-block; padding:3px 11px; border-radius:12px; font-size:11px; font-weight:700; letter-spacing:0.6px; text-transform:uppercase; color:#0f1117; box-shadow:0 1px 8px rgba(0,0,0,0.25); }}

  @media (max-width:768px) {{ body {{ padding:12px; }} .header {{ flex-direction:column; gap:8px; }} .header .meta {{ text-align:left; }} table {{ font-size:12px; }} .interview-banner {{ flex-direction:column; text-align:center; gap:10px; }} }}
  /* Tap-to-toggle stat-card tooltips (mobile-friendly fallback for hover) */
  .stat-card.touched .tooltip {{ display:block !important; }}
  /* Tighter mobile layout and touch affordances */
  @media (max-width:640px) {{
    body {{ padding:10px 8px; max-width:100%; line-height:1.45; }}
    .header h1 {{ font-size:20px; }}
    .header h1 span {{ font-size:14px; }}
    .season-badge {{ display:none; }}
    .stats {{ grid-template-columns:repeat(2, 1fr); gap:8px; margin-bottom:16px; }}
    .stat-card {{ padding:10px 8px; cursor:pointer; }}
    .stat-card .number {{ font-size:22px; }}
    .stat-card .label {{ font-size:9px; }}
    /* Mobile tooltip: tap-to-toggle, positioned in-card so it doesn't overflow */
    .stat-card .tooltip {{ position:fixed; left:8px; right:8px; top:auto; bottom:16px; transform:none; margin-top:0; min-width:0; max-width:none; white-space:normal; box-shadow:0 -4px 24px rgba(0,0,0,0.5); z-index:200; }}
    .stat-card .tooltip::before {{ display:none; }}
    .stat-card:hover .tooltip {{ display:none; }}
    .stat-card.touched .tooltip {{ display:block !important; }}
    .section-header {{ font-size:14px; margin:20px 0 10px; gap:6px; flex-wrap:wrap; }}
    .section-header .badge {{ font-size:10px; padding:2px 7px; }}
    table {{ font-size:11px; }}
    table th, table td {{ padding:6px 5px; }}
    .table-wrapper {{ margin-bottom:16px; }}
    .action-banner {{ padding:12px; margin:16px 0; }}
    .action-banner h2 {{ font-size:15px; }}
    .action-item {{ padding:8px; gap:8px; }}
    .action-item .priority {{ font-size:16px; min-width:24px; }}
    .dd-grid {{ gap:10px; }}
    .ip-grid {{ grid-template-columns:1fr; }}
    /* Buttons and pills get proper tap targets per Apple HIG (min ~44px) */
    button, .action-item {{ min-height:36px; }}
    .pill {{ min-height:24px; padding:6px 12px !important; font-size:12px !important; display:inline-flex; align-items:center; }}
    .badge.pill {{ padding:4px 10px !important; font-size:11px !important; }}
    /* Pipeline / applications tables: keep horizontal scroll but hint at it */
    .table-wrapper {{ position:relative; }}
    .table-wrapper::after {{ content:"← scroll →"; position:absolute; bottom:4px; right:8px; font-size:9px; color:var(--text-muted); opacity:0.5; pointer-events:none; }}
    /* Personal tiles single-column on phone */
    .ne-sports {{ grid-template-columns:1fr !important; }}
    .ne-team {{ padding:10px; }}
    .ne-game {{ font-size:13px; }}
    .ne-snark {{ font-size:11px; }}
    /* Hide noise columns on mobile so most-useful columns fit visible */
    /* Applications Sent: 11 cols. Hide only Applied(4). Days, Domain, Comp, Link all kept per Paul's request 2026-04-26 (table will scroll horizontally on phone, that's fine). */
    .applications-table th:nth-child(4),
    .applications-table td:nth-child(4) {{ display:none; }}
    /* Pipeline (Tier 1/2/3): 10 cols. Hide #(1), Fit(4), Added(6), Location(8). Keep Domain(7) and Link(9) per Paul's request 2026-04-26. */
    .pipeline-table th:nth-child(1),
    .pipeline-table td:nth-child(1),
    .pipeline-table th:nth-child(4),
    .pipeline-table td:nth-child(4),
    .pipeline-table th:nth-child(6),
    .pipeline-table td:nth-child(6),
    .pipeline-table th:nth-child(8),
    .pipeline-table td:nth-child(8) {{ display:none; }}
    /* Verdict and notes columns: take full width on mobile, wrap freely */
    .next-action {{ max-width:none; white-space:normal; }}
    .notes {{ max-width:none; white-space:normal; }}
  }}
  @media (max-width:480px) {{
    .header h1 {{ font-size:18px; }}
    .header h1 span {{ font-size:11px; display:block; margin-top:2px; }}
  }}
  @media (max-width:400px) {{
    body {{ padding:8px 6px; }}
    .stats {{ grid-template-columns:1fr 1fr; }}
    .stat-card .number {{ font-size:20px; }}
    .action-banner h2 {{ font-size:14px; }}
  }}
</style>
{seasonal_override_html}
</head>
<body>

<div class="header">
  <div>
    <h1>Paul Whitaker — <span>Job Search Command Center</span></h1>
  </div>
  <div class="meta">
    <div class="updated">Last updated: {today_short} &nbsp; {season_badge_html}</div>
  </div>
</div>

{interview_banner_html}

<div class="stats">
{build_stat_cards_html(stat_cards)}
</div>

<div class="action-banner">
  <h2>What To Do Next</h2>
{action_items}
</div>

{interview_prep_html}

<details open class="collapsible-section">
<summary class="section-header">Ranked Opportunities <span class="badge pill-purple">{len(ranked_t12)} Tier 1 &amp; 2</span></summary>
<div id="haiku-slot" style="display:none;text-align:center;padding:24px 16px;margin-bottom:16px;">
  <div id="haiku-text" style="font-style:italic;color:var(--text-muted);font-size:14px;line-height:1.8;white-space:pre-line;min-height:80px;display:flex;align-items:center;justify-content:center;"></div>
  <div id="haiku-source" style="margin-top:8px;font-size:10px;opacity:0.45;min-height:14px;"></div>
  <div style="margin-top:14px;">
    <button id="haiku-refresh" style="background:transparent;border:1px solid var(--cyan);color:var(--cyan);font-size:12px;padding:6px 14px;border-radius:6px;cursor:pointer;font-family:inherit;font-weight:600;">&#x21bb; new haiku</button>
    <span id="haiku-counter" style="margin-left:12px;color:var(--text-muted);font-size:10px;opacity:0.7;"></span>
  </div>
  <div style="margin-top:8px;color:var(--text-muted);font-size:9px;opacity:0.4;">v4 &middot; 62-haiku no-repeat cycle &middot; some riff on a source</div>
</div>
<div class="dd-grid">
{build_ranked_cards(ranked_t12)}
</div>

</details>

{personal_section_html}

<details open class="collapsible-section">
<summary class="section-header">Applications Sent <span class="badge pill-green">{s["awaiting_response"]} active</span> <span class="badge pill-muted" style="font-size:10px;">{s["rejected_closed"]} closed below</span></summary>
<input class="table-filter" type="search" placeholder="Filter applications by company, role, domain, status..." aria-label="Filter applications" />
<div class="table-wrapper">
<table class="applications-table">
  <thead><tr><th data-type="text">Company</th><th data-type="text">Role</th><th data-type="num">Score</th><th data-type="date">Applied</th><th data-type="num">Days</th><th data-type="text">Domain</th><th data-type="text">Location</th><th data-type="text">Comp</th><th data-type="text">Status</th><th>Link</th><th>Next Action</th></tr></thead>
  <tbody>
{build_app_rows(data["applications"], include='active')}
  </tbody>
</table>
</div>

</details>

<details open class="collapsible-section">
<summary class="section-header">Active Pipeline <span class="badge pill-blue">{len(active_ranked)} actionable</span></summary>
<p style="font-size:12px;color:var(--text-muted);margin-bottom:14px;">Derived from scored opportunities. Tier 1 = score 75+, Tier 2 = 60-74, Tier 3 = under 60.</p>

<details open>
<summary class="section-header" style="margin-top:12px"><span style="color:var(--green);font-weight:600;">Tier 1 — Top Targets (75+)</span> <span class="badge pill-green">{len(tier1)} roles</span></summary>
<input class="table-filter" type="search" placeholder="Filter Tier 1..." aria-label="Filter Tier 1" />
<div class="table-wrapper" style="margin-top:12px">
<table class="pipeline-table">
  <thead><tr><th data-type="num">#</th><th data-type="text">Company</th><th data-type="text">Role</th><th data-type="num">Fit</th><th data-type="num">Score</th><th data-type="date">Added</th><th data-type="text">Domain</th><th data-type="text">Location</th><th>Link</th><th>Why</th></tr></thead>
  <tbody>
{build_pipeline_rows(tier1)}
  </tbody>
</table>
</div>
</details>

<details open>
<summary class="section-header" style="margin-top:12px"><span style="color:var(--amber);font-weight:600;">Tier 2 — Strong Fits (60-74)</span> <span class="badge pill-amber">{len(tier2)} roles</span></summary>
<input class="table-filter" type="search" placeholder="Filter Tier 2..." aria-label="Filter Tier 2" />
<div class="table-wrapper" style="margin-top:12px">
<table class="pipeline-table">
  <thead><tr><th data-type="num">#</th><th data-type="text">Company</th><th data-type="text">Role</th><th data-type="num">Fit</th><th data-type="num">Score</th><th data-type="date">Added</th><th data-type="text">Domain</th><th data-type="text">Location</th><th>Link</th><th>Why</th></tr></thead>
  <tbody>
{build_pipeline_rows(tier2)}
  </tbody>
</table>
</div>
</details>

<details>
<summary class="section-header" style="margin-top:12px"><span style="color:var(--text-muted);font-weight:600;">Tier 3 — Worth a Look (under 60)</span> <span class="badge pill-muted">{len(tier3)} roles</span></summary>
<input class="table-filter" type="search" placeholder="Filter Tier 3..." aria-label="Filter Tier 3" />
<div class="table-wrapper" style="margin-top:12px">
<table class="pipeline-table">
  <thead><tr><th data-type="num">#</th><th data-type="text">Company</th><th data-type="text">Role</th><th data-type="num">Fit</th><th data-type="num">Score</th><th data-type="date">Added</th><th data-type="text">Domain</th><th data-type="text">Location</th><th>Link</th><th>Why</th></tr></thead>
  <tbody>
{build_pipeline_rows(tier3)}
  </tbody>
</table>
</div>
</details>
</details>

<details open class="collapsible-section">
<summary class="section-header">Company of the Day <span class="badge pill-cyan">from {len(data.get("watch_list",[]))} watched</span></summary>
<div id="cotd-spotlight" class="cotd-card">
  <div class="cotd-loading" style="color:var(--text-muted);font-size:13px;padding:20px;">Loading...</div>
</div>
</details>

{speculative_outreach_html}

<details>
<summary class="section-header">Retired <span class="badge pill-muted" style="font-size:10px;">{s["retired"]} retired</span></summary>
<p style="font-size:12px;color:var(--text-muted);margin-bottom:14px;">Applications where the proactive process has run its course, follow-ups sent, no response. Kept here for record so the same role does not get re-prioritized.</p>
<input class="table-filter" type="search" placeholder="Filter retired..." aria-label="Filter retired" />
<div class="table-wrapper" style="margin-top:12px">
<table class="applications-table">
  <thead><tr><th data-type="text">Company</th><th data-type="text">Role</th><th data-type="num">Score</th><th data-type="date">Applied</th><th data-type="num">Days</th><th data-type="text">Domain</th><th data-type="text">Location</th><th data-type="text">Comp</th><th data-type="text">Status</th><th>Link</th><th>Next Action</th></tr></thead>
  <tbody>
{build_app_rows(data["applications"], include='retired')}
  </tbody>
</table>
</div>
</details>

<details>
<summary class="section-header">Rejected / Closed <span class="badge pill-muted" style="font-size:10px;">{s["rejected_closed"]} closed</span></summary>
<input class="table-filter" type="search" placeholder="Filter rejected/closed..." aria-label="Filter rejected" />
<div class="table-wrapper" style="margin-top:12px">
<table class="applications-table">
  <thead><tr><th data-type="text">Company</th><th data-type="text">Role</th><th data-type="num">Score</th><th data-type="date">Applied</th><th data-type="num">Days</th><th data-type="text">Domain</th><th data-type="text">Location</th><th data-type="text">Comp</th><th data-type="text">Status</th><th>Link</th><th>Next Action</th></tr></thead>
  <tbody>
{build_app_rows(data["applications"], include='closed')}
  </tbody>
</table>
</div>
</details>

{cost_section_html}

<details>
<summary class="section-header">Morning Brief Log <span class="badge pill-muted" style="font-size:10px;">archived</span></summary>
<input class="table-filter" type="search" placeholder="Filter brief log by date or keyword..." aria-label="Filter morning brief log" />
<div class="table-wrapper" style="margin-top:12px">
<table>
  <thead><tr><th>Date</th><th>Jobs</th><th>7+ Scores</th><th>Deep Dives</th><th>Result</th></tr></thead>
  <tbody>
{brief_rows}
  </tbody>
</table>
</div>
</details>

<div class="footer">
  <p>Last sync: {today_short}</p>
</div>

<script>
// --- Company of the Day ---
(function() {{
  const watchList = {watch_list_json};
  const spot = document.getElementById('cotd-spotlight');
  if (!spot || watchList.length === 0) return;

  // Day-based index so it rotates daily
  const now = new Date();
  const dayOfYear = Math.floor((now - new Date(now.getFullYear(),0,0)) / 86400000);
  let idx = dayOfYear % watchList.length;

  function render(i) {{
    const w = watchList[i];
    const careersLink = w.careers_url ? `<a href="${{w.careers_url}}" target="_blank" class="btn-primary">View Careers Page</a>` : '';
    const researchLink = `<a href="https://www.google.com/search?q=${{encodeURIComponent(w.company + ' jobs careers')}}" target="_blank" class="btn-secondary">Research</a>`;
    spot.innerHTML = `
      <div class="cotd-counter">${{i+1}} of ${{watchList.length}}</div>
      <div class="cotd-company">${{w.company}}</div>
      <div class="cotd-category">${{w.category}}</div>
      <div class="cotd-why">${{w.roast || w.why}}</div>
      <div class="cotd-actions">
        ${{careersLink}}
        ${{researchLink}}
        <div class="cotd-nav" style="margin-left:auto;">
          <button onclick="window._cotdPrev()" title="Previous">&#9664;</button>
          <button onclick="window._cotdNext()" title="Next">&#9654;</button>
        </div>
      </div>`;
  }}

  window._cotdPrev = function() {{ idx = (idx - 1 + watchList.length) % watchList.length; render(idx); }};
  window._cotdNext = function() {{ idx = (idx + 1) % watchList.length; render(idx); }};
  render(idx);
}})();

// --- Status changes ---
function changeStatus(select, company) {{
  const newStatus = select.value;
  const card = select.closest('.dd-card');
  if (card) card.dataset.status = newStatus;

  // Persist to localStorage (include score for migration to applications table)
  let changes = JSON.parse(localStorage.getItem('status_changes') || '{{}}');
  const scoreText = card ? (card.querySelector('.score-row span')?.textContent || '').replace('Score: ', '') : '';
  const score = parseFloat(scoreText) || null;
  changes[company] = {{ status: newStatus, date: new Date().toISOString(), score: score }};
  localStorage.setItem('status_changes', JSON.stringify(changes));

  // Visual feedback toast
  const labels = {{ not_applied: 'Not Applied', applied: 'Applied', awaiting: 'Awaiting Response', '1st_interview_scheduled': '1st Interview Scheduled', '1st_interview_held': '1st Interview Held', '2nd_interview_scheduled': '2nd Interview Scheduled', '2nd_interview_held': '2nd Interview Held', '3rd_interview_scheduled': '3rd Interview Scheduled', '3rd_interview_held': '3rd Interview Held', 'final_round_scheduled': 'Final Round Scheduled', 'final_round_held': 'Final Round Held', offer: 'Offer', cold_outreach: 'Speculative', speculative: 'Speculative', rejected: 'Rejected', pass: 'Pass', '1st_interview': '1st Interview', '2nd_interview': '2nd Interview' }};
  showToast(`<strong>${{company}}</strong> → ${{labels[newStatus] || newStatus}}`);

  // Dim card if rejected/pass
  if (newStatus === 'rejected' || newStatus === 'pass') {{
    card.style.opacity = '0.45';
  }} else {{
    card.style.opacity = '1';
  }}

  // Hide/show action item if status is no longer "not_applied"
  renumberCards();
  updateActionItems();
}}

// On load, re-apply saved status changes
(function() {{
  let changes = JSON.parse(localStorage.getItem('status_changes') || '{{}}');
  document.querySelectorAll('.dd-card').forEach(card => {{
    const company = card.dataset.company;
    if (changes[company]) {{
      const sel = card.querySelector('.status-select');
      if (sel) sel.value = changes[company].status;
      card.dataset.status = changes[company].status;
      if (['rejected','pass'].includes(changes[company].status)) card.style.opacity = '0.45';
    }}
  }});
}})();

// --- Dismiss ---
function dismissCard(btn, company) {{
  const card = btn.closest('.dd-card');
  card.classList.add('dismissed');

  let dismissed = JSON.parse(localStorage.getItem('dismissed_jobs') || '[]');
  dismissed.push({{ company: company, date: new Date().toISOString() }});
  localStorage.setItem('dismissed_jobs', JSON.stringify(dismissed));

  showToast(`Dismissed <strong>${{company}}</strong>`, () => undoDismiss(company));
  renumberCards();
  updateActionItems();
}}

function undoDismiss(company) {{
  let dismissed = JSON.parse(localStorage.getItem('dismissed_jobs') || '[]');
  dismissed = dismissed.filter(d => d.company !== company);
  localStorage.setItem('dismissed_jobs', JSON.stringify(dismissed));

  document.querySelectorAll('.dd-card').forEach(card => {{
    if(card.dataset.company === company) card.classList.remove('dismissed');
  }});
  renumberCards();
  updateActionItems();
}}

// On load, purge stale localStorage entries and re-apply valid ones
(function() {{
  // Get all company names currently in the dashboard
  const activeCompanies = new Set();
  document.querySelectorAll('.dd-card[data-company]').forEach(c => activeCompanies.add(c.dataset.company));

  // Purge dismissed entries for companies no longer in the dashboard
  let dismissed = JSON.parse(localStorage.getItem('dismissed_jobs') || '[]');
  dismissed = dismissed.filter(d => activeCompanies.has(d.company));
  localStorage.setItem('dismissed_jobs', JSON.stringify(dismissed));

  // Purge status changes for companies no longer in the dashboard
  let changes = JSON.parse(localStorage.getItem('status_changes') || '{{}}');
  Object.keys(changes).forEach(k => {{ if (!activeCompanies.has(k)) delete changes[k]; }});
  localStorage.setItem('status_changes', JSON.stringify(changes));

  // Re-apply valid dismissed cards
  dismissed.forEach(d => {{
    document.querySelectorAll('.dd-card').forEach(card => {{
      if(card.dataset.company === d.company) card.classList.add('dismissed');
    }});
  }});
  renumberCards();
  updateActionItems();
}})();

// --- Renumber visible cards ---
function renumberCards() {{
  let n = 1;
  document.querySelectorAll('.dd-card').forEach(card => {{
    if (card.classList.contains('dismissed') || card.style.display === 'none') return;
    const rankEl = card.querySelector('.rank');
    if (rankEl) rankEl.textContent = '#' + n;
    n++;
  }});
}}

// --- Sync action items with card states ---
function updateActionItems() {{
  const dismissed = JSON.parse(localStorage.getItem('dismissed_jobs') || '[]').map(d => d.company);
  const changes = JSON.parse(localStorage.getItem('status_changes') || '{{}}');
  let visibleCount = 0;

  document.querySelectorAll('.action-item[data-company]').forEach(item => {{
    const company = item.dataset.company;
    const statusChange = changes[company];
    const isDismissed = dismissed.includes(company);
    const isNoLongerActionable = statusChange && statusChange.status !== 'not_applied';

    if (isDismissed || isNoLongerActionable) {{
      item.style.display = 'none';
    }} else {{
      visibleCount++;
      item.style.display = 'flex';
      // Update priority number
      const priorityEl = item.querySelector('.priority');
      if (priorityEl) priorityEl.textContent = visibleCount;
    }}
  }});

  // If no action items left, show a "caught up" message
  const banner = document.querySelector('.action-banner');
  if (banner && visibleCount === 0) {{
    const existing = banner.querySelector('.caught-up');
    if (!existing) {{
      const msg = document.createElement('div');
      msg.className = 'caught-up';
      msg.style.cssText = 'color:var(--green);font-size:14px;padding:8px 0;';
      msg.textContent = 'All caught up — no pending actions right now.';
      banner.appendChild(msg);
    }}
  }}
}}

// --- Copy file path to clipboard (for .docx links) ---
function copyFilePath(el, path) {{
  navigator.clipboard.writeText(path).then(() => {{
    showToast(`\u2705 Path copied! Open Finder \u2192 <b>Cmd+Shift+G</b> \u2192 paste to open.`);
  }}).catch(() => {{
    // fallback: select a temp input
    const tmp = document.createElement('input');
    tmp.value = path;
    document.body.appendChild(tmp);
    tmp.select();
    document.execCommand('copy');
    tmp.remove();
    showToast(`\u2705 Path copied! Open Finder \u2192 <b>Cmd+Shift+G</b> \u2192 paste to open.`);
  }});
}}

// --- Toast helper ---
function showToast(html, undoFn) {{
  document.querySelectorAll('.toast').forEach(t => t.remove());
  const toast = document.createElement('div');
  toast.className = 'toast';
  const undoBtn = undoFn ? `<button onclick="this.closest('.toast').remove(); (${{undoFn.toString()}})()">Undo</button>` : '';
  toast.innerHTML = `<span>${{html}}</span>${{undoBtn}}`;
  document.body.appendChild(toast);
  setTimeout(() => {{ if(toast.parentNode) toast.remove(); }}, 5000);
}}

// --- Live staleness flags for applications ---
function updateStaleness() {{
  const now = new Date();
  const actions = [];

  document.querySelectorAll('.days-since').forEach(el => {{
    const applied = el.dataset.applied;
    const status = el.dataset.status;
    const followedUp = el.dataset.followedUp || '';
    if (!applied) return;
    const appliedDate = new Date(applied + 'T00:00:00');
    const daysSinceApplied = Math.floor((now - appliedDate) / 86400000);
    el.textContent = daysSinceApplied + 'd';

    const row = el.closest('tr');
    const company = row ? row.querySelector('.company-name')?.textContent : '';

    if (status !== 'awaiting') {{
      el.style.color = 'var(--text-muted)';
      return;
    }}

    // Has a follow-up been sent?
    if (followedUp) {{
      const fuDate = new Date(followedUp + 'T00:00:00');
      const daysSinceFollowUp = Math.floor((now - fuDate) / 86400000);

      if (daysSinceFollowUp >= 14) {{
        // Follow-up sent, 14+ days ago, still no response — time to retire
        el.style.color = 'var(--red)';
        el.style.fontWeight = '600';
        el.title = 'Follow-up sent ' + daysSinceFollowUp + 'd ago with no response — retire?';
        if (company) actions.push({{ company, days: daysSinceApplied, daysSinceFU: daysSinceFollowUp, level: 'retire' }});
      }} else {{
        // Follow-up sent recently — ball is in their court
        el.style.color = 'var(--cyan)';
        el.style.fontWeight = '400';
        el.title = 'Follow-up sent ' + daysSinceFollowUp + 'd ago — waiting for response';
      }}
    }} else {{
      // No follow-up sent
      if (daysSinceApplied >= 30) {{
        el.style.color = 'var(--red)';
        el.style.fontWeight = '600';
        el.title = 'Likely stale — consider follow-up or writing off';
        if (company) actions.push({{ company, days: daysSinceApplied, level: 'stale' }});
      }} else if (daysSinceApplied >= 21) {{
        el.style.color = 'var(--amber)';
        el.style.fontWeight = '600';
        el.title = 'Consider sending a follow-up';
        if (company) actions.push({{ company, days: daysSinceApplied, level: 'followup' }});
      }} else {{
        el.style.color = 'var(--text-muted)';
      }}
    }}
  }});

  // Inject action items into What To Do Next
  const banner = document.querySelector('.action-banner');
  if (banner) {{
    // Remove any previous staleness items
    banner.querySelectorAll('.followup-item').forEach(el => el.remove());

    if (actions.length > 0) {{
      // Sort: retire first, then stale, then followup; within each by days descending
      const levelOrder = {{ retire: 0, stale: 1, followup: 2 }};
      actions.sort((a, b) => {{
        if (a.level !== b.level) return (levelOrder[a.level] || 99) - (levelOrder[b.level] || 99);
        return b.days - a.days;
      }});

      const existing = banner.querySelectorAll('.action-item:not(.followup-item)').length;

      actions.forEach((f, i) => {{
        const div = document.createElement('div');
        div.className = 'action-item followup-item';
        let color, label, badge;
        if (f.level === 'retire') {{
          color = 'var(--red)';
          badge = '<span class="pill pill-red" style="font-size:10px;margin-left:6px">RETIRE</span>';
          label = 'Follow-up sent ' + f.daysSinceFU + 'd ago, ' + f.days + 'd total — time to write off?';
        }} else if (f.level === 'stale') {{
          color = 'var(--red)';
          badge = '<span class="pill pill-red" style="font-size:10px;margin-left:6px">STALE</span>';
          label = f.days + 'd with no response — follow up or write off';
        }} else {{
          color = 'var(--amber)';
          badge = '<span class="pill pill-amber" style="font-size:10px;margin-left:6px">FOLLOW UP</span>';
          label = f.days + 'd with no response — consider a follow-up';
        }}
        div.innerHTML = `<div class="priority" style="color:${{color}}">${{existing + i + 1}}</div><div><strong>${{f.company}}</strong>${{badge}} — ${{label}}</div>`;
        banner.appendChild(div);
      }});

      // Remove "caught up" message if actions exist
      const caughtUp = banner.querySelector('.caught-up');
      if (caughtUp) caughtUp.remove();
    }}
  }}
}}
updateStaleness();

// --- Interview countdown live ticker ---
(function() {{
  const el = document.querySelector('.ib-countdown');
  if (!el) return;
  const deadline = new Date(el.getAttribute('data-deadline')).getTime();
  function tick() {{
    const now = Date.now();
    let d = deadline - now;
    if (d < 0) {{ el.textContent = 'LIVE NOW'; el.classList.add('ib-live'); return; }}
    const days = Math.floor(d / 86400000); d -= days * 86400000;
    const hrs = Math.floor(d / 3600000); d -= hrs * 3600000;
    const mins = Math.floor(d / 60000); d -= mins * 60000;
    const secs = Math.floor(d / 1000);
    el.textContent = (days > 0 ? days + 'd ' : '') + hrs + 'h ' + mins + 'm ' + secs + 's';
  }}
  tick();
  setInterval(tick, 1000);
}})();

// --- Haiku when Tier 1 & 2 are empty ---
(function() {{
  const HAIKU_NEXT_REFRESH = {haiku_next_refresh_js};
  const haiku = [
    "Dust on the mesa\\nravens cross the Sangre line\\nspring returns, so will",
    "Rio Grande cuts deep\\nholding more than any job\\npatience, cold, and time",
    "Taos sun at noon\\nadobe walls drink the heat\\nthe inbox can wait",
    "Piñon smoke at dusk\\npinyon jays call from the sage\\nnothing closes tonight",
    "Full moon on the gorge\\nthe river keeps its schedule\\noffers come in time",
    "Wheeler holds the dawn\\nfirst light before the inbox\\nwalk before the wire",
    "Empty pipeline day\\nsometimes the wire just stays quiet\\ntrust the craft, not noise",
    "ATS ate them all\\nthe haiku survived the sweep\\na small victory",
    "Applied fourteen days\\nthe waiting room is empty\\nsit down, pour water",
    "Sixty yes became\\nthe one that actually stuck\\nkeep throwing the net",
    "The right role is rare\\nthe wrong ones arrive in waves\\nfilter, do not chase",
    "Rejection is data\\nnot personal, not verdict\\nlog it, move along",
    "KSAT to GFW\\nTromsø cold to Taos sun\\nsame hustle, new light",
    "Satellite sees all\\nbut cannot read a resume\\nhumans ghost better",
    "Pilot to precedent\\nENI moved the regulator\\nthe pattern still works",
    "Fishing vessels ghost\\nthe dark fleet at the equator\\nsomeone sees them all",
    "SAR at Tromsø\\noil spills under Arctic cloud\\nbuilt the whole business",
    "Commercial from zero\\nthree times now, at three shops\\nthe map is the man",
    "Shell, ENI, Exxon\\nclosed the first five the hard way\\nthe sixth was simpler",
    "Twenty-five years in\\nstill building something from scratch\\nstill the best version",
    "Telemark turns through\\nlate-spring corn on the south face\\nworth the dawn patrol",
    "Backpack on the trail\\nno cell signal for three days\\nbest interview prep",
    "Pecos in June\\nthunder at three, camp by five\\nsummer's honest deal",
    "A-Basin holds on\\nJune skiing at ten thousand\\nstubborn like the search",
    "Weminuche calls\\na week without a phone or pitch\\nthe answer gets clear",
    "Tuckerman Ravine\\nthe last of April's big bowls\\nworth a redeye flight",
    "The CDT moves\\nthru-hikers through Cumbres today\\nsummer is coming",
    "Wind River high route\\nten days, one sat phone, no signal\\ngood for the soul math",
    "The dashboard refreshes\\ntwelve o eight, twelve o eight daily\\nrhythm holds the work",
    "Morning brief arrives\\nscores, blockers, one-line verdicts\\nopen, read, decide",
    "An em dash appears\\nthe gate catches it and yells loud\\nrewrite at the source",
    "A hard requirement\\ncaps the score at forty-two points\\nthe rubric holds firm",
    "CBAM price drops in\\nseventy-five per the ton\\nthe steel mill writes checks",
    "MethaneSAT is dark\\nthe billion-dollar eye died\\nghost in the pipeline",
    "Taos under wind\\nfire gate closes on the sage\\nforty-five-mile gusts",
    "Kachina is closed\\nthe snow left in early March\\nmud season arrives",
    "Merlin remaps Earth\\ndaily pass at one meter\\norbit holds the plan",
    "Cormac stays in print\\nBlood Meridian rereads\\njudge in the desert",
    "Abbey's ghost still haunts\\nmonkey wrench in the glovebox\\nHayduke would not file",
    "Sangre de Cristo\\nthe peaks hold April's last white\\nsnow line creeps upward",
    "Gorge bridge at high noon\\nhawks ride wind above the scour\\nsix hundred feet down",
    "Tromsø in April\\npolar light returns to sea\\nthe dark was a friend",
    "Forty-eight no thanks\\nforty-ninth still has a pulse\\nkeep the net in play",
    "Fire ban in the sage\\nstatewide, all the fuel too dry\\nspring came in thirsty",
    "EPA repeals\\nendangerment finding gone\\nthe lawsuits begin",
    "By decree it goes\\ndeep-sea mining by April\\nthe seabed gets sold",
    "Tanager finds plumes\\nten methane leaks in the field\\nCalifornia knocks",
    "Cora packs his box\\nten and seventeen broke him\\nTracy gets the keys",
    "Tracy in the chair\\nfive to three on debut night\\nContreras hits one",
    "Lomu in round one\\nUtah tackle plugs the line\\nthe trench gets adult",
    "One percent snowpack\\nSangres east drained out by March\\nthe river runs thin",
    "Palo Flechado\\nfour percent of average\\nthe ditches still wait",
    "Acequias dry\\nrationing in Talpa now\\nfire damage still rules",
    "Artemis returns\\nfour around the moon and home\\nfifty years between",
    "Ten deals took the cake\\ntwenty-eight percent of all\\nlate-stage eats the rest",
    "Brussels punts again\\nEUDR slides a year\\npilots get their breath",
    "Mud splatters the truck\\nApril rolls into a May\\nthat looks like July",
    "Cast wider, he said\\nthe net pulls in stranger fish\\nbreadth before the bite",
    "Corn snow at sunrise\\nspring lines hold above tree line\\ndawn patrol still pays",
    "Viasat goes up\\nFalcon Heavy on the Cape\\ntwenty-seventh dusk",
  ];

  const intros = [
    "Empty top tiers. Haiku took the shift.",
    "Pipeline's clean. Have a haiku.",
    "April mud, April quiet. A haiku holds the line.",
    "Tier 1 and 2 are empty. The land provides a haiku.",
    "No opportunities worth chasing right now. Haiku break.",
    "The pipeline will refill. Until then:",
    "Zero ranked. Maximum haiku.",
    "No offers to chew on. A haiku to sit with.",
    "All quiet on the pipeline front. Haiku dispatch:",
    "Tier 1: empty. Tier 2: empty. Tier haiku: full.",
    "The dashboard rests. The poet does not.",
    "Scoreboard's blank today. Let the poem fill the hole.",
    "Your pipeline called in sick today. Haiku showed up instead.",
    "Between waves. A haiku to hold the space.",
    "The mesa wind ran the screener today. Nothing made the cut except this.",
    "The ATS ate them all. The haiku survived.",
    "Trump signed the deep-sea mining order Friday. ISA gets bypassed, the seabed gets sold by decree. Pipeline ran quiet anyway. Haiku held.",
    "MethaneSAT went dark in orbit. CBAM hit seventy-five a ton. Your old world keeps shifting. Pipeline quiet. Haiku shows up.",
    "Brussels punted EUDR another year. The pipeline did not blink. Haiku holds.",
    "Tanager-1 caught ten methane leaks for California's air board. Microsoft buys ninety percent of the carbon market by itself now. Pipeline quiet. Haiku stretches.",
    "Virginia redrew four House seats in a single referendum. Pipeline did not flinch. Haiku keeps count.",
    "Cora got fired Saturday night, ten and seventeen out of the gate. Tracy ran the bench Sunday and won five to three behind a Contreras homer. Pipeline ran quiet. Haiku showed up.",
    "Sangres east at one percent of normal snowpack. Palo Flechado at four. Acequias rationing in Talpa already. The water year is the story now. Pipeline quiet. Haiku holds.",
    "EDF and fifteen co-petitioners filed against the EPA endangerment repeal April sixteenth. The litigation calendar is the work now. Pipeline quiet. Haiku on the wall.",
    "Patriots took Caleb Lomu in the first round. Trench got an adult. Pipeline did not. Haiku covers the gap.",
    "Artemis 2 came back from the moon April first, four humans, fifty years between. Pipeline quiet that week too. Haiku still here.",
  ];

  const grid = document.querySelector('.dd-grid');
  const slot = document.getElementById('haiku-slot');
  const text = document.getElementById('haiku-text');
  const sourceEl = document.getElementById('haiku-source');
  const counter = document.getElementById('haiku-counter');
  const refreshBtn = document.getElementById('haiku-refresh');

  // Helpers: haiku entries are either plain strings or {{t, u, s}} objects with optional source link
  function haikuText(item) {{ return (typeof item === 'string') ? item : item.t; }}
  function haikuUrl(item)  {{ return (typeof item === 'string') ? null : (item.u || null); }}
  function haikuSrc(item)  {{ return (typeof item === 'string') ? null : (item.s || null); }}

  // No-repeat cycle: pick from unseen pool tracked in localStorage.
  // v6 (2026-04-27): tracks seen by content hash, not array index. Index-based
  // tracking broke whenever the daily refresh added/removed haikus, because the
  // same index pointed to different content the next day. Hash tracking survives
  // pool churn: a haiku you've seen stays "seen" even after it shifts position
  // or disappears and reappears.
  const POOL_KEY = 'dashHaikuSeen_v6';
  const INTRO_KEY = 'dashIntroSeen_v6';
  const POOL_SIG_KEY = 'dashHaikuSig_v6';
  const INTRO_SIG_KEY = 'dashIntroSig_v6';
  const HAIKU_POOL_VERSION = 'v6-hash';
  const INTRO_POOL_VERSION = 'v6-hash';
  const poolSig = HAIKU_POOL_VERSION;
  const introSig = INTRO_POOL_VERSION;

  // In-memory backup (across clicks within one page session) in case localStorage fails
  let memSeenHaiku = null;
  let memSeenIntro = null;

  // djb2 hash, deterministic, base36 short string. Used as the seen-set key for each item.
  function poolItemKey(item) {{
    const s = (typeof item === 'string') ? item : (item.t || JSON.stringify(item));
    let h = 5381;
    for (let i = 0; i < s.length; i++) {{ h = ((h << 5) + h + s.charCodeAt(i)) | 0; }}
    return (h >>> 0).toString(36);
  }}

  function pickUnseen(pool, seenKey, sigKey, currentSig, memRef) {{
    let seen = [];
    let lsWorked = false;
    try {{
      if (localStorage.getItem(sigKey) !== currentSig) {{
        localStorage.setItem(sigKey, currentSig);
        localStorage.removeItem(seenKey);
      }}
      const raw = localStorage.getItem(seenKey);
      seen = raw ? JSON.parse(raw) : [];
      // Defense: if old index-based entries leaked in, drop them.
      seen = seen.filter(x => typeof x === 'string');
      lsWorked = true;
    }} catch(e) {{ lsWorked = false; }}
    if (!lsWorked) seen = memRef.value || [];

    const seenSet = new Set(seen);
    let unseenIdx = [];
    for (let i = 0; i < pool.length; i++) {{
      if (!seenSet.has(poolItemKey(pool[i]))) unseenIdx.push(i);
    }}

    // Pool exhausted: every current haiku has been seen. Don't reset (Paul's rule:
    // never see the same one twice). Show a random one without adding it to seen,
    // and flag the state so the caller can render an "all caught up" hint.
    if (unseenIdx.length === 0) {{
      const idx = Math.floor(Math.random() * pool.length);
      memRef.value = seen;
      return {{ item: pool[idx], seenCount: seen.length, total: pool.length, exhausted: true }};
    }}

    const idx = unseenIdx[Math.floor(Math.random() * unseenIdx.length)];
    seen.push(poolItemKey(pool[idx]));
    if (lsWorked) {{
      try {{ localStorage.setItem(seenKey, JSON.stringify(seen)); }} catch(e) {{}}
    }}
    memRef.value = seen;
    return {{ item: pool[idx], seenCount: seen.length, total: pool.length, exhausted: false }};
  }}

  function renderHaiku() {{
    const hMem = {{ value: memSeenHaiku }};
    const iMem = {{ value: memSeenIntro }};
    const h = pickUnseen(haiku, POOL_KEY, POOL_SIG_KEY, poolSig, hMem);
    const i = pickUnseen(intros, INTRO_KEY, INTRO_SIG_KEY, introSig, iMem);
    memSeenHaiku = hMem.value;
    memSeenIntro = iMem.value;

    // Pool exhausted: do NOT render an old haiku. Paul's rule is no repeats.
    // Show a quiet "all caught up" message instead. The refresh button is
    // disabled until the next pipeline run adds new haiku.
    if (h.exhausted) {{
      text.innerHTML = '<div style="color:var(--text-muted);font-size:13px;font-style:normal;opacity:0.7;">all ' + h.total + ' seen \u00b7 next batch arrives ' + HAIKU_NEXT_REFRESH + '</div>';
      if (sourceEl) {{ sourceEl.innerHTML = ''; sourceEl.style.display = 'none'; }}
      if (counter) {{ counter.textContent = ''; }}
      if (refreshBtn) {{ refreshBtn.disabled = true; refreshBtn.style.opacity = '0.4'; refreshBtn.style.cursor = 'not-allowed'; }}
      return;
    }}

    if (refreshBtn) {{ refreshBtn.disabled = false; refreshBtn.style.opacity = ''; refreshBtn.style.cursor = ''; }}
    const introText = haikuText(i.item);
    const bodyText = haikuText(h.item);
    const url = haikuUrl(h.item);
    const srcName = haikuSrc(h.item) || 'source';
    text.innerHTML = '<div style="color:var(--cyan);font-size:12px;margin-bottom:10px;font-style:normal;">' + introText + '</div>' + bodyText;
    if (sourceEl) {{
      if (url) {{
        sourceEl.innerHTML = '<a href="' + url + '" target="_blank" rel="noopener noreferrer" style="color:var(--text-muted);text-decoration:none;border-bottom:1px dotted var(--border);">\u2192 ' + srcName + '</a>';
        sourceEl.style.display = 'block';
      }} else {{
        sourceEl.innerHTML = '';
        sourceEl.style.display = 'none';
      }}
    }}
    if (counter) {{
      counter.textContent = h.seenCount + '/' + h.total + ' this cycle';
    }}
  }}

  if (slot && text && grid) {{
    const cards = grid.querySelectorAll('.dd-card');
    if (cards.length === 0) {{
      renderHaiku();
      slot.style.display = 'block';
      if (refreshBtn) refreshBtn.addEventListener('click', renderHaiku);
    }}
  }}
}})();
</script>

<script>
// --- New England Sportsball (live widget) ---
// Two data sources:
//   1. ESPN public JSON — used ONLY for live game state (in-progress score, final, upcoming).
//      Browser-side fetch (ESPN returns CORS headers). If ESPN is unreachable we just skip.
//   2. An embedded `sports_feed` block from dashboard-data.json, refreshed by the
//      `refresh-sports-feed` scheduled task. Each item has a source outlet, a headline,
//      a URL, and a Claude-written snarky take. This is where the diversity of voice lives
//      (Over the Monster, Pats Pulpit, MassLive, WEEI, BSJ, The Ringer, Globe, NESN, etc.).
//      A sibling sports-feed.json is re-polled every 3 min so fresh items land without a reload.
(async function() {{
  const $sox  = document.getElementById('ne-sox');
  const $pats = document.getElementById('ne-pats');
  if (!$sox || !$pats) return;

  // FEED is the baked-in snapshot of sports-feed data at build time.
  // We also poll ./sports-feed.json every 3 minutes so fresh items land without a reload.
  let FEED = {sports_feed_json};

  // Pre-computed at build time from the personal-feeds cron schedule. Used as
  // the footer tag on Industry/Outdoors tiles since renderFeedCard rewrites
  // their innerHTML on every paint and would wipe out a static tag.
  const PERSONAL_NEXT_REFRESH = {personal_next_refresh_js};

  // ---- Snark templates for live game state (per-team) — Barstool-adjacent bar-stool-podcast voice.
  const TPL = {{
    sox: {{
      liveWin:  ["Up {{margin}}. Don't get too hard yet, the bullpen's warming.",
                 "Leading {{margin}} — cardiologists and divorce lawyers on standby.",
                 "{{margin}}-run lead. Enjoy the 20 minutes before we throw it all away.",
                 "Cruising at {{margin}}. Don't look directly at the bullpen or you'll jinx it.",
                 "Sox ahead {{margin}}. Actual baseball is occurring at Fenway. Call your mother.",
                 "Up {{margin}}. This is the part where we pretend we've been calm the whole time."],
      liveLose: ["Down {{margin}}. Rotation's cooked, bullpen's cooked, my chicken wings are cooked.",
                 "Trailing {{margin}}. These guys couldn't hit water from a boat.",
                 "Losing {{margin}}. Somebody in the dugout forgot the bats are supposed to make contact.",
                 "Behind {{margin}}. Would someone — anyone — explain 'hitting' to this lineup?",
                 "Down {{margin}}. This team is softer than a Tinder bio.",
                 "Trailing {{margin}}. The Monster is still green. Everything else is on fire."],
      liveTied: ["Tied {{score}}. A drawn-out form of suffering, available on NESN.",
                 "Knotted at {{score}}. Nothing matters until the 8th. Pour another one.",
                 "Even at {{score}}. The stomach lining is the real underdog tonight."],
      finalW:   ["Won {{score}}. Mark the calendar and text your ex.",
                 "{{score}} W. Hot take: hitting is a skill — somebody finally told them.",
                 "Sox {{score}}. Enjoy the 14 hours before something breaks.",
                 "Took it {{score}}. Standings briefly make sense. Do not trust it.",
                 "{{score}} W. Write it down. Frame it. Show the grandkids."],
      finalL:   ["Lost {{score}}. Papi is not walking through that door. Neither is the rotation.",
                 "Dropped {{score}}. The bullpen owes Fenway a refund and a formal apology.",
                 "{{score}} loss. Who scripted this rotation — a ransom note written by a drunk?",
                 "Fell {{score}}. Baseball is a mystery. This loss is not. This loss is obvious.",
                 "Lost {{score}}. Fire everyone. Start with accounting, work down."],
      sched:    ["{{home}} · first pitch {{time}}. Try not to pre-grieve. It's only April.",
                 "{{home}} at {{time}}. Manage expectations like a professional drinker.",
                 "Gametime {{time}} {{home}}. Buckle in. Lightly. No sudden moves.",
                 "{{home}} · {{time}}. Bring a beer, bring a sedative, bring both."],
      off:      ["Quiet day at Fenway. Bullpen is resting. Metaphorically.",
                 "Dark day. Small mercies.",
                 "Off day. Use the time to update your grievance list.",
                 "No game. The bats couldn't find it anyway."]
    }},
    pats: {{
      liveWin:  ["Up {{margin}}. Vrabel permits himself half a smile. Terrifying.",
                 "Leading {{margin}}. Maye is doing Maye things. Jets fans are crying.",
                 "Ahead {{margin}}. The Belichick clouds briefly part. Clouds return Thursday.",
                 "Up {{margin}}. Somewhere a 'Tommy from Quincy' is yelling into a phone.",
                 "{{margin}}-point lead. Brand is back. Briefly."],
      liveLose: ["Down {{margin}}. This is why we moved to New Mexico.",
                 "Trailing {{margin}}. Bench somebody. Anybody. Bench the equipment manager.",
                 "Behind {{margin}}. The secondary could not cover a picnic blanket in a hurricane.",
                 "Down {{margin}}. The offensive line is blocking like it's a group project.",
                 "Losing {{margin}}. Burn the tape. Keep the draft picks. Burn the tape again."],
      liveTied: ["Tied {{score}}. Football is doing its thing.",
                 "Knotted at {{score}}. Coin-flip football. Pour a second one.",
                 "Even at {{score}}. This will end badly. Or excellently. Probably badly."],
      finalW:   ["Won {{score}}. The brand is back, briefly. Buy merch now.",
                 "{{score}} W. Everyone calm down. Nobody will.",
                 "Took it {{score}}. Jets fans are already blaming their GM. Again."],
      finalL:   ["Lost {{score}}. Same old story, new uniforms, same bad defense.",
                 "Dropped {{score}}. Burn the tape. Keep the Krafts. Kidding.",
                 "{{score}} loss. Somebody tell Maye to lawyer up before the next offensive coordinator arrives."],
      sched:    ["{{home}} on {{day}}. Hopes managed, beverages stockpiled, Sundays cleared.",
                 "{{home}} — {{day}}. Low expectations, high fiber, bigger beer.",
                 "{{home}} · {{day}}. Bet the under on Patriots words spoken in the presser."],
      off:      ["No football. Vrabel's in the film room muttering about leverage and bench press.",
                 "Offseason. Enjoy the calm before Maye's cap chart lands.",
                 "Dark Sunday. Someone in Foxborough is already angry. Always angry.",
                 "Offseason. The Krafts are counting something, somewhere, slowly.",
                 "No game. OTA leaks are the real content. They are also fake."]
    }}
  ,
    industry: {{
      off: ["Industry feed quiet. Constellations still in orbit, ocean still getting fished.",
            "No fresh takes on the wire. Somewhere a regulator is still drafting a comment.",
            "Space industry inbox: empty. Paul's former colleagues: still employed (probably)."]
    }},
    outdoor: {{
      off: ["Outdoor feed quiet. Somewhere, a ski patroller is probing a cornice.",
            "No fresh powder takes on the wire. Check back when the snow starts flying.",
            "Trail reports loading. Go stretch your calves."]
    }},
    recipe: {{
      off: ["Recipe queue empty. Consider takeout.",
            "No candidates on the wire. Open the fridge and start there.",
            "Chef's taking a break. Algorithms too."]
    }}
  }};

  function pick(arr) {{ return arr[Math.floor(Math.random() * arr.length)]; }}
  function fmt(s, v) {{ return s.replace(/\{{(\w+)\}}/g, (_,k) => (v[k] ?? '')); }}
  function escapeHtml(s) {{
    return String(s).replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}})[c]);
  }}
  function humanAgo(d) {{
    const s = (Date.now() - d.getTime()) / 1000;
    if (s < 60)    return Math.floor(s) + 's ago';
    if (s < 3600)  return Math.floor(s/60) + 'm ago';
    if (s < 86400) return Math.floor(s/3600) + 'h ago';
    return Math.floor(s/86400) + 'd ago';
  }}

  async function fetchJSON(url, timeoutMs) {{
    try {{
      const ctl = new AbortController();
      const t = setTimeout(() => ctl.abort(), timeoutMs || 5000);
      const r = await fetch(url, {{ cache: 'no-store', signal: ctl.signal }});
      clearTimeout(t);
      if (!r.ok) return null;
      return await r.json();
    }} catch(e) {{ return null; }}
  }}

  function findRelevantEvent(schedule) {{
    const events = schedule?.events || schedule?.team?.events || [];
    if (!events.length) return null;
    const now = Date.now();
    // in-progress wins
    for (const ev of events) {{
      const st = ev.competitions?.[0]?.status?.type?.state;
      if (st === 'in') return ev;
    }}
    // upcoming within 30h
    const upcoming = events
      .filter(ev => {{ const t = new Date(ev.date).getTime(); return t > now && t - now < 30*3600*1000; }})
      .sort((a,b) => new Date(a.date) - new Date(b.date));
    if (upcoming.length) return upcoming[0];
    // recent final within 20h
    const recent = events
      .filter(ev => {{ const t = new Date(ev.date).getTime();
        return ev.competitions?.[0]?.status?.type?.state === 'post' && now - t < 20*3600*1000; }})
      .sort((a,b) => new Date(b.date) - new Date(a.date));
    if (recent.length) return recent[0];
    // next scheduled (any future) — for the scheduled fallback
    const future = events
      .filter(ev => new Date(ev.date).getTime() > now)
      .sort((a,b) => new Date(a.date) - new Date(b.date));
    if (future.length) return future[0];
    return null;
  }}

  // Find the next upcoming event regardless of time window. Used for the small
  // "next game" footer line so the widget can show pitcher matchups days in advance.
  function findNextUpcoming(schedule, excludeId) {{
    const events = schedule?.events || schedule?.team?.events || [];
    const now = Date.now();
    const future = events
      .filter(ev => new Date(ev.date).getTime() > now && ev.id !== excludeId)
      .sort((a,b) => new Date(a.date) - new Date(b.date));
    return future[0] || null;
  }}

  // ESPN score field shape varies by endpoint:
  //   missing (live game on /teams/<id>/schedule)
  //   string "4" or number 4 (summary endpoint / some scoreboards)
  //   {{value: 4, displayValue: "4"}} object (completed games on schedule endpoint)
  function extractScore(s) {{
    if (s == null) return null;
    if (typeof s === 'number') return s;
    if (typeof s === 'string') {{ const n = parseInt(s, 10); return Number.isNaN(n) ? null : n; }}
    if (typeof s === 'object') {{
      if (typeof s.value === 'number') return s.value;
      if (s.displayValue != null) {{ const n = parseInt(s.displayValue, 10); return Number.isNaN(n) ? null : n; }}
    }}
    return null;
  }}

  // /teams/<id>/schedule does not include scores for live games. Patch in the
  // running score from /summary?event=<id>. Ignores completed/scheduled games.
  async function enrichLiveScore(ev, sportPath) {{
    if (!ev || ev.competitions?.[0]?.status?.type?.state !== 'in') return ev;
    try {{
      const url = 'https://site.api.espn.com/apis/site/v2/sports/' + sportPath + '/summary?event=' + ev.id;
      const data = await fetchJSON(url);
      const sumComps = data?.header?.competitions?.[0]?.competitors || [];
      const evComps = ev.competitions?.[0]?.competitors || [];
      for (const ec of evComps) {{
        const match = sumComps.find(sc => sc.id === ec.id || sc.team?.id === ec.team?.id);
        if (match && match.score != null) ec.score = match.score;
      }}
    }} catch(e) {{ /* network/parse error, fall back to 0-0 */ }}
    return ev;
  }}

  function gameInfo(ev, teamId) {{
    if (!ev) return null;
    const comp = ev.competitions?.[0]; if (!comp) return null;
    const status = comp.status?.type || {{}};
    const state  = status.state || 'pre';
    const comps  = comp.competitors || [];
    const us   = comps.find(c => c.team?.id === String(teamId));
    const them = comps.find(c => c.team?.id !== String(teamId));
    if (!us || !them) return null;
    const usScore   = extractScore(us.score) ?? 0;
    const themScore = extractScore(them.score) ?? 0;
    const homeAway  = us.homeAway || 'home';
    // Probable pitchers (if ESPN has posted them). Each competitor may have probables.
    const probName = (c) => {{
      const p = (c.probables || [])[0];
      if (!p) return null;
      return p.athlete?.shortName || p.athlete?.displayName || p.shortName || p.name || null;
    }};
    return {{
      state,
      usScore, themScore,
      usWin: us.winner === true,
      homeAway,
      opp: them.team?.displayName || them.team?.abbreviation || '',
      oppAbbrev: them.team?.abbreviation || them.team?.displayName || '',
      date: new Date(ev.date),
      link: ev.links?.[0]?.href || comp.links?.[0]?.href || '',
      detail: status.shortDetail || status.detail || '',
      usPitcher: probName(us),
      themPitcher: probName(them),
      usAbbrev: us.team?.abbreviation || ''
    }};
  }}

  function renderGameCard($el, teamKey, g, teamLabel) {{
    const tpl = TPL[teamKey];
    const vsAt = g.homeAway === 'home' ? 'vs ' + g.oppAbbrev : '@ ' + g.oppAbbrev;
    let state, line, snark;
    if (g.state === 'in') {{
      const margin = Math.abs(g.usScore - g.themScore);
      const score  = g.usScore + '-' + g.themScore;
      const pool = g.usScore > g.themScore ? tpl.liveWin
                 : g.usScore < g.themScore ? tpl.liveLose
                 : tpl.liveTied;
      state = 'LIVE'; line = teamLabel + ' ' + score + ' ' + vsAt + ' · ' + g.detail;
      snark = fmt(pick(pool), {{margin, score, opp: g.opp}});
    }} else if (g.state === 'post') {{
      const score = g.usScore + '-' + g.themScore;
      const won = g.usWin || g.usScore > g.themScore;
      state = 'FINAL'; line = teamLabel + ' ' + (won?'W':'L') + ' ' + score + ' ' + vsAt;
      snark = fmt(pick(won ? tpl.finalW : tpl.finalL), {{score, opp: g.opp}});
    }} else if (g.state === 'pre') {{
      const now = Date.now(); const ms = g.date.getTime() - now;
      if (ms > 30*3600*1000) return false; // too far out, defer to news rotation
      const time = g.date.toLocaleTimeString('en-US',{{hour:'numeric',minute:'2-digit'}});
      const day  = g.date.toLocaleDateString('en-US',{{weekday:'short',month:'short',day:'numeric'}});
      state = 'NEXT UP'; line = vsAt + ' · ' + day + ' ' + time;
      snark = fmt(pick(tpl.sched), {{time, day, home: vsAt, opp: g.opp}});
    }} else {{
      return false;
    }}
    const cls = state === 'LIVE' ? 'live' : state === 'FINAL' ? 'final' : 'scheduled';
    // Small secondary pitcher line: "BOS TBD vs NYY C. Schlittler" when probables are known
    let pitcherLine = '';
    if (g.state === 'in' || g.state === 'pre') {{
      const usName   = g.usPitcher   || 'TBD';
      const themName = g.themPitcher || 'TBD';
      if (g.usPitcher || g.themPitcher) {{
        // home/away ordering: show away pitcher on left, home on right (matches convention)
        const awayAbbrev = g.homeAway === 'home' ? g.oppAbbrev : g.usAbbrev;
        const awayName   = g.homeAway === 'home' ? themName : usName;
        const homeAbbrev = g.homeAway === 'home' ? g.usAbbrev : g.oppAbbrev;
        const homeName   = g.homeAway === 'home' ? usName : themName;
        pitcherLine = '<div class="ne-pitchers">' + escapeHtml(awayAbbrev + ' ' + awayName + ' @ ' + homeAbbrev + ' ' + homeName) + '</div>';
      }}
    }}
    $el.innerHTML =
      '<div class="ne-row1">'
      + '<span class="ne-team-name">' + escapeHtml(teamLabel) + '</span>'
      + '<span class="ne-state ne-state-' + cls + '">' + state + '</span>'
      + '</div>'
      + '<div class="ne-game ne-fade">' + escapeHtml(line) + '</div>'
      + '<div class="ne-snark ne-fade">' + escapeHtml(snark) + '</div>'
      + pitcherLine
      + (g.link ? '<div class="ne-link"><a href="' + g.link + '" target="_blank" rel="noopener">ESPN box &rarr;</a></div>' : '');
    return true;
  }}

  // Build the small footer line that rides below the news card.
  // Shows the most useful game context given what's happening:
  //   - Just ended (final < 20h ago): "Final: L 0-4 vs NYY · Next: vs NYY Thu 6:10pm · NYY Schlittler @ BOS TBD"
  //   - Upcoming (pre): "Next: vs NYY Thu 6:10pm · NYY Schlittler @ BOS TBD"
  //   - Nothing near: empty string (no footer)
  function buildGameFooter(current, next) {{
    const fmtDay  = (d) => d.toLocaleDateString('en-US',{{weekday:'short',month:'short',day:'numeric'}});
    const fmtTime = (d) => d.toLocaleTimeString('en-US',{{hour:'numeric',minute:'2-digit'}});
    const probStr = (g) => {{
      if (!g) return '';
      const usName   = g.usPitcher   || 'TBD';
      const themName = g.themPitcher || 'TBD';
      if (!g.usPitcher && !g.themPitcher) return '';
      const awayAbbrev = g.homeAway === 'home' ? g.oppAbbrev : g.usAbbrev;
      const awayName   = g.homeAway === 'home' ? themName : usName;
      const homeAbbrev = g.homeAway === 'home' ? g.usAbbrev : g.oppAbbrev;
      const homeName   = g.homeAway === 'home' ? usName : themName;
      return awayAbbrev + ' ' + awayName + ' @ ' + homeAbbrev + ' ' + homeName;
    }};

    const gameLine = (g) => {{
      const vsAt = g.homeAway === 'home' ? 'vs ' + g.oppAbbrev : '@ ' + g.oppAbbrev;
      return 'Next: ' + vsAt + ' ' + fmtDay(g.date) + ' ' + fmtTime(g.date);
    }};
    const parts = [];
    if (current && current.state === 'post') {{
      // Post-game: show Final line, THEN the next game if we have one
      const vsAt = current.homeAway === 'home' ? 'vs ' + current.oppAbbrev : '@ ' + current.oppAbbrev;
      const score = current.usScore + '-' + current.themScore;
      const won = current.usWin || current.usScore > current.themScore;
      parts.push('Final: ' + (won?'W':'L') + ' ' + score + ' ' + vsAt);
      if (next) {{
        parts.push(gameLine(next));
        const prob = probStr(next);
        if (prob) parts.push(prob);
      }}
    }} else if (current && current.state === 'pre') {{
      // Upcoming: current IS the next game. Do not skip it for a later one.
      parts.push(gameLine(current));
      const prob = probStr(current);
      if (prob) parts.push(prob);
    }} else if (next) {{
      // No relevant current event; fall back to whatever is next
      parts.push(gameLine(next));
      const prob = probStr(next);
      if (prob) parts.push(prob);
    }}
    return parts.join(' · ');
  }}

  function renderFeedCard($el, teamKey, items, teamLabel, footerText) {{
    const tpl = TPL[teamKey];
    if (!items || items.length === 0) {{
      $el.innerHTML =
        '<div class="ne-row1">'
        + '<span class="ne-team-name">' + escapeHtml(teamLabel) + '</span>'
        + '<span class="ne-state ne-state-quiet">QUIET</span>'
        + '</div>'
        + '<div class="ne-game">No fresh takes on the wire.</div>'
        + '<div class="ne-snark">' + escapeHtml(pick(tpl.off)) + '</div>'
        + (footerText ? '<div class="ne-pitchers">' + escapeHtml(footerText) + '</div>' : '');
      return;
    }}
    let idx = Math.floor(Math.random() * items.length);
    function paint() {{
      const a = items[idx % items.length];
      idx++;
      const hl     = a.headline || a.title || '';
      const source = a.source || 'wire';
      const snark  = a.snark || '';
      const url    = a.url || '';
      const pub    = a.published ? new Date(a.published) : null;
      const ago    = pub && !isNaN(pub) ? ' · ' + humanAgo(pub) : '';
      $el.innerHTML =
        '<div class="ne-row1">'
        + '<span class="ne-team-name">' + escapeHtml(teamLabel) + '</span>'
        + '<span class="ne-state ne-state-news">' + escapeHtml(source.toUpperCase()) + escapeHtml(ago) + '</span>'
        + '</div>'
        + '<div class="ne-game ne-fade">' + escapeHtml(hl) + '</div>'
        + '<div class="ne-snark ne-fade">' + escapeHtml(snark) + '</div>'
        + (url ? '<div class="ne-link"><a href="' + url + '" target="_blank" rel="noopener">' + escapeHtml(source) + ' &rarr;</a></div>' : '')
        + (footerText ? '<div class="ne-pitchers">' + escapeHtml(footerText) + '</div>' : '');
    }}
    paint();
    // Rotate headlines every ~20s so the card feels alive without being jittery; pause on hover.
    // Also track the active interval id on the element so we can clear it when FEED changes.
    if ($el._neTimer) clearInterval($el._neTimer);
    $el._neTimer = setInterval(paint, 40000);
    $el.addEventListener('mouseenter', () => {{ if ($el._neTimer) clearInterval($el._neTimer); $el._neTimer = null; }});
    $el.addEventListener('mouseleave', () => {{ if (!$el._neTimer) $el._neTimer = setInterval(paint, 40000); }});
  }}

  async function refresh() {{
    // Fire both ESPN fetches in parallel; slow ones will just be skipped.
    const [soxSched, patsSched] = await Promise.all([
      fetchJSON('https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/teams/2/schedule'),
      fetchJSON('https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/17/schedule'),
    ]);
    const soxEv  = findRelevantEvent(soxSched);
    const patsEv = findRelevantEvent(patsSched);
    // For live games the schedule endpoint omits scores; patch them in from /summary.
    await Promise.all([
      enrichLiveScore(soxEv,  'baseball/mlb'),
      enrichLiveScore(patsEv, 'football/nfl'),
    ]);
    const soxG  = gameInfo(soxEv,  2);
    const patsG = gameInfo(patsEv, 17);

    // For non-live states, we prefer the news feed as the main card and park
    // the game context in a small footer line. The MLB season has 162 games, so
    // "NEXT UP" as the whole card between days leaves the widget wilting.
    const soxNext  = gameInfo(findNextUpcoming(soxSched,  soxEv && soxEv.id),  2);
    const patsNext = gameInfo(findNextUpcoming(patsSched, patsEv && patsEv.id), 17);
    const soxFooter  = buildGameFooter(soxG,  soxNext);
    const patsFooter = buildGameFooter(patsG, patsNext);

    const soxItems  = (FEED.sox  && FEED.sox.items)  || [];
    const patsItems = (FEED.pats && FEED.pats.items) || [];

    // LIVE: show score card (full treatment). Otherwise: news feed + small game footer.
    if (soxG && soxG.state === 'in') {{
      if (!renderGameCard($sox, 'sox', soxG, 'Red Sox')) renderFeedCard($sox, 'sox', soxItems, 'Red Sox', soxFooter);
    }} else {{
      renderFeedCard($sox, 'sox', soxItems, 'Red Sox', soxFooter);
    }}
    if (patsG && patsG.state === 'in') {{
      if (!renderGameCard($pats, 'pats', patsG, 'Patriots')) renderFeedCard($pats, 'pats', patsItems, 'Patriots', patsFooter);
    }} else {{
      renderFeedCard($pats, 'pats', patsItems, 'Patriots', patsFooter);
    }}

    // Industry and Outdoor tiles: pure feed cards, no game state
    const $industry = document.getElementById('ne-industry');
    const $outdoor  = document.getElementById('ne-outdoor');
    const indItems = (FEED.industry && FEED.industry.items) || [];
    const outItems = (FEED.outdoor  && FEED.outdoor.items)  || [];
    const personalFeedFooter = 'next refresh: ' + PERSONAL_NEXT_REFRESH;
    if ($industry) renderFeedCard($industry, 'industry', indItems, 'Industry', personalFeedFooter);
    if ($outdoor)  renderFeedCard($outdoor,  'outdoor',  outItems, 'Outdoors', personalFeedFooter);

    // Recipe tile: haiku-style manual scroll, NOT auto-rotating
    const $recipe = document.getElementById('ne-recipe');
    const recItems = (FEED.recipe && FEED.recipe.items) || [];
    if ($recipe) renderScrollTile($recipe, recItems, 'recipe', 'Recipe');
  }}

  // Generic scroll tile: haiku-style cycle through a cached array with prev/next buttons.
  // Used by the Recipe tile.
  // feedKey is 'recipe'; idLabel matches the button IDs (ne-<feedKey>-prev, -next, -counter).
  const _scrollIdx = {{}};
  function renderScrollTile($el, items, feedKey, teamLabel) {{
    if (!_scrollIdx[feedKey]) _scrollIdx[feedKey] = 0;
    if ($el._scrollWired !== feedKey) {{
      $el._scrollWired = feedKey;
      const prevBtn = $el.querySelector('#ne-' + feedKey + '-prev');
      const nextBtn = $el.querySelector('#ne-' + feedKey + '-next');
      const getLen = () => (FEED[feedKey]?.items?.length || 1);
      if (prevBtn) prevBtn.addEventListener('click', () => {{ _scrollIdx[feedKey] = (_scrollIdx[feedKey] - 1 + getLen()) % getLen(); paintScroll($el, feedKey, teamLabel); }});
      if (nextBtn) nextBtn.addEventListener('click', () => {{ _scrollIdx[feedKey] = (_scrollIdx[feedKey] + 1) % getLen(); paintScroll($el, feedKey, teamLabel); }});
    }}
    // Reset index if it overflows (feed updated with fewer items)
    if (_scrollIdx[feedKey] >= items.length) _scrollIdx[feedKey] = 0;
    paintScroll($el, feedKey, teamLabel);
  }}
  function paintScroll($el, feedKey, teamLabel) {{
    const items = (FEED[feedKey] && FEED[feedKey].items) || [];
    const counter = $el.querySelector('#ne-' + feedKey + '-counter');
    if (!items.length) {{
      const gameEl  = $el.querySelector('.ne-game');  if (gameEl)  gameEl.textContent  = 'No items loaded yet.';
      const snarkEl = $el.querySelector('.ne-snark'); if (snarkEl) snarkEl.textContent = pick(TPL[feedKey]?.off || ['Feed empty.']);
      if (counter) counter.textContent = '';
      return;
    }}
    const idx = _scrollIdx[feedKey];
    const item = items[idx % items.length];
    const stateEl = $el.querySelector('.ne-state');
    if (stateEl) {{
      stateEl.className = 'ne-state ne-state-news';
      const src = (item.source || teamLabel).toUpperCase();
      const pub = item.published ? new Date(item.published) : null;
      const ago = pub && !isNaN(pub) ? ' · ' + humanAgo(pub) : '';
      stateEl.textContent = src + ago;
    }}
    const gameEl = $el.querySelector('.ne-game');
    if (gameEl) gameEl.textContent = item.title || item.headline || '';
    const snarkEl = $el.querySelector('.ne-snark');
    if (snarkEl) snarkEl.textContent = item.note || item.snark || '';
    let linkEl = $el.querySelector('.ne-link');
    if (item.url) {{
      if (!linkEl) {{
        linkEl = document.createElement('div');
        linkEl.className = 'ne-link';
        const controls = $el.querySelector('.ne-recipe-controls');
        $el.insertBefore(linkEl, controls);
      }}
      linkEl.innerHTML = '<a href="' + item.url + '" target="_blank" rel="noopener">' + escapeHtml(item.source || teamLabel) + ' &rarr;</a>';
    }} else if (linkEl) {{
      linkEl.remove();
    }}
    if (counter) counter.textContent = (idx + 1) + ' of ' + items.length;
  }}

  // Poll the separately-published sports-feed.json (same origin on GitHub Pages) so a
  // scheduled task running every ~30 min can surface fresh items into an already-open dashboard.
  async function pollFeed() {{
    try {{
      const cb = '?t=' + Date.now();
      const [sportsR, industryR, outdoorR, recipeR] = await Promise.all([
        fetch('./sports-feed.json'   + cb, {{ cache: 'no-store' }}).then(r => r.ok ? r.json() : null).catch(() => null),
        fetch('./industry-feed.json' + cb, {{ cache: 'no-store' }}).then(r => r.ok ? r.json() : null).catch(() => null),
        fetch('./outdoor-feed.json'  + cb, {{ cache: 'no-store' }}).then(r => r.ok ? r.json() : null).catch(() => null),
        fetch('./recipe-feed.json'   + cb, {{ cache: 'no-store' }}).then(r => r.ok ? r.json() : null).catch(() => null),
      ]);
      let changed = false;
      if (sportsR && sportsR.sox && sportsR.pats) {{
        const sameStamp = (FEED.updated && sportsR.updated && FEED.updated === sportsR.updated);
        const sameCount = ((FEED.sox?.items?.length || 0) === (sportsR.sox?.items?.length || 0))
                       && ((FEED.pats?.items?.length || 0) === (sportsR.pats?.items?.length || 0));
        if (!sameStamp || !sameCount) {{
          FEED.updated = sportsR.updated;
          FEED.sox     = sportsR.sox;
          FEED.pats    = sportsR.pats;
          changed = true;
        }}
      }}
      if (industryR && industryR.items) {{
        const sameCount = (FEED.industry?.items?.length || 0) === (industryR.items.length || 0);
        const sameStamp = (FEED.industry?.updated === industryR.updated);
        if (!sameStamp || !sameCount) {{ FEED.industry = industryR; changed = true; }}
      }}
      if (outdoorR && outdoorR.items) {{
        const sameCount = (FEED.outdoor?.items?.length || 0) === (outdoorR.items.length || 0);
        const sameStamp = (FEED.outdoor?.updated === outdoorR.updated);
        if (!sameStamp || !sameCount) {{ FEED.outdoor = outdoorR; changed = true; }}
      }}
      if (recipeR && recipeR.items) {{
        const sameCount = (FEED.recipe?.items?.length || 0) === (recipeR.items.length || 0);
        const sameStamp = (FEED.recipe?.updated === recipeR.updated);
        if (!sameStamp || !sameCount) {{ FEED.recipe = recipeR; changed = true; }}
      }}
      return changed;
    }} catch(e) {{ return false; }}
  }}

  await refresh();
  // Every 60 seconds: re-fetch ESPN for live game state (cheap, ESPN is CDN-cached).
  setInterval(refresh, 60000);
  // Every 3 minutes: poll the curated sports-feed.json — if it changed, repaint the news cards.
  setInterval(async () => {{
    const changed = await pollFeed();
    if (changed) await refresh();
  }}, 180000);
}})();
</script>


<style>
/* Sortable table headers — click to sort asc/desc */
table thead th[data-type] {{ cursor: pointer; user-select: none; position: relative; padding-right: 18px; }}
table thead th[data-type]:hover {{ background: rgba(255,255,255,0.04); }}
table thead th[data-type]::after {{
  content: "↕"; position: absolute; right: 6px; top: 50%; transform: translateY(-50%);
  opacity: 0.25; font-size: 10px;
}}
table thead th[data-type].sort-asc::after {{ content: "↑"; opacity: 0.95; color: var(--cyan); }}
table thead th[data-type].sort-desc::after {{ content: "↓"; opacity: 0.95; color: var(--cyan); }}
</style>
<script>
// Lightweight click-to-sort on any <table> whose <th> has data-type="num|text|date".
// Numeric and date sorts use the column cell's data-sort attribute if present,
// otherwise fall back to cell textContent.
(function() {{
  function sortTable(table, colIndex, type, dir) {{
    const tbody = table.tBodies[0]; if (!tbody) return;
    const rows = Array.from(tbody.rows);
    const getKey = (row) => {{
      const cell = row.cells[colIndex]; if (!cell) return '';
      const raw = cell.getAttribute('data-sort');
      const val = raw != null ? raw : cell.textContent.trim();
      if (type === 'num') {{ const n = parseFloat(val); return isNaN(n) ? -Infinity : n; }}
      if (type === 'date') {{ const t = Date.parse(val); return isNaN(t) ? 0 : t; }}
      return String(val).toLowerCase();
    }};
    rows.sort((a, b) => {{
      const ka = getKey(a), kb = getKey(b);
      if (ka < kb) return dir === 'asc' ? -1 : 1;
      if (ka > kb) return dir === 'asc' ? 1 : -1;
      return 0;
    }});
    rows.forEach(r => tbody.appendChild(r));
  }}
  document.addEventListener('click', function(e) {{
    const th = e.target.closest('th[data-type]'); if (!th) return;
    const table = th.closest('table'); if (!table) return;
    const headerRow = th.parentElement;
    const colIndex = Array.from(headerRow.cells).indexOf(th);
    const type = th.getAttribute('data-type');
    const wasAsc = th.classList.contains('sort-asc');
    headerRow.querySelectorAll('th').forEach(h => h.classList.remove('sort-asc', 'sort-desc'));
    const dir = wasAsc ? 'desc' : 'asc';
    th.classList.add(dir === 'asc' ? 'sort-asc' : 'sort-desc');
    sortTable(table, colIndex, type, dir);
  }}, false);
}})();
</script>

<script>
// On narrow viewports, default-collapse the heavy tables so the page doesn't
// land the user in a forest of 10-column scroll zones.
(function() {{
  if (!window.matchMedia('(max-width: 700px)').matches) return;
  document.querySelectorAll('details.collapsible-section, details').forEach(d => {{
    const summary = d.querySelector('summary');
    if (!summary) return;
    const text = (summary.textContent || '').trim();
    if (/Applications Sent|Active Pipeline|Rejected|Morning Brief Log|Speculative Outreach/i.test(text)) {{
      d.removeAttribute('open');
    }}
  }});
}})();
</script>

<script>
// Per-table search filter. Inputs with class .table-filter filter rows in the
// next sibling table-wrapper. Multi-term: all whitespace-separated terms must
// match (case-insensitive substring across the whole row's text).
(function() {{
  function applyFilter(input) {{
    const terms = input.value.toLowerCase().trim().split(/\\s+/).filter(Boolean);
    input.classList.toggle('has-active-filter', terms.length > 0);
    let el = input.nextElementSibling;
    while (el && !el.querySelector) el = el.nextElementSibling;
    const table = el && el.querySelector ? el.querySelector('table') : null;
    if (!table || !table.tBodies[0]) return;
    Array.from(table.tBodies[0].rows).forEach(row => {{
      if (!terms.length) {{ row.style.display = ''; return; }}
      const text = row.textContent.toLowerCase();
      row.style.display = terms.every(t => text.includes(t)) ? '' : 'none';
    }});
  }}
  document.querySelectorAll('.table-filter').forEach(input => {{
    input.addEventListener('input', () => applyFilter(input));
  }});
}})();
</script>
<script>
// Stat-card tooltips: hover-shown on desktop, tap-to-toggle on mobile (no hover).
// Tap a card to open its tooltip; tap again or tap another card to close/swap.
(function() {{
  const cards = document.querySelectorAll('.stat-card');
  cards.forEach(card => {{
    card.addEventListener('click', (e) => {{
      // Only act as tap-toggle on mobile width
      if (!window.matchMedia('(max-width: 640px)').matches) return;
      const wasOpen = card.classList.contains('touched');
      cards.forEach(c => c.classList.remove('touched'));
      if (!wasOpen) card.classList.add('touched');
      e.stopPropagation();
    }});
  }});
  // Tap outside any stat card closes the tooltip
  document.addEventListener('click', () => {{
    cards.forEach(c => c.classList.remove('touched'));
  }});
}})();
</script>
</body>
</html>'''

def publish_to_github(html_path):
    """Copy HTML to index.html. Git add/commit/push is handled entirely by the
    macOS launchd WatchPaths agent (com.paulwhitaker.dashboard-push) on Paul's
    Mac, which fires when index.html changes. Do NOT run any git commands here —
    the sandbox cannot reach github.com and racing with the launchd agent causes
    lock conflicts.
    """
    dashboard_dir = os.path.dirname(os.path.abspath(html_path))
    index_path = os.path.join(dashboard_dir, "index.html")

    try:
        shutil.copy2(html_path, index_path)
        print("index.html updated. launchd agent will commit and push to GitHub Pages.")
        return True
    except Exception as e:
        print(f"Failed to copy index.html: {e}")
        return False


def main():
    # Filter out flags from positional args
    positional = [a for a in sys.argv[1:] if not a.startswith("--")]
    json_path = positional[0] if len(positional) > 0 else os.path.join(os.path.dirname(__file__), "dashboard-data.json")
    html_path = positional[1] if len(positional) > 1 else os.path.join(os.path.dirname(__file__), "job-search-command-center.html")
    data = load_data(json_path)
    html = build_html(data)
    with open(html_path, "w") as f:
        f.write(html)
    print(f"Dashboard built: {html_path}")

    # Also write sports-feed.json as a standalone sibling file so the in-browser widget
    # can poll it while the dashboard is already open and pick up fresh Sox/Pats items
    # written by the refresh-sports-feed scheduled task without needing a full HTML rebuild.
    sports_feed = data.get("sports_feed") or {"sox": {"items": []}, "pats": {"items": []}}
    sports_feed_path = os.path.join(os.path.dirname(html_path), "sports-feed.json")
    with open(sports_feed_path, "w") as f:
        json.dump(sports_feed, f, ensure_ascii=False, indent=2)
    print(f"Sports feed written: {sports_feed_path}")

    # Auto-publish to GitHub Pages if --no-publish is not passed
    if "--no-publish" not in sys.argv:
        publish_to_github(html_path)

if __name__ == "__main__":
    main()
