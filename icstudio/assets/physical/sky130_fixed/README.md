# Fixed SKY130 PNP geometry

`sky130_fd_pr__rf_pnp_05v5_W3p40L3p40.gds` is an **unmodified** upstream
SkyWater PDK Authors asset, distributed under Apache-2.0 (see `LICENSE`).

- Repository: https://github.com/fossi-foundation/skywater-pdk-libs-sky130_fd_pr
- Commit: `403964dc7f9cca5ec1a8cc7b4f2a6f532b781676` (the reference used by the pinned open_pdks adapter)
- Path: `cells/rf_pnp_05v5/sky130_fd_pr__rf_pnp_05v5_W3p40L3p40.gds`
- SHA-256: `19758688e586f1c670ebac59ffe9adff75bd20f6fa094abc16af2834bfeacad0`

`icstudio.sky130_fixed_devices` checks the immutable bytes, model bytes, layer
mapping and original terminal labels before generating geometry. It preserves
every physical mask, omits annotation/label/port-marker layers, and adds explicit
metal1 terminal accesses. Multiplicity uses real parallel copies. Each edited
instance still requires process DRC and extracted LVS; these bytes are not a
general fixed-cell qualification service.
