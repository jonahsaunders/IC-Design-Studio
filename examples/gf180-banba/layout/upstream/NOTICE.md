# GF180 primitive geometry provenance

`pnp_05p00x05p00.gds` is copied unchanged from the GlobalFoundries PDK Authors' [GF180 primitive library](https://github.com/efabless/globalfoundries-pdk-libs-gf180mcu_fd_pr/tree/aacc04cc30ed119baaa616dff266cca7006dc3d6/cells/klayout/pymacros/cells/bjt).

- Revision: `aacc04cc30ed119baaa616dff266cca7006dc3d6`.
- Upstream path: `cells/klayout/pymacros/cells/bjt/pnp_05p00x05p00.gds`.
- SHA-256: `59e36ad406b03027054754627051686ea5a605f045d1a8f164e877a4da3008a9`.
- License: Apache License 2.0, retained in [`LICENSE`](LICENSE).

The Banba generator removes the unit's default text labels, merges overlapping polygons without changing their area, translates the masks, assigns native device terminals, and adds circuit routing. It does not claim the routed assembly has the upstream cell's verification status.

GF180 mask numbers and high-Rs resistor construction dimensions were checked against the same revision's `layers_def.py` and `draw_res.py`. MOS construction extends the geometry approach already used in Studio's bounded GF180 adapter to this example's explicitly checked sizes. MIM dimensions and top/bottom access follow the public GF180 Option B rules. These project-specific generators are independently screened; they are not certified foundry PCells.
