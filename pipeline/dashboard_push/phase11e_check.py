"""Phase 11e checkpoint: regression tests for the em-dash gate.

Validates that the new gate catches em-dashes anywhere in the dashboard data
structure, including in places earlier ad-hoc gates missed (nested arrays,
specific field names that weren't in any allow-list, etc).

Exits 0 on pass, 1 on fail.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# Import path-tolerant: run from anywhere
try:
    from pipeline.dashboard_push.push import (
        BANNED_DASHES,
        _find_banned_dashes,
        _enforce_em_dash_gate,
    )
except ImportError:
    # Allow running as a standalone script from this dir
    here = Path(__file__).resolve().parent
    sys.path.insert(0, str(here.parent.parent))
    from pipeline.dashboard_push.push import (
        BANNED_DASHES,
        _find_banned_dashes,
        _enforce_em_dash_gate,
    )


class TestRunner:
    def __init__(self):
        self.passed = 0
        self.failed: list[str] = []

    def case(self, name: str, condition: bool, detail: str = "") -> None:
        if condition:
            self.passed += 1
            print(f"  PASS  {name}")
        else:
            self.failed.append(f"{name}: {detail}")
            print(f"  FAIL  {name}  ({detail})")

    def summary(self) -> int:
        print(f"\n  Total: {self.passed} passed, {len(self.failed)} failed")
        if self.failed:
            print("\n  Failures:")
            for f in self.failed:
                print(f"    - {f}")
            return 1
        return 0


def test_walker(t: TestRunner) -> None:
    print("\n[1] _find_banned_dashes walker")

    # Clean structure, no hits
    clean = {
        "applications": [
            {"company": "Phoenix Tailings", "next_action": "Awaiting initial response."},
        ],
        "stats": {"applications_sent": 26},
    }
    t.case("clean structure has zero hits", _find_banned_dashes(clean) == [])

    # Em-dash in a nested string
    dirty = {
        "applications": [
            {"company": "Foo", "next_action": "Rejected Mar 25 — encouraged to apply"},
        ],
    }
    hits = _find_banned_dashes(dirty)
    t.case("em-dash in nested string is caught", len(hits) == 1, f"got {hits}")
    t.case("path looks reasonable", "next_action" in hits[0][0] if hits else False)

    # En-dash
    hits = _find_banned_dashes({"applied": "2026–05–01"})
    t.case("en-dash is caught", len(hits) == 1)

    # Figure-dash
    hits = _find_banned_dashes({"x": "1‒2"})
    t.case("figure-dash is caught", len(hits) == 1)

    # Multiple hits in different fields
    multi = {
        "a": "ok",
        "b": "bad — here",
        "c": [{"d": "also bad — here"}],
    }
    hits = _find_banned_dashes(multi)
    t.case("multiple hits found independently", len(hits) == 2, f"got {len(hits)}")

    # Unicode-escaped em-dash sequence (the json-serialized form). The walker
    # checks the dict, NOT the json string, so this should NOT be a false
    # positive (the literal char sequence "—" in a string is the escape
    # sequence as 6 separate characters, not the dash).
    hits = _find_banned_dashes({"x": "literal backslash u 2014, not a dash"})
    t.case("escape-sequence text is not flagged", len(hits) == 0,
           "the gate works on dict values, not json strings, so \\u2014 in a string isn't a hit")


def test_enforcer(t: TestRunner) -> None:
    print("\n[2] _enforce_em_dash_gate")

    # Build a temp repo dir with a clean dashboard-data.json
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        clean = {"applications": [{"company": "Foo", "next_action": "all good"}]}
        (repo / "dashboard-data.json").write_text(json.dumps(clean, indent=2))
        try:
            _enforce_em_dash_gate(repo)
            t.case("clean repo passes gate", True)
        except RuntimeError as e:
            t.case("clean repo passes gate", False, str(e))

    # Dirty repo: gate should raise
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        dirty = {"applications": [{"company": "Foo", "next_action": "Rejected — see note"}]}
        (repo / "dashboard-data.json").write_text(json.dumps(dirty, indent=2))
        # Note: json.dumps default escapes em-dash to — in the file; the
        # gate reads the file with json.loads which decodes it back to the
        # literal em-dash character. So the gate must catch it.
        try:
            _enforce_em_dash_gate(repo)
            t.case("dirty repo raises", False, "gate did not raise on em-dash")
        except RuntimeError as e:
            ok = "em-dash gate FAILED" in str(e)
            t.case("dirty repo raises", ok, f"raised but message looks wrong: {e}")

    # Repo without dashboard-data.json: gate is a no-op (some pushes don't
    # touch the data file, e.g. pure HTML or feed updates).
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        try:
            _enforce_em_dash_gate(repo)
            t.case("missing data file is a no-op", True)
        except Exception as e:
            t.case("missing data file is a no-op", False, str(e))

    # Malformed JSON: gate should NOT raise (let build-dashboard.py surface
    # the JSON error instead). We just want to make sure the gate doesn't
    # crash the whole push for an unrelated reason.
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        (repo / "dashboard-data.json").write_text("{not valid json")
        try:
            _enforce_em_dash_gate(repo)
            t.case("malformed JSON does not crash gate", True)
        except Exception as e:
            t.case("malformed JSON does not crash gate", False, str(e))


def test_constants(t: TestRunner) -> None:
    print("\n[3] BANNED_DASHES tuple")
    t.case("em-dash present", "—" in BANNED_DASHES)
    t.case("en-dash present", "–" in BANNED_DASHES)
    t.case("figure-dash present", "‒" in BANNED_DASHES)
    # Plain hyphen-minus must NOT be in the banned set, that would break
    # everything (dates 2026-05-01, scores 200-250K, role names, etc).
    t.case("hyphen-minus is NOT banned", "-" not in BANNED_DASHES)


def main() -> int:
    print("Phase 11e checkpoint, em-dash gate")
    t = TestRunner()
    test_walker(t)
    test_enforcer(t)
    test_constants(t)
    return t.summary()


if __name__ == "__main__":
    sys.exit(main())
