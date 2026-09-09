# Choose a download

Use the repository's **Releases** page for published assets. Match the version across the application, optional adapters and release notes. Until a maintainer publishes them, prepared archives are local release candidates.

| Asset | Who it is for | What it contains |
|---|---|---|
| `IC-Design-Studio-0.21.0-Windows-x64.zip` | Windows users | Portable app, Python, Qt, ngspice, docs and examples |
| `IC-Design-Studio-0.21.0-GitHub.zip` | Repository maintainers and contributors | Clean source tree, README assets, tests, workflows and project templates; no native binaries |
| `IC-Design-Studio-0.21.0-Source.zip` | Users running or modifying source | Application source plus the Windows ngspice runtime |
| `IC-Design-Studio-0.21.0-PDK-Adapters.zip` | Users exploring the three supported process families | Pinned adapter subsets, hashes, notices and provenance; IHP Verilog-A source |
| `IC-Design-Studio-0.21.0-Validation.json` | Release reviewers | Executed checks and explicit platform limits |
| `SHA256SUMS-0.21.0.txt` | Anyone checking a download | SHA-256 hashes of the release files |

## Windows

Extract the **entire** Windows ZIP and launch `ICDesignStudio.exe`. Keep its `app` and `python` folders beside the launcher. Do not run it from inside the ZIP viewer. `ICDesignStudio-Console.exe` provides startup diagnostics. No separate Python or ngspice installation is needed for the included native examples.

The portable package targets Windows 10/11 x64 and is unsigned. The build prepared in this workspace has manifest and PE dependency checks, not a native Windows execution test. The repository's Windows CI job is intended to execute that additional qualification before a public release is designated stable.

## Linux and macOS

Follow the source instructions in the [README](../README.md). Use the operating system's native ngspice and select it in the app. Linux regression and offscreen Qt workflows are exercised by this release's validation. macOS still needs platform qualification. No new Linux or macOS binary is represented by the prepared Windows asset.

## Check a downloaded archive

On Linux:

```sh
sha256sum -c SHA256SUMS-0.21.0.txt
```

On Windows PowerShell:

```powershell
Get-FileHash .\IC-Design-Studio-0.21.0-Windows-x64.zip -Algorithm SHA256
```

Compare the hash with the corresponding line in the checksum file. The PDK companion is optional; begin with the included gallery before installing it.
