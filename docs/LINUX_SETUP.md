# Linux launch and setup

## Complete desktop package

The Linux desktop targets **x86_64, glibc 2.39 or newer** (Ubuntu 24.04 baseline).
Use the [download guide](DOWNLOADS.md) to select a package and verify its source
identity. Extract the entire archive into a writable location, enter the
`ICDesignStudio` directory, and run:

```sh
./ICDesignStudio
```

Keep `_internal` beside the executable. Python, PySide6, KLayout, native ngspice,
simulation PDK subsets, the managed digital/physical tools, VGA assets and the
independent openEMS runtime are included in the current packaging recipe. A
source ZIP or lone executable does not contain that complete runtime.

A graphical X11 or Wayland session and the platform's graphics/font libraries
are required. The bundle stages desktop loader libraries but does not replace
system glibc. For a loader failure, run the executable in a terminal and inspect:

```sh
ldd ./ICDesignStudio
ldd ./_internal/PySide6/Qt/plugins/platforms/libqxcb.so
```

The Qt plugin path can differ by build; locate the actual `libqxcb.so` under
`_internal`. Qt WebEngine additionally needs the libraries listed in
[VGA source setup](VGA_PLAYGROUND.md#source-setup-and-desktop-packaging).
Build-host package prerequisites are recorded in
[the desktop workflow](../.github/workflows/build-desktop.yml).

## First circuit and engines

Open **File → Start here / example gallery → Your first waveform → Open a copy**
and press **F5**. The teaching example needs no external tools. Native SPICE and
included process-model examples use the bundled native ngspice.

For digital implementation, let **Included tools → Set up and verify** complete.
The private native runtime needs several GB and runs actual installation checks.
Use **Digital → New digital counter example**, then **Run stage**. See
[digital setup](DIGITAL_FLOW.md#included-tools-and-first-setup).

For process layout verification, open **Tools → Physical tools setup…** and
select the included Magic/Netgen/ngspice tools, or explicitly choose custom tools.
Setup is shared with the digital runtime. Physical checks still require matching
locked PDK assets and decks; included analog simulation subsets are insufficient.
Register included simulation packages or a compatible external PDK through
**File → Project Hub… → PDKs**. See the [PDK guide](PDK_GUIDE.md).

Student Hub Digital lessons use the selected Included or Custom digital
toolchain and open setup when needed. SAR experiments, Mixed Signal lessons and
the capstone require native local ngspice and Icarus separately. On Ubuntu,
`sudo apt install ngspice iverilog` supplies those native tools. Check them in
the [lesson setup](STUDENT_HUB.md#engines-and-models) or
[SAR Local engines tab](MIXED_SIGNAL_SAR.md#local-engine-setup).

## Source launch

Follow the [README source instructions](../README.md#start-in-three-steps) in a
Python 3.12 virtual environment. Install native ngspice for SPICE examples.
`launch-linux.sh` creates a local `.venv` with the available `python3` and
installs requirements on its first run; the explicit README commands let you
choose the reference Python 3.12 interpreter.

Python requirements do not create the managed runtime or VGA assets. Use custom
tools or build the required assets as described in [digital design](DIGITAL_FLOW.md)
and [VGA Playground](VGA_PLAYGROUND.md). Source openEMS setup is described in
[its guide](OPENEMS.md#custom-installations-and-source-builds).

## Launch and package checks

To exercise the packaged app with an isolated test profile:

```sh
./ICDesignStudio --release-test /absolute/path/to/new-launch-check
```

The check opens Qt widgets, saves/reopens a project, runs a worker and tests
editing. It writes `release-test.json` and screenshots. On a host without a
display, prepend `QT_QPA_PLATFORM=offscreen`; a headless pass does not establish
graphics-driver or native desktop behavior.

Packaged physical probes can use `ICSTUDIO_PROBE_PDK_ROOT`,
`ICSTUDIO_PROBE_MAGIC`, `ICSTUDIO_PROBE_NETGEN` and
`ICSTUDIO_PROBE_NGSPICE` as explicit test inputs. Ordinary users configure the
engine selection in Studio. Never copy temporary build-host wrappers into a
normal installation's settings.

Use [native acceptance](NATIVE_DESKTOP_ACCEPTANCE.md) for clean-machine,
display/scaling, accessibility and upgrade observations. The archived
[dev25 package handoff](DEV25_ACCEPTANCE_HANDOFF.md) identifies one earlier
hosted-qualified build; subsequent source changes need their own package records.
Historical offscreen or fresh-profile runs do not qualify every Linux desktop.
