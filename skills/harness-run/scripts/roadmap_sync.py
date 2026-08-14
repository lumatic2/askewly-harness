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
    block = next((b for b in blocks if b.milestone_id == args.milestone), None)
    if block is None:
        print(f"milestone not found: {args.milestone}", file=sys.stderr)
        return 1

    # 2026-08-06 감사 #15②: 직전 status 를 보지 않고 completed 로 덮어써서 blocked·pending
    # milestone 도 무조건 완료가 됐다. 막힌 것을 닫는 건 사람의 판단이므로 --force 를 요구한다.
    prior = block.attrs.get("status", "pending")
    if prior not in {"active", "completed"} and not getattr(args, "force", False):
        print(
            f"거부: {args.milestone} 의 현재 status 는 '{prior}' 다 — 완료로 덮지 않는다.\n"
            f"  막힌·보류 중인 milestone 을 닫는 것은 사람의 판단이다. 의도한 것이면 --force 를 준다.",
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
    write_lines(path, lines)
    print(f"completed {args.milestone}")
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


def dangling_plan_pointers(roadmap: Path, lines: list[str]) -> list[str]:
    """ROADMAP 이 가리키는 plan doc 이 실재하는지 검사한다 (2026-07-20).

    plan doc 의 존재 이유는 "새 에이전트가 읽고 몇 시간 이어받는다"인데, 재개
    경로는 ROADMAP milestone 블록의 `- Plan:` 포인터를 따라간다. 2026-07-17 배치
    이동(`docs/plans/` → `archive/plans/`)이 백링크를 안 고쳐 이 레포 포인터 18개
    중 11개가 빈 주소였다 — 가장 최근 완료한 LA2·LA3 포함. 계획 산출물의 전달
    경로 자체가 끊긴 것이라 completed 라고 면제하지 않는다(재개·감사 둘 다 깨진다).
    """
    root = roadmap.resolve().parent
    missing: list[str] = []
    seen: set[str] = set()
    for path in pointer_scan_files(roadmap):
        text = "\n".join(lines) if path == roadmap.resolve() else path.read_text(encoding="utf-8")
        label = path.relative_to(root).as_posix() if path != roadmap.resolve() else roadmap.name
        for pointer in dict.fromkeys(PLAN_POINTER_RE.findall(text)):
            if (root / pointer).is_file() or pointer in seen:
                continue
            seen.add(pointer)
            missing.append(f"{label}: {pointer}")
    return missing


def lint(args: argparse.Namespace) -> int:
    """살아있는 계획 문서의 plan doc 포인터가 실재하는지. exit 1 = 위반.

    구 Scale 선언 검사(`changesets>=N`)는 2026-07-23 재조립 P3 에서 제거했다 —
    milestone 크기를 changeset 수로 재던 규약이 horizon 층과 함께 폐지됐다.
    cs#245: 검사 범위를 ROADMAP → 살아있는 계획 문서 전체(BACKLOG·plans/·horizons)로 확대.
    """
    roadmap = Path(args.roadmap)
    lines = read_lines(roadmap)
    errors: list[str] = []
    for pointer in dangling_plan_pointers(roadmap, lines):
        errors.append(
            f"dangling plan pointer: `{pointer}` — 파일이 없다. 아카이브로 옮겼으면 "
            "`archive/plans/…` 로 백링크를 갱신한다 (재개 경로가 끊긴다)"
        )
    if errors:
        print("roadmap lint: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("roadmap lint: PASS (plan 포인터 전부 실재)")
    return 0


# (제거 2026-07-23, 재조립 P3) size_retro_line — milestone 크기를 changeset 수로
# 재던 인플레 적발기. 크기 규약(Scale 선언·하한 게이트·verdict 장부)이 horizon 층과
# 함께 폐지됐다. 크기 판정은 계획서의 step 수와 리프 판정으로 되돌아간다.
def status(args: argparse.Namespace) -> int:
    lines = read_lines(Path(args.roadmap))
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
    if args.cmd == "gap-check":
        return gap_check(args)
    if args.cmd == "compact":
        return compact(args)
    parser.error(f"unknown command: {args.cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
