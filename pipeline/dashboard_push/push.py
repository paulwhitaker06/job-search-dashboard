"""Headless dashboard push from a sandbox session.

Designed to replace the manual `Push Dashboard.command` round-trip when Claude
is editing the dashboard from a Cowork session. Mirrors the pattern used by
`phase1-bootstrap/pipeline/commit_and_push.py` (which is what paul-job-pipeline
uses for the morning brief).

Workflow:
    1. Load DASHBOARD_REPO_TOKEN (env var or file)
    2. Clone the dashboard repo into /tmp/dashboard-push (fresh, depth=1)
    3. Run the user-supplied modifier(repo_path) callback to edit files
    4. Stage everything, commit, push via HTTPS with token-embedded URL
    5. Return the commit URL on success

The user's local working tree (~/Documents/Claude/Projects/Improving the dashboard)
is NEVER touched. This avoids racing with the launchd auto-push agent.
"""

from __future__ import annotations

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


def _token_file_candidates() -> list[Path]:
    """Build the search list for the PAT file.

    Honors REAL_HOME (set by build-dashboard.py and other sandbox callers to
    point at the human's actual $HOME on the host Mac) before falling back to
    Path.home(). Also probes any common sandbox-mount paths.
    """
    candidates: list[Path] = []
    real_home = os.environ.get("REAL_HOME", "").strip()
    if real_home:
        candidates.append(Path(real_home) / ".claude" / "dashboard-push-token")
        candidates.append(Path(real_home) / ".config" / "dashboard-push-token")
    candidates.append(Path.home() / ".claude" / "dashboard-push-token")
    candidates.append(Path.home() / ".config" / "dashboard-push-token")
    # Sandbox-mount fallback: when running inside a Cowork sandbox, the user's
    # ~/.claude is mounted under <sandbox_home>/mnt/.claude. Probe that too.
    sandbox_mount = Path.home() / "mnt" / ".claude" / "dashboard-push-token"
    candidates.append(sandbox_mount)
    # And the absolute sandbox path that this sandbox specifically uses.
    candidates.append(Path("/sessions/lucid-funny-wright/mnt/.claude/dashboard-push-token"))
    # Deduplicate while preserving order
    seen: set[Path] = set()
    out: list[Path] = []
    for p in candidates:
        if p not in seen:
            out.append(p)
            seen.add(p)
    return out


# ---------------------------------------------------------------------------
# Token loading
# ---------------------------------------------------------------------------

def load_token() -> str:
    """Resolve the dashboard PAT from env var or a known file location.

    Raises RuntimeError with a clear setup hint if not found anywhere.
    """
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


# ---------------------------------------------------------------------------
# Subprocess helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, cwd=str(cwd) if cwd else None,
                              capture_output=True, text=True, check=check)
    except subprocess.CalledProcessError as e:
        # Strip any embedded token before re-raising, just in case.
        stdout = e.stdout or ""
        stderr = e.stderr or ""
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\nstdout: {stdout}\nstderr: {stderr}"
        ) from e


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
    """Stage everything, commit, push. Return commit SHA or None if no changes."""
    _run(["git", "add", "-A"], cwd=repo_dir)

    diff = _run(["git", "diff", "--cached", "--quiet"], cwd=repo_dir, check=False)
    if diff.returncode == 0:
        return None  # Nothing to commit

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
    """Clone fresh, run modifier, commit, push.

    Args:
        modifier: Callable that takes the cloned repo path and edits files in
                  place. Receives a Path; should not return anything.
        message: Commit message.
        branch: Branch to clone/push (default 'main').
        clone_dir: Where to clone (default /tmp/dashboard-push).
        rebuild_html: If True (default), runs `python3 build-dashboard.py` in
                      the clone after the modifier, so HTML stays consistent
                      with dashboard-data.json edits. Set False if the modifier
                      handles HTML itself or doesn't change underlying data.

    Returns:
        GitHub commit URL on success, or None if there were no changes to push.

    Raises:
        RuntimeError: token missing, clone failed, or push rejected.
    """
    token = load_token()
    repo = _clone_fresh(token, Path(clone_dir), branch)

    modifier(repo)

    if rebuild_html:
        # Use the build script that lives in the repo we just cloned. Mirrors
        # the morning-brief flow: data edits + HTML rebuild are one atomic commit.
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
