# GF180 connectivity inputs in runtime builds

The runtime build prepares and enables the complete GF180 connectivity inputs
for both included C and D profiles. Existing installed runtimes keep their
original captured inputs. A new build still needs its own installed acceptance;
changing the builder does not qualify an older payload or any PDK.

## Source capture and preparation

`scripts/fetch_gf180_connectivity.py` fetches the 460 independent cell/attribution
files and 32 original native-rule/attribution files from pinned GitHub revisions.
It verifies every SHA-256, plus the cell sources' recorded sizes and Git blob
identities. Only verified objects enter the reusable cache. A failed download
does not publish a partial source tree or overwrite an existing destination.

```sh
python scripts/fetch_gf180_connectivity.py \
  --output /path/to/new-gf180-sources \
  --cache /path/to/gf180-download-cache
```

The runtime packager applies the existing [strict rule preparation](GF180_LVS_RECIPE.md)
and [complete cell preparation](GF180_CONNECTIVITY_PROFILE.md), then attaches
both reference and combined-connectivity policies. Shared C/D source files and
notices are captured once. Their separate stack settings and timing corners
are preserved. Missing or changed sources abort the build before publishing a
runtime catalog.

`scripts/build_digital_runtime.py` includes all required preparation scripts
and source locks in the Docker build context. The image build invokes the
preparation automatically. No manual profile edit is needed for a newly built
payload. A fresh finish job is required because the captured platform identity
changes.

## Verified boundaries

The [packaging-input checkpoint](validation/gf180-runtime-inputs-2026-10-09.json)
records a real Windows download from an empty cache and Linux reconstruction
with the downloader's network access disabled. All 492 source files match their
locks. Both prepared profiles contain 1,101 captured files and 229 independent
cell pairs, with identical portable metadata across operating systems. They
also match the profiles used for the prior successful configured finish jobs.

These checks prove source capture and the actual GF180 preparation path in the
packager. The full Windows application suite passes 1,638 tests with 62 skips;
35 focused packaging tests pass on Linux and on Windows with one symlink test
skipped on Windows.

The separate [runtime build checkpoint](validation/gf180-runtime-build-2026-10-09.json)
records the real Docker build and exported 1.53 GB package. Independent archive
readback verifies every one of its 54,396 locked files, all four platform
profiles and the complete GF180 source/rule bindings. The exact package and
frozen build source are retained outside dated build folders. GF180 C/D share
the same captured files while keeping their separate stack settings.

The [fresh Linux installation checkpoint](validation/gf180-installed-linux-2026-10-09.json)
and [fresh Windows installation checkpoint](validation/gf180-installed-windows-2026-10-09.json)
record unmodified first-run setup on this exact payload. On each OS, all 34
digital checks, 18 declared timing pairs and seven native tool controls pass
their expected outcomes. Independent readback authenticates 1,391 artifact
bindings per installation and reconstructs the saved results. Both GF180
counter implementations pass the combined connectivity gate on each OS.

Six further controls per OS execute the actual installed verification engine
on copies of those C/D counters. Both unchanged layouts pass. Each VDD-port open has 790
disconnected supply terminals and is rejected by the combined check, despite
matching under native device comparison. Both signal shorts fail the native
and written-metal checks. Saved failure records remain rejected. The controls
preserve the standard-cell masks and top labels; the modified masks and native
comparison databases are retained in a fully verified archive outside dated
folders.

The [installed macro checkpoint](validation/gf180-installed-macros-2026-10-09.json)
also retains actual exports from all four installed C/D counter jobs. Windows
reopens each complete saved job and reproduces all 102 native macro members
byte for byte, including its manifest. Each macro carries 94 artifacts, one
constraint file and six captured source notices. Independent audits check the
exact source-result and input identities, every payload byte, and all 80 required
connectivity/reference artifacts. Zip container metadata can differ between
exports; the comparison covers their complete contents.

These installation counters have no perimeter dummy fill. Exact desktop
packages, complete fill coverage and full post-fill electrical and timing
acceptance remain separate. See the
[combined finish workflow](GF180_FINISH_CONNECTIVITY.md) and the
[qualification plan](PDK_QUALIFICATION_PLAN.md) for those separate gates.
