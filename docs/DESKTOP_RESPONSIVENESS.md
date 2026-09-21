# Desktop edit responsiveness

This experimental follow-up targets the measured 500-device/10,000-shape edit
workload. It preserves full connectivity validation, transactional isolation,
undo/redo and durable recovery. It changes three avoidable costs:

- Electrical flattening isolates devices and wires without copying unrelated
  layout geometry. A reused master is rebuilt once per flatten call; each
  instance still resolves its own parameters and port mapping.
- Schematic transaction repair reads History's existing previous snapshot.
  The callback still edits an isolated copy; a second complete cell copy is removed.
- Each outline refresh draws one icon per device kind and reuses it for matching
  rows. It still rebuilds the rows and updates names, values, selection and theme.

## Reproduction and acceptance

Use the same Python/Qt versions and display backend for before/after comparisons:

```sh
QT_QPA_PLATFORM=offscreen python tests/gui_analog_scale.py \
  --out build/analog-scale-evidence --iterations 3 --max-edit-ms 1500
```

The **1,500 ms regression ceiling** applies to every recorded schematic/layout
edit, undo and redo sample, including immediate refresh and synchronous repaint.
It excludes loading, saving and recovery completion, which remain measured
separately. Both Windows and Linux desktop workflows enforce the ceiling and
retain the report. The report fails if any selected stage exceeds it; medians
do not hide slow samples. This initial ceiling is not an immediate-response
claim. A further goal is ordinary edits below 200 ms on a declared native host.

Every workload checks selection/pan without design mutation, unchanged electrical
partition after moves, exact content after undo/redo, saved-project reopening,
and recovery of the latest unsaved edit without overwriting the saved file.
Focused flatten regressions cover input/output isolation, wire authority,
shared-master parameter/port differences, fresh reads after source edits and
failure without partial mutation.

## Recorded follow-up

The [comparison](validation/dev25/performance-followup/comparison.json) identifies
the unchanged baseline and modified source hashes, environment, timing medians
and maxima, and links the complete before/after reports. The baseline is
experimental commit `a2df5e81654e7509f82aa9dceaf099cc476f4d6a`. All measurements
are source execution on this Linux host with Qt offscreen; the existing draft
contains the baseline, not these improvements.

| Workload / operation | Baseline median | Optimized median |
|---|---:|---:|
| 500 devices / 10,000 shapes: schematic edit | 1,136.5 ms | 954.6 ms |
| 500 devices / 10,000 shapes: layout edit | 1,338.0 ms | 887.8 ms |
| Hierarchical amplifier bank: schematic edit | 98.8 ms | 72.1 ms |
| Hierarchical amplifier bank: layout edit | 148.0 ms | 108.6 ms |

All six iterations passed the correctness checks and the configured edit budget
with unchanged product source during each run. These are same-host source
measurements; they are not comparisons with the earlier 1.7-second record from
a different host. The new hosted budget still needs validation on its own commit.

The remaining cost includes full transaction copying/validation, connectivity
rebuilds, widget reconstruction and recovery snapshots. Further work should
profile those paths before introducing narrower invalidation or transaction
specialization. Keep the existing correctness gates. Repeat on real consumer
displays: offscreen timings do not measure physical presentation latency,
mixed-monitor behavior, audio, accessibility or packaged application acceptance.
