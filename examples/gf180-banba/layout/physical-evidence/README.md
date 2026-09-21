# Banba physical verification evidence

**Partial physical closure; not fabrication signoff.** The revised GDS passes upstream geometry and antenna checks and strict LVS. Its capacitance-extracted circuit passes the saved electrical screens. Whole-die density and distributed RC remain open.

The authoritative artifact identities and results are in [`../physical-verification.json`](../physical-verification.json). [`manifest.json`](manifest.json) hashes this evidence bundle. The original GDS is available at parent commit `b24a08539e99567c40cf207a25790ab01e8e0afb`; `baseline/` retains its capacitance result and failed startup corner.

| Evidence | Purpose |
| --- | --- |
| `geometry.lyrdb`, `antenna.lyrdb`, `density.lyrdb` | Open in KLayout to inspect the actual rule results; density has 314 markers across PL.8/M1.4/M2.4. |
| `comparison.lvsdb` | Full strict comparison: 103 devices, 56 nets, three ports. |
| `schematic.spice`, `schematic.cdl`, `layout.cdl` | Independent resolved reference, upstream reader translation, and physical extraction. |
| `capacitance.ext`, `extracted-c.spice`, `capacitance.log` | Raw Magic extraction and the checked C-only simulation circuit. |
| `simulation-c.json` | All 20 PVT operating points and 60 startup results with unchanged acceptance limits. |
| `startup-before.csv.gz`, `startup-after.csv.gz` | Complete time/VREF traces at SS/−40 °C/3.6 V/10 µs, used for the comparison plot. |
| `rejected-resistance.ext`, `resistance.log`, `diagnostics/` | Failed distributed-R output, original diagnostics and sanitizer evidence. Never use these as a simulation netlist. |
| `runtime-lock.json`, `tests.log` | Executable hashes/source pins and the ten passing native/reference/fault-injection tests. |

KLayout is 0.28.16, Magic is 8.3.684 (`4f53bb3091d1e4a9b2009a58f157a8a4331d4c84`), and ngspice is 42. The GF180 rule and technology pins and the reproduction command are in the parent README. The technology-generation script retains all four PNP model selectors, correcting their terminal declaration and area selector. It does not replace extracted devices with schematic instances.

The extraction Tcl files and logs retain the original run paths. Reproduce through `scripts/verify_gf180_banba_physical.py`, which generates paths appropriate to the new workspace. All raw simulation decks, staged locked models, waveforms and logs are retained by that command; only the compact results and the before/after worst-case waveforms are checked into Git.

The local ngspice launcher redirects libc temporary files into a writable scratch directory through `diagnostics/tmpfile-env.c`; this only changes temporary-file location. It does not change circuit models or numerical options. A conventional local ngspice installation with writable `/tmp` does not need that adapter. Linux Tcl 8 builds were run with a 1024-descriptor limit. Diagnostic sanitizer builds are identified separately and are not used for the final capacitance simulations.

To finish physical closure, integrate legal fill with the actual chip floorplan and rerun all checks on that filled GDS. Distributed RC additionally needs a corrected or independently qualified GF180 extractor that preserves every device terminal and yields a valid resistance graph; then repeat the electrical screens using that RC netlist. The present evidence does not waive either requirement.
