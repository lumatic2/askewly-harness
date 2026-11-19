"""ROADMAP.md 마커 파서 — session-end 의 ROADMAP 위생 점검 전용.

2026-09-21 이관: 원래 `the-orchestration-repo/scripts/portfolio_status.py` 안에 있었으나,
그 스크립트는 전 레포 총괄 뷰(`PORTFOLIO.generated.md`)를 만드는 것이 본체였고 그 뷰는
다른 계층 정본으로 계층 정본이 옮겨 가면서 은퇴했다. 파서만 남은 유일한 소비자인
여기로 옮긴다 — 레포 하나의 ROADMAP 을 읽는 일은 원래 총괄이 아니라 레포 단위 작업이다.

원본 주석(실측 근거)은 그대로 보존한다.
"""

import re
from pathlib import Path  # noqa: F401 — 호출자가 Path 를 넘긴다

GOAL_RE = re.compile(r"<!--\s*harness:goal\s+(?P<attrs>[^>]*?)-->")
MILESTONE_RE = re.compile(r"<!--\s*harness:milestone\s+(?P<attrs>[^>]*?)-->")
ATTR_RE = re.compile(r'(\w+)="([^"]*)"')
HEADING_RE = re.compile(r"^#{2,4}\s+(?P<title>.+?)\s*$")
# milestone 제목을 heading 이 아니라 굵은 줄로 쓰는 레포가 있다 (2026-08-17
# `check_generated_view.py` 적발: `toolshelf` 8건 `- **M9 · …** — 꼬리`,
# `knowledge-graph` 2건 `**M6 — …**`). heading 만 보면 그 10건이 title=None 이 돼
# 화면에 id 로만 뜬다. 굵은 *필드 이름* 은 제목이 아니므로 걸러 낸다.
BOLD_TITLE_RE = re.compile(r"^\s*(?:-\s*)?\*\*(?P<title>.+?)\*\*\s*(?P<tail>.*)$")
BOLD_TITLE_STOPWORDS = {
    "dod", "evidence", "gap", "status", "plan", "scale", "summary",
    "dropped by", "completed at", "blocked by", "note",
}
# milestone 블록의 끝을 정하는 상위 절 경계. `##` 는 문서의 절이지 milestone 제목이
# 아니다 (milestone 은 `###`).
SECTION_BOUNDARY_RE = re.compile(r"^##\s+\S")
FIELD_RE = re.compile(r"^\s*-\s*(?P<key>DoD|Evidence|Gap|Status|Plan|Scale)\s*:\s*(?P<val>.*)$", re.I)



def parse_attrs(raw):
    return dict(ATTR_RE.findall(raw))


def read_text(path):
    # 일부 ROADMAP 은 BOM 이 있어 utf-8-sig 로 읽는다.
    return path.read_text(encoding="utf-8-sig", errors="replace")


def parse_roadmap(path):
    """ROADMAP.md 에서 goal 1개와 milestone 목록을 뽑는다."""
    text = read_text(path)
    lines = text.splitlines()

    goal = None
    milestones = []
    parked = None
    # 마커가 있는 줄 번호를 먼저 모아 블록 경계를 정한다.
    marks = []
    for i, line in enumerate(lines):
        m = GOAL_RE.search(line)
        if m:
            marks.append((i, "goal", parse_attrs(m.group("attrs"))))
            continue
        m = MILESTONE_RE.search(line)
        if m:
            marks.append((i, "milestone", parse_attrs(m.group("attrs"))))

    # 첫 마커 이전 머리말에서 레포 단위 동결 선언을 찾는다 (인용문 `>` 줄만 대상).
    head_end = marks[0][0] if marks else min(len(lines), 30)
    for line in lines[:head_end]:
        if not line.lstrip().startswith(">"):
            continue
        content = line.lstrip("> ").strip()
        if not PARK_DECL_RE.match(content):
            continue
        # 마커 모양의 **첫 줄이 판정한다.** 해제문이면 거기서 멈춘다 — 이어서 찾으면
        # 그 아래 보존해 둔 옛 선언을 살아 있는 것으로 줍는다(2026-08-15 실측:
        # `luma3-portfolio` 은 3행이 해제, 6행이 "(이하 PARK 기록 — 동결 보존)" 아래의 옛 선언).
        # 해제문 = 취소선으로 시작하거나, 콜론 앞 머리에 「해제」가 있는 줄.
        if content.startswith("~~") or "해제" in content.split(":", 1)[0]:
            break
        parked = content
        break

    for idx, (line_no, kind, attrs) in enumerate(marks):
        end = marks[idx + 1][0] if idx + 1 < len(marks) else len(lines)
        # 다음 마커가 없으면 블록이 파일 끝까지 늘어나, 그 아래 있는 상위 절 제목을
        # 이 milestone 의 제목으로 주워 온다 (2026-08-16 실측: `toolshelf` 의 M9 가
        # 「Next Candidates」로, `knowledge-graph` 의 마지막 마커가 「Closed Horizon」
        # 으로 표시됐다 — id 는 멀쩡한데 화면 이름만 거짓이었다).
        # milestone 제목은 플릿 전수에서 `###` 이므로(265건 vs `##` 2건, 그 2건이
        # 정확히 이 버그다) 레벨 2 제목을 블록 경계로 삼는다.
        for offset, line in enumerate(lines[line_no + 1 : end]):
            if SECTION_BOUNDARY_RE.match(line):
                end = line_no + 1 + offset
                break
        block = lines[line_no + 1 : end]

        title = None
        fields = {}
        open_key = None  # 여러 줄로 접힌 필드 값을 이어붙이기 위한 커서
        for line in block:
            if title is None:
                h = HEADING_RE.match(line)
                if h:
                    title = h.group("title")
                    open_key = None
                    continue
                b = BOLD_TITLE_RE.match(line)
                if b:
                    cand = b.group("title").strip()
                    if cand.lower().rstrip(":").strip() not in BOLD_TITLE_STOPWORDS:
                        title = cand
                        open_key = None
                        continue
            f = FIELD_RE.match(line)
            if f:
                key = f.group("key").lower()
                if key in fields:
                    open_key = None  # 이미 채운 필드는 덮지 않는다
                else:
                    fields[key] = f.group("val").strip()
                    open_key = key
                continue
            # `- Gap:` 다음 줄이 들여쓰기된 이어쓰기면 같은 값으로 합친다.
            # 빈 줄·새 불릿·새 마커를 만나면 끊는다.
            if open_key:
                if line.strip() and line.startswith((" ", "\t")) and not line.lstrip().startswith("- "):
                    fields[open_key] = (fields[open_key] + " " + line.strip()).strip()
                else:
                    open_key = None

        if kind == "goal":
            # goal 은 마커 바로 다음 본문 한 줄이 목표 문장인 경우가 많다.
            summary = title
            if summary is None:
                for line in block:
                    if line.strip() and not line.startswith("<!--"):
                        summary = line.strip()
                        break
            goal = {
                "id": attrs.get("id"),
                "status": attrs.get("status"),
                "summary": summary,
                "line": line_no + 1,
            }
        else:
            checkbox = fields.get("status", "")
            milestones.append(
                {
                    "id": attrs.get("id"),
                    "status": attrs.get("status"),
                    "priority": attrs.get("priority"),
                    "title": title,
                    "gap": fields.get("gap"),
                    "plan": fields.get("plan"),
                    "checkbox": checkbox or None,
                    "held": bool(checkbox and HOLD_RE.search(checkbox)),
                    "line": line_no + 1,
                }
            )

    return goal, milestones, parked


TERMINAL_STATUSES = {"completed", "skipped", "dropped", "archived"}
# 진행 중으로 보는 어휘. `active` 가 정본이고 나머지는 레포별 변종 — 흡수하되 아래에서 별도 보고한다.
ACTIVE_STATUSES = {"active", "in_progress"}
# 진행 중이지만 스스로 막혔다고 선언한 상태.
BLOCKED_STATUSES = {"blocked"}
CANONICAL_STATUSES = TERMINAL_STATUSES | {"active", "pending", "blocked"}
# 이 일수를 넘도록 커밋이 없고 의지 선언(진행중/PARK)도 없으면 판정 대기 큐로 내린다.
DECISION_QUEUE_DAYS = 30
# 레포 단위 동결 선언 — ROADMAP 첫 마커 이전 머리말에 쓴다. 예: `> **PARK (2026-07-03)**: ...`
PARK_RE = re.compile(r"\bPARK\b|동결|휴면", re.I)
# ⚠ 위 PARK_RE 는 **단어 등장**을 잡는다 — 선언 판정에 그대로 쓰면 안 된다.
# 2026-08-15 M8 실측 오검출 3건: `law-mcp`(본문의 "기록 동결") · `ai-guide`("PARK 해제") ·
# `luma3-portfolio`(취소선 친 옛 선언). 선언은 인용문 내용이 마커로 **시작**해야 한다.
PARK_DECL_RE = re.compile(r"^[*~\s]*(?:\bPARK\b|동결|휴면)", re.I)
# milestone 단위 보류 선언 — `- Status: [ ] **보류(2026-07-12)** — 사용자 결정: ...`
HOLD_RE = re.compile(r"보류|\bHOLD\b|\bPARK\b|\bdeferred\b|이월", re.I)


def checkbox_mismatch(ms):
    """마커 status 와 `- Status: [x]` 체크박스가 어긋나는지.

    completed 뿐 아니라 skipped/dropped 도 종결 상태다 — `[x] SKIP` 은 정상.
    """
    cb = (ms.get("checkbox") or "").strip()
    if not cb:
        return False
    # `[x]` 완료 · `[-]` 취소/보류 — 둘 다 "더 안 건드림" 종결 표시로 본다.
    done_cb = cb[:3] in ("[x]", "[X]", "[-]")
    done_marker = ms.get("status") in TERMINAL_STATUSES
    return done_cb != done_marker

