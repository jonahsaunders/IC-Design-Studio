# SKY130 thick-oxide and native MOS layouts

The generator accepts the ordinary and per-finger four-terminal views of
`nfet_g5v0d10v5`, `pfet_g5v0d10v5`, `nfet_03v3_nvt` and `nfet_05v0_nvt`.
Use the existing generated-layout review, regeneration and save/reopen actions.
The process readout adapter authenticates the exact public model and its
internal transistor wiring before collecting operating-point results.

HVI encloses NMOS active and body taps by 180 nm; for PMOS it matches NWell.
HVNTM encloses NMOS active by 185 nm. Native devices retain LVTN, and the 3.3 V
native model retains Magic's 81/60 identification marker. That marker is an
existing extraction identifier, not an additional fabrication mask. The public
rule tables, layer map, Apache-2.0 license and exact identities are retained in
[the source lock](qualification/sky130-voltage-sources-v1/source-lock.json).
The project and bundled model licenses are unchanged.

Native recipes accept only the nine 3.3 V and eleven 5 V nominal per-finger W/L
centers in the locked public model bins. They do not imply continuous geometry
qualification between those centers. The 25 µm native model requires one finger
and has a second contacted body tap with a real metal connection to the original
body terminal. Separate parallel copies retain the existing generator semantics.
Other generated dimensions retain the 5 nm grid and existing finger/copy bounds;
unsupported models and missing required process layers fail before generation.

## Verified physical batch

The [execution record](validation/sky130-voltage-layouts-2026-10-22.json)
binds the full final local run to its exact source. It covers 32 configurations
and four rotations:

| Check | Result |
| --- | --- |
| Native full Magic DRC, strict Netgen comparison and public KLayout block DRC | 128 layouts pass |
| Missing oxide/native identity, open contacts and wrong reference dimensions/terminals | All 257 controls detected, including the long-channel tap-distance fault |
| Independent saved-stream and native-netlist readback on each host | 128 layouts, 272 channels, 256 stream comparisons, 385 report bindings and 3,465 artifact bindings verified |
| Source tests and editor workflows | 66 tests and all eight source desktop views pass on each host |
| Windows staging and local native backend | Four valid layouts and four damaged-oxide controls pass their expected outcomes; 192 returned files verified |

The native reader verifies the exact model, four terminal roles, channel length
and summed width across fingers and parallel copies. GDS/OASIS exchange keeps
the physical geometry. Removing the second long-channel tap recreates Magic's
LU.2 failure while extraction and LVS still complete successfully; a tool crash
cannot satisfy this negative control. Missing HVNTM is not claimed as a proven
failure control because the locked extraction technology derives that layer.

The first full run passed 31 configurations and failed the 25 µm native model's
substrate-tap distance check. The original geometry and failed evidence are
retained. The fix adds the contact stack and body rail without weakening the
rule deck, comparison criteria or fault requirements.

An 81.9 MB deduplicated archive preserves 3.06 GB of logical source and evidence,
including failed attempts. All object hashes pass verification. Restoring 2,359
source and physical-input files reproduces the four-model pilot and 31 controls.
The first readout-test fixture used an invalid 0.5 µm length for the 5 V native
model; its genuine simulator rejection is retained. The corrected test preserves
the selected model length and compares all eight real ordinary/per-finger
operating readouts on each host.

## Reproduction and scope

Prepare the physical adapter with `prepare_sky130_qualification.py`, then use
the pinned local engines:

```sh
python scripts/qualify_sky130_voltage_layouts.py --sky130 /path/to/physical-adapter/sky130A --magic /path/to/magic --netgen /path/to/netgen --klayout /path/to/klayout --output /path/to/new-results --workers 2
python tests/gui_sky130_voltage.py --out /path/to/new-desktop-results
```

`--pilot` selects one nominal configuration per model, giving four layouts and
31 fault controls. The full run additionally covers all native nominal centers,
multifinger/copy cases and the 25 µm tap regression. Physical CI runs the pilot;
desktop CI runs all eight editor views. Configuring CI is not evidence that the
new revision has passed it.

This is sampled physical and connectivity support. Complete operating ranges,
reliability, statistical/RF accuracy, remaining device classes and upstream
process options still require qualification. Three-terminal views and 16 V/20 V
extended-drain recipes are outside this addition. Seven required real-device
bindings remain unavailable; the 286 available catalog entries remain partial.
Chunk 7 and complete-chip tapeout qualification remain open.
