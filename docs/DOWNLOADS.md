# Download IC Design Studio

Use the [GitHub Releases page](https://github.com/jonahsaunders/IC-Design-Studio/releases) for packaged **0.22.0.dev10** prerelease downloads. Check the [release packaging workflow](https://github.com/jonahsaunders/IC-Design-Studio/actions/workflows/publish-preview.yml) if assets are still building.

| Asset | Intended use |
|---|---|
| `IC-Design-Studio-0.22.0.dev10-Windows-x64.zip` | Portable desktop with Python, Qt, NGSpice 42 and offline GF180MCU/SKY130 simulation subsets |
| `IC-Design-Studio-0.22.0.dev10-Source.zip` | Source plus staged Windows NGSpice runtime and the same PDK models; Python dependencies install on first setup |
| `IC-Design-Studio-0.22.0.dev10-GitHub.zip` | Clean source tree and models; Windows launcher downloads NGSpice on first setup |
| `IC-Design-Studio-0.22.0.dev10-Validation.json` | Recorded local simulation checks and explicit platform limits |
| `SHA256SUMS-0.22.0.dev10.txt` | SHA-256 checksums of release assets |

GitHub's automatic **Source code (zip)** and **Source code (tar.gz)** links do not contain a prebuilt application or Windows NGSpice executable.

## Windows quick start

Extract the entire **Windows-x64 ZIP**, then double-click `ICDesignStudio.exe`. Keep its `app` and `python` folders beside it. Choose **07 · GF180 bandgap startup → Open a copy**, then **F5**. The portable app needs no first-launch downloads. Use `ICDesignStudio-Console.exe` for startup diagnostics.

This unsigned package targets Windows 10/11 x64. Linux simulation and static Windows package checks do not establish native Windows desktop qualification. See [simulation setup and validation limits](../SIMULATION_SETUP.md).

## Source setup

On Windows, install 64-bit Python 3.12, extract the source and run `launch-windows.bat`. On Linux/macOS, install a host-native NGSpice and follow the [README](../README.md). The PDK simulation subsets are included in every source download.

## Verify a download

On Linux, place the downloaded release assets and checksum file in the same directory:

```sh
sha256sum --ignore-missing -c SHA256SUMS-0.22.0.dev10.txt
```

On Windows PowerShell:

```powershell
Get-FileHash .\IC-Design-Studio-0.22.0.dev10-Windows-x64.zip -Algorithm SHA256
```

Compare the result with the matching line in `SHA256SUMS-0.22.0.dev10.txt`.
