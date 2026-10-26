# Corrected SKY130 native ESD simulation binding

The public Xschem [correction at 08367118](https://github.com/StefanSchippers/xschem_sky130/commit/08367118f8ad7311b9264b856fb4d5f1f58b45f9)
changes `nfet_g5v0d10v5_nvt_esd.sym` to the published
`sky130_fd_pr__esd_nfet_05v0_nvt` model, with default W=10 µm and L=2 µm.
Studio can build a separate package containing that corrected binding. This is
an explicit source correction, not an invented alias for the missing legacy
model or evidence of a 10.5 V operating rating.

Build the package from the reviewed bundled SKY130 revision:

```text
python scripts/prepare_sky130_esd_nvt.py --output build/sky130-esd-nvt/sky130A
```

Import its `package.json` through Studio's PDK manager, then explicitly choose
that revision for a new project. The bundled default and previously saved
projects keep their existing revisions. Existing projects do not silently gain
this corrected model. The candidate manifest is
`5315d2d6ad7618047eeeb48a15f81f221e6f42864647208acfb65124ee5c9c7a`
and its revision is `ac43172dd991a7a5`.

The binding preserves ordered drain/gate/source/body terminals and the source
symbol's `m`/`mult` convention and junction equations. It accepts W=10 µm,
nf=1, and the three explicit source-bin centers L=0.9, 2, or 4 µm. Other W/L/nf
values are rejected. Positive electrical multiplicity remains a source
parameter; the selected integration cases exercise 1 and 3. These discrete
geometry constraints describe this adapter, not a continuous process envelope.

The original model comes from
[the public SKY130 primitive repository at 16f93a79](https://github.com/fossi-foundation/skywater-pdk-libs-sky130_fd_pr/blob/16f93a795d87ea2b393fe5c74d32674e111e44a2/cells/esd_nfet_05v0_nvt/sky130_fd_pr__esd_nfet_05v0_nvt.pm3.spice).
Its equations are unchanged. The corrected symbol, prior symbol, upstream
example, source identities, copyright headers and both Apache-2.0 license texts
are retained under `icstudio/assets/qualification/sky130-esd-nvt-source-v1/`.
All previous package assets and unrelated catalog bindings remain byte-identical.

The selected electrical protocol compares actual saved/reopened Studio circuits
with independently written four-terminal model calls. It checks signed DC
currents and complex AC currents, all terminal voltages, current conservation,
and actual wrong-multiplicity/gate/body/length simulations. The selected scope
is five ordinary model sections at 0/27/85 °C for a 0–1.2 V gate sweep with
drain=0.6 V, source=0 V and body=−0.15 V, plus four independent terminal AC
excitations at nominal/27 °C. These temperatures and biases are integration
points, not published device limits.

The version-2 evidence protocol binds each actual command, unique circuit title,
execution directory, simulator, deck, raw output and log before and after each
run. Independent readback requires externally retained report and complete
manifest hashes, the original source snapshot, and every selected case. The
earlier exploratory protocol and failed attempts retain their original scope.

This work does not qualify an ESD protection rating, reliability or latch-up,
a physical ESD layout, measured-model accuracy, a complete device family, or
manufacturing signoff. The six unavailable bindings in the bundled default are
unchanged by an opt-in package.

The [retained selected acceptance](validation/sky130-esd-nvt-source-2026-10-26.json)
passes on Windows46 and Linux42: 19 contexts and 98 actual executions per host,
with independent four-terminal raw readback and all 12 rehashed corruption
controls rejected. It uses the recorded original source snapshot plus the
numeric-choice correction; later integrated source checks remain distinct.

```text
python scripts/qualify_sky130_esd_nvt.py --repo REVIEWED_SOURCE --package CANDIDATE --ngspice PINNED_ENGINE --output NEW_EVIDENCE
python scripts/audit_sky130_esd_nvt.py --repo ORIGINAL_SOURCE --package CANDIDATE --runner ORIGINAL_PRODUCER --evidence CAPTURE --expected-report-sha256 TRUSTED_REPORT_SHA --expected-manifest-sha256 TRUSTED_MANIFEST_SHA --output NEW_AUDIT
```
