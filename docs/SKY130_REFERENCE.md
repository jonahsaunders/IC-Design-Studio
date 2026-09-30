# Archived SKY130 standard-cell inverter reference

The 0.4.0 reference flow passed all stages in this Linux workspace. The fixture is the PDK standard cell `sky130_fd_sc_hd__inv_1`, represented as an editable two-MOS native schematic and hierarchical testbench with its imported GDS layout. This is one adapter/reference regression, not qualification of arbitrary designs or foundry tapeout signoff.

| Stage | Observed result |
|---|---|
| PDK and tool preflight | Checksummed assets and tool identities recorded |
| Native schematic and GDS import | NMOS + high-threshold PMOS, six cell ports; 1 nm database units |
| Schematic transient | 3,185 samples; correct settled high/low outputs; six measured transitions |
| Magic DRC | Zero violations |
| LVS extraction | Two MOS devices extracted from the GDS |
| Netgen LVS | Native Studio-exported schematic matches extracted layout uniquely; pin lists equivalent |
| Parasitic extraction | 14 capacitors, including coupling and substrate capacitance |
| Post-layout transient | 3,185 samples; correct settled outputs; six measured transitions |

At the TT corner, 1.8 V supply and 5 fF output load, mean measured delay was **32.338 ps** before extraction and **36.380 ps** afterward, a **4.042 ps** increase. Settled output high minima were 1.799983 V / 1.799969 V; low maxima were 0.000303 V / 0.000558 V. Delay is averaged over the six observed 50%-threshold transitions; it is not a characterized timing library.

## Locked environment

- PDK: SKY130A, Volare release `sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392`; technology reports `1.0.291-82-gfa87f8f`.
- ngspice 42, Magic 8.3.683, Netgen 1.5.133, KLayout 0.30.5.
- ngspice HSA compatibility is supplied explicitly by the locked technology settings; local/user startup files are ignored.
- Primitive bindings: `sky130_fd_pr__nfet_01v8` and `sky130_fd_pr__pfet_01v8_hvt`; native dimensions converted explicitly to the PDK model units.
- The environment needed local runtime paths and the official Magic batch executable (`magicdnull`). The initial Ubuntu Magic 8.3.105 was rejected because the technology requires at least 8.3.306. A compatible Magic was built from upstream source. No PDK rules, device geometry or extraction algorithms were changed.
- This restricted host requires a test-only ngspice `tmpfile()` adapter to use writable scratch storage. It changes temporary-file location only. The adapter and locally built tool binaries are not included in the app distribution or required on normal desktop systems.

## Run it

Reproduce this specific archived standard-cell flow with the CLI below, on a
host with the matching PDK and ngspice, Magic and Netgen executables. The current
desktop's **Create PDK reference circuit…** opens the technology/template
selector; it does not execute this archived standard-cell qualification.
For an editable new inverter, use **File → Examples → New PDK inverter…**.

From a terminal:

```sh
python main.py --cli sky130-reference \
  --pdk-root /path/to/pdk/sky130A \
  --output /path/to/empty/reference-run \
  --ngspice /path/to/ngspice \
  --magic /path/to/magic \
  --netgen /path/to/netgen
```

The installed app accepts the same `--cli` arguments, but this legacy reference
command uses the explicitly supplied executables; it is not a managed WSL job.
`scripts/fetch_sky130_reference.py --output <empty-directory>` downloads the exact upstream PDK archives and verifies their hashes; it requires internet access and the `zstd` command. The archive hashes and release location are in `examples/sky130-reference-assets.json`.

The output contains `report.json`, `pdk-lock.json`, tool version logs, native `inverter.icproj`, isolated `inverter.gds`, the native-exported schematic used for LVS, extraction scripts/decks, DRC/LVS logs and before/after waveforms. A stage failure stops dependent stages and leaves their status as `not_run`. Missing tools/assets produce a blocked report.

## Boundaries

This flow uses an existing PDK standard-cell layout. It does not prove a newly drawn custom inverter, arbitrary user layouts, whole-chip rules, other device families, PVT corners, reliability rules or foundry signoff. Extraction includes interconnect capacitance; distributed interconnect resistance is still outside this verified fixture. This archived run was not repeated on Windows. The actual logs and waveforms are supplied separately in the reference-evidence archive. Current desktop physical verification has a separate [included Linux/private WSL runtime](REFERENCE_COMPATIBILITY_REPAIRS.md#linux-and-windows-physical-verification) and its own acceptance scope.

Primary references: https://github.com/google/skywater-pdk-libs-sky130_fd_sc_hd ; https://github.com/chipfoundry/volare ; https://github.com/RTimothyEdwards/magic ; https://opencircuitdesign.com/magic/commandref/drc.html ; https://opencircuitdesign.com/open_pdks/reference.html .
