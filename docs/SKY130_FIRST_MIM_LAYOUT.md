# SKY130 first-MiM orientation and contact placement

The first SKY130 MiM capacitor now preserves its width and length when a
rectangular layout is rotated or mirrored. A retained native probe of a
2 × 10 µm capacitor passed at 0 degrees and failed strict LVS at 90 degrees
before this correction. The public model's `rm3 * lc / wc` resistance makes
the distinction electrically significant.

The shared [orientation adapter](SKY130_MIM_ORIENTATION.md) now identifies
`cap_mim_m3_1` through capm (89/44), metal3 (70/20) and via3 (70/44), separately
from the second MiM's masks. Written bottom contacts determine the model axis;
schematic values and generator metadata do not supply extraction dimensions.
Native model identity and position must match the corresponding electrode.
Only W/L tokens change; connectivity and all other native records are retained.

The same qualification exposed a generator defect at 3.005 × 5.005 µm. Contact
placement had bounded the cut's starting coordinate without accounting for its
200 nm width. Certain allowed dimensions therefore placed the far edge too close
to capm and metal4, producing native `capm.4` and `met4.3` violations. The corrected
loop keeps the entire cut inside the existing 300 nm edge margin. Already legal
contact arrays retain their positions. Tests cover all eighty 5 nm offsets in
the 400 nm pitch and both dimension bounds.

The reviewed public `sky130::cap_device` convention, technology and PCell hashes
are unchanged from the orientation guide. Upstream files, coefficients, package
revisions and Apache notices are unchanged. These are application corrections
under the project's existing license, without private technical inputs.

## Local acceptance

The [execution record](validation/sky130-first-mim-2026-10-23.json) binds the
tested sources, original failures, independent audits and retained archive.

- Eight selected sizes/counts pass 64 translated rotations and mirrors: 2×10,
  10×2, 3.005×5.005, 6×30 and 30×6 µm; three and sixteen parallel 2×10 units;
  and a 2×2 square. Native full DRC, strict LVS and the public KLayout checks pass.
- All 47 physical/reference faults are detected. The independent audit verifies
  200 capacitors, 128 stream comparisons and 1,200 evidence bindings.
- Twenty-four electrical conditions compare schematic, extracted and literal
  independent public-model calls, including complex admittance and series
  resistance. Swapped dimensions are detected in all 21 asymmetric conditions.
- Eight mixed-family layouts preserve both models, four distinct terminals and
  perpendicular device orientations. All four deliberately swapped references
  are rejected. A separate audit checks native geometry and unchanged records.
- Four corrupted-output controls fail the independent audit, including native
  and corrected dimensions whose checksums were recomputed.

The validation record distinguishes native Linux checks, the Windows electrical
repeat, source desktop workflows, checked Windows/native receipts and regression
tests. Source-desktop results do not establish installed-release acceptance.

## Reproduction and limits

With the pinned physical adapter and local engines:

```sh
python scripts/qualify_sky130_mim_orientation.py --plate 1 \
  --sky130 /path/to/adapter --magic /path/to/magic --netgen /path/to/netgen \
  --klayout /path/to/klayout --ngspice /path/to/ngspice --output /path/to/new-first-mim
python scripts/audit_sky130_mim_orientation.py --root /path/to/new-first-mim \
  --output /path/to/new-first-mim/audit.json
python scripts/qualify_sky130_mim_mixed.py --sky130 /path/to/adapter \
  --magic /path/to/magic --netgen /path/to/netgen --klayout /path/to/klayout \
  --output /path/to/new-mixed-mim
```

The existing first-plate recipe bounds remain 2–30 µm, a 5 nm grid, aspect ratio
at most 5:1 and 1–16 parallel units. Unsupported shared bottom electrodes,
ambiguous contacts and direct hierarchical native records remain rejected.
The ordinary layout-verification flow uses a private flattened stream.
Distributed RC for rectangular MiM devices remains explicitly blocked.

These finite public-model integration checks do not establish measured RF
accuracy, a complete statistical/operating/reliability envelope, arbitrary
layout acceptance or foundry signoff. No device or chunk status is promoted.
The earlier second-MiM record retains its original source and acceptance scope.
