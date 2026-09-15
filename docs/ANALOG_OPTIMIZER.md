# Analog optimizer

Open **Analysis → Analog design workspace → Optimize**. This tool runs the
existing analog simulators and retains every candidate as a separate saved job.
No additional optimization package or new simulator is required.

![Circuit search and candidate review](images/analog-workspace/optimizer.png)

## Guided starting point

Open **Setup → Guided design setup** (also available in Circuit search). Choose
an amplifier, differential pair or current mirror, then map the DUT's exposed
ports. **Add teaching example** supplies an editable generic DUT when starting
from an empty project. Enter explicit DC voltages for any unused bias ports.

Enter supply, load, gain, bandwidth and power goals; settling time is optional.
The current-mirror template uses reference current, ratio, tolerance and output
compliance instead. Additional stimulus and sweep settings sit behind a disclosure
control. **Preview setup** shows the actual requirements and expressions.
**Create setup** adds fixture cells, saved analyses, editable testbenches and a
PVT plan in one undoable operation. The fixtures reference the original DUT, so
subsequent sizing changes reach every test. No simulation runs until requested.
Native saved testbenches use ngspice and preserve the original root model scope.

![Review generated analyses and measurements](images/analog-workspace/guided-setup.png)

## Circuit search

1. In **Setup**, save an analysis or testbench and its scalar measurement limits.
   For multiple tests or operating conditions, create a plan in **Results matrix**.
   Save all variable/limit drafts before running a search.
2. In **Optimize → Circuit search**, choose that analysis or analog PVT plan.
   Choose the cell containing the adjustable parameters. Editing a shared cell
   master changes every instance of that master; this is stated in candidate review.
3. Select the objective test, a scalar expression, its unit, and **Minimize**,
   **Maximize**, or **Target**. Existing saved limits remain hard constraints.
   For example, maximize `final(V("vout"))`, with `V` as the unit. Use the waveform
   calculator's supported scalar functions for gain, delay, settling, and other
   measurements appropriate to the chosen analysis.
4. Add one to eight parameter axes. Each has lower/upper bounds and a sample
   count. SI prefixes such as `2u`, `10k`, and `100n` are supported. Project
   variables use `@name`; instance fields use existing names such as
   `M1.params.w`, `R1.value`, or a native device parameter. Choose **Linear**,
   **Logarithmic** (positive bounds), or **Integer** spacing. Integer samples are
   deduplicated; finger counts/multiplicities and their links must remain positive
   integers. Declared editable catalog fields such as `M1.model_params.nf` are
   available alongside native fields. Derived catalog expressions remain live.
5. Optional matching/ratio links share an axis: in **Linked target = ratio**,
   enter `M2.params.w = 1` for equal widths, or `M2.params.w = 2` for twice the
   swept width. Separate multiple links with commas. Every target may occur only
   once. Links are numerical relationships in this search, not persistent layout
   matching constraints.
6. Optionally enable **Add gm/Id and bias limits**, choose an operating-point test
   and MOS instance, and enter minimum/maximum gm/Id and/or minimum bias margin.
   Missing required device values fail the candidate.
7. Choose **Adaptive · sensitivity first**, **Gaussian process · experimental**,
   or **Exhaustive grid**, a simulation budget, and **Run search**. Every passing
   candidate must complete every test and PVT condition. The total must fit the
   budget, with an absolute maximum of 500 jobs. Overlapping plan, supply, or corner overrides are rejected instead
   of silently cancelling a search parameter.

Use **Add trade-off objective** to add up to two further objectives, possibly
from other tests in the plan. Results show each objective separately, with its
unit and direction; the exact expressions remain in the review text and CSV.
A **Pareto** candidate passes every constraint and has no other passing tested
candidate that is at least as good in every objective and better in one. There
is no single automatically preferred candidate for a multi-objective experiment.

Adaptive mode begins at the nearest allowed saved/seeded parameter values and
runs independent neighboring probes. **Show parameter sensitivity** reports
local finite differences of worst-condition metrics, scaled over the requested
parameter range. Linked parameters move together, and the worst PVT condition
can change, so these are local trends rather than causal explanations.

Further adaptive candidates use deterministic bounded pattern search around
measured promising/Pareto points, including paired parameter moves, with global
grid coverage when local proposals are exhausted. Samples define discrete
parameter resolution. Adaptive pattern search does not guarantee a global optimum. The simulation
budget includes all test/PVT jobs for the initial probes and later candidates;
manual retries are additional executions of existing conditions.

**Candidates per adaptive batch** accepts 1–8. Independent candidates can use the
existing parallel job queue; each next batch waits for the preceding batch's
required evidence. All proposals are persisted before execution. A changed engine
environment stops continuation instead of mixing incomparable evidence.

**Screen operating points before expensive tests** runs all saved OP conditions
first. Candidates that fail these checks are **Screened out**; their remaining
analyses are never queued or represented as simulated. Accepted candidates still
complete all required tests and PVT conditions before they can pass or apply.
The progress display counts executed jobs separately from avoided jobs. The
budget conservatively reserves the full plan per candidate; screening savings
are not used to silently increase the number of candidates. Cancel and restart
pause deferred stages until explicit resume.

The optional Gaussian-process backend learns from measured candidates. It uses
a fixed RBF kernel, rotating normalized objective weights, expected improvement,
and an approximate feasibility surrogate. Training is bounded to 64 observations
and proposals to 256 per step. It has no additional package dependency. Predicted
values guide search only; they never appear as verified measurements or yield
probabilities. This option remains experimental and adaptive remains the default.

An equal-budget ngspice-46 benchmark used 24 simulations per method and circuit:

| Circuit / measured goal | Adaptive | Gaussian process |
| --- | ---: | ---: |
| Divider: minimum supply current within output limits | 9.00 µA | 83.11 µA |
| MOS: absolute error from a 20 µA current target | 3.65 µA | 0.225 µA |

These two small deterministic examples show different strengths, not a general
advantage. Reproduce with `scripts/benchmark_analog_search.py --executable /path/to/ngspice --out benchmark.json`.

Adaptive batches are checkpointed before enqueueing and continue while the
workspace is hidden. Cancel pauses further proposals. After application restart,
an incomplete experiment stays paused until **Resume incomplete**. Saved
settings can be restored with **Reuse experiment settings** for a new run on the
current design. Engine changes reject replay of old unfinished jobs.

![Adaptive multi-objective results](images/analog-workspace/adaptive-tradeoffs.png)

Ranking uses the worst objective condition: maximum value when minimizing,
minimum value when maximizing, or maximum absolute error when targeting a value.
A candidate passes only after every associated job completes, its objective is
valid, and all saved limits, testbench measurements, and enabled device limits
pass. Failed, missing, cancelled, and interrupted work remains visible.

Select a candidate to review current/proposed parameters and failure details.
Use **Show failed requirement** to open its exact saved waveform and referenced
net/devices, or choose a saved condition and **Inspect saved run** to see its original circuit,
waveforms, and diagnostics. **Apply selected candidate** becomes available after
the search finishes and the selected candidate passes. Applying checks the
original design identity again and uses the normal undo history. A changed
circuit or unsaved Setup draft blocks application. Undo creates a new revision,
so a new search is required before applying historical candidates again.

**Cancel remaining** stops this experiment's queued/running jobs. **Resume
incomplete** retries missing, interrupted, cancelled, or engine-failed jobs using
their captured inputs. Completed candidates with failed performance limits are
retained rather than rerun unchanged. Experiments and results reload from the
existing local job store. **Export CSV** includes numerical values at full stored
precision, parameters, failures, and the experiment/base design identities.

## gm/Id explorer

![Captured gm/Id values and sweep curve](images/analog-workspace/gmid.png)

Save an **operating-point** analysis first. In **gm/Id explorer**, choose that
analysis, a MOS instance, a parameter cell, and one parameter to sweep. Usually
this is a gate-bias source, but it may also be width, length, or a project variable.
Other parameters and the saved corner/temperature remain fixed. Run 2–100 points.
For a testbench circuit, save an operating-point analysis of its bench cell.
The separate saved-testbench flow currently captures selected probes without
the primitive MOS vector contract, so it is not offered as a gm/Id source.

The table and plot use captured `abs(gm / Id)`, in 1/V. Signed drain current,
gm, VGS, VDS, and `abs(VDS) - abs(VDSAT)` bias margin are shown when available.
Negligible/zero current, missing vectors, and simulation failures remain explicit;
the curve leaves gaps instead of interpolating across missing samples. These are
in-circuit operating points: changing gate bias can also change drain/body bias.

For teaching primitive MOS devices, the explorer also resolves each selected
hierarchy instance's actual W/L, including instance parameter overrides, and
calculates `abs(Id) / W`. Enter a desired drain current and select a point to
estimate `W = desired current / current density`. This is an initial estimate at
the captured length and bias. It does not change the design; validate proposed
widths with Circuit search before applying them.

Native/process MOS readouts use the existing explicit model-vector mapping.
gm/Id does not require a width convention. The explorer deliberately leaves
width-normalized density/sizing unavailable for native or catalog-bound devices,
where model units, fingers, multiplicity, and internal subcircuit paths can differ.
Their explicit numeric sizing parameters can still be swept in Circuit search.

## Isolated-device characterization library

Open **Optimize → gm/Id explorer → Device characterization library**. Choose an
existing MOS device, comma-separated lengths, forward gate/drain biases, reverse
body biases, temperatures and deterministic corners. **Characterize / reuse
cache** either runs the isolated fixtures or reuses an exact matching cache.
The **Size and transfer** tab accepts a gm/Id and absolute drain-current target
and displays estimated W, L and forward gate bias. Select an estimate to populate
an adaptive search's sizing ranges and initial seed; it does not edit the circuit.
Set the appropriate circuit bias in the editable fixture and verify the search.

The process adapter supports the pinned standard SKY130 `nfet_01v8`/`pfet_01v8`
models with direct W/L emission, `nf=1`, and `m=mult=1`. It validates the model's
micrometre parameter scale, four terminals, locked definition checksum and exact
internal MOS path. Other native/catalog models remain usable in the in-circuit
explorer when they expose gm/Id, but do not receive invented width conventions.
The isolated process fixture uses the installed locked PDK model environment;
native DUT-specific model overrides must be verified in the actual circuit.

Library dimensions are metres, amperes, siemens and volts. Forward VGS/VDS mean
VSG/VSD for PMOS; positive VSB denotes reverse body bias for either polarity.
Density is `abs(Id)/total_drawn_W` in A/m. The generic teaching library supports
only zero body bias, 27 °C and nominal corner, with its square-law limitations.

Each experiment is bounded to 500 simulations. Tables retain signed Id/gm,
absolute gm/Id, density, bias, captured headroom, gds, intrinsic gain, available
intrinsic capacitances, sample status and source run
fingerprints. Cache identity includes the model/geometry contract, locked model
assets, grid and engine/workflow identity. Invalid samples remain explicit.
Multilinear interpolation requires complete enclosing samples and forbids
extrapolation or crossing missing data. Inverse gm/Id lookup exposes multiple
bias crossings as separate choices. Width scaling is an initial estimate,
especially when narrow-width effects change the model behavior.

Choose **Plot measurement** to inspect current density, gm/Id, gds, intrinsic
gain (`abs(gm)/gds`), intrinsic Cgg, or the intrinsic speed estimate
`abs(gm)/(2πCgg)`. **Compare characterized lengths** overlays the same bias slice
for each measured L. Exact values and source identities are available through
**Export measured data**. Missing neighboring capacitances remain unavailable
during interpolation; derived gain/speed metrics use interpolated raw vectors.

The SKY130 adapter captures signed Cgg/Cgs/Cgd/Cgb charge derivatives. The speed
estimate excludes overlap capacitance, wiring and circuit loading and is not
circuit bandwidth. The teaching solver supplies gds from its actual current
model but does not invent device capacitances. Zero/nonpositive gds or Cgg does
not produce infinite gain or speed.

**Size and transfer → Verify selected sizing with SPICE** creates a separate saved
ngspice job with the proposed W/L and bias. Both |Id| and gm/Id must be within 5%
of their targets for **Verified**; otherwise the errors are displayed as
**Outside tolerance**. Engine identity and circuit snapshot must match the saved
job. This checks isolated width scaling; circuit search must still verify the
actual DUT bias, performance requirements, and full PVT plan.

![Measured model lookup table](images/analog-workspace/characterization-library.png)

![Review sizing suggestions](images/analog-workspace/sizing-suggestions.png)

## Model and release boundaries

- The bundled teaching solver works without an external installation. Its
  square-law MOS model omits subthreshold current, body effect, and device
  capacitances. It cannot support meaningful weak-inversion, gm/C, fT, or
  transistor temperature analysis. MOS temperature sweeps require ngspice and
  suitable models; failures remain visible.
- Process simulation uses the existing ngspice setup and model assets. The tool
  does not generate PDK curves from generic equations or invent hidden device
  vectors. Existing engine identity checks govern resumed jobs.
- Searches are bounded and deterministic. Statistical yield optimization and
  noise characterization remain outside this implementation. No missing device
  capacitance/noise values are invented. The optional GP backend is experimental.
- Optimization accepts analog schematic analyses/testbenches and PVT plans.
  After applying a candidate, use **Layout and constraints** and **Verification
  runs** to update layout and validate extracted performance. An optimizer pass
  does not establish extracted or foundry-qualified performance.

The SPICE-generated lookup approach is described in
[Jespers and Murmann's gm/Id design resources](https://github.com/bmurmann/Book-on-gm-ID-design).
Device-vector availability follows the particular model and simulator; see the
[ngspice manual](https://ngspice.sourceforge.io/docs/ngspice-manual.pdf).

## Validation

`tests/test_analog_optimizer.py` exercises numerical NMOS/PMOS gm/Id, current
density, hierarchy overrides, ratio links, PVT budgeting, worst-condition ranking,
constraint evaluation, stale/mismatched evidence, and restart behavior. A real
ngspice test runs when `ICSTUDIO_TEST_NGSPICE` is configured.

`tests/gui_analog_optimizer.py --out build/analog-optimizer-evidence` runs real Qt
worker jobs and checks cancel/resume, apply/undo, saved-run inspection, gm/Id
readouts, CSV export, accessibility metadata, keyboard activation, and compact /
enlarged-text layouts in both appearances. See the
[Apple HIG audit](ANALOG_GUI_AUDIT.md) for its scope and remaining limitations.


`tests/test_analog_experiments.py` covers generated fixtures, native model scope,
adaptive sensitivity/budgets, Pareto constraints, cache identity, interpolation,
missing samples and sizing. Real ngspice/SKY130 tests cover both polarities,
body bias, temperature, corners and native saved testbenches when
`ICSTUDIO_TEST_NGSPICE` is set. `tests/gui_analog_experiments.py` exercises the
new flows through actual Qt widgets and worker jobs, including hidden-window
continuation, cache reuse and saved requirement/sensitivity navigation.
