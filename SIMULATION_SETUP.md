# ngspice and open PDK setup

Use the [download guide](docs/DOWNLOADS.md) for a complete Windows or Linux
desktop package, or follow the [source instructions](README.md#start-in-three-steps).
The source version is **0.22.0.dev25**; match any package to its exact commit.
The retained [dev10 simulation record](docs/validation/0.22.0.dev10.json) is
historical evidence, not the current package's acceptance result.

## Choose the simulation workflow

| Workflow | Engine and setup |
|---|---|
| First RC waveform and generic teaching circuits | Included teaching solver; no external engine or PDK |
| Native SPICE and imported control programs | Native ngspice; included in complete desktop packages |
| Process-model analog design | ngspice plus included SKY130, GF180 C/D or IHP subsets; IHP uses the included physical runtime by default |
| Digital simulation and RTL-to-GDS | [Included digital tools or a custom toolchain](docs/DIGITAL_FLOW.md) |
| Student Hub Digital lessons | The selected Included or Custom digital tools, with guided setup before running |
| SAR, Mixed Signal lessons and capstone | Native local ngspice and Icarus; [local engine setup](docs/MIXED_SIGNAL_SAR.md#local-engine-setup) |
| Inductor EM simulation | [Included openEMS runtime](docs/OPENEMS.md) plus declared process materials and layer data |

Digital and physical verification share a managed Linux runtime, using an
app-owned WSL 2 distribution on Windows. That runtime is separate from native
ngspice and from the native engines used by Mixed Signal lessons, the capstone
and SAR experiments. Student Hub Digital lessons use the selected digital tools.

## Start with a complete desktop package

1. Extract the entire portable archive, or install the Windows setup package.
   Keep `_internal` beside `ICDesignStudio.exe` on Windows or `ICDesignStudio`
   on Linux. A source ZIP is a different download.
2. Launch Studio. Open **File → Start here / example gallery**.
3. Choose **07 · GF180 bandgap startup → Open a copy**, then press **F5**.
4. Open **Analysis → Program analyses** for waveforms and measured final voltages.

Desktop packages include Python, Qt, native ngspice and SKY130, GF180 C/D and IHP
process subsets. The GF180/SKY130 gallery examples need no model download. IHP
uses the matching compiled models in the included physical runtime. First setup
of the separate managed toolchain takes additional time; Windows may need
internet access, administrator approval and a restart to enable WSL support.
See [digital first setup](docs/DIGITAL_FLOW.md#included-tools-and-first-setup).
There is no qualified macOS desktop package.

## Run from source

On Windows, install 64-bit Python 3.12 and run `launch-windows.bat`. It creates
an isolated environment under `%LOCALAPPDATA%\ICStudio`, installs the pinned
Python requirements, stages the checksum-pinned ngspice 42 runtime when needed,
and checks a real divider simulation before launch. Failed or interrupted
downloads are retried; an incomplete setup stops launch. A source archive may
include staged Windows ngspice files, but a Git clone does not include its native
binaries.

On Ubuntu, install native ngspice with `sudo apt install ngspice`. On macOS,
`brew install ngspice` supplies a native engine; that source workflow remains
unqualified. Install the Python requirements in the source environment as
described in the README.

Choose a custom engine in **Tools → Engine diagnostics and paths…**, or set
`ICSTUDIO_NGSPICE` to its executable. Blank settings allow Studio to discover
its bundled native engine or an installed one. Python requirements alone do not
install Icarus, the managed digital runtime, VGA assets or openEMS.

For offline Windows provisioning from an already downloaded official archive:

```sh
python scripts/stage_windows_ngspice.py --archive path/to/ngspice-42_64.7z --ensure
```

The archive must match the pinned SHA-256. Optional XSPICE code-model plugins
need compatible, separate runtime configuration. For bundled IHP, prepare the
included physical runtime through **Tools → Physical tools setup**. A custom
IHP revision or simulator needs matching OSDI libraries selected in **Simulation runtime**.

## Included process examples

The **GF180 bandgap startup** project changes only the control program of
`examples/gf180-bandgap/5vfullv2-original.sch` to one 5 V, 25 °C, 3 ms transient.
The retained Linux ngspice 42 run produced 30,035 samples and about **1.19507 V**
at VREF. This is an installation check, not complete circuit qualification.

**08 · GF180 full characterization** preserves the original supplied schematic
and runs its **144 analyses**. Allow several minutes or longer. Studio resolves
the supported `/foss/pdks/gf180mcuD/...` model includes using bundled primitive
files and relocates supported `/foss/designs/...` output tables beneath the
run's `outputs` folder. Choose **Open output files** in Program analyses.

**09 · SKY130 transistor inverter** runs a 12 ns transient with the included
1.8 V MOS models. The [example library](examples/README.md) also covers the
native Banba schematic, optimization and layout sequence and the SAR ADC.
These are separate circuits with their own conditions and qualification records.

## Start a native PDK project

Open **File → Project Hub…**, select an included PDK marked **Available offline**,
and choose **Install PDK & create project**. Registration is offline and
checksummed. Native PDK runs stage the locked model include closure into their
run folder, including when project/profile paths contain spaces.

| Included package | Simulation scope |
|---|---|
| GF180MCU C and D adapters | Primitive models, symbols and display layers; distinct C/D physical configurations |
| SKY130A | Primitive corner model closure; symbols and display layers |
| IHP SG13G2 | Primitive models, symbols, display layers and Verilog-A sources; matching compiled models in the included runtime |

These packages preserve upstream revisions, hashes and license notices. They are
bounded teaching subsets, not complete foundry PDKs. GF180 C/D and IHP include
the physical decks used by the qualified core-MOS inverter course. A process
label alone does not establish qualification for arbitrary device classes or layouts.

For physical checks, use **Tools → Physical tools setup…** for included
Magic/Netgen/ngspice or explicit custom tools, and supply matching locked physical
PDK assets/decks. The managed digital runtime separately carries the full SKY130
HD standard-cell platform for RTL implementation. Bundled IHP analyses and
imported programs automatically select its matching runtime when no custom OSDI
libraries are configured. See [PDK setup](docs/PDK_GUIDE.md).

## DC startup and inductor analysis

For native DC sweeps that repeatedly enter convergence stepping, enable
**Analysis → DC startup → Use first-point voltage guesses**. Studio solves the
first source value and uses its voltages as initial guesses. Existing nodesets
take precedence; solver-only internal nodes are excluded. Circuit parameters,
temperature and accuracy remain unchanged. The startup deck, raw result and
generated nodesets stay with the run evidence.

The [SKY130 detector guide](docs/OPEN_PROJECTS.md) generates a native bench with
this setting and both circuit/layout views. Open `overvoltage-bench.icproj` and
press **F5** on `detector_dc_bench`.

For inductor EM work, choose **Inductor creator → EM results → Run openEMS…**.
The [openEMS guide](docs/OPENEMS.md) describes the included solver, process data,
excitation fixture, convergence checks and retained results.

## Reproduce the simulation checks

Run from the repository root in its Python environment with native ngspice
available. Use a fresh output directory:

```sh
python scripts/check_simulation_assets.py
python scripts/verify_bundled_simulation.py --output build/simulation-check
# Add --full to include the unchanged 144-analysis characterization.
```

The asset check verifies models and symbols; the second command runs actual
ngspice examples and native process-device checks. Use `--ngspice PATH` or
`ICSTUDIO_TEST_NGSPICE` to select a specific engine. For a staged desktop bundle,
`check_simulation_assets.py --bundle PATH --runtime` additionally tests the
native runtime.

[Windows packaging](docs/WINDOWS_RELEASE.md) and [release preparation](docs/RELEASING.md)
describe the additional managed runtime, VGA, build identity and package gates.
A successful simulation does not establish every saved specification, native
consumer-platform acceptance or fabrication signoff.

## Historical dev10 evidence

The [dev10 local record](docs/validation/0.22.0.dev10.json) reported 439 tests,
a then-nine-entry gallery, seven short GUI worker simulations and the original
144-analysis characterization. Those counts and its unexecuted Windows/macOS
items describe that historical run. Current gallery contents and platform
records are documented in the [README](README.md#example-library) and
[release status](docs/RELEASE_STATUS.md); later hosted installer evidence does
not change the original local record.
