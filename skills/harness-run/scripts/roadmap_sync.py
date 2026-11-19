#!/usr/bin/env python3
"""Synchronize harness milestone state with ROADMAP.md.

ROADMAP.md is the active milestone board. docs/BACKLOG.md (new layout; falls back
to root BACKLOG.md for pre-relocation repos) stores compressed completed
milestone history. This script intentionally handles only harness marker blocks:

  <!-- harness:goal id="..." -->
  <!-- harness:milestone id="M1" status="active" priority="P0" -->
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


MILESTONE_RE = re.compile(r"<!--\s*harness:milestone\s+([^>]*)-->")
GOAL_RE = re.compile(r"<!--\s*harness:goal\s+([^>]*)-->")
ATTR_RE = re.compile(r'([A-Za-z_][A-Za-z0-9_-]*)="([^"]*)"')
STATUS_RE = re.compile(r"^(-\s*Status:\s*)\[[ xX]\](.*)$")
COMPLETED_AT_RE = re.compile(r"^- Completed at:\s*")
EVIDENCE_RE = re.compile(r"^- Evidence:\s*")
SUMMARY_RE = re.compile(r"^- Summary:\s*")
DOD_RE = re.compile(r"^- DoD:\s*")


@dataclass
class MarkerBlock:
    milestone_id: str
    attrs: dict[str, str]
    start: int
    end: int
    lines: list[str]


def today() -> str:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date().isoformat()


def read_lines(path: Path) -> list[str]:
    if not path.exists():
        raise SystemExit(f"ROADMAP not found: {path}")
    return path.read_text(encoding="utf-8").splitlines()


def write_lines(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


# 2026-08-06 감사 #15①: 값을 그대로 `key="value"` 로 넣으면 evidence 안의 `"` 가 속성을
# 끊고 `--` 가 HTML 주석을 닫아 마커가 깨진다. 마커가 깨지면 그 milestone 은 파서에서
# 사라지고 — 총괄 뷰(PORTFOLIO)까지 조용히 틀린다. 왕복이 보존되도록 쓰기/읽기 양쪽에 건다.
_ESCAPES = ((("&"), "&amp;"), (('"'), "&quot;"), (("--"), "&#45;&#45;"), ((">"), "&gt;"))


def escape_attr(value: str) -> str:
    for raw, encoded in _ESCAPES:
        value = value.replace(raw, encoded)
    return value


def unescape_attr(value: str) -> str:
    for raw, encoded in reversed(_ESCAPES):
        value = value.replace(encoded, raw)
    return value


def parse_attrs(raw: str) -> dict[str, str]:
    return {m.group(1): unescape_attr(m.group(2)) for m in ATTR_RE.finditer(raw)}


def format_attrs(attrs: dict[str, str]) -> str:
    ordered = []
    for key in ("id", "status", "priority", "evidence"):
        if key in attrs:
            ordered.append((key, attrs[key]))
    ordered.extend((k, v) for k, v in attrs.items() if k not in {k for k, _ in ordered})
    return " ".join(f'{k}="{escape_attr(v)}"' for k, v in ordered)


def marker_line(attrs: dict[str, str]) -> str:
    return f"<!-- harness:milestone {format_attrs(attrs)} -->"


def _block_end(lines: list[str], start: int) -> int:
    """End (exclusive) of a milestone block = first structural boundary after it.

    A block is the marker line + its own ``### title`` (if it follows the marker)
    + the milestone's bullet lines, stopping at the next structural boundary:
    another marker, a ``##``/``### `` heading, or a ``---`` rule. Bounding at the
    boundary (not at the *next marker*) prevents compact from deleting prose
    sections that sit between a completed marker and the following marker.
    """
    i = start + 1
    # absorb the block's own immediate heading (marker-first format)
    if i < len(lines) and lines[i].startswith("### "):
        i += 1
    while i < len(lines):
        line = lines[i]
        if (
            MILESTONE_RE.search(line)
            or line.startswith("## ")
            or line.startswith("### ")
            or line.strip() == "---"
        ):
            break
        i += 1
    return i


def find_blocks(lines: list[str]) -> list[MarkerBlock]:
    blocks: list[MarkerBlock] = []
    for idx, line in enumerate(lines):
        match = MILESTONE_RE.search(line)
        if not match:
            continue
        attrs = parse_attrs(match.group(1))
        milestone_id = attrs.get("id")
        if not milestone_id:
            continue
        end = _block_end(lines, idx)
        blocks.append(
            MarkerBlock(
                milestone_id=milestone_id,
                attrs=attrs,
                start=idx,
                end=end,
                lines=lines[idx:end],
            )
        )
    return blocks


# ── 섹션 배치 (M5 2026-08-20) ────────────────────────────────────────────────
#
# `complete()` 는 블록을 제자리에서만 고쳐서 닫은 milestone 이 진행 섹션에 영구히
# 남았고, 밖으로 빼는 유일한 경로인 `compact()` 는 줄수 게이트에 막혀 있었다. 종결
# 마커를 가진 레포 대부분이 그 게이트 아래라 배치가 영원히 안 고쳐졌다. 줄수 예산
# (compact)과 섹션 배치(여기)를 갈라 놓는다 — 둘은 다른 처분이다.
#
# **이 절이 섹션 배치 어휘의 정본이다.** session-end 의 roadmap_hygiene.py 가 여기서
# import 해 간다(사본 금지 — 위생 게이트가 지적하는 것과 이 도구가 고치는 것이 어긋나면
# 안내문이 거짓이 된다).

# 진행 계열 섹션 제목. 이 안에 드는 섹션 아래의 종결 블록만 옮긴다 — `## 마일스톤`
# 처럼 완료·미완이 섞여 사는 미분류 섹션은 건드리지 않는다(레포마다 관습이 다르다).
IN_PROGRESS_HEADING_RE = re.compile(r"Active|Pending|Next|진행|대기|후보", re.I)

# 종결 status. 정본은 `session-end/bin/roadmap_parse.py` 의
# TERMINAL_STATUSES 이고 여기 리터럴은 그 사본이다 — 이 스크립트는 플릿 전체가
# 공유하므로 외부 레포 절대경로에 하드 의존하지 않는다. 두 집합이 어긋나면
# `promoted/session-end/tests/test_roadmap_hygiene.py` 의 동치 테스트가 잡는다.
TERMINAL_STATUSES = frozenset({"completed", "skipped", "dropped", "archived"})

# 종결 블록을 담는 그릇으로 인정하는 섹션 제목 — **정확 일치만**.
# 넓은 정규식을 쓰면 안 된다: 플릿 33 레포의 `## Archive Pointer` 는 docs/BACKLOG.md 를
# 가리키는 포인터 문단이지 그릇이 아니고, `## Completed Milestone — M60` 처럼 회차가
# 박힌 record 섹션에 새 블록을 떨구는 것도 오배치다.
TERMINAL_SECTION_TITLES = ("Completed", "Completed Milestones", "완료", "완료 이력")
CANONICAL_TERMINAL_SECTION = "Completed"


def section_spans(lines: list[str]) -> list[tuple[str, int, int]]:
    """`## ` 섹션 목록 — (제목, 헤딩 줄 index, 끝 index(exclusive))."""
    heads = [i for i, l in enumerate(lines) if l.startswith("## ")]
    spans = []
    for n, i in enumerate(heads):
        end = heads[n + 1] if n + 1 < len(heads) else len(lines)
        spans.append((lines[i][3:].strip(), i, end))
    return spans


def _section_title_at(spans: list[tuple[str, int, int]], idx: int) -> str:
    for title, start, end in spans:
        if start <= idx < end:
            return title
    return ""


def _trim_trailing_blanks(lines: list[str], start: int, end: int) -> int:
    """[start, end) 끝쪽의 빈 줄을 제외한 삽입 지점."""
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    return end


def _ensure_terminal_section(lines: list[str]) -> tuple[list[str], int]:
    """대상 섹션을 확보하고 (새 lines, 그 섹션 끝의 삽입 지점) 을 돌려준다.

    기존 화이트리스트 섹션이 있으면 재사용하고, 없으면 **마지막 진행 섹션 바로 뒤**에
    `## Completed` 를 만든다. 진행 계열이 여럿인 레포(`Active` + `Next Candidates` 가
    표준형)에서 첫 진행 섹션 뒤에 끼우면 진행 계열이 둘로 쪼개진다.
    """
    spans = section_spans(lines)
    for title, start, end in spans:
        if title in TERMINAL_SECTION_TITLES:
            return lines, _trim_trailing_blanks(lines, start, end), title

    last_ip = None
    for title, start, end in spans:
        if IN_PROGRESS_HEADING_RE.search(title):
            last_ip = (start, end)
    if last_ip is None:  # 호출자가 진행 섹션 아래 블록만 넘기므로 도달하지 않는다
        return lines, len(lines), CANONICAL_TERMINAL_SECTION

    at = _trim_trailing_blanks(lines, *last_ip)
    heading = ["", f"## {CANONICAL_TERMINAL_SECTION}", ""]
    return lines[:at] + heading + lines[at:], at + len(heading), CANONICAL_TERMINAL_SECTION


def _is_setext_underline(lines: list[str], idx: int) -> bool:
    """`---` 가 thematic break 가 아니라 **setext 제목 밑줄**인가.

    바로 위가 빈 줄이 아닌 텍스트면 그 `---` 는 위 줄을 h2 로 만드는 밑줄이다.
    접으면 제목이 사라진다(2026-08-20 코드 리뷰 적발).
    """
    return idx > 0 and bool(lines[idx - 1].strip())


def _collapse_rules_at(lines: list[str], seams: list[int]) -> list[str]:
    """**이동으로 생긴 이음매에서만** 중복 `---` 를 하나로 접는다.

    전 파일을 훑으면 이 이동과 무관한 섹션의 구분자까지 조용히 다시 쓴다 — `complete()`
    가 이 경로를 항상 타므로 플릿의 모든 마감에 적용된다(2026-08-20 코드 리뷰 적발).
    `_selfcheck` 는 `---` 와 빈 줄을 구조적으로 안 보므로 그 변경을 잡아 주지도 못한다.
    """
    drop: set[int] = set()
    for seam in seams:
        after = seam
        while after < len(lines) and not lines[after].strip():
            after += 1
        if after >= len(lines) or lines[after].strip() != "---":
            continue
        if _is_setext_underline(lines, after):
            continue
        before = seam - 1
        while before >= 0 and not lines[before].strip():
            before -= 1
        if before >= 0 and lines[before].strip() == "---" and not _is_setext_underline(lines, before):
            drop.add(after)
    return [l for i, l in enumerate(lines) if i not in drop]


def _selfcheck(before: list[str], after: list[str]) -> str | None:
    """쓰기 직전 자기검사. 문제를 찾으면 사람이 읽을 한 줄, 없으면 None.

    이 스크립트는 출고되면 플릿 전 레포의 상태판을 만진다. 잘못 쓴 파일을 되돌리는
    것보다 안 쓰는 쪽이 싸다.
    """
    import collections

    before_m = sorted(l for l in before if MILESTONE_RE.search(l))
    after_m = sorted(l for l in after if MILESTONE_RE.search(l))
    if before_m != after_m:
        return f"마커 집합이 바뀌었다 (before {len(before_m)} → after {len(after_m)})"

    def bag(ls: list[str]) -> collections.Counter:
        # 빈 줄과 `---` 는 접기 대상이라 제외한다.
        return collections.Counter(l for l in ls if l.strip() and l.strip() != "---")

    lost = bag(before) - bag(after)
    if lost:
        sample = next(iter(lost))
        return f"줄이 사라졌다 ({sum(lost.values())}줄, 예: {sample.strip()[:60]!r})"
    gained = bag(after) - bag(before)
    allowed = {f"## {CANONICAL_TERMINAL_SECTION}"}
    stray = {l for l in gained if l not in allowed}
    if stray:
        sample = next(iter(stray))
        return f"없던 줄이 생겼다 (예: {sample.strip()[:60]!r})"
    return None


def relocate_terminal(
    lines: list[str], only: set[str] | None = None
) -> tuple[list[str], list[str]]:
    """진행 섹션 아래의 종결 블록을 대상 섹션 **끝**으로 옮긴다.

    섹션 끝에 파일 등장 순서를 유지해 append 하는 것이 계약이다 — 그래야 두 번째
    실행이 no-op 이 되고, `compact()` 가 파일 앞에서부터 걷어내는 기존 의미(오래된
    것부터 아카이브)가 유지된다.

    마커를 지우지 않고 BACKLOG 에 쓰지 않는다. 그건 `compact()` 가 하는 **다른
    처분**이고, "ROADMAP 에 남은 종결 마커 = 아직 아카이브되지 않은 것" 이라는 규약이
    거기 걸려 있다.

    반환: (새 lines, 옮긴 milestone id 목록, 대상 섹션 제목, 건너뛴 [id, 사유] 목록)
    """
    spans = section_spans(lines)
    candidates = [
        b
        for b in find_blocks(lines)
        if b.attrs.get("status") in TERMINAL_STATUSES
        and (only is None or b.milestone_id in only)
        and IN_PROGRESS_HEADING_RE.search(_section_title_at(spans, b.start))
    ]

    # 하위 `###` 절을 달고 있는 블록은 **옮기지 않는다** (2026-08-20 코드 리뷰 적발).
    # `_block_end` 는 다음 `###` 에서 멈추는데, 그 경계는 원래 `compact`(삭제)가 사이의
    # 산문을 안 지우려고 만든 것이다. 삭제에는 맞지만 **이동에는 안 맞는다** — 마커와
    # 첫 제목만 Completed 로 가고 하위 절은 진행 섹션에 남아 고아가 된다. 줄이 사라진
    # 것은 아니라서 `_selfcheck` 도 못 잡고, 위생 게이트는 마커가 옮겨졌으니 PASS 를
    # 준다. 즉 조용히 쪼개진다. 경계를 넓히면 이번엔 milestone 것이 아닌 산문까지
    # 삼킬 수 있으므로(2026-06-20 데이터 소실과 같은 모양), 확실히 못 옮기는 것은
    # 옮기지 않고 사유를 말한다.
    movers, skipped = [], []
    for block in candidates:
        tail = lines[block.end] if block.end < len(lines) else ""
        if tail.startswith("### "):
            skipped.append((block.milestone_id, "하위 `###` 절이 딸려 있어 경계를 확정할 수 없다"))
            continue
        movers.append(block)

    if not movers:
        return list(lines), [], CANONICAL_TERMINAL_SECTION, skipped

    chunks = []
    for block in movers:
        chunk = list(block.lines)
        while chunk and not chunk[-1].strip():
            chunk.pop()
        chunks.append(chunk)

    # 이음매를 **센티넬**로 표시해 둔다. 삽입(섹션 생성·payload)이 인덱스를 밀기
    # 때문에 산술로 따라가면 조용히 어긋난다. 조립이 끝난 뒤 위치를 찾아 걷어낸다.
    seam = "\x00SEAM\x00"
    remaining: list[str] = []
    cursor = 0
    for block in movers:
        remaining.extend(lines[cursor : block.start])
        remaining.append(seam)
        cursor = block.end
    remaining.extend(lines[cursor:])

    remaining, insert_at, section_title = _ensure_terminal_section(remaining)

    # 블록 사이에 빈 줄을 넣는다. 안 넣으면 `- Status: [x]` 다음 줄이 곧바로 다음 마커라
    # Completed 섹션에서 블록 경계가 보이지 않는다(2026-08-20 코드 리뷰 적발 — toolshelf 실측).
    payload: list[str] = []
    for chunk in chunks:
        if payload:
            payload.append("")
        payload.extend(chunk)

    merged = remaining[:insert_at] + payload + remaining[insert_at:]
    # 센티넬을 걷어낸 뒤의 좌표로 옮겨 적는다 — 접기는 실제 본문 위에서 판정해야 한다.
    seams: list[int] = []
    out: list[str] = []
    for line in merged:
        if line == seam:
            seams.append(len(out))
            continue
        out.append(line)
    return _collapse_rules_at(out, seams), [b.milestone_id for b in movers], section_title, skipped


def relocate(args: argparse.Namespace) -> int:
    path = Path(args.roadmap)
    lines = read_lines(path)
    moved_lines, moved, section, skipped = relocate_terminal(lines)
    for mid, why in skipped:
        print(f"건너뜀: {mid} — {why}", file=sys.stderr)
    if not moved:
        print("배치 이동 0건 — 진행 섹션에 남은 종결 블록이 없다")
        return 0
    problem = _selfcheck(lines, moved_lines)
    if problem:
        print(f"거부: 자기검사 실패라 쓰지 않았다 — {problem}", file=sys.stderr)
        return 1
    if args.dry_run:
        print(f"[dry-run] 이동 대상 {len(moved)}건: {', '.join(moved)} → ## {section}")
        return 0
    write_lines(path, moved_lines)
    print(f"배치 이동 {len(moved)}건: {', '.join(moved)} → ## {section}")
    return 0


def find_goal(lines: list[str]) -> str:
    for idx, line in enumerate(lines):
        if GOAL_RE.search(line):
            text = []
            for rest in lines[idx + 1 :]:
                if rest.startswith("## ") or MILESTONE_RE.search(rest):
                    break
                if rest.strip():
                    text.append(rest.strip())
            return " ".join(text) if text else "(goal marker present, body empty)"
    for line in lines:
        stripped = line.strip().lstrip(">").strip()
        if stripped.startswith("북극성:"):
            return stripped
    return "(no harness goal marker found)"


def replace_or_append(block: list[str], pattern: re.Pattern[str], replacement: str) -> list[str]:
    out = []
    replaced = False
    for line in block:
        if pattern.search(line):
            if not replaced:
                out.append(replacement)
                replaced = True
            continue
        out.append(line)
    if not replaced:
        insert_at = len(out)
        for idx, line in enumerate(out):
            if idx > 0 and line.startswith("## "):
                insert_at = idx
                break
        out.insert(insert_at, replacement)
    return out


def complete(args: argparse.Namespace) -> int:
    path = Path(args.roadmap)
    lines = read_lines(path)
    blocks = find_blocks(lines)
    # ⚠ **중복 ID 면 닫지 않는다** (2026-09-03 리뷰). 종전엔 첫 매치를 닫아서 「어느 블록을
    # 닫을지 운」이었다 — 오늘 실제로 M28 이 둘인 상태로 이 명령이 돌았고 맞은 것을 닫은 게
    # 우연이었다. 탐지를 lint(관찰자)에만 두면 사고 경로가 그대로 열려 있다.
    same_id = [b for b in blocks if b.milestone_id == args.milestone]
    if len(same_id) > 1:
        print(f"duplicate milestone id: `{args.milestone}` — {len(same_id)}개 블록이 같은 번호다. "
              "어느 것을 닫을지 정해지지 않으므로 거부한다. 살아있는 쪽 번호를 옮긴 뒤 다시 실행한다 "
              "(워크트리 규약 §2.5 ① 번호 선점). 진단: `roadmap_sync.py lint`", file=sys.stderr)
        return 1
    block = same_id[0] if same_id else None
    if block is None:
        print(f"milestone not found: {args.milestone}", file=sys.stderr)
        return 1

    # 2026-08-06 감사 #15②: 직전 status 를 보지 않고 completed 로 덮어써서 blocked·pending
    # milestone 도 무조건 완료가 됐다. 막힌 것을 닫는 건 사람의 판단이므로 --force 를 요구한다.
    prior = block.attrs.get("status", "pending")
    if prior not in {"active", "completed"} and not getattr(args, "force", False):
        print(
            f"거부: {args.milestone} 의 현재 status 는 '{prior}' 다 — 완료로 덮지 않는다.\n"
            f"  막힌·보류 중인 milestone 을 닫는 것은 사람의 판단이다. 의도한 것이면 --force 를 준다.\n"
            f"  마커 status 허용 값: active(진행 중·계획 승인 시점) · pending · blocked · completed · skipped · dropped · archived "
            f"(in_progress 는 값이 아니다 — active 로 고친다).",
            file=sys.stderr,
        )
        return 1

    new_attrs = dict(block.attrs)
    new_attrs["status"] = "completed"
    if args.evidence:
        new_attrs["evidence"] = args.evidence

    new_block = list(block.lines)
    new_block[0] = marker_line(new_attrs)
    new_block = replace_or_append(new_block, STATUS_RE, r"- Status: [x]")
    new_block = replace_or_append(new_block, COMPLETED_AT_RE, f"- Completed at: {today()}")
    if args.evidence:
        new_block = replace_or_append(new_block, EVIDENCE_RE, f"- Evidence: {args.evidence}")
    if args.summary:
        new_block = replace_or_append(new_block, SUMMARY_RE, f"- Summary: {args.summary}")

    lines = lines[: block.start] + new_block + lines[block.end :]

    # M5 2026-08-20: 마커를 닫는 순간이 옮길 자연스러운 시점이다. 별도 명령으로만 두면
    # 아무도 안 불러서(그게 원래 결함이었다) 진행 섹션에 그대로 남는다. 방금 닫은 것
    # 하나만 옮긴다 — 같은 파일의 다른 종결 블록 소급은 `relocate` 서브커맨드 몫이다.
    before = lines
    lines, moved, section, skipped = relocate_terminal(lines, only={args.milestone})
    for mid, why in skipped:
        print(f"  배치 이동 건너뜀: {mid} — {why}", file=sys.stderr)
    if moved:
        problem = _selfcheck(before, lines)
        if problem:
            print(
                f"거부: 배치 이동 자기검사 실패라 쓰지 않았다 — {problem}\n"
                f"  `- Status: [x]` 갱신도 함께 보류됐다. ROADMAP 모양을 확인하고 다시 돌린다.",
                file=sys.stderr,
            )
            return 1

    write_lines(path, lines)
    print(f"completed {args.milestone}")
    if moved:
        print(f"  배치 이동: {', '.join(moved)} → ## {section}")
    return 0


DROPPED_BY_RE = re.compile(r"^- Dropped by:\s*")


def drop(args: argparse.Namespace) -> int:
    """milestone 을 폐기(dropped)로 닫고 종결 섹션으로 옮긴다. completed 는 거부, dropped 는 멱등."""
    path = Path(args.roadmap)
    lines = read_lines(path)
    blocks = find_blocks(lines)
    same_id = [b for b in blocks if b.milestone_id == args.milestone]
    if len(same_id) > 1:
        print(f"duplicate milestone id: `{args.milestone}` — {len(same_id)}개 블록이 같은 번호다. "
              "어느 것을 폐기할지 정해지지 않으므로 거부한다. 진단: `roadmap_sync.py lint`",
              file=sys.stderr)
        return 1
    if not same_id:
        print(f"milestone not found: {args.milestone}", file=sys.stderr)
        return 1
    block = same_id[0]

    prior = block.attrs.get("status", "pending")
    if prior == "completed":
        print(f"거부: {args.milestone} 는 이미 completed 다 — 완료된 것을 폐기로 덮지 않는다.",
              file=sys.stderr)
        return 1
    if prior == "dropped":
        print(f"already dropped: {args.milestone} (변화 없음)")
        return 0

    new_attrs = dict(block.attrs)
    new_attrs["status"] = "dropped"
    new_attrs["evidence"] = args.evidence

    new_block = list(block.lines)
    new_block[0] = marker_line(new_attrs)
    new_block = replace_or_append(new_block, STATUS_RE, "- Status: [x] DROP")
    new_block = replace_or_append(new_block, DROPPED_BY_RE, f"- Dropped by: {args.reason}")
    new_block = replace_or_append(new_block, EVIDENCE_RE, f"- Evidence: {args.evidence}")

    lines = lines[: block.start] + new_block + lines[block.end :]

    before = lines
    lines, moved, section, skipped = relocate_terminal(lines, only={args.milestone})
    for mid, why in skipped:
        print(f"  배치 이동 건너뜀: {mid} — {why}", file=sys.stderr)
    if moved:
        problem = _selfcheck(before, lines)
        if problem:
            print(f"거부: 배치 이동 자기검사 실패라 쓰지 않았다 — {problem}", file=sys.stderr)
            return 1

    write_lines(path, lines)
    print(f"dropped {args.milestone}")
    if moved:
        print(f"  배치 이동: {', '.join(moved)} → ## {section}")
    return 0


# `changesets/` 접두어 유무 모두 카운트 — Evidence 가 "changesets/A/ + B/" 처럼
# 뒤 항목의 접두어를 생략하면 1개로 오탐하던 결함 수정 (2026-07-07, F-FRONT 실사례)
CHANGESET_REF_RE = re.compile(r"\b(\d{8}-[A-Za-z0-9][A-Za-z0-9-]*)")

# 2026-07-20 CS5 실사례: "changesets/20260717-cs5-layout-contract + cs5-root-plans + ..."
# 처럼 뒤 항목이 *날짜* 접두어까지 생략하면 위 정규식이 첫 항목만 잡아 5개를 1개로 세고
# inflation-candidate 오탐을 냈다(size-retro 10건 중 1건). `+` 로 이어붙인 bare slug 를
# 같은 줄의 직전 날짜 접두어로 복원해 함께 센다. 경로(`/` 포함)·파일명(`.` 포함)은 제외.
BARE_SLUG_RE = re.compile(r"^\s*\+\s*([a-z0-9][a-z0-9-]*-[a-z0-9-]+)")



def collect_changeset_tokens(block_lines: list[str]) -> set[str]:
    refs: set[str] = set()
    for line in block_lines:
        refs.update(CHANGESET_REF_RE.findall(line))
        prefix: str | None = None
        for segment in re.split(r"(?=\+)", line):
            full = CHANGESET_REF_RE.search(segment)
            if full:
                prefix = full.group(1)[:8]
                continue
            bare = BARE_SLUG_RE.match(segment)
            if prefix and bare:
                refs.add(f"{prefix}-{bare.group(1)}")
    return refs


def count_changeset_refs(block_lines: list[str]) -> int:
    return len(collect_changeset_tokens(block_lines))


# MM6 step-1 (2026-07-21): 토큰 모양(`YYYYMMDD-slug`)만 보고 세면 changeset 이 아닌
# 산출물까지 changeset 으로 센다 — HQ1 실사례에서 Evidence 가
# `evidence/harness/20260721-hq1-e2e.md` 하나였는데 카운터가 changeset 1개로 읽어
# INFLATION 후보 오탐을 냈다. 실재하는 `changesets/<slug>/` 만 센다.
def classify_changeset_refs(
    block_lines: list[str], root: Path | None
) -> tuple[set[str], set[str]]:
    """(실재 확인된 changeset, 확인 불가 토큰) 으로 가른다.

    `changesets/` 디렉터리가 없는 레포는 검증 근거 자체가 없으므로 전부
    "확인 불가"가 아니라 종전처럼 텍스트 카운트로 취급한다(빈 unresolved).
    """
    tokens = collect_changeset_tokens(block_lines)
    if root is None:
        return tokens, set()
    base = root / "changesets"
    if not base.is_dir():
        return tokens, set()
    verified = {t for t in tokens if (base / t).is_dir()}
    return verified, tokens - verified


# plan doc 포인터 — `- Plan: \`plans/...\`` 및 본문 인용 둘 다. archive 이동분 포함.
#
# 2026-07-20 (cs#245): 앞부분을 `(?:archive/)?` 로 좁게 잡으면 `docs/archive/plans/x.md`
# 같은 *틀린* 경로에서 `\b` 가 `archive/` 앞에 걸려 뒤쪽만 잘라 매칭하고, 그 잘린
# 경로는 실재하므로 검사를 통과한다(cs#244 봉합이 이 구멍으로 새어 나갔다). 접두어를
# 전부 삼킨 뒤 실재를 검사해야 "틀린 주소"가 걸린다.
PLAN_POINTER_RE = re.compile(r"(?<![\w/.-])((?:[\w.-]+/)*plans/(?:horizons/)?[\w.-]+\.md)")

# 검사 대상 — 살아있는 재개 경로만. `archive/` 는 record 동결이라 제외한다.
POINTER_SCAN_GLOBS = ("docs/BACKLOG.md", "BACKLOG.md", "plans/*.md", "plans/horizons/*.md")


def pointer_scan_files(roadmap: Path) -> list[Path]:
    """포인터 검사 대상 파일 목록 (2026-07-20 cs#245).

    ROADMAP 하나만 보던 검사 범위를 살아있는 계획 문서 전체로 넓힌다. cs#244 가
    ROADMAP 만 lint 하고 `docs/BACKLOG.md`·horizon doc 은 수기로 봉합했는데, 그
    수기분이 틀린 접두어(`docs/archive/plans/`)로 들어가 아무도 못 잡았다.
    """
    root = roadmap.resolve().parent
    files = [roadmap.resolve()]
    for pattern in POINTER_SCAN_GLOBS:
        for path in sorted(root.glob(pattern)):
            if path.is_file() and path.resolve() not in files:
                files.append(path.resolve())
    return files


# M8 F3 (2026-08-21): 언급/사용 표면 분리. 사용 표면은 백틱이 아니라 **필드**로
# 정의한다 — 정본 표기 자체가 백틱 포함이라(위 PLAN_POINTER_RE 주석의 `- Plan:` 예시)
# 백틱은 이 코퍼스에서 판별자가 아니다(플릿 실측: 백틱 111 중 다수가 진짜 백링크).
_POINTER_FENCE_RE = re.compile(r"^```.*?^```", re.M | re.S)
_POINTER_APPEND_RE = re.compile(r"^##[ \t]+(?:진행 로그|finding 큐)\b.*$", re.M)
_POINTER_FIELD_RE = re.compile(
    r"^\s*(?:>\s*)?-?\s*\*{0,2}(?:Plan|Evidence|milestone plan)\*{0,2}\s*:", re.I
)


def _pointer_exempt_spans(text: str) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """→ (펜스 스팬, append-only 절 스팬). 둘을 가르는 이유: 펜스는 필드 리드인보다
    우선하는 면제(펜스 안 `- Plan:` 예시는 인용)지만, append-only 절 안의 필드는
    여전히 사용 표면이다(M8 리뷰 수리 — 순서를 뭉개면 펜스 예시가 오탐된다)."""
    fence = [m.span() for m in _POINTER_FENCE_RE.finditer(text)]
    append: list[tuple[int, int]] = []
    for m in _POINTER_APPEND_RE.finditer(text):
        tail = text[m.end():]
        h2 = re.search(r"^##\s", tail, re.M)
        append.append((m.start(), m.end() + (h2.start() if h2 else len(tail))))
    return fence, append


def _cross_repo_resolves(pointer: str, projects_root: Path | None = None) -> bool:
    root = projects_root if projects_root is not None else Path.home() / "projects"
    if (root / pointer).is_file():
        return True
    return pointer.startswith("projects/") and (root.parent / pointer).is_file()


def _dangling_matches(
    roadmap: Path, lines: list[str], projects_root: Path | None = None
):
    """(path, text, match) — 끊긴 포인터의 **원소별 위치**. 탐지 규칙 단일 구현.

    `lint`(보고)와 `repair-plan-pointers`(치환)가 같은 함수를 쓴다. 사본을 두면
    "고쳤는데 lint 가 계속 FAIL" 또는 그 반대가 조용히 생긴다.
    """
    root = roadmap.resolve().parent
    for path in pointer_scan_files(roadmap):
        text = "\n".join(lines) if path == roadmap.resolve() else path.read_text(encoding="utf-8")
        fence_spans, append_spans = _pointer_exempt_spans(text)
        for match in PLAN_POINTER_RE.finditer(text):
            pointer = match.group(1)
            if (root / pointer).is_file():
                continue
            start, end = match.span(1)
            if any(a <= start and end <= b for a, b in fence_spans):
                continue  # 펜스 안 = 인용 (필드 리드인 예시 포함 — 펜스가 우선)
            line_start = text.rfind("\n", 0, start) + 1
            line_end = text.find("\n", start)
            line = text[line_start: line_end if line_end != -1 else len(text)]
            if _POINTER_FIELD_RE.match(line):
                pass  # 사용 표면 — append-only 절 안에서도 필드가 우선
            elif any(a <= start and end <= b for a, b in append_spans):
                continue  # append-only 절의 산문 = 사후 기록
            elif _cross_repo_resolves(pointer, projects_root):
                continue  # 다른 레포로 실재 해석 = 언급
            yield path, text, match


def dangling_plan_pointers(
    roadmap: Path, lines: list[str], projects_root: Path | None = None
) -> list[str]:
    """살아있는 계획 문서의 plan doc 백링크가 실재하는지 검사한다 (2026-07-20 · M8 재정의).

    plan doc 의 존재 이유는 "새 에이전트가 읽고 몇 시간 이어받는다"인데, 재개
    경로는 `- Plan:`·`- Evidence:`·`> milestone plan:` 필드 값을 따라간다. 이
    **사용 표면은 면제가 없다**(백틱 무관 — 정본 표기가 백틱 포함이다). 그 밖의
    산문은 좁게 면제한다: 코드 펜스·append-only 절(`## 진행 로그`·`## finding 큐`)
    안의 경로, 그리고 다른 레포로 실재 해석되는 cross-repo 인용(M8 D2). 로컬로도
    cross-repo 로도 해석 안 되는 산문 경로는 그냥 끊긴 포인터라 그대로 잡는다.
    """
    root = roadmap.resolve().parent
    missing: list[str] = []
    seen: set[str] = set()
    for path, _text, match in _dangling_matches(roadmap, lines, projects_root):
        pointer = match.group(1)
        if pointer in seen:
            continue
        seen.add(pointer)
        label = path.relative_to(root).as_posix() if path != roadmap.resolve() else roadmap.name
        missing.append(f"{label}: {pointer}")
    return missing


def _label_for(roadmap: Path, path: Path) -> str:
    root = roadmap.resolve().parent
    return path.relative_to(root).as_posix() if path != roadmap.resolve() else roadmap.name


def archive_candidate(root: Path, pointer: str) -> str | None:
    """끊긴 포인터의 아카이브 사본 (M8 D3 우선순위 — 첫 히트만 채택).

    `archive/<pointer>` → `archive/plans/<basename>` 순. 어느 쪽도 없으면 None 이고,
    그때는 **경로를 지어내지 않는다** — 소멸 포인터에 추정 주소를 쓰는 것은 기록 위조다.
    """
    for candidate in (f"archive/{pointer}", f"archive/plans/{Path(pointer).name}"):
        if (root / candidate).is_file():
            return candidate
    return None


def repair_plan_pointers(args: argparse.Namespace) -> int:
    """끊긴 plan 백링크를 아카이브 사본으로 갱신한다 (2026-09-02).

    **왜 있나 — 규칙 두 개가 부딪치고 있었다.** milestone 을 닫으면 계획서가
    `archive/plans/` 로 이동하는데, `harness-done` 산문은 "옛 백링크는 정정하지
    않는다"(record 동결)고 적고 `lint` 는 ROADMAP 마커의 `- Plan:` 을 **사용
    표면**(살아있는 재개 경로)으로 보고 실재를 요구한다(M8 D2). 그래서 **milestone 을
    닫을 때마다 lint 가 FAIL** 했고, 그 발견이 고쳐지지 않은 채 HANDOFF 로 이월되며
    세션마다 같은 노이즈가 반복됐다(2026-09-02 M9 실측 — M8 step-4 가 플릿 178건을
    청소한 지 12일 만에 같은 자리가 재오염됐다). record 동결의 대상은 archive 안의
    옛 문서 본문이지 살아있는 ROADMAP 마커가 아니다.

    탐지는 `_dangling_matches` 를 그대로 쓴다 — lint 와 **다른 판정을 할 수 없는**
    구조다. 치환은 매치 스팬 단위로만 하고(펜스·append-only 산문의 같은 문자열은
    애초에 탐지에 안 걸리므로 손대지 않는다) 뒤에서부터 적용해 오프셋을 보존한다.
    """
    roadmap = Path(args.roadmap)
    lines = read_lines(roadmap)
    root = roadmap.resolve().parent
    per_file: dict[Path, list[tuple[int, int, str, str]]] = {}
    texts: dict[Path, str] = {}
    fixed: list[str] = []
    unresolved: list[str] = []
    for path, text, match in _dangling_matches(roadmap, lines):
        pointer = match.group(1)
        candidate = archive_candidate(root, pointer)
        label = _label_for(roadmap, path)
        if candidate is None:
            unresolved.append(f"{label}: {pointer}")
            continue
        texts.setdefault(path, text)
        start, end = match.span(1)
        per_file.setdefault(path, []).append((start, end, pointer, candidate))
        fixed.append(f"{label}: {pointer} -> {candidate}")

    if not args.dry_run:
        for path, spans in per_file.items():
            text = texts[path]
            for start, end, _pointer, candidate in sorted(spans, reverse=True):
                text = text[:start] + candidate + text[end:]
            path.write_text(text.rstrip() + "\n", encoding="utf-8")

    prefix = "[dry-run] " if args.dry_run else ""
    if fixed:
        print(f"{prefix}plan 포인터 갱신 {len(fixed)}건")
        for item in fixed:
            print(f"- {item}")
    if unresolved:
        print(f"판정 불가 {len(unresolved)}건 — 아카이브 사본이 없다(경로를 지어내지 않는다)")
        for item in unresolved:
            print(f"- {item}")
    if not fixed and not unresolved:
        print("plan 포인터 갱신: 대상 없음 (전부 실재)")
    return 1 if unresolved else 0


def duplicate_milestone_ids(lines: list[str]) -> list[tuple[str, str]]:
    """같은 ROADMAP 안에 중복된 milestone id 와 그 줄 번호.

    2026-09-03 신설 — 두 세션이 같은 날 독립으로 M28 을 등록했고, `lint` 는 PASS 를 줬다.
    `complete --milestone M28` 이 맞는 블록을 닫은 것은 운이었고, 그 사이 Codex 세션의
    plan-position 훅은 남의 블록을 읽어 엉뚱한 step 을 「다음 할 일」로 띄우고 있었다.
    status 와 무관하게 본다 — 완료된 것과 진행 중인 것이 같은 번호여도 위 두 사고가 그대로 난다.
    """
    # ⚠ 탐지원을 `find_blocks` 로 맞춘다 (2026-09-03 리뷰) — `complete` 가 실제로 다루는
    # 집합과 같아야 「lint 는 경고하는데 complete 는 다른 걸 본다」가 생기지 않는다.
    # (둘 다 코드펜스 안의 예시 마커를 구분하지 않는다는 한계는 공유한다 — 갈라지는 것보다 낫다.)
    seen: dict[str, list[int]] = {}
    for b in find_blocks(lines):
        seen.setdefault(b.milestone_id, []).append(b.start + 1)
    return [
        (mid, "줄 " + ", ".join(str(n) for n in rows))
        for mid, rows in sorted(seen.items())
        if len(rows) > 1
    ]


def warn_duplicates(lines: list[str]) -> None:
    """읽기 전용 명령에서는 거부하지 않고 경고만 낸다."""
    for mid, where in duplicate_milestone_ids(lines):
        print(f"⚠ duplicate milestone id: `{mid}` — {where} "
              "(complete 는 거부된다. `lint` 로 진단)", file=sys.stderr)


def lint(args: argparse.Namespace) -> int:
    """살아있는 계획 문서의 plan doc 포인터가 실재하는지. exit 1 = 위반.

    구 Scale 선언 검사(`changesets>=N`)는 2026-07-23 재조립 P3 에서 제거했다 —
    milestone 크기를 changeset 수로 재던 규약이 horizon 층과 함께 폐지됐다.
    cs#245: 검사 범위를 ROADMAP → 살아있는 계획 문서 전체(BACKLOG·plans/·horizons)로 확대.
    """
    roadmap = Path(args.roadmap)
    lines = read_lines(roadmap)
    errors: list[str] = []
    for milestone_id, where in duplicate_milestone_ids(lines):
        errors.append(
            f"duplicate milestone id: `{milestone_id}` — {where}. 한 ROADMAP 에 같은 번호가 둘이면 "
            "`complete --milestone <ID>` 가 어느 블록을 닫을지 정해지지 않고, plan-position 훅이 "
            "남의 블록을 읽는다(2026-09-03 실측: Codex 세션이 다른 milestone 의 step 을 자기 다음 "
            "할 일로 표시했다). 살아있는 쪽 번호를 옮긴다 — 완료·동결된 기록이 아니라 active 쪽을 "
            "고치는 방향이 규약(워크트리 규약 §2.5 ① 번호 선점)이다"
        )
    for pointer in dangling_plan_pointers(roadmap, lines):
        errors.append(
            f"dangling plan pointer: `{pointer}` — 파일이 없다. 아카이브로 옮겼으면 "
            "`archive/plans/…` 로 백링크를 갱신한다 — 기계 갱신은 "
            "`roadmap_sync.py repair-plan-pointers` (재개 경로가 끊긴다. "
            "필드 값과 산문의 로컬 경로는 실재해야 하고, 언급은 코드 펜스·"
            "진행 로그/finding 큐 절·실재하는 다른 레포 경로로만 통과한다)"
        )
    if errors:
        print("roadmap lint: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("roadmap lint: PASS (plan 포인터 실재 · milestone ID 중복 없음)")
    return 0


# (제거 2026-07-23, 재조립 P3) size_retro_line — milestone 크기를 changeset 수로
# 재던 인플레 적발기. 크기 규약(Scale 선언·하한 게이트·verdict 장부)이 horizon 층과
# 함께 폐지됐다. 크기 판정은 계획서의 step 수와 리프 판정으로 되돌아간다.
def status(args: argparse.Namespace) -> int:
    lines = read_lines(Path(args.roadmap))
    warn_duplicates(lines)
    counts: dict[str, int] = {}
    for block in find_blocks(lines):
        state = block.attrs.get("status", "pending")
        counts[state] = counts.get(state, 0) + 1
    print("milestones:")
    for state in sorted(counts):
        print(f"  {state}: {counts[state]}")
    if not counts:
        print("  none: 0")
    return 0


def active_blocks(blocks: list[MarkerBlock]) -> list[MarkerBlock]:
    return [b for b in blocks if b.attrs.get("status") == "active"]


def gap_report_text(lines: list[str], blocks: list[MarkerBlock]) -> str:
    done = [b for b in blocks if b.attrs.get("status") == "completed"]
    goal = find_goal(lines)
    date = today()
    summaries = []
    for block in done:
        title = next((line.strip("# ").strip() for line in block.lines if line.startswith("### ")), block.milestone_id)
        evidence = block.attrs.get("evidence", "-")
        summaries.append(f"- {block.milestone_id}: {title} (evidence: {evidence})")
    if not summaries:
        summaries.append("- No completed harness milestones found.")
    return f"""# Roadmap Gap Review

Date: {date}

## North Star
{goal}

## Current State
{chr(10).join(summaries)}

## Gap
- Active harness milestones are exhausted.
- Compare the north star above with current evidence before starting new implementation.
- Do not infer completion without a new DoD and evidence path.

## Proposed Next Milestones
- N1 - define the next measurable gap.
- N2 - create one evidence-producing milestone.
- N3 - add the smallest validation or smoke gate.

## Recommendation
Promote one proposed item to ROADMAP.md only after the user approves the next milestone.
"""


# 2026-07-24 재조립 P6 후속: horizon-check → gap-check 개명 (horizon 층 폐지 — 하는 일은
# 원래부터 "active milestone 0 이면 gap 요약"이었다). 기계 호출처 0 실측 — alias 없음.
def gap_check(args: argparse.Namespace) -> int:
    path = Path(args.roadmap)
    lines = read_lines(path)
    blocks = find_blocks(lines)
    active = active_blocks(blocks)
    if active:
        print(f"active milestones: {len(active)}")
        for block in active:
            print(f"  {block.milestone_id}: {block.attrs.get('status', 'pending')}")
        return 0

    print("active milestones: 0")
    report = gap_report_text(lines, blocks)
    if args.gap_out:
        # UD3 step-3: file output is opt-in only (--gap-out explicit). Default
        # behavior prints the same gap summary to stdout without creating a
        # file — measured re-reference on prior roadmap-gap-*.md files was 0
        # (evidence/harness/interruption-diagnosis-2026-07-14.md ②-2).
        out = Path(args.gap_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        print(f"gap report: {out}")
    else:
        print(report)
    return 2


def archive_entry(block: MarkerBlock, date: str) -> str:
    title = next((line.strip("# ").strip() for line in block.lines if line.startswith("### ")), block.milestone_id)

    def _body(rx: re.Pattern[str]) -> str:
        # Evidence/DoD live as BODY lines (- Evidence: ...), not marker attrs.
        for line in block.lines:
            if rx.search(line):
                return line.split(":", 1)[1].strip()
        return ""

    # Result: prefer an explicit Summary line, else fall back to DoD so the
    # milestone body is not lost on archive (F1, dogfooding 2026-06-24).
    summary = _body(SUMMARY_RE) or _body(DOD_RE) or "-"
    # Evidence: read the body line first, then the marker attr, then "-".
    evidence = _body(EVIDENCE_RE) or block.attrs.get("evidence", "") or "-"
    return (
        f"- {block.milestone_id} - {title}\n"
        f"  - Completed: {date}\n"
        f"  - Result: {summary}\n"
        f"  - Evidence: {evidence}\n"
    )


def append_backlog(backlog: Path, entries: list[str]) -> None:
    if not entries:
        return
    if backlog.exists():
        text = backlog.read_text(encoding="utf-8")
    else:
        text = "# BACKLOG\n\n> Compressed milestone archive. ROADMAP.md is capped at 150 lines.\n\n## Completed\n"
    month = today()[:7]
    section = f"\n### {month}\n" + "\n".join(entries).rstrip() + "\n"
    backlog.write_text(text.rstrip() + "\n" + section, encoding="utf-8")


def resolve_backlog_path(explicit: str | None) -> Path:
    """UD3 step-1: BACKLOG.md relocated to docs/ (new repos). If the caller did
    not pass --backlog explicitly, prefer an existing docs/BACKLOG.md, then an
    existing root BACKLOG.md (pre-relocation repos), else default to the new
    docs/BACKLOG.md path."""
    if explicit is not None:
        return Path(explicit)
    docs_backlog = Path("docs/BACKLOG.md")
    root_backlog = Path("BACKLOG.md")
    if docs_backlog.exists():
        return docs_backlog
    if root_backlog.exists():
        return root_backlog
    return docs_backlog


def compact(args: argparse.Namespace) -> int:
    roadmap = Path(args.roadmap)
    backlog = resolve_backlog_path(args.backlog)
    lines = read_lines(roadmap)
    if len(lines) <= args.max_lines:
        print(f"ROADMAP lines: {len(lines)} <= {args.max_lines}; no compact needed")
        return 0

    blocks = find_blocks(lines)
    completed = [b for b in blocks if b.attrs.get("status") == "completed"]
    if not completed:
        print(f"ROADMAP lines: {len(lines)} > {args.max_lines}; no completed milestones to archive", file=sys.stderr)
        return 1

    archived_entries: list[str] = []
    remove_ranges: list[tuple[int, int]] = []
    current_len = len(lines)
    for block in completed:
        if current_len <= args.max_lines:
            break
        archived_entries.append(archive_entry(block, today()))
        remove_ranges.append((block.start, block.end))
        current_len -= block.end - block.start

    if not remove_ranges:
        return 0

    new_lines: list[str] = []
    cursor = 0
    for start, end in remove_ranges:
        new_lines.extend(lines[cursor:start])
        cursor = end
    new_lines.extend(lines[cursor:])
    # 2026-08-06 감사 #15③: 구 순서는 ROADMAP 을 먼저 쓰고 백로그를 나중에 붙였다 —
    # 그 사이 크래시면 milestone 이 **양쪽 어디에도 없다**(이력 소실). 순서를 뒤집으면
    # 같은 크래시가 중복(양쪽에 존재)으로 끝난다. 중복은 복구 가능하고 소실은 아니다.
    append_backlog(backlog, archived_entries)
    write_lines(roadmap, new_lines)
    print(f"archived {len(archived_entries)} milestone(s) to {backlog}")
    print(f"ROADMAP lines: {len(new_lines)}")
    if len(new_lines) > args.max_lines:
        print(
            f"ROADMAP still exceeds max-lines ({len(new_lines)} > {args.max_lines}); "
            "no more completed milestones can be archived safely",
            file=sys.stderr,
        )
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roadmap", default="ROADMAP.md")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status")

    sub.add_parser("lint")

    p_complete = sub.add_parser("complete")
    p_complete.add_argument("--milestone", required=True)
    p_complete.add_argument("--evidence", default="")
    p_complete.add_argument("--summary", default="")
    p_complete.add_argument("--force", action="store_true",
                            help="active/completed 가 아닌 status(blocked·pending 등)도 완료로 덮는다")

    p_drop = sub.add_parser("drop", help="milestone 을 폐기(dropped)로 닫고 종결 섹션으로 옮긴다")
    p_drop.add_argument("--milestone", required=True)
    p_drop.add_argument("--evidence", required=True)
    p_drop.add_argument("--reason", required=True)

    p_relocate = sub.add_parser(
        "relocate",
        help="진행 섹션에 남은 종결 블록을 Completed 섹션으로 옮긴다 (마커·BACKLOG 는 안 건드린다)",
    )
    p_relocate.add_argument("--dry-run", action="store_true",
                            help="옮길 대상만 출력하고 파일은 쓰지 않는다")

    p_repair = sub.add_parser(
        "repair-plan-pointers",
        help="끊긴 plan 백링크를 archive/ 사본으로 갱신한다 (milestone 마감 직후 — lint FAIL 예방)",
    )
    p_repair.add_argument("--dry-run", action="store_true",
                          help="갱신 대상만 출력하고 파일은 쓰지 않는다")

    p_gap = sub.add_parser("gap-check")
    p_gap.add_argument("--gap-out", default="")

    p_compact = sub.add_parser("compact")
    p_compact.add_argument("--max-lines", type=int, default=150)
    p_compact.add_argument("--backlog", default=None, help="default: docs/BACKLOG.md (new layout), falls back to existing root BACKLOG.md")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "status":
        return status(args)
    if args.cmd == "lint":
        return lint(args)
    if args.cmd == "complete":
        return complete(args)
    if args.cmd == "drop":
        return drop(args)
    if args.cmd == "relocate":
        return relocate(args)
    if args.cmd == "repair-plan-pointers":
        return repair_plan_pointers(args)
    if args.cmd == "gap-check":
        return gap_check(args)
    if args.cmd == "compact":
        return compact(args)
    parser.error(f"unknown command: {args.cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
