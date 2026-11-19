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
        ],
        "promoted/",
        "",
    ),
    (
        # 부트스트랩 엔진 — init 스크립트와 갈래 스켈레톤(PLAN/REPORT 포함)은
        # scripts/ 아래 한 곳이다(2026-09 harness-engineering → agent-orchestration/harness
        # 흡수로 templates/ 층이 scripts/templates/workflow/ 로 합쳐졌다).
        "engine-scripts",
        HOME / "projects/agent-orchestration",
        ["harness/scripts/init-ai-readiness.sh", "harness/scripts/templates"],
        "harness/scripts/",
        "harness-bootstrap/scripts/",
    ),
]

# ── 제외 — 개인 인프라 없이는 동작하지 않는 파일 ─────────────────────────
EXCLUDE = {
    "harness-run/references/fanout.md",          # orca fan-out 절차 (개인 오케스트레이션)
    "harness-run/scripts/spawn_chain.py",        # Orca 워크트리 스폰 (개인 오케스트레이션)
    "harness-run/scripts/sync_stop_gate.py",     # 텔레그램 동기 정지 relay
    "harness-run/scripts/test_sync_stop_gate.py",
    "session-end/bin/update_evidence_ledger.sh", # 개인 중앙 evidence 레포 collector
    "harness-run/scripts/fanout.py",             # 사적 Orca 의존
    "harness-run/scripts/test_fanout.py",
    "harness-run/scripts/test_harvest_worktree.py",
    # 아래는 위 셋과 같은 사유(사적 Orca 의존)로 임시 제외 — 공개 여부는 사용자 결정 대기
    "harness-run/scripts/harvest_worktree.py",   # orca 탭 정리 호출
    "harness-run/scripts/launch_session.py",     # orca 새 세션 발사
    "harness-run/scripts/test_launch_session.py",
    "harness-run/scripts/chain_handoff.py",      # orca 탭 교대
    "harness-run/scripts/test_chain_handoff.py",
    "session-end/bin/data_repos.py",             # 개인 데이터 레포(kg·ts·vault) 점검
    "session-end/tests/test_data_repos.py",
}
# 접두사 단위 제외 — 디렉터리째 개인 자산인 것
EXCLUDE_PREFIX = (
    "harness-bootstrap/design-pack/",  # Askewly Design 개인 디자인 시스템 (node_modules 포함)
)

# ── 플러그인 설치 위치 해석 ──────────────────────────────────────────────
# 원본은 폴더 복사 설치(~/.claude/skills·~/.codex/skills)를 전제한다. 공개판은
# 플러그인으로 깔리므로 설치 위치가 판마다 바뀐다 — 고정 경로를 아래 조각으로 바꾼다.
#   Claude Code: 스킬 본문의 ${CLAUDE_PLUGIN_ROOT} 를 실제 경로로 바꿔 준다.
#   Codex: 바꿔 주지 않는다 → 셸에서 빈 값으로 풀리고, 플러그인 캐시에서 찾는다.
PLUGIN_ROOT_LINE = (
    'ASKEWLY_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -d "$ASKEWLY_ROOT/skills" ] || '
    'ASKEWLY_ROOT="$(ls -d "${CODEX_HOME:-$HOME/.codex}"/plugins/cache/*/askewly/*/ 2>/dev/null | sort -V | tail -1)"; '
    '[ -d "${ASKEWLY_ROOT%/}/skills" ] || echo "askewly 플러그인 설치 위치를 못 찾았다 — 플러그인이 설치됐는지 확인하라" >&2'
)
_SCRIPTS_LINE = 'HARNESS_SCRIPTS="${ASKEWLY_ROOT%/}/skills/harness-run/scripts"'
_QUOTED_HEADER = (
    r'> HARNESS_SCRIPTS="\$HOME/\.codex/skills/harness-run/scripts"\n'
    r'> \[ -d "\$HARNESS_SCRIPTS" \] \|\| HARNESS_SCRIPTS="\$HOME/\.claude/skills/harness-run/scripts"\n'
)
PLUGIN_P = [
    (f"{name}/SKILL.md", _QUOTED_HEADER, f"> {PLUGIN_ROOT_LINE}\n> {_SCRIPTS_LINE}\n", 1)
    for name in ("harness-plan", "harness-run", "harness-done")
] + [
    ("session-end/SKILL.md",
     r'HARNESS_SCRIPTS="\$HOME/\.claude/skills/harness-run/scripts"; \[ -d "\$HARNESS_SCRIPTS" \] \|\| HARNESS_SCRIPTS="\$HOME/\.codex/skills/harness-run/scripts"\n'
     r'SE_BIN="\$HOME/\.claude/skills/session-end/bin"; \[ -d "\$SE_BIN" \] \|\| SE_BIN="\$HOME/\.codex/skills/session-end/bin"\n',
     f'{PLUGIN_ROOT_LINE}\n{_SCRIPTS_LINE}\nSE_BIN="${{ASKEWLY_ROOT%/}}/skills/session-end/bin"\n', 1),
    ("session-end/SKILL.md",
     r"# 둘 다 ~/\.claude 우선 — [^\n]*\n",
     "# 플러그인 설치 위치에서 찾는다 — Claude Code 는 아래 변수를 실제 경로로 바꿔 주고, Codex 는 플러그인 캐시에서 찾는다\n", 1),
    ("harness-done/SKILL.md",
     r"`python ~/\.claude/skills/harness-done/bin/retire_check\.py ",
     '`python "$HARNESS_SCRIPTS/../../harness-done/bin/retire_check.py" ', 1),
    ("session-end/bin/roadmap_hygiene.py",
     r"~/\.(?:claude|codex)/skills/", "<플러그인 루트>/skills/", 4),
]
# Codex 표시 파일의 스킬 호출 이름 — 플러그인으로 깔리면 `<플러그인>:<스킬>` 이다.
OPENAI_YAML_P = (r"\$(harness-(?:plan|run|done|bootstrap)|session-end)(?![\w-])", r"$askewly:\1")

# ── 디커플링 치환 규칙 ───────────────────────────────────────────────────
# (대상 파일, 정규식, 치환문, 최소 적중 수). 최소 적중에 못 미치면 소스가
# 바뀐 것이다 — 조용히 넘어가지 않고 실패한다(규칙이 물어야 leak 이 안 샌다).
P = [
    # harness-plan: 개인 위임 규약 참조 → 일반화
    ("harness-plan/SKILL.md",
     r"\(`~/projects/agent-orchestration/context/delegation\.md` 모델 선택 표\)",
     "(자기 런타임의 서브에이전트 규약 — 모델 선택 표)", 1),
    # harness-plan: Codex 어댑터 packet 경로 → 일반화
    ("harness-plan/SKILL.md",
     r", packet 은 `agent-orchestration/harness/scripts/codex_spawn_adapter\.py`",
     "", 1),
    # harness-plan elicit 출처 줄: 개인 레포 경로 제거 (외부 원저작 표기는 보존)
    ("harness-plan/references/elicit.md",
     r"\(2026-07-24 열람, agent-orchestration `harness/`\)",
     "(2026-07-24 열람)", 1),
    # harness-run: 단독 배차 하한 정본 경로 → 일반화
    ("harness-run/SKILL.md",
     r"정본 `~/projects/agent-orchestration/context/delegation\.md` 「단독 배차 하한」",
     "자기 런타임의 서브에이전트 규약", 1),
    # harness-run: 공유 레포 예시명 일반화
    ("harness-run/SKILL.md",
     r"\*\*공유 레포\(custom-skills·agent-orchestration 등\)에서는",
     "**공유 레포(여러 세션이 함께 쓰는 레포)에서는", 1),
    # harness-done: 마커 정본 경로 일반화 (마커 불변 경고 자체는 보존)
    ("harness-done/SKILL.md",
     r"`agent-orchestration/harness/scripts/init-ai-readiness\.sh` 가 찍는 것이 정본",
     "번들 `init-ai-readiness.sh` 가 찍는 것이 정본", 1),
    # harness-bootstrap: 엔진 탐색 사슬 재작성 — 공개판은 스크립트를 번들하므로
    # 번들 경로가 1순위, 외부 체크아웃($AO_ROOT)은 opt-in 폴백
    ("harness-bootstrap/SKILL.md",
     r"핵심 로직: `harness/scripts/init-ai-readiness\.sh`\(구 h-e\) \(Codex·CI 등 어디서든 호출 가능\)\. 경로는 §3 의 해석 사슬로 찾는다 — `\$AO_ROOT`\(기본 `~/projects/agent-orchestration`\) → 형제 디렉터리\.",
     "핵심 로직: 번들 `scripts/init-ai-readiness.sh` (이 스킬 디렉터리에 동봉 — Codex·CI 등 어디서든 호출 가능). 경로는 §3 의 해석 사슬로 찾는다 — 번들 경로(플러그인 설치 위치) → `$AO_ROOT`(opt-in).", 1),
    ("harness-bootstrap/SKILL.md",
     r'AO_ROOT="\$\{AO_ROOT:-\$HOME/projects/agent-orchestration\}"\n',
     'AO_ROOT="${AO_ROOT:-/nonexistent}"\n', 1),
    ("harness-bootstrap/SKILL.md",
     r'for c in "\$AO_ROOT/harness/scripts/init-ai-readiness\.sh" "\$\(git rev-parse --show-toplevel 2>/dev/null\)/\.\./agent-orchestration/harness/scripts/init-ai-readiness\.sh"; do',
     PLUGIN_ROOT_LINE + '\nfor c in "${ASKEWLY_ROOT%/}/skills/harness-bootstrap/scripts/init-ai-readiness.sh" "$AO_ROOT/scripts/init-ai-readiness.sh"; do', 1),
    ("harness-bootstrap/SKILL.md",
     r"init-ai-readiness\.sh 를 못 찾았다 — agent-orchestration 체크아웃 경로를 AO_ROOT 로 지정하라",
     "init-ai-readiness.sh 를 못 찾았다 — askewly 플러그인이 설치됐는지 확인하라(Claude Code `/plugin` · Codex `codex plugin list`)", 1),
    # harness-bootstrap: 개인 디자인 스킬 참조 제거
    ("harness-bootstrap/SKILL.md",
     r"웹 화면 디자인은 팩이 아니라 `/askewly-design` 스킬이 받는다\(design-pack 은 2026-09-21 은퇴 — 공식 DESIGN\.md 스펙과 불일치한 채 8/6 부터 STALE 이었다\)\.",
     "웹 화면 디자인은 팩이 아니라 별도 디자인 스킬의 몫이다.", 1),
    # harness-done: 개인 vault 경로 조각 제거
    ("harness-done/bin/retire_check.py", r'"40-Logs/", ', "", 1),
    # 워크트리 규약 문서 이름(orca.md) 일반화 — 주석·메시지 문자열만
    ("harness-run/scripts/check_worktree_scope.py", r"`?orca\.md`?(?= §)", "워크트리 규약", 3),
    ("harness-run/scripts/roadmap_sync.py", r"orca\.md(?= §)", "워크트리 규약", 2),
    # session-end: Orca 프로젝트 그룹 서사 일반화
    ("session-end/bin/roadmap_parse.py", r"Orca 프로젝트 그룹으로", "다른 계층 정본으로", 1),
    # session-end: 개인 데이터 레포 점검 절(§2)과 Orca 새 세션 발사 절(§3b) 제거
    ("session-end/SKILL.md",
     r"## 2\. 데이터 레포 점검[\s\S]*?(?=^## 3\.)", "", 1),
    ("session-end/SKILL.md",
     r"## 3b\. 새 세션 발사[\s\S]*?(?=^## 4\.)", "", 1),
    # session-end: 저널 경로 env 화 + 개인 vault 명칭 제거
    ("session-end/SKILL.md", r"`?~/vault/40-Logs(/YYYY-MM-DD\.md)?`?",
     "`$HARNESS_JOURNAL_DIR`", 1),
    ("session-end/SKILL.md", r"vault 40-Logs", "저널", 1),
    ("session-end/SKILL.md", r"\bvault\b", "저널", 1),
]

# 전 파일 공통 마무리 치환 — 파일별 규칙이 놓친 서사적 언급을 일반화한다.
GLOBAL_P = [
    (r"harness-engineering", "the-source-repo"),
    (r"agent-orchestration", "the-orchestration-repo"),
    (r"second-brain", "the-notes-repo"),
    (r"askewly-(?:command|precon|security)[a-z-]*", "a-private-repo"),
    (r"/mnt/c/Users/[A-Za-z0-9_]+", "/mnt/c/Users/<you>"),
    (r"[Cc]:\\+Users\\+[A-Za-z0-9_]+", r"C:\\Users\\<you>"),
    (r"/Users/[A-Za-z0-9_]+/", "/Users/<you>/"),
    (r"\byusun[a-z0-9]*\b", "<user>"),
]

# ── leak-check — 출고 트리에 남으면 안 되는 패턴 ─────────────────────────
LEAK_PATTERNS = [
    r"\byusun",
    r"lumatic",                            # 허용 문자열(LEAK_ALLOW)은 검사 전에 지운다
    r"\.(?:claude|codex)/skills",         # 폴더 복사 설치 시절의 고정 경로 — 플러그인에서는 안 맞는다
    r"[Cc]:\\+Users\\+(?!<you>)[A-Za-z]",
    r"/Users/(?!<you>)[a-z]",
    r"/mnt/c/Users/(?!<you>)[A-Za-z]",
    r"harness-engineering",
    r"agent-orchestration",
    r"second-brain",
    r"askewly-(?:command|precon|security)",
    r"telegram",
    r"\borca\b|\bOrca\b",
    r"~/vault|40-Logs|\"vault\"",
    r"upstage",
    r"spawn_chain|sync_stop_gate|update_evidence_ledger",
]
# 개인 배선이 아닌 공개 정보 — 이 레포 주소와, 따옴표·공백으로 끝나는 계정 주소만.
# 같은 계정의 다른 레포 주소는 허용하지 않는다.
LEAK_ALLOW = re.compile(
    r"(?:github\.com/)?lumatic2/askewly-harness(?![\w-])|github\.com/lumatic2(?=[\"'\s>)]|$)"
)
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
    for rel, pat, repl, min_hits in P + PLUGIN_P:
        if rel not in blobs:
            failures.append(f"규칙 대상 없음: {rel}")
            continue
        text = blobs[rel].decode("utf-8")
        # 치환문은 글자 그대로 넣는다 — 셸 조각의 역슬래시·그룹 참조가 해석되지 않게.
        new, n = re.subn(pat, lambda _m, _r=repl: _r, text, flags=re.MULTILINE)
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
        if rel.endswith("agents/openai.yaml"):
            text = re.sub(OPENAI_YAML_P[0], OPENAI_YAML_P[1], text)
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
            line = LEAK_ALLOW.sub("", line)
            for pat in LEAK_PATTERNS:
                if re.search(pat, line):
                    hits.append(f"{rel}:{i}: [{pat}] {line.strip()[:100]}")
                    break
    return hits


def scan_repo_tree(root: Path = ROOT) -> dict[str, bytes]:
    """제품에 들어가는 파일만 본다 — 추적 파일과, gitignore 에 안 걸린 미추적 파일."""
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True, check=True,
    ).stdout.decode("utf-8")
    tree: dict[str, bytes] = {}
    for rel in sorted(r for r in out.split("\0") if r.strip()):
        p = root / rel
        if p.is_file():
            tree[rel] = p.read_bytes()
    return tree


def collect(allow_dirty: bool = False) -> tuple[dict[str, bytes], list[str]]:
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
        if pending and allow_dirty:
            # 읽는 것은 커밋의 바이트다(blob_at) — 작업 중인 변경은 실리지 않는다.
            print(f"주의: {repo.name} 에 커밋되지 않은 변경 {len(pending)}건 — 마지막 커밋 {head[:12]} 기준으로 뜬다.")
        elif pending:
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
    ap.add_argument("--allow-dirty-source", action="store_true",
                    help="원본에 커밋 안 된 변경이 있어도 마지막 커밋 기준으로 뜬다(기본은 거부)")
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

    blobs, manifest_lines = collect(allow_dirty=args.allow_dirty_source)
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
