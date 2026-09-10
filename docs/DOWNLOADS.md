# Get IC Design Studio

Current source: **0.22.0.dev11**, an engineering-preview release candidate.
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
| `SHA256SUMS-0.22.0.dev11.txt` | Final download checksums |

Keep the complete runtime folder beside the executable. A clean GitHub source
export contains no native binaries: the Windows launcher downloads the pinned
ngspice runtime, verifies its hash and executes a small installation check.
Python dependencies need internet during source setup. The first-waveform
example uses the included educational solver and requires no external PDK.

The previous embedded-Python portable handoff used `app/` and `python/` folders.
It is different from the PyInstaller portable ZIP now built and extracted by CI.
Only the validation record for the exact downloaded file establishes what ran.

See [current release status](RELEASE_STATUS.md) for the confirmed dev10 hosted
baseline and remaining consumer-platform checks. Windows builds are unsigned;
macOS has no qualified binary. Read [simulation setup](../SIMULATION_SETUP.md)
for custom engine paths and [the release guide](RELEASING.md) for maintainers.

## Verify a download

On Linux, run `sha256sum -c SHA256SUMS-0.22.0.dev11.txt` in the download directory.
On Windows, run `Get-FileHash .\IC-Design-Studio-0.22.0.dev11-Windows-x64-Setup.exe -Algorithm SHA256`
and compare it with the matching line in the checksum file. Missing optional
files in a full checksum inventory do not verify any files you did not download.
