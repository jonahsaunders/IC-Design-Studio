# GF180 finished-layout connectivity

Configured GF180 C/D finish jobs now generate the independent circuit reference,
run the captured native LVS recipe, and check the actual written metal before
accepting connectivity. Both checks must pass. The result remains explicitly
unqualified for complete fill, extracted performance, process corners and tapeout.

## Inputs and acceptance

The [complete profile preparer](GF180_CONNECTIVITY_PROFILE.md) captures all 229
independent 9-track CDL/GDS pairs and the 32 prepared rule and attribution files.
It attaches matching `lvs_reference` and `gf180_connectivity` policies to the
5LM C/9K or D/11K profile. The policies and captured file hashes participate in
the finished-job identity. Missing cells, changed rules, mismatched stacks and
incomplete evidence are rejected.

Native verification removes child text labels in a separate layout copy while
requiring every physical mask and top-level label to remain identical. Readback
checks the complete native circuit, bijective net mapping, every device terminal,
MOS width/length and diode area/perimeter. Native extraction diagnostics block
acceptance. The [written-metal check](GF180_METAL_CONTINUITY.md) independently
checks the full port set and every placed-cell supply connection.

The saved result includes both reports, the native comparison database, the
verification layout, the independent reference and library views, exact rules,
commands and source bindings. Reopening a result reconstructs the checks from
those artifacts. Engine-local metal identifiers are replaced with deterministic
identifiers that preserve the complete observed equality partition, missing
connections and findings. Renumbering cannot hide a short, split or wrong supply.
A configured result cannot omit required evidence and become a historical job.

Macro export retains the implementation checkpoint and all reference/native/
metal artifacts. Its bounded connectivity status does not change the broader
LVS qualification statement or imply foundry acceptance. Historical unconfigured
jobs remain readable without a new connectivity claim.

## Evidence and limits

The [combined acceptance checkpoint](validation/gf180-combined-acceptance-2026-10-09.json)
records actual reference generation and native checks on all six retained filled
C/D counter, UART and APB layouts. Positive comparisons cover 98,524 devices,
394,080 terminals and 197,048 primary geometry values. A physically disconnected
C-counter VDD port still matches under the native device comparison, but the
written-metal check fails and the combined finish adapter rejects it.

After canonicalizing engine-local identifiers in separate copies, current-source
Windows and Linux reconstruction produces byte-identical reports and saved data
for all seven cases. Original engine results remain retained. This readback is
separate from fresh native engine execution. One hundred focused regressions pass
on each OS, including missing evidence and preserved fault-partition checks.
The complete Windows application suite passes 1,626 tests with 62 skips.

The [configured counter checkpoint](validation/gf180-configured-finishes-2026-10-09.json)
also retains two fresh complete C/D synthesis and physical-finish jobs with
801 cells each, zero router findings, both connectivity checks passing, and
actual macro exports. Independent byte audits cover every exported artifact,
constraint and notice. The current source also reopens both complete jobs on
Windows and reproduces all 102 macro payload members byte for byte, including
the manifest. These counter runs use the existing explicit physical
settings; they do not add the later perimeter dummy fill or qualify post-fill
electrical timing.

The [runtime build](GF180_RUNTIME_INPUTS.md) now prepares and enables these
inputs by default. The exact new payload passes fresh Linux and Windows
installation, saved-result reconstruction and six additional C/D connectivity
controls on each OS, including rejected power opens and signal shorts.
Desktop-package acceptance, complete fill coverage and all required
before/filled electrical and timing checks remain open in
[chunk 4](PDK_QUALIFICATION_PLAN.md). No complete PDK qualification is claimed
by these bounded results.
