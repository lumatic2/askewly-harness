#!/usr/bin/env python3
"""Synchronize harness milestone state with ROADMAP.md.

ROADMAP.md is the active horizon board. BACKLOG.md stores compressed completed
milestone history. This script intentionally handles only harness marker blocks:

  <!-- harness:goal id="..." -->
  <!-- harness:milestone id="M1" status="active" priority="P0" -->
"""

from __future__ import annotations

import argparse
import datetime as dt
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


def parse_attrs(raw: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in ATTR_RE.finditer(raw)}


def format_attrs(attrs: dict[str, str]) -> str:
    ordered = []
    for key in ("id", "status", "priority", "evidence"):
        if key in attrs:
            ordered.append((key, attrs[key]))
    ordered.extend((k, v) for k, v in attrs.items() if k not in {k for k, _ in ordered})
    return " ".join(f'{k}="{v}"' for k, v in ordered)


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

## Proposed Next Horizon
- N1 - define the next measurable gap.
- N2 - create one evidence-producing milestone.
- N3 - add the smallest validation or smoke gate.

## Recommendation
Promote one proposed item to ROADMAP.md only after the user approves the next horizon.
"""


def horizon_check(args: argparse.Namespace) -> int:
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
    if args.gap_out:
        out = Path(args.gap_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(gap_report_text(lines, blocks), encoding="utf-8")
        print(f"gap report: {out}")
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


def compact(args: argparse.Namespace) -> int:
    roadmap = Path(args.roadmap)
    backlog = Path(args.backlog)
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
    write_lines(roadmap, new_lines)
    append_backlog(backlog, archived_entries)
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

    p_complete = sub.add_parser("complete")
    p_complete.add_argument("--milestone", required=True)
    p_complete.add_argument("--evidence", default="")
    p_complete.add_argument("--summary", default="")

    p_horizon = sub.add_parser("horizon-check")
    p_horizon.add_argument("--gap-out", default="")

    p_compact = sub.add_parser("compact")
    p_compact.add_argument("--max-lines", type=int, default=150)
    p_compact.add_argument("--backlog", default="BACKLOG.md")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "status":
        return status(args)
    if args.cmd == "complete":
        return complete(args)
    if args.cmd == "horizon-check":
        return horizon_check(args)
    if args.cmd == "compact":
        return compact(args)
    parser.error(f"unknown command: {args.cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
