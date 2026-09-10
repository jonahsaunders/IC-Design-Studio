# NGSpice and open PDK setup — 0.22.0.dev10

## Fastest start on Windows

1. Extract the whole `IC-Design-Studio-0.22.0.dev10-Windows-x64.zip`.
2. Double-click `ICDesignStudio.exe`. Keep the `app` and `python` folders beside it.
3. In the example gallery, choose **07 · GF180 bandgap startup**, **Open a copy**, then **F5**.
4. Open **Simulate → Program analyses** to inspect the waveform and measured final voltages.

Python, Qt, NGSpice 42 and the GF180MCU/SKY130 simulation packages are included. The portable app needs no first-launch download. Its launcher checks the engine files and runs a voltage-divider simulation before opening the desktop. `ICDesignStudio-Console.exe` shows startup diagnostics.

The source ZIP includes the same Windows NGSpice runtime and both PDK subsets. It requires installed 64-bit Python 3.12 and internet for first-time Python dependency setup. Run `launch-windows.bat`. A clean GitHub export omits native binaries; this launcher downloads the checksum-pinned NGSpice archive when needed. Interrupted downloads are retried, missing DLLs are detected, and simulation setup failure prevents a misleading successful launch.

## Your supplied schematic

`examples/gf180-bandgap/5vfullv2-original.sch` is byte-for-byte identical to the uploaded `5vfullv2(20260910-015224).sch`. Open it directly or select **08 · GF180 full characterization** in the gallery. F5 runs its 144 analyses. Allow several minutes or longer, depending on the machine.

The app resolves the `/foss/pdks/gf180mcuD/...` model includes using its bundled primitive files. It preserves device geometry, parameters, analysis ordering and measurements. The existing control-program adapter relocates `/foss/designs/...` output tables beneath the run's `outputs` folder and prepares those directories on Windows. Use **Open output files** in Program analyses.

`5vfullv2-startup.sch` changes only the NGSPICE control block to one 5 V, 25 °C, 3 ms startup transient. It is a fast installation check, not a replacement for the original characterization. The Linux NGSpice 42 run produced 30,035 samples, a 5.0 V supply and a final VREF of about 1.19507 V.

The **09 · SKY130 transistor inverter** gallery example runs a 12 ns transient with the bundled 1.8 V MOS models. Its switching behavior was checked with real NGSpice.

## Start a native PDK project

Choose **Tools → Set up an open PDK → Use included PDKs**, select a registered revision, then choose **New project with this PDK**. Installation is offline and checksummed. Native PDK runs stage their locked model include closure into the run folder, so user/profile paths containing spaces also work.

| Package | Placeable / indexed symbols | Included scope |
|---|---:|---|
| GF180MCU D adapter | 64 / 68 | Primitive MOS, bipolar and passive models; symbols; display layers |
| SKY130A | 71 / 74 | Primitive corner model closure; symbols; display layers |

Models retain pinned source revisions, hashes and license notices. These are simulation PDK subsets. Standard cells, fabrication collateral, Magic/Netgen verification decks and IHP OSDI binaries are not included. IHP remains available through the existing external-PDK/OSDI setup workflow. The GF180 D adapter uses the existing pinned primitive model family; it does not replace a complete foundry option-specific PDK.

## Source builds and checks

On Windows, `build-windows.bat` now provisions and tests NGSpice before packaging. `scripts/package.py` rejects a build with missing PDKs or no working NGSpice, then checks the final bundle. The Inno Setup script packages those staged files into the installer. The prepared portable app was assembled on Linux; an actual Windows installer must be built on Windows.

On Linux, install NGSpice through your distribution (Ubuntu: `sudo apt install ngspice`). On macOS, use `brew install ngspice`. The models are portable, but an executable must match the host. Existing custom engine settings and `ICSTUDIO_NGSPICE` remain supported.

```sh
python scripts/check_simulation_assets.py
python scripts/verify_bundled_simulation.py --output build/simulation-check
# Add --full to include the unchanged 144-case characterization.
python -m unittest discover -s tests -v
```

For offline Windows provisioning from an already downloaded official archive:

```sh
python scripts/stage_windows_ngspice.py --archive path/to/ngspice-42_64.7z --ensure
```

`--archive` still requires the pinned SHA-256; a different runtime archive is rejected. The bundled console runtime covers the device models used here. Optional XSPICE code-model plugins and IHP OSDI native libraries require separate runtime configuration.

## Validation limits

All 439 unit/integration tests passed. Offscreen GUI checks opened all nine examples, executed seven short worker simulations and verified one-click PDK installation. Native catalog device runs passed for both PDKs from folders containing spaces. The unchanged original bandgap completed all 144 analyses with no failed cases or detected program diagnostics; its small numeric tables passed column-count and finite-value checks. See `docs/validation/0.22.0.dev10.json` for the evidence. Linux/offscreen execution does not establish native Windows or macOS execution. The Windows portable artifact includes verified upstream x64 components and launch-time checks; native Windows display, installer execution and platform acceptance are still pending. Simulation completion does not establish that the bandgap meets every specification in its characterization program.
