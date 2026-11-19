"""기다리는 일·백로그 계약 (2026-11-07 · v3 M25) — 날짜 없는 기다리는 일과 14일 묵은 할 일은 레포 백로그
두 절로 간다(첫 `## ` 앞). 지켜보는 장치가 있는 일·다른 레포 일은 경고."""
from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "handoff_merge.py"
spec = importlib.util.spec_from_file_location("handoff_merge_w", SCRIPT)
hm = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = hm  # dataclass 가 모듈을 찾는다
spec.loader.exec_module(hm)

TODAY = dt.date(2026, 11, 7)


def test_split_backlog_by_date():
    keep, backlog = hm.split_backlog(["⏳ 리서처 10건 쌓이면 — 집계한다", "⏳ 2026-12-01 — 본다", "그냥 한다"])
    assert backlog == ["⏳ 리서처 10건 쌓이면 — 집계한다"]
    assert keep == ["⏳ 2026-12-01 — 본다", "그냥 한다"]


def test_add_backlog_section_before_first_heading_and_dedupes():
    text = "# BACKLOG\n\n> x\n\n## Completed\n\n- old\n"
    out, n = hm.add_backlog(text, ["⏳ 조건 — 일"], "t", TODAY)
    assert n == 1
    assert out.index(hm.BACKLOG_WAIT_H) < out.index("## Completed")
    assert "- ⏳ 조건 — 일 (2026-11-07 · t)" in out
    out2, n2 = hm.add_backlog(out, ["⏳ 조건 — 일", "⏳ 다른 조건 — 일2"], "u", TODAY)
    assert n2 == 1 and out2.count("조건 — 일 (") == 1 and "다른 조건 — 일2 (2026-11-07 · u)" in out2
    sec = out2.split(hm.BACKLOG_WAIT_H)[1].split("## Completed")[0]
    assert sec.index("일 (2026") < sec.index("일2 (")
    # roadmap_sync.compact 가 끝에 덧붙여도 섞이지 않는다
    assert out2.rstrip().endswith("- old")


def test_old_todo_section_goes_after_wait_section_and_before_completed():
    text = "# BACKLOG\n\n## Completed\n\n- old\n"
    out, _ = hm.add_backlog(text, ["⏳ 조건 — 일"], "t", TODAY)
    out, n = hm.add_backlog_lines(out, hm.BACKLOG_OLD_H, ["- 묵은 일 (2026-10-01 · z)", "- 묵은 일 (2026-10-02 · y)"])
    assert n == 1
    assert out.index(hm.BACKLOG_WAIT_H) < out.index(hm.BACKLOG_OLD_H) < out.index("## Completed")
    assert out.rstrip().endswith("- old")


def test_add_backlog_creates_file_text():
    out, n = hm.add_backlog("", ["⏳ c — d"], "t", TODAY)
    assert n == 1 and out.startswith("# BACKLOG") and "## Completed" in out


def test_lint_flags_monitored_and_foreign_repo(tmp_path: Path):
    projects = tmp_path / "projects"
    for name in ("the-orchestration-repo", "knowledge-graph"):
        (projects / name).mkdir(parents=True)
    root = projects / "the-orchestration-repo"
    warns = hm.lint_todos([
        "`/oss-contribute followup` 으로 #13042 응답을 본다",
        "⏳ M22 커밋 뒤 — knowledge-graph 의 manifest 에 넣는다",
        "`knowledge-graph` 에서 노드를 고친다",
        "the-orchestration-repo 의 문서를 고친다",
        "평범한 일",
    ], root, projects)
    assert sum("지켜보는 장치" in w for w in warns) == 1
    assert sum("다른 레포(knowledge-graph)" in w for w in warns) == 2
    assert len(warns) == 3
