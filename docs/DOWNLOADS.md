# Get IC Design Studio

For the easiest digital-design experience, install a **complete desktop package**.
It includes Python, the application, digital engines, compiler dependencies and
the SKY130 HD platform. You do not need to install Icarus, Verilator, Yosys or
OpenROAD separately.

## Choose your download

Use the [Releases page](https://github.com/jonahsaunders/IC-Design-Studio/releases)
for published packages. Development source is **0.22.0.dev24**; a source update
does not necessarily have a published desktop release.

For the experimental branch, open a successful
[Build and verify desktop release run](https://github.com/jonahsaunders/IC-Design-Studio/actions/workflows/build-desktop.yml?query=branch%3Aexperimental).
Download its **release-Windows** or **release-Linux** artifact, then extract that
artifact to find the desktop package, matching validation record and checksums.
Downloading Actions artifacts requires a GitHub sign-in. Draft releases are
visible to maintainers until published.

| Asset suffix | What to do |
|---|---|
| `Windows-x64-Setup.exe` | Run the installer, then launch Studio |
| `Windows-x64-Portable.zip` | Extract the entire archive, then open `ICDesignStudio/ICDesignStudio.exe` |
| `Linux-x86_64.tar.gz` | Extract the entire archive, then run `ICDesignStudio/ICDesignStudio` |
| `Source-Windows.zip` / `Source-Linux.zip` | Developer source; these are not the complete digital desktop runtime |
| `Validation-*.json` / `Evidence-*.zip` | Build identity and the checks performed on that package |
| `SHA256SUMS-*.txt` | Checksums for the matching downloads |

Keep `_internal` and all its contents beside the executable. Copying only the
executable, or using **Code → Download ZIP**, does not install the digital tools.
Check **About** for the exact source commit and compare it with the downloaded
build. The version number alone may identify multiple experimental builds.

## First launch

1. Launch Studio. **Included tools (recommended)** is selected automatically.
2. Let the visible setup finish. Progress, detailed logs and retry are available
   in the setup window. Allow several minutes and several GB of free disk space.
3. Open **Digital → New digital counter example**, then press **F5**. If setup
   is still needed, Run opens it and continues after success. Editing the design
   during setup asks you to click Run again so an unexpected design is not run.

On **Windows x64**, the full digital flow uses Studio's private WSL 2
distribution. If requested, click **Enable Windows Linux support**, accept the
Windows administrator prompt, restart Windows and reopen Studio. Windows
components may need internet access; the digital engines and platform are
already in the desktop package. Existing WSL distributions are preserved.

On **Linux x64**, the included native runtime targets Ubuntu 24.04 and requires
glibc 2.39 or newer. macOS has no qualified desktop package.

## If setup needs attention

| What Studio reports | Next step |
|---|---|
| Source checkout has no included tools | Use the desktop package, or explicitly select Custom tools for development |
| Included archive or tools are missing | Reinstall the desktop package or extract the entire portable archive |
| Windows Linux support is unavailable | Enable it in the setup window, restart if requested, then retry |
| Setup did not complete | Expand setup details; correct the reported problem and retry. Open setup logs for retained evidence |
| Custom tool cannot be found | Select Included tools to use Studio's runtime, or correct the custom executable path |

Saved custom paths do not disable included tools. Choose **Custom tools**
explicitly when you want your own installation. Switching modes preserves those
paths. Existing project platform selections are also preserved.

The [digital guide](DIGITAL_FLOW.md) covers supported tools, platform locks,
custom configurations and headless setup. [Release status](RELEASE_STATUS.md)
records acceptance scope; passing CI does not establish all consumer-machine
configurations. Windows packages currently have no configured signing step.

## Verify a download

On Linux, run `sha256sum -c SHA256SUMS-0.22.0.dev24.txt` in the download directory.
On Windows, run `Get-FileHash .\IC-Design-Studio-0.22.0.dev24-Windows-x64-Setup.exe -Algorithm SHA256`
and compare it with the matching checksum file. Use the filenames supplied with
your exact build. A checksum for another build does not verify your download.
