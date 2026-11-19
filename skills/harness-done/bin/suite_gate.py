#!/usr/bin/env python3
"""마감 직전 레포 테스트 스위트를 실제로 돌리고 결과를 `.harness/suite-gate.json` 에 남긴다.

`report_close.py` 가 이 기록을 현재 HEAD 와 대조해, 기록이 없거나·다른 커밋의 것이거나·실패면
닫기를 거부한다. 「테스트 돌렸습니다」라는 문장 대신 실행 기록을 보게 하는 장치다.
(문장 지시는 건너뛸 수 있다는 근거 — the-orchestration-repo/research/2026-11-06-test-gates-delta.md)

명령 해석: `--command` 가 있으면 그것. 없으면 자동 감지 — pytest 설정이나 tests/ 가 있으면
pytest, package.json 에 실제 test 스크립트가 있으면 `npm test`(둘 다면 둘 다, 앞이 실패하면 멈춘다).
아무것도 없으면 status=none 으로 기록한다(테스트 없는 레포는 막지 않는다).

Usage:
  suite_gate.py --root <레포> [--command "<명령>"] [--timeout 초(기본 3600, env SUITE_GATE_TIMEOUT)]
  suite_gate.py --root <레포> --waive "<사유>"   # 플레이키·남의 변경으로 빨간 경우. 노트 `스위트:` 줄이 필수가 된다
  suite_gate.py --root <레포> --command "<명령>" --shell bash   # 명령을 기본 셸 대신 `bash -c` 로(괄호 묶음 `(cd a && …) && (cd b && …)` 용). 기록에 shell 필드
  suite_gate.py --root <레포> --command "<명령>" --stream   # 실행 출력을 로그에 쓰면서 표준 출력에도 줄 단위로 실시간 흘린다(--check 와 함께 못 쓴다)
  suite_gate.py --root <레포> --check [--head <sha>] [--command "<명령>"] [--strict-clean]
      # 실행 없이 판정만(기록을 쓰지 않는다): 기록이 pass 이고 대상 커밋(기본 HEAD)을 덮는가 —
      # 같은 커밋이거나, 기록 커밋이 조상이고 그 뒤 바뀐 파일이 전부 RECORD_ONLY_PATHS(plans/ archive/plans/ changesets/
      # archive/reports/ docs/reports/ ROADMAP.md HANDOFF.md docs/BACKLOG.md) 안. --command 를 주면 기록의 명령과 같아야 하고,
      # --strict-clean 이면 기록 당시 추적 파일 미커밋 변경(dirty_tracked)이 0 이어야 한다.
      # 덮으면 `suite-gate: covered — <사유>` exit 0, 아니면 `suite-gate: not covered — <사유>` exit 1.
  suite_gate.py --root <레포> --check --head <sha> --base <원격 sha> [...]
      # pre-push 훅용: 원격에 이미 있는 커밋(--base)이 대상의 조상이고 그 뒤 바뀐 파일이 전부 RECORD_ONLY_PATHS 안이면
      # 스위트 기록과 무관하게 덮는다(다른 세션이 HANDOFF 한 줄만 넘기는 push). 못 덮으면 위 기록 판정으로 이어진다.

실패·시간 초과 시 출력 끝 80줄을 화면에, 실행 출력은 `.harness/suite-gate.log` 에 남긴다.

exit: 0 = pass·none·waived (--check 는 덮음) / 1 = fail(시간 초과 포함) (--check 는 안 덮음) / 2 = 사용법 오류
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

RECORD = Path(".harness") / "suite-gate.json"
DEFAULT_TIMEOUT = 3600
TAIL_LINES = 80
LOG = Path(".harness") / "suite-gate.log"


def default_timeout() -> int:
    try:
        return int(os.environ.get("SUITE_GATE_TIMEOUT", ""))
    except ValueError:
        return DEFAULT_TIMEOUT
PYTEST_NO_TESTS = 5
NPM_PLACEHOLDER = "no test specified"


def _git(root: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def _has_pytest(root: Path) -> bool:
    if (root / "pytest.ini").is_file() or (root / "tests").is_dir():
        return True
    for name, marker in (("pyproject.toml", "[tool.pytest"), ("tox.ini", "[pytest]"), ("setup.cfg", "[tool:pytest]")):
        path = root / name
        if path.is_file() and marker in path.read_text(encoding="utf-8", errors="replace"):
            return True
    return False


def _has_npm_test(root: Path) -> bool:
    path = root / "package.json"
    if not path.is_file():
        return False
    try:
        script = (json.loads(path.read_text(encoding="utf-8-sig")).get("scripts") or {}).get("test")
    except ValueError:
        return False
    return bool(script) and NPM_PLACEHOLDER not in script


def detect_commands(root: Path) -> list[str]:
    commands = []
    if _has_pytest(root):
        commands.append(f'"{sys.executable}" -m pytest -q')
    if _has_npm_test(root):
        commands.append("npm test")
    return commands


def _kill_tree(proc: subprocess.Popen) -> None:
    """셸만 죽이면 손자 프로세스가 남는다 — 이 프로세스 트리만 지정해 끝낸다."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
    proc.wait()


def _echo_line(raw: bytes) -> None:
    text = raw.decode("utf-8", errors="replace")
    try:
        sys.stdout.write(text)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        sys.stdout.write(text.encode(enc, errors="replace").decode(enc, errors="replace"))
    sys.stdout.flush()


def _pump(pipe, sink) -> None:
    """--stream: 자식 출력을 줄 단위로 로그 파일과 표준 출력에 함께 흘린다."""
    for raw in iter(pipe.readline, b""):
        try:
            sink.write(raw)
            sink.flush()
        except (ValueError, OSError):
            return  # 로그가 이미 닫혔다(손자가 파이프를 쥔 채 부모가 끝남) — 조용히 멈춘다
        try:
            _echo_line(raw)
        except OSError:
            pass  # 표준 출력이 막혀도 파이프는 계속 비운다 — 안 비우면 자식이 멈춘다


def run_command(command: str, root: Path, timeout: int, log_path: Path | None = None,
                shell: str | None = None, stream: bool = False) -> tuple[int | None, str]:
    """(exit code, 전체 출력). 시간 초과면 code=None. 파이프 대신 파일 — 손자가 파이프를 쥐면 멈춘다.
    `shell="bash"` 면 플랫폼 기본 셸 대신 `bash -c <명령>` 으로 돌린다.
    `stream=True` 면 파일 대신 파이프로 받아 로그에 쓰면서 표준 출력에도 실시간으로 흘린다."""
    with (log_path.open("a+b") if log_path else tempfile.TemporaryFile()) as sink:
        sink.seek(0, os.SEEK_END)
        start = sink.tell()
        kwargs = {} if os.name == "nt" else {"start_new_session": True}
        out = subprocess.PIPE if stream else sink
        if shell == "bash":
            proc = subprocess.Popen([shutil.which("bash") or "bash", "-c", command], cwd=root,
                                    stdout=out, stderr=subprocess.STDOUT, **kwargs)
        else:
            proc = subprocess.Popen(command, cwd=root, shell=True, stdout=out, stderr=subprocess.STDOUT, **kwargs)
        pump = None
        if stream:
            pump = threading.Thread(target=_pump, args=(proc.stdout, sink), daemon=True)
            pump.start()
        try:
            code: int | None = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            code = None
        if pump is not None:
            pump.join(timeout=10)  # 손자가 파이프를 쥐고 있어도 무한정 기다리지 않는다
        sink.seek(start)
        text = sink.read().decode("utf-8", errors="replace")
    return code, text


def ensure_local_exclude(root: Path) -> None:
    """기록·로그를 이 체크아웃의 `info/exclude` 에 올린다 — 레포 `.gitignore` 에 기대지 않는다
    (M26 마감 감사 F3: untracked 로 뜬 기록을 갈래가 커밋해 버렸다). git 레포가 아니면 그냥 넘어간다."""
    rel = _git(root, "rev-parse", "--git-path", "info/exclude")
    if not rel or not rel.strip():
        return
    path = Path(rel.strip())
    if not path.is_absolute():
        path = root / path
    want = [f"/{RECORD.as_posix()}", f"/{LOG.as_posix()}"]
    try:
        have = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
        missing = [w for w in want if w not in have]
        if missing:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                if have and have[-1] != "":
                    fh.write("\n")
                fh.write("\n".join(missing) + "\n")
    except OSError:
        pass


def save_log(root: Path, text: str) -> Path:
    ensure_local_exclude(root)
    path = root / LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def tail(text: str) -> str:
    return "\n".join(text.splitlines()[-TAIL_LINES:])


def _porcelain_paths(line: str) -> list[str]:
    """`git status --porcelain` 한 줄(`XY path`, `R  a -> b`, 따옴표 경로)에서 경로들을 뽑는다."""
    body = line[3:]
    parts = body.split(" -> ") if line[:1] in "RC" or line[1:2] in "RC" else [body]
    out = []
    for part in parts:
        part = part.strip()
        if len(part) >= 2 and part[0] == part[-1] == '"':
            part = part[1:-1]
        out.append(part.replace("\\", "/"))
    return out


def _count_dirty_tracked(status_out: str | None) -> int | None:
    """추적 파일 미커밋 줄 수 — `??` 와, 경로가 전부 `.harness/` 아래인 줄(하네스 상태)은 세지 않는다."""
    if status_out is None:
        return None
    n = 0
    for ln in status_out.splitlines():
        if ln.startswith("??"):
            continue
        paths = _porcelain_paths(ln)
        if paths and all(p.startswith(".harness/") for p in paths):
            continue
        n += 1
    return n


def write_record(root: Path, **fields) -> dict:
    ensure_local_exclude(root)
    status_out = _git(root, "status", "--porcelain")
    record = {
        "head": (_git(root, "rev-parse", "HEAD") or "").strip() or None,
        "at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "dirty": len(status_out.splitlines()) if status_out is not None else None,
        # 추적 파일의 미커밋 변경 줄 수(`??` 제외) — 훅 건너뛰기 판정(--strict-clean)이 쓴다
        "dirty_tracked": _count_dirty_tracked(status_out),
        **fields,
    }
    path = root / RECORD
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record


# 통과 뒤 이 경로만 바뀐 커밋은 스위트를 다시 돌리지 않는다(M28 D5). 끝이 `/` 면 접두 경로, 아니면 정확한 파일.
# `archive/plans/` 는 마감 감사 뒤 더했다 — 닫기 커밋이 계획서를 거기로 옮겨서, 없으면 마감 push 에서 훅이 건너뛰지 못한다.
# `.harness/work.json`·`.harness/execution-ledger.jsonl` — 연쇄 승인·마감 커밋이 커밋하는 하네스 상태(M30 마감 감사).
# `.harness/` 전체가 아니다 — 그 아래 스크립트는 검사가 읽는 소스다.
RECORD_ONLY_PATHS = ("plans/", "archive/plans/", "changesets/", "archive/reports/", "docs/reports/",
                     "ROADMAP.md", "HANDOFF.md", "docs/BACKLOG.md",
                     ".harness/work.json", ".harness/execution-ledger.jsonl")


def _is_record_only(rel: str) -> bool:
    return any(rel.startswith(p) if p.endswith("/") else rel == p for p in RECORD_ONLY_PATHS)


def _load_record(root: Path) -> tuple[dict | None, str]:
    path = root / RECORD
    if not path.is_file():
        return None, f"스위트 실행 기록이 없다({RECORD.as_posix()})"
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, f"스위트 실행 기록이 깨졌다({RECORD.as_posix()})"
    if not isinstance(rec, dict):
        return None, f"스위트 실행 기록이 깨졌다({RECORD.as_posix()})"
    return rec, ""


def record_scope(root: Path, head: str | None = None, *, record: dict | None = None) -> tuple[bool, str]:
    """기록이 이 커밋을 「범위로」 덮는가 — status·command 는 보지 않는다.
    같은 커밋이거나, 기록 커밋이 대상의 조상이고 그 사이 바뀐 파일이 전부 RECORD_ONLY_PATHS 안일 때 True.
    호출자가 이미 읽은 기록이 있으면 `record` 로 넘긴다 — 한 판정에서 파일을 두 번 읽지 않는다."""
    rec = record
    if rec is None:
        rec, why = _load_record(root)
        if rec is None:
            return False, why
    recorded = rec.get("head")
    if not isinstance(recorded, str) or not recorded:
        return False, "기록에 head 가 없다"
    target = (_git(root, "rev-parse", "--verify", "--quiet", f"{head or 'HEAD'}^{{commit}}") or "").strip()
    if not target:
        return False, f"대상 커밋을 풀 수 없다({head or 'HEAD'}) — git 레포가 아니거나 없는 커밋"
    if recorded == target:
        return True, "같은 커밋"
    if _git(root, "merge-base", "--is-ancestor", recorded, target) is None:
        return False, f"기록 커밋 {recorded[:8]} 가 대상 {target[:8]} 의 조상이 아니다"
    diff = _git(root, "diff", "--name-only", "--no-renames", "-z", recorded, target)
    if diff is None:
        return False, f"기록 커밋 {recorded[:8]} 와 대상 {target[:8]} 의 차이를 읽지 못했다"
    changed = [p for p in diff.split("\0") if p]
    outside = [p for p in changed if not _is_record_only(p)]
    if outside:
        shown = ", ".join(outside[:3]) + (f" 외 {len(outside) - 3}개" if len(outside) > 3 else "")
        return False, f"기록 커밋 뒤 기록 파일 밖이 바뀌었다: {shown}"
    return True, f"기록 커밋 뒤 기록 파일 {len(changed)}개만 변경"


def base_covers(root: Path, base: str, head: str | None = None) -> tuple[bool, str]:
    """원격에 이미 있는 커밋 `base` 뒤로 대상까지 기록 파일만 바뀌었는가 — 스위트 기록은 보지 않는다.
    base 가 대상의 진짜 조상이고(0 sha·없는 커밋·되감기 아님) 바뀐 파일이 1개 이상이며 전부 RECORD_ONLY_PATHS 안일 때 True."""
    if not base or set(base) == {"0"}:
        return False, "원격 커밋이 없다(새 브랜치)"
    if not root.is_dir():
        return False, f"레포 경로가 없다({root})"
    target = (_git(root, "rev-parse", "--verify", "--quiet", f"{head or 'HEAD'}^{{commit}}") or "").strip()
    if not target:
        return False, f"대상 커밋을 풀 수 없다({head or 'HEAD'})"
    base_sha = (_git(root, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}") or "").strip()
    if not base_sha:
        return False, f"원격 커밋 {base[:8]} 이 로컬에 없다"
    if base_sha == target:
        return False, "원격 커밋과 대상이 같다"
    if _git(root, "merge-base", "--is-ancestor", base_sha, target) is None:
        return False, f"원격 커밋 {base_sha[:8]} 이 대상 {target[:8]} 의 조상이 아니다"
    diff = _git(root, "diff", "--name-only", "--no-renames", "-z", base_sha, target)
    if diff is None:
        return False, f"원격 커밋 {base_sha[:8]} 와 대상 {target[:8]} 의 차이를 읽지 못했다"
    changed = [p for p in diff.split("\0") if p]
    if not changed:
        return False, "원격 커밋 뒤 바뀐 파일이 없다"
    outside = [p for p in changed if not _is_record_only(p)]
    if outside:
        shown = ", ".join(outside[:3]) + (f" 외 {len(outside) - 3}개" if len(outside) > 3 else "")
        return False, f"원격 커밋 뒤 기록 파일 밖이 바뀌었다: {shown}"
    return True, f"원격 커밋 {base_sha[:8]} 뒤 기록 파일 {len(changed)}개만 변경"


def record_covers(root: Path, head: str | None = None, *, command: str | None = None,
                  strict_clean: bool = False) -> tuple[bool, str]:
    """`.harness/suite-gate.json` 기록이 이 커밋을 덮는가. (덮는가, 사람이 읽는 사유 한 줄)."""
    rec, why = _load_record(root)
    if rec is None:
        return False, why
    status = rec.get("status")
    if status != "pass":
        return False, f"기록 status 가 pass 가 아니다({status})"
    if command is not None and rec.get("command") != command:
        return False, f"기록의 명령({rec.get('command')})이 요청한 명령({command})과 다르다"
    if strict_clean:
        dirty = rec.get("dirty_tracked")
        if not isinstance(dirty, int) or isinstance(dirty, bool):
            return False, "기록에 dirty_tracked 가 없다(옛 기록)"
        if dirty != 0:
            return False, f"기록 당시 추적 파일에 미커밋 변경이 {dirty}줄 있었다"
    return record_scope(root, head, record=rec)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--command", default=None, help="자동 감지 대신 쓸 명령(한 줄)")
    parser.add_argument("--timeout", type=int, default=default_timeout(), help="명령당 제한 초(기본 3600, env SUITE_GATE_TIMEOUT)")
    parser.add_argument("--waive", default=None, metavar="사유", help="실행 없이 면제 기록 — 사유 필수")
    parser.add_argument("--shell", default=None, choices=["bash"], help="명령을 플랫폼 기본 셸 대신 bash -c 로 돌린다(기본: 기본 셸)")
    parser.add_argument("--stream", action="store_true", help="실행 출력을 로그 파일에 쓰면서 표준 출력에도 줄 단위로 실시간 출력(--check 와 함께 못 쓴다)")
    parser.add_argument("--check", action="store_true", help="실행 없이 기록이 이 커밋을 덮는지만 판정(기록을 쓰지 않는다)")
    parser.add_argument("--head", default=None, metavar="sha", help="--check 대상 커밋(기본 HEAD)")
    parser.add_argument("--strict-clean", action="store_true", help="--check: 기록 당시 추적 파일 미커밋 변경(dirty_tracked)이 0 일 때만 덮는다")
    parser.add_argument("--base", default=None, metavar="sha", help="--check: 원격에 이미 있는 커밋 — 그 뒤 기록 파일만 바뀌었으면 기록 없이도 덮는다")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    if not root.is_dir():
        print(f"error: 레포 경로가 없다: {root}", file=sys.stderr)
        return 2

    if args.check and args.stream:
        print("error: --stream 은 실행 전용이다 — --check 와 함께 쓰지 않는다", file=sys.stderr)
        return 2
    if args.check and args.waive is not None:
        print("error: --check 는 판정만 한다 — --waive 와 함께 쓰지 않는다", file=sys.stderr)
        return 2
    if args.check:
        if args.base is not None:
            covered, why = base_covers(root, args.base, args.head)
            if covered:
                print(f"suite-gate: covered — {why}")
                return 0
        covered, why = record_covers(root, args.head, command=args.command, strict_clean=args.strict_clean)
        print(f"suite-gate: {'covered' if covered else 'not covered'} — {why}")
        return 0 if covered else 1
    if args.head is not None or args.strict_clean or args.base is not None:
        print("error: --head·--strict-clean·--base 는 --check 와 함께만 쓴다", file=sys.stderr)
        return 2
    if args.shell == "bash" and not shutil.which("bash"):
        print("error: --shell bash 인데 bash 를 찾지 못했다(PATH 확인)", file=sys.stderr)
        return 2

    if args.timeout <= 0:
        print("error: --timeout 은 0보다 커야 한다", file=sys.stderr)
        return 2

    started_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    started = time.monotonic()
    start_head = (_git(root, "rev-parse", "HEAD") or "").strip() or None

    def finish(**fields):
        completed_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        fields.setdefault("shell", args.shell)
        end_head = (_git(root, "rev-parse", "HEAD") or "").strip() or None
        head = end_head
        if start_head != end_head:
            # 실행 중 기록 파일(노트·changeset·HANDOFF 등)만 커밋했으면 돈 코드는 그대로다 — 시작 HEAD 로
            # 기록하고 이후 커밋은 record_scope 가 덮는다(2026-11-19 M30 마감 마찰: 5분 재실행 1회).
            moved_ok = bool(start_head and end_head) and record_scope(
                root, end_head, record={"head": start_head})[0]
            if moved_ok:
                head = start_head
            else:
                fields.update(status="fail", reason="실행 중 HEAD 변경")
        return write_record(root, **fields, head=head, start_head=start_head,
                            started_at=started_at, completed_at=completed_at,
                            elapsed_seconds=round(time.monotonic() - started, 3))

    if args.waive is not None:
        reason = args.waive.strip()
        if not reason:
            print("error: --waive 에는 사유가 필요하다", file=sys.stderr)
            return 2
        rec = finish(status="waived", exit_code=None, command=args.command, reason=reason)
        if rec["status"] == "fail":
            print("suite-gate: fail — 실행 중 HEAD 변경")
            return 1
        print(f"suite-gate: waived — {reason}\n완료 노트 §3 에 `스위트: waived — <사유>` 줄을 적어야 닫힌다.")
        return 0

    commands = [args.command] if args.command else detect_commands(root)
    if not commands:
        rec = finish(status="none", exit_code=None, command=None, reason="감지된 테스트 없음")
        if rec["status"] == "fail":
            print("suite-gate: fail — 실행 중 HEAD 변경")
            return 1
        print("suite-gate: none — 감지된 테스트 없음. 있는데 못 찾은 것이면 --command 로 지정한다.")
        return 0

    log = save_log(root, "")
    write_record(root, status="running", exit_code=None, command=" && ".join(commands),
                 reason=None, log=str(log), head=start_head, start_head=start_head,
                 started_at=started_at, shell=args.shell)
    ran = 0
    for command in commands:
        print(f"suite-gate: 실행 {command}", flush=True)
        code, text = run_command(command, root, args.timeout, log, args.shell, args.stream)
        if code is None:
            print(tail(text))
            finish(status="fail", exit_code=None, command=command,
                         reason=f"시간 초과({args.timeout}초)", log=str(log))
            print(f"suite-gate: fail — 시간 초과({args.timeout}초). 전체 로그 {log}. 마지막 테스트의 병목을 진단하거나 스위트를 분할한 뒤 예산을 설정한다.")
            return 1
        if code == PYTEST_NO_TESTS and "pytest" in command:
            continue
        if code != 0:
            print(tail(text))
            finish(status="fail", exit_code=code, command=command, reason=None, log=str(log))
            print(
                f"suite-gate: fail (exit {code}) — 전체 로그 {log}. 고치고 커밋한 뒤 다시 돌린다. "
                "환경 탓이면 --command, 플레이키·남의 변경이면 --waive \"<사유>\"."
            )
            return 1
        ran += 1

    if not ran:
        rec = finish(status="none", exit_code=PYTEST_NO_TESTS, command=" && ".join(commands), reason="수집된 테스트 없음", log=str(log))
        if rec["status"] == "fail":
            print("suite-gate: fail — 실행 중 HEAD 변경")
            return 1
        print("suite-gate: none — 수집된 테스트 없음.")
        return 0
    record = finish(status="pass", exit_code=0, command=" && ".join(commands), reason=None, log=str(log))
    if record["status"] == "fail":
        print("suite-gate: fail — 실행 중 HEAD 변경")
        return 1
    print(f"suite-gate: pass — {record['command']} (dirty {record['dirty']}, {record['elapsed_seconds']}초). 전체 로그 {log}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
