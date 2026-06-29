#!/usr/bin/env python3
"""Contract tests for roadmap_sync.py."""

from __future__ import annotations

import tempfile
from pathlib import Path

import roadmap_sync


ROADMAP = """# ROADMAP

> line budget: <=150

## Current Horizon

<!-- harness:goal id="g1" -->
Goal: prove the harness with evidence.

## Active Milestones

<!-- harness:milestone id="M1" status="active" priority="P0" -->
### M1 - first proof
- DoD: run passes
- Evidence: evidence/run.json
- Gap: no proof yet
- Status: [ ]

<!-- harness:milestone id="M2" status="active" priority="P1" -->
### M2 - second proof
- DoD: another run passes
- Evidence: evidence/second.json
- Gap: still thin
- Status: [ ]

## Next Candidates
- N1
"""


def run_in_tmp(fn):
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "ROADMAP.md").write_text(ROADMAP, encoding="utf-8")
        old = Path.cwd()
        try:
            import os

            os.chdir(root)
            fn(root)
        finally:
            os.chdir(old)


def test_complete_updates_marker_and_status():
    def case(root: Path):
        code = roadmap_sync.main(
            [
                "complete",
                "--milestone",
                "M1",
                "--evidence",
                "evidence/run.json",
                "--summary",
                "run passed",
            ]
        )
        assert code == 0
        text = (root / "ROADMAP.md").read_text(encoding="utf-8")
        assert 'id="M1" status="completed"' in text
        assert "- Status: [x]" in text
        assert "- Summary: run passed" in text

    run_in_tmp(case)


def test_horizon_check_generates_gap_when_all_closed():
    def case(root: Path):
        assert roadmap_sync.main(["complete", "--milestone", "M1"]) == 0
        assert roadmap_sync.main(["complete", "--milestone", "M2"]) == 0
        code = roadmap_sync.main(["horizon-check", "--gap-out", "docs/roadmap-gap.md"])
        assert code == 2
        gap = (root / "docs" / "roadmap-gap.md").read_text(encoding="utf-8")
        assert "Roadmap Gap Review" in gap
        assert "Active harness milestones are exhausted" in gap

    run_in_tmp(case)


def test_horizon_check_ignores_non_active_open_statuses():
    def case(root: Path):
        text = (root / "ROADMAP.md").read_text(encoding="utf-8")
        text = text.replace('id="M1" status="active"', 'id="M1" status="pending"')
        text = text.replace('id="M2" status="active"', 'id="M2" status="blocked"')
        (root / "ROADMAP.md").write_text(text, encoding="utf-8")

        code = roadmap_sync.main(["horizon-check", "--gap-out", "docs/roadmap-gap.md"])
        assert code == 2
        gap = (root / "docs" / "roadmap-gap.md").read_text(encoding="utf-8")
        assert "Active harness milestones are exhausted" in gap

    run_in_tmp(case)


def test_gap_report_uses_legacy_north_star_fallback():
    def case(root: Path):
        text = (root / "ROADMAP.md").read_text(encoding="utf-8")
        text = text.replace("> line budget: <=150", "> 북극성: evidence over understanding")
        text = text.replace('<!-- harness:goal id="g1" -->\nGoal: prove the harness with evidence.\n', "")
        (root / "ROADMAP.md").write_text(text, encoding="utf-8")
        assert roadmap_sync.main(["complete", "--milestone", "M1"]) == 0
        assert roadmap_sync.main(["complete", "--milestone", "M2"]) == 0
        code = roadmap_sync.main(["horizon-check", "--gap-out", "docs/roadmap-gap.md"])
        assert code == 2
        gap = (root / "docs" / "roadmap-gap.md").read_text(encoding="utf-8")
        assert "북극성: evidence over understanding" in gap

    run_in_tmp(case)


def test_compact_archives_completed_when_over_budget():
    def case(root: Path):
        # Push line count over the cap while preserving active M2.
        with (root / "ROADMAP.md").open("a", encoding="utf-8") as fh:
            for idx in range(40):
                fh.write(f"\nextra line {idx}")
        assert roadmap_sync.main(["complete", "--milestone", "M1", "--summary", "done"]) == 0
        code = roadmap_sync.main(["compact", "--max-lines", "65", "--backlog", "BACKLOG.md"])
        assert code == 0
        roadmap = (root / "ROADMAP.md").read_text(encoding="utf-8")
        backlog = (root / "BACKLOG.md").read_text(encoding="utf-8")
        assert 'id="M1"' not in roadmap
        assert 'id="M2"' in roadmap
        assert "M1 - M1 - first proof" in backlog
        # F1 regression: body Evidence must survive archive, not become "-".
        assert "evidence/run.json" in backlog
        assert "Evidence: -" not in backlog

    run_in_tmp(case)


def test_archive_falls_back_to_dod_when_no_summary():
    # F1 regression: completing without --summary must preserve the DoD as
    # Result (and the body Evidence), instead of writing "Result: -".
    def case(root: Path):
        with (root / "ROADMAP.md").open("a", encoding="utf-8") as fh:
            for idx in range(40):
                fh.write(f"\nextra line {idx}")
        assert roadmap_sync.main(["complete", "--milestone", "M1"]) == 0
        assert roadmap_sync.main(["compact", "--max-lines", "65", "--backlog", "BACKLOG.md"]) == 0
        backlog = (root / "BACKLOG.md").read_text(encoding="utf-8")
        assert "Result: run passes" in backlog       # DoD fallback
        assert "evidence/run.json" in backlog          # body Evidence
        assert "Result: -" not in backlog

    run_in_tmp(case)


ROADMAP_WITH_PROSE = """# ROADMAP

> line budget: <=150

## Active Milestones

<!-- harness:milestone id="M1" status="completed" priority="P0" -->
### M1 - done
- DoD: x
- Evidence: e
- Gap: g
- Status: [x]

---

## Prose Section
This prose must survive compaction.
Line A
Line B

<!-- harness:milestone id="M2" status="active" priority="P1" -->
### M2 - active
- DoD: y
- Status: [ ]
"""


def test_compact_preserves_prose_between_markers():
    # Regression: a completed marker block must NOT swallow the prose section
    # that sits between it and the next marker (data-loss bug 2026-06-20).
    def case(root: Path):
        (root / "ROADMAP.md").write_text(ROADMAP_WITH_PROSE, encoding="utf-8")
        code = roadmap_sync.main(["compact", "--max-lines", "20", "--backlog", "BACKLOG.md"])
        assert code == 0
        roadmap = (root / "ROADMAP.md").read_text(encoding="utf-8")
        assert 'id="M1"' not in roadmap
        assert 'id="M2"' in roadmap
        assert "This prose must survive compaction." in roadmap
        assert "## Prose Section" in roadmap

    run_in_tmp(case)


if __name__ == "__main__":
    test_complete_updates_marker_and_status()
    test_horizon_check_generates_gap_when_all_closed()
    test_horizon_check_ignores_non_active_open_statuses()
    test_gap_report_uses_legacy_north_star_fallback()
    test_compact_archives_completed_when_over_budget()
    test_archive_falls_back_to_dod_when_no_summary()
    test_compact_preserves_prose_between_markers()
    print("test_roadmap_sync.py: PASS")
