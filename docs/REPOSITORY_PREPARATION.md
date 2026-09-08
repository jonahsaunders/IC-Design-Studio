# GitHub repository preparation

Prepared from `IC-Design-Studio-0.13.0-AI-Handoff(1).zip` on 2026-09-08.
Application version remains 0.13.0.

## Changes

- Extracted the complete 264-file source archive into the repository root.
- Preserved application code, examples, tests, native sources, packaging scripts,
  dependencies, GPL license and third-party notices byte-for-byte.
- Expanded `.gitignore` for local environments, credentials, caches, build output
  and release archives; added `.gitattributes` for cross-platform line endings.
- Added `UPLOAD_TO_GITHUB.md` with terminal, Desktop and browser upload routes
  and a manifest of the original companion release downloads.
- Corrected outdated README and release-status references to 0.13.0.
- Preserved current continuation notes and selected original evidence summaries
  under `docs/handoff/`, with their historical scope stated explicitly.
- Enabled the existing desktop workflow on relevant pushes to main/master,
  expanded source-path triggers, added required Linux desktop libraries and a
  45-minute job timeout, and allowed both platform jobs to finish independently.
- Set `launch-linux.sh` executable. The ZIP contains no Git metadata or remote.

## Validation performed during preparation

| Check | Result |
| --- | --- |
| Original release files versus supplied SHA-256 checksums | All 5 match |
| Original source files retained | All 264 present |
| Application modules, tests, examples and licenses | Unchanged |
| Python syntax | All 143 Python files parsed |
| Unit regression suite | 185 tests passed; no skips reported |
| Native Qt smoke suite | Passed with `QT_QPA_PLATFORM=offscreen` |
| Workflow YAML and JSON parsing | Passed |
| Links in added/updated overview documentation | Resolved |
| Git tracking of workflow, ignore rules and attributes | Confirmed |
| Ignore behavior for local secrets, dependencies and build output | Confirmed |
| Common embedded credential patterns | No matches found |

Tests ran on Python 3.12 with the supplied pinned PySide6 6.8.3 and KLayout
0.30.5 dependencies. The host initially lacked `libEGL.so.1`; the GUI smoke test
then passed using loader libraries extracted from the original Linux bundle.
That test exercised editing, undo/redo, worker simulation, geometry, DRC,
keyboard interactions, themes and recovery. It is an offscreen check.

The GitHub-hosted Linux/Windows build matrix, installer checks, external-engine
physical verification and fresh-desktop/user acceptance were not run during
repository preparation. No new qualification is inferred from the original
handoff evidence. No GitHub repository or Release has been published.

The original source ZIP SHA-256 is:

```text
10afe3ec5ae9e2d8302792f6ed267d1cb3c3554a45a58c9e9b65af8e95aa349a
```

Large app/PDK/evidence archives, tool installers and historical handoff bundles
remain in the original attachment. The repository's upload guide identifies
which original downloads can accompany a GitHub Release.
