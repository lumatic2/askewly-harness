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
        # M5 2026-08-20: 부분문자열만 보면 블록이 **어디에 있든** 통과한다. 닫힌
        # milestone 이 진행 섹션에 남는 것이 원래 결함이었으므로 위치까지 단언한다.
        head = text.split("## Next Candidates", 1)[0]
        assert 'id="M1"' not in head

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


# ── M5 (2026-08-20) 섹션 배치 ────────────────────────────────────────────────
# `complete()` 가 블록을 제자리에서만 고쳐 닫은 milestone 이 진행 섹션에 영구히 남았다.
# 밖으로 빼는 유일한 경로였던 `compact()` 는 줄수 게이트에 막혀 있어서, 줄수가 여유로운
# 레포(플릿 실측상 거의 전부)는 배치가 영원히 안 고쳐졌다.


def _section_of(text: str, marker_id: str) -> str:
    """마커가 실제로 어느 `## ` 섹션 아래에 앉아 있는지."""
    current = ""
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
        elif f'id="{marker_id}"' in line:
            return current
    return "(없음)"


ROADMAP_WITH_POINTER = """# ROADMAP

## Active Milestones

<!-- harness:milestone id="M1" status="active" priority="P0" -->
### M1 - first
- DoD: x
- Status: [ ]

<!-- harness:milestone id="M2" status="active" priority="P1" -->
### M2 - second
- DoD: y
- Status: [ ]

## Next Candidates
- N1

## Archive Pointer
See docs/BACKLOG.md
"""


def test_complete_moves_block_out_of_progress_section():
    def case(root: Path):
        assert roadmap_sync.main(["complete", "--milestone", "M1"]) == 0
        text = (root / "ROADMAP.md").read_text(encoding="utf-8")
        assert _section_of(text, "M1") == "Completed"
        assert _section_of(text, "M2") == "Active Milestones"  # 열린 것은 안 건드린다

    run_in_tmp(case)


def test_terminal_section_created_after_last_progress_section():
    # 진행 계열이 여럿이면(Active + Next Candidates 가 표준형) 첫 진행 섹션 뒤에
    # 끼우는 것은 진행 계열을 둘로 쪼개는 짓이다.
    def case(root: Path):
        (root / "ROADMAP.md").write_text(ROADMAP_WITH_POINTER, encoding="utf-8")
        assert roadmap_sync.main(["complete", "--milestone", "M1"]) == 0
        heads = [l[3:].strip() for l in (root / "ROADMAP.md").read_text(encoding="utf-8").splitlines()
                 if l.startswith("## ")]
        assert heads == ["Active Milestones", "Next Candidates", "Completed", "Archive Pointer"]

    run_in_tmp(case)


def test_archive_pointer_is_not_treated_as_a_container():
    # 플릿 33 레포가 `## Archive Pointer` 를 갖고 있다. 이름에 Archive 가 들어가지만
    # docs/BACKLOG.md 를 가리키는 포인터 문단이지 블록을 담는 그릇이 아니다.
    def case(root: Path):
        (root / "ROADMAP.md").write_text(ROADMAP_WITH_POINTER, encoding="utf-8")
        assert roadmap_sync.main(["complete", "--milestone", "M1"]) == 0
        text = (root / "ROADMAP.md").read_text(encoding="utf-8")
        assert _section_of(text, "M1") != "Archive Pointer"

    run_in_tmp(case)


def test_existing_terminal_section_is_reused_and_appended_to():
    # 섹션 끝에 append 하는 것이 계약이다 — 그래야 compact 가 파일 앞에서부터
    # 걷어내는 기존 의미(오래된 것부터 아카이브)가 유지된다.
    def case(root: Path):
        (root / "ROADMAP.md").write_text(
            ROADMAP.replace("## Next Candidates\n- N1\n",
                            '## Completed\n\n<!-- harness:milestone id="M0" status="completed" -->\n'
                            "### M0 - old\n- Status: [x]\n"),
            encoding="utf-8")
        assert roadmap_sync.main(["complete", "--milestone", "M1"]) == 0
        text = (root / "ROADMAP.md").read_text(encoding="utf-8")
        assert text.count("## Completed") == 1  # 중복 생성 금지
        assert text.index('id="M0"') < text.index('id="M1"')  # 오래된 것이 앞

    run_in_tmp(case)


UNCLASSIFIED_SECTION = """# ROADMAP

## 마일스톤

<!-- harness:milestone id="M1" status="completed" priority="P0" -->
### M1 - done
- Status: [x]
"""


def test_unclassified_section_is_left_alone():
    # hygiene 이 침묵하는 구간과 같아야 한다 — 완료·미완이 섞여 사는 미분류 섹션은
    # 레포마다 관습이 달라 무차별 이동이 잔소리가 아니라 파손이 된다.
    def case(root: Path):
        (root / "ROADMAP.md").write_text(UNCLASSIFIED_SECTION, encoding="utf-8")
        assert roadmap_sync.main(["relocate"]) == 0
        text = (root / "ROADMAP.md").read_text(encoding="utf-8")
        assert _section_of(text, "M1") == "마일스톤"
        assert "## Completed" not in text

    run_in_tmp(case)


def test_relocate_preserves_prose_between_markers():
    # 2026-06-20 에 같은 자리에서 실제 데이터 소실이 있었다(compact 가 산문을 삼켰다).
    def case(root: Path):
        (root / "ROADMAP.md").write_text(ROADMAP_WITH_PROSE, encoding="utf-8")
        assert roadmap_sync.main(["relocate"]) == 0
        text = (root / "ROADMAP.md").read_text(encoding="utf-8")
        assert "This prose must survive compaction." in text
        assert _section_of(text, "M1") == "Completed"
        assert _section_of(text, "M2") == "Prose Section"  # 열린 것은 원위치

    run_in_tmp(case)


def test_relocate_is_idempotent_and_never_archives():
    # 배치 이동과 BACKLOG 아카이브는 다른 처분이다 — "ROADMAP 에 남은 종결 마커 =
    # 아직 아카이브되지 않은 것" 이라는 규약이 여기 걸려 있다.
    def case(root: Path):
        assert roadmap_sync.main(["complete", "--milestone", "M1"]) == 0
        once = (root / "ROADMAP.md").read_text(encoding="utf-8")
        assert roadmap_sync.main(["relocate"]) == 0
        assert (root / "ROADMAP.md").read_text(encoding="utf-8") == once  # 2회 = 1회
        assert once.count("harness:milestone") == 2  # 마커 개수 불변
        assert not (root / "BACKLOG.md").exists()
        assert not (root / "docs" / "BACKLOG.md").exists()

    run_in_tmp(case)


def test_skipped_milestones_are_relocated_too():
    # hygiene 의 오배치 판정은 TERMINAL_STATUSES(종결 4종)를 쓴다. completed 전용으로
    # 만들면 그 안내문이 거짓이 된다 — 플릿 실측 `skipped` 9건이 전부 진행 섹션 아래다.
    def case(root: Path):
        (root / "ROADMAP.md").write_text(
            ROADMAP.replace('id="M1" status="active"', 'id="M1" status="skipped"'),
            encoding="utf-8")
        assert roadmap_sync.main(["relocate"]) == 0
        text = (root / "ROADMAP.md").read_text(encoding="utf-8")
        assert _section_of(text, "M1") == "Completed"
        assert 'status="skipped"' in text  # status 는 안 건드린다

    run_in_tmp(case)


def test_relocate_dry_run_writes_nothing():
    def case(root: Path):
        before = (root / "ROADMAP.md").read_text(encoding="utf-8")
        assert roadmap_sync.main(["complete", "--milestone", "M1"]) == 0
        # 이미 옮겨졌으므로 다시 옮길 것이 없다. 새 대상을 만들어 dry-run 을 본다.
        (root / "ROADMAP.md").write_text(before.replace(
            'id="M2" status="active"', 'id="M2" status="completed"'), encoding="utf-8")
        snapshot = (root / "ROADMAP.md").read_text(encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = roadmap_sync.main(["relocate", "--dry-run"])
        assert code == 0
        assert "M2" in buf.getvalue() and "dry-run" in buf.getvalue()
        assert (root / "ROADMAP.md").read_text(encoding="utf-8") == snapshot

    run_in_tmp(case)


def test_selfcheck_refuses_to_write_when_lines_would_be_lost():
    # 이 스크립트는 출고되면 플릿 전 레포의 상태판을 만진다. 잘못 쓴 파일을 되돌리는
    # 것보다 안 쓰는 쪽이 싸다.
    before = ["# R", "## Active", "- keep me", "x"]
    assert roadmap_sync._selfcheck(before, ["# R", "## Active", "x"]) is not None
    assert roadmap_sync._selfcheck(before, before) is None
    # 새로 만든 Completed 헤딩만 예외로 허용한다
    assert roadmap_sync._selfcheck(before, before + ["## Completed"]) is None
    assert roadmap_sync._selfcheck(before, before + ["## 딴것"]) is not None


def test_title_travels_with_the_block_when_it_is_not_a_heading():
    # 플릿 실측 10건(toolshelf 8·knowledge-graph 2)은 마커 다음 줄이 `### 제목` 이
    # 아니라 굵은 글씨·불릿이다. 이들은 no-op 대상이 아니라 정상 이동 대상이다.
    def case(root: Path):
        (root / "ROADMAP.md").write_text(
            "# ROADMAP\n\n## Active Milestones\n\n"
            '<!-- harness:milestone id="M1" status="completed" priority="P0" -->\n'
            "**M1 — 굵은 글씨 제목**\n- Status: [x]\n\n## Next Candidates\n- N1\n",
            encoding="utf-8")
        assert roadmap_sync.main(["relocate"]) == 0
        text = (root / "ROADMAP.md").read_text(encoding="utf-8")
        assert _section_of(text, "M1") == "Completed"
        body = text.split("## Completed", 1)[1]
        assert "**M1 — 굵은 글씨 제목**" in body  # 제목 줄이 블록과 함께 갔다

    run_in_tmp(case)


def test_relocate_noop_when_no_progress_section_exists():
    def case(root: Path):
        (root / "ROADMAP.md").write_text(
            "# ROADMAP\n\n"
            '<!-- harness:milestone id="M1" status="completed" priority="P0" -->\n'
            "### M1 - done\n- Status: [x]\n",
            encoding="utf-8")
        snapshot = (root / "ROADMAP.md").read_text(encoding="utf-8")
        assert roadmap_sync.main(["relocate"]) == 0
        assert (root / "ROADMAP.md").read_text(encoding="utf-8") == snapshot

    run_in_tmp(case)


def test_relocated_block_still_archives_oldest_first():
    # 합성 계약: 배치가 바뀌면 compact 가 걷어가는 집합도 바뀔 수 있다. 섹션 **끝**에
    # append 하는 계약이 "오래된 것부터 아카이브" 라는 기존 의미를 지킨다.
    def case(root: Path):
        with (root / "ROADMAP.md").open("a", encoding="utf-8") as fh:
            for idx in range(40):
                fh.write(f"\nextra line {idx}")
        assert roadmap_sync.main(["complete", "--milestone", "M1", "--summary", "first"]) == 0
        assert roadmap_sync.main(["complete", "--milestone", "M2", "--summary", "second"]) == 0
        text = (root / "ROADMAP.md").read_text(encoding="utf-8")
        assert text.index('id="M1"') < text.index('id="M2"')  # 닫은 순서 = 파일 순서
        assert roadmap_sync.main(["compact", "--max-lines", "70", "--backlog", "BACKLOG.md"]) == 0
        roadmap = (root / "ROADMAP.md").read_text(encoding="utf-8")
        backlog = (root / "BACKLOG.md").read_text(encoding="utf-8")
        assert 'id="M1"' not in roadmap and "M1 - first proof" in backlog  # 오래된 것이 먼저
        assert 'id="M2"' in roadmap

    run_in_tmp(case)


def test_collapse_rules_only_touches_the_seam():
    # 블록을 빼낸 자리에 구분자가 남는다. 하지만 **이음매에서만** 접는다 — 전 파일을
    # 훑으면 이 이동과 무관한 섹션의 구분자까지 조용히 다시 쓴다(2026-08-20 리뷰 적발).
    at = roadmap_sync._collapse_rules_at
    # `a` 바로 밑의 `---` 는 setext 제목 밑줄이므로 fixture 에 빈 줄을 둔다.
    dup = ["a", "", "---", "", "---", "b"]
    assert at(dup, [3]) == ["a", "", "---", "", "b"]
    assert at(dup, []) == dup                      # 이음매가 아니면 안 건드린다
    keep = ["a", "", "---", "x", "---", "b"]
    assert at(keep, [3]) == keep                   # 사이에 내용이 있으면 안 접는다


def test_collapse_never_eats_a_setext_heading():
    # `설계 노트` 다음 줄의 `---` 는 thematic break 가 아니라 그 줄을 h2 로 만드는
    # **밑줄**이다. 접으면 제목이 사라진다 (2026-08-20 리뷰 적발).
    lines = ["---", "", "설계 노트", "---", "본문"]
    assert roadmap_sync._collapse_rules_at(lines, [1]) == lines


def test_block_with_subsection_is_refused_not_split():
    # `_block_end` 는 다음 `###` 에서 멈춘다. 그 경계는 compact(삭제)가 산문을 안
    # 지우려고 만든 것이라 **이동에는 안 맞는다** — 마커만 옮기면 하위 절이 진행
    # 섹션에 고아로 남고, 줄이 사라진 게 아니라서 자기검사도 못 잡는다.
    def case(root: Path):
        (root / "ROADMAP.md").write_text(
            "# ROADMAP\n\n## Active Milestones\n\n"
            '<!-- harness:milestone id="M1" status="completed" priority="P0" -->\n'
            "### M1 - done\n- Status: [x]\n\n### M1 세부\n산문\n\n## Next Candidates\n- N1\n",
            encoding="utf-8")
        snapshot = (root / "ROADMAP.md").read_text(encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            assert roadmap_sync.main(["relocate"]) == 0
        assert (root / "ROADMAP.md").read_text(encoding="utf-8") == snapshot  # 쪼개지 않는다
        assert "건너뜀: M1" in buf.getvalue()  # 조용히 넘어가지도 않는다

    run_in_tmp(case)


def test_moved_blocks_keep_a_blank_line_between_them():
    # 안 넣으면 `- Status: [x]` 다음이 곧바로 다음 마커라 Completed 섹션에서 블록
    # 경계가 안 보인다 (2026-08-20 리뷰 적발, toolshelf 실측).
    def case(root: Path):
        (root / "ROADMAP.md").write_text(
            ROADMAP.replace('id="M1" status="active"', 'id="M1" status="completed"')
                   .replace('id="M2" status="active"', 'id="M2" status="completed"'),
            encoding="utf-8")
        assert roadmap_sync.main(["relocate"]) == 0
        body = (root / "ROADMAP.md").read_text(encoding="utf-8").split("## Completed", 1)[1]
        lines = body.splitlines()
        idx = next(i for i, l in enumerate(lines) if 'id="M2"' in l)
        assert not lines[idx - 1].strip()  # 마커 바로 앞은 빈 줄

    run_in_tmp(case)


def test_message_names_the_actual_section(capsys):
    # 기존 `## 완료 이력` 에 붙였는데 "→ ## Completed" 라고 말하면, 사용자는 그 레포에
    # 없는 섹션을 찾게 된다 (2026-08-20 리뷰 적발).
    def case(root: Path):
        (root / "ROADMAP.md").write_text(
            ROADMAP.replace("## Next Candidates\n- N1\n", "## 완료 이력\n"),
            encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            assert roadmap_sync.main(["complete", "--milestone", "M1"]) == 0
        assert "→ ## 완료 이력" in buf.getvalue()
        assert "## Completed" not in (root / "ROADMAP.md").read_text(encoding="utf-8")

    run_in_tmp(case)


# ── M8 F3 (2026-08-21): lint 언급/사용 표면 재정의 ───────────────────────────
# 사용 표면 = `- Plan:`·`- Evidence:`·`> milestone plan:` 필드 값 (백틱 무관, 면제 없음)
# 면제 표면 = 코드 펜스 · append-only 절 · cross-repo 실재 인용. 그 밖 산문은 검사.


def _lint_errors(root: Path) -> list[str]:
    roadmap = root / "ROADMAP.md"
    return roadmap_sync.dangling_plan_pointers(roadmap, roadmap_sync.read_lines(roadmap))


def test_use_fields_fail_even_in_backticks():
    # 끊긴 필드 값은 백틱이어도 FAIL — 사용 표면까지 면제가 새면 lint 의 존재 이유가 없다.
    def case(root: Path):
        rm = root / "ROADMAP.md"
        rm.write_text(ROADMAP + "\n- Plan: `plans/2026-01-01-ghost.md`\n", encoding="utf-8")
        assert any("ghost" in e for e in _lint_errors(root))
        # `- Evidence:` 와 `> milestone plan:` 리드인도 같은 사용 표면이다
        rm.write_text(ROADMAP + "\n- Evidence: `plans/2026-01-01-ghost2.md`\n", encoding="utf-8")
        assert any("ghost2" in e for e in _lint_errors(root))
        rm.write_text(ROADMAP + "\n> milestone plan: `docs/plans/2026-01-01-ghost3.md`\n", encoding="utf-8")
        assert any("ghost3" in e for e in _lint_errors(root))

    run_in_tmp(case)


def test_fence_and_append_only_paths_pass():
    def case(root: Path):
        rm = root / "ROADMAP.md"
        rm.write_text(
            ROADMAP
            + "\n```text\nplans/2026-01-01-fenced.md\n```\n"
            + "\n## 진행 로그 (append-only)\n- 옛 경로 plans/2026-01-01-logged.md 를 정리했다.\n",
            encoding="utf-8")
        assert _lint_errors(root) == [], _lint_errors(root)
        # 같은 경로가 본문 절 산문에 있으면 FAIL (면제가 절 경계를 넘지 않는다)
        rm.write_text(ROADMAP + "\n## 회고\n- 옛 경로 plans/2026-01-01-logged.md 참조.\n", encoding="utf-8")
        assert any("logged" in e for e in _lint_errors(root))

    run_in_tmp(case)


def test_cross_repo_citation_passes_and_unresolvable_fails():
    # 밀폐형: 실기기 홈이 아니라 주입한 projects_root 로 판정한다 (M8 리뷰 수리 —
    # 기계 결합 fixture 는 다른 기기·CI·레포 이동에서 전제부터 깨진다).
    def case(root: Path):
        projects = root / "projects"
        real = "other-repo/plans/2026-01-01-cited.md"
        (projects / "other-repo" / "plans").mkdir(parents=True)
        (projects / real).write_text("# cited\n", encoding="utf-8")
        rm = root / "ROADMAP.md"

        def errors():
            return roadmap_sync.dangling_plan_pointers(
                rm, roadmap_sync.read_lines(rm), projects_root=projects)

        rm.write_text(ROADMAP + f"\n산문에서 {real} 사례를 인용한다.\n", encoding="utf-8")
        assert errors() == [], errors()
        # 로컬로도 cross-repo 로도 해석 안 되면 그냥 끊긴 포인터다
        rm.write_text(ROADMAP + "\n산문에서 no-such-repo/plans/2026-01-01-nowhere.md 를 인용한다.\n", encoding="utf-8")
        assert any("nowhere" in e for e in errors())

    run_in_tmp(case)


def test_fenced_field_example_is_quotation():
    # 펜스는 필드 리드인보다 우선하는 면제다 — 템플릿 예시를 펜스로 인용한 문서가
    # 오탐되면 안 된다 (M8 리뷰 수리: 판정 순서를 펜스 → 필드 → append-only 로 고정).
    def case(root: Path):
        rm = root / "ROADMAP.md"
        rm.write_text(
            ROADMAP + "\n```markdown\n- Plan: plans/2026-01-01-fenced-example.md\n```\n",
            encoding="utf-8")
        assert _lint_errors(root) == [], _lint_errors(root)

    run_in_tmp(case)


def test_field_inside_append_only_is_still_checked():
    # 필드 리드인은 append-only 절 안에 있어도 사용 표면이다 (필드 우선 판정)
    def case(root: Path):
        rm = root / "ROADMAP.md"
        rm.write_text(
            ROADMAP + "\n## 진행 로그 (append-only)\n- Plan: plans/2026-01-01-ghost4.md\n",
            encoding="utf-8")
        assert any("ghost4" in e for e in _lint_errors(root))

    run_in_tmp(case)


# --- repair-plan-pointers (2026-09-02) — milestone 마감이 만들던 lint FAIL 을 닫는다 ---


def _repair(root: Path, dry_run: bool = False) -> tuple[int, str]:
    argv = ["repair-plan-pointers"] + (["--dry-run"] if dry_run else [])
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = roadmap_sync.main(argv)
    return code, buf.getvalue()


def test_repair_rewrites_archived_plan_pointer():
    # milestone 을 닫고 계획서를 archive/plans/ 로 옮기면 마커의 `- Plan:` 이 끊긴다.
    # 이 명령이 그 자리를 아카이브 사본으로 갱신해 lint 를 PASS 로 되돌린다.
    def case(root: Path):
        (root / "archive" / "plans").mkdir(parents=True)
        (root / "archive" / "plans" / "p.md").write_text("plan", encoding="utf-8")
        rm = root / "ROADMAP.md"
        rm.write_text(ROADMAP + "\n- Plan: plans/p.md\n", encoding="utf-8")
        assert _lint_errors(root)  # 착수 상태 = FAIL
        code, out = _repair(root)
        assert code == 0, out
        assert "archive/plans/p.md" in out
        assert "- Plan: archive/plans/p.md" in rm.read_text(encoding="utf-8")
        assert _lint_errors(root) == []

    run_in_tmp(case)


def test_repair_dry_run_does_not_write():
    def case(root: Path):
        (root / "archive" / "plans").mkdir(parents=True)
        (root / "archive" / "plans" / "p.md").write_text("plan", encoding="utf-8")
        rm = root / "ROADMAP.md"
        rm.write_text(ROADMAP + "\n- Plan: plans/p.md\n", encoding="utf-8")
        before = rm.read_text(encoding="utf-8")
        code, out = _repair(root, dry_run=True)
        assert code == 0
        assert "[dry-run]" in out
        assert rm.read_text(encoding="utf-8") == before

    run_in_tmp(case)


def test_repair_does_not_invent_paths():
    # 아카이브 사본이 없으면 고치지 않고 판정 불가로 보고한다 (경로 위조 금지, M8 D3).
    def case(root: Path):
        rm = root / "ROADMAP.md"
        rm.write_text(ROADMAP + "\n- Plan: plans/gone.md\n", encoding="utf-8")
        code, out = _repair(root)
        assert code == 1
        assert "판정 불가" in out
        assert "- Plan: plans/gone.md" in rm.read_text(encoding="utf-8")

    run_in_tmp(case)


def test_repair_leaves_fenced_and_append_only_prose_alone():
    # 탐지에 안 걸리는 자리(펜스 인용)의 같은 문자열은 치환 대상이 아니다 —
    # 스팬 단위 치환이라 전역 replace 로 예시를 망가뜨리지 않는다.
    def case(root: Path):
        (root / "archive" / "plans").mkdir(parents=True)
        (root / "archive" / "plans" / "p.md").write_text("plan", encoding="utf-8")
        rm = root / "ROADMAP.md"
        rm.write_text(
            ROADMAP
            + "\n- Plan: plans/p.md\n"
            + "\n```markdown\n- Plan: plans/p.md\n```\n",
            encoding="utf-8")
        code, out = _repair(root)
        assert code == 0, out
        text = rm.read_text(encoding="utf-8")
        assert "- Plan: archive/plans/p.md" in text
        assert "```markdown\n- Plan: plans/p.md\n```" in text  # 펜스 예시는 그대로

    run_in_tmp(case)


def test_repair_is_idempotent_and_noop_when_clean():
    def case(root: Path):
        code, out = _repair(root)
        assert code == 0
        assert "대상 없음" in out

    run_in_tmp(case)


def _roadmap_parse_module():
    import sys

    bin_dir = str(Path(__file__).resolve().parents[2] / "session-end" / "bin")
    if bin_dir not in sys.path:
        sys.path.insert(0, bin_dir)
    import roadmap_parse

    return roadmap_parse


def test_drop_marks_and_relocates():
    def case(root: Path):
        code = roadmap_sync.main(
            ["drop", "--milestone", "M1", "--evidence", "notes/drop.md", "--reason", "범위 폐기"]
        )
        assert code == 0
        path = root / "ROADMAP.md"
        text = path.read_text(encoding="utf-8")
        assert 'id="M1" status="dropped"' in text
        assert 'evidence="notes/drop.md"' in text
        assert "- Dropped by: 범위 폐기" in text
        assert "- Evidence: notes/drop.md" in text
        assert "- Status: [x] DROP" in text
        assert "- Status: [ ]\n" in text  # M2 는 그대로
        assert _section_of(text, "M1") == "Completed"
        assert _section_of(text, "M2") == "Active Milestones"
        rp = _roadmap_parse_module()
        _goal, milestones, _parked = rp.parse_roadmap(path)
        m1 = next(m for m in milestones if m["id"] == "M1")
        assert m1["status"] in rp.TERMINAL_STATUSES
        assert m1["status"] == "dropped"
        assert m1["checkbox"].startswith("[x]")

    run_in_tmp(case)


def test_drop_rejects_completed():
    def case(root: Path):
        assert roadmap_sync.main(["complete", "--milestone", "M1"]) == 0
        path = root / "ROADMAP.md"
        before = path.read_bytes()
        with contextlib.redirect_stderr(io.StringIO()):
            code = roadmap_sync.main(
                ["drop", "--milestone", "M1", "--evidence", "e.md", "--reason", "x"]
            )
        assert code != 0
        assert path.read_bytes() == before

    run_in_tmp(case)


def test_drop_is_idempotent_and_not_found_fails():
    def case(root: Path):
        args = ["drop", "--milestone", "M2", "--evidence", "e.md", "--reason", "r"]
        assert roadmap_sync.main(args) == 0
        path = root / "ROADMAP.md"
        after_first = path.read_bytes()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            assert roadmap_sync.main(args) == 0
        assert path.read_bytes() == after_first
        assert "already dropped" in out.getvalue()
        with contextlib.redirect_stderr(io.StringIO()):
            assert roadmap_sync.main(["drop", "--milestone", "M9", "--evidence", "e", "--reason", "r"]) == 1

    run_in_tmp(case)
