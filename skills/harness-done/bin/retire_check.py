#!/usr/bin/env python3
"""은퇴 검사 — 은퇴시킨 옛 이름이 ~/projects 전 레포의 추적 파일에 남았는지 확인한다.

사용: python retire_check.py "<옛 이름>" ["<옛 이름2>" ...] [--root ~/projects] [--json] [--include-history]
exit 0 = 잔존 0, 1 = 잔존 있음.
"""
import argparse
import fnmatch
import json
import os
import subprocess
import sys

# 건너뛸 레포 디렉터리 이름
SKIP_REPO_DIRS = ("reference", "archive")
# 과거 기록: 경로에 이 조각이 들어간 것은 제외
HISTORY_PATH_PARTS = ("archive/", "changesets/", "research/", "logs/", "evidence/",
                      "deprecated/", "-findings/", ".harness/")  # deprecated = 꺼진 스킬 버킷 · *-findings = 조사 기록
# 과거 기록: 파일명 패턴
HISTORY_NAME_GLOBS = ("HANDOFF.md", "CHANGELOG*", "*.jsonl")
MAX_LEN = 120


def is_history(path):
    p = "/" + path.replace("\\", "/")
    if any((part if part.startswith("-") else "/" + part) in p for part in HISTORY_PATH_PARTS):
        return True
    name = p.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(name, g) for g in HISTORY_NAME_GLOBS)


def grep_repo(repo, names):
    cmd = ["git", "-C", repo, "grep", "-n", "-I", "-F"]
    for n in names:
        cmd += ["-e", n]
    r = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace")
    hits = []
    for line in r.stdout.splitlines():
        parts = line.split(":", 2)
        if len(parts) == 3:
            hits.append((parts[0], parts[1], parts[2]))
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="+")
    ap.add_argument("--root", default=os.path.join("~", "projects"))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--include-history", action="store_true")
    a = ap.parse_args()
    root = os.path.expanduser(a.root)

    results = {}
    for d in sorted(os.listdir(root)):
        repo = os.path.join(root, d)
        if d in SKIP_REPO_DIRS or not os.path.exists(os.path.join(repo, ".git")):
            continue
        hits = [h for h in grep_repo(repo, a.names) if a.include_history or not is_history(h[0])]
        if hits:
            results[d] = hits

    total = sum(len(v) for v in results.values())
    if a.json:
        out = {"total": total, "repos": {k: [{"path": p, "line": int(l), "text": t.strip()[:MAX_LEN]} for p, l, t in v]
                                          for k, v in results.items()}}
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        for repo, hits in results.items():
            print(f"[{repo}]")
            for p, l, t in hits:
                print(f"  {p}:{l}: {t.strip()[:MAX_LEN]}")
        print(f"잔존 {total}건 · {len(results)}레포" if total else "잔존 0 — 은퇴 완료")
    return 1 if total else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
