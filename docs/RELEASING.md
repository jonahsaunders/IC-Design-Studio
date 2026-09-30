# Preparing and publishing a release

The [IC Design Studio repository](https://github.com/jonahsaunders/IC-Design-Studio)
uses separate desktop, qualification and draft-release workflows. Desktop and
qualification jobs have read-only repository permissions. The draft workflow,
triggered by selected source changes or manual dispatch, grants contents write
only to its final job after all seven qualification jobs succeed. It creates a
draft prerelease and never publishes automatically.

## Source and build identity

Build from a clean, committed Git checkout of the selected `main` or
`experimental` commit. `scripts/package.py` rejects unknown or dirty source
identity. A GitHub/source archive is useful for reading or source launch, but
lacks the Git identity needed for a qualified build. Preserve `.github/`, the
GPL license, third-party notices and upstream provenance when preparing a fork.

Suggested About description: **Open desktop workspace for circuit design, ngspice simulation, Xschem migration and linked layout.**

Suggested topics: `eda`, `analog-design`, `schematic-editor`, `ngspice`, `xschem`, `klayout`, `pdk`, `pyside6`, `circuit-simulation`.

Use `docs/images/banner.svg` as the editable artwork source. The README screenshots are captures of the application, not concept mockups. Set up branch review and issue labels according to the maintainer's workflow.

## Release checks

1. Update `icstudio/__init__.py`, the README version badge, release notes and versioned asset references together. `python scripts/check_release.py` checks consistency, all repository documentation links and example availability. The physical workflow also retains real-project import evidence; strict detector LVS, HSA sweeps and fault-detection gates must pass; remaining GDS-conversion and PVT scope limits stay visible in release notes.
2. Run core tests and the desktop workflow on Windows and Linux. Keep the native migration, native analysis and getting-started evidence artifacts. Check a clean user profile and paths containing spaces.
3. Review dependencies, corresponding-source availability and all bundled notices. When preparing PDK adapters, regenerate manifests with `scripts/prepare_pdk_collection.py` and preserve upstream provenance. Do not label installation or hash checks as foundry qualification.
4. Build packages, inspect their contents and launch them on their target platforms. Static PE checks do not replace Windows execution. Sign Windows binaries only through the maintainer's signing infrastructure.
5. Generate checksums over the final files. Attach validation records that match those files. Run the README link check after screenshots and docs are copied into the tree.

The desktop workflow runs on manual dispatch, every pull request,
main/experimental pushes and `v*` tags. It builds Linux and Windows artifacts and
runs their defined acceptance tests. Review the actual workflow run before
promoting a release. Historical embedded-Python Windows archives used a different
route; their records do not qualify a current PyInstaller/installer asset.

## Desktop build prerequisites

Follow [build-desktop.yml](../.github/workflows/build-desktop.yml) for the exact
host dependencies and order. In addition to Python 3.12 and
`requirements-build.txt`, packaging requires:

- A complete digital/physical payload from
  `python scripts/build_digital_runtime.py` on Linux with Docker. The
  [runtime workflow](../.github/workflows/digital-runtime.yml) exports it as
  `digital-runtime-payload`; stage all files under `build/digital-payload`.
- A successful `python scripts/qualify_digital_runtime.py` on each packaging
  OS. It executes real engine checks and writes `qualified-Windows.json` or
  `qualified-Linux.json` matching that payload. Windows requires WSL 2.
- Pinned VGA assets from `python scripts/build_vga_playground.py --test`, using
  Git and Node.js 22.12+ (or 24), plus the platform graphics/WebEngine libraries.
- Native ngspice: Windows staging uses
  `python scripts/stage_windows_ngspice.py --ensure`; Linux uses an installed
  executable or `ICSTUDIO_BUNDLED_NGSPICE`.

`scripts/package.py` also stages and verifies the independent openEMS runtime.
Its build/download prerequisites are in [OPENEMS.md](OPENEMS.md). Python
requirements or `build-windows.bat` alone do not provision all release assets.
See [Windows build and installed-app verification](WINDOWS_RELEASE.md) and
[Linux launch checks](LINUX_SETUP.md). End users of complete packages do not
need Docker, Node.js or build compilers.

## Build source and repository archives

```sh
python scripts/release_archives.py --output release --repository
```

The source archive includes a Windows ngspice runtime only when staged locally
or selected with `--windows-runtime`. The GitHub archive excludes native
binaries. Neither archive includes generated desktop runtimes from `build/`.
After satisfying the build prerequisites, build a Windows installer on Windows
with `scripts/build_windows.ps1` and validate it with `scripts/verify_windows.ps1`.
That verifier also needs the locked physical adapter prepared as described in
the Windows guide.

For Linux PyInstaller builds, set `ICSTUDIO_BUNDLED_NGSPICE` to the native
executable before running `scripts/package.py`; CI does so explicitly. After
package verification, `release_archives.py --with-linux-bundle` can archive the
built directory. The release workflow uses `prepare_release_payload.py` for
distribution execution, corresponding-source/evidence packaging and hashes.

## Publish a reviewable release

Create a **draft prerelease** for the matching tag. Use [UPDATE_0.22_DEV25.md](UPDATE_0.22_DEV25.md) as the current notes, then update its validation section with the actual hosted run and exact artifacts. Upload application packages, matching source, optional PDK adapters, the validation record and checksums.

Check the rendered README, release links and download instructions in the destination repository. Only then publish the draft. Keep the engineering-preview designation until the documented platform and process gates justify a stronger status. Do not attach an archive from another version to fill an unbuilt platform slot.

## Automated draft preparation

Run **Prepare draft preview release** on `experimental` for a reviewable branch
candidate, or on `main` after merging its verified PR.
It invokes desktop, interoperability, physical, digital, VGA, statistical
campaign and reference compatibility qualification on the same commit,
then assembles verified assets and creates a draft prerelease with the current
application version. Automatic tags use
`BRANCH-vVERSION-COMMIT-RUN-ATTEMPT`, including the full source SHA and GitHub run
identity. A rerun creates a separate draft, so an interrupted upload cannot cause
assets from different builds to be mixed. Existing releases are never overwritten
or deleted. See
[qualification and repository setup](QUALIFICATION_0.22.md) for required checks,
the reviewed main ruleset and remaining clean-machine acceptance.

The desktop jobs run `scripts/prepare_release_payload.py` after installer/frozen
checks. That script executes the extracted archive with isolated application
settings and retains its hash. `scripts/assemble_prerelease.py` rejects a changed
asset, different source commit, missing platform or unqualified archive.

The Windows acceptance record names and hashes the exact installer before running
it, checks its hash again afterwards and retains all three installed DPI probe
reports. Payload assembly requires these reports to identify the current clean
commit/version and the installer hash to match the supplied setup executable.
Each platform also requires its expected desktop archive, corresponding source
ZIP and evidence ZIP. A refreshed asset manifest cannot substitute for executing
a changed installer.
Distribution archives are hashed before extraction and checked again after the
desktop and VGA probes; replacing an archive during execution fails acceptance.

A version-file change pushed to `experimental` or `main` automatically starts
**Prepare draft preview release**. Selected probe, packaging and workflow files
also trigger it; ordinary source edits outside the exact
[push path list](../.github/workflows/release-preview.yml) do not. Manual dispatch
remains available. The workflow reruns all seven qualifications for the selected
commit and creates only a draft prerelease; publication remains a separate
maintainer action.

The statistical gate must complete its 1,152-case ngspice workload, coordinator
crash recovery and trial classifications. Draft assembly checks its commit and
workflow-run identity, includes the full evidence archive and a compact validation
record, and checksums both. Deliberate specification failures in this workload
test classification; unresolved cases or failed recovery block the draft. This
one-host gate does not satisfy [two-host worker acceptance](CAMPAIGN_WORKER_ACCEPTANCE.md).

## Large evidence archives

Release evidence is complete even when an archive exceeds GitHub's per-asset
limit. `scripts/release_evidence.py` retains ZIPs up to 1 GiB as ordinary assets
and splits larger ZIP byte streams into 1 GiB parts. The ordered `.zip.parts.json`
manifest records each part's byte count and SHA-256 and the reconstructed ZIP's
byte count and SHA-256. No files or qualification gates are removed to reduce size.
Every asset must pass a strict below-2-GiB size check before draft creation.

Download all parts of an archive, its manifest and the release's
`reassemble_evidence.py` helper into the same directory. With Python 3.11 or newer:

```sh
python reassemble_evidence.py reassemble ARCHIVE.zip.parts.json --output restored
```

Use the actual manifest filename in place of `ARCHIVE.zip.parts.json`. The helper
verifies every part and the entire reconstructed ZIP, fails on missing or corrupt
parts and refuses to overwrite an existing archive. The release includes full
instructions in `EVIDENCE-REASSEMBLY.md`. Final `SHA256SUMS` cover the ordered
manifests, parts, helper and instructions as well as the other release assets.
An oversized application/source asset still fails preflight; only qualification
evidence ZIPs are split, so existing package validation records stay unchanged.

## VGA package evidence

The installed Windows executable and both extracted archives run
`--vga-test OUTPUT`. `scripts/verify_packaged_vga.py` selects the native Windows
display or Linux Xvfb, prevents successful external HTTP(S) access, and validates
the report against the exact clean commit/version. Release assembly requires all
eight presets to pass for every distributed desktop and the Windows installer.
Audio rendering state is automated; speaker quality remains manual.

Digital and VGA workflows are reusable required draft jobs, and their evidence
archives are included in the final checksums. Notes are selected from the current
application version; update the matching versioned document, README badge and
download examples together. `scripts/check_release.py` rejects missing current
notes. See [release acceptance](RELEASE_FOLLOWUPS.md) for publication gates.
