# Six-case GF180 bandgap compatibility test

`examples/gf180-bandgap/5vfullv2-compatibility.sch` reduces the uploaded
`5vfullv2(20260910-165347).sch` from **144 analyses to 6** (95.8% fewer).
Only the NGSPICE code component's value changes. Device sizes, model choices,
wires, labels, placement and other source bytes are preserved. The original
144-case example remains available separately.

| Case | Conditions | Size |
| --- | --- | --- |
| Startup | 5 V, 25 °C; 100 µs supply ramp; 3 ms duration | 100 ns requested step |
| Cold DC | −40 °C; supply 3–5 V | 17 points |
| Room-temperature DC | 25 °C; supply 3–5 V | 17 points |
| Hot DC | 125 °C; supply 3–5 V | 17 points |
| PSRR | 5 V, 25 °C; 1 V AC supply excitation | 61 points, 1 Hz–1 MHz |
| Output impedance | 5 V, 25 °C; 1 A AC output excitation | 61 points, 1 Hz–1 MHz |

The three DC sweeps use an exactly representable 0.125 V step so ngspice can
measure the 5 V endpoint reliably. Each case resets the simulator before
setting its conditions. Outputs use relative filenames and require no shell
commands. Five startup measurements and voltage/current waveforms are retained.

## Run in IC Design Studio

1. For the supplied native `.icproj`, choose **File → Open project**. It contains
   its simulation models and the six-case program.
2. To exercise import yourself, choose **File → Import and migrate Xschem
   project…** and select `5vfullv2-compatibility.sch`.
3. In **Target device library**, select the installed GF180MCUD revision to
   exercise catalog conversion. If needed, install the included package through
   **File → Project Hub → PDKs** first. The review should match **60 model
   devices**, with **0 unmatched**. Save the native project.
4. Keep **ngspice** and the saved **program** analysis selected, then press
   **F5**. Under **Results → Simulation → Program analyses**, six cases should
   finish. Open any case's waveform. Selecting a separate single-analysis
   setup runs that analysis instead of the embedded six-case program.

The repository schematic retains the original `/foss/pdks/...` references;
Studio resolves these using its included GF180 simulation library. The separate
test bundle also contains a `portable-source` folder with those two include
paths relocated to bundled `models` files. Keep that entire folder together
when opening it directly in Xschem. Add its root to `XSCHEM_LIBRARY_PATH` if
your Xschem configuration does not already search the schematic folder.

## Compatibility result and required fix

Tested on Linux with **Xschem 3.4.4 and ngspice 42**, using the experimental
`0.22.0.dev10` source at `57ba473` plus the native-expression fix accompanying
this document. The original current build passed the preserved-import path.
It needed the accompanying fix for the full native catalog round trip.

Native conversion previously evaluated live device formulas into rounded
numbers. That changed this circuit's startup waveform by up to **5.77 mV**
and froze diffusion dimensions after Xschem export. The fix preserves validated
expressions and unchanged source numeric spellings. Xschem export also keeps
simulation expressions when adding LVS parameter aliases.

| Compared against independent Xschem → ngspice | Analyses passed | Maximum measured trace difference after fix |
| --- | --- | --- |
| Studio preserved Xschem import | 6/6 | 0 |
| Native GF180 catalog conversion, saved and reopened | 6/6 | 0 |
| Native export netlisted by real Xschem | 6/6 | 0 |
| Export reimported into native Studio, saved and reopened | 6/6 | 0 |

The comparison includes four voltage traces, two current traces and complex
AC values, so AC phase is checked too. All **68 device identities**, all
connections and all **60 catalog model identities** survived. Additional
checks edit MOS width after reimport to verify dependent formulas still update.
The Qt desktop test exercised migration, save/reopen, the actual simulation
worker, six completed cases, five startup measurements and waveform switching.

Measured final startup VREF was **1.19507235 V**, IREF **209.933 nA**, and supply
current **37.7370 µA**. These are compatibility reference values, not a claim
that the circuit meets every specification in the original characterization.
This shorter test omits much of the original PVT, noise and load coverage.
A schematic alone does not establish Magic/KLayout layout, DRC or LVS
compatibility. This circuit uses GF180 models; it does not qualify the other
PDKs. Windows execution is a CI gate added by this change and was not run in
the Linux validation environment.

## Repeat the checks

From the repository root with its Python dependencies, Xschem and ngspice installed:

```sh
python -m unittest tests.test_bandgap_compatibility -v
python scripts/verify_bandgap_compatibility.py --output build/bandgap-check
```

Use a new, empty output directory. If executables are outside PATH, pass
`--ngspice /path/to/ngspice --xschem /path/to/xschem`. The comparison script
performs one independent reference run and four execution paths, each with
six analyses. A normal user run of the schematic performs only six analyses.
It writes `report.json`, native projects, a portable source package, a native
Xschem export, decks, logs and waveforms. Comparison failures return a nonzero
exit status. Reports identify the build, source hash, PDK revision and measured
errors; tolerances are 0.01% of reference peak plus 2 µV / 20 pA.

For the desktop test, set `QT_QPA_PLATFORM=offscreen` and
`ICSTUDIO_TEST_NGSPICE` to your executable, then run:

```sh
python tests/gui_bandgap_compatibility.py
```

CI runs the independent Xschem comparison on Linux and the native desktop test
on Linux and Windows. It retains both evidence folders in the build artifact.
Source provenance and exact hashes are in
`examples/gf180-bandgap/compatibility-source.json`.

Local validation used an unmodified ngspice binary with a workspace-only
temporary-file adapter because the test environment does not provide `/tmp`.
The adapter changes temporary-file placement, not numerical routines. Normal
desktop installations do not require it. The included reports identify that
local launcher; they are not evidence of a completed GitHub Actions run.
