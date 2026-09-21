# Preparing and publishing a release

This repository is prepared for public GitHub hosting. The local archive does not create a repository, push a tag or publish a release. The desktop and qualification workflows have read-only repository permissions. The separate draft-release workflow, triggered by selected source changes or manual dispatch, grants contents write only to its final job, after all verification succeeds. It creates a draft and never publishes it automatically.

## Repository setup

Extract the **GitHub** archive and use the contents of its `IC-Design-Studio` directory as the repository root. Preserve `.github/`, `.gitignore`, the GPL license and third-party notices. Choose the repository owner and name when creating the actual repository; no placeholder owner is embedded in this README.

Suggested About description: **Open desktop workspace for circuit design, ngspice simulation, Xschem migration and linked layout.**

Suggested topics: `eda`, `analog-design`, `schematic-editor`, `ngspice`, `xschem`, `klayout`, `pdk`, `pyside6`, `circuit-simulation`.

Use `docs/images/banner.svg` as the editable artwork source. The README screenshots are captures of the application, not concept mockups. Set up branch review and issue labels according to the maintainer's workflow.

## Release checks

1. Update `icstudio/__init__.py`, the README version badge, release notes and versioned asset references together. `python scripts/check_release.py` checks consistency, all repository documentation links and example availability. The physical workflow also retains real-project import evidence; strict detector LVS, HSA sweeps and fault-detection gates must pass; remaining GDS-conversion and PVT scope limits stay visible in release notes.
2. Run core tests and the desktop workflow on Windows and Linux. Keep the native migration, native analysis and getting-started evidence artifacts. Check a clean user profile and paths containing spaces.
3. Review dependencies, corresponding-source availability and all bundled notices. When preparing PDK adapters, regenerate manifests with `scripts/prepare_pdk_collection.py` and preserve upstream provenance. Do not label installation or hash checks as foundry qualification.
4. Build packages, inspect their contents and launch them on their target platforms. Static PE checks do not replace Windows execution. Sign Windows binaries only through the maintainer's signing infrastructure.
5. Generate checksums over the final files. Attach validation records that match those files. Run the README link check after screenshots and docs are copied into the tree.

The desktop workflow runs on manual dispatch, every pull request, main/experimental pushes and `v*` tags. It builds Linux and Windows artifacts and runs their available acceptance tests. Review the actual workflow run before promoting a release. The locally assembled portable Windows package has a different packaging route from the CI PyInstaller/installer build; qualify the exact asset being published.

## Build source and repository archives

```sh
python scripts/release_archives.py --output release --repository
```

The source archive includes a Windows ngspice runtime only when staged locally. The GitHub archive always excludes native binaries. To stage the pinned Windows engine, use `scripts/stage_windows_ngspice.py`. Build a Windows installer on Windows with `scripts/build_windows.ps1`; validate it with `scripts/verify_windows.ps1`.

For Linux PyInstaller builds, set `ICSTUDIO_BUNDLED_NGSPICE` to the native executable before running `scripts/package.py`. CI sets this explicitly. Add a Linux archive only after testing the resulting bundle on its target system.

## Publish a reviewable release

Create a **draft prerelease** for the matching tag. Use [UPDATE_0.22_DEV25.md](UPDATE_0.22_DEV25.md) as the current notes, then update its validation section with the actual hosted run and exact artifacts. Upload application packages, matching source, optional PDK adapters, the validation record and checksums.

Check the rendered README, release links and download instructions in the destination repository. Only then publish the draft. Keep the engineering-preview designation until the documented platform and process gates justify a stronger status. Do not attach an archive from another version to fill an unbuilt platform slot.

## Automated draft preparation

Run **Prepare draft preview release** on `experimental` for a reviewable branch
candidate, or on `main` after merging its verified PR.
It invokes desktop, interoperability, physical, digital, VGA and statistical
campaign qualification on the same commit,
then assembles verified assets and creates a draft prerelease with the current
application version. It fails if that release already exists. Experimental tags include the commit prefix. See
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

A version change pushed to `experimental` or merged into `main` automatically starts **Prepare draft preview release**. Manual dispatch remains available. The workflow reruns all six qualifications for the selected commit and creates only a draft prerelease; publication remains a separate maintainer action.

The statistical gate must complete its 1,152-case ngspice workload, coordinator
crash recovery and trial classifications. Draft assembly checks its commit and
workflow-run identity, includes the full evidence archive and a compact validation
record, and checksums both. Deliberate specification failures in this workload
test classification; unresolved cases or failed recovery block the draft. This
one-host gate does not satisfy [two-host worker acceptance](CAMPAIGN_WORKER_ACCEPTANCE.md).

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
