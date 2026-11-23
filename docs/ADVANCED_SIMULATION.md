# RF network analysis and external simulators

Open **Analysis → Advanced simulation**. Both workflows use Simulation Explorer
for run history, cancellation and rerunning the captured inputs.

## Measure a circuit's network parameters

1. Open the fixture schematic and give each port's signal and return identifiable
   net names. Set up bias and coupling in the fixture as needed.
2. Choose **RF network analysis…**. Enter one to eight ports, one per line.
   A line such as `out 0 0.9` means signal `out`, return `0`, and 0.9 V DC at the
   internal source. Port numbers follow the row order. Use one real reference
   impedance for all ports. For a one-port sweep, Studio gives ngspice an
   isolated matched termination as its required second port and reports only
   the requested port.
3. Enter the start and stop frequencies, number of linearly spaced points,
   model corner and temperature. Run the analysis. ngspice places an internal
   voltage source and series reference impedance at each port. The impedance
   also loads the circuit at DC, so inspect bias conditions in the fixture.
4. Select the completed result and choose **Inspect RF parameters…** to view
   magnitude, phase, real or imaginary components. The Y and Z conversions use
   the same reference impedance. A conversion that is singular or
   ill-conditioned anywhere in the sweep is reported as unavailable.
5. Choose **Export RF Touchstone…** to write the complex S matrix in RI format
   to an `.sNp` file. The run retains the exact generated SPICE deck, ngspice
   output and the engine executable hash.

A two-port check uses a single 50 Ω series resistor between `in` and `out` and
50 Ω port references. Across the sweep, `S11 = S22 = 1/3` and
`S21 = S12 = 2/3`. The admittance matrix is defined and the impedance matrix
is singular because the device under test has no shunt path. A grounded
three-port check verifies the corresponding complex matrices, including
`Z11 = 100 Ω`, `Z12 = 50 Ω` and an independent `Z33 = 100 Ω`. Both were
verified with native Windows ngspice 46.

The sweep is small-signal at the DC operating point. Its reference planes
are the specified fixture terminals. De-embedding, mixed-mode conversion,
RF noise and large-signal periodic analysis are outside this workflow. See the
[ngspice manual](https://ngspice.sourceforge.io/docs/ngspice-46-manual.pdf) and
[Touchstone specification](https://ibis.org/touchstone_ver2.0/).

## Run a deck with another installed simulator

Choose **Run external simulator…** and select the simulator's own deck or
argument file. Supply these fields in the dialog.

| Field | Input |
| --- | --- |
| Simulator executable | Full path or a command on PATH. Install and configure the simulator and its license before running. |
| Arguments | Enter one argument per line. Use `{input}` as the deck or argument-file token. Supply the remaining flags according to the engine version and deck. |
| Additional input files | List each fixture dependency relative to the selected file's folder. Studio captures the named files by value. Use self-contained relative includes when a replay must reproduce every input. |
| Required outputs | List files or folders the engine should create in its working directory. A run with missing required outputs fails. |
| CSV result to plot | Optional. Use a single file with a header, one increasing sweep column and numeric trace columns. Fields named `INDEX` or `STEP` are excluded. Other output formats remain available in the run folder. |

The engine runs directly with the configured argument list. Studio captures
its executable hash, the selected input bytes, the log and hashes of the
requested output files. Use **Open external run folder** with a run selected
in Simulation Explorer. Keep absolute includes, simulator-specific libraries
and license setup available if the deck uses them. An external run is stored
with the active project, and its input deck governs what the simulator runs.

For a known working setup, choose ngspice and a deck containing an analog
analysis. Enter `-n`, `-b`, `-r`, `wave.raw` and `{input}` as five lines, and
require `wave.raw`. A divider with two 1 kΩ resistors and a 1 V source was
verified through this workflow. It produces 0.5 V even after the original
load file changes, because the run uses the captured copy.

## Scope of the first implementation

| Workflow | Evidence |
| --- | --- |
| Native S, Y and Z with Touchstone export (RF-02, RF-03) | Windows ngspice 46, analytical one-, two- and three-port references, and a desktop queue, plot and export pass. |
| Configurable simulator execution (SIM-21) | A real ngspice deck verified the external command, captured dependency, run reuse inputs and artifact integrity. |
| Xyce harmonic balance (RF-10) | The runner accepts an engine-authored deck and can preserve output or plot a compatible CSV. Actual Xyce execution requires a working local build and remains unverified. |
| Cadence PSS, periodic AC/noise, harmonic balance, envelope and X-parameters (RF-09–13) | A licensed Cadence solver and reference runs are needed to verify deck execution and output. Native setup and vendor-output import remain pending. |
| Mixed-signal HDL (AMS-01–09) | A Cadence AMS command can be supplied to the external runner with its inputs. Native Verilog-AMS authoring, view binding, co-simulation and vendor-result inspection remain pending. |

See the backend references for [Xyce](https://xyce.sandia.gov/documentation-tutorials/),
[Cadence SpectreRF](https://www.cadence.com/en_US/home/tools/custom-ic-analog-rf-design/circuit-simulation/spectre-rf-option.html),
and [Cadence AMS Designer](https://www.cadence.com/en_US/home/resources/datasheets/spectre-ams-designer-ds.html).
