# Get IC Design Studio

The current source is **0.22.0.dev9**, an engineering preview. See the [grid and drawing update](DRAWING_0.22.md) and [recorded validation](validation/0.22.0.dev9.json).

## Current source

On the [repository page](https://github.com/jonahsaunders/IC-Design-Studio), choose **Code → Download ZIP** and extract it, or clone it:

```sh
git clone https://github.com/jonahsaunders/IC-Design-Studio.git
cd IC-Design-Studio
```

On Windows, install 64-bit Python 3.12 with the Python launcher and double-click `launch-windows.bat`. It installs verified dependencies in a short environment path under `%LOCALAPPDATA%\ICStudio\venvs` to avoid deeply nested Qt resource paths. Linux/macOS users should follow the [source setup instructions](../README.md).

The source includes the educational solver. A native ngspice installation is required for ngspice analyses. There is no published dev9 portable executable. Native Windows/macOS display testing remains pending; recorded Linux/offscreen checks are linked above.

## Historical prepared assets

The **0.21.0** files below describe earlier locally prepared release candidates. They do not contain the dev9 improvements. No assets were published on the [Releases page](https://github.com/jonahsaunders/IC-Design-Studio/releases) when this update was prepared. Use current source for dev9; do not treat the filenames below as download links.

| Asset | Who it is for | What it contains |
|---|---|---|
| `IC-Design-Studio-0.21.0-Windows-x64.zip` | Windows users | Portable app, Python, Qt, ngspice, docs and examples |
| `IC-Design-Studio-0.21.0-GitHub.zip` | Repository maintainers and contributors | Clean source tree, README assets, tests, workflows and project templates; no native binaries |
| `IC-Design-Studio-0.21.0-Source.zip` | Users running or modifying source | Application source plus the Windows ngspice runtime |
| `IC-Design-Studio-0.21.0-PDK-Adapters.zip` | Users exploring the three supported process families | Pinned adapter subsets, hashes, notices and provenance; IHP Verilog-A source |
| `IC-Design-Studio-0.21.0-Validation.json` | Release reviewers | Executed checks and explicit platform limits |
| `SHA256SUMS-0.21.0.txt` | Anyone checking a download | SHA-256 hashes of the release files |

### Historical Windows portable package

Extract the **entire** Windows ZIP and launch `ICDesignStudio.exe`. Keep its `app` and `python` folders beside the launcher. Do not run it from inside the ZIP viewer. `ICDesignStudio-Console.exe` provides startup diagnostics. No separate Python or ngspice installation is needed for the included native examples.

That portable package targets Windows 10/11 x64 and is unsigned. Its historical validation covered manifest and PE dependency checks, not native Windows execution. It is a separate artifact from this source update.

### Check a historical archive

On Linux:

```sh
sha256sum -c SHA256SUMS-0.21.0.txt
```

On Windows PowerShell:

```powershell
Get-FileHash .\IC-Design-Studio-0.21.0-Windows-x64.zip -Algorithm SHA256
```

Compare the hash with the corresponding line in the checksum file. The PDK companion is optional; begin with the included gallery before installing it.
