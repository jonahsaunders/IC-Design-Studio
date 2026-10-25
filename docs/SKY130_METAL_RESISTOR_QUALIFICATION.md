# SKY130 local-interconnect and metal resistors

The October 25 [native editor and linked electrical milestone](SKY130_METAL_RESISTOR_EDITOR.md)
adds direct placement/regeneration for all five models and independently
audited M1–M4 DC/AC/transient/noise linkage. The earlier records below retain
their original LI-only electrical scope and separate physical evidence.

The [retained execution record](validation/sky130-li-metal-resistors-2026-10-17.json)
contains 72 electrical analysis comparisons on Windows/Linux, 864 detected
faulted instances, 60 legal physical layouts and 150 detected layout/reference
faults. Independent readback checks all 216 simulator outputs and 210 native
netlists. Thirty-one focused and 29 default-package/matrix tests pass per host;
source-desktop placement and save/reopen also pass on both hosts.

The local-interconnect symbol is now bound to the existing public
`sky130_fd_pr__res_generic_l1` model. Its source spelling, `res_generic_li`,
previously left the device unavailable. The correction verifies the exact
symbol and model hashes; it does not change equations, dimensions or model
files. The [public device documentation](https://skywater-pdk.readthedocs.io/en/main/rules/device-details.html#generic-resistors)
identifies `l1` as local interconnect, separately from the metal-1 model.
Original source bytes and Apache notices remain intact.

The simulation package has a new immutable identity. Existing saved projects
retain their package revision, and the preceding manifest remains available
for reproducing earlier qualification recipes. New folder registrations apply
the same source-checked mapping. Unrecognized source changes remain unavailable
until reviewed.

`scripts/qualify_sky130_li.py` compares application-generated circuits with
independent manual model calls. Six width/length pairs and multiplicities 1/3
exercise DC, complex AC and transient responses. Noise is checked on the
0.17-by-10 micrometre single resistor with a 1 kohm/1 pF load. Nominal, slow and
fast process selections run at -40, 27 and 125 C. These are finite electrical
test selections, not physical legality or continuous operating limits. Every
isolated device must detect changed width, changed multiplicity, a disconnected
terminal and substitution of the metal-1 model. An independent raw-file audit
also checks DC resistance scaling, analytical RC-divider gain and Johnson noise.

`scripts/qualify_sky130_metal_resistor_layouts.py` uses the separately locked
physical adapter identified by `examples/sky130-qualification-lock.json`.
Its revision is distinct from the simulation package. The unmodified public
Magic generators produce single straight LI and metal-1 through metal-4
resistors. Native full-style DRC and strict LVS run on two rotations of each
of six geometries per family. Native save/reopen, independent GDS/OASIS
exchange, exact resistor model, terminal connectivity and numerical micrometre
dimensions are checked. Each geometry has two physical faults and three
schematic-reference faults; failures must come from actual connectivity or
property evidence, not a failed tool invocation.

The physical LI square uses 0.29 micrometres. The public generator's 0.17
micrometre default is narrower than ordinary rule li.7; the
[public rule table](https://skywater-pdk.readthedocs.io/en/main/rules/periphery.html#li)
allows the smaller width only in a stated special context. No exemption marker
is added. Generation uses a 5 nm internal grid so half-width coordinates do not
round a requested 0.29 micrometre rectangle to 0.30. The earlier illegal 0.17
case and the earlier reference-unit mismatch are retained as failed evidence.

This batch does not qualify resistor snakes or arrays, arbitrary layouts,
continuous geometry or temperature ranges, silicon-model accuracy, full-chip
antenna/density, electromigration, RF/statistical behavior or the final installed
release. The 0.17 micrometre electrical test points do not establish layout
legality. Chunk 7 remains incomplete.
