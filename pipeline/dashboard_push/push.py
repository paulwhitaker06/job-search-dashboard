"""Headless dashboard push from a sandbox session.

Designed to replace the manual `Push Dashboard.command` round-trip when Claude
is editing the dashboard from a Cowork session. Mirrors the pattern used by
`phase1-bootstrap/pipeline/commit_and_push.py` (which is what paul-job-pipeline
uses for the morning brief).

Phase 11e change (2026-05-01):
    Added an em-dash and en-dash gate that walks the dashboard-data.json dict
    pre-serialization. Prior gates checked the json.dumps output, which silently
    passed on em-dashes because json.dumps defaults to ensure_ascii=True and
    escapes them to \\u2014 / \\u2013 in the output string. The new gate is a
    recursive walker over dict / list / str values, so any em-dash, en-dash, or
    figure-dash anywhere in the structure raises before the push happens.

    The gate is enforced inside push_dashboard_edits itself, after the modifier
    runs and before commit. Modifier callbacks no longer need to add their own
    em-dash check; the helper does it.

Workflow:
    1. Load DASHBOARD_REPO_TOKEN (env var or file)
    2. Clone the dashboard repo into /tmp/dashboard-push (fresh, depth=1)
    3. Run the user-supplied modifier(repo_path) callback to edit files
    4. Em-dash gate: walk dashboard-data.json dict, reject on any banned dash
    5. Stage everything, commit, push via HTTPS with token-embedded URL
    6. Return the commit URL on success

The user's local working tree (~/Documents/Claude/Projects/Improving the dashboard)
is NEVER touched. This avoids racing with the launchd auto-push agent.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional


DASHBOARD_REPO = "paulwhitaker06/job-search-dashboard"
DEFAULT_BRANCH = "main"
COMMIT_AUTHOR_NAME = "claude-cowork"
COMMIT_AUTHOR_EMAIL = "paul.whitaker06@gmail.com"

DEFAULT_CLONE_DIR = Path("/tmp/dashboard-push")

# Em-dash, en-dash, figure-dash. Paul's hard rule, no dashes anywhere in
# dashboard-data.json. Uses commas, periods, semicolons, or restructured prose
# instead.
BANNED_DASHES = ("—", "–", "‒")


def _token_file_candidates() -> list[Path]:
    """Build the search list for the PAT file."""
    candidates: list[Path] = []
    real_home = os.environ.get("REAL_HOME", "").strip()
    if real_home:
        candidates.append(Path(real_home) / ".claude" / "dashboard-push-token")
        candidates.append(Path(real_home) / ".config" / "dashboard-push-token")
    candidates.append(Path.home() / ".claude" / "dashboard-push-token")
    candidates.append(Path.home() / ".config" / "dashboard-push-token")
    sandbox_mount = Path.home() / "mnt" / ".claude" / "dashboard-push-token"
    candidates.append(sandbox_mount)
    candidates.append(Path("/sessions/lucid-funny-wright/mnt/.claude/dashboard-push-token"))
    seen: set[Path] = set()
    out: list[Path] = []
    for p in candidates:
        if p not in seen:
            out.append(p)
            seen.add(p)
    return out


def load_token() -> str:
    env = os.environ.get("DASHBOARD_REPO_TOKEN", "").strip()
    if env:
        return env
    for path in _token_file_candidates():
        if path.exists():
            text = path.read_text().strip()
            if text:
                return text
    candidates = "\n  ".join(str(p) for p in _token_file_candidates())
    raise RuntimeError(
        "DASHBOARD_REPO_TOKEN not found. Set the env var, or place the PAT in "
        "one of these files (chmod 600):\n  " + candidates
    )


def _authenticated_url(token: str, repo: str = DASHBOARD_REPO) -> str:
    return f"https://x-access-token:{token}@github.com/{repo}.git"


def _run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, cwd=str(cwd) if cwd else None,
                              capture_output=True, text=True, check=check)
    except subprocess.CalledProcessError as e:
        stdout = e.stdout or ""
        stderr = e.stderr or ""
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\nstdout: {stdout}\nstderr: {stderr}"
        ) from e


# ---------------------------------------------------------------------------
# Phase 11e: em-dash gate
# ---------------------------------------------------------------------------

def _find_banned_dashes(obj, path: str = "") -> list[tuple[str, str]]:
    """Walk a dict / list / str structure and return [(json-pointer-like-path,
    offending substring snippet)] for every string containing a banned dash.
    Empty list means clean."""
    hits: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            hits.extend(_find_banned_dashes(v, f"{path}.{k}" if path else str(k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits.extend(_find_banned_dashes(v, f"{path}[{i}]"))
    elif isinstance(obj, str):
        for ch in BANNED_DASHES:
            if ch in obj:
                idx = obj.index(ch)
                snippet = obj[max(0, idx - 25):idx + 25].replace("\n", " ")
                hits.append((path, snippet))
                break
    return hits


def _enforce_em_dash_gate(repo: Path) -> None:
    """Read dashboard-data.json from `repo` and reject if any banned dash
    appears anywhere in the structure. Raises RuntimeError on violation with
    enough detail for the caller to find the offending field."""
    data_file = repo / "dashboard-data.json"
    if not data_file.exists():
        return
    try:
        d = json.loads(data_file.read_text())
    except Exception as e:
        # If JSON is malformed, that's a different error. Let the gate skip
        # silently and let the build script surface the JSON error.
        print(f"[em-dash gate] dashboard-data.json unparseable, skipping gate: {e}")
        return
    hits = _find_banned_dashes(d)
    if not hits:
        return
    summary = "\n  ".join(f"{path}: ...{snippet}..." for path, snippet in hits[:10])
    raise RuntimeError(
        f"em-dash gate FAILED: {len(hits)} field(s) contain banned dashes "
        f"(em, en, or figure dash). Sample:\n  {summary}\n"
        "Fix the source by replacing dashes with commas, periods, or "
        "restructured prose. The gate walks dict values pre-serialization, "
        "so json.dumps escaping cannot mask violations."
    )


# ---------------------------------------------------------------------------
# Clone + commit + push
# ---------------------------------------------------------------------------

def _clone_fresh(token: str, target: Path, branch: str) -> Path:
    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    _run(["git", "clone", "--depth", "1", "--branch", branch,
          _authenticated_url(token), str(target)])
    _run(["git", "config", "user.name", COMMIT_AUTHOR_NAME], cwd=target)
    _run(["git", "config", "user.email", COMMIT_AUTHOR_EMAIL], cwd=target)
    return target


def _commit_and_push(token: str, repo_dir: Path, message: str, branch: str) -> Optional[str]:
    _run(["git", "add", "-A"], cwd=repo_dir)
    diff = _run(["git", "diff", "--cached", "--quiet"], cwd=repo_dir, check=False)
    if diff.returncode == 0:
        return None
    _run(["git", "commit", "-m", message], cwd=repo_dir)
    _run(["git", "push", _authenticated_url(token), f"HEAD:{branch}"], cwd=repo_dir)
    sha = _run(["git", "rev-parse", "HEAD"], cwd=repo_dir).stdout.strip()
    return sha


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def push_dashboard_edits(
    modifier: Callable[[Path], None],
    message: str,
    *,
    branch: str = DEFAULT_BRANCH,
    clone_dir: Path = DEFAULT_CLONE_DIR,
    rebuild_html: bool = True,
) -> Optional[str]:
    """Clone fresh, run modifier, gate em-dashes, rebuild HTML, commit, push.

    Phase 11e: em-dash gate now runs automatically after the modifier. Modifier
    callbacks do not need to add their own check; the helper enforces it.

    Args:
        modifier: Callable that takes the cloned repo path and edits files in
                  place. Receives a Path; should not return anything.
        message: Commit message.
        branch: Branch to clone/push (default 'main').
        clone_dir: Where to clone (default /tmp/dashboard-push).
        rebuild_html: If True (default), runs `python3 build-dashboard.py` in
                      the clone after the modifier, so HTML stays consistent
                      with dashboard-data.json edits.

    Returns:
        GitHub commit URL on success, or None if there were no changes to push.

    Raises:
        RuntimeError: token missing, em-dash gate violated, build script
                      failed, clone failed, or push rejected.
    """
    token = load_token()
    repo = _clone_fresh(token, Path(clone_dir), branch)

    modifier(repo)

    # Phase 11e: em-dash gate. Runs after modifier and before HTML rebuild +
    # commit, so a violation aborts the push without leaving anything on the
    # remote.
    _enforce_em_dash_gate(repo)

    if rebuild_html:
        build = repo / "build-dashboard.py"
        if build.exists():
            env = os.environ.copy()
            env["REAL_HOME"] = str(Path.home())
            try:
                subprocess.run(["python3", str(build)], cwd=str(repo),
                               capture_output=True, text=True, check=True, env=env)
            except subprocess.CalledProcessError as e:
                raise RuntimeError(
                    f"build-dashboard.py failed.\nstdout: {e.stdout}\nstderr: {e.stderr}"
                ) from e

    sha = _commit_and_push(token, repo, message, branch)
    if sha is None:
        return None
    return f"https://github.com/{DASHBOARD_REPO}/commit/{sha}"
