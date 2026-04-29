"""
Patcher for phase 10g: adds Pipeline Cost panel to build-dashboard.py.
Idempotent. Three insertions, each guarded so re-runs are no-ops.
"""
import pathlib
import sys

COST_HELPERS = '''
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
            \'\'\'<details>
<summary class="section-header">Pipeline Cost <span class="badge pill-muted" style="font-size:10px;">monitoring active</span></summary>
<p style="color:var(--text-muted); font-size:14px; margin:10px 0;">Cost monitoring is wired. After workflow runs and the Sunday rollup fires, this populates with weekly totals.</p>
</details>\'\'\'
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
            f\'\'\'<details>
<summary class="section-header">Pipeline Cost <span class="badge pill-muted" style="font-size:10px;">$0.00 this week</span></summary>
<p style="color:var(--text-muted); font-size:14px; margin:10px 0;">No API calls logged this week yet.</p>
<p style="color:var(--text-muted); font-size:11px;">Last updated {updated}</p>
</details>\'\'\'
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
        workflow_rows += f\'    <tr><td>{wf}</td><td style="text-align:right;">${float(total or 0):.2f}</td></tr>\\n\'
    if not workflow_rows:
        workflow_rows = \'    <tr><td colspan="2" style="color:var(--text-muted);">No data in past 4 weeks.</td></tr>\\n\'

    first_week = weekly_chrono[0].get("week_start", "")
    last_week = weekly_chrono[-1].get("week_start", "")

    return (
        f\'\'\'<details>
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
</details>\'\'\'
    )


'''

CALL_LINE = "    cost_section_html = build_cost_section_html(compute_cost_summary())\n"
INSERT_AFTER = "    stat_cards = compute_stat_cards(data)\n"
TEMPLATE_NEEDLE = '<details>\n<summary class="section-header">Morning Brief Log'
TEMPLATE_REPLACE = '{cost_section_html}\n\n<details>\n<summary class="section-header">Morning Brief Log'

def patch(src: str) -> str:
    if "def compute_cost_summary" in src:
        print("[10g] helpers already present, skipping")
    else:
        if "def compute_stats(data):" not in src:
            raise SystemExit("[10g] anchor 'def compute_stats(data):' not found")
        src = src.replace("def compute_stats(data):", COST_HELPERS + "def compute_stats(data):", 1)
        print("[10g] inserted compute_cost_summary + build_cost_section_html")

    if "cost_section_html = build_cost_section_html" in src:
        print("[10g] call already present, skipping")
    else:
        if INSERT_AFTER not in src:
            raise SystemExit("[10g] anchor 'stat_cards = compute_stat_cards(data)' not found")
        src = src.replace(INSERT_AFTER, INSERT_AFTER + CALL_LINE, 1)
        print("[10g] inserted call to build_cost_section_html in main_builder")

    if "{cost_section_html}" in src:
        print("[10g] template slot already present, skipping")
    else:
        if TEMPLATE_NEEDLE not in src:
            raise SystemExit("[10g] anchor 'Morning Brief Log <details>' not found")
        src = src.replace(TEMPLATE_NEEDLE, TEMPLATE_REPLACE, 1)
        print("[10g] inserted {cost_section_html} slot in template before Morning Brief Log")
    return src


def main():
    target = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "build-dashboard.py")
    src = target.read_text()
    new_src = patch(src)
    target.write_text(new_src)
    print(f"[10g] wrote {target}")


if __name__ == "__main__":
    main()
