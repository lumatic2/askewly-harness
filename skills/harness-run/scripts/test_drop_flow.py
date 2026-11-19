#!/usr/bin/env python3
"""M24 step-4 (2026-11-03): 중단 종결 흐름 E2E — 실제 CLI 를 subprocess 로 돈다."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE.parent.parent / "harness-done" / "templates" / "DROP_TEMPLATE.md"

ROADMAP = """# Roadmap

## Active

<!-- harness:milestone id="M1" status="active" -->
### M1 — 서면 제출
- Status: [ ]
- DoD: 제출본 업로드

<!-- harness:milestone id="M2" status="pending" -->
### M2 — 본선 준비
- Status: [ ]
- DoD: 본선 발표

## Completed
"""


def run(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")


def fill_template(path: Path, milestone: str) -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    filled = (
        text.replace("{milestone-id}", milestone).replace("{제목}", "테스트").replace("{YYYY-MM-DD}", "2026-11-03")
        .replace("{무엇 때문에 접나 — 한두 문장}", "서면평가 미선발로 대회가 끝났다.")
        .replace("{접게 만든 외부 결과의 출처 — 메일·공지·URL·날짜}", "주최 측 결과 메일 2026-11-02")
    )
    lines = []
    for line in filled.splitlines():
        if line.startswith("{") and line.endswith("}"):
            line = "submissions/ 제출본 (커밋 abc123)" if "산출물" in line or "커밋된" in line else "다음 회차 공고"
        lines.append(line)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_drop_flow_end_to_end(tmp_path: Path) -> None:
    (tmp_path / "ROADMAP.md").write_text(ROADMAP, encoding="utf-8")
    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "work.json").write_text(json.dumps({
        "schema_version": 1, "active_work_id": "W1",
        "works": {"W1": {"work_id": "W1", "milestone_id": "M1", "status": "active",
                         "approval": {"plan_sha256": "s1"}}},
    }), encoding="utf-8")

    for milestone, task in (("M1", "W1"), ("M2", "M2")):  # M1 은 work 있음, M2 는 계획서·work 없음
        note = tmp_path / "archive" / "reports" / f"2026-11-03-{milestone}-중단.md"
        fill_template(note, milestone)
        rc = run(str(HERE / "report_close.py"), str(note), "--task-id", task, "--milestone-id", milestone,
                 "--root", str(tmp_path), "--drop", cwd=tmp_path)
        assert rc.returncode == 0, rc.stderr
        rs = run(str(HERE / "roadmap_sync.py"), "--roadmap", str(tmp_path / "ROADMAP.md"), "drop",
                 "--milestone", milestone, "--evidence", note.relative_to(tmp_path).as_posix(),
                 "--reason", "서면평가 미선발", cwd=tmp_path)
        assert rs.returncode == 0, rs.stderr

    events = [json.loads(row) for row in (tmp_path / ".harness" / "execution-ledger.jsonl").read_text(encoding="utf-8").splitlines() if row.strip()]
    assert [e["event"] for e in events] == ["task_dropped", "task_dropped"]
    assert not any(e["event"] == "task_completed" for e in events)
    roadmap = (tmp_path / "ROADMAP.md").read_text(encoding="utf-8")
    assert roadmap.count('status="dropped"') == 2
    state = json.loads((tmp_path / ".harness" / "work.json").read_text(encoding="utf-8"))
    assert state["works"]["W1"]["status"] == "dropped"
    nc = run(str(HERE / "harness_work_state.py"), "next-chained", "--root", str(tmp_path), "--json", cwd=tmp_path)
    assert nc.returncode == 1  # 남은 연쇄 후보 없음 — dropped 는 후보가 아니다
    assert "M1" not in nc.stdout and "M2" not in nc.stdout


def test_completion_path_refuses_drop_note(tmp_path: Path) -> None:
    note = tmp_path / "archive" / "reports" / "2026-11-03-M1-중단.md"
    fill_template(note, "M1")
    rc = run(str(HERE / "report_close.py"), str(note), "--task-id", "M1", "--root", str(tmp_path), cwd=tmp_path)
    assert rc.returncode != 0


def test_dropped_work_with_pending_marker_is_not_chain_candidate(tmp_path: Path) -> None:
    # 감사 권고: ROADMAP 마커가 아직 pending 이어도 work 가 dropped 면 연쇄 후보가 아니다
    (tmp_path / "ROADMAP.md").write_text(
        '<!-- harness:milestone id="M1" status="completed" -->\n'
        '<!-- harness:milestone id="M2" status="pending" -->\n', encoding="utf-8")
    (tmp_path / "plans").mkdir()
    (tmp_path / "plans" / "2026-11-03-m2-next.md").write_text("# Plan\n", encoding="utf-8")
    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "work.json").write_text(json.dumps({
        "schema_version": 1, "active_work_id": "W1",
        "works": {"W1": {"work_id": "W1", "milestone_id": "M1", "status": "completed",
                         "approval": {"plan_sha256": "s1", "chain": ["M2"]}},
                  "W2": {"work_id": "W2", "milestone_id": "M2", "status": "dropped",
                         "approval": {"plan_sha256": "s2"}}},
    }), encoding="utf-8")
    nc = run(str(HERE / "harness_work_state.py"), "next-chained", "--root", str(tmp_path), "--json", cwd=tmp_path)
    assert nc.returncode == 1, nc.stdout
