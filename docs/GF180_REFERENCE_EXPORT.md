# GF180 final-layout reference export

A configured GF180 finish job now generates its transistor reference from the
captured final OpenDB and separately captured standard-cell CDL. This removes
manual reference assembly from that job. The reference is retained when the
result is reopened and included with its source library in a macro export.
Native LVS and written-metal continuity are still required for acceptance.

## Captured platform inputs

The optional platform `lvs_reference` object uses this structure:

```json
{
  "recipe": "gf180-9t-opendb-reference-v1",
  "library_revision": "3781fd2951da6e3dc4600e52d997398a9463caeb",
  "masters": {
    "gf180mcu_fd_sc_mcu9t5v0__inv_1": "cdl/inv_1.cdl"
  }
}
```

This one-cell example illustrates the schema; a real capture must provide a
separate CDL file for every used master, including filler and antenna cells.
Each relative path must appear in the platform's hashed `files` list. This
recipe supports the `gf180` and `gf180d` 9-track profiles. Changing the recipe,
revision or master mapping invalidates the finished-result identity.

The existing included runtime does not yet bundle these additional inputs.
Historical and unconfigured jobs remain readable without a reference claim.
Adding captured metadata does not establish installed-runtime qualification.

## Connection checks

The read-only OpenROAD worker verifies the checkpoint and CDL hashes before and
after export. It reads every instance, terminal, placement, top port and stored
global connection rule, then exports CDL with filler cells included.

The application requires the fresh database to match the captured placement
exactly. Every instance must appear once, use its captured master, and preserve
all terminal assignments. The independent library must contain exactly the
used masters, with supported flat MOS/diode definitions and retained device
geometry. The existing diode adapter retains polarity, area, perimeter and
multiplicity.

Only missing LEF bulk terminals may be resolved from the explicitly stored
`VNW -> VDD` and `VPW -> VSS` global rules. Scoped, nonliteral or ambiguous rules
fail. Intentional unused outputs must be captured as unconnected outputs and
have distinct generated nodes. Missing inputs or supply terminals fail.

A top-level port can have a different internal net name: the APB example's
`pready` port is attached to `net`. Export uses that exact recorded mapping and
rejects collisions with other internal nets. An initial native attempt exposed
this case; its failed result is retained alongside the correction.

Saved-result validation reconstructs the reference from the retained raw CDL,
database readback, captured library policy and source files. It compares the
full circuit and report rather than accepting a stored status alone. Macro
exports carry these artifacts while retaining the existing unqualified LVS
status.

## Verified scope

The [checkpoint](validation/gf180-reference-generation-2026-10-09.json) records
six real Linux OpenROAD exports through the finish adapter and Windows saved
result reconstruction. C and D counter, UART and APB references are byte-identical
to their earlier independently audited references after the same exact diode
conversion. Together they cover 16,592 instances, 98,524 devices and 106 top
ports. The full Windows suite passes 1,600 tests with 62 skips; 74 focused tests
pass on each OS.

These runs exercise the actual adapter against captured full designs. They do
not establish a fresh complete route/finish run, native Windows OpenROAD, a
frozen desktop installation, or combined native LVS/metal acceptance. Runtime
bundling and that final dispatch remain integration work.

Use the [strict LVS recipe](GF180_LVS_RECIPE.md) and
[written-metal checker](GF180_METAL_CONTINUITY.md) for their respective checks.
Complete fill coverage and post-fill electrical performance remain open in the
[qualification plan](PDK_QUALIFICATION_PLAN.md).
