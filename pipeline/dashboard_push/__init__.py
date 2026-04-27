"""dashboard_push: headless commit + push from a Cowork sandbox session.

Public API:
    push_dashboard_edits(modifier, message=...) -> commit_url
        modifier: callable(repo_dir: Path) -> None
                  receives a fresh checkout of paulwhitaker06/job-search-dashboard,
                  edits files in place, returns nothing.
        Returns the GitHub commit URL on success, or None if no changes.

Auth:
    DASHBOARD_REPO_TOKEN env var, OR a file at one of:
        ~/.claude/dashboard-push-token
        ~/.config/dashboard-push-token
    File contents = the raw PAT, no quotes, no whitespace, no JSON.
"""

from .push import push_dashboard_edits, load_token

__all__ = ["push_dashboard_edits", "load_token"]
