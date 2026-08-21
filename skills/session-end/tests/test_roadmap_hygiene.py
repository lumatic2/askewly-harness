"""roadmap_hygiene.py 계약 테스트 (M3 2026-08-19).

핵심 계약 둘을 기계로 못 박는다.
1. **깨끗하면 조용하다** — 결함 없는 ROADMAP 에서 출력은 정확히 1줄이다. 게이트가
   잔소리를 하면 사람이 /session-end 를 피하게 되고, 그러면 게이트가 있으나 없으나다.
2. **어떤 예외에도 exit 0** — 총괄 뷰 모듈 부재·projects.json 부재 어느 쪽에서도
   세션 마감이 막히지 않는다.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parents[1] / "bin" / "roadmap_hygiene.py"


def load_helper():
    spec = importlib.util.spec_from_file_location("roadmap_hygiene", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = load_helper()


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "ROADMAP.md"
    path.write_text(text, encoding="utf-8")
    return path


class KindShim:
    """실제 총괄 모듈을 그대로 위임하되 load_kinds 만 갈아끼운다.

    kind 조회는 `manifests/projects.json`(생성물)에 의존하므로 테스트에서 실제
    파일에 기대면 다른 기기에서 조용히 다르게 돈다.
    """

    def __init__(self, inner, kinds=None, raise_exc=None):
        self._inner = inner
        self._kinds = kinds or {}
        self._raise = raise_exc

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def load_kinds(self):
        if self._raise is not None:
            raise self._raise
        return self._kinds


def patch_kinds(monkeypatch, kinds=None, raise_exc=None):
    real = mod.load_portfolio_status

    def fake(path=mod.PORTFOLIO_STATUS):
        return KindShim(real(path), kinds=kinds, raise_exc=raise_exc)

    monkeypatch.setattr(mod, "load_portfolio_status", fake)


CLEAN = """# Roadmap

## Active

<!-- harness:milestone id="M9" status="active" priority="P1" -->
### M9 — 지금 하는 것
- Status: [ ]
- DoD: 무언가

## Completed

<!-- harness:milestone id="M8" status="completed" priority="P1" -->
### M8 — 끝난 것
- Status: [x]
"""


def test_clean_roadmap_prints_one_line(tmp_path, capsys, monkeypatch):
    """ⓐ 깨끗하면 출력은 정확히 1줄 — 잔소리 금지 계약의 기계 검사."""
    patch_kinds(monkeypatch)
    rc = mod.main(["--roadmap", str(write(tmp_path, CLEAN)), "--repo", str(tmp_path)])
    out = capsys.readouterr().out.strip().splitlines()
    assert rc == 0
    assert out == ["ROADMAP 위생: PASS (active 1)"]


MISPLACED = """# Roadmap

## Active Milestones

<!-- harness:milestone id="M9" status="active" priority="P1" -->
### M9 — 지금 하는 것
- Status: [ ]

## Pending Milestones

<!-- harness:milestone id="M7" status="completed" priority="P1" -->
### M7 — 닫힌 것
- Status: [x]
<!-- harness:milestone id="M6" status="completed" priority="P1" -->
### M6 — 닫힌 것
- Status: [x]

## Completed (recent)

<!-- harness:milestone id="M5" status="completed" priority="P1" -->
### M5 — 제자리에 있는 것
- Status: [x]

## 마일스톤

<!-- harness:milestone id="M4" status="completed" priority="P1" -->
### M4 — 미분류 섹션의 완료분
- Status: [x]
"""


def test_misplaced_terminal_markers(tmp_path, capsys, monkeypatch):
    """ⓑ 진행 섹션 아래 종결 마커만 잡는다 — Completed·미분류 섹션은 침묵."""
    patch_kinds(monkeypatch)
    mod.main(["--roadmap", str(write(tmp_path, MISPLACED)), "--repo", str(tmp_path)])
    out = capsys.readouterr().out
    assert "발견 2건" in out
    assert "[섹션 오배치]" in out
    assert 'M7 (completed) — "## Pending Milestones" 아래' in out
    assert 'M6 (completed) — "## Pending Milestones" 아래' in out
    # 제자리(Completed)와 미분류(마일스톤) 섹션의 완료분은 지적 대상이 아니다.
    assert "M5" not in out
    assert "M4" not in out


PENDING_ONLY = """# Roadmap

## Completed

<!-- harness:milestone id="M8" status="completed" priority="P1" -->
### M8 — 끝난 것
- Status: [x]

## Next

<!-- harness:milestone id="M9" status="pending" priority="P1" -->
### M9 — 착수 대기
- Status: [ ]
"""


def test_active_zero_with_pending_is_silent(tmp_path, capsys, monkeypatch):
    """ⓒ active 0 + pending 잔존은 **정상 상태**다 — 다음이 있으면 그걸 하면 된다.

    2026-08-20 사용자 확정: 진행 중 milestone 유무는 결함이 아니라 사용자 소유 판단이다.
    """
    patch_kinds(monkeypatch)
    mod.main(["--roadmap", str(write(tmp_path, PENDING_ONLY)), "--repo", str(tmp_path)])
    out = capsys.readouterr().out.strip().splitlines()
    assert out == ["ROADMAP 위생: PASS (active 0)"]


ALL_DONE = """# Roadmap

## Completed

<!-- harness:milestone id="M8" status="completed" priority="P1" -->
### M8 — 끝난 것
- Status: [x]
<!-- harness:milestone id="M7" status="completed" priority="P1" -->
### M7 — 끝난 것
- Status: [x]
"""


def test_all_terminal_is_silent_not_a_three_way_demand(tmp_path, capsys, monkeypatch):
    """ⓓ 전건 종결도 정상 상태다 — 승격/PARK/면제를 매 마감에 요구하지 않는다.

    구 판본은 여기서 발견 1건 + 세 갈래 처분을 냈다. 그 처분은 사용자 소유 결정이고,
    방치 판정은 주간 PORTFOLIO 리뷰의 판정 대기 큐가 이미 본다. 같은 말을 매 세션
    마감에 반복하면 사람이 /session-end 를 피하게 되고 게이트가 무력해진다.
    """
    patch_kinds(monkeypatch)
    mod.main(["--roadmap", str(write(tmp_path, ALL_DONE)), "--repo", str(tmp_path)])
    out = capsys.readouterr().out.strip().splitlines()
    assert out == ["ROADMAP 위생: PASS (active 0)"]


def test_missing_status_attribute_is_still_caught(tmp_path, capsys, monkeypatch):
    """구 ② 가 유일하게 혼자 잡던 신호는 살아 있어야 한다.

    status 속성이 아예 없는 마커는 총괄이 진행으로도 종결로도 못 읽어 레포가 조용히
    사라진다. 그건 상태가 아니라 **마커 결함**이다.
    """
    patch_kinds(monkeypatch)
    mod.main(["--roadmap", str(write(tmp_path, """# Roadmap

## Active

<!-- harness:milestone id="M9" priority="P1" -->
### M9 — status 가 없다
- Status: [ ]
""")), "--repo", str(tmp_path)])
    out = capsys.readouterr().out
    assert "[비정본 status 어휘]" in out
    assert "M9: `없음`" in out


CHECKBOX_MISMATCH = """# Roadmap

## Active

<!-- harness:milestone id="M9" status="active" priority="P1" -->
### M9 — 지금 하는 것
- Status: [ ]

## Completed

<!-- harness:milestone id="M8" status="completed" priority="P1" -->
### M8 — 닫혔다는데 체크가 없다
- Status: [ ]
"""


def test_checkbox_mismatch(tmp_path, capsys, monkeypatch):
    """ⓕ 마커 status 와 체크박스 불일치."""
    patch_kinds(monkeypatch)
    mod.main(["--roadmap", str(write(tmp_path, CHECKBOX_MISMATCH)), "--repo", str(tmp_path)])
    out = capsys.readouterr().out
    assert "[체크박스 불일치]" in out
    assert "M8: status=completed" in out


OFF_VOCAB = """# Roadmap

## Active

<!-- harness:milestone id="M9" status="doing" priority="P1" -->
### M9 — 비정본 어휘
- Status: [ ]
"""


def test_off_canonical_status(tmp_path, capsys, monkeypatch):
    """ⓖ 비정본 status 어휘 — 총괄이 진행으로 세지 않는다."""
    patch_kinds(monkeypatch)
    mod.main(["--roadmap", str(write(tmp_path, OFF_VOCAB)), "--repo", str(tmp_path)])
    out = capsys.readouterr().out
    assert "[비정본 status 어휘]" in out
    assert "M9: `doing`" in out


def test_missing_portfolio_module_skips(tmp_path, capsys):
    """ⓗ 총괄 모듈 부재 → 생략 1줄 + exit 0 (예외가 새면 마감이 막힌다)."""
    rc = mod.main([
        "--roadmap", str(write(tmp_path, CLEAN)),
        "--repo", str(tmp_path),
        "--portfolio-status", str(tmp_path / "없는파일.py"),
    ])
    out = capsys.readouterr().out.strip().splitlines()
    assert rc == 0
    assert len(out) == 1
    assert out[0].startswith("ROADMAP 위생: 생략 —")


def test_missing_projects_json_keeps_report(tmp_path, capsys, monkeypatch):
    """ⓘ load_kinds() 예외(projects.json 부재)여도 나머지 발견은 살아남는다.

    구 판본은 kind 조회를 ② 에서 썼고, 예외가 전역 가드까지 올라가면 ①③④ 가 통째로
    버려졌다(2026-08-19 코드 리뷰 적발). ② 가 사라진 지금은 kind 조회 자체를 판정에
    쓰지 않으므로, 그 예외가 어디로도 새지 않는지만 확인한다.
    """
    patch_kinds(monkeypatch, raise_exc=FileNotFoundError("projects.json"))
    rc = mod.main(["--roadmap", str(write(tmp_path, MISPLACED)), "--repo", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "[섹션 오배치]" in out
    assert "생략" not in out


def test_unexpected_exception_still_exits_zero(tmp_path, capsys, monkeypatch):
    """점검 자체가 터져도 exit 0 + 생략 1줄 — 세션 마감을 막지 않는다."""
    def boom(*_a, **_k):
        raise RuntimeError("파서 붕괴")

    monkeypatch.setattr(mod, "build_report", boom)
    rc = mod.main(["--roadmap", str(write(tmp_path, CLEAN)), "--repo", str(tmp_path)])
    out = capsys.readouterr().out.strip().splitlines()
    assert rc == 0
    assert len(out) == 1
    assert out[0].startswith("ROADMAP 위생: 생략 — RuntimeError")


OPEN_OFF_VOCAB = """# Roadmap

## Active

<!-- harness:milestone id="M9" status="todo" priority="P1" -->
### M9 — 열려 있는데 어휘가 정본 밖
- Status: [ ]
"""


def test_open_off_vocab_is_reported_as_a_vocabulary_defect(tmp_path, capsys, monkeypatch):
    """열린 milestone 인데 어휘가 정본 밖 — 상태 안내가 아니라 마커 결함으로 낸다.

    구 판본은 이걸 `[active 0]` 갈래에서 다뤘다. active 0 판정이 사라진 뒤에도 이
    신호는 ④ 가 그대로 잡아야 한다. PARK·면제는 어느 쪽이든 이 경우의 처분이 아니다.
    """
    patch_kinds(monkeypatch)
    mod.main(["--roadmap", str(write(tmp_path, OPEN_OFF_VOCAB)), "--repo", str(tmp_path)])
    out = capsys.readouterr().out
    assert "[비정본 status 어휘]" in out
    assert "M9: `todo`" in out
    assert "2. PARK 선언" not in out
    assert "3. 면제" not in out


ABSORBED_VARIANT = """# Roadmap

## Active

<!-- harness:milestone id="M9" status="in_progress" priority="P1" -->
### M9 — 흡수되는 변종
- Status: [ ]
"""


def test_absorbed_variant_wording(tmp_path, capsys, monkeypatch):
    """in_progress 는 총괄이 active 로 흡수한다 — "안 센다"는 거짓이다."""
    patch_kinds(monkeypatch)
    mod.main(["--roadmap", str(write(tmp_path, ABSORBED_VARIANT)), "--repo", str(tmp_path)])
    out = capsys.readouterr().out
    assert "흡수하긴 하지만" in out
    assert "읽지 못하는 값" not in out
    assert "(active 1)" in out


# ── M5 (2026-08-20) 배치 어휘 공유 ───────────────────────────────────────────


def test_placement_vocabulary_has_no_local_copy():
    """진행 섹션 판정은 roadmap_sync 가 소유한다 — 여기 사본이 있으면 안 된다.

    사본이 남으면 이 게이트가 지적하는 것과 `relocate` 가 실제로 옮기는 것이 갈라져
    안내문이 거짓이 된다.
    """
    source = HELPER.read_text(encoding="utf-8")
    assert "IN_PROGRESS_HEADING_RE = re.compile" not in source
    assert mod.load_roadmap_sync().IN_PROGRESS_HEADING_RE is not None


def test_terminal_statuses_agree_with_portfolio_status():
    """roadmap_sync 의 종결 4종 리터럴이 총괄 정본과 같은지.

    roadmap_sync 는 플릿 공유 스크립트라 외부 레포 절대경로에 하드 의존하지 않는다.
    그 대가로 생긴 사본의 drift 를 여기서 잡는다 — 이 테스트가 있는 자리에서만
    두 모듈이 동시에 잡히기 때문이다.
    """
    try:
        ps = mod.load_portfolio_status()
    except Exception:  # noqa: BLE001 — 총괄 모듈이 없는 기기에서는 판정할 수 없다
        pytest.skip("portfolio_status 를 불러올 수 없다")
    assert set(mod.load_roadmap_sync().TERMINAL_STATUSES) == set(ps.TERMINAL_STATUSES)


def test_placement_import_failure_keeps_other_findings(tmp_path, capsys, monkeypatch):
    """배치 어휘를 못 읽어도 exit 0 이고, 나머지 발견은 그대로 나온다.

    구 코드는 여기서 위생 점검 **전체**가 "생략" 한 줄로 사라졌다 — 이 게이트가
    막으려는 침묵과 정확히 같은 모양이라, 그게 이 probe 가 잡아야 할 회귀다.
    """
    patch_kinds(monkeypatch)
    # 오배치 **말고 다른** 발견이 있는 ROADMAP 이어야 "나머지가 산다"를 볼 수 있다.
    with_other = MISPLACED + (
        '\n<!-- harness:milestone id="M5" status="wip" priority="P1" -->\n'
        "### M5 — 어휘가 정본 밖\n- Status: [ ]\n"
    )
    rc = mod.main([
        "--roadmap", str(write(tmp_path, with_other)),
        "--repo", str(tmp_path),
        "--sync-scripts", str(tmp_path / "없는-경로"),
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert "판정이 꺼졌다" in out              # 조용히 지나가지 않는다
    assert '— "## ' not in out                 # 오배치 목록은 낼 수 없다
    assert "[비정본 status 어휘]" in out       # 나머지 발견은 산다


def test_placement_skip_is_visible_even_when_nothing_else_is_found(tmp_path, capsys, monkeypatch):
    """다른 발견이 0 이어도 '판정이 꺼졌다'가 PASS 로 삼켜지지 않는다."""
    patch_kinds(monkeypatch)
    rc = mod.main([
        "--roadmap", str(write(tmp_path, CLEAN)),
        "--repo", str(tmp_path),
        "--sync-scripts", str(tmp_path / "없는-경로"),
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert "PASS" not in out
    assert "판정이 꺼졌다" in out


def test_relocate_command_is_named_in_the_guidance(tmp_path, capsys, monkeypatch):
    """안내문이 실행 가능한 한 줄을 가리킨다 — 도구가 없어 손으로 하라는 뜻이 되면 아무도 안 한다."""
    patch_kinds(monkeypatch)
    mod.main(["--roadmap", str(write(tmp_path, MISPLACED)), "--repo", str(tmp_path)])
    assert "roadmap_sync.py\" relocate" in capsys.readouterr().out


def test_missing_roadmap_skips(tmp_path, capsys):
    """ROADMAP 자체가 없는 레포 — 만들지 않고 생략한다."""
    rc = mod.main(["--roadmap", str(tmp_path / "ROADMAP.md"), "--repo", str(tmp_path)])
    assert rc == 0
    assert "생략" in capsys.readouterr().out


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
