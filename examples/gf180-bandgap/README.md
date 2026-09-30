# Supplied GF180 5 V bandgap

This folder contains the supplied Xschem bandgap and short simulation variants.
It uses the included GF180 transistor, bipolar and resistor models with ngspice.
It is a different circuit from the [native 3.3 V Banba design exercise](../gf180-banba/README.md),
and no Banba physical result qualifies this schematic's layout.

## Choose a starting point

| Source | Open / run | What it does |
| --- | --- | --- |
| [`5vfullv2-startup.sch`](5vfullv2-startup.sch) | **File → Start here / example gallery → 07 · GF180 bandgap startup → Open a copy**, then **F5** | One 3 ms startup transient at 5 V and 25 °C. Start here to check the simulator and bundled models. |
| [`5vfullv2-original.sch`](5vfullv2-original.sch) | **08 · GF180 full characterization → Open a copy**, then **F5** | The unchanged supplied source and its 144-analysis program: startup, temperature, supply, load and AC studies. Allow several minutes or longer. |
| [`5vfullv2-compatibility.sch`](5vfullv2-compatibility.sch) | **File → Import and migrate Xschem project…**; choose the registered `gf180mcuD` library, save the native project, keep its program analysis selected, then **F5** | Six cases: startup; DC supply sweeps at −40, 25 and 125 °C; PSRR; output impedance. See the [compatibility guide](../../docs/BANDGAP_COMPATIBILITY.md). |

Open **Analysis → Program analyses** to inspect cases, measurements and waveforms;
select `vref` and `avdd` for startup. **Open output files** exposes the original
program's tables. Studio relocates its `/foss` output paths into the run folder
and resolves model includes through the bundled library. Save an independent
native copy with **Ctrl+S** before editing. If needed, register the models with
**Tools → Set up an open PDK → Use included PDKs**. Desktop packages include
ngspice; source checkouts need the [simulation setup](../../SIMULATION_SETUP.md).

Selecting a separate operating-point or transient setup replaces the selected
program for that run. Keep the saved program selected to execute all its cases.
Running the full source is a characterization exercise, not an assertion that
every measurement or specification passes.

## Recorded six-case result

The [independent compatibility run](../../docs/BANDGAP_COMPATIBILITY.md)
compared Xschem/ngspice with preserved import, native catalog migration,
native Xschem export and reimport. The archived Linux run used Xschem 3.4.4 and
ngspice 42 and recorded six matching cases on each path. Its final startup
values were **VREF 1.19507235 V**, **IREF 209.933 nA** and **supply current
37.7370 µA**. These are reference measurements for that fixture and toolchain;
they are not the Banba output or full PVT/physical qualification.

To recreate the independent checks from the repository root, install the normal
Python requirements and provide Xschem and ngspice:

```sh
python scripts/verify_bandgap_compatibility.py --output build/bandgap-check --xschem /path/to/xschem --ngspice /path/to/ngspice
```

Use a new output directory. It contains `5vfullv2-native.icproj`,
`5vfullv2-roundtrip.icproj`, a `portable-source` package, reference/native decks,
logs, waveforms and `report.json`. The verifier performs five executions of the
six-case program; a normal Studio run performs six analyses once. For current
modern-tool adapters and CI scope, see [reference compatibility](../../docs/REFERENCE_COMPATIBILITY.md).

## Source identity

[`source.json`](source.json) pins the original upload
`5vfullv2(20260910-015224).sch`; the startup variant changes only its NGSPICE
control block. [`compatibility-source.json`](compatibility-source.json) pins a
separate later upload, `5vfullv2(20260910-165347).sch`, and its six-case reduction.
That reduction changes only the NGSPICE component value relative to its own
recorded source. The two identity records must not be treated as the same
byte-for-byte original.

For direct Xschem execution, keep the verifier's entire `portable-source`
directory together so symbols and relocated model includes remain available.
The checked-in schematics retain their original `/foss/pdks/...` references.
