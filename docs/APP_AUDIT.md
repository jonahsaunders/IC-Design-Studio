# Application audit — 2026-10-01

Branch: `codex/student-hub-design-paths`. Starting revision:
`f8d0b5ff9a8aa77fe3aafc9182109c25045e84f0`.

This audit reproduced the desktop build failure, exercised the application’s
menus and workspaces, and ran real simulation and physical checks for SKY130,
GF180 C/D and IHP SG13G2. The fixes include regressions and release gates.
The results qualify the executed cases; they do not establish that every
possible circuit, imported construct, or operating system configuration works.

## Failure and repairs

| Problem reproduced | Repair |
| --- | --- |
| Both desktop release jobs selected a GF180 catalog key for IHP, producing `Unknown PDK catalog device`. | Release cases now select the process’s registered device and supply. IHP must run with its matching compiled models; missing setup fails the gate. |
| Ordinary IHP analyses could use ngspice without the required OSDI runtime. Imported/native control programs did not load configured OSDI libraries. | Route IHP analyses and programs to the included runtime by default. Preserve explicit custom configurations, verify their hashes, and load them after validating imported commands. Retain transferred program waveforms in the host job folder. |
| Compatible Xschem import discarded an explicitly selected PDK. | Preserve the selected technology, including its revision lock and IHP runtime requirement. |
| IHP model import stopped on Latin-1 micro signs in HBT model comments. | Record source encoding and retain original bytes and hashes. Model staging and native migration remain checksummed; modified sources still fail. |
| Exported GF180 symbols referred to `@L`/`@W` in LVS while exporting `l`/`w`, blocking independent native reimport. | Bind the preserved LVS format to the exported live parameter names. |
| Native/captured handoffs called a serializer that rejects those project types. Moving locked handoffs could invalidate exchange metadata and PDK paths. | Use each document’s serializer, include its models, rebase every project and dependency lock, and refresh the affected sidecar hashes. |
| SPICE, GDS, image and handoff exports could omit pending inspector edits. | Flush pending edits before export and stop on invalid drafts. |
| Zoom In/Out raised a Qt point-type exception. | Use floating-point canvas coordinates while preserving the point under the viewport center. |
| Repeated switching among digital examples restored a deleted Qt window. | Exclude temporary digital windows from saved circuit panels and verify dock validity before restoring visibility. |
| Runtime guidance described included tools as external-only; older GUI assertions expected retired UI behavior and only two PDK packages. | Update compatibility/runtime guidance and tests for the current queue, dependency review, menus and four packaged variants. |

The failing baseline jobs are in [desktop run 36797138235](https://github.com/jonahsaunders/IC-Design-Studio/actions/runs/36797138235).
Code fixes were first pushed in [87cf772](https://github.com/jonahsaunders/IC-Design-Studio/commit/87cf772018e69b9287aa7194c1654b44040b7c3b).

## Executed coverage

| Check | Result and evidence |
| --- | --- |
| Unit suite | 1,243 tests: 1,190 passed, 53 skipped because their external engine/fixture conditions were absent. No failures. Separate real-engine probes below supplement those skips. |
| GUI acceptance | 74 general GUI scripts passed, plus the real SKY130 interface-change/physical-flow script: [75 results](validation/app-audit/gui-tests.json). |
| Menu and tab survey | 308 menu entries inventoried; 303 enabled entries invoked; 66 workspace tabs visited; no unexpected exceptions. [Menu inventory](validation/app-audit/menus.json), [tab inventory](validation/app-audit/tabs.json), [summary](validation/app-audit/menu-checks.json). |
| Device/corner simulation | All 51 real ngspice cases passed across MOS variants, diodes, IHP resistors, capacitor and bipolar devices: [results](validation/app-audit/device-corners.json). Nominal cases also check Xschem round trips. |
| Process inverter flows | Four variants passed DC, transient, deliberately failing and repaired DRC/LVS, final combined checks, and tampered-evidence rejection: [results](validation/app-audit/inverter-qualification.json). |
| Independent import/export simulation | Eight cases passed: native and captured programs for all four variants, after handoff export and relocation into paths containing spaces and Unicode: [results](validation/app-audit/pdk-exchange.json). |
| Release materials | Repository document/link/gallery checks passed. |

The menu sweep cancels file selections and confirmation dialogs. Its 75
prerequisite guards are reported separately from successful operations. Dialog
buttons are inventoried, while the action-specific GUI scripts exercise real
submissions, editing, queueing, cancellation, import/export and recovery.
Undo/Redo, layout-only grid snapping and stopping a running simulation are
initially disabled in the generic menu fixture; their applicable states are
covered by the editing, grid and cancellation probes. Closing is tested at the
end of the sweep. This is not a claim that merely opening a menu verifies every
button’s full behavior.

The acceptance scripts cover the Student Hub and process picker, schematic and
layout editing, hierarchy, symbols, analysis and waveforms, analog studies,
digital source/workspace controls, 3D views, collaboration/recovery, project
lifecycle and interchange. Fixture-based openEMS and digital tests are identified
by their scripts; they do not imply full native solver qualification.

## Real process measurements

All physical results below use real Magic and Netgen, not parser fixtures.

| Process | Locked package revision | Supply | Measured switching threshold | DRC after repair | LVS after repair |
| --- | --- | ---: | ---: | --- | --- |
| SKY130 A | `01b4bb7a87cc7fe5` | 1.8 V | 0.869841 V | Pass | Pass |
| GF180 C | `627ca682d68e1e92` | 3.3 V | 1.531999 V | Pass | Pass |
| GF180 D | `7dd87219f1333dbb` | 3.3 V | 1.531999 V | Pass | Pass |
| IHP SG13G2 | `3abac20fcb57e184` | 1.2 V | 0.617303 V | Pass | Pass |

SKY130 physical checks use the full pinned qualification package, separately
prepared from the smaller bundled simulation package. GF180 C and D have
separate physical configurations and were each tested. The broader device/corner
probe uses locally registered process adapters; its exact identities are in its
JSON record and should not be confused with the inverter package revisions.

Local engines: ngspice 42; Magic 8.3.684 at
`4f53bb3091d1e4a9b2009a58f157a8a4331d4c84`; Netgen 1.5.300 at
`1de6f88f1eebb786efadecc28e9e0dde37e8c433`.
IHP uses all six libraries compiled with the pinned OpenVAF build and generic
CPU target. Local wrappers supply library paths and redirect temporary files
into the writable workspace; no numerical engine or process model is replaced.

Handoff regressions additionally reopen GDS/OASIS sidecars and native/captured
Xschem exchange after removing original sources, verify preservation hashes,
check relative PDK dependency locks, and reject changed model bytes. Native bus
and instance-array exports still report their documented unsupported cases
instead of silently changing connectivity.

## Reproduce

Use Python 3.12 and the repository requirements. Use fresh output directories.

```sh
python -m unittest discover -s tests -v
python scripts/check_release.py
QT_QPA_PLATFORM=offscreen python tests/gui_menu_audit.py --out build/menu-audit
QT_QPA_PLATFORM=offscreen python tests/gui_audit_regressions.py --out build/audit-regressions
QT_QPA_PLATFORM=offscreen python tests/gui_project_hub.py
python tests/probe_pdk_exchange.py --ngspice /path/to/ngspice --out build/pdk-exchange
```

The exchange probe uses the installed included IHP runtime unless
`--osdi-directory /path/to/compiled-models` selects native compiled libraries.
`scripts/qualify_student_inverter.py` reproduces each real physical flow with
`--pdk-manifest`, `--out`, `--ngspice`, `--magic` and `--netgen`; add
`--osdi-directory` for native IHP execution. The broader device/corner matrix is
`scripts/verify_release_pdks.py` with `--pdk-root`, `--ngspice`, `--osdi` and
`--output`.

The desktop workflow now gates the menu regressions, tab survey, all bundled
process choices, managed inverter runs and all eight program handoff cases on
Linux and Windows. Its simulations reuse the installed runtime’s explicit state
directory. These checks supplement the existing packaging, native display,
external tool, VGA, digital implementation and physical qualification workflows.

![IHP runtime dialog](validation/app-audit/runtime-ihp.png)

The screenshot verifies the dialog’s layout under the GUI routing fixture;
its readiness response is mocked. Real process execution is recorded separately
above. Local GUI checks use Qt’s offscreen platform. Native Windows/WSL,
installer, audio-device and hardware-rendering acceptance depend on their CI
or manual checks; local offscreen success is not a substitute.

At this report’s preparation, the first fix revision passed GitHub’s external
tool interoperability and VGA Playground workflows, including real embedded
rendering. The full desktop, reference-design and physical matrices were still
running. Consult the branch’s current Actions results for release status.
