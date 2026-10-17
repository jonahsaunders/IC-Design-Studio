# Source-listed alternate electrical models

New bundled projects expose the available choices listed by the pinned public
SKY130 and GF180 source symbols. Each choice has its own catalog identity and
model name. Saved projects retain their original package revision. All original
symbols, model files and license notices remain byte-for-byte unchanged.

The [execution record](validation/alternate-models-2026-10-17.json) accounts for
all 52 declarations: five existing default views, 44 added usable views and three
explicitly unavailable choices. This completes the adapter/execution work for
these declarations, not the complete upstream model inventory or chunk 7.

| Package | Added usable views | Added unavailable views | Revision |
| --- | ---: | ---: | --- |
| SKY130A | 14 diode and 8 fixed VPP views | 3 | `3e3cdb6aecf49063` |
| GF180MCU C | 11 MIM views | 0 | `bcc631ec5c59d6b6` |
| GF180MCU D | 11 MIM views | 0 | `ab8d6cd6e79d2f4b` |

IHP has no alternate declarations in its bundled symbols; its revision remains
`1e24ec25b491028b`. The catalog now has 302 entries: 279 usable and 23 unavailable.
Four SKY130 diode views share models with another symbol view. A view count is
not a count of distinct physical devices.

## Selecting and reproducing a choice

Create a project with the current bundled PDK and search the component library
for the complete model name. For an existing project, install/select the new
package explicitly and review device migration. Existing identities are never
silently rebound. The unavailable entries explain their missing definitions;
the application does not substitute another model.

```sh
python scripts/prepare_default_device_packages.py --output /path/to/new-packages
python scripts/prepare_alternate_models.py --input icstudio/assets/pdks/sky130A --output /path/to/new-sky130-package
python scripts/qualify_alternate_models.py --output /path/to/new-results --ngspice /path/to/ngspice --workers 4
```

The qualifier can reuse prepared packages with `--packages /path/to/packages`.
Use `--pilot` for nominal 27 C checks or `--targets sky130A --families diode`
for the diode sweep. Output directories must be new. Exact retained manifests
allow earlier qualification recipes and the current defaults to rebuild without
duplicating or modifying upstream model assets.

## Terminal, parameter and simulator contracts

SKY130 primitive diodes retain anode/cathode order. Eleven reviewed public
level-3 models use the source symbols' legacy area convention. The application
now declares that convention for every supported choice and adapts only the
temporary simulator deck according to an executable behavior probe. This fixes
the reproduced alternate-diode failure on newer ngspice. It does not change
saved parameter values or model bytes, infer units from parameter magnitude, or
enable the two missing RF models.

The eight additional fixed VPP models use source order `c0 c1 b m4` or
`c0 c1 b m5`. The catalog maps those terminals to `c0 c1 sub top`; `top` is the
specific model's M4 or M5 shield. W/L controls remain absent because these are
fixed layouts. Positive `mult` retains the source model's subcircuit multiplier
and statistical parameter semantics.

GF180 MIM choices retain source terminals `1 2`, width/length in metres and
multiplicity. Their names identify density and metal pair. Availability in the
simulation library does not establish fabrication compatibility with the C/D
metal option, a matching layout generator or extracted equivalence.

The missing SKY130 choices are `model__parasitic__rf_diode_ps2nw`,
`model__parasitic__rf_diode_pw2dn` and
`cap_vpp_11p3x11p8_l1m1m2m3m4_shieldm5` (each with the `sky130_fd_pr__` prefix).
Their absence is checked across every selectable include section.

## Recorded execution and limits

Linux passes 144 capacitor cases and nine diode cases. Native Windows passes
eight capacitor cases at nominal 27 C and nine diode cases. Independent calls
exercise all terminals, selected geometry/multiplicity, three requested process
corners and 0/27/85 C where the full matrix is run. Capacitor frequencies span
100 Hz–10 MHz; diode voltage sweeps span -0.2–0.8 V. These are selected integration
points, not complete model operating envelopes or RF accuracy claims.

The accepted cases compare 5,064 device instances, 12,560 terminal vectors and
341,680 samples. All 10,128 deliberately faulted instances are detected. Raw
readback independently checks all 680 output files. All 47 added interfaces
pass save/reopen/export checks or their expected unavailable-model rejection on
both hosts. Forty-eight focused regression tests pass on each host, including
exact package reproduction and preservation of saved revisions.

Source-desktop checks on both hosts place and reopen all 44 usable views,
inspect fixed VPP controls and reject all three missing models. These checks
use isolated settings and offscreen rendering; installed-binary and normal
display acceptance remain separate.

The complete Linux regression run discovered 3,003 tests: 2,970 passed,
31 skipped and two failed because of the isolated test setup. The relocation
test copied a launcher without its sibling executable; all five path tests
pass with the actual executable. The evidence test required Git metadata
absent from the source snapshot; all eight evidence tests pass against the
repository. The original failed run and both passing reruns are retained.

The original Linux pilot diode failure is retained. The first full run also
retains three failed cold-diode sanity checks: its arbitrary 100 nA minimum was
inappropriate for those public models. The final check requires measurable
forward conduction above 100 times the comparison floor and rectification;
the application/reference tolerances and fault thresholds are unchanged. All
nine diode cases were rerun on each host. The passing 144 capacitor cases keep
their original source/report identity and are not counted twice.

No full operating-range, statistical, noise, RF-band, physical/extracted,
metal-option or installed-executable qualification follows from this batch.
The broader chunk-7 requirements remain recorded in the
[qualification plan](PDK_QUALIFICATION_PLAN.md).
