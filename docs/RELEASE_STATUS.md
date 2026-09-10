# Current delivery: 0.22.0.dev10

NGSpice is now provisioned and executed during Windows source setup and installer builds. The prepared portable Windows x64 app contains Python, Qt, the pinned NGSpice 42 console runtime, GF180MCU and SKY130 simulation subsets, and the supplied bandgap schematic.

The gallery offers a short bandgap startup check, the original full characterization, and a SKY130 inverter. Native PDK projects can install both bundled model packages through **Use included PDKs**. Standard cells and physical signoff decks are outside this bundle.

See [simulation setup](../SIMULATION_SETUP.md) and the [dev10 validation record](validation/0.22.0.dev10.json). Native Windows installer and desktop execution remain pending; prepared Windows bytes and Linux/offscreen execution are reported separately.
