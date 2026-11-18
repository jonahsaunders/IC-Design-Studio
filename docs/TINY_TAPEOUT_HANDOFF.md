# Tiny Tapeout SKY 26e source handoff

Open **Digital → New UART regression example**, then choose
**Digital → Export Tiny Tapeout Source…**. Check the title, author,
description, and `tt_um_` top module before choosing where to save the ZIP.
The dialog uses the selected RTL cell and includes any unapplied source
edits in that cell. Set your own top module name before publishing the project.

The export targets the Studio `uart_tx` RTL contract on SKY130A using the HD
standard-cell library, a single 1 × 1 tile, and a 10 ns clock target. Use the
example’s one clock and 1 ns input/output constraint file. The exporter
preserves that SDC for inspection and sets LibreLane’s I/O delay budget to
10 percent of the clock period. The generated wrapper changes the pin names
and adapts the active-low shuttle reset to the UART’s synchronous reset.

| Shuttle signal | UART function |
| --- | --- |
| `clk` | 100 MHz design target |
| `rst_n` | Assert low across a rising clock edge to reset |
| `ena` | Enable the UART. A low level resets it on the next rising edge. |
| `ui_in[7:0]` | Parallel byte |
| `uio_in[0]` | Pulse high for one clock to send when idle |
| `uo_out[0]` | Serial TX |
| `uo_out[1]` | Busy |
| Other outputs | Tied low. Bidirectional pins stay in input mode. |

The desktop dialog follows Apple’s guidance on keyboard access and feedback
with named fields, focus on the author field, inline messages for recoverable
errors, and a completion message that names the next verification step.
[Apple accessibility](https://developer.apple.com/design/human-interface-guidelines/accessibility) ·
[Apple feedback](https://developer.apple.com/design/human-interface-guidelines/feedback)

## Export and check from the command line

```text
python -m icstudio --cli digital tapeout examples/digital-uart.icproj --author "Your Name" --output "UART source.zip"
python -m icstudio --cli digital verify-tapeout "UART source.zip"
```

Use `--title`, `--description`, and `--top-module` to set the public
metadata, and `--cell` for a specific RTL cell. The ZIP includes the source,
pinout, configuration, UART test, and a GitHub Actions workflow. The manifest
records the input configuration hash, target profile, downstream status at
export, and SHA-256 checksums of the packaged files. The verification command
checks the file inventory and checksums against that manifest.

Extract the ZIP to an empty directory and run `make -C test` with Icarus
Verilog. The test exercises reset, enable, the unused outputs, and the
start, data, and stop bits for three UART frames. It retains a waveform and
a test report for inspection.

## Produce and review the physical artifacts

Put the extracted files at the root of your Tiny Tapeout project repository,
including `.github/workflows/gds.yaml`. Preserve the source’s license and
authorship. In GitHub Actions, run **Tiny Tapeout SKY 26e**. It hardens the
design, then uses the resulting submission artifact for stream precheck and
gate-level simulation. Review the reports, including timing at the 10 ns
target, before submitting through Tiny Tapeout.
[Tiny Tapeout submission requirements](https://tinytapeout.com/specs/) ·
[Local hardening guide](https://tinytapeout.com/guides/local-hardening/)

| Input | Pinned reference |
| --- | --- |
| Shuttle definition | [SKY 26e at `9ae0815`](https://github.com/TinyTapeout/tinytapeout-sky-26e/tree/9ae0815308c185f9c32799e5235346c230c95748) |
| Support tools, tile template, and configuration generator | [`9d13ff3`](https://github.com/TinyTapeout/tt-support-tools/tree/9d13ff3e3e6202090740110438c6a10c1d62ca0f) |
| Project hardening, precheck, and gate-level actions | [`395eedb`](https://github.com/TinyTapeout/tt-gds-action/tree/395eedb3eeec3c2f4961c3b04ff2cf87f5525636) |
| Project hardening | [LibreLane 3.0.14 with SKY130 revision `8afc834`](https://github.com/librelane/librelane/blob/3.0.14/librelane/pdk_hashes.yaml) |
| Stream precheck | [SKY130 revision `0536d02`](https://github.com/TinyTapeout/tt-gds-action/blob/395eedb3eeec3c2f4961c3b04ff2cf87f5525636/precheck/action.yml) |

The [qualification log](QUALIFICATION_PROGRESS.md) records the checks run on
Studio’s UART fixture. Physical hardening, timing closure, gate-level
simulation, stream precheck, and shuttle acceptance require their own
evidence for the exact submission.
