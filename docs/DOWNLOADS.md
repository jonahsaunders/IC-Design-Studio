# Get IC Design Studio

Current development source: **0.22.0.dev21**. [Release status](RELEASE_STATUS.md) records the exact scope of the source, desktop and physical checks. New source does not imply a published or signed package.

The [dev21 update](UPDATE_0.22_DEV21.md) is newer than the dev20 draft below.
Use the dev21 PR's successful desktop workflow artifacts (`release-Windows` or
`release-Linux`), or the experimental draft once its complete workflow succeeds.
Check About for the exact source commit. Drafts remain maintainer-visible until
publication.

The earlier dev20 draft was assembled successfully from `6b1e30f3d13c1dcb8d662523fd6cf4919f1b2a0d`
by [release run 34703715977](https://github.com/jonahsaunders/IC-Design-Studio/actions/runs/34703715977).
Its Windows/Linux packages, source, evidence and checksums are uploaded. It remains
a draft engineering preview pending consumer-machine acceptance and the signing decision.
Check the [Releases page](https://github.com/jonahsaunders/IC-Design-Studio/releases)
for published downloads. A draft release or Actions artifact is not a published
release. If there is no current release, use **Code → Download ZIP** and the
[source setup instructions](../README.md#start-in-three-steps).

## Release assets

| Asset suffix | Use |
|---|---|
| `Windows-x64-Setup.exe` | Install the app, bundled ngspice and simulation PDK subsets |
| `Windows-x64-Portable.zip` | Extract the entire archive and launch `ICDesignStudio/ICDesignStudio.exe` |
| `Linux-x86_64.tar.gz` | Extract and run `ICDesignStudio/ICDesignStudio`; targets Ubuntu 24.04 |
| `Source-Windows.zip` | Matching Windows source, including its staged ngspice runtime |
| `Source-Linux.zip` | Matching Linux application source; install native ngspice for source use |
| `Validation-*.json` and `Evidence-*.zip` | Exact commit, package hashes and executed platform/numerical checks |
| `SHA256SUMS-0.22.0.dev20.txt` | Final download checksums |

Keep the complete runtime folder beside the executable. A clean GitHub source
export contains no native binaries: the Windows launcher downloads the pinned
ngspice runtime, verifies its hash and executes a small installation check.
Python dependencies need internet during source setup. The first-waveform
example uses the included educational solver and requires no external PDK.

The previous embedded-Python portable handoff used `app/` and `python/` folders.
It is different from the PyInstaller portable ZIP now built and extracted by CI.
Only the validation record for the exact downloaded file establishes what ran.

See [current release status](RELEASE_STATUS.md) for the confirmed dev20 hosted
baseline and remaining consumer-platform checks. Windows builds are unsigned;
macOS has no qualified binary. Read [simulation setup](../SIMULATION_SETUP.md)
for custom engine paths and [the release guide](RELEASING.md) for maintainers.

## Verify a download

On Linux, run `sha256sum -c SHA256SUMS-0.22.0.dev20.txt` in the download directory.
On Windows, run `Get-FileHash .\IC-Design-Studio-0.22.0.dev20-Windows-x64-Setup.exe -Algorithm SHA256`
and compare it with the matching line in the checksum file. Missing optional
files in a full checksum inventory do not verify any files you did not download.
