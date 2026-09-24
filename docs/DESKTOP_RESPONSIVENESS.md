# Desktop edit responsiveness

## Ordinary editing on experimental

This pass targets actual capture moves, select-drag previews, layout reference
moves and the refresh/recovery work that follows them. It preserves electrical
identities, isolated transactions, undo/redo and durable recovery.

- Geometry-only schematic moves, stretches and mirrors copy the containers they
  change. Changed named connections, unsupported selections and live sessions
  retain the general validated transaction. Point-label artwork drags retain
  their original semantics.
- Net identity matching uses indexed terminal/wire memberships instead of an
  all-pairs search. Validation reuses rebuilt masters within that validation;
  public flattening still creates an isolated, fresh circuit.
- Device/wire drag previews stop copying unrelated physical geometry. Committed
  layout geometry and vector pictures survive unchanged refreshes; geometry,
  order, net, layer, ownership, technology color and style changes invalidate
  their corresponding display state.
- Outline, placement, constraints, layer and selector widgets retain unchanged
  rows. Source selectors walk hierarchy without electrical netlisting.
- Recovery captures immutable bytes with the C serializer and reconstructs the
  worker-owned tree in the existing serial writer. This private in-memory
  boundary preserves Python types and observes in-place edits. No serialized
  bytes are accepted from disk/network; durable recovery files remain JSON.
  Validation, write ordering, coalescing and lifecycle fences remain in place.

## Current reproduction and evidence

Run the same harness on the baseline and modified source, using fresh output
directories and the same Python, Qt and display backend:

```sh
QT_QPA_PLATFORM=offscreen python tests/gui_analog_scale.py \
  --out build/ordinary-edit-evidence --iterations 3 \
  --command-path interactive --electrical-ledger --max-edit-ms 750
```

The baseline is experimental commit `03780af9dc5bd5acb95859c39964c81a2849fdd9`.
Its product code was unchanged; only the current measurement harness was copied
into that checkout. The baseline uses the equivalent general capture callback
where the new interactive helper does not exist. Both runs have the same
harness hash and unchanged product source throughout each run.

The [comparison](validation/ordinary-editing/comparison.json) records source
hashes, commands, environment, medians and maxima. Complete
[baseline](validation/ordinary-editing/baseline.json) and
[optimized](validation/ordinary-editing/optimized.json) reports retain individual
samples, repaint counts, memory measurements and correctness checks.

All measurements below are same-host Linux source execution with Python 3.12.14,
Qt/PySide 6.8.3 and the offscreen backend. Live layout checks are disabled. Each
operation includes immediate refresh and synchronous QWidget repaint; loading,
saving and recovery completion are recorded separately.

| Workload / operation | Baseline median | Optimized median | Optimized maximum |
|---|---:|---:|---:|
| 500 devices / 10,000 shapes: schematic move | 885.7 ms | 181.2 ms | 275.0 ms |
| 500 devices / 10,000 shapes: layout move | 882.9 ms | 300.1 ms | 321.1 ms |
| Same large design + electrical identities: schematic move | 2,020.2 ms | 350.8 ms | 381.6 ms |
| Same large design + electrical identities: layout move | 1,733.6 ms | 331.2 ms | 388.4 ms |
| Hierarchical amplifier bank: schematic move | 61.7 ms | 51.8 ms | 62.9 ms |
| Hierarchical amplifier bank: layout move | 100.4 ms | 85.0 ms | 115.3 ms |

All nine iterations passed selection/pan immutability, electrical partition,
exact undo/redo content, save/reopen and latest-unsaved-recovery checks. All edit,
undo and redo samples passed the **750 ms local ceiling**; the highest sample
was 745.2 ms (large identity workload, schematic redo). This is an improvement,
not a claim that every operation is below 200 ms. A
[500 ms trial](validation/ordinary-editing/trial-500ms.json) passed correctness
but exceeded that stricter timing budget. Large visible-layout rendering,
general transactions and undo/redo tail latency remain further work.

Two preliminary runs (including one on unchanged baseline code) encountered
intermittent older recovery-file contents after the worker reported the latest
hash. Later isolated runs passed. The earlier failures remain unexplained;
file timestamps suggest external replacement but do not establish its cause.
No correctness assertion was removed or relaxed. The final full suite and
optimized benchmark ran in one command/polling session with process stdout
retained, and the final report includes successful recovery on every iteration.

The Windows/native and Linux/X11 workflows now measure the interactive command
and identity workload while retaining their existing 1,500 ms host regression
ceiling. They also run the new widget-reuse and rendered-cache regressions.
These source/offscreen results do not establish native display, packaged app,
live DRC or consumer-hardware latency. Repeat qualification on those hosts.

Validation for this pass: 1,037 unit tests run (39 skipped), GUI presentation,
cache/rendering, wiring, labels and reliability checks, and release consistency.
The regressions also check transaction equivalence, rejected edits, stable net
identities, label anchors, hierarchy isolation, mutable-source recovery,
coalescing/failure/retry, and exact scalar types across worker snapshots.

---

## Earlier dev25 follow-up

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
