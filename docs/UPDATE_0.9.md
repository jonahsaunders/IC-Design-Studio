# IC Design Studio 0.9.0 — analog characterization

This native desktop engineering preview continues the verified 0.8.0 source.
It completes an analog schematic/characterization slice of the proposed 0.9
roadmap, plus initial process-adapter contracts and coordinated layout movement.
It does not complete the whole roadmap: GF180 native physical generation and
qualification remain pending.

## Start an analog design

1. Install one of the supplied PDK packages in **Tools → PDK manager**, then link
   its revision to your project. Existing locks are retained; no PDK files changed.
2. Choose **File → New PDK current mirror** or **New PDK differential pair**.
   These create a new project with an editable two-transistor circuit, reusable
   symbol, separate source/load fixture, and saved OP and DC benches.
3. Edit the circuit, symbol and fixture using the existing native views. The
   recipes select explicit standard four-terminal models and tie each body to
   the declared VSS port. SKY130 uses `sky130_fd_pr__nfet_01v8`; GF180 uses
   `nfet_03v3`. Both recipes use W=10 µm and L=1 µm, emitted through the PDK's
   existing unit conversion and parameter binding.
4. In **Saved testbenches**, choose the OP or DC bench. Configure ngspice in
   **Tools → Engine diagnostics & paths**.
5. Choose **Analysis → Configure saved-bench characterization**. Sweep a numeric
   source/load property, a PVT combination, or a declared component tolerance.
   Choose **Run saved-bench characterization** to execute the saved setup.

The current mirror uses a 50 µA reference, a forced output voltage, and a 0 V
sense source. Its DC bench sweeps output voltage and characterizes three reference
currents. The differential pair uses two 10 kΩ resistive loads and an ideal 100 µA
tail source. Its OP study changes differential input; its DC study compares
temperature cases. These ideal fixtures are editable; they do not establish
physical bias-generator, noise, startup or mismatch behavior.

## Measurements and case comparison

- **Current** measures a fixture voltage source. Positive current flows from its
  positive terminal to its negative terminal. AC measurements use magnitude.
  The source is saved explicitly; no manual SPICE editing is needed.
- **Voltage** optionally subtracts another saved probe, specified under
  **Reference net**. AC subtraction uses complex phase, then reports magnitude.
- **At** interpolates a measurement at an analysis coordinate, including a
  descending DC sweep. A blank coordinate keeps the existing last-sample behavior.
- Frequency, inverting delay and range measurements remain available.
- Every saved measurement limit is checked for every case. A failed measurement
  or engine run remains a failed row and makes the overall characterization fail.

The **Characterization** tab displays per-case values, units, status and failure
details. Select up to eight rows, choose a voltage/current probe, and click
**Show waveforms**. Each trace retains its own sampled coordinates. **Export CSV**
exports all measurements and failure details.

Study settings live inside the saved bench and support project save/reopen and
undo/redo. The selected bench controls the fixture, analysis, model corner,
temperature, probes and limits even when the circuit layout or another cell is
active. Changes mark earlier results stale. Undo advances the project revision,
so a fresh run is still required. Changing projects clears the comparison panel.

Each study retains `input.json`, `report.json`, and case directories containing
the actual input, SPICE decks, raw ngspice output, result and failure evidence.
Waveform opening checks its recorded checksum and project/cell/design identity.
The worker result remains tied to the original job snapshot. Monte Carlo here
uses user-declared independent component tolerances, not foundry mismatch models.

## Physical workspace and PDK capabilities

**Design → Transform layout selection** now has **Move cell ports and labels**.
Choose Yes only after selecting all shapes and physical placements in the active
cell. Named ports, text labels and assigned terminals then move/rotate/mirror
together in one undoable transaction. Partial selection is rejected. Parent
routes stay fixed when a child interface moves; check connectivity afterward.

The initial process adapter owns SKY130 native recipe dispatch, layer contracts
and locked Magic/Netgen input selection. Physical engine files must be present
in the linked lock and match their hashes. PDK Manager separately reports
registration, indexed/placeable symbols, simulation bindings, native recipes,
and bounded release physical evidence. A catalog entry or package metadata
cannot enable an unimplemented adapter. Physical evidence refers to specific
release fixtures, never automatically to the current edited design.

| Process | Analog recipes | Native physical generation in this release |
|---|---|---|
| SKY130A, revision `b19a81c06779a79d` | NMOS mirror and differential pair | Existing standard 1.8 V MOS, inverter and ring |
| GF180MCU C, revision `a1610a6b160f44d6` | NMOS mirror and differential pair | Pending; models and tool assets do not establish qualification |
| IHP SG13G2, revision `4a83d130587a7404` | No new recipe | Pending; existing model workflow requires compatible OSDI libraries |

The new analog circuits have schematic simulation evidence, not completed
physical implementations. SKY130 geometry generation and capacitance-only
extraction retain their previous bounds; full distributed RC and fabrication
signoff remain outside this release.

## Automation

From a project with the desired linked PDK:

```sh
python main.py --cli analog linked-project.icproj --kind current_mirror --output mirror.icproj
python main.py --cli characterize mirror.icproj --testbench current_mirror_dc --ngspice ngspice --output mirror-study
```

`--kind differential_pair` creates the second recipe. `characterize --spec study.json`
overrides the saved study for that run. Outputs must use a new/empty directory.
The CLI exits with failure if any case fails its measurements or simulator run.

## Verification and continuation

The accompanying evidence package records the actual executed checks and tool
provenance. Core tests cover the new measurements, complex AC subtraction,
descending-sweep interpolation, process gating, case failure retention,
waveform integrity, PVT section selection, deterministic tolerances and complete
annotation movement. `scripts/verify_analog.py` uses actual ngspice and checks
mirror compliance, differential-pair polarity/balance, Kirchhoff current balance,
SPICE export equivalence, reversed sense polarity and deliberately impossible
measurement limits. `tests/gui_analog.py` exercises the actual native editor and
ngspice worker, overlays, round trips, freshness and layout movement.

Remaining roadmap work: bounded GF180 MOS/inverter geometry with actual DRC/LVS
and pre/post-layout qualification; physical mirror/pair recipes; via placement,
path stretching and alignment; richer DRC/LVS navigation. Existing Windows
build definitions remain available; no Windows execution or installer
qualification is claimed. See the final release manifest for the exact platform
and regression outcomes from this build.
