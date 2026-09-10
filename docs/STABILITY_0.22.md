# Stability and performance — 0.22.0.dev7

This source update keeps the dev6 layout features and improves their implementation. It remains an engineering preview: this development host cannot complete file synchronization, and native Windows and process qualification are still open.

## Storage and recovery

`atomic_write` still writes a sibling temporary file, flushes it, calls `os.fsync`, closes it and replaces the destination only after successful synchronization. Errors retain the operating-system code and identify the failed stage and destination. A failed synchronization leaves the existing destination intact. Temporary-file cleanup cannot hide the original error. No `fsync` bypass, unchecked rename, memory-only substitute or automatic EIO retry was added.

Recovery status now remains correct after full refreshes, undo and redo. A failed snapshot stays marked **Unsaved · recovery failed** until a successful snapshot or explicit project save. Identical repeated recovery errors do not repeatedly open modal dialogs; the status and error details remain visible. Unsaved documents without a confirmed snapshot are no longer labeled as recoverable.

Use **File → Recovery → Retry recovery save** after correcting a storage problem. **Choose recovery folder…** publishes a real, fully validated and synchronized snapshot in the chosen folder before switching the session or saving the preference. A failed destination is rejected. Previous recovery folders remain discoverable, with up to eight prior folder preferences retained. A saved recovery-folder preference no longer requires creating its session directory during application startup; write failures are handled at the actual recovery attempt.

This is an application-side recovery fix, not a repair of the development host's filesystem. Direct file synchronization, data synchronization, directory synchronization and repeated fresh-file probes return error 5 here. Ordinary writes and reads work, and free space is reported in the evidence. The underlying host fault still blocks a claim of durable-save success. A clean full-suite run is required because storage failures can mask later application defects.

On native Windows, run `benchmark-windows.bat`. It now runs the real storage/recovery probe before the complete edit benchmark and leaves its report in `benchmark-results`. If that probe fails, use the reported path and error to identify a working local drive and retry. The earlier long-path dependency installer fix is preserved and is distinct from this host error.

## Editing and drawing changes

- Connected alignment reuses one verified graph for topology and spacing, avoiding a third graph build. Route endpoint attachment checks use native box lookup followed by exact polygon containment. The same indexing supports connected local moves and the complete fallback move.
- Native contact lookup retains bounded immutable patches for small edits. Each undirected contact pair is tested once; complete connected components are invalidated once even when many of their members move. Polygon contact, terminal identities, layer locks, spacing, saved constraints and atomic undo still gate edits.
- Rectangle geometry avoids unnecessary point objects. Alignment history validates the complete candidate once, including its new revision, before publishing it.
- Qt drawing paths are created when visible geometry or picking needs them. Their immutable geometry snapshots preserve correctness through in-place changes and undo. A 10k-shape GUI fixture builds only 88 paths for its initial view.
- Translated whole-array recordings use individual vector paths; controlled two-pass trials retained the original 128-pixel margin and removed rectangle batching in this path. Wide hierarchy caches are discarded when a later close-up or point query should use the native spatial search. Viewport culling includes cosmetic outline width so small pans and drags do not lose edge pixels.
- Full workspace refresh computes the saved-state digest once for its status fields. All drawing caches remain transient; none enter project files or worker snapshots.

## Validation

The focused suite passes 41 tests, including nine new stability regressions. The full suite discovers 415: 314 pass, seven real-ngspice cases skip, and 94 failure/error blocks contain the independently reproduced host synchronization error. The full suite is **not passed**.

Six pipeline GUI checks, three existing feature GUI checks and three new stability GUI checks pass. The new tests cover deferred paths and selection, exact rotated/skew array pixels during fine and long drags in both themes and patterned layers, and deliberately injected storage failures through refresh/undo/redo/retry/folder rejection. Injection only forces failures; it is not evidence of successful durability. The separately attempted actual recovery retry still reports the real host error.

Actual worker publication, full Studio recovery timing and process acceptance remain blocked. No new Windows binary, native Windows/macOS execution, foundry signoff or external-tool performance parity is claimed.

## Measurements

See the enclosing handoff's `evidence/development-0.22-dev7/performance-comparison.json` and raw source-hashed measurements. Comparisons run sequentially on one Linux offscreen Qt host. Alignment uses five samples; attachment-heavy edits use three; viewport runs use 40 frames, with a second 10k pass in reverse source order to expose timing variation. These are CPU editing/rendering measurements, not monitor FPS. Complete GUI latency including durable recovery is still unavailable.

<!-- measured-table -->

| Workload | dev6 | dev7 |
| --- | ---: | ---: |
| Align 1,000 footprints with 1,000 attached routes | 8,268.0 ms | 629.8 ms |
| Align 10,000 rectangles with topology/spacing checking | 3,238.7 ms | 2,396.7 ms |
| Move one connected component of 1,000 shapes | 516.4 ms | 278.1 ms |
| First 10k flat canvas, two independent runs | 535.9 / 547.2 ms | 372.1 / 449.5 ms |
| Pick in a 10k array after overview, two runs | 3.5 / 3.3 ms | 0.1 / 0.1 ms |
| Whole-array drag, two runs | 38.4 / 35.0 ms | 38.8 / 31.8 ms |

Attached-route alignment improves about 13.1×. Flat first-view setup improves by 31% / 18% across the two passes. Array picking no longer scans the whole overview cache. Whole-array drag remains mixed across the two passes. Its p95 remains mixed or worse; a uniform tail-latency fix is not established. Other viewport workloads and timing variation remain visible in the complete report. These tests do not establish a universal frame-rate improvement or native-display parity. Keep the raw medians/p95 values and avoid cherry-picking the faster pass.
