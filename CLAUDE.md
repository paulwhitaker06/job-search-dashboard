# CLAUDE.md, Paul Whitaker's Job Search Workspace

Read this before doing scoring, deep-dive, plugin, or dashboard work in this folder. It is not long and every item on it is a pattern that cost Paul real frustration at least once.

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

### What's actually deployed in paul-job-pipeline (as of 2026-04-27)

`.github/workflows/` contains:
- `morning-brief.yml` — daily 13:00 UTC (7am MDT)
- `refresh-haiku.yml` — every 3 days at 18:00 UTC (noon MDT)
- `refresh-personal-feeds.yml` — every 21 days at 19:00 UTC (1pm MDT)
- `refresh-sports.yml` — daily 14:00 UTC (8am MDT) [deployed 2026-04-27 from phase11b-bootstrap]
- A bunch of `phaseN-checkpoint.yml` per-phase manual-trigger validators

If a refresh isn't appearing, first check whether the workflow file actually exists in paul-job-pipeline, not whether a draft exists in the dashboard repo's bootstrap dir.

### Auth model — read carefully before reaching for a new PAT

There is exactly one PAT in normal use, named `paul-job-pipeline-dashboard-push`, scoped to `paulwhitaker06/job-search-dashboard` only with contents:write. It exists so paul-job-pipeline's GHA workflows can push to the dashboard repo (via the `DASHBOARD_REPO_TOKEN` secret in GHA, AND via `~/.claude/dashboard-push-token` for sandbox-side pushes). Same token, two consumers.

This PAT does NOT have write access to paul-job-pipeline itself, by design. paul-job-pipeline's own GHA workflows self-push using the auto-provided `GITHUB_TOKEN`. Sandbox-side writes to paul-job-pipeline are NOT a supported flow — Paul does those via cp-R from his local clone. Don't try to invent a Claude-to-paul-job-pipeline auth path. The clean answer is "ask Paul to run the cp-R."

Token file: `~/.claude/dashboard-push-token` (chmod 600).

### Sandbox-side dashboard pushes

The `dashboard-push` skill (in `~/.claude/skills/dashboard-push/`) wraps the API path: clone fresh into `/tmp/dashboard-push`, run a modifier callback, build HTML, commit, push. Use it whenever Paul says "update the dashboard," "log this on the dashboard," "push that change," or anything where a dashboard edit is the obvious next step. The helper module lives at `pipeline/dashboard_push/` in the dashboard repo and is committed to origin.

Do NOT touch Paul's local working tree of the dashboard repo when making sandbox-driven dashboard updates. The launchd auto-push agent races with manual-tree edits and produced today's divergence storm. The dashboard-push skill never touches the local tree, which is the correct pattern.

### Cowork desktop scheduled tasks

All Cowork (Claude desktop) scheduled tasks for the job search pipeline are disabled as of 2026-04-27. Paul wants no leash to his laptop. If a refresh seems missing, the answer is never "is the Mac awake?" The answer is "is the GHA workflow deployed and is its cron correct?"

### Common pitfalls

1. The bootstrap dir's `refresh-X.yml` is NOT the deployed workflow. The deployed one is in paul-job-pipeline.
2. The dashboard PAT is intentionally narrow. Don't ask Paul to widen it; deploy via cp-R instead.
3. The dashboard's `Push Dashboard.command` does not pull-rebase before pushing, so it'll fail on divergence. The `dashboard-push` skill is the better path; if Push Dashboard fails, the recovery is `git stash && git pull --rebase origin main && git stash pop && Push Dashboard.command`.
4. The cron schedules are in the workflow files in paul-job-pipeline, not in the bootstrap dirs. If you want to confirm or change a schedule, look at paul-job-pipeline's `.github/workflows/`.
