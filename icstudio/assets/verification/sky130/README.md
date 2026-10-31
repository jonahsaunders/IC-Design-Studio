# Generic SKY130 geometry reference

`sky130A_mr.drc` is copied without modification from
[ChipFoundry cf-precheck](https://github.com/chipfoundry/cf-precheck/blob/6c401ed5134a6466c7eed3e5524ebaacad4cea2a/src/cf_precheck/drc_scripts/sky130A_mr.drc).
Its explicit GPLv3 header governs this file; `GPL-3.0.txt` retains that license.
Original headers and notices are unchanged. The surrounding application remains
GPL-3.0-or-later. The source is also retained in the public-deck regression fixture.

Source SHA-256: `aeba6ab5137923f2258714ab5d91ce99ca6a6f932bea55dedfe6f79aca697ba1`.
Git blob: `3f9420347b04ab1c1e9929af2167d03c7ebcf76c`.
Release reported by the deck: `2026.03.30_01.00`.

`categories.json` records the 255 categories emitted by the pinned native deck
with FEOL, BEOL and off-grid enabled and the other options explicitly set by
`digital_sky130_native.py`. It detects incomplete native report output. Category
counts are not a claim of complete foundry rule coverage.

This application stage imposes no shuttle names, tile dimensions, pin interface
or reserved metal layer. The AL backend in the unmodified source is the supported
backend for this stage. Seal and floating-metal options are explicitly false;
complete-chip/seal and connectivity qualification remain separate. The source's
built-in cell filters remain visible and SRAM_EXCLUDE is false. All invoked
options, source, license, native report and final-layout identity are exported.

The nonempty 1.8 V MOS controls demonstrate a specific limitation: removing
NSDM from an NMOS, or PSDM from a PMOS, can still produce zero native markers.
Studio's separate drawn-implant profile detects these faults. This native check
supplements that profile; it cannot replace the drawn-mask or electrical checks.
