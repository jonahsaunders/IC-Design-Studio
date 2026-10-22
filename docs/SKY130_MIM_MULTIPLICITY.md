# SKY130 MiM multiplicity and mismatch integration

New SKY130 projects use revision `857acac277f431b3`. The second MiM capacitor
now emits `mf=MF m=MF`. Its original symbol emits `VM=MF`, but the public model
declares `mf`, not `vm`, and divides its random mismatch term by
`sqrt(wc*lc*mf)`. The old mapping therefore left that model parameter at one.
The separate simulator multiplier already scaled the nominal capacitance.

This correction changes catalog metadata in a new package revision. Every
original model, symbol, license and other asset remains byte-identical; the
previous manifest is retained. Saved projects keep their previous revision
and mapping. Installing the new default does not silently migrate them.
Local PDK import applies the same correction only to the exact reviewed symbol
and model hashes. Unreviewed source changes require an explicit adapter.

The [execution record](validation/sky130-mim-binding-2026-10-22.json) binds the
actual decks, raw outputs, package and application sources to these results.
Each host runs 54 native simulations with both MiM models, four shapes
(2×2, 2×10, 10×2 and 30×30 µm), four multipliers (0.5, 1, 4 and 16), and three
selected process/temperature pairs (nominal/27 °C, ss/0 °C and ff/85 °C).
Sixteen instances per model and shape provide distinct samples from a fixed
random seed. These are electrical fixtures; rectangular physical generation
remains unsupported by the [bounded layout recipe](SKY130_SECOND_MIM_LAYOUT.md).

Application exports match independent literal model calls. Paired samples
follow the model's inverse-square-root mismatch scaling; nominal capacitance
scales linearly. Restoring the unused `vm` mapping or omitting the simulator
multiplier produces 1,728 detected faulty device instances per host. The first
MiM is an unchanged-model control. Nonpositive multiplicity remains rejected;
positive fractional multiplicity remains an electrical capability, with
physical generation still restricted to supported integer counts.

An independent auditor imports no application or qualifier code. It checks
6,912 actual device calls and 20,736 raw capacitance samples per host using
complex admittance and an independently rearranged scaling equation. It also
rejects wrong parameter names, changed width, truncated raw data and falsely
reported fault counts, even when the directly affected file hashes are updated.
The native simulator's documented seed mechanism is described in the
[ngspice manual](https://ngspice.sourceforge.io/docs/ngspice-manual.pdf).

The source desktop generates and regenerates the capacitor, supports undo/redo,
and saves/reopens the corrected netlist and package identity on both hosts.
The existing LI source desktop also exercises ordinary default-package
installation. Neither offscreen source workflow is installed-release acceptance.

To reproduce with local tools:

```sh
python scripts/qualify_sky130_mim_binding.py --sky130 icstudio/assets/pdks/sky130A --ngspice /path/to/ngspice --output /path/to/new-results
python scripts/audit_sky130_mim_binding.py /path/to/new-results --output /path/to/audit.json
python -m unittest tests.test_sky130_mim_binding tests.test_default_device_packages tests.test_sky130_rf_candidate -v
python tests/gui_sky130_mim2.py --out /path/to/new-editor-results
```

`--pilot` checks two instances per shape/model at nominal/27 °C: 18 native
runs and 72 faulty instances. CI runs that pilot and the independent audit.
`prepare_sky130_mim_binding.py` rebuilds the exact new package from either the
retained previous default or the new default's original assets.

This establishes application integration with the public model's stated
equations. It does not establish measured-silicon accuracy, full statistical
or reliability limits, complete operating envelopes, rectangular rotation,
all device families, or final installed-release acceptance. All 286 available
catalog entries remain partial; seven real bindings remain unavailable.
Chunk 7 remains incomplete.
