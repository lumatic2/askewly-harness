#!/usr/bin/env python3
"""handoff_merge.py — HANDOFF.md 레포 공용 할 일 큐 병합 (v3 · 2026-11-07 M25, ADR 0038).

v2(세션 소유 블록)는 「남의 할 일」이라는 개념을 만들었다. 그런데 이 작업 방식에서는 세션이 끝나면
다음 일은 언제나 다른 세션이 한다 — 할 일의 주인은 세션이 아니라 레포다. 그래서 v3 는
**할 일을 레포 공용 큐로**, 세션은 **「최근 작업」 한 줄**로만 남기고, 병합은 블록 교체가 아니라
**항목 단위 조작(추가·완료·수정)** 이라 동시 마감이 서로 덮어쓰지 않는다.

파일 형식 (v3):
    # HANDOFF — 세션 간 인계 (git-tracked, session-end 소유 · 레포 공용 할 일 큐)

    ## 이어서 할 일
    - <행동> (<YYYY-MM-DD> · <작업 이름>)      ← 날짜 = 마지막으로 추가·수정한 날. 작업 이름은 출처 표시일 뿐
    - 없음.

    ## 기다리는 일 (날짜가 되면 깬다)
    - ⏳ <날짜가 든 조건> — <행동> (<YYYY-MM-DD> · <작업 이름>)

    ## 최근 작업 (7일 · 세션당 한 줄)
    - <날짜> · <작업 이름> · <기기> · <커밋·근거 포인터>

    (그 밖의 절은 손대지 않고 끝에 그대로 보존한다)

수명:
- 할 일은 14일 동안 추가·수정이 없으면 레포 백로그 「오래된 할 일」로 내린다(「아직 유효」 확인으로 날짜를
  갱신하는 장치는 없다 — 같은 본문을 다시 넣어도 날짜는 그대로다).
- 기다리는 일은 조건의 날짜 + 7일이 지나면 「오래된 할 일」로. 날짜 없는 기다리는 일은 백로그 「기다리는 일」로.
- 최근 작업 줄은 7일. 같은 작업 이름이면 교체(체크포인트 뒤 끝내기).
- 「만료」 절은 없다.

완료 근거는 HANDOFF 본문에 남기지 않고 `<git-dir>/HANDOFF_COMMIT_MSG` 에 덧붙인다 — `handoff_commit.sh` 가
그 본문을 핸드오프 커밋 메시지 본문으로 싣고 지운다. 최근 작업 줄에는 `완료 N건` 만.

옛 형식은 **쓸 때 한 번** 이행한다(읽는 쪽 — 주입 훅·브리핑 — 은 두 형식을 다 읽는다):
- v2 할 일·기다리는 일 → 항목(날짜 = 그 태그 블록 날짜, 블록이 없으면 오늘)
- v2 블록 → 최근 작업 줄(`커밋:` 상태 줄을 160자로, 없으면 첫 상태 줄)
- v2 「만료」 절 → 21일 안 된 것만 백로그 「오래된 할 일」, 더 묵은 것은 버린다(git 이력에 있다)
- v1 단일 문서 → 항목(날짜 = 기록일, 작업 이름 legacy)

사용:
    handoff_merge.py --root <repo> --tag <작업 이름> [--machine <label>] [--pull] [--today YYYY-MM-DD]
                     [--resolve 일부=근거 ...] < 입력
입력(stdin):
    - <행동>                       추가 (`+ <행동>` 도 같다)
    - ⏳ <조건> — <행동>           기다리는 일 추가 (조건에 날짜가 없으면 백로그로)
    완료: <일부> = <근거>           본문 기준 정확히 1건 일치하는 할 일·기다리는 일을 뺀다(같은 본문 여러 줄은 함께)
    수정: <일부> => <새 문구>       정확히 1건 일치하는 항목을 찾아 **그 줄 전체를** 새 문구로 대체한다(날짜 = 오늘)
                                   왼쪽 = 줄을 찾는 조각(부분 치환 아님), 오른쪽 = 그 줄을 통째로 대체할 전체 문구.
                                   예) `수정: 린트 고친다 => 린트를 고치고 CI 에서 확인한다` → 매칭된 줄 전체가 오른쪽 문구 한 줄이 된다
    ## 최근 작업
    - <커밋·근거 포인터>           이 세션의 최근 작업 줄(여러 줄이면 ` · ` 로 잇는다)
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import platform
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")
except Exception:  # pragma: no cover
    pass

TITLE = "# HANDOFF — 세션 간 인계 (git-tracked, session-end 소유 · 레포 공용 할 일 큐)"
TODO_H = "## 이어서 할 일"
WAIT_H = "## 기다리는 일 (날짜가 되면 깬다)"
RECENT_H = "## 최근 작업 (7일 · 세션당 한 줄)"
# v2 절 — 이행할 때만 읽는다
BLOCK_H = "## 세션 블록"
EXPIRED_H = "## 만료 (확인 후 지운다)"
BACKLOG_WAIT_H = "## 기다리는 일 (조건이 되면 — session-end 가 보냄)"
BACKLOG_OLD_H = "## 오래된 할 일 (14일 안 건드려 내려옴)"
BACKLOG_INTRO = {
    BACKLOG_WAIT_H: "> 지켜볼 장치도 날짜도 없는 기다리는 일. 항상 읽히지 않는다 — 조건이 됐을 때 찾아 읽고, 끝나면 지운다.",
    BACKLOG_OLD_H: "> HANDOFF 할 일 중 14일 동안 추가·수정이 없던 것과 날짜 + 7일이 지난 기다리는 일. 다시 할 거면 HANDOFF 에 새로 넣는다.",
}
COMMIT_MSG_NAME = "HANDOFF_COMMIT_MSG"
WITH_NAME = "HANDOFF_WITH"  # 병합기가 바꾼 백로그 경로 — handoff_commit.sh 가 같은 커밋에 넣는다
LOCK_NAME = "HANDOFF.lock"
LOCK_WAIT_SEC = 20
WAIT_MARK = "⏳"
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
MONITORED_RE = re.compile(r"oss-contribute followup|상류 응답|메인테이너[^—]{0,40}(답|응답|리뷰)")
TODO_DAYS = 14
WAIT_GRACE_DAYS = 7
RECENT_DAYS = 7
EXPIRED_KEEP_DAYS = 21  # v2 만료 절 이행: 이보다 묵은 항목은 버린다
POINTER_MAX = 160
BLOCK_RE = re.compile(r"^### (\d{4}-\d{2}-\d{2}) · ([^·]+?) · (.+)$")
RECENT_RE = re.compile(r"^- (\d{4}-\d{2}-\d{2}) · ([^·]+?) · ([^·]+?) · (.*)$")
SUFFIX_RE = re.compile(r"\s*\((\d{4}-\d{2}-\d{2}) · ([^()]*)\)\s*$")  # v3 꼬리 `(날짜 · 작업 이름)`
TAG_SUFFIX_RE = re.compile(r"\s*\[([^\[\]]+)\]\s*$")
TAIL_TAGS_RE = re.compile(r"(?:\s+\[[^\[\]`]{1,60}\])+\s*$")  # v2 이월 꼬리표 `[a] [b 2026-10-20]`
EXPIRED_DATE_RE = re.compile(r"\[[^\[\]]*?(\d{4}-\d{2}-\d{2})\]\s*$")
DONE_COUNT_RE = re.compile(r"(?: · )?완료 (\d+)건$")
NONE = ("없음.", "없음")


def strip_tails(text: str) -> str:
    """머리 `- ` 와 v3 꼬리·v2 꼬리표를 뗀 본문."""
    body = text[2:] if text.startswith("- ") else text
    prev = None
    while prev != body:
        prev = body
        body = SUFFIX_RE.sub("", body)
        body = TAIL_TAGS_RE.sub("", body)
    return body.strip()


def norm(text: str) -> str:
    """중복 판정 키 — 꼬리를 모두 떼고 공백을 정리한 본문."""
    return " ".join(strip_tails(text).split())


def machine_label() -> str:
    # handoff_commit.sh 와 같은 규칙: ASCII hostname, 비면 OS 이름(Windows·Darwin·Linux)
    host = re.sub(r"[^A-Za-z0-9._-]", "", platform.node() or "")
    return host or (platform.system() or "machine")


def main_checkout(root: Path) -> Path:
    """linked worktree 면 main 체크아웃 경로, 아니면 root 그대로."""
    try:
        git_dir = subprocess.run(["git", "-C", str(root), "rev-parse", "--path-format=absolute", "--git-dir"],
                                 capture_output=True, text=True, check=True).stdout.strip()
        common = subprocess.run(["git", "-C", str(root), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                                capture_output=True, text=True, check=True).stdout.strip()
        if git_dir and common and Path(git_dir) != Path(common):
            wt = subprocess.run(["git", "-C", str(root), "worktree", "list", "--porcelain"],
                                capture_output=True, text=True, check=True).stdout
            for line in wt.splitlines():
                if line.startswith("worktree "):
                    return Path(line[len("worktree "):].strip())
    except (subprocess.CalledProcessError, OSError):
        pass
    return root


def git_dir(root: Path) -> Path | None:
    try:
        out = subprocess.run(["git", "-C", str(root), "rev-parse", "--path-format=absolute", "--git-dir"],
                             capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return None
    return Path(out) if out else None


# --- 입력 ---------------------------------------------------------------------

@dataclass
class Ops:
    adds: list[str] = field(default_factory=list)
    completes: list[tuple[str, str]] = field(default_factory=list)
    edits: list[tuple[str, str]] = field(default_factory=list)
    recent: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)


def parse_input(text: str) -> Ops:
    ops = Ops()
    in_recent = False
    # BOM(U+FEFF)과, BOM 바이트 EF BB BF 를 Latin-1 로 읽었다 UTF-8 로 다시 보낸 글자(ï»¿)를 줄마다 벗긴다 —
    # PowerShell `Get-Content -Raw | python` 이 첫 줄 앞에 남겨 같은 항목이 중복 줄로 들어간 실측(누적 4회).
    for raw in text.splitlines():
        line = raw.replace("﻿", "").replace("ï»¿", "").rstrip()
        if not line.strip():
            continue
        if line.startswith("## ") or line.startswith("### "):
            in_recent = "최근 작업" in line or "상태" in line
            continue
        body = line.strip()
        if body[:2] in ("- ", "+ "):
            body = body[2:].strip()
        if body.startswith("완료:"):
            part, sep, evidence = split_evidence(body[len("완료:"):])
            if not sep or not part.strip() or not evidence.strip():
                ops.rejected.append(f"거부 — 근거 없는 완료는 받지 않는다(`완료: <일부> = <근거>`): {body[:80]}")
            else:
                ops.completes.append((part.strip(), evidence.strip()))
            continue
        if body.startswith("수정:"):
            part, sep, new = body[len("수정:"):].partition("=>")
            if not sep or not part.strip() or not strip_tails(new.strip()):
                ops.rejected.append(f"거부 — 수정은 `수정: <일부> => <새 문구>` 형식이다: {body[:80]}")
            else:
                ops.edits.append((part.strip(), strip_tails(new.strip())))
            continue
        if body in NONE:
            continue
        if in_recent:
            ops.recent.append(body)
        else:
            body = strip_tails(body)  # 이월하면서 옛 꼬리를 끌고 오지 않는다
            if body and body not in NONE:
                ops.adds.append(body)
    return ops


def split_evidence(raw: str) -> tuple[str, str, str]:
    """`일부 = 근거` — 양옆 공백 있는 첫 ` = ` 를 구분자로(근거에 `a=b`·URL 쿼리가 와도 된다). 없으면 첫 `=`."""
    if " = " in raw:
        return raw.partition(" = ")
    return raw.partition("=")


def parse_resolve(raw: str) -> tuple[str, str]:
    text, sep, evidence = split_evidence(raw)
    if not sep or not text.strip() or not evidence.strip():
        raise argparse.ArgumentTypeError("--resolve 는 '<할 일 일부>=<근거(커밋 등)>' 형식이다")
    return text.strip(), evidence.strip()


# --- 읽기 (v3 · v2 · v1) --------------------------------------------------------

def section_lines(text: str, header: str) -> list[str]:
    """절의 `- ` 줄(「없음.」 제외)."""
    lines = text.lstrip("﻿").splitlines()
    try:
        start = lines.index(header)
    except ValueError:
        return []
    out = []
    for ln in lines[start + 1:]:
        if ln.startswith("## "):
            break
        if ln.startswith("- ") and ln[2:].strip() not in NONE:
            out.append(ln)
    return out


@dataclass
class State:
    todos: list[dict] = field(default_factory=list)   # {text, date, tag}
    waits: list[dict] = field(default_factory=list)
    recent: list[dict] = field(default_factory=list)  # {date, tag, machine, pointer}
    expired: list[dict] = field(default_factory=list)  # v2 만료 절 → 이행
    other: list[str] = field(default_factory=list)
    version: str = "v3"


def _safe_date(raw: str, today: dt.date) -> dt.date:
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        return today


def _item(line: str, today: dt.date, block_dates: dict[str, dt.date]) -> dict | None:
    body = line[2:].strip()
    if not body or body in NONE:
        return None
    m = SUFFIX_RE.search(body)
    if m:
        return {"text": strip_tails(body), "date": _safe_date(m.group(1), today), "tag": m.group(2).strip()}
    m = TAG_SUFFIX_RE.search(body)
    if m:  # v2 — 마지막 꼬리표가 그 할 일의 블록 태그
        tag = m.group(1).strip().split(" ")[0]
        return {"text": strip_tails(body), "date": block_dates.get(tag, today), "tag": tag}
    return {"text": strip_tails(body), "date": today, "tag": "-"}  # 손으로 쓴 줄


def parse_existing(text: str, today: dt.date) -> State:
    text = text.lstrip("﻿")
    st = State()
    if not text.strip():
        return st
    lines = text.splitlines()
    heads = [ln for ln in lines if ln.startswith("## ")]
    structured = any(h.startswith(("## 최근 작업", BLOCK_H, "## 기다리는 일", "## 만료")) for h in heads)
    if not structured:
        return _parse_v1(lines, today)
    st.version = "v3" if any(h.startswith("## 최근 작업") for h in heads) and BLOCK_H not in heads else "v2"
    block_dates: dict[str, dt.date] = {}
    for ln in lines:
        bm = BLOCK_RE.match(ln)
        if bm:
            d = _safe_date(bm.group(1), today)
            tag = bm.group(2).strip()
            block_dates[tag] = max(d, block_dates.get(tag, d))
    section = None
    cur: dict | None = None
    known = (TODO_H, WAIT_H, RECENT_H, BLOCK_H, EXPIRED_H)
    for ln in lines:
        if ln.startswith("## "):
            section = next((h for h in known if ln.startswith(h)), None)
            if section is None and ln.startswith("## 최근 작업"):
                section = RECENT_H  # 손으로 줄인 헤더도 같은 절
            cur = None
            if section is None:
                st.other.append(ln)
                section = "other"
            continue
        if section == "other":
            st.other.append(ln)
            continue
        if section is None or ln.startswith("# "):
            continue
        if section in (TODO_H, WAIT_H):
            if ln.startswith("- "):
                it = _item(ln, today, block_dates)
                if it:
                    (st.waits if it["text"].startswith(WAIT_MARK) else st.todos).append(it)
            continue
        if section == RECENT_H:
            rm = RECENT_RE.match(ln)
            if rm:
                st.recent.append({"date": _safe_date(rm.group(1), today), "tag": rm.group(2).strip(),
                                  "machine": rm.group(3).strip(), "pointer": rm.group(4).strip()})
            continue
        if section == BLOCK_H:
            bm = BLOCK_RE.match(ln)
            if bm:
                cur = {"date": _safe_date(bm.group(1), today), "tag": bm.group(2).strip(),
                       "machine": bm.group(3).strip(), "states": []}
                st.recent.append(cur)
            elif cur is not None and ln.startswith("- "):
                cur["states"].append(ln[2:].strip())
            continue
        if section == EXPIRED_H and ln.startswith("- "):
            body = ln[2:].strip()
            m = EXPIRED_DATE_RE.search(body)
            d = _safe_date(m.group(1), today) if m else today
            tm = TAG_SUFFIX_RE.search(body)
            tag = DATE_RE.sub("", tm.group(1)).strip() if tm else "-"
            st.expired.append({"text": strip_tails(body), "date": d, "tag": tag or "-"})
    for r in st.recent:
        if "states" in r:
            states = r.pop("states")
            pick = next((s for s in states if s.startswith("커밋:")), states[0] if states else "-")
            r["pointer"] = cap(pick)
    while st.other and not st.other[-1].strip():
        st.other.pop()
    return st


def _parse_v1(lines: list[str], today: dt.date) -> State:
    """v1 단일 문서 — 「이어서 할 일」 의 직속 불릿만 항목으로 옮기고 나머지는 원문 그대로 「그 밖의 절」로 보존한다.

    v1 에는 할 일이 아닌 인계(재개 지점·배포 명령·확정 사실·함정)가 절로 들어 있다 — 버리면 인계가 사라진다
    (2026-11-07 M25 마감 감사: a-private-repo 2034→274 바이트). `### ` 하위 절은 `## ` 로 올려 보존한다.
    """
    st = State(version="v1")
    date = today
    in_todo = sub = False
    seen_h2 = False
    stray: list[str] = []
    last_todo: dict | None = None
    for line in lines:
        m = re.match(r"^> (\d{4}-\d{2}-\d{2}) 세션 종료 시 기록", line)
        if m:
            date = _safe_date(m.group(1), today)
            continue
        if line.startswith("## "):
            seen_h2 = True
            in_todo, sub, last_todo = "이어서 할 일" in line, False, None
            if not in_todo:
                st.other.append(line)
            continue
        if not seen_h2:
            if line.strip() and not line.startswith("# "):
                stray.append(line)
            continue
        if not in_todo:
            st.other.append(line)
            continue
        if line.startswith("### "):
            sub, last_todo = True, None
            st.other.append("## " + line[4:].strip())
            continue
        if sub:
            st.other.append(line)
            continue
        if line.startswith("- "):
            body = strip_tails(line[2:].strip())
            last_todo = None
            if body and body not in NONE:
                last_todo = {"text": body, "date": date, "tag": "legacy"}
                (st.waits if body.startswith(WAIT_MARK) else st.todos).append(last_todo)
            continue
        if line.strip() and last_todo is not None and line[:1].isspace():
            last_todo["text"] += " " + line.strip()  # 줄바꿈된 할 일 이어 붙이기
            continue
        if line.strip():
            stray.append(line)
    if stray:
        st.other = ["## 옛 문서 메모 (v1 이행 때 옮김)", *stray, "", *st.other]
    while st.other and not st.other[-1].strip():
        st.other.pop()
    return st


# --- 병합 ---------------------------------------------------------------------

def cap(text: str, limit: int = POINTER_MAX) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def wait_date(text: str) -> dt.date | None:
    """`⏳ <조건> — <할 일>` 의 조건 쪽 첫 날짜. 없으면 None."""
    cond = text.split("—", 1)[0]
    m = DATE_RE.search(cond)
    if not m:
        return None
    try:
        return dt.date.fromisoformat(m.group(0))
    except ValueError:
        return None


def split_backlog(todos: list[str]) -> tuple[list[str], list[str]]:
    """날짜 없는 `⏳` 할 일을 떼어 낸다 → (HANDOFF 로 갈 것, 백로그로 갈 것)."""
    keep, backlog = [], []
    for t in todos:
        (backlog if t.startswith(WAIT_MARK) and wait_date(t) is None else keep).append(t)
    return keep, backlog


def fmt_item(it: dict) -> str:
    return f"- {it['text']} ({it['date'].isoformat()} · {it['tag']})"


@dataclass
class Result:
    text: str
    notes: list[str]
    completions: list[str]
    backlog_old: list[str]
    backlog_waits: list[str]


def _match(items: list[dict], part: str) -> list[dict]:
    return [it for it in items if part in it["text"]]


def merge(existing: str, tag: str, machine: str, ops: Ops, today: dt.date) -> Result:
    notes: list[str] = list(ops.rejected)
    st = parse_existing(existing, today)
    pool = st.todos + st.waits  # 순서 보존용 참조 — 아래에서 다시 나눈다
    if st.version != "v3":
        kept = sum(1 for ln in st.other if ln.strip())
        notes.append(f"옛 형식({st.version}) → v3 이행: 할 일 {len(st.todos)} · 기다리는 일 {len(st.waits)} · "
                     f"최근 작업 {len(st.recent)}" + (f" · 만료 절 {len(st.expired)}건 정리" if st.expired else "")
                     + (f" · 그 밖의 절 {kept}줄 보존" if kept else ""))
    # 수정 — 정확히 1건(같은 본문 여러 줄은 함께)
    for part, new in ops.edits:
        hits = _match(pool, part)
        bodies = {norm(it["text"]) for it in hits}
        if len(bodies) != 1:
            notes.append(f"수정 못 했다 — '{part}' 가 할 일 {len(bodies)}건에 맞는다(정확히 1건이어야 한다)")
            continue
        for i, it in enumerate(hits):
            if i == 0:
                it["text"], it["date"] = new, today
            else:
                pool.remove(it)
        notes.append(f"수정: {bodies.pop()} → {new}")
    # 완료 — 정확히 1건, 근거는 커밋 메시지 파일로
    completions: list[str] = []
    for part, evidence in ops.completes:
        hits = _match(pool, part)
        bodies = {norm(it["text"]) for it in hits}
        if not bodies and any(part in r["pointer"] for r in st.recent):
            # 앞선 세션이 이미 뺐다 — 지금 HANDOFF 에는 없고 최근 작업 줄에 그 문자열이 있다(경고 아님)
            notes.append(f"완료 처리 건너뜀 — '{part}' 는 이미 빠져 있다(최근 작업 절에 있다)")
            continue
        if len(bodies) != 1:
            notes.append(f"완료 처리 못 뺐다 — '{part}' 가 할 일·기다리는 일 {len(bodies)}건에 맞는다(정확히 1건이어야 한다)")
            continue
        for it in hits:
            pool.remove(it)
        body = bodies.pop()
        src = hits[0]["tag"]
        completions.append(f"완료: {body} ({src}) — {evidence}")
        notes.append(f"완료 처리: {body} ({src}) — {evidence}" + (f" (같은 본문 {len(hits)}줄)" if len(hits) > 1 else ""))
    # 추가 — 같은 본문이면 아무 일도 안 한다(날짜 갱신 없음)
    adds, backlog_waits = split_backlog(ops.adds)
    seen = {norm(it["text"]) for it in pool}
    fresh: list[dict] = []
    for a in adds:
        key = norm(a)
        if not key or key in seen:
            continue
        seen.add(key)
        fresh.append({"text": a, "date": today, "tag": tag})
    pool = fresh + pool
    # 같은 본문 중복 정리(이행·손 편집에서 생긴 것) — 앞(새 것)만
    uniq: list[dict] = []
    keys: set[str] = set()
    for it in pool:
        k = norm(it["text"])
        if k in keys:
            continue
        keys.add(k)
        uniq.append(it)
    todos = [it for it in uniq if not it["text"].startswith(WAIT_MARK)]
    waits = [it for it in uniq if it["text"].startswith(WAIT_MARK)]
    # 수명
    backlog_old: list[str] = []
    kept_todos = []
    for it in todos:
        if (today - it["date"]).days > TODO_DAYS:
            backlog_old.append(fmt_item(it))
        else:
            kept_todos.append(it)
    if len(todos) - len(kept_todos):
        notes.append(f"{TODO_DAYS}일 안 건드린 할 일 {len(todos) - len(kept_todos)}건 → 백로그 「오래된 할 일」")
    kept_waits = []
    for it in waits:
        d = wait_date(it["text"])
        if d is None:
            backlog_waits.append(it["text"])
        elif (today - d).days > WAIT_GRACE_DAYS:
            backlog_old.append(fmt_item(it))
            notes.append(f"기다리는 일 날짜 {d} + {WAIT_GRACE_DAYS}일 지남 → 백로그 「오래된 할 일」: {it['text']}")
        else:
            kept_waits.append(it)
    kept_waits.sort(key=lambda it: wait_date(it["text"]) or dt.date.max)
    old_exp = 0
    for it in st.expired:
        if (today - it["date"]).days <= EXPIRED_KEEP_DAYS and norm(it["text"]) not in keys:
            backlog_old.append(fmt_item(it))
        else:
            old_exp += 1
    if old_exp:
        notes.append(f"만료 절에서 {EXPIRED_KEEP_DAYS}일 넘었거나 살아 있는 할 일과 겹친 {old_exp}건 버림 — git 이력에 남는다")
    # 최근 작업 — 같은 작업 이름이면 교체, 7일
    prev_done = 0
    prev_pointer = "-"
    for r in st.recent:
        if r["tag"] == tag and r["date"] == today:
            m = DONE_COUNT_RE.search(r["pointer"])
            prev_done = int(m.group(1)) if m else 0
            prev_pointer = DONE_COUNT_RE.sub("", r["pointer"]).strip() or "-"
    recent = [r for r in st.recent if r["tag"] != tag]
    # 같은 날 같은 작업 재실행(체크포인트 → 끝내기)에서 새 포인터가 없으면 앞 포인터를 잇는다
    pointer = cap(" · ".join(ops.recent)) if ops.recent else prev_pointer
    done = prev_done + len(completions)
    if done:
        pointer = (pointer + " · " if pointer != "-" else "") + f"완료 {done}건"
    recent.insert(0, {"date": today, "tag": tag, "machine": machine, "pointer": pointer})
    recent = [r for r in recent if (today - r["date"]).days <= RECENT_DAYS]
    recent.sort(key=lambda r: r["date"], reverse=True)  # 안정 정렬 — 같은 날짜는 이번 세션이 앞
    text = render(kept_todos, kept_waits, recent, st.other)
    return Result(text, notes, completions, backlog_old, backlog_waits)


def render(todos: list[dict], waits: list[dict], recent: list[dict], other: list[str]) -> str:
    out = [TITLE, "", TODO_H]
    out += [fmt_item(it) for it in todos] or ["- 없음."]
    if waits:
        out += ["", WAIT_H, *(fmt_item(it) for it in waits)]
    out += ["", RECENT_H]
    out += [f"- {r['date'].isoformat()} · {r['tag']} · {r['machine']} · {r['pointer']}" for r in recent] or ["- 없음."]
    if other:
        out += ["", *other]
    return "\n".join(out).rstrip("\n") + "\n"


# --- 백로그 -------------------------------------------------------------------

def backlog_path(root: Path) -> Path:
    for cand in (root / "docs" / "BACKLOG.md", root / "BACKLOG.md"):
        if cand.exists():
            return cand
    return root / "docs" / "BACKLOG.md"


def add_backlog_lines(text: str, header: str, items: list[str]) -> tuple[str, int]:
    """백로그 절(header)에 완성된 `- …` 줄을 덧붙인다(같은 본문은 건너뜀). 관리 절은 첫 비관리 `## ` 앞에 둔다 —
    `roadmap_sync.compact` 가 파일 끝에 월별 절을 덧붙이므로 끝에 두면 섞인다. → (새 본문, 추가 수)."""
    text = text.lstrip("﻿")
    lines = text.splitlines() if text.strip() else [
        "# BACKLOG", "", "> Compressed milestone archive. ROADMAP.md is capped at 150 lines.", "", "## Completed"]
    managed = (BACKLOG_WAIT_H, BACKLOG_OLD_H)
    if header in lines:
        start = lines.index(header)
    else:
        at = next((i for i, ln in enumerate(lines) if ln.startswith("## ") and ln not in managed), len(lines))
        block = [header, "", BACKLOG_INTRO.get(header, ""), ""] if BACKLOG_INTRO.get(header) else [header, ""]
        lines[at:at] = block
        start = at
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    have = {norm(ln) for ln in lines[start + 1:end] if ln.startswith("- ")}
    new = []
    for ln in items:
        key = norm(ln)
        if not key or key in have:
            continue
        have.add(key)
        new.append(ln if ln.startswith("- ") else f"- {ln}")
    insert_at = end
    while insert_at > start + 1 and not lines[insert_at - 1].strip():
        insert_at -= 1
    lines[insert_at:insert_at] = new
    after = insert_at + len(new)
    if after < len(lines) and lines[after].startswith("## ") and lines[after - 1].strip():
        lines.insert(after, "")  # 다음 절과 붙지 않게
    return "\n".join(lines).rstrip("\n") + "\n", len(new)


def add_backlog(text: str, items: list[str], tag: str, today: dt.date) -> tuple[str, int]:
    """날짜 없는 기다리는 일을 백로그 「기다리는 일」 절로."""
    return add_backlog_lines(text, BACKLOG_WAIT_H, [f"- {t} ({today.isoformat()} · {tag})" for t in items])


def lint_todos(todos: list[str], root: Path, projects: Path | None = None) -> list[str]:
    """쓰지 말아야 할 할 일로 보이는 것 — 경고만(막지 않는다)."""
    projects = projects or (Path.home() / "projects")
    try:
        names = {p.name for p in projects.iterdir() if p.is_dir() and p.name != root.name}
    except OSError:
        names = set()
    warns = []
    for t in todos:
        body = t.split("—", 1)[1].strip() if t.startswith(WAIT_MARK) and "—" in t else t
        if MONITORED_RE.search(t):
            warns.append(f"지켜보는 장치(브리핑 상류 응답)가 이미 있는 일로 보인다 — HANDOFF 에 쓰지 않는다: {t[:80]}")
        m = re.match(r"^`?([A-Za-z0-9._-]+)`?\s*(의|에서|에)\s", body)
        if m and m.group(1) in names:
            warns.append(f"다른 레포({m.group(1)}) 할 일로 보인다 — 그 레포 HANDOFF 에 쓴다(--root): {t[:80]}")
    return warns


def append_commit_msg(root: Path, lines: list[str]) -> Path | None:
    gd = git_dir(root)
    if gd is None:
        return None
    path = gd / COMMIT_MSG_NAME
    have = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    add = [ln for ln in lines if ln not in have]
    if add:
        path.write_text("\n".join(have + add) + "\n", encoding="utf-8", newline="\n")
    return path


class Lock:
    """`<git-dir>/HANDOFF.lock` 배타 잠금 — 같은 체크아웃의 동시 마감이 읽기-수정-쓰기 경합으로 서로를 지우지 않게.
    LOCK_WAIT_SEC 안에 못 얻으면(죽은 잠금 등) 경고 후 잠금 없이 진행한다 — 마감을 막지 않는다."""

    def __init__(self, root: Path):
        gd = git_dir(root)
        self.path = (gd / LOCK_NAME) if gd else None
        self.held = False

    def __enter__(self):
        import time
        if self.path is None:
            return self
        deadline = time.monotonic() + LOCK_WAIT_SEC
        while True:
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                self.held = True
                return self
            except FileExistsError:
                if time.monotonic() > deadline:
                    print(f"[handoff] 잠금 {self.path} 를 {LOCK_WAIT_SEC}초 안에 못 얻음 — 잠금 없이 진행(죽은 잠금이면 지운다)")
                    return self
                time.sleep(0.1)

    def __exit__(self, *exc):
        if self.held:
            try:
                os.remove(str(self.path))
            except OSError:
                pass
        return False


def append_with(root: Path, rel: str) -> None:
    gd = git_dir(root)
    if gd is None:
        return
    path = gd / WITH_NAME
    have = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    if rel not in have:
        path.write_text("\n".join(have + [rel]) + "\n", encoding="utf-8", newline="\n")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".")
    ap.add_argument("--tag", required=True, help="작업 이름(계획서 slug·워크트리 브랜치 등, '·' '[' ']' '(' ')' 금지)")
    ap.add_argument("--machine", default=None)
    ap.add_argument("--pull", action="store_true", help="병합 전 git pull --ff-only (실패는 경고)")
    ap.add_argument("--today", default=None)
    ap.add_argument("--resolve", action="append", default=[], type=parse_resolve, metavar="할일일부=근거",
                    help="`완료: 일부 = 근거` 의 별칭. 반복 가능")
    args = ap.parse_args(argv)
    if any(ch in args.tag for ch in "·[]()"):
        print("[handoff] 작업 이름(--tag)에 '·' '[' ']' '(' ')' 를 쓸 수 없다")
        return 2
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    root = main_checkout(Path(args.root))
    if root != Path(args.root):
        print(f"[handoff] linked worktree — main 체크아웃({root})의 HANDOFF.md 에 병합")
    path = root / "HANDOFF.md"
    if args.pull:
        r = subprocess.run(["git", "-C", str(root), "pull", "--ff-only", "-q"], capture_output=True, text=True)
        if r.returncode != 0:
            print("[handoff] pull 실패 — 로컬본에 병합 (" + (r.stderr.strip().splitlines() or ["?"])[-1] + ")")
    ops = parse_input(sys.stdin.read() if not sys.stdin.isatty() else "")
    ops.completes.extend(args.resolve)
    pre_notes = lint_todos(ops.adds, root)
    with Lock(root):
        return _merge_locked(args, ops, root, path, today, pre_notes)


def _merge_locked(args, ops: Ops, root: Path, path: Path, today: dt.date, pre_notes: list[str]) -> int:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    res = merge(existing, args.tag, args.machine or machine_label(), ops, today)
    notes = pre_notes + res.notes
    if res.backlog_waits or res.backlog_old:
        bpath = backlog_path(root)
        btext = bpath.read_text(encoding="utf-8") if bpath.exists() else ""
        btext, nw = add_backlog(btext, res.backlog_waits, args.tag, today)
        btext, no = add_backlog_lines(btext, BACKLOG_OLD_H, res.backlog_old)
        rel = bpath.relative_to(root).as_posix()
        if nw or no:
            _write(bpath, btext)
            append_with(root, rel)
        total = len(res.backlog_waits) + len(res.backlog_old)
        notes.append(f"백로그 {nw + no}건 추가(기다리는 일 {nw} · 오래된 할 일 {no} · {total - nw - no}건은 이미 있음) → {rel}"
                     + (" — 커밋 헬퍼가 같은 커밋에 넣는다" if nw or no else ""))
    _write(path, res.text)
    if res.completions:
        mp = append_commit_msg(root, res.completions)
        notes.append(f"완료 근거 {len(res.completions)}건 → 커밋 메시지 파일 {mp}" if mp
                     else "git 레포가 아니라 완료 근거를 커밋 메시지에 못 남긴다")
    for n in notes:
        print(f"[handoff] {n}")
    print(f"[handoff] 병합 완료: [{args.tag}] 추가 {len(ops.adds)} · 완료 {len(res.completions)} · 수정 {len(ops.edits)} → {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
