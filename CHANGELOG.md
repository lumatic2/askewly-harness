# Changelog

Each release is a snapshot of how the harness is actually run at that date.

## 0.1.2 — 2026-11-20

- On Codex, skills pick the newest installed plugin version by version order and say so when the plugin cannot be found, instead of failing later on a missing script path.
- `skills/` re-taken from the source at the commit recorded in `skills/MANIFEST.md` (completion-gate fixes).

## 0.1.1 — 2026-11-20

- README lists where the install was actually exercised. No change to the skills.

## 0.1.0 — 2026-11-20

First plugin release.

- Installs as a plugin on Claude Code and Codex (`askewly@askewly`). The `install.sh` / `install.ps1` copy installers are removed.
- Skills are called with the plugin name in front: `/askewly:harness-plan`, `/askewly:harness-run`, `/askewly:harness-done`, `/askewly:harness-bootstrap`, `/askewly:session-end`.
- Skill bodies no longer assume a fixed copy-install folder; they resolve the plugin's install location at run time.
- `skills/` re-taken from the source at `e6131d3` (see `skills/MANIFEST.md`).
