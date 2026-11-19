"""handoff_merge.py 계약 테스트 — v3 레포 공용 할 일 큐 (2026-11-07 M25, ADR 0038).

계약: 할 일은 레포 공용 큐다 — 출처(작업 이름)는 표시만, 어느 세션이든 근거를 달아 뺀다 ·
병합은 항목 단위(추가·완료·수정)라 동시 마감이 서로 덮어쓰지 않는다 · 세션은 「최근 작업」 한 줄(7일) ·
14일 안 건드린 할 일은 BACKLOG 「오래된 할 일」 · 만료 절은 없다 · 완료 근거는 커밋 메시지 파일로 ·
옛 형식(v1 단일 문서·v2 세션 블록)은 쓸 때 한 번 이행 · 입력 BOM 은 지운다.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "handoff_merge.py"
spec = importlib.util.spec_from_file_location("handoff_merge", SCRIPT)
hm = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = hm  # dataclass 가 모듈을 찾는다
spec.loader.exec_module(hm)

TODAY = dt.date(2026, 11, 7)


def _merge(existing, tag, stdin, today=TODAY, resolve=None):
    ops = hm.parse_input(stdin)
    if resolve:
        ops.completes.extend(resolve)
    return hm.merge(existing, tag, "Win", ops, today)


def _todos(text):
    return hm.section_lines(text, hm.TODO_H)


def _git(cwd, *a):
    return subprocess.run(["git", "-C", str(cwd), *a], capture_output=True, text=True, check=True,
                          encoding="utf-8").stdout.strip()


def _run(root, tag, stdin, *extra):
    return subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), "--tag", tag, "--today", TODAY.isoformat(),
                           *extra], input=stdin, capture_output=True, text=True, encoding="utf-8")


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    return root


# --- v3 형식 ---------------------------------------------------------------

def test_empty_file_creates_v3():
    r = _merge("", "a", "- 할 일 1\n## 최근 작업\n- 커밋 abc\n")
    assert r.text.startswith(hm.TITLE)
    assert "- 할 일 1 (2026-11-07 · a)" in _todos(r.text)
    assert hm.RECENT_H in r.text and "- 2026-11-07 · a · Win · 커밋 abc" in r.text
    assert hm.BLOCK_H not in r.text and "만료" not in r.text


def test_no_todos_renders_none():
    r = _merge("", "a", "")
    assert hm.TODO_H + "\n- 없음." in r.text and _todos(r.text) == []


def test_same_body_readd_is_noop_and_keeps_date():
    r = _merge("", "a", "- X 한다\n", today=TODAY - dt.timedelta(days=3))
    r2 = _merge(r.text, "b", "- X 한다\n- X 한다 (2026-11-01 · zz)\n")
    assert _todos(r2.text) == ["- X 한다 (2026-11-04 · a)"]  # 결정 5: 다시 쓰기는 「건드림」이 아니다


def test_new_items_go_on_top_in_given_order():
    r = _merge("", "a", "- 옛 일\n")
    r = _merge(r.text, "b", "- 새 일 1\n+ 새 일 2\n")
    assert [ln.split(" (")[0] for ln in _todos(r.text)] == ["- 새 일 1", "- 새 일 2", "- 옛 일"]


# --- 공용 큐: 누구든 근거로 뺀다 ---------------------------------------------------

def test_any_session_completes_with_evidence(tmp_path: Path):
    root = _repo(tmp_path)
    assert _run(root, "b", "- briefing_collect 줄 281 을 고친다\n- B2\n").returncode == 0
    p = _run(root, "a", "완료: briefing_collect = abc123\n## 최근 작업\n- 커밋 def\n")
    assert p.returncode == 0, p.stderr
    text = (root / "HANDOFF.md").read_text(encoding="utf-8")
    assert "briefing_collect" not in text  # 근거는 HANDOFF 본문에 남지 않는다(T4)
    assert "- B2 (2026-11-07 · b)" in text
    assert "완료 1건" in text.split(hm.RECENT_H)[1]
    msg = (Path(_git(root, "rev-parse", "--path-format=absolute", "--git-dir")) / hm.COMMIT_MSG_NAME).read_text(encoding="utf-8")
    assert "briefing_collect 줄 281 을 고친다" in msg and "abc123" in msg and "(b)" in msg


def test_completion_message_file_appends_across_reruns(tmp_path: Path):
    root = _repo(tmp_path)
    _run(root, "b", "- 일 하나\n- 일 둘\n")
    _run(root, "a", "완료: 일 하나 = c1\n")
    _run(root, "a", "완료: 일 둘 = c2\n")
    msg = (root / ".git" / hm.COMMIT_MSG_NAME).read_text(encoding="utf-8")
    assert "c1" in msg and "c2" in msg
    assert "완료 2건" in (root / "HANDOFF.md").read_text(encoding="utf-8")  # 같은 날 같은 작업 재실행은 건수를 잇는다


def test_completion_ambiguous_or_missing_changes_nothing():
    r = _merge("", "b", "- 고친다 X\n- 고친다 Y\n")
    r2 = _merge(r.text, "a", "완료: 고친다 = c1\n완료: 없는 일 = c2\n")
    assert len(_todos(r2.text)) == 2 and r2.completions == []
    assert sum("못 뺐다" in n for n in r2.notes) == 2


def test_completion_without_evidence_is_rejected():
    r = _merge("", "b", "- 끝난 일\n")
    r2 = _merge(r.text, "a", "완료: 끝난 일\n완료: 끝난 일 =  \n")
    assert "끝난 일" in r2.text
    assert sum("근거" in n and "거부" in n for n in r2.notes) == 2


def test_completion_removes_duplicate_bodies_together():
    existing = (hm.TITLE + "\n\n" + hm.TODO_H + "\n- 같은 일 (2026-11-01 · p)\n- 같은 일 [q]\n\n" + hm.RECENT_H + "\n- 없음.\n")
    r = _merge(existing, "a", "완료: 같은 일 = c9\n")
    assert "같은 일" not in r.text and len(r.completions) == 1


def test_completion_reaches_waits():
    r = _merge("", "a", "- ⏳ 2026-12-01 — Y 한다\n")
    r2 = _merge(r.text, "b", "완료: Y 한다 = c9\n")
    assert "Y 한다" not in r2.text and "c9" in r2.completions[0]


def test_resolve_flag_is_alias_of_completion():
    r = _merge("", "b", "- 끝난 일\n")
    r2 = _merge(r.text, "a", "", resolve=[("끝난 일", "c1")])
    assert "끝난 일" not in r2.text
    assert hm.parse_resolve("briefing_collect 줄=4d9c902") == ("briefing_collect 줄", "4d9c902")


def test_edit_replaces_text_and_touches_date():
    r = _merge("", "b", "- 옛 문구로 한다\n", today=TODAY - dt.timedelta(days=10))
    r2 = _merge(r.text, "a", "수정: 옛 문구 => 새 문구로 한다\n")
    assert _todos(r2.text) == ["- 새 문구로 한다 (2026-11-07 · b)"]
    r3 = _merge(r2.text, "a", "수정: 없는 => x\n수정: 새 문구 =>  \n")
    assert r3.text.count("새 문구로 한다") == 1 and sum("수정" in n for n in r3.notes) == 2


# --- 동시 마감 -----------------------------------------------------------------

def test_concurrent_merges_do_not_clobber():
    base = _merge("", "x", "- 원래 일\n## 최근 작업\n- 커밋 0\n").text
    # 두 세션이 같은 원본을 보고 마감한다 — 병합은 그 시점 파일에 항목만 더하므로 차례로 돌면 둘 다 남는다
    first = _merge(base, "a", "- A 가 남긴 일\n## 최근 작업\n- 커밋 1\n").text
    second = _merge(first, "b", "- B 가 남긴 일\n## 최근 작업\n- 커밋 2\n").text
    todos = "\n".join(_todos(second))
    assert "A 가 남긴 일" in todos and "B 가 남긴 일" in todos and "원래 일" in todos
    # 같은 작업 이름(체크포인트 뒤 다른 세션)이어도 덮어쓰지 않는다 — v2 는 같은 태그 블록을 통째로 교체했다
    third = _merge(second, "a", "- A 의 두 번째 일\n## 최근 작업\n- 커밋 3\n").text
    todos = "\n".join(_todos(third))
    assert "A 가 남긴 일" in todos and "A 의 두 번째 일" in todos
    recent = hm.section_lines(third, hm.RECENT_H)
    assert sum(" · a · " in ln for ln in recent) == 1 and any("커밋 3" in ln for ln in recent)


# --- 수명: 14일 할 일 · 기다리는 일 · 최근 작업 7일 ------------------------------------

def test_untouched_14_days_moves_to_backlog():
    r = _merge("", "a", "- 묵은 일\n", today=TODAY - dt.timedelta(days=15))
    r = _merge(r.text, "b", "- 새 일\n", today=TODAY - dt.timedelta(days=1))
    r2 = _merge(r.text, "c", "")
    assert "묵은 일" not in r2.text and "- 새 일 (2026-11-06 · b)" in _todos(r2.text)
    assert r2.backlog_old == ["- 묵은 일 (2026-10-23 · a)"]
    assert any("14일" in n for n in r2.notes)
    # 14일째는 아직 남는다
    r3 = _merge(_merge("", "a", "- 경계 일\n", today=TODAY - dt.timedelta(days=14)).text, "c", "")
    assert "경계 일" in r3.text and r3.backlog_old == []


def test_dated_wait_lives_until_date_plus_7_then_backlog():
    r = _merge("", "a", "- ⏳ 2026-12-07 이후 — 재심한다\n- 지금 할 일\n")
    assert "재심한다" not in "\n".join(_todos(r.text))
    assert "- ⏳ 2026-12-07 이후 — 재심한다 (2026-11-07 · a)" in hm.section_lines(r.text, hm.WAIT_H)
    r2 = _merge(r.text, "b", "", today=dt.date(2026, 12, 14))  # 날짜 + 7일 — 아직
    assert "재심한다" in r2.text
    r3 = _merge(r.text, "b", "", today=dt.date(2026, 12, 15))
    assert "재심한다" not in r3.text and any("재심한다" in ln for ln in r3.backlog_old)


def test_undated_wait_goes_to_backlog_waits():
    r = _merge("", "a", "- ⏳ PR 머지되면 — 문구를 고친다\n- 지금 한다\n")
    assert "문구를 고친다" not in r.text
    assert r.backlog_waits == ["⏳ PR 머지되면 — 문구를 고친다"]


def test_waits_sorted_by_date():
    r = _merge("", "a", "- ⏳ 2026-12-09 — 늦은 일\n- ⏳ 2026-11-20 — 이른 일\n")
    waits = "\n".join(hm.section_lines(r.text, hm.WAIT_H))
    assert waits.index("이른 일") < waits.index("늦은 일")


def test_recent_lines_last_7_days_newest_first():
    r = _merge("", "old", "## 최근 작업\n- 커밋 o\n", today=TODAY - dt.timedelta(days=8))
    r = _merge(r.text, "mid", "## 최근 작업\n- 커밋 m\n", today=TODAY - dt.timedelta(days=2))
    r = _merge(r.text, "new", "## 최근 작업\n- 커밋 n\n- 판정 근거 plans/x.md\n")
    recent = hm.section_lines(r.text, hm.RECENT_H)
    assert recent == ["- 2026-11-07 · new · Win · 커밋 n · 판정 근거 plans/x.md", "- 2026-11-05 · mid · Win · 커밋 m"]


def test_recent_pointer_capped():
    r = _merge("", "a", "## 최근 작업\n- " + "가" * 400 + "\n")
    line = hm.section_lines(r.text, hm.RECENT_H)[0]
    assert len(line) < 220 and line.endswith("…")


# --- 옛 형식 이행 --------------------------------------------------------------

V2 = (
    "# HANDOFF — 세션 간 인계 (git-tracked, session-end 소유 · 세션별 블록 병합)\n\n"
    "## 이어서 할 일\n- 할 일 A [ta]\n- 할 일 B [older 2026-10-20] [tb]\n- 고아 할 일 [gone]\n\n"
    "## 기다리는 일 (날짜가 되면 깬다)\n- ⏳ 2026-12-01 — 기다림 [ta]\n\n"
    "## 세션 블록\n### 2026-11-06 · ta · Windows\n- Milestone(active): M1\n- 커밋: aaa111 push\n\n"
    "### 2026-11-03 · tb · Darwin\n- 그냥 상태 줄\n\n"
    "## 만료 (확인 후 지운다)\n- 최근 만료 [p 2026-10-25]\n- 오래된 만료 [q 2026-10-01]\n\n"
    "## 워크트리에서 온 메모 — feat (2026-11-01)\n\n- repo-level note\n"
)


def test_migrates_v2_blocks_todos_waits_expired():
    r = _merge(V2, "new", "")
    t = r.text
    assert hm.BLOCK_H not in t and "## 만료" not in t and hm.RECENT_H in t
    todos = _todos(t)
    assert "- 할 일 A (2026-11-06 · ta)" in todos
    assert "- 할 일 B (2026-11-03 · tb)" in todos
    assert "- 고아 할 일 (2026-11-07 · gone)" in todos  # 블록이 없으면 오늘
    assert "- ⏳ 2026-12-01 — 기다림 (2026-11-06 · ta)" in hm.section_lines(t, hm.WAIT_H)
    recent = hm.section_lines(t, hm.RECENT_H)
    assert "- 2026-11-06 · ta · Windows · 커밋: aaa111 push" in recent
    assert "- 2026-11-03 · tb · Darwin · 그냥 상태 줄" in recent
    assert r.backlog_old == ["- 최근 만료 (2026-10-25 · p)"]  # 21일 넘은 만료는 버린다
    assert "오래된 만료" not in t
    assert "## 워크트리에서 온 메모 — feat (2026-11-01)" in t and "- repo-level note" in t
    assert any("이행" in n for n in r.notes)


def test_migration_happens_once():
    r = _merge(V2, "new", "- 새 일\n")
    r2 = _merge(r.text, "new", "")
    assert _todos(r.text) == _todos(r2.text)
    assert r2.backlog_old == [] and not any("이행" in n for n in r2.notes)


def test_migrates_v1():
    v1 = (
        "# HANDOFF — 세션 간 인계 (git-tracked, session-end 소유)\n\n"
        "## 이어서 할 일\n> 2026-11-01 세션 종료 시 기록\n\n- 옛 할 일\n- 없음.\n\n"
        "### 현재 상태 / 주의점\n- 상태 s0\n"
    )
    r = _merge(v1, "new", "- 새 할 일\n")
    assert _todos(r.text) == ["- 새 할 일 (2026-11-07 · new)", "- 옛 할 일 (2026-11-01 · legacy)"]
    assert hm.RECENT_H in r.text
    assert "## 현재 상태 / 주의점" in r.text and "- 상태 s0" in r.text  # 할 일이 아닌 인계는 보존(T5)
    assert any("v1" in n for n in r.notes)


def test_unknown_sections_preserved_in_v3():
    r = _merge("", "a", "- A\n")
    text = r.text + "\n## 손으로 쓴 메모\n\n- 레포 메모\n"
    r2 = _merge(text, "b", "- B\n")
    assert "## 손으로 쓴 메모" in r2.text and "- 레포 메모" in r2.text


# --- 입력 ---------------------------------------------------------------------

def test_bom_first_line_is_not_duplicated():
    r = _merge("", "a", "- X 한다\n")
    r2 = _merge("﻿" + r.text, "a", "﻿- X 한다\n")
    assert _todos(r2.text) == ["- X 한다 (2026-11-07 · a)"]
    assert "﻿" not in r2.text


def test_parse_input_strips_carried_tails():
    ops = hm.parse_input("- 리뷰를 본다 [rea-windows-1014] [briefing-1019 2026-10-20]\n"
                         "- `a[0]` 를 고친다 (2026-11-01 · x)\n## 상태\n- 커밋 c\n- 없음.\n")
    assert ops.adds == ["리뷰를 본다", "`a[0]` 를 고친다"]
    assert ops.recent == ["커밋 c"]


def test_main_writes_backlog_and_prints_with_hint(tmp_path: Path):
    root = _repo(tmp_path)
    (root / "docs").mkdir()
    (root / "docs" / "BACKLOG.md").write_text("# BACKLOG\n\n## Completed\n\n- old\n", encoding="utf-8")
    old = TODAY - dt.timedelta(days=20)
    (root / "HANDOFF.md").write_text(
        hm.TITLE + "\n\n" + hm.TODO_H + f"\n- 묵은 일 ({old.isoformat()} · z)\n\n" + hm.RECENT_H + "\n- 없음.\n",
        encoding="utf-8")
    p = _run(root, "t", "- ⏳ PR 머지되면 — 고친다\n- 지금 한다\n")
    assert p.returncode == 0, p.stderr
    assert "커밋 헬퍼가 같은 커밋에 넣는다" in p.stdout
    bl = (root / "docs" / "BACKLOG.md").read_text(encoding="utf-8")
    assert "- ⏳ PR 머지되면 — 고친다 (2026-11-07 · t)" in bl
    assert "- 묵은 일 (2026-10-18 · z)" in bl
    assert bl.index(hm.BACKLOG_WAIT_H) < bl.index("## Completed") and bl.index(hm.BACKLOG_OLD_H) < bl.index("## Completed")
    assert bl.rstrip().endswith("- old")


def test_tag_with_separator_rejected(tmp_path: Path):
    p = _run(_repo(tmp_path), "a·b", "")
    assert p.returncode == 2


def test_main_checkout_resolves_linked_worktree(tmp_path: Path):
    repo = _repo(tmp_path)
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "init")
    wt = tmp_path / "wt"
    _git(repo, "worktree", "add", "-q", str(wt), "-b", "feat")
    assert hm.main_checkout(wt).resolve() == repo.resolve()
    assert hm.main_checkout(repo).resolve() == repo.resolve()


# --- 마감 리뷰 반영 (2026-11-07) ------------------------------------------------

def test_hash_lines_in_preserved_sections_survive():
    r = _merge("", "a", "- A\n")
    text = r.text + "\n## 메모\n\n```bash\n# 주석 줄\nls\n```\n"
    r2 = _merge(text, "b", "")
    assert "# 주석 줄" in r2.text and "ls" in r2.text


def test_v2_without_block_section_is_not_v1():
    text = ("# HANDOFF\n\n## 이어서 할 일\n- 할 일 [a]\n\n## 기다리는 일 (날짜가 되면 깬다)\n- ⏳ 2026-12-01 — 기다림 [a]\n")
    r = _merge(text, "b", "")
    assert "- ⏳ 2026-12-01 — 기다림 (2026-11-07 · a)" in hm.section_lines(r.text, hm.WAIT_H)
    assert "- 할 일 (2026-11-07 · a)" in _todos(r.text)


def test_shortened_recent_header_still_v3():
    r = _merge("", "a", "- A\n## 최근 작업\n- 커밋 1\n")
    text = r.text.replace(hm.RECENT_H, "## 최근 작업")
    r2 = _merge(text, "b", "")
    assert "- 2026-11-07 · a · Win · 커밋 1" in hm.section_lines(r2.text, hm.RECENT_H)
    assert not any("이행" in n for n in r2.notes)


def test_completion_evidence_may_contain_equals():
    r = _merge("", "b", "- 고친다\n")
    r2 = _merge(r.text, "a", "완료: 고친다 = commit a=b\n")
    assert "고친다" not in "\n".join(_todos(r2.text)) and r2.completions[0].endswith("— commit a=b")


def test_bracket_without_space_is_not_a_tail_tag():
    r = _merge("", "a", "- foo[0] 를 고친다 [WIP]\n- bar[0]\n")
    assert "- foo[0] 를 고친다 (2026-11-07 · a)" in _todos(r.text)
    assert "- bar[0] (2026-11-07 · a)" in _todos(r.text)


def test_same_day_rerun_without_pointer_keeps_previous_pointer():
    r = _merge("", "a", "- X\n## 최근 작업\n- 커밋 abc\n")
    r2 = _merge(r.text, "b", "- Y\n")
    r3 = _merge(r2.text, "a", "완료: Y = c1\n")
    assert "- 2026-11-07 · a · Win · 커밋 abc · 완료 1건" in hm.section_lines(r3.text, hm.RECENT_H)


def test_simultaneous_processes_do_not_clobber(tmp_path: Path):
    root = _repo(tmp_path)
    _run(root, "x", "- 원래 일\n")
    procs = [subprocess.Popen([sys.executable, str(SCRIPT), "--root", str(root), "--tag", f"t{i}", "--today", TODAY.isoformat()],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
             for i in range(6)]
    for i, p in enumerate(procs):
        p.communicate(f"- 동시 일 {i}\n".encode("utf-8"), timeout=60)
    todos = "\n".join(_todos((root / "HANDOFF.md").read_text(encoding="utf-8")))
    assert all(f"동시 일 {i}" in todos for i in range(6)) and "원래 일" in todos
    assert not (root / ".git" / hm.LOCK_NAME).exists()


def test_backlog_change_is_listed_for_commit_helper(tmp_path: Path):
    root = _repo(tmp_path)
    p = _run(root, "t", "- ⏳ PR 머지되면 — 고친다\n")
    assert p.returncode == 0, p.stderr
    assert (root / ".git" / hm.WITH_NAME).read_text(encoding="utf-8").split() == ["docs/BACKLOG.md"]


def test_migrates_v1_without_todos_keeps_all_sections():
    # 감사 실례(a-private-repo): 할 일 0 · `## ` 절만 있는 v1 이 2034→274 바이트로 사라졌다
    v1 = ("# HANDOFF\n\n## 상태: 대회 미제출 종료 — PARK (2026-08-04)\n\n해커톤 미제출.\n\n"
          "## 재개한다면 여기서 시작\n\n- **먼저 답할 질문**: 정체 —\n  SaaS 인가 데모인가.\n\n"
          "## 현재 상태 / 주의점\n\n- 배포 명령: `node scripts/vercel-deploy.mjs <dir> <name>`\n\n"
          "```bash\n# 주석\nls\n```\n")
    r = _merge(v1, "new", "")
    for s in ("## 상태: 대회 미제출 종료 — PARK (2026-08-04)", "해커톤 미제출.", "## 재개한다면 여기서 시작",
              "- **먼저 답할 질문**: 정체 —", "  SaaS 인가 데모인가.", "## 현재 상태 / 주의점",
              "- 배포 명령: `node scripts/vercel-deploy.mjs <dir> <name>`", "# 주석"):
        assert s in r.text, s
    assert any("보존" in n for n in r.notes)
    r2 = _merge(r.text, "new2", "")
    assert r2.text.count("## 재개한다면 여기서 시작") == 1 and "- 배포 명령" in r2.text


def test_migrates_v1_wrapped_todo_and_stray_prose():
    v1 = ("# H\n\n## 이어서 할 일\n> 2026-11-01 세션 종료 시 기록\n\n- 긴 할 일 앞부분\n  뒷부분이다\n\n"
          "설명 문단 한 줄\n")
    r = _merge(v1, "n", "")
    assert "- 긴 할 일 앞부분 뒷부분이다 (2026-11-01 · legacy)" in _todos(r.text)
    assert "## 옛 문서 메모 (v1 이행 때 옮김)" in r.text and "설명 문단 한 줄" in r.text


def test_stdin_bom_bytes_do_not_duplicate_item(tmp_path):
    """PowerShell `Get-Content -Raw | python` 이 첫 줄 앞에 BOM 을 남겨도 같은 항목이 두 줄이 되지 않는다."""
    root = _repo(tmp_path)
    for raw in (b"- X \xed\x95\x9c\xeb\x8b\xa4\n",                        # 평문
                b"\xef\xbb\xbf- X \xed\x95\x9c\xeb\x8b\xa4\n",            # UTF-8 BOM
                "ï»¿- X 한다\n".encode("utf-8"),                           # BOM 바이트를 Latin-1 로 읽어 다시 UTF-8 로 보낸 글자
                b"\xef\xbb\xbf- X \xed\x95\x9c\xeb\x8b\xa4\r\n"):         # CRLF
        r = subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), "--tag", "a",
                            "--today", TODAY.isoformat()], input=raw, capture_output=True)
        assert r.returncode == 0, r.stderr
    text = (root / "HANDOFF.md").read_text(encoding="utf-8")
    assert _todos(text) == ["- X 한다 (2026-11-07 · a)"]
    assert "﻿" not in text and "ï»¿" not in text


def test_existing_file_bom_before_bullet_is_not_duplicated():
    """이미 오염된 HANDOFF(줄 선두 BOM)에 같은 항목을 다시 넣어도 중복되지 않는다."""
    base = _merge("", "a", "- X 한다\n").text
    polluted = base.replace("- X 한다", "﻿- X 한다")
    r = _merge(polluted, "a", "- X 한다\n")
    assert _todos(r.text) == ["- X 한다 (2026-11-07 · a)"]


def test_completion_zero_hit_already_gone_in_recent_is_info_not_warning():
    """앞선 세션이 이미 뺀 항목: 최근 작업 절에 그 문자열이 있으면 경고(못 뺐다)가 아니다."""
    existing = "## 이어서 할 일\n- 다른 일 하나\n## 최근 작업\n- 2026-11-07 · a · Win · 린트 고침 abc123\n"
    r = _merge(existing, "b", "완료: 린트 고침 = abc123\n")
    assert not any("못 뺐다" in n for n in r.notes)
    assert any("이미 빠져 있다" in n and "린트 고침" in n for n in r.notes)
    assert r.completions == []


def test_completion_zero_hit_not_anywhere_keeps_warning():
    existing = "## 이어서 할 일\n- 다른 일 하나\n## 최근 작업\n- 2026-11-07 · a · Win · 무관한 줄\n"
    r = _merge(existing, "b", "완료: 없는 일 = abc123\n")
    assert any("완료 처리 못 뺐다" in n and "0건" in n for n in r.notes)
    assert not any("이미 빠져 있다" in n for n in r.notes)


def test_completion_two_hits_keeps_warning_even_if_in_recent():
    existing = ("## 이어서 할 일\n- 고친다 X\n- 고친다 Y\n## 최근 작업\n"
                "- 2026-11-07 · a · Win · 고친다 했다\n")
    r = _merge(existing, "b", "완료: 고친다 = c1\n")
    assert any("완료 처리 못 뺐다" in n and "2건" in n for n in r.notes)
    assert not any("이미 빠져 있다" in n for n in r.notes)
