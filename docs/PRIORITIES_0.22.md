# Layout workflow update — 0.22.0.dev6

The current source is **0.22.0.dev7**. This document describes the features introduced in dev6; its timing table is historical. See the [current stability update](STABILITY_0.22.md) for recovery changes, measured improvements and remaining blockers.


This development build implements bounded improvements across the seven approved workflow priorities. Release qualification is incomplete: this host still returns `OSError: [Errno 5] Input/output error` from `os.fsync`, and no native Windows, Magic, Netgen or ngspice qualification was available. No storage check was disabled. Use the source launcher; the preserved 0.21.0 binaries do not contain these changes.

| Priority | Added in this build | Remaining boundary |
| --- | --- | --- |
| 1. Release and recovery | Reusable real-storage/recovery probe; actual alignment command, undo/redo and recovery attempts; failure remains visible after the command refresh. Fresh full-suite and worker attempts retain their errors. | Full durable integration, crash recovery and native Windows installation remain unqualified. |
| 2. Interaction performance | Stationary geometry replays during partial drag; label-free vector geometry can replay across zoom levels. Complete generated footprints and flat-cell align/distribute use constrained history operations. Flat connected edit checks use indexed contact components. | Recovery is synchronous. Cold cache setup remains visible. Hierarchical verification uses the complete fallback; no GPU/display-FPS claim. |
| 3. Schematic-driven layout | Review current, changed, missing, orphan and unsupported placements; update changed linked MOS geometry at its saved origin/orientation, preserve role/pin IDs and optionally retarget routes. | Missing devices and deleted footprints need explicit placement/removal. Hierarchical ECO and arbitrary contact healing remain open. |
| 4. One process workflow | Pinned SKY130A qualification driver verifies every locked file and prepares a nominal inverter plus narrow-metal, route-open and channel-length faults. Fixed hidden-body symbol order when creating devices from older catalogs. | Actual process DRC, device extraction, LVS and simulation cases are **not run** here. The script must pass with the real engines before qualification. |
| 5. Routing and intent | Canvas start/end routing with direct-bend and full-via previews, cancel and stale-state rejection; full detour search remains a cancellable worker. New matched/shield routes retain shape identities and are checked after editing. Connected edits reject new saved analog/route constraint violations. | Preview cap: 2,500 expanded shapes. No general push-and-shove, interactive waypoint router or electrical matching guarantee. |
| 6. Device generation | Stable MOS geometry roles and terminal IDs across dimension changes; recorded rotations/mirrors support regeneration. Mirror generation now accepts equal 1–8-finger devices. Constraint placement updates footprint origins and pins. | Legacy transformed records without orientation still require explicit regeneration. Automatic dummy insertion and sharing diffusion between separate electrical devices remain future work. Existing taps, guard rings and within-device finger sharing retain their prior qualifications. |
| 7. Post-layout comparison | Fit sheet R, area/edge C and parallel coupling from supplied coupons; residual checks, locked technology identity, sample hashes and named corner profiles. Extraction records its coefficient/corner provenance and compares the same saved specifications. | Supplied example coupons are synthetic. No independently calibrated process data, field solver, cross-layer coupling or device-recognition qualification. |

## Align and distribute

Select complete local objects, then **Layout → Align layout selection…** (or the Align tool-group button).

- Left, right, top, bottom, horizontal center and vertical center alignment.
- A selectable reference edge on the same axis plus a signed offset, in micrometres.
- Equal center spacing or equal edge-to-edge gaps, horizontally or vertically.
- Alignment keeps the first selected group fixed. Distribution sorts by center and keeps the outer groups fixed; reference/offset controls do not affect distribution.
- Complete process footprints, PCells, via stacks and physical instances remain groups. Instance bounds include every array element, rotation, mirror and both array vectors.
- Exact arrangements that would leave the technology grid are rejected before publication. Locked nested layers are checked without expanding every array member.
- **Preserve connections** retargets local Manhattan endpoints and checks terminal/conductor partitions, declared spacing and saved analog/route constraints. Cell ports stay fixed. Unsupported contact changes fail with an explanation.
- **Keep coordinates** moves the selected geometry and associated terminals; surrounding routes remain at their coordinates. This is useful for intentional topology changes and requires verification afterward.

The [KLayout alignment documentation](https://www.klayout.de/doc/manual/object_align.html) describes primary/secondary selection and visible/all-layer instance bounds. Studio uses a first-selected reference and all-layer bounds; it does not reproduce every selection or smart-snapping mode. This build does not establish desktop performance parity with another EDA application.

Run `python scripts/benchmark_alignment.py --out alignment.json`. The same script can read an extracted previous source tree with `--source`. It measures geometry, history transactions, connected alignment and a native KLayout database transform loop. That native loop excludes database creation, selection, validation, history, recovery and display, and is an engine reference only. Timing samples include first-use work. Full GUI recovery is a separate gate, not included in these operation timings.

## Measured behavior on this host

These are the final-source Linux/offscreen samples, compared with an extracted dev5 source tree using the same scripts. They are not native-display or commercial-tool benchmarks.

| Workload | dev5 median | dev6 median |
| --- | ---: | ---: |
| Align 1,000 rectangles, geometry + validation | 442.0 ms | 20.0 ms |
| Align 10,000 rectangles, geometry + validation | 27,094.9 ms | 292.0 ms |
| Align 10,000 rectangles, history transaction | 29,803.9 ms | 497.6 ms |
| Flat 10k pan | 38.9 ms | 26.6 ms |
| Flat 10k zoom | 51.1 ms | 30.8 ms |
| Flat 10k single-shape drag | 36.5 ms | 27.7 ms |
| Array 10k zoom | 58.0 ms | 34.5 ms |
| Whole-array 10k drag | 29.6 ms | 37.2 ms |

Connection-preserving alignment adds topology, clearance and constraint work: 212.4 ms for 1k and 3,053.3 ms for 10k rectangles, excluding history, GUI and recovery. The native KLayout database-only 10k transform reference is 47.1 ms and omits Studio's grouping, validation and history. Full durable GUI timings remain blocked. Cold samples and p95 values are retained in the handoff evidence. Whole-array drag still regresses in this run, and flat zoom p95 is essentially unchanged; there is no uniform speedup or parity claim. Address those limits before increasing scale caps.

## Schematic changes and regeneration

Use **Layout → Review schematic changes in layout…**. The review reports missing and orphan devices without deleting or creating placements automatically. For changed linked process MOS devices, choose whether to preserve attached connections, then inspect the candidate before applying. A changed project invalidates an open review.

Parameter updates preserve origin, recorded orientation, matching geometry-role IDs and terminal IDs. A changed finger count creates new role identities where the geometry's meaning changes. Routes are retargeted only when their endpoint exactly matches an old physical terminal on the same layer. Ambiguous shared endpoints, unrelated owned routing, locked geometry, newly broken terminal partitions and spacing conflicts must be resolved explicitly. Net changes are reported; unrelated route labels are not silently renamed. Manual edits to generated geometry are replaced by regeneration.

New generated records retain orientation through right-angle rotation and mirroring. Old records marked transformed without an orientation cannot be reconstructed safely. The original process assets remain locked. A legacy catalog with an exposed hidden body and an old three-pin artwork order is normalized on the newly created device; the catalog itself is preserved.

## Cursor routing and saved constraints

Choose **Layout → Multilayer routing → Route with cursor…**, enter a net, layers and width, then click the start and destination. Green geometry indicates a direct bend/via candidate clear under declared rules. Red geometry indicates that the direct alternatives are blocked; clicking can still ask the worker to search a detour. The result is reviewed before installation. Escape clears the preview. Changing the active cell, revision or locks invalidates it.

New matched-pair records check current geometric lengths and assigned nets against the saved tolerance. New shield records check both side traces, span, reference net, minimum gap and contact to the saved ground tie. Deletion is a finding. Older route records without shape identity inventories keep their historical behavior. Connected move/stretch/arrange reject newly introduced saved constraints; free geometry edits retain findings for correction. These checks do not establish matched resistance/delay or shielding effectiveness.

## Coupon calibration and comparison

Use **Analysis → Post-layout → Calibrate RC from measurements…** and select a measurement JSON file. Review the fitted coefficients and residual before applying. A separate profile is stored for each named corner. Once profiles exist, extraction requires an exact matching corner; it does not silently substitute nominal estimates. Changing the process lock/layer mapping or tampering with the evidence invalidates the fit. Manual estimate editing is blocked while calibrated profiles are installed.

The input format is illustrated by [rc-coupons-teaching.json](../examples/rc-coupons-teaching.json). It contains **synthetic analytic data**, not measured silicon. Supply your own traceable measurements before treating coefficients as calibrated process data.

Each layer needs at least two resistance coupons, three capacitance coupons with independent area/perimeter ratios and two parallel-coupling coupons. All dimensions are in micrometres, resistance in ohms, capacitance in farads. `source` identifies the measurement/extraction reference, `corner` names the operating/process corner, and `max_relative_error` limits the residual of every coupon (at most 25%).

The fitted model is:

- `R = sheet_ohm × length / width`.
- `Cground = cap_f_per_um2 × area + edge_f_per_um × perimeter`.
- `Ccoupling = coupling_f_per_um × overlap / gap` for same-layer parallel paths.

The fit rejects singular dimensions, nonfinite/negative inputs, negative fitted capacitances and excessive residuals. A low residual only describes the supplied coupons and chosen model; it is not independent validation. RC extraction continues to require flat, connected Manhattan routing, at most 2,000 sections, with ideal pads. The existing before/after comparison uses the same analysis and saved requirements for both implementations. Repeat it at each calibrated/model corner; native process simulation still requires ngspice and matching models.

## Reproduce validation

```sh
python -m unittest discover -s tests -v
python scripts/check_layout_storage.py --out storage-check
python tests/gui_layout_pipeline.py --out gui-pipeline
python tests/gui_layout_priorities.py --out gui-priorities
python tests/gui_layout_performance.py --out gui-performance
python scripts/verify_layout_development.py --out workers --gui
python scripts/benchmark_layout_pipeline.py --out pipeline
python scripts/benchmark_alignment.py --out alignment.json
python scripts/benchmark_layout.py --out viewport.json
python scripts/check_release.py
```

Run the Windows source setup and `benchmark-windows.bat` on a native Windows host. Offscreen Qt results do not qualify installation, platform DPI or native display behavior.

For process acceptance, extract the preserved PDK adapter archive and run:

```sh
python scripts/qualify_layout_process.py --pdk /path/to/sky130A --out process-check \
  --magic /path/to/magic --netgen /path/to/netgen --ngspice /path/to/ngspice
```

The supplied package manifest has revision `72f8bbf4c3ce0df2`, file-inventory hash `bfc52234af448e3b0259d09147d896aef2a38cd4a1f7cd10781fba683c86ef23` and manifest SHA-256 `fda519af05946d1e58623f488bc54a2a58436f6554b3b115fc6b587fb20e1eaa`. Every file is verified before use. Re-indexing with a newer importer can produce a different catalog revision; this driver intentionally uses the shipped locked manifest. It expects nominal acceptance, DRC rejection for narrow metal, and extracted LVS rejection for an open route or changed channel length. Missing tools and storage failures are reported as blocked, never accepted. A fresh qualification result is required for other packages or device families.
