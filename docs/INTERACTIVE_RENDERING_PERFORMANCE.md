# Interactive layout rendering

This follow-up reduces the foreground work needed to select and redraw layout
geometry. Project contents, validation, connectivity, undo and recovery semantics
are unchanged.

## Changes

- Flat-layout picture chunks now depend on their own highlighted shapes. Selecting
  a shape or cross-probing a net only rerecords chunks whose appearance changes.
  Device-owned shapes, multiselection and deselection follow the same rule.
  Unchanged frames also reuse the highlight mask rather than scanning shapes.
- The rectangle batching option is resolved once per drawing pass. Previously,
  each visible rectangle could perform an expensive missing-attribute lookup on
  the Qt widget.

The retained pixel comparisons use the uncached renderer as an independent
reference. They cover overlapping translucent geometry, selection, linked-device
and net highlights, in-place metadata edits, reordering, undo/redo, themes, zoom,
pan and layer styles.

## Measurements

Baseline: experimental commit `c33cee4dbbab1cdafb03f11a7aa1d11b08230c57`.
Both runs use the updated benchmark harness, Python 3.12 and Qt 6.8.3 on the same
Linux host with the offscreen renderer. Canvas measurements use 30 frames per
operation at each size. Timings describe these workloads and host; they do not
measure physical display presentation or qualify packaged applications.

| Workload | Baseline median | Updated median |
| --- | ---: | ---: |
| Select/deselect, 1,000 flat shapes | 50.0 ms | 37.7 ms |
| Select/deselect, 1,024 hierarchy occurrences | 52.4 ms | 39.4 ms |
| Select/deselect, 10,000 flat shapes | 220.9 ms | 81.6 ms |
| Select/deselect, 10,000 hierarchy occurrences | 287.4 ms | 137.2 ms |

The canvas benchmark excludes inspector updates, recovery and other full-window
work. Pan, zoom and drag timings were mixed across workloads and runs, including
regressions. These measurements establish a selection-redraw improvement, not a
general editing or frame-rate improvement. The 10,000-shape flat workload uses
about 63% less time for selection redraw; the hierarchy workload uses about 52%
less. The hierarchy improvement comes from the drawing-loop change, while flat
layouts also benefit from narrower chunk invalidation.

The [comparison](validation/interactive-rendering/comparison.json) records source
hashes and measurements. Complete [baseline](validation/interactive-rendering/layout-before.json)
and [final](validation/interactive-rendering/layout-after.json) canvas results
include the other measured operations and 95th percentiles.

## Experiments and limitations

An attempted spatial-query fast path was removed before this change was finalized:
although it helped fully contained viewport queries, a same-process point-query
comparison was slower. The [paired Studio experiment](validation/interactive-rendering/paired-with-spatial.json)
also showed slower schematic moves. The final patch leaves spatial queries alone.

Earlier canvas runs are retained as
[initial candidate](validation/interactive-rendering/layout-intermediate.json) and
[candidate with highlight-mask reuse](validation/interactive-rendering/layout-with-spatial.json).
Both include the discarded spatial change. The corresponding full-Studio
[baseline](validation/interactive-rendering/desktop-before.json),
[initial candidate](validation/interactive-rendering/desktop-intermediate.json) and
[mask-reuse candidate](validation/interactive-rendering/desktop-with-spatial.json)
passed correctness checks but showed mixed timings, including slower edit samples.
Those candidate results are not evidence for a general editing speedup in the
final patch. Diagnostic profiles are retained in the same evidence directory.

## Validation

The final renderer-only source passed the full unit suite: 1,201 tests run,
44 skipped. It also passed the chunk pixel comparisons, layout-cache refresh
and presentation-reuse GUI checks. The [check record](validation/interactive-rendering/checks.json)
and [unit output](validation/interactive-rendering/unit-tests.txt) retain the
commands and results. Release/document consistency checks passed. These are
Linux source/offscreen checks; native Windows and packaged display qualification
remain for the existing desktop CI workflows.

## Reproduce

```sh
QT_QPA_PLATFORM=offscreen python scripts/benchmark_layout.py \
  --out build/layout-rendering.json --sizes 1000 10000 --frames 30
QT_QPA_PLATFORM=offscreen python tests/gui_analog_scale.py \
  --out build/desktop-rendering --iterations 3 --command-path interactive \
  --electrical-ledger --live-checks --display-class offscreen
QT_QPA_PLATFORM=offscreen python tests/gui_layout_chunks.py
python -m unittest discover -s tests -v
python scripts/check_release.py
```

For a matching baseline, run the same `scripts/benchmark_layout.py` harness with
`--source /path/to/baseline-checkout`. The new `selection_repaint` measurement
includes the frame painted after selection changes; `selection` continues to
measure hit-testing alone.

One initial, unmodified five-iteration desktop baseline failed its latest-recovery
read assertion. A fresh three-iteration baseline passed all nine workload
iterations without changes to product code or assertions. The failed record is
retained in the [failed baseline record](validation/interactive-rendering/desktop-initial-failure.json);
its cause is not established by this rendering change. Recovery checks remain enabled.
