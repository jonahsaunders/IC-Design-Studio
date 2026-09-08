# Continue from IC Design Studio 0.13.0

Baseline: 0.12 commit b27b4d931cff1d72fa07d389f8d99c529d4d2930. Read the Update
guide, capability ledger and verification/RELEASE-RESULTS.json. Preserve the
native Python/PySide6 application, schema 1, History transactions, object/pin
identities, immutable PDK locks and independent verification gates.

New modules:
- interface_update.py: read-only candidate planning, stable explicit old→new
  mapping, per-instance added connections, physical interfaces/labels, bench
  impact/removal handling and revision/candidate hashes checked at Apply.
- interface_ui.py: complete native review, explicit Disconnect, connection and
  port tables, stale-input invalidation and single transaction application.
- electrical_rules.py: saved policy, scope, hierarchy occurrence paths, primitive
  topology, optional terminals, direction/scalar-bus and physical-port checks.
- cross_probe.py: occurrence identities, placement/terminal status and root-net
  propagation through actual pin mappings rather than coincidental names.
- consistency_workspace.py: first MRO mixin; native review/policy/cross-probe
  dialogs, finding navigation, overlap selection and compact active controls.

Existing code extended: symbol editor dropdown metadata, required pins, initial
fit, vector drawing cache; symbol_io required-pin exchange; wire topology and
hover indexes; layout painter caches; hierarchy render cache preserves cached
schematic symbols; active-cell-only, grid-deduplicated capture previews. The
public model.erc/CLI entry point now uses the same electrical policy as the GUI.
Studio.connect and Studio.move retain their explicit legacy dispatch aliases.

Contracts to preserve:
Interface planning clones the project and validates the full candidate without
mutating the input. Apply rejects both a changed base and a tampered candidate.
Use capture_commit/History for atomic undo. A QDialog completion callback must
not shadow QDialog.done (the review uses on_applied). SymbolEditor callbacks
returning False keep its window open until review completion. A stale cell
symbol editor must be reopened; unrelated project changes can refresh review.

Renames preserve external parent net names while changing child net names,
anchors, port labels, cached instance symbols and generated-record net metadata.
Do not refresh the rest of a PDK specification: stale dimensions must still fail
PDK.STALE. Removed pins leave parent wire/label stubs and internal child circuits.
Blank added connections remain unconnected. No implicit ground and no many-to-one
terminal mapping. The last 20 receipts are saved; existing result hashes go stale.
Only invalid bench probes and dependent measurements may be removed after the
explicit review option; removing every probe remains invalid.

Wires connect at endpoints, vertices, pins and explicit junctions, not bare
crossings. Indexed queries retain on_segment floating tolerance. Geometry caches
hold strong references to bounded immutable array snapshots; commits and undo
replace arrays. Never mutate cached geometry in place without invalidating it.
SymbolPad.notify invalidates its vector picture after artwork edits. Optional
terminal metadata survives .sym exchange; scripts remain non-executable data.
Cross-probe rows carry stable ID paths as well as readable instance names. They
open shared cell definitions; physical guidance is local contact checking, not
extracted recognition or automatic routing. The list is revision-bound.

Reproduce with unittest discovery, tests/gui_consistency.py --output … --ngspice
/absolute/path, tests/gui_interface_process.py with explicit PDK/engine paths,
tests/gui_capture.py, the two performance drivers and existing GUI suites.
The same performance driver can point --source-root at the prior source. The
baseline report and final workloads retain exact measured values separately.

Build with scripts/package.py; it calculates the actual workflow hash. Run the
packaged --release-test at 100%/200% with real ICSTUDIO_PROBE_* paths. Historical
reports keep their original version/scope. Fresh extraction is not fresh OS
qualification. Do not fill the desktop/user acceptance template without actual
sessions. Source, executable, workflow, PDK and recovery hashes are verified.
