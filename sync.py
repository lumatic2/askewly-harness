#!/usr/bin/env python3
"""소스 저장소에서 하네스 스킬을 떠 와 공개용으로 디커플링한다.

luka-playbook `scripts/vendor_sources.py` 를 이식·확장한 것이다 — 커밋 고정
채취·sha256 MANIFEST·`--check` drift 판정·dirty 원본 거부를 승계하고, 위에
공개 배포용 디커플링(개인 배선 제거·치환)과 leak-check 를 얹었다.
구 `SYNC.md` 수동 체크리스트를 대체한다.

    python sync.py            # skills/ 재생성 + MANIFEST + leak-check
    python sync.py --check    # 원본과 이격됐는지만 판정 (쓰지 않음)
    python sync.py --leak-check-only   # 현재 트리의 잔류 개인 배선만 스캔

작성자 기기 전용이다 — 소스 저장소가 없으면 실행되지 않는다.
사용자는 이미 떠 온 `skills/` 를 설치하면 된다.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
ROOT = Path(__file__).resolve().parent
OUT = ROOT / "skills"

# ── 채취 대상 ────────────────────────────────────────────────────────────
# (묶음, 원본 저장소, 가져올 경로, 벗겨낼 접두사, 붙일 접두사)
SOURCES = [
    (
        "skills",
        HOME / "projects/custom-skills",
        [
            "promoted/harness-plan",
            "promoted/harness-run",
            "promoted/harness-done",
            "promoted/harness-bootstrap",
            "promoted/session-end",
            "promoted/session-log",
        ],
        "promoted/",
        "",
    ),
    (
        # 부트스트랩 엔진 — init 스크립트와 갈래 스켈레톤은 scripts/ 아래,
        # cascade 템플릿(PLAN/REPORT)은 스크립트의 `$SCRIPT_DIR/../templates`
        # 해석에 맞춰 스킬 루트 templates/ 아래. 두 층을 다 채워야 한다 —
        # 한 층만 채우면 부트스트랩이 set -e 로 즉사한다(구 SYNC 실사고).
        "engine-scripts",
        HOME / "projects/harness-engineering",
        ["scripts/init-ai-readiness.sh", "scripts/templates"],
        "scripts/",
        "harness-bootstrap/scripts/",
    ),
    (
        "engine-templates",
        HOME / "projects/harness-engineering",
        ["templates/PLAN_TEMPLATE.md", "templates/REPORT_TEMPLATE.md"],
        "",
        "harness-bootstrap/",
    ),
]

# ── 제외 — 개인 인프라 없이는 동작하지 않는 파일 ─────────────────────────
EXCLUDE = {
    "harness-run/scripts/spawn_chain.py",        # Orca 워크트리 스폰 (개인 오케스트레이션)
    "harness-run/scripts/sync_stop_gate.py",     # 텔레그램 동기 정지 relay
    "harness-run/scripts/test_sync_stop_gate.py",
    "session-end/bin/update_evidence_ledger.sh", # 개인 중앙 evidence 레포 collector
}
# 접두사 단위 제외 — 디렉터리째 개인 자산인 것
EXCLUDE_PREFIX = (
    "harness-bootstrap/design-pack/",  # Askewly Design 개인 디자인 시스템 (node_modules 포함)
)

# ── 디커플링 치환 규칙 ───────────────────────────────────────────────────
# (대상 파일, 정규식, 치환문, 최소 적중 수). 최소 적중에 못 미치면 소스가
# 바뀐 것이다 — 조용히 넘어가지 않고 실패한다(규칙이 물어야 leak 이 안 샌다).
P = [
    # harness-plan: 개인 위임 규약 참조 → 일반화
    ("harness-plan/SKILL.md",
     r"운용 정본 → `~/projects/agent-orchestration/context/delegation\.md` 를 위임 결정 전 Read\.",
     "위임 규약은 자기 런타임의 서브에이전트 문서를 따른다.", 1),
    # harness-plan: 부트스트랩 경로 → 번들 경로
    ("harness-plan/SKILL.md",
     r"bash ~/projects/harness-engineering/scripts/init-ai-readiness\.sh",
     "bash ~/.claude/skills/harness-bootstrap/scripts/init-ai-readiness.sh", 1),
    # harness-plan: orca 스폰 옵트인 줄 삭제
    ("harness-plan/SKILL.md",
     r"\n\s*- \*orca 스폰 경로\(옵트인\)\*[^\n]*", "", 1),
    # harness-plan: 실행 위치 3택(M17)의 워크트리 스폰 항 삭제 → 공개판은 2택
    ("harness-plan/SKILL.md",
     r" / 워크트리 스폰\(`spawn_chain\.py` 1커맨드 — orca 옵트인\)", "", 1),
    ("harness-plan/SKILL.md",
     r"\*\*실행 위치 3택\*\* \(M17 2026-08-14\)", "**실행 위치**", 1),
    # harness-run: 이어받기 절차(M17)의 3택 언급 일반화
    ("harness-run/SKILL.md",
     r" 실행 위치 3택\(같은 턴·새 세션·워크트리 스폰\)의 어느 경로로 와도 이 계약은 같다\.",
     " 어느 경로로 와도 이 계약은 같다.", 1),
    # harness-run: 사다리 2단 위임 규약 참조 → 일반화
    ("harness-run/SKILL.md",
     r"\(운용 규약 `~/projects/agent-orchestration/context/delegation\.md` — model 명시 필수\)",
     "(자기 런타임의 서브에이전트 규약을 따른다 — model 명시 필수)", 1),
    # harness-run: 사다리 3단 텔레그램 동기 정지 → 평문 질문 정지
    ("harness-run/SKILL.md",
     r"\| \*\*3\*\* \| \*\*동기 정지 → 사용자\(텔레그램\)\*\*[^\n]*\|",
     "| **3** | **정지 → 사용자에게 평문 질문** — 지금까지 모은 근거와 함께 한 문장으로 묻고 답을 기다린다 |", 1),
    ("harness-run/SKILL.md",
     r"\*\*3단은 동기다(?:[^\n]*\n)*?[^\n]*telegram_resume_relay\.py[^\n]*\n?",
     "", 1),
    # harness-run: 공유 레포 예시명 일반화
    ("harness-run/SKILL.md",
     r"\(`custom-skills`·`harness-engineering`·`second-brain` 등 하네스 공유 레포\)",
     "(여러 세션이 함께 쓰는 레포)", 1),
    # harness-done: 개인 총괄 수집기 문장 일반화 (마커 불변 경고 자체는 보존)
    ("harness-done/SKILL.md",
     r"\*\*형식 정본은 부트스트랩이 실제로 찍는 것\*\*: `harness-engineering/scripts/init-ai-readiness\.sh` 의 ROADMAP 스켈레톤\. ⚠ \*\*태그명과 필드 키워드를 바꾸지 않는다\*\* — `agent-orchestration/scripts/portfolio_status\.py` 가 22개 레포의 이 마커를 긁어 총괄 뷰를 만들고, 이름이 바뀌면 예외 없이 조용히 빈 결과를 낸다\(2026-07-23 실측\)\.",
     "**형식 정본은 부트스트랩이 실제로 찍는 것**: 번들 `init-ai-readiness.sh` 의 ROADMAP 스켈레톤. ⚠ **태그명과 필드 키워드를 바꾸지 않는다** — 이 마커를 파싱하는 도구는 이름이 바뀌면 예외 없이 조용히 빈 결과를 낸다.", 1),
    # session-end / session-log: 저널 경로 env 화 + 개인 vault 명칭 제거
    ("session-end/bin/session-log.py",
     r'Path\.home\(\) / "vault" / "40-Logs"',
     'Path(os.environ.get("HARNESS_JOURNAL_DIR", str(Path.home() / "harness-journal")))', 1),
    ("session-log/bin/session-log.py",
     r'Path\.home\(\) / "vault" / "40-Logs"',
     'Path(os.environ.get("HARNESS_JOURNAL_DIR", str(Path.home() / "harness-journal")))', 1),
    ("session-end/bin/session-log.py", r"^(import .*\n)", r"import os\n\1", 1),
    ("session-log/bin/session-log.py", r"^(import .*\n)", r"import os\n\1", 1),
    ("session-end/bin/session-log.py", r"~/vault/40-Logs", "$HARNESS_JOURNAL_DIR", 1),
    ("session-log/bin/session-log.py", r"~/vault/40-Logs", "$HARNESS_JOURNAL_DIR", 1),
    # session-log.py 양쪽: 개인 기기명 서사·매핑 일반화
    ("session-end/bin/session-log.py",
     r"\n    2026-07-29 수리:[\s\S]*?실측 호스트명:[^\n]*\n",
     "\n    hostname 을 라벨로 매핑하고, 미등재 기기는 호스트명을 그대로 보여준다.\n", 1),
    ("session-log/bin/session-log.py",
     r"\n    2026-07-29 수리:[\s\S]*?실측 호스트명:[^\n]*\n",
     "\n    hostname 을 라벨로 매핑하고, 미등재 기기는 호스트명을 그대로 보여준다.\n", 1),
    ("session-end/bin/session-log.py", r'\("Macmini", "M4"\)', '("Macmini", "Mac mini")', 1),
    ("session-log/bin/session-log.py", r'\("Macmini", "M4"\)', '("Macmini", "Mac mini")', 1),
    ("session-end/bin/session-log.py",
     r'\n    # WSL 이 아닌 진짜 Linux 도 "M4" 로[\s\S]*?재발한다\.\n', "\n", 1),
    ("session-log/bin/session-log.py",
     r'\n    # WSL 이 아닌 진짜 Linux 도 "M4" 로[\s\S]*?재발한다\.\n', "\n", 1),
    ("session-end/SKILL.md", r"`?~/vault/40-Logs(/YYYY-MM-DD\.md)?`?",
     "`$HARNESS_JOURNAL_DIR`", 1),
    ("session-log/SKILL.md", r"`?~/vault/40-Logs(/YYYY-MM-DD\.md)?`?",
     "`$HARNESS_JOURNAL_DIR`", 1),
    ("session-end/SKILL.md", r"vault 40-Logs", "저널", 1),
    ("session-log/SKILL.md", r"vault 40-Logs", "저널", 1),
    # session-end: 개인 지식 시스템(kg·ts·sb) 절과 개인 evidence collector 절 제거
    ("session-end/SKILL.md",
     r"## 2-b\. 지식 승격 후보 인입[\s\S]*?(?=^## 3\.)", "", 1),
    ("session-end/SKILL.md",
     r"## 3\. harness evidence ledger 갱신[\s\S]*?(?=^## 4\.)", "", 1),
    ("session-end/SKILL.md", r"## 4\. 출력", "## 3. 출력", 1),
    ("session-end/SKILL.md", r"\bvault\b", "저널", 1),
    ("session-log/SKILL.md", r"\bvault\b", "저널", 0),
    # harness-bootstrap: 엔진 탐색 사슬 재작성 — 공개판은 스크립트를 번들하므로
    # 번들 경로가 1순위, 외부 체크아웃($HARNESS_ENGINEERING_ROOT)은 opt-in 폴백 (step-2)
    ("harness-bootstrap/SKILL.md",
     r"핵심 로직: harness-engineering `scripts/init-ai-readiness\.sh` \(Codex·CI 등 어디서든 호출 가능\)\. 경로는 §3 의 해석 사슬로 찾는다 — `\$HARNESS_ENGINEERING_ROOT` → `~/projects/…` → 형제 디렉터리\.",
     "핵심 로직: 번들 `scripts/init-ai-readiness.sh` (이 스킬 디렉터리에 동봉 — Codex·CI 등 어디서든 호출 가능). 경로는 §3 의 해석 사슬로 찾는다 — 번들 경로(`~/.claude`·`~/.codex`) → `$HARNESS_ENGINEERING_ROOT`(opt-in).", 1),
    ("harness-bootstrap/SKILL.md",
     r'"\$HARNESS_ENGINEERING_ROOT/scripts/init-ai-readiness\.sh"\s+"\$HOME/projects/harness-engineering/scripts/init-ai-readiness\.sh"\s+"\$\(git rev-parse --show-toplevel 2>/dev/null\)/\.\./harness-engineering/scripts/init-ai-readiness\.sh"',
     '"$HOME/.claude/skills/harness-bootstrap/scripts/init-ai-readiness.sh"          "$HOME/.codex/skills/harness-bootstrap/scripts/init-ai-readiness.sh"          "${HARNESS_ENGINEERING_ROOT:-/nonexistent}/scripts/init-ai-readiness.sh"', 1),
    ("harness-bootstrap/SKILL.md",
     r"init-ai-readiness\.sh 를 못 찾았다 — harness-engineering 체크아웃 경로를 HARNESS_ENGINEERING_ROOT 로 지정하라",
     "init-ai-readiness.sh 를 못 찾았다 — 스킬이 ~/.claude/skills 또는 ~/.codex/skills 에 설치됐는지 확인하라", 1),
    # harness-bootstrap: design-pack 은 공개판 미포함 — 참조에 표기
    ("harness-bootstrap/SKILL.md",
     r"\| `--add design` \| design-pack `DESIGN\.md` \+ lint hook \|",
     "| `--add design` | design-pack `DESIGN.md` + lint hook (⚠ 이 배포판 미포함 — 없으면 명시적으로 실패) |", 1),
    ("harness-bootstrap/SKILL.md",
     r"웹 디자인은 `--add design` 시 design-pack\(`harness-bootstrap/design-pack/`\) `minimal` family 가 `DESIGN\.md`\+lint hook 을 설치한다\.",
     "웹 디자인 design-pack 은 이 배포판에 포함되지 않는다 — `--add design` 은 팩이 없으면 명시적으로 실패한다.", 1),
    # harness-plan elicit 출처 줄: 개인 레포 경로 제거 (외부 원저작 표기는 보존)
    ("harness-plan/references/elicit.md",
     r"\(2026-07-24 열람, harness-engineering `references/harness/fn-opt-dryforge/`\)",
     "(2026-07-24 열람)", 1),
]

# 전 파일 공통 마무리 치환 — 파일별 규칙이 놓친 서사적 언급을 일반화한다.
GLOBAL_P = [
    (r"harness-engineering", "the-source-repo"),
    (r"agent-orchestration", "the-orchestration-repo"),
    (r"second-brain", "the-notes-repo"),
    (r"/mnt/c/Users/[A-Za-z0-9_]+", "/mnt/c/Users/<you>"),
    (r"[Cc]:\\+Users\\+[A-Za-z0-9_]+", r"C:\\Users\\<you>"),
    (r"/Users/[A-Za-z0-9_]+/", "/Users/<you>/"),
    (r"\byusun[a-z0-9]*\b", "<user>"),
]

# ── leak-check — 출고 트리에 남으면 안 되는 패턴 ─────────────────────────
LEAK_PATTERNS = [
    r"\byusun",
    r"lumatic",
    r"[Cc]:\\+Users\\+(?!<you>)[A-Za-z]",
    r"/Users/(?!<you>)[a-z]",
    r"/mnt/c/Users/(?!<you>)[A-Za-z]",
    r"harness-engineering",
    r"agent-orchestration",
    r"second-brain",
    r"telegram",
    r"\borca\b|\bOrca\b",
    r"~/vault|40-Logs|\"vault\"",
    r"upstage",
    r"spawn_chain|sync_stop_gate|update_evidence_ledger",
]
LEAK_SCAN_SKIP = {"sync.py", "SYNC.md"}  # 규칙 자신은 패턴을 담는다
TEXT_SUFFIXES = {".md", ".py", ".sh", ".ps1", ".txt", ".json", ".yaml", ".yml"}


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def files_of(repo: Path, rev: str, paths: list[str]) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(repo), "ls-tree", "-r", "-z", "--name-only", rev, "--", *paths],
        capture_output=True, check=True,
    ).stdout.decode("utf-8")
    return sorted(p for p in out.split("\0") if p.strip())


def blob_at(repo: Path, rev: str, rel: str) -> bytes:
    # 워킹트리가 아니라 커밋의 바이트를 읽는다 — 커밋 안 된 내용이
    # "그 커밋의 스냅샷" 이름으로 실리는 것을 막는다 (vendor_sources 승계).
    return subprocess.run(
        ["git", "-C", str(repo), "show", f"{rev}:{rel}"],
        capture_output=True, check=True,
    ).stdout


def dirty_paths(repo: Path, paths: list[str]) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain", "--", *paths],
        capture_output=True, text=True, check=True,
    ).stdout
    return [l[3:].strip() for l in out.splitlines() if l.strip()]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def apply_patches(blobs: dict[str, bytes]) -> list[str]:
    """파일별 규칙 → 전역 규칙 순서로 치환. 못 문 규칙은 실패로 처리."""
    failures: list[str] = []
    patched: set[str] = set()
    for rel, pat, repl, min_hits in P:
        if rel not in blobs:
            failures.append(f"규칙 대상 없음: {rel}")
            continue
        text = blobs[rel].decode("utf-8")
        new, n = re.subn(pat, repl, text, flags=re.MULTILINE)
        if n < min_hits:
            failures.append(f"규칙 미적중({n}<{min_hits}): {rel} :: {pat[:60]}")
            continue
        blobs[rel] = new.encode("utf-8")
        patched.add(rel)
    for rel in list(blobs):
        if Path(rel).suffix not in TEXT_SUFFIXES:
            continue
        text = blobs[rel].decode("utf-8", errors="replace")
        orig = text
        for pat, repl in GLOBAL_P:
            text = re.sub(pat, repl, text)
        if text != orig:
            blobs[rel] = text.encode("utf-8")
            patched.add(rel)
    return failures


def leak_check(tree: dict[str, bytes]) -> list[str]:
    hits: list[str] = []
    for rel, data in sorted(tree.items()):
        if rel in LEAK_SCAN_SKIP or Path(rel).suffix not in TEXT_SUFFIXES:
            continue
        text = data.decode("utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            for pat in LEAK_PATTERNS:
                if re.search(pat, line):
                    hits.append(f"{rel}:{i}: [{pat}] {line.strip()[:100]}")
                    break
    return hits


def scan_repo_tree() -> dict[str, bytes]:
    tree: dict[str, bytes] = {}
    for p in ROOT.rglob("*"):
        if p.is_file() and ".git" not in p.parts:
            tree[p.relative_to(ROOT).as_posix()] = p.read_bytes()
    return tree


def collect() -> tuple[dict[str, bytes], list[str]]:
    blobs: dict[str, bytes] = {}
    lines = [
        "# skills/ 매니페스트",
        "",
        "> `sync.py` 가 만든 생성물이다. 손으로 고치지 않는다.",
        "> 각 파일은 아래 커밋 시점의 스냅샷에 공개용 디커플링 치환을 적용한 것이다.",
        "",
    ]
    for label, repo, paths, strip, prefix in SOURCES:
        if not (repo / ".git").exists():
            raise SystemExit(f"{label}: 소스 저장소 없음({repo}) — 작성자 기기에서만 실행된다.")
        # HEAD 가 아니라 채취 경로를 마지막으로 건드린 커밋을 기록한다 —
        # HEAD 를 적으면 무관한 커밋마다 MANIFEST 가 stale 로 뜬다(2026-08-14 실측).
        head = git(repo, "log", "-1", "--format=%H", "--", *paths)
        when = git(repo, "log", "-1", "--format=%cs", "--", *paths)
        pending = dirty_paths(repo, paths)
        if pending:
            raise SystemExit(
                f"{repo.name}: 채취 대상에 커밋되지 않은 변경 {len(pending)}건.\n"
                + "\n".join(f"  {p}" for p in pending[:10])
                + "\n먼저 커밋하거나 되돌린 뒤 다시 실행한다."
            )
        picked = files_of(repo, head, paths)
        kept = []
        for rel in picked:
            dest = rel[len(strip):] if strip and rel.startswith(strip) else rel
            dest = prefix + dest
            if dest in EXCLUDE or dest.startswith(EXCLUDE_PREFIX):
                continue
            blobs[dest] = blob_at(repo, head, rel)
            kept.append(dest)
        lines += [f"## {label}", "", f"- 커밋: `{head[:12]}` ({when} 기준) · 파일: {len(kept)}개", ""]

    failures = apply_patches(blobs)
    if failures:
        raise SystemExit("디커플링 규칙 실패:\n" + "\n".join(f"  {f}" for f in failures))

    lines += ["| 파일 | sha256(치환 후) |", "|---|---|"]
    for rel in sorted(blobs):
        lines.append(f"| `{rel}` | `{sha256(blobs[rel])[:16]}` |")
    lines.append("")
    return blobs, lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="쓰지 않고 이격 여부만 판정")
    ap.add_argument("--leak-check-only", action="store_true", help="현재 트리 잔류 스캔만")
    args = ap.parse_args()

    if args.leak_check_only:
        hits = leak_check(scan_repo_tree())
        if hits:
            print(f"LEAK: {len(hits)}건")
            for h in hits[:30]:
                print(f"  {h}")
            return 1
        print("leak-check PASS: 잔류 개인 배선 0")
        return 0

    blobs, manifest_lines = collect()
    manifest = "\n".join(manifest_lines).rstrip() + "\n"
    wanted = dict(blobs)
    wanted["MANIFEST.md"] = manifest.encode("utf-8")

    hits = leak_check({f"skills/{k}": v for k, v in wanted.items()})
    if hits:
        print(f"LEAK: 치환 후에도 {len(hits)}건 잔류 — 쓰지 않고 중단")
        for h in hits[:30]:
            print(f"  {h}")
        return 1

    current: dict[str, bytes] = {}
    if OUT.exists():
        for p in OUT.rglob("*"):
            if p.is_file():
                current[p.relative_to(OUT).as_posix()] = p.read_bytes()

    added = sorted(set(wanted) - set(current))
    removed = sorted(set(current) - set(wanted))
    changed = sorted(k for k in set(wanted) & set(current) if wanted[k] != current[k])

    if args.check:
        if added or removed or changed:
            print(f"STALE: 신규 {len(added)} · 삭제 {len(removed)} · 변경 {len(changed)}")
            for k in (added + removed + changed)[:10]:
                print(f"  {k}")
            return 1
        print("skills/ 최신")
        return 0

    if OUT.exists():
        shutil.rmtree(OUT)
    for rel, data in wanted.items():
        dest = OUT / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    print(f"skills/ 갱신: 파일 {len(wanted)}개 (신규 {len(added)} · 변경 {len(changed)} · 삭제 {len(removed)})")
    print("leak-check PASS: 잔류 개인 배선 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
