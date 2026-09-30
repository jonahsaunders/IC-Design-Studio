# Build and verify the Windows desktop release

The supported build recipe is the
[Windows job in the desktop workflow](../.github/workflows/build-desktop.yml).
It builds a package from a clean Git commit and executes the installed app and
portable archive. Use [downloads](DOWNLOADS.md) to install an existing desktop;
the steps here are for release builders.

The archived dev25 [hosted run](https://github.com/jonahsaunders/IC-Design-Studio/actions/runs/35550664971)
passed Windows Server 2022 installer, DPI and portable checks at
`a88cfe1cfe20254638b7bd97ec9128e843578282`. Those results belong to that package.
The [acceptance handoff](DEV25_ACCEPTANCE_HANDOFF.md) records its consumer
Windows 10/11 checks separately; newer source needs fresh qualification.

## Prepare a Windows x64 build

1. Use a **clean, committed Git checkout** of the selected source. A source ZIP
   has no Git build identity and cannot by itself produce a qualified package.
2. Install x64 Python 3.12, Git, Node.js 22.12+ (or 24), and
   [Inno Setup 6](https://jrsoftware.org/isinfo.php).
3. Create a Python environment and install `requirements-build.txt`. For the
   optional C++ solver, install Visual Studio Build Tools with the x64 C++
   toolchain. Without it, the Python solver remains available.
4. Build the pinned VGA assets with `python scripts/build_vga_playground.py --test`.
5. Stage `build/digital-payload` from the selected source's runtime build. The
   [runtime workflow](../.github/workflows/digital-runtime.yml) runs
   `python scripts/build_digital_runtime.py` on Linux with Docker and exports
   the `digital-runtime-payload` artifact. Copy the whole payload, not just its
   manifest.
6. Enable WSL 2 on the Windows build host, then run
   `python scripts/qualify_digital_runtime.py` in this checkout. It must create
   `qualified-Windows.json` for the staged payload after actual engine checks.
7. Run `build-windows.bat` or, from the prepared environment,
   `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_windows.ps1`.

The build stages and tests native ngspice 42, runs unit tests, packages the app,
and builds the installer. `scripts/package.py` stages the independent openEMS
runtime and rejects missing VGA assets, an unqualified managed payload or
unknown/dirty source identity. Download/build steps need network access and
substantial disk space; Python requirements alone are insufficient.

Deliverables appear in `dist/installers`: the Setup EXE, portable ZIP, source
archive and checksums. These builder outputs still need the verification below
and the [complete release workflow](RELEASING.md).

## Included tools and installer behavior

The current package contains Python, Qt, KLayout, native ngspice, the SKY130/GF180
simulation subsets, offline VGA assets, openEMS, and the qualified managed
digital/physical runtime. The managed runtime includes the digital engines,
SKY130 HD platform and Magic/Netgen/ngspice for supported physical checks.
Matching physical PDK assets/decks and IHP OSDI plugins remain separate.

Studio installs its managed Linux environment through visible setup. The
installer itself is per-user and requests no administrator privileges; enabling
Windows Linux support can separately prompt for elevation and require a reboot.
The package does not replace other WSL distributions. See
[digital first setup](DIGITAL_FLOW.md#included-tools-and-first-setup).

The installer offers optional desktop and `.icproj` registration and registers
the `icstudio:` invitation protocol. Uninstall retains user projects and
application data, including installed managed runtimes. No signing step or
automatic updater is configured in the current recipe.

Student Hub and SAR use native local Icarus, independently of the managed
toolchain. See [lesson engines](STUDENT_HUB.md#engines-and-models).

## Verify the exact package

In a disposable Windows test account, follow the desktop workflow's physical
adapter preparation before installed-app verification:

```powershell
python scripts/verify_frozen_digital.py
python scripts/fetch_sky130_reference.py --physical-only --output build/qualification-pdk
python scripts/prepare_sky130_qualification.py --input build/qualification-pdk/sky130A --output build/physical-adapter/sky130A
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify_windows.ps1
```

Use fresh evidence directories. The Windows verifier installs into
`build/windows-evidence/Installed App With Spaces`, executes the installed app
at 100/150/200% scaling, checks VGA and supported physical workflows, verifies
shortcuts and associations, and uninstalls. It changes that test account's
registrations and shortcuts during the check. Evidence remains in
`build/windows-evidence`.

The `--release-test OUTPUT` probe writes machine-readable results and images,
including actual worker execution. The release pipeline separately exercises the
extracted portable archive and hashes the exact assets; see
[release preparation](RELEASING.md). A source test, a successfully built EXE or a
different installer does not substitute for those package checks.

Human display transitions, mixed-monitor behavior, accessibility, upgrades and
ordinary keyboard/mouse interactions require
[native consumer acceptance](NATIVE_DESKTOP_ACCEPTANCE.md). Retain the package
hash and source commit with every record. Earlier 0.6–0.8 notes that described
Windows/WSL execution as unimplemented are superseded by the current source and
the dated hosted evidence; they are not current setup instructions.
