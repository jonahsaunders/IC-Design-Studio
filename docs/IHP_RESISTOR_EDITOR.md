# Selected IHP resistor editor and native verification

The linked device-layout action supports the public IHP `rsil`, `rppd` and
`rhigh` straight resistors at five exact W/L pairs: 0.5/0.5, 0.5/20, 20/0.5,
2/7 and 7/2 micrometres. Select the schematic resistor and choose **Generate
PDK device layout**. Metal1 is the default terminal access; Metal2 adds Via1
and the source-rule-derived landing at both resistor terminals. The independent
body terminal stays on Metal1. The selected recipe requires one unit and zero
bends; unsupported dimensions are rejected before changing the layout.

Generated shapes remain editable. The saved footprint records its exact model,
dimensions, access option, package, public generator and template identities.
Changing the schematic or terminal-access option marks it stale; reviewed
regeneration preserves placement and rotation. Undo/redo and old projects
retain their geometry and connections. Verification still needs actual cell
ports and a saved schematic reference.

The pinned templates preserve the original public generator masks, with only
the separately specified [Metal2 landing and access changes](IHP_RESISTOR_TERMINAL_VIAS.md).
Their original Apache-2.0 license, upstream lock and derivation record are
distributed alongside them. A changed or missing source, template, manifest or
catalog binding is rejected. Registry installation may format `package.json`
differently; identity checks compare its strict canonical content and locked
file hashes, while retaining the actual manifest-byte hash separately.

Native staging carries the authenticated recipe assets and the matching package
manifest. For layout-versus-schematic comparison, the three pinned public
resistor symbols omit the statistical `mm_ok` selector from their LVS format.
The application follows that format only for one literal Boolean selector on
the exact three-terminal X-device binding. The original simulation schematic
remains unchanged and is retained alongside the derived physical reference and
per-instance source proof. Dimensions, model, body node, multiplicity, bends,
unknown parameters and nonliteral or duplicate selectors are not discarded.
This does not establish statistical equivalence. The upstream comparison deck
also discards bends; the selected recipe and independent gate enforce zero
bends explicitly rather than claiming native bend-error detection.

The source GUI producer exercises 60 combinations: three models, five size
pairs, two terminal-access choices and two rotations. It installs the actual
package through the registry, places catalog devices, saves and reopens twice,
exports GDS and OASIS, and checks legacy recovery, unsupported-size rejection
and rotated Metal2-to-Metal1 regeneration. Source feedback runs all 60 cases and
checks the complete inventory after the child exits.

The independent installed gate requires the exact Git candidate, frozen
executable and shipped resources. It validates actual saved parameters, masks,
ports and exports, then starts 60 fresh native positives and 165 deliberately
faulty jobs through that executable's managed worker. It reads actual DRC,
extraction and unique-LVS results, verifies opened terminals/body and shorted
interfaces, and checks runtime and evidence identities before and after the
run. Source results cannot satisfy this frozen gate. Both desktop release
paths retain the complete gate output and failure receipts.

Current execution evidence is separated in the
[IHP editor record](validation/ihp-resistor-editor-2026-10-28.json).
Fresh exact-candidate installed acceptance is pending. These finite straight
recipes do not cover continuous size domains, snake/array shapes, guard vias,
alternate isolation, operating/statistical/reliability envelopes, or complete
family qualification. The chunk-7 completion gate is unchanged.
