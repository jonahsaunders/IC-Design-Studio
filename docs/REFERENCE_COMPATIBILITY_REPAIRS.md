# Reference compatibility repairs

The references are the GF180 B Banba bandgap and LDFranck's SKY130 overvoltage
detector at the revisions already locked in this repository. Passing these
checks qualifies their tested routes, not arbitrary PDKs or fabrication signoff.

## Hierarchical layout exchange

Magic import retains `magic-raw.gds`, writes `imported.gds` through KLayout, and
requires exact cell/layer polygon XOR, labels and presentation, hierarchy,
arrays and database units. A disagreement aborts the import. The raw Magic
stream remains a diagnostic: its DRC failure must not be treated as a passing
independent stream route. The canonicalized import is the supported route.

`qualify_reference_exchange.py` verifies fresh extraction and strict LVS on
every exchanged detector stream, checks full DRC, and injects narrow metal,
missing vias, shorts, resistor-width changes and missing/extra interface pins.
It now exports the captured native schematic with the current exporter before
asking a separate Xschem process to produce its reference netlist.

## Windows physical verification

The included Linux/private WSL runtime now contains pinned Magic and Netgen,
ngspice and the locked KLayout Python module. Tools > Physical tools setup
performs positive and negative DRC/LVS controls before recording readiness.
The Windows Qt worker transfers the locked PDK and captured job into a private
Linux work directory, then verifies an inventory of every returned artifact.
Source design identity is restored for navigation while native evidence remains
available. Cancellation uses the existing supervised process-tree protocol.

Custom engine paths retain their existing behavior. Standalone interactive
Magic editing and native `.mag` conversion still require explicitly configured
external tools; the managed runtime supports Studio's physical verification job.

`tests/gui_physical_qualification.py --managed --pdk ... --out ...` checks
nominal verification, stale results after an edit, deliberate DRC failure,
navigation to its geometry, undo and fresh verification, and missing-engine
blocking. `--physical-acceptance` runs the same probe inside the frozen app.
Windows installer acceptance requires this test before uninstalling the exact
installed build; it checks the executable hash and clean source commit.

## GF180 distributed RC and fill

The default Magic/Netgen lock is unchanged. The separate experimental GF180 RC
lock pins Magic 8.3.684 and a checksummed two-file patch. It extracts passive
nets without a transistor driver and searches the complete device identifier
area for cross-plane terminals. This repairs the Banba PNP emitter connection.
Implicit bulk space is excluded from conductor traversal to prevent walking
past the database boundary during PNP resistance extraction.
The pinned technology adapter corrects PNP terminal ordering and makes the MIM
input contact match the existing 260 nm output cut plus two 40 nm borders.
Raw upstream technology, extraction records and engine logs are retained.

All original nets must be extracted. The existing area-weighted C distribution
must conserve the original capacitance matrix, and contracting wire resistance
must recover all 103 devices, their terminals and dimensions. A separate pass
may remove only a disconnected resistor-only component touching no port,
device terminal or capacitor endpoint. It retains the source and lists every
omitted resistor. It never inserts leakage or changes device dimensions.

The complete post-RC gate retains the existing 20 process/temperature/supply
cases and all three startup ramps, sample steps and electrical thresholds.
KLU and one solver thread per independent case control execution cost.
Timeouts, incomplete traces and failed cases remain failures.

The fill audit checks every original circuit mask and all six dummy purposes.
The actual filled reference lies beyond the pinned deck's 8 micrometre
interaction range. Separate near/absent/far structures on all four metal
layers materialize dummy purpose 4 as floating conductors in disposable GDS,
then require real positive coupling only in the near case. This bounds direct
core/fill interaction in this model; it does **not** establish long-range
coupling, fill-to-fill network effects or foundry-calibrated parasitics.

Build and run on Linux with the dependencies listed in the qualification CI:

```sh
python scripts/build_physical_engines.py --lock examples/gf180-rc-engine-lock.json --output build/gf180-engines
python scripts/build_physical_engines.py --lock examples/modern-schematic-engine-lock.json --output build/modern-engines
python scripts/qualify_gf180_rc.py --open-pdks build/open-pdks --magic "$PWD/build/gf180-engines/installed/bin/magic" --ngspice "$PWD/build/modern-engines/installed/bin/ngspice" --out build/gf180-rc
```

## Modern schematic and simulation tools

The optional modern lock pins Xschem 3.4.8RC and ngspice 46. Exact legacy
voltage-source templates are adapted only inside captured Xschem workspaces:
their boolean current-probe property gets a private name so Xschem's newer
`@savecurrent` expansion cannot turn it into a Tcl expression. Custom formats
remain the author's responsibility. Exports preserve input/output port
directions, and headless ERC diagnostics are saved even when Xschem exits early.
The captured headless session supplies a no-op Tk focus command only when Tk
is absent, allowing the newer Tcl property evaluator to finish netlisting.

SKY130 legacy level-3 diode symbols explicitly declare their pre-46 AREA/PJ
units. Studio probes the selected executable's actual scaling behavior and
converts only declared instances in disposable simulation decks. Original
model files remain unchanged. Source/runtime hashes and the behavioral control
are saved. Ordinary diode instances and unsupported models are not guessed
from numeric size. This adapter applies to Studio's native/Xschem execution
paths; a raw exported SPICE file passed directly to another simulator needs
an equivalent units adapter at that destination.

## OASIS text presentation

Optional property 124 records text rotation, mirror, size, font and alignment
with an anchor binding. Restoration requires the same label string, layer,
location and database units. External content/position changes win. Stale
owned metadata is discarded, and a foreign property 124 is never overwritten.
The independent KLayout rewrite test requires exact presentation after
reimport/export to GDS. Tools that discard optional OASIS properties cannot
preserve that extra appearance information through this route.

## Virtuoso handoff: prepared, not qualified

There is no licensed Cadence environment available for this work. Open-source
round trips and adapter unit tests do not establish Virtuoso interoperability.

`scripts/qualify_virtuoso_exchange.py prepare --gds ... --cdl ... --top ... --out ...`
creates checksummed layout/CDL inputs and an explicit interface/layer inventory.
A site with the matching licensed PDK supplies its real layer/purpose map,
strict LVS setup and version-specific command wrappers. The configuration is:

```json
{
  "schema": 1,
  "pdk_id": "actual-site-PDK",
  "pdk_revision": "actual-installed-revision",
  "layer_map": "/site/pdk/actual-stream-map",
  "lvs_setup": "/site/pdk/actual-netgen-setup.tcl",
  "netgen": "/site/tools/netgen",
  "commands": {
    "version": ["/site/bin/record-cadence-version"],
    "import": ["/site/bin/import-into-fresh-native-library", "{bundle}", "{work}", "{top}", "{layer_map}"],
    "export_layout": ["/site/bin/export-native-layout", "{work}", "{top}", "{returned_gds}", "{layer_map}"],
    "export_netlist": ["/site/bin/export-native-cdl", "{work}", "{top}", "{returned_cdl}"]
  }
}
```

These are site wrapper names, not supplied Cadence commands. They must invoke
the actual installed tools, use a fresh native database, fail on tool errors,
and export its independent layout and netlist. Copying the handoff inputs is
not a qualification. No universal layer map or untested OpenAccess API is
invented here. Run `run --bundle ... --adapter ... --out ...` at that site.
The runner records executable hashes, logs, PDK identity and immutable mapping
and setup hashes, then requires exact stream equality and strict independent
LVS. Review the recorded command/tool provenance alongside the content verdict.
