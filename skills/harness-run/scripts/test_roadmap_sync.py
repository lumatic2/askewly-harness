#!/usr/bin/env python3
"""Contract tests for roadmap_sync.py."""

from __future__ import annotations

import contextlib
import io
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


# ── 2026-08-06 감사 #15 회귀 ──────────────────────────────────────────────
def test_evidence_with_quotes_and_dashes_survives_roundtrip():
    """마커가 깨지면 그 milestone 은 파서에서 사라지고 총괄 뷰까지 조용히 틀린다."""
    def case(root: Path):
        nasty = 'changesets/a --> b "quoted"'
        assert roadmap_sync.main(["complete", "--milestone", "M1", "--evidence", nasty]) == 0
        text = (root / "ROADMAP.md").read_text(encoding="utf-8")
        marker = next(l for l in text.splitlines() if 'id="M1"' in l)
        assert marker.count('"') % 2 == 0 and marker.endswith("-->")
        assert roadmap_sync.parse_attrs(marker)["evidence"] == nasty  # 왕복 보존

    run_in_tmp(case)


def test_blocked_milestone_is_not_silently_completed():
    def case(root: Path):
        path = root / "ROADMAP.md"
        path.write_text(ROADMAP.replace('id="M1" status="active"', 'id="M1" status="blocked"'),
                        encoding="utf-8")
        assert roadmap_sync.main(["complete", "--milestone", "M1"]) == 1
        assert 'status="blocked"' in path.read_text(encoding="utf-8")
        # 의도한 것이면 --force 로 명시한다
        assert roadmap_sync.main(["complete", "--milestone", "M1", "--force"]) == 0
        assert 'status="completed"' in path.read_text(encoding="utf-8")

    run_in_tmp(case)


def test_gap_check_generates_gap_when_all_closed():
    def case(root: Path):
        assert roadmap_sync.main(["complete", "--milestone", "M1"]) == 0
        assert roadmap_sync.main(["complete", "--milestone", "M2"]) == 0
        code = roadmap_sync.main(["gap-check", "--gap-out", "docs/roadmap-gap.md"])
        assert code == 2
        gap = (root / "docs" / "roadmap-gap.md").read_text(encoding="utf-8")
        assert "Roadmap Gap Review" in gap
        assert "Active harness milestones are exhausted" in gap

    run_in_tmp(case)


def test_gap_check_ignores_non_active_open_statuses():
    def case(root: Path):
        text = (root / "ROADMAP.md").read_text(encoding="utf-8")
        text = text.replace('id="M1" status="active"', 'id="M1" status="pending"')
        text = text.replace('id="M2" status="active"', 'id="M2" status="blocked"')
        (root / "ROADMAP.md").write_text(text, encoding="utf-8")

        code = roadmap_sync.main(["gap-check", "--gap-out", "docs/roadmap-gap.md"])
        assert code == 2
        gap = (root / "docs" / "roadmap-gap.md").read_text(encoding="utf-8")
        assert "Active harness milestones are exhausted" in gap

    run_in_tmp(case)


def test_gap_check_default_prints_gap_without_file():
    def case(root: Path):
        assert roadmap_sync.main(["complete", "--milestone", "M1"]) == 0
        assert roadmap_sync.main(["complete", "--milestone", "M2"]) == 0
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = roadmap_sync.main(["gap-check"])
        assert code == 2
        assert not (root / "docs").exists() or not any((root / "docs").glob("roadmap-gap*.md"))
        out = buf.getvalue()
        assert "Roadmap Gap Review" in out
        assert "Active harness milestones are exhausted" in out

    run_in_tmp(case)


def test_gap_check_active_milestones_no_gap_file():
    def case(root: Path):
        code = roadmap_sync.main(["gap-check"])
        assert code == 0
        assert not (root / "docs").exists() or not any((root / "docs").glob("roadmap-gap*.md"))

    run_in_tmp(case)


def test_gap_report_uses_legacy_north_star_fallback():
    def case(root: Path):
        text = (root / "ROADMAP.md").read_text(encoding="utf-8")
        text = text.replace("> line budget: <=150", "> 북극성: evidence over understanding")
        text = text.replace('<!-- harness:goal id="g1" -->\nGoal: prove the harness with evidence.\n', "")
        (root / "ROADMAP.md").write_text(text, encoding="utf-8")
        assert roadmap_sync.main(["complete", "--milestone", "M1"]) == 0
        assert roadmap_sync.main(["complete", "--milestone", "M2"]) == 0
        code = roadmap_sync.main(["gap-check", "--gap-out", "docs/roadmap-gap.md"])
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


def _scale_ok(root: Path) -> str:
    """Scale lint 를 통과시켜 포인터 검사만 남긴다."""
    text = (root / "ROADMAP.md").read_text(encoding="utf-8")
    text = text.replace(
        "- DoD: run passes",
        "- DoD: run passes\n- Scale: changesets>=2; surfaces: a·b; capability: proof loop",
    )
    text = text.replace('id="M2" status="active"', 'id="M2" status="completed"')
    return text


def test_lint_fails_on_dangling_plan_pointer():
    # 2026-07-20: 아카이브 이동이 백링크를 안 고쳐 이 레포 포인터 18개 중 11개가
    # 빈 주소였다(LA2·LA3 포함). 재개 경로가 끊기므로 completed 라도 면제 없음.
    def case(root: Path):
        text = _scale_ok(root) + "\n- Plan: `plans/2026-07-19-gone.md`\n"
        (root / "ROADMAP.md").write_text(text, encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = roadmap_sync.main(["lint"])
        out = buf.getvalue()
        assert code == 1, out
        assert "dangling plan pointer" in out and "2026-07-19-gone.md" in out

    run_in_tmp(case)


def test_lint_passes_when_pointer_resolves_after_archive_move():
    # 아카이브로 옮긴 뒤 백링크를 `archive/plans/…` 로 갱신하면 통과해야 한다.
    def case(root: Path):
        target = root / "archive" / "plans" / "2026-07-19-moved.md"
        target.parent.mkdir(parents=True)
        target.write_text("# PLAN\n", encoding="utf-8")
        text = _scale_ok(root) + "\n- Plan: `archive/plans/2026-07-19-moved.md`\n"
        (root / "ROADMAP.md").write_text(text, encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = roadmap_sync.main(["lint"])
        assert code == 0, buf.getvalue()

    run_in_tmp(case)


def test_lint_ignores_horizon_pointer_that_exists():
    # plans/horizons/ 경로도 같은 검사 대상 — 실재하면 통과.
    def case(root: Path):
        target = root / "plans" / "horizons" / "2026-x.md"
        target.parent.mkdir(parents=True)
        target.write_text("# HORIZON\n", encoding="utf-8")
        text = _scale_ok(root) + "\n상세 → `plans/horizons/2026-x.md`\n"
        (root / "ROADMAP.md").write_text(text, encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = roadmap_sync.main(["lint"])
        assert code == 0, buf.getvalue()

    run_in_tmp(case)


def test_lint_reports_dangling_pointer_once_per_path():
    # 같은 경로가 여러 번 인용돼도 에러는 1건 — 노이즈 방지.
    def case(root: Path):
        text = _scale_ok(root) + "\n- Plan: `plans/dup.md`\n다시 `plans/dup.md`\n"
        (root / "ROADMAP.md").write_text(text, encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            roadmap_sync.main(["lint"])
        assert buf.getvalue().count("dangling plan pointer") == 1, buf.getvalue()

    run_in_tmp(case)


def test_lint_catches_wrong_prefix_even_when_tail_resolves():
    # cs#245: `docs/archive/plans/x.md` 는 틀린 주소인데, 구 정규식은 `archive/plans/x.md`
    # 만 잘라 매칭해 실재하는 파일로 보고 통과시켰다(cs#244 봉합이 샌 구멍). 접두어를
    # 전부 삼켜 검사해야 "틀린 주소"가 걸린다.
    def case(root: Path):
        target = root / "archive" / "plans" / "2026-07-19-moved.md"
        target.parent.mkdir(parents=True)
        target.write_text("# PLAN\n", encoding="utf-8")
        text = _scale_ok(root) + "\n- Plan: `docs/archive/plans/2026-07-19-moved.md`\n"
        (root / "ROADMAP.md").write_text(text, encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = roadmap_sync.main(["lint"])
        out = buf.getvalue()
        assert code == 1, out
        assert "docs/archive/plans/2026-07-19-moved.md" in out, out

    run_in_tmp(case)


def test_lint_scans_backlog_and_horizon_docs():
    # cs#245: 검사 범위가 ROADMAP 하나면, 수기로 봉합한 BACKLOG·horizon doc 의
    # 끊긴 포인터는 아무도 안 본다 — 실제로 그렇게 10건이 남았다.
    def case(root: Path):
        (root / "ROADMAP.md").write_text(_scale_ok(root), encoding="utf-8")
        (root / "docs").mkdir(exist_ok=True)
        (root / "docs" / "BACKLOG.md").write_text(
            "- Evidence: docs/archive/plans/2026-07-03-ghost.md\n", encoding="utf-8"
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = roadmap_sync.main(["lint"])
        out = buf.getvalue()
        assert code == 1, out
        assert "docs/BACKLOG.md" in out and "2026-07-03-ghost.md" in out, out

    run_in_tmp(case)


def test_lint_ignores_pointers_inside_archive_records():
    # `archive/` 는 record 동결(§B3 — 옛 백링크 정정 안 함). 검사 대상에서 제외한다.
    def case(root: Path):
        (root / "ROADMAP.md").write_text(_scale_ok(root), encoding="utf-8")
        old = root / "archive" / "plans" / "2026-06-01-old.md"
        old.parent.mkdir(parents=True)
        old.write_text("이전 계획 → `plans/2026-05-01-vanished.md`\n", encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = roadmap_sync.main(["lint"])
        assert code == 0, buf.getvalue()

    run_in_tmp(case)


def _repo_with_changesets(names: list[str]) -> Path:
    root = Path(tempfile.mkdtemp())
    for name in names:
        (root / "changesets" / name).mkdir(parents=True)
    return root


# MM6 step-1 (2026-07-21): 토큰 모양만 보고 세면 changeset 이 아닌 산출물까지 센다.
# HQ1 실사례 — Evidence 가 `evidence/harness/20260721-hq1-e2e.md` 하나였는데
# 카운터가 changeset 1개로 읽어 INFLATION 후보 오탐을 냈다.


def test_classify_falls_back_when_repo_has_no_changesets_dir():
    root = Path(tempfile.mkdtemp())
    verified, unresolved = roadmap_sync.classify_changeset_refs(
        ["- Evidence: changesets/20260721-whatever"], root
    )
    assert len(verified) == 1 and unresolved == set()
