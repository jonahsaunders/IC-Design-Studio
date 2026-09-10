# The path forward

Our goal is an independent open design environment that makes circuit intent, experiments and physical implementation easy to follow. Compatibility with Xschem, ngspice, KLayout, Magic and Netgen remains part of that direction. This roadmap expresses priorities and acceptance criteria, not promised delivery dates.

## Foundation already available

The current application has native schematic/layout editing, visible grids, reusable cells, saved simulation setups, run tables, waveform markers and calculations, specifications, parameter studies, reviewed Xschem migration/exchange, locked PDK adapters, linked physical geometry and external verification entry points. Version 0.21 adds guided examples and a PDK setup assistant. See [release notes](RELEASE_0.21.md) for what has actually been tested.

## 1. Make releases dependable

**Next priority.** Run fresh-machine acceptance on Windows and Linux, including import, first simulation, save/reopen, model paths with spaces, cancellation, recovery and upgrade settings. Add signed Windows distributions when signing infrastructure is available. Qualify scaling, keyboard navigation, screen-reader names, text contrast and the macOS source workflow.

**Done when:** each advertised platform has a reproducible install-to-result test and attached evidence. “Built” and “executed successfully” are separate release states.

## 2. Make native design a strong destination

Progress in [0.21.1.dev1](UPDATE_0.21.1.md): a small parameterized hierarchy now covers repeated connected moves, exact undo/redo, stable identities and reviewed exchange after source removal. Exported ports reuse their own net labels, avoiding collisions with other nets and repeated label growth. Broader editing and exchange qualification remains open.

Expand parameterized hierarchy, bus editing, symbol authoring and supported model expressions. Improve connection-preserving move/stretch behavior on dense designs, with previews and predictable undo. Broaden migration fixtures across common open libraries, and improve the review of unsupported constructs.

**Done when:** a representative hierarchical project can be imported, migrated, edited, exported, reimported and compared without unexplained topology or parameter changes. Native projects remain usable without Xschem installed.

## 3. Make each PDK workflow reproducible

Add managed, pinned downloads with progress, interruption/retry, storage estimates and revision rollback. Expand model and symbol adapters, guided OSDI provisioning, device-family smoke circuits and corner evidence. Make PDK capabilities searchable and pair physical recipes with matching extraction/rule decks.

**Done when:** every advertised process/device subset lists its model revision, tested engine build, representative circuit results, physical support and known exclusions. Registration alone never becomes a “qualified” badge.

## 4. Close the electrical–physical loop

Progress in [0.22.0.dev1](UPDATE_0.22.md): connected translation/stretching with physical component guards, queued multilayer route proposals with vias, bounded length tuning and shields, a declarative PCell library, and captured relative KLayout rule dependencies. New geometry is traced to design and technology inputs. Broader process device qualification and calibrated hierarchical extraction remain open.

Extend parametric device coverage and routing feedback. Improve hierarchical extraction, calibrated resistance/capacitance, coupling support, DRC/LVS cross-probing and review of stale physical links. Build process-specific tests around reusable blocks rather than isolated shapes.

**Done when:** a declared process flow can trace a schematic change through regenerated geometry, verification, extraction and before/after specification results with reproducible inputs.

## 5. Deepen experiments and reporting

Build beyond the current finite-difference sensitivity and bounded sampled search: richer optimization strategies, reusable expressions, statistical summaries, correlation/yield views, multi-run reports and efficient waveform retention. Extend convergence diagnostics and run scheduling. Advanced periodic, harmonic-balance and RF analyses need engine support, explicit semantics and reference circuits; they are future work.

**Done when:** every new analysis has a numerical reference, a clear failure state, progress/cancellation behavior and saved inputs that reproduce the result.

## 6. Scale and collaborate

Progress in [0.22.0.dev1](UPDATE_0.22.md): hierarchical file XOR by layer/datatype, exact area summaries, saved reference snapshots, geometry queries, tiled density and bounded fill/rounding. A reproducible 10,000-square GDS/OASIS workload checks the comparison path. This does not establish large-layout interactive viewport performance.

Profile large schematics, geometry and waveform sets. Introduce measured rendering/indexing improvements, reusable project libraries and reviewable project diffs. Improve plugin/adapter boundaries and regression automation. Evaluate remote workers and team collaboration only after the local document and job model are reliable.

**Done when:** published workload definitions and measured responsiveness justify the supported scale. Collaboration preserves revision identity, result provenance and recoverable edits.

## How to help

Small real examples are especially useful: a wire move that breaks a net, a symbol that cannot migrate, a model corner that fails, or a layout finding that is hard to locate. Open a focused issue using the repository templates. Proposals should describe the user's task, the expected behavior and a minimal acceptance example. See [CONTRIBUTING.md](../CONTRIBUTING.md).
