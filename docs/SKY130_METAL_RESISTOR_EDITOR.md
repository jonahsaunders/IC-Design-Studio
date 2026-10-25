# Editable SKY130 LI and metal resistors

The native editor now generates straight local-interconnect and metal1–metal4
resistors directly from their catalog devices. Previously these five devices
required geometry imported from an external generator. Placement uses the
existing **Generate linked PDK device** preview; changes use the normal
regeneration review and undo history. Saved projects retain their original
package identity.

Choose `res_generic_li.sym` or `res_generic_m1.sym` through
`res_generic_m4.sym`, set W/L, connect the `m` and `p` terminals, and generate
the linked layout. Route each exposed end on its own drawing layer. The
recipe supports one straight resistor, W/L 0.5–10 µm on the 5 nm grid, with
0.5 µm unmarked terminal extensions. These bounds are the editor's supported
recipe, not claimed process operating limits. Contacts, snakes and physical
parallel arrays are separate geometry classes. Unsupported multiplicity or
dimensions are rejected before the design changes.

The marker on datatype 13 sets the primitive width and length. For live
connectivity, the app subtracts the actual marker polygon from its matching
conductor; it does not treat the resistive body as an ideal wire. Removing,
moving or narrowing the marker exposes a short. A bypass outside the marker
also exposes a short, and a terminal inside the body does not count as an end
connection. The original masks remain unchanged in the project and exported
GDS/OASIS. Native DRC and extracted LVS remain required after edits.

Regeneration preserves the two terminal identities and the generated shape
roles. Connected moves retain attached routes and check spacing at the split
terminal geometry. Layer locks are checked again when applying a preview,
including locks changed after the preview was opened.

## Acceptance scope

The [October 25 execution record](validation/sky130-metal-editor-linked-2026-10-25.json)
binds the original native source snapshots, exact packages, independent audits
and separately recorded final source feedback.

The fresh native editor batch covers all five models at six width/length
pairs: 0.5 × 0.5, 2 × 5, 5 × 2, 0.505 × 2.005, 10 × 10 and 10 × 0.5 µm.
The 30 coupons produce 60 orientations at 0°/90°. Each passes save/reopen,
GDS/OASIS round-trip, full native DRC, strict LVS and exact model/terminal/W/L
readback. Five deliberate physical/reference faults per coupon give 150
detected controls. The physical adapter and simulation package are separately
locked; only exported masks and actual stream labels cross that boundary.

The source Qt workflow exercises all five models through preview, a late
layer-lock rejection, apply, undo/redo, resize/regeneration, save/reopen and
model export. These source workflows and the selected native geometry batch
do not establish installed-delivery acceptance or continuous device validity.

The separate [linked electrical contract](qualification/sky130-metal-resistors-linked-v1.json)
defines the four metal models' DC, AC, transient and noise comparisons across
five actual passive sections and selected temperatures. Its electrical
multiplicity of three means three parallel extracted circuits; it does not
qualify a physical resistor array. The existing
[LI contract](SKY130_LI_REQUIREMENTS.md) retains its own scope and unresolved
requirements.

Full operating envelopes, applicable written rules, reliability/current
density, measured/statistical accuracy, additional geometry classes and exact
installed acceptance remain separate. Generic-resistor documentation cautions
against precision analog use. No catalog entry is promoted to fully qualified
by this feature.

Reproduce the native editor batch with `scripts/qualify_sky130_metal_editor.py`
and the source Qt workflow with `tests/gui_sky130_metal_editor.py`.
Use new output directories and the exact locked physical adapter. The normal
source-feedback lane includes the new editor's unit and GUI checks.
