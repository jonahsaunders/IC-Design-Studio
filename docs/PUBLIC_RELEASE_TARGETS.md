# Public release and tapeout acceptance targets

Follow the [twelve-chunk qualification plan](PDK_QUALIFICATION_PLAN.md) and its
validated per-process/device matrix for the ordered implementation work.

## Target and current boundary

The release target is analog and digital design on **SKY130, GF180MCU C/D and
IHP SG13G2**, with reproducible tapeout evidence for each supported flow.
This is a development and acceptance target, not a present capability claim.
The published 0.23.0 desktop remains an engineering preview. A public GitHub
release and successful hosted tests do not establish foundry signoff.

Use exact source commits, package hashes, PDK revisions, standard-cell libraries,
device subsets, process options, model/rule/extraction decks and tool builds in
every qualification record. A result for one process or variant cannot qualify
another. “All PDKs” here means these named targets, not arbitrary PDK compatibility.

Upstream PDK status also bounds release claims. Checked on 2026-10-06, the
[SKY130](https://github.com/google/skywater-pdk#current-status----experimental-preview),
[GF180MCU](https://github.com/google/gf180mcu-pdk/blob/main/README.rst#current-status----experimental-preview)
and [IHP SG13G2](https://github.com/IHP-GmbH/IHP-Open-PDK#current-status----preview)
repositories describe their open releases as previews and exclude general
production use from their stated readiness. Application tests cannot confer
production qualification on those decks. Tapeout acceptance must identify the
specific foundry/shuttle-approved revisions and requirements for the submitted
design. This does not prevent continued implementation and test-chip validation.

## Present support and remaining work

| Flow | SKY130 | GF180MCU C/D | IHP SG13G2 |
|---|---|---|---|
| Analog models and native symbols | Bundled subset with device/corner regressions | Bundled subsets with device/corner regressions | Bundled subset; managed compiled OSDI models required |
| Analog physical implementation | Bounded recipes, reference layouts and process-RC tests; separate physical assets required | Bounded core-MOS recipes and C/D rule decks; additional Banba evidence has its own scope | Bounded core-MOS recipes and rule decks; not general BiCMOS/RF layout qualification |
| Digital standard-cell implementation | Included locked SKY130 HD platform | Source import and candidate runtime for ORFS 9-track 5 V / 5LM_1TM / 9K | Source import and candidate runtime for ORFS SG13G2 standard cells |
| Digital timing and equivalence | Source runtime bundles 3 library × 3 RC corners; separate UART/APB qualification at those corners | Counter, UART and APB block qualification at declared typical/slow/fast libraries | Counter, UART and APB block qualification at declared typical/slow/fast libraries |
| Chip-level signoff | Unqualified | Unqualified | Unqualified |

The generic digital manifest importer is an integration mechanism; it does not
establish support for a process. Automatic ORFS imports now include explicit
GF180 and IHP profiles beside SKY130 HD and Nangate45. The
[process qualification guide](DIGITAL_PLATFORM_QUALIFICATION.md) defines their
exact library, metal-stack and acceptance-fixture scope. Broader designs, GF180
variants and final desktop release packages still need independent qualification.
Source runtime builds now bundle all three platforms, expose their selection in
the workspace and CLI, and require every advertised platform to pass installation
checks. Published 0.23.0 packages still contain only SKY130 HD.
The UART and APB cases retain their original 10 ns and 20 ns constraints through
mapping, routing, extracted timing and physical-netlist equivalence. These bounded
block results do not establish full-chip closure or complete PVT/RC coverage.
Nangate45 is not a replacement for either target process.

PVT library corners and extracted interconnect corners must be tracked separately.
The [LibreLane timing-corner guide](https://librelane.readthedocs.io/en/latest/usage/timing_corners.html)
documents distinct SKY130 typical/slow/fast libraries and nominal/minimum/maximum
interconnect collateral. A [separate SKY130 platform preparer](DIGITAL_PLATFORM_QUALIFICATION.md#separate-sky130-pvt-and-interconnect-platform)
now captures three library corners, matched physical views and three independent
RC extractions. The [two-block qualification record](validation/sky130-corners-2026-10-06.json)
retains all 18 passing timing pairs and their source-bound extraction evidence.
Source runtime builds now package those matched SKY130 inputs and require all
nine timing pairs during setup. Older payloads retain their single SKY130 library
corner; GF180/IHP still use one extraction condition per process.
Corner execution and timing closure still require evidence for the exact design,
source and engine revision; neither establishes chip-level or foundry acceptance.

See [PDK subsets](PDK_GUIDE.md), [digital limits](DIGITAL_FLOW.md),
[analog closure](ANALOG_CLOSURE.md), [process-RC scope](ANALOG_IMPLEMENTATION_EXTENSIONS.md)
and [reference qualification](REFERENCE_QUALIFICATION.md).

## Required process acceptance

For each process and supported variant, retain an independently reviewable
acceptance design and deliberate-fault cases:

1. Native schematic and hierarchical exchange preserve connectivity, parameters,
   device identities and model units. Unsupported devices stop with a diagnosis.
2. Analog DC, AC, transient and noise checks reproduce reference results over
   declared process, voltage, temperature, load and geometry conditions. Statistical
   tests identify their distribution/model assumptions and do not claim yield.
3. Layout generation and edits preserve connectivity. Run the accepted DRC/LVS
   decks against final streamed geometry, including hierarchy, fill, taps, I/O
   and power connectivity. Retain rule counts, unmatched devices and waivers.
4. Extraction uses declared RC corners with supported devices and coupling. Compare
   schematic and extracted requirements; detect injected opens, shorts, device
   mismatches and parasitic faults. Reject stale or changed geometry/decks.
5. Digital simulation/regression, technology mapping and equivalence pass on the
   intended library. Verify clock/reset assumptions and declared functional coverage.
6. Floorplan, PDN, placement, clock tree and routing complete on the target process.
   Extracted setup/hold timing and electrical checks cover required modes/corners;
   exceptions, unconstrained endpoints and CDC/RDC need explicit review.
7. Chip-level antenna, density/fill, ERC, latch-up/ESD, electromigration, IR drop,
   package/I/O and shuttle-specific requirements are checked with accepted methods.
8. Export an immutable handoff with final GDS/OASIS, netlists, constraints,
   parasitics, tool/deck identities, checksums, reports and reviewed waivers. Obtain
   process-owner or shuttle acceptance for that precise design and revision.

Items 6–8 require capabilities and evidence beyond the current reference flows.
Do not turn a missing engine, unsupported check or absent report into PASS.
The historical included-corner record retains an adversarial macro-export
input-binding defect. Current export code rejects a saved input snapshot whose
project, cell, design, source or available stage identity differs from the
implementation result. Rejection preserves an existing export. This integrity
check does not establish the chip-level handoff and signoff acceptance above.
Broad periodic/RF analyses, general Verilog-AMS and proprietary design-database
compatibility also need separate implementation and qualification before claiming
replacement of workflows that require them.

## Desktop release acceptance

Maintain the seven [automated release gates](RELEASING.md) and qualify the exact
packages on native Windows and Ubuntu: installation, first design, save/reopen,
upgrade/recovery, scaling, accessibility, offline operation and network use.
Record the Windows signing policy. macOS needs its own qualification before being
advertised as a supported packaged platform.

On 2026-10-06, GitHub issues #8, #9, #10 and #31 were closed with unchecked
acceptance lists and no issue comments or attached completion records. Their
closed state supplies no additional acceptance evidence. Preserve that distinction
in [release tracking](RELEASE_FOLLOWUPS.md); obtain actual observations for the
candidate being considered.

## First correctness repair

The timing-evidence repair prevents missing hold paths, invalid or missing
reports, negative total slack and errors in later corners from producing a clean
timing verdict. Independent setup/hold totals, missing-evidence reasons and
per-corner reports remain inspectable. Tests include deliberately incomplete and
contradictory evidence as well as real-engine passing, violating and unconstrained
SKY130 counters. This repairs timing reporting; it does not close the process or
chip-level gates above.

The [2026-10-06 validation record](validation/release-readiness-2026-10-06.json)
retains source hashes, real timing outcomes, the 51 analog device/corner checks,
test totals and the limits of the local environment. Its GF180 electrical cases
cover variant C; that run does not qualify variant D or digital implementation.
