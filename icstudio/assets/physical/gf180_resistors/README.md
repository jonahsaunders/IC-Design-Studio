# Pinned public GF180 resistor generators

These six source/license files are unmodified files from open-pdks commit
`aa3fc215a80d32437b8cca1cb3fdee819d18c4c9`. Their Apache-2.0 license, original
headers, paths and hashes are retained in `LICENSE` and `upstream-lock.json`.
The Makefile and startup file record the C/D variant flags and 5 nm grid.

`scripts/qualify_gf180_resistor_layouts.py` preprocesses the original generator
and common Tcl dependency. A separately recorded invocation adds explicit
contact enclosure on both axes, guard-ring clearance, reduced contact coverage
and a fixed placement seed. Those are local geometry changes; no DRC, extraction,
LVS, model or upstream source bytes are changed. The original generator's failed
physical checks must not be represented as a passing upstream result.

The qualification recipe is project code under GPL-3.0. These upstream files
retain their separate Apache-2.0 license.
