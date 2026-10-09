# Complete GF180 connectivity inputs

`scripts/prepare_gf180_connectivity.py` prepares the independent standard-cell
views and native verification rules needed by the configured GF180 finish
checks. It captures all 229 cells at library revision
`3781fd2951da6e3dc4600e52d997398a9463caeb`, including physical-only cells.
This is input preparation, not qualification of every cell or process.

The [library lock](../examples/gf180-connectivity-library-lock.json) records
every CDL and GDS view, its upstream blob identity and SHA-256, and the source
license and README. Twenty duplicate upstream GDS paths have the same blob
contents as their canonical cell-family paths; the lock records those aliases.
They do not add distinct cells.

## Preparation and profile binding

First prepare the [strict native LVS recipe](GF180_LVS_RECIPE.md). Then run:

```sh
python scripts/prepare_gf180_connectivity.py \
  --library /path/to/pinned-independent-library \
  --rules /path/to/prepared-native-rules \
  --output /path/to/platform-root/gf180/verification
```

The source library must contain every file in the library lock. The rule
directory must match all 32 locked prepared rule and attribution files. The
command authenticates every input before creating a new destination, retains
licenses and source locks, and refuses to replace an existing directory.

The preparation API's `attach(platform, collateral)` returns a new captured
profile. It verifies the original files, rechecks the prepared inputs, adds both
`lvs_reference` and `gf180_connectivity` policies, and calculates a new platform
fingerprint. It accepts the matching 9-track, 5 V, 5LM C/9K or D/11K settings in
every selected corner. It rejects missing views, changed rules, reused captures,
and collateral outside the platform root. The original profile is unchanged.

The output deliberately changes the platform identity. Existing jobs retain
their original inputs; run a fresh implementation with the new profile.
The included runtime build has not yet been changed to prepare and enable this
collateral by default. Fresh runtime and desktop installation acceptance remain
required before treating it as an included workflow.

## Checked scope

The [preparation checkpoint](validation/gf180-connectivity-profile-2026-10-09.json)
retains fresh Windows and Linux preparations and identical C/D profile records.
Each profile captures 1,101 files, including the original 606 production files
and all independent circuit/layout views, rules, attribution and preparation
records. Thirty-one focused preparation and connectivity tests pass on each OS.

An independent inventory checks every one of the 229 cells against the actual
production platform. All GDS files are byte-identical to the independent source
views. All 1,294 LEF terminal names agree with their CDL interfaces, with 456
`VNW`/`VPW` bulk terminals recorded separately. This verifies interface and view
compatibility; it does not prove transistor connectivity, functional behavior,
timing, all operating conditions or complete device-family support.

The [combined finish workflow](GF180_FINISH_CONNECTIVITY.md) records the separate
native controls, saved-result portability and configured counter/macro evidence.
Complete fill, full before/filled electrical checks and runtime installation
retain their own acceptance requirements in the
[qualification plan](PDK_QUALIFICATION_PLAN.md).
