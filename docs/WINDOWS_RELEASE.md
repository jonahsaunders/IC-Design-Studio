# Build and verify the Windows desktop release

Status: the dev25 [hosted release run](https://github.com/jonahsaunders/IC-Design-Studio/actions/runs/35550664971)
passed Windows Server 2022 installer execution, installed DPI probes and portable
archive checks at `a88cfe1cfe20254638b7bd97ec9128e843578282`. Clean consumer
Windows 10/11 acceptance remains open. See the [acceptance handoff](DEV25_ACCEPTANCE_HANDOFF.md).

## Build on Windows 10/11 x64

1. Install x64 Python 3.12 and Inno Setup 6 from https://jrsoftware.org/isinfo.php.
2. For the optional C++ solver, install Visual Studio Build Tools with the x64 C++ toolchain. The build script initializes its environment if available; otherwise the Python solver is used.
3. Extract the entire source ZIP. Run `build-windows.bat`.
4. Deliverables appear in `dist/installers`: the Setup EXE, portable ZIP, complete source and checksums.

The installed app includes Python, Qt, KLayout, NGSpice 42, and GF180MCU/SKY130 simulation PDK subsets. It does not require a browser, server, account or a separately installed Python. The build stages and executes NGSpice before packaging and checks the final bundle. Additional PDKs, physical verification engines and IHP OSDI plugins are configured separately.

The installer uses a per-user application directory and does not request administrator privileges. It offers optional desktop and .icproj Open With registration. User projects and application data are retained by uninstall. No publisher signature or automatic updater is configured.

## Verification

Run `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify_windows.ps1` in a disposable Windows test account. It installs into an isolated test directory, exercises the installed executable at three DPI scales, checks shortcuts/registration, and uninstalls. It changes the test account's application registration and shortcuts while running.

Evidence is saved under `build/windows-evidence`. The frozen executable's `--release-test <directory>` mode writes a machine-readable report and screenshot, including a real worker simulation. The GitHub Actions workflow runs core and GUI regression tests before installer verification, then retains build/evidence artifacts even on failure.

The hosted run completed these automated checks. Human checks for display transitions,
accessibility, installation upgrade behavior and normal keyboard/mouse use still
need consumer-machine records. Passing hosted execution alone does not close them.

Installer references: https://jrsoftware.org/ishelp/topic_setup_architecturesallowed.htm and https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm.

## Historical 0.6–0.8 verification additions

The desktop CI job also runs gui_project_pdk.py, gui_lifecycle.py, gui_usability.py , gui_silicon.py and gui_hierarchy.py before packaging. The installed-app probe verifies independent project duplication, parameterized SPICE component import, the simulation runtime dialog the physical workflow tab, and saved-testbench editor/persistence in addition to save/reopen, keyboard and worker checks. The workflow provisions Inno Setup when it is missing. These definitions have been prepared and Linux-tested where applicable, but still require execution on Windows. The actual Magic/Netgen/ngspice physical flow is qualified on Linux only; automatic Windows/WSL tool installation and path translation are not implemented.
