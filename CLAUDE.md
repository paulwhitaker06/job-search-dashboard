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
