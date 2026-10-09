# GF180 written-metal continuity

`scripts/check_gf180_connectivity.py` checks the written GF180 C/D five-metal
layout against every captured standard-cell supply terminal and top port. It
uses `icstudio/gf180_connectivity.py`, the reusable application checker.

The checker requires the hierarchical source layout, the finished job's
`database.json`, `layout_preview.json` and `result.json`, and independent
9-track cell GDS files. The library's `source-lock.json` identifies its revision,
maps each master through `views[master][".gds"]`, and gives each file's SHA-256
under `files[path]["sha256"]`. Use a library lock authenticated against the
selected PDK revision; a caller-supplied hash alone does not establish provenance.

```sh
python scripts/check_gf180_connectivity.py --gds filled.gds --reference-gds source.gds --database finished/database.json --preview finished/layout_preview.json --result finished/result.json --library-root independent-library --library-lock independent-library/source-lock.json --top counter --variant C --output checks/metal.json
```

The reference and candidate may be the same layout. A separate candidate can
contain fill or flattened hierarchy; terminal locations remain bound to the
captured reference. Existing reports are preserved. Exit 0 means this metal
check passed, exit 1 reports failed continuity. Neither status qualifies the
process or replaces native LVS.

## What is checked

- Database and preview hashes agree with the captured finished job.
- Every captured standard-cell instance appears at its exact placement and
  orientation. Independent cell masks match the reference layout.
- Each cell's VDD and VSS points come from the independently hashed library,
  transformed by its captured placement. Missing supplies, duplicate instance
  names, unknown cell masters and unsupported orientations are rejected.
- Written signal-port labels match the complete captured port set and positions.
  Supply anchors may use another location on the same rail; that location must
  connect physically to the corresponding written port.
- Metal1 through Metal5, their dummy-metal shapes and all four intervening via
  layers form the network. Text cannot join disconnected shapes. Distinct top
  ports must remain separate, and every cell supply must reach its matching port.
- All extraction diagnostics are retained and prevent a pass. Input identities
  are retained; changed capture sources are rejected before candidate inspection.

The current supported placements are R0, MX, MY and R180 in the 9-track library.
The source layout must have one declared top cell on the 1 nm database grid.
Six-metal layouts, other device libraries and uncounted device hierarchy are
rejected. Hierarchical metal/via stream-out cells are allowed.

## Evidence and remaining integration

The [module checkpoint](validation/gf180-metal-module-2026-10-09.json) records
six actual C/D counter, UART and APB layouts on Windows and Linux. On each OS,
the checker reproduces all thirty retained physical controls and derives all
33,184 supply points from 16,592 captured placements. Supply opens and signal
shorts fail; substrate-only contact removal remains a passing metal control
and therefore demonstrates the need for the separate device/substrate check.

Use this check together with the [strict GF180 LVS recipe](GF180_LVS_RECIPE.md).
The command is available from the source checkout; automatic finished-job
dispatch, combined acceptance and fresh installed-runtime verification remain
pending. Full fill coverage and post-fill electrical/timing acceptance remain
open in [chunk 4](PDK_QUALIFICATION_PLAN.md). No tapeout acceptance is claimed.
