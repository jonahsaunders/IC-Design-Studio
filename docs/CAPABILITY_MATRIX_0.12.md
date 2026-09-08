# 0.12 capture capability ledger

| Area | Implemented in 0.12 | Boundary / follow-up |
|---|---|---|
| Familiar commands | Editable schematic and symbol profiles; canvas-only keys; configurable Ctrl-drag and Alt-right cut | Inspired presets, not exact vendor emulation; middle pan and wheel zoom are fixed |
| Schematic editing | Reference move/stretch/copy, preview/cancel, wire cut/rejoin, bulk parameters | Manhattan stored wires; labelled nets remain intentionally connected by name |
| Placement | Persistent searchable browser, vector preview, repeated placement, rotation/mirror | One device model per placement sequence; no arbitrary external library browser |
| Hierarchy | Enter schematic/symbol, return parent viewport, make cell from circuitry | Shared-cell edits; physical and saved-DUT extraction constraints are guarded |
| Symbol artwork | Multiselect, marquee, copy/rotate/mirror, align/distribute, endpoint handles, polygons/arcs, styled text | 1,000 primitives and ±500-unit coordinates; no arbitrary executable graphics |
| Electrical definition | Stable pin IDs, directions/roles/bus metadata, order, coordinates, visibility, dynamic labels | Scalar bus membership; connected deletion and protected physical/bench renaming require reconciliation |
| Consistency | Check and Save, active ERC, interface/order/overlap/unused/output-driver findings, clickable cell navigation | Does not establish analog, digital timing, LVS or foundry signoff |
| Xschem exchange | Declarative symbol metadata/styles, dynamic tokens, mirror-aware schematic package exchange | Generated package lock remains enforced; import changed .sym files through symbol editor |
| Layout and analog | Existing 0.11 layout workspace and 0.10 process/analog workflows retained | See CAPABILITY_MATRIX_0.11.md for physical capability limits |
| Distribution | Complete source, Linux x86_64 bundle, examples, locks, evidence and continuation patch | No newly qualified Windows installer or fresh-OS qualification |

Acceptance details and historical scope are explicit in the final handoff matrix.
