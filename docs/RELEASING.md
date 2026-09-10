# Preparing and publishing a release

This repository is prepared for public GitHub hosting. The local archive does not create a repository, push a tag or publish a release. The supplied desktop workflow has read-only repository permissions: tag pushes build artifacts but do not publish them automatically.

## Repository setup

Extract the **GitHub** archive and use the contents of its `IC-Design-Studio` directory as the repository root. Preserve `.github/`, `.gitignore`, the GPL license and third-party notices. Choose the repository owner and name when creating the actual repository; no placeholder owner is embedded in this README.

Suggested About description: **Open desktop workspace for circuit design, ngspice simulation, Xschem migration and linked layout.**

Suggested topics: `eda`, `analog-design`, `schematic-editor`, `ngspice`, `xschem`, `klayout`, `pdk`, `pyside6`, `circuit-simulation`.

Use `docs/images/banner.svg` as the editable artwork source. The README screenshots are captures of the application, not concept mockups. Set up branch review and issue labels according to the maintainer's workflow.

## Release checks

1. Update `icstudio/__init__.py`, the README version badge, release notes and versioned asset references together. `python scripts/check_release.py` checks consistency, current documentation links and example availability.
2. Run core tests and the desktop workflow on Windows and Linux. Keep the native migration, native analysis and getting-started evidence artifacts. Check a clean user profile and paths containing spaces.
3. Review dependencies, corresponding-source availability and all bundled notices. When preparing PDK adapters, regenerate manifests with `scripts/prepare_pdk_collection.py` and preserve upstream provenance. Do not label installation or hash checks as foundry qualification.
4. Build packages, inspect their contents and launch them on their target platforms. Static PE checks do not replace Windows execution. Sign Windows binaries only through the maintainer's signing infrastructure.
5. Generate checksums over the final files. Attach validation records that match those files. Run the README link check after screenshots and docs are copied into the tree.

The desktop workflow runs on manual dispatch, relevant pull requests and `v*` tags. It builds Linux and Windows artifacts and runs their available acceptance tests. Review the actual workflow run before promoting a release. The locally assembled portable Windows package has a different packaging route from the CI PyInstaller/installer build; qualify the exact asset being published.

## Build source and repository archives

```sh
python scripts/release_archives.py --output release --repository
```

The source archive includes a Windows ngspice runtime only when staged locally. The GitHub archive always excludes native binaries. To stage the pinned Windows engine, use `scripts/stage_windows_ngspice.py`. Build a Windows installer on Windows with `scripts/build_windows.ps1`; validate it with `scripts/verify_windows.ps1`.

For Linux PyInstaller builds, set `ICSTUDIO_BUNDLED_NGSPICE` to the native executable before running `scripts/package.py`. CI sets this explicitly. Add a Linux archive only after testing the resulting bundle on its target system.

## Publish a reviewable release

Create a **draft prerelease** for the matching tag. Use [RELEASE_0.21.md](RELEASE_0.21.md) as the starting notes, then update its validation section with the actual hosted run and exact artifacts. Upload application packages, matching source, optional PDK adapters, the validation record and checksums.

Check the rendered README, release links and download instructions in the destination repository. Only then publish the draft. Keep the engineering-preview designation until the documented platform and process gates justify a stronger status. Do not attach an archive from another version to fill an unbuilt platform slot.
