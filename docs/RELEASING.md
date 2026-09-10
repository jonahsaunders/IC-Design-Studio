# Preparing and publishing a release

This project publishes source and packaged engineering previews through GitHub. The desktop verification workflow builds artifacts with read-only permissions; the separate preview workflow publishes release assets after its checks pass.

## Repository and automated preview publication

The repository is [jonahsaunders/IC-Design-Studio](https://github.com/jonahsaunders/IC-Design-Studio). Keep native binaries in release assets; the source tree includes checksummed simulation models and their notices.

The [preview workflow](../.github/workflows/publish-preview.yml) runs when the dev10 release notes change on `main`, or through manual dispatch. It tests Linux simulations and the gallery, assembles the Windows portable package, checks every manifest entry and ZIP, and creates matching source archives and checksums. A separate job with `contents: write` creates a draft, uploads all required files and publishes it as a prerelease. An already published version is never overwritten. Failed uploads leave a draft for diagnosis and retry.

This route does not claim native Windows execution. The broader desktop workflow separately builds and checks a Windows installer. Promote a preview only after qualifying the exact packages on their target platforms.

To reproduce the preview assets with Python 3.12 and `requirements-build.txt` installed:

```sh
python scripts/prepare_preview_release.py --output release
```

The script downloads checksum-pinned Python, Windows wheels and NGSpice. Use a fresh assembly directory for each run. PDK files come from the committed, locked collection.

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

Create a **draft prerelease** for the matching tag. Use the [dev10 notes](releases/0.22.0.dev10.md) as the starting notes, then update its validation section with the actual hosted run and exact artifacts. Upload application packages, matching source, optional PDK adapters, the validation record and checksums.

Check the rendered README, release links and download instructions in the destination repository. Only then publish the draft. Keep the engineering-preview designation until the documented platform and process gates justify a stronger status. Do not attach an archive from another version to fill an unbuilt platform slot.
