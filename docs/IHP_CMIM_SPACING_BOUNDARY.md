# IHP `cap_cmim` shared-electrode spacing source experiment

This bounded source experiment checks two complete imported IHP `cap_cmim` devices sharing both electrodes, at three MIM edge separations and two rotations. The [execution record](validation/ihp-cmim-spacing-boundary-2026-11-03.json) identifies the retained native output and independent readback. It does not qualify isolated electrodes, other arrays, electrical parasitics, installed releases or the device family.

Each 7 × 7 µm MIM rectangle retains the original source-drawn 25-contact Vmim array. The original Metal5 surrounds overlap, making a common bottom electrode. A declared full-height TopMetal1 bridge joins the original top plates into a common top electrode. The independent raw reader compares the original masks, translated second copy and bridge with both written stream formats, and verifies the two ordered ports and two distinct extracted capacitors before comparison.

The pinned public table gives MIM.b a 0.60 µm minimum spacing. Each row ran at 0° and 90°. Both public decks completed; the main deck reported no findings in these six cases, and strict LVS passed all six.

| MIM edge separation | Maximal-deck result per rotation |
| --- | --- |
| 0.58 µm | One MIM.b finding |
| 0.60 µm | Zero findings |
| 0.62 µm | Zero findings |

The comparison uses a predeclared physical `C` reference with two `cap_cmim` instances, not a simulation-reference export. Netgen combines the two parallel capacitors during comparison. Its matching result alone therefore does not establish separate extraction: independent readback verifies that the unfiltered native netlist contains two `cap_cmim` records, each with ordered C1/C2 terminals, 7 µm width and length, 49 µm² area, 28 µm perimeter and unit multiplicity. This is connectivity and physical comparison evidence, not calibrated extracted electrical behavior.

The first 0.60 µm construction used a narrow top-metal bridge. Its extraction and LVS passed, but the main deck found two TM1.b notches. That actual failed construction is retained. The accepted experiment uses the full-height bridge, preserving the same MIM masks and source contacts rather than filtering those findings.

Four controls exercise the shared-electrode topology. A wrong-width reference produced native property errors; swapped reference terminals failed pin matching. Removing one device's contact array produced MIM.h and a native LVS mismatch, with the affected top terminal disconnected. A physical bridge short merged C1 and C2; native extraction completed and the application rejected the changed ports before LVS, which was not run. Tool errors are not counted as successful fault detection.

An independent review checked all ten native contexts and the copied public decks and extraction sources, with nine corruption controls rejecting altered geometry, contacts, device count, parameters, nets or findings. The source snapshot, native runtime, public deck identities, original failed construction, all six cases, four faults and readback are retained in the hash-verified evidence archives. The original source PCell and its parameter checks were not changed. Reproduction uses the retained external drivers, recorded source snapshot and native tool/runtime, with fresh output directories; a repository CLI for this selection does not currently exist. This work adds a selected shared-electrode physical class to the remaining [IHP capacitor requirements](IHP_CMIM_REQUIREMENTS.md); it does not waive contact-enclosure applicability, other geometry classes or device operating limits.
