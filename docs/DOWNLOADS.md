# Get IC Design Studio

For digital implementation with included tools, use a **complete desktop package**.
The current package recipe includes Python, Qt, native ngspice, digital/physical
engines, compiler dependencies, the locked SKY130 HD digital platform, VGA assets
and openEMS. Local Student Hub/SAR engine requirements are separate; see below.

## Choose your download

The **0.23.0 engineering preview** is publicly available in
[release v0.23.0](https://github.com/jonahsaunders/IC-Design-Studio/releases/tag/v0.23.0),
published on **2026-10-03** from commit
`6c9cf950737c5d0e793d47ef8e9ddcb7caa72b83`. GitHub metadata checked on
2026-10-04 lists 23 release assets, including the downloads below. Its
[release preparation](https://github.com/jonahsaunders/IC-Design-Studio/actions/runs/37135864594)
passed all seven required gates for that commit. See
[release status](RELEASE_STATUS.md#0230-desktop-engineering-preview) for the
hosted scope and remaining consumer acceptance. Later source changes do not
alter these published downloads.

For a successful [desktop build](https://github.com/jonahsaunders/IC-Design-Studio/actions/workflows/build-desktop.yml?query=branch%3Amain),
open its **release-Windows** or **release-Linux** artifact and extract it to find
the package and matching validation record with asset hashes. The completed
release supplies the final checksum file. Actions artifacts require
GitHub sign-in and may expire. If an artifact is unavailable, use a retained
matching draft asset or prepare a new build; do not substitute another commit.

| 0.23.0 asset | What to do |
|---|---|
| [Windows x64 installer](https://github.com/jonahsaunders/IC-Design-Studio/releases/download/v0.23.0/IC-Design-Studio-0.23.0-Windows-x64-Setup.exe) | Run the installer, then launch Studio |
| [Windows x64 portable ZIP](https://github.com/jonahsaunders/IC-Design-Studio/releases/download/v0.23.0/IC-Design-Studio-0.23.0-Windows-x64-Portable.zip) | Extract everything, then open `ICDesignStudio/ICDesignStudio.exe` |
| [Linux x86_64 archive](https://github.com/jonahsaunders/IC-Design-Studio/releases/download/v0.23.0/IC-Design-Studio-0.23.0-Linux-x86_64.tar.gz) | Extract everything, enter `ICDesignStudio`, then run `./ICDesignStudio` |
| [Windows source](https://github.com/jonahsaunders/IC-Design-Studio/releases/download/v0.23.0/IC-Design-Studio-0.23.0-Source-Windows.zip) / [Linux source](https://github.com/jonahsaunders/IC-Design-Studio/releases/download/v0.23.0/IC-Design-Studio-0.23.0-Source-Linux.zip) | Corresponding developer source; not the complete desktop runtime |
| `Validation-*.json` / `Evidence-*.zip` | Build identity and evidence recorded for that asset |
| `*.zip.parts.json` and numbered parts | Split evidence archive; [reassemble and verify it](RELEASING.md#large-evidence-archives) |
| [SHA256SUMS-0.23.0.txt](https://github.com/jonahsaunders/IC-Design-Studio/releases/download/v0.23.0/SHA256SUMS-0.23.0.txt) | Checksums for the matching downloads |

Keep `_internal` and all its contents beside the executable. Copying a lone
executable, or choosing **Code → Download ZIP**, does not install the desktop
runtimes. Check **Help → About and release status** for the exact source commit.

## First launch

1. Launch Studio. To try a circuit immediately, open **File → Start here /
   example gallery → Your first waveform → Open a copy**, then press **F5**.
   That RC circuit uses the teaching solver.
2. For digital work, let **Included tools (recommended)** setup complete.
   Progress, detailed logs and retry are available; allow several minutes and
   several GB of disk space.
3. Open **Digital → New digital counter example**, then press **F5**. If setup
   is still needed, Run opens it and continues after success. Editing the design
   during setup requires a fresh Run request.

On **Windows x64**, the managed digital/physical flow uses Studio's private
WSL 2 distribution. If requested, choose **Enable Windows Linux support**, accept
the Windows administrator prompt, restart Windows and reopen Studio. Windows
components may need internet access; the engine payload itself is included.
Existing WSL distributions are preserved.

On **Linux x64**, the private native runtime targets Ubuntu 24.04 with
**glibc 2.39+**. See [Linux setup](LINUX_SETUP.md). macOS has no qualified desktop
package; [source launch](../README.md#start-in-three-steps) remains experimental.

Native SPICE uses bundled ngspice. Process physical verification uses
**Tools → Physical tools setup…** plus matching locked physical PDK assets/decks.
The included analog simulation subsets are not complete foundry PDKs.

**Student Hub Digital lessons use the selected Included or Custom digital tools.**
Run lesson opens first-run setup when needed and resumes after successful setup.
SAR experiments, Mixed Signal lessons and the capstone require separate native
local `ngspice`, `iverilog` and `vvp` executables. Their setup panels check all
prerequisites and link to the [native installation guide](MIXED_SIGNAL_SAR.md#local-engine-setup);
they do not download native Icarus. See [lesson engines](STUDENT_HUB.md#engines-and-models).

## If setup needs attention

| What Studio reports | Next step |
|---|---|
| Source checkout has no included tools | Use a complete desktop or explicitly select Custom tools |
| Included archive or tools are missing | Reinstall or extract the entire portable archive |
| Windows Linux support is unavailable | Enable it, restart if requested, then retry |
| Setup did not complete | Expand details, correct the reported problem and retry; retain setup logs |
| Custom tool cannot be found | Select Included tools for the managed flow, or correct the custom path |
| A lesson/SAR engine is missing | Configure its separate native executable paths |

Saved custom paths do not disable included digital tools. Choose **Custom tools**
explicitly to use your installation; switching modes preserves those paths and
existing project platform selections. The [digital guide](DIGITAL_FLOW.md) covers
platform locks and headless setup.

The current Windows build recipe has no signing step. Consumer-machine,
signing-policy and physical-network acceptance remain tracked in
[release follow-ups](RELEASE_FOLLOWUPS.md).

## Verify a download

Use the checksum file supplied with the exact build. On Linux, a complete set
can be checked with `sha256sum -c SHA256SUMS-0.23.0.txt` if that is its
actual filename. On Windows:

```powershell
Get-FileHash .\IC-Design-Studio-0.23.0-Windows-x64-Setup.exe -Algorithm SHA256
```

Compare the result with the matching checksum entry. If you downloaded only a
subset, verify those specific entries; missing optional evidence files do not
mean the application bytes were checked.

## Archived dev25 download snapshot · 2026-09-30

As checked through authenticated GitHub metadata on **2026-09-30**, the two
latest completed draft preparations listed below were **unpublished drafts**,
with 23 assets each. A draft is visible to maintainers; its existence does not
establish a public download or consumer acceptance. This is a dated snapshot,
not the identity or acceptance record of 0.23.0.

| Candidate | Packaged source | Completed preparation |
|---|---|---|
| [Main draft](https://github.com/jonahsaunders/IC-Design-Studio/releases/tag/untagged-acb598aac62045d768f7) | `168976360c18a0c5fa038bf9e8b89e85c6d781a8` | [Run 36509225273](https://github.com/jonahsaunders/IC-Design-Studio/actions/runs/36509225273), successful |
| [Experimental draft](https://github.com/jonahsaunders/IC-Design-Studio/releases/tag/untagged-675c8eb70526765cc344) | `c33cee4dbbab1cdafb03f11a7aa1d11b08230c57` | [Run 36559252677](https://github.com/jonahsaunders/IC-Design-Studio/actions/runs/36559252677), successful |

Both use version **0.22.0.dev25**. Later experimental source, including the merged
README update at `34c4a9a7d94c8bcc234ef579186676c866053d9c`, is different.
Use the full commit, not the version alone, to identify a package. See
[release status](RELEASE_STATUS.md) for the dated evidence and remaining gates.
That metadata review did not independently download or re-hash package bytes.
