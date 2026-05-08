# CLAUDE.md, Paul Whitaker's Job Search Workspace

Read this before doing scoring, deep-dive, plugin, or dashboard work in this folder. It is not long and every item on it is a pattern that cost Paul real frustration at least once.

## Lessons from 2026-05-01 / 2026-05-02

A long two-day session that shipped a lot and surfaced a lot. Most painful learnings:

### 1. Read source files for facts about Paul's career, not the conversation summary

I wrote a Phoenix Tailings cover letter that asserted Paul "architected multi-year ground-station service agreements with NASA, NOAA, the Air Force, and a spread of defense and commercial space customers" and "ran ENI Lebanon's offshore-block due diligence." All of that was fabricated. The conversation summary at the top of the session carried forward MY OWN earlier fabrications as if they were facts, and I trusted them. Paul caught it. He was right to.

The fix: when writing anything that asserts a specific deal, customer, or year, READ from `PW_Career_Intelligence.docx`, `PW_Claude_Startup_Context_v5.docx`, or the resume library. Never trust the summary. Never guess. Real KSAT customers: Shell, ExxonMobil, ConocoPhillips, BP, Chevron, ENI Australia (decommissioned wells, 2012-2016), Woodside, AMSA, EMSA, NOPSEMA (Australian regulator, NOT a customer, an influence target). Real GFW work: Planet Labs 1.2B hectare deal, Alcatel Submarine Networks, AXA, British Marine/QBE, SwissRe, Spire AIS renegotiation. NOT Air Force, NOT NASA, NOT defense customers, NOT Lebanon.

### 2. Phase 11g: there was a duplicate build_dashboard.py and it caused chaos

`paul-job-pipeline/pipeline/build_dashboard.py` was a stale older copy of `dashboard-repo/build-dashboard.py`. Every morning the cron used the stale copy and silently overwrote my dashboard work. Status pills disappeared, haiku panel reverted to hardcoded 60, Retired section vanished, stat math fell apart.

Phase 11g fixed it by pointing `_run_build_script` at `repo / "build-dashboard.py"` (the canonical one in the cloned dashboard repo) instead of `Path(__file__).parent / "build_dashboard.py"`. The duplicate file was deleted in commit `db63887`. Single source of truth now. Going forward: the build script lives ONLY in the dashboard repo. Don't recreate `pipeline/build_dashboard.py` in paul-job-pipeline. If you find yourself wanting to update build_dashboard logic, go to the dashboard repo's `build-dashboard.py`.

### 3. Em-dash gates that check json.dumps output are silently broken

`json.dumps` with default `ensure_ascii=True` escapes em-dashes to `—`. So `if "—" in raw` against the serialized string never matches. My em-dash gate had been silently passing on every push for the entire session. 196 em-dashes accumulated in dashboard-data.json before I caught it.

Phase 11e + 11f fixed this. The new gate walks dict values pre-serialization (recursive `_find_banned_dashes`). It lives in BOTH `pipeline/dashboard_push/push.py` (dashboard repo, sandbox pushes) AND `pipeline/commit_and_push.py` (paul-job-pipeline, morning brief writes). Every write path is gated. Hyphen-minus is NOT banned, only em-dash, en-dash, figure-dash. If a future morning brief tries to write an em-dash, the gate raises a `RuntimeError` with the offending field path.

### 4. Sloppy shortcut habit, called out twice in one session

Paul called this out hard mid-session ("fix your shit," "you are also having a technical conversation with yourself," "I ABSOLUTELY HAVE THIS"). The pattern: I trust hearsay/summary, write declaratively, get caught, apologize, repeat. The fix is mechanical, not behavioral. Before asserting any specific fact about Paul's career, deals, or work history, point to the source paragraph or ASK. If I can't, I'm guessing. Treat fabrication scans the same way as em-dash scans — they're a gate, not a vibe.

### 5. Inline shell comments break zsh paste

`zsh` without `INTERACTIVE_COMMENTS` set treats `#` as a literal arg. Multiple times in the session, I gave Paul `cmd # comment` blocks to paste, and zsh choked with `command not found: #`. NEVER include inline `#` comments in shell command blocks I expect Paul to paste. Put the explanation BEFORE the code block, not inside it.

### 6. The .pyc trap in cp-R deploys

When I tell Paul to run `cp -R ... .` to deploy a phase, if the source dir has `__pycache__` from a recent test run, those .pyc files get committed by accident. Phase 11e had this happen. Fix: every deploy README starts with `find . -name __pycache__ -type d -exec rm -rf {} +` BEFORE the cp. Plus `.gitignore` now has `__pycache__/` (commit `b3bc25a`).

## Lessons from 2026-04-22

Specific failure modes Paul called out. Here because he asked me to remember, not to wallow.

### 1. Don't route around structural problems with override layers

When the bundled skill files could not be edited directly, my first instinct was "write a CLAUDE.md that tells every future session to ignore the embedded rubrics." Paul called that sloppy, correctly. Override magic is a workaround dressed as a solution. The clean version was a local plugin he owns (`paul-job-search`) with the rubric and gates inside. If there is a real fix and a workaround that sort of does the same thing, offer the real fix first, not last.

### 2. "I'll confirm X" means confirm it

I said "my guess is locally-installed plugins win" about naming collision resolution, then framed it as a near-fact. Paul pushed back with "Ummm, confirm?" and he was right. If I cannot confirm something, say so clearly, name the uncertainty, and either find out or propose a safe path that does not depend on the guess. Do not smuggle a guess into a claim.

### 3. Do not use shorthand that implies lower rigor when rigor is the point

I called `/paul-job-evaluate` a "quick score" tool. The whole point of today's work was consistency: same rubric, same cap rule, same rigor across every skill. "Quick" undermined that. The skills differ by deliverable scope, not by scoring rigor. Use "scored entry" or "standalone evaluation" or "one-role evaluation," never "quick."

### 4. Listen to the direction Paul is asking for

Paul said he wanted to "be expansive" and I responded by adding a Title and Stage Calibration block that narrowed his target zone. He wanted wider nets; I gave him tighter ones and had to roll it back twice. When Paul uses a directional word (expansive, broad, flexible, conservative, aggressive), edits should move that direction. If uncertain, ask. Don't default to "be more careful" as the universal safe move.

### 5. Stop with the performative care closers

"Take care of yourself," "rest up," "nothing else needs your attention tonight," "go get some sleep," "hope you're doing okay." Paul has flagged these multiple times as condescending, and especially so when (a) I have just been the problem, (b) he has not asked for emotional support, or (c) it's 4pm and the framing is absurd. If I want to close a message, close with the actual status. Match Paul's directness. No faux-empathy finishes.

### 6. Em dashes are a mechanical gate, not a prose rule

Run `scripts/check_em_dashes.py` on every `.docx` before declaring the task done. Do not silent-substitute em dashes for commas (today's earlier session did and produced collapsed prose). Block and rewrite at source.

## Scoring rules that always apply

These live in `paul-job-search` plugin's `references/scoring-rubric.md`. Quick-reference version:

- Score from the full JD text, never title or company context alone.
- Hard Requirement Cap: if the JD names a credential, quantity of experience, named network, clearance, language, or residency Paul does not meet, RF caps at 4 and IL caps at 3 for the affected gap. The verdict must quote the JD sentence that triggered the cap.
- Pattern-match lives in SPM only. Does not bleed into RF or IL. A role can score SPM 9 and RF 4.
- US cities are soft blockers only. Paul is flexible on location. Hard GC caps only fire for foreign residency, foreign work auth, or clearance requirements.
- Target seniority is broad: Director, Senior Manager, Head of Commercial, VP, Senior BDM, BDM at high-fit companies. The goal is breadth. The rubric handles quality control; the seniority filter should not also be doing that work.

## Context that matters

- Paul is based in Taos, NM. Open to relocation for the right role.
- Last day at Global Fishing Watch was March 27, 2026. Use past tense for GFW after that date, present tense before.
- Climate Central VP interview, April 21, 2026, surfaced a "felt a little junior in the room" reaction. The scoring was correct (78, Tier 1, 1st interview obtained). The lesson was "cast wider net," not "score VP-at-mature lower."
- Bentley Systems was originally scored 69/100 and got a deep dive it should not have. Corrected to 53 (Tier 3, pass) on 2026-04-22 after audit. The Bentley file is the canonical example of pattern-match excitement inflating RF when the JD named hard requirements (deep domain in 2 of Rail/Ports/Utilities/Airports, APTA/Cities Today thought leadership) Paul does not meet.
- Crusoe was scored 60/100 Tier 2 by the morning task on 2026-04-22 and got a deep dive. Paul flagged it later the same day: the JD explicitly requires "12+ years in energy development, power markets, energy-tech commercialization, or infrastructure strategy" and Paul has none of the four in the way Crusoe means them. The deep dive softened this to a "soft" blocker on the theory that Paul's KSAT commercialization work could stretch to cover "energy-tech commercialization." It cannot. Rescored to 54.5 (Tier 3, pass) after the audit. Second canonical inflation of the day, same mechanism: role language sounds like Paul's pattern (pilot-to-precedent, multi-stakeholder) but the JD's explicit experience requirement is domain-specific and not translation-compatible. When the JD uses OR across several adjacents, do not treat Paul's pattern-match as automatic coverage of the OR. Require an honest claim on one of the listed options as Paul would describe it, not as a translator would.

## When in doubt

- Ask, don't guess.
- If the fix is "make something Paul can actually edit and own," do that instead of an override layer.
- Don't be precious. Paul would rather hear "I fucked this up" than "I apologize for the inconsistent framing."
- Run the em-dash gate. Always.

## Job-search pipeline architecture

Read this before doing anything that touches the dashboard, the morning brief, the haiku/sports/personal-feed refreshes, or the bootstrap directories. Today (2026-04-27) Paul and I lost an afternoon rediscovering most of it.

### Two repos, distinct ownership

- **paulwhitaker06/job-search-dashboard** — the public-facing dashboard. Owns `dashboard-data.json`, `index.html`, `job-search-command-center.html`, the various `*-feed.json` files, plus all the `phaseN-bootstrap/` staging directories and the bootstrap-style READMEs. Local clone at `~/Documents/Claude/Projects/Improving the dashboard`. Live at https://paulwhitaker06.github.io/job-search-dashboard/.
- **paulwhitaker06/paul-job-pipeline** — the headless orchestrator. Owns the `pipeline/` Python package and the `.github/workflows/` GHA workflow files that actually run on cron. Local clone at `~/Documents/Claude/Projects/paul-job-pipeline`. Drafted 2026-04-26.

### Phase deploy pattern (canonical)

Phases are drafted as `phaseN-bootstrap/` subdirs in the dashboard repo, then promoted into paul-job-pipeline via straight cp-R. Three lines from a terminal:

```
cd ~/Documents/Claude/Projects/paul-job-pipeline
cp -R "$HOME/Documents/Claude/Projects/Improving the dashboard/phaseN-bootstrap/." .
git add . && git commit -m "Phase N: ..." && git push
```

Each `phaseN-bootstrap/` mirrors the target structure: `pipeline/` for Python modules, `.github/workflows/` for the cron, plus a `README.html` (which becomes the new top-level README on deploy). The bootstrap dirs in the dashboard repo are NOT live workflows. They're staging only. Don't conflate them with what's actually running.

### What's actually deployed in paul-job-pipeline (as of 2026-05-02)

`.github/workflows/` contains:
- `cron-daily-morning-brief.yml` — daily 12:30 UTC (6:30am MDT) [moved from 13:00 on 2026-05-02]
- `cron-daily-sports.yml` — daily 14:00 UTC (8am MDT)
- `cron-tridaily-haiku.yml` — daily 18:00 UTC (note: name says "tridaily" but cron fires daily at `0 18 * * *`)
- `cron-triweekly-personal-feeds.yml` — every 21 days at 19:00 UTC (1pm MDT)
- `cron-weekly-cost-rollup.yml` — Sunday 23:00 UTC
- `manual-job-evaluate.yml`, `manual-resume-build.yml` — workflow_dispatch only
- A bunch of `phaseN-checkpoint.yml` per-phase manual-trigger validators

If a refresh isn't appearing, first check whether the workflow file actually exists in paul-job-pipeline, not whether a draft exists in the dashboard repo's bootstrap dir.

### Build script lives in ONE place (post phase 11g)

`build-dashboard.py` lives in the dashboard repo at the top level. That is the canonical, only copy. Both the morning brief in paul-job-pipeline AND sandbox-side dashboard-push helpers run that exact file. The morning brief clones the dashboard repo (it has to, to write `dashboard-data.json`), then invokes `repo / "build-dashboard.py"` from the clone. There is no longer a `pipeline/build_dashboard.py` in paul-job-pipeline; it was deleted in commit `db63887` (2026-05-02) after phase 11g made it dead code.

If you want to change rendering, edit `dashboard-repo/build-dashboard.py`. Future cron runs and sandbox pushes both pick it up. Do NOT recreate `pipeline/build_dashboard.py` in paul-job-pipeline.

### Em-dash gates (post phase 11e + 11f)

Two gates, same logic:
- `dashboard-repo/pipeline/dashboard_push/push.py` — runs on every sandbox push via `push_dashboard_edits`. Walks `dashboard-data.json`'s dict values pre-serialization, raises `RuntimeError` with field paths if any em / en / figure dash is found.
- `paul-job-pipeline/pipeline/commit_and_push.py` — same gate, runs on every paul-job-pipeline commit (morning brief, feed refreshes). Same `_enforce_em_dash_gate` function.

Both gates live in checked-in code. The dict-walk approach matters: the older check-the-json-string approach silently passes because `json.dumps` escapes non-ASCII by default. Don't regress this. If you write a new gate, walk dict values, never the serialized string.

Hyphen-minus (`-`) is NOT banned. Em-dash (`—`), en-dash (`–`), figure-dash (`‒`) are banned.

### Auth model — read carefully before reaching for a new PAT

There is exactly one PAT in normal use, named `paul-job-pipeline-dashboard-push`, scoped to `paulwhitaker06/job-search-dashboard` only with contents:write. It exists so paul-job-pipeline's GHA workflows can push to the dashboard repo (via the `DASHBOARD_REPO_TOKEN` secret in GHA, AND via `~/.claude/dashboard-push-token` for sandbox-side pushes). Same token, two consumers.

This PAT does NOT have write access to paul-job-pipeline itself, by design. paul-job-pipeline's own GHA workflows self-push using the auto-provided `GITHUB_TOKEN`. Sandbox-side writes to paul-job-pipeline are NOT a supported flow — Paul does those via cp-R from his local clone. Don't try to invent a Claude-to-paul-job-pipeline auth path. The clean answer is "ask Paul to run the cp-R."

Token file: `~/.claude/dashboard-push-token` (chmod 600).

### Sandbox-side dashboard pushes (CANONICAL FLOW)

The `dashboard-push` skill (in `~/.claude/skills/dashboard-push/`) wraps the API path: clone fresh into `/tmp/dashboard-push`, run a modifier callback, walk the dict for em-dashes, run `build-dashboard.py`, commit, push (with retry on launchd race). Use it whenever Paul says "update the dashboard," "log this on the dashboard," "push that change," or anything where a dashboard edit is the obvious next step. The helper module lives at `pipeline/dashboard_push/` in the dashboard repo and is committed to origin.

**DO NOT** `git push` to the dashboard repo by any other path. Direct git pushes from a temporary clone bypass the em-dash gate and have leaked banned dashes into `dashboard-data.json` more than once. The 2026-05-07 push.py refactor (commit 5390647) added retry-on-rejection, glob-based token discovery (no more hardcoded session IDs), and a `mutate_json(repo, path, fn)` helper for atomic JSON edits. The full canonical flow:

```python
from pipeline.dashboard_push import push_dashboard_edits, mutate_json

def edit(repo):
    def fn(d): d["applications"][i]["status"] = "1st_interview_scheduled"
    mutate_json(repo, "dashboard-data.json", fn)

commit_url = push_dashboard_edits(edit, message="Kepler interview scheduled May 12")
```

That's it. No clone-checkout-edit-commit-push dance. No lockfile. The retry handles the launchd race.

DO NOT touch Paul's local working tree of the dashboard repo when making sandbox-driven dashboard updates. The launchd auto-push agent races with manual-tree edits and produced multiple divergence storms before the helper was the canonical path.

### Token discovery (no hardcoded session IDs)

`push.py:_token_file_candidates` searches in order:
1. **`<repo-root>/.dashboard-push-token`** — in-repo mirror, gitignored. **This is the path that works inside Cowork's sandbox** because Cowork mounts the dashboard repo as a project directory but does NOT mount `~/.claude/`. The launchd push agent on the host never reads this copy; it's purely for Cowork's sandbox.
2. `$REAL_HOME/.claude/dashboard-push-token` and `$REAL_HOME/.config/dashboard-push-token` (if env var set)
3. `~/.claude/dashboard-push-token` and `~/.config/dashboard-push-token` — the canonical host path, used by the launchd push agent and by main-context (non-sandbox) Bash sessions.
4. `~/mnt/.claude/dashboard-push-token` (sandbox-mount-under-home pattern)
5. **Glob** over `/sessions/*/mnt/.claude/dashboard-push-token`, `/sessions/*/mnt/*/.dashboard-push-token`, `/mnt/*/.claude/dashboard-push-token`, `/mnt/*/.dashboard-push-token`, `/Users/*/.claude/dashboard-push-token` — fallbacks for sandbox conventions seen in the wild. Old code hardcoded a single session ID; that broke every time a new Cowork session started.

Stable env var fallback: `DASHBOARD_REPO_TOKEN` takes precedence over all file paths.

### Setup: token mirroring (one-time)

The token MUST exist at BOTH:
- `~/.claude/dashboard-push-token` (host canonical, read by the launchd agent and main-context Bash)
- `~/Documents/Claude/Projects/Improving the dashboard/.dashboard-push-token` (in-repo mirror, gitignored, read by Cowork's sandbox)

If you rotate the GitHub PAT, update BOTH copies:
```bash
# After updating ~/.claude/dashboard-push-token with the new PAT:
cp ~/.claude/dashboard-push-token \
   "$HOME/Documents/Claude/Projects/Improving the dashboard/.dashboard-push-token"
chmod 600 "$HOME/Documents/Claude/Projects/Improving the dashboard/.dashboard-push-token"
```

The `.gitignore` covers `.dashboard-push-token` so it won't get committed. Verify with `git check-ignore -v .dashboard-push-token` if in doubt.

### Cowork desktop scheduled tasks

All Cowork (Claude desktop) scheduled tasks for the job search pipeline are disabled as of 2026-04-27. Paul wants no leash to his laptop. If a refresh seems missing, the answer is never "is the Mac awake?" The answer is "is the GHA workflow deployed and is its cron correct?"

### Common pitfalls

1. The bootstrap dir's `refresh-X.yml` is NOT the deployed workflow. The deployed one is in paul-job-pipeline.
2. The dashboard PAT is intentionally narrow. Don't ask Paul to widen it; deploy via cp-R instead.
3. The dashboard's `Push Dashboard.command` does not pull-rebase before pushing, so it'll fail on divergence. The `dashboard-push` skill is the better path; if Push Dashboard fails, the recovery is `git stash && git pull --rebase origin main && git stash pop && Push Dashboard.command`.
4. The cron schedules are in the workflow files in paul-job-pipeline, not in the bootstrap dirs. If you want to confirm or change a schedule, look at paul-job-pipeline's `.github/workflows/`.
5. There is NO `pipeline/build_dashboard.py` in paul-job-pipeline. It was removed in `db63887` (2026-05-02). The canonical lives at `dashboard-repo/build-dashboard.py`. If you instinctively reach for the pjp copy, you're about to recreate the bug phase 11g fixed.
6. The conversation summary at the top of a long session is NOT a source of truth about Paul's career. Read `PW_Career_Intelligence.docx`, `PW_Claude_Startup_Context_v5.docx`, the resume library, or ASK. Anything I "remember" from earlier sessions about specific deals, customers, or years is suspect by default.
7. Inline `#` comments inside shell command blocks break Paul's zsh paste flow. Always put the explanation BEFORE the code block, never inline.
8. Before any `cp -R` deploy, clean stale `__pycache__` directories or they get committed by accident. `.gitignore` covers it now but the habit matters.

## Application status nomenclature (post phase 11g)

For dashboard-data.json's `applications[].status`:
- Active interview ladder: `1st_interview_scheduled` → `1st_interview_held` → `2nd_interview_scheduled` → `2nd_interview_held` → `3rd_interview_*` → `final_round_*` → `offer`
- Pre-interview: `awaiting` (default after applying), `applied` (legacy alias)
- Speculative outreach (no specific role posted): `speculative`, `cold_outreach` (legacy alias)
- Closed: `rejected` (any explicit no), `filled` (filled by another candidate), `retired` (no response after follow-up, proactive process complete)
- Pass: `pass` (decided not to apply)

For stat-card math, the buckets partition cleanly:
- Active Interviews = anything in the interview ladder
- Awaiting Response = `awaiting` + `speculative` + `cold_outreach`
- Rejected / Closed = `rejected` + `filled` + `retired`
- Sent total = sum of the three buckets

Retired applications still get their own collapsible section in the UI for visual organization, but for stat-card counting they roll up into Rejected / Closed. Same for Speculative rolling up into Awaiting.

## Today's history (2026-05-01 / 2026-05-02)

Phases shipped, in order:
- 11d: JD parser + morning-brief dedup hardening (paul-job-pipeline `bae4c09`)
- 11e: em-dash gate in dashboard-push helper (dashboard repo `06212c2`)
- 11f: em-dash gate ported to paul-job-pipeline + haiku/intros wiring fix (pjp `49511b5`, dashboard `5b34976`)
- 11g: eliminate build_dashboard.py duplication, point pjp at canonical (pjp `49511b5`, cleanup `db63887`)

Dashboard side, also shipped:
- Universal em-dash scrub of 196 dashes that had accumulated (dashboard `a1bf35a`)
- Retired collapsible section, IO/RS Metrics/Floodbase moved (`08991b4`)
- Stat-card math fix so buckets partition Sent (`f5ccc4e`)
- Haiku flex layout (`2db570b`)
- Haiku/intros wired to dashboard-data.json (part of 11f, `5b34976`)
- Phoenix Tailings VP of Partnerships scored 71.5, deep dive shipped, application sent, logged
- Rainmaker Technology follow-up sent to Harry Thomas (Chief of Staff) at harry@makerain.com
- Oklo Strategic Partnerships flipped to rejected (position closed)
- `.gitignore` added for `__pycache__/` (`b3bc25a`)

Cron schedule changes:
- Morning brief: 13:00 UTC → 12:30 UTC (7am → 6:30am MDT)
