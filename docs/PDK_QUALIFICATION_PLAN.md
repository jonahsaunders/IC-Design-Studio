# PDK qualification in twelve chunks

The target is analog and digital design on SKY130, GF180MCU C/D and IHP SG13G2.
No target is currently qualified for complete-chip tapeout. Work proceeds in the
order below; a passing small reference design keeps its original scope.

The [machine-readable matrix](qualification/pdk-matrix.json) is the coverage
record. It includes 125 process/workflow requirements and all 255 bundled catalog
entries, including utilities and unavailable devices. Every requirement points to
a defined fixture, procedure, expected result, operating conditions, remaining
automation work and status. Each device has separate interface, simulation and
physical tests. These are test contracts; many are not executable yet.

The matrix also records the exact package revisions, source-lock hashes, model
include sections, device terminal/parameter mappings, digital libraries, metal
options and current digital operating points. It does **not** equate this bundled
subset with the complete upstream PDK. Upstream completeness and the remaining
device-specific operating envelopes are explicit open requirements.

## Sequence and gates

| Chunk | Achievable batches | Completion gate |
|---|---|---|
| 1. Qualification matrix | Inventory bundled inputs; enumerate tests and missing upstream coverage; validate identities and completeness. | Every requirement has a test, expected result and status. Missing coverage is visible. This planning gate is defined; process execution is not qualified. |
| 2. Toolchain | Compatible KLayout CLI; hosted OpenROAD result; clean Linux install; clean Windows/WSL install; native rule coupons and fault controls. | Exact fresh runtimes execute every required valid/invalid case correctly. |
| 3. GF180 geometry | Integrate via pitch; integrate tap spacing; counter; UART; APB. Establish a separate matched D platform. | Production-flow geometry, antenna, extracted timing and equivalence pass without changing the original design constraints. |
| 4. GF180 density | Resolve active/poly fill; resolve each metal layer; check exclusions; rerun all post-fill checks. | Zero required density/geometry findings and passing connectivity, extraction, timing and equivalence. The isolated C counter currently has 555 density markers. |
| 5. IHP geometry/fill | Resolve the twelve observed findings, grouped by rule; recheck counter; UART; APB. | Complete final-layout rules, connectivity and extracted performance pass. |
| 6. SKY130 rules | Reconcile rule inventory; enable FEOL; check density/antenna; final-GDS LVS; negative controls. | Every required rule group executes; no silently disabled coverage or unexplained violations. |
| 7. Devices | Reconcile upstream inventory; MOS; resistors; capacitors; diodes; bipolar; remaining devices. Treat IHP RF separately. | Every supported device passes terminal/parameter/model, operating-envelope, layout and extracted-connectivity tests. Unsupported required devices remain blockers. |
| 8. Extraction/corners | Wire coupons; vias; device parasitics; coupling/fill; independent RC corners; complete required PVT/RC pairs. | Independent references agree within frozen, source-backed tolerances and injected faults fail. |
| 9. Analog blocks | Mirror; differential pair; amplifier; reference; oscillator; noise/statistics; separate IHP bipolar and RF batches. | Schematic and extracted results meet numerical specifications fixed before execution, across declared conditions. |
| 10. Digital/mixed signal | Select larger controller; functional coverage; clock/reset review; physical/timing closure; analog/digital integration. | Functional, equivalence, all-mode timing/electrical and final-layout checks pass. |
| 11. Complete chips | Assemble chip; electrical-rule review; ESD/latch-up review; EM/IR review; I/O/package review. | Every required chip-level check passes on final geometry and the actual package/modes. |
| 12. Delivery/tapeout | Exact Windows package; exact Ubuntu package; independent handoff reproduction; submission preparation; external acceptance. | Consumer workflows pass and the required foundry/shuttle acceptance covers the precise submitted design, revisions and waivers. |

## Locked starting scope

| Analog target | Bundle revision | Indexed / placeable | Physical option and present digital coverage |
|---|---|---|---|
| SKY130 A | `24bc6d0bfd6a0224` | 74 / 71 | Local interconnect plus five metals; HD digital library; 3 library by 3 RC conditions. |
| GF180 C | `627ca682d68e1e92` | 68 / 64 | Five metals, 0.9 micrometre top metal, MIM, HRPOLY1K; digital 9-track 5 V, 5LM_1TM/9K; 3 library by 1 RC condition. |
| GF180 D | `7dd87219f1333dbb` | 68 / 64 | Five metals, 1.1 micrometre top metal, MIM, HRPOLY1K; separate `gf180d` 9-track 5 V / 5LM / 11K production references; both installed-runtime reference gates passed. |
| IHP SG13G2 | `3abac20fcb57e184` | 45 / 35 | Five ordinary and two top metals; SG13G2 digital cells; 3 library by 1 RC condition. MOS, bipolar and RF qualification remain distinct. |

All digital profiles start from ORFS
`eaba6576441bf7c1743ea56ecdb1904210ec02c2`. SKY130's prepared digital profile
uses the additional checksum-locked Volare assets listed in the matrix.
GF180 primitive models and physical decks have separate source locks; the
matrix retains both. Do not infer that matching analog device names establish
matching digital views or matching metal stacks.

Current digital library points are:

| Target | Typical | Slow | Fast |
|---|---|---|---|
| SKY130 HD | 1.80 V, 25 C | 1.60 V, 100 C | 1.95 V, -40 C |
| GF180 C digital | 5.00 V, 25 C | 4.50 V, 125 C | 5.50 V, -40 C |
| IHP digital | 1.20 V, 25 C | 1.08 V, 125 C | 1.32 V, -40 C |

These are selected library conditions, not the valid operating envelopes for
all analog devices. IHP's generic slow/fast aliases leave some HBT, capacitor and
resistor sections at nominal; the exact include mappings are in the inventory.
Their actual best/worst and statistical sections need their own tests.

## Using the record

Run the coverage check from the repository root:

```sh
python scripts/check_pdk_qualification.py
```

The release documentation check also invokes it. It verifies all bundled asset
hashes, exact device coverage, required process/workflow rows, test contracts,
referenced runner paths and the hashes of historical evidence records. Its
success is named `matrix_consistent`; process qualification remains
`unqualified`. Missing evidence and unsupported devices cannot become passes.

Current execution statuses are `not_run`, `partial`, `failed`,
`needs_definition`, `unsupported` and `passed_reference`. A `partial` row identifies
prior limited evidence without claiming the complete test passed. Schema 3 retains
the chunk 2 toolchain references, which require the complete,
hash-bound [acceptance record](validation/toolchain-2026-10-07.json). It requires
both operating systems, valid/fault controls and every required hosted step on
the recorded source. It separately binds the [chunk 3 acceptance record](validation/gf180-geometry-2026-10-07.json)
to current production evidence, both operating systems, actual rule/fault controls,
all required timing conditions and the captured C/D technologies. Device rows,
density and later chunks cannot inherit either pass. Later completed gates need
their own reviewed acceptance schema and records;
preserve previous failures rather than merely changing a status string.

Chunks 1 and 2 are complete within these boundaries. On the corrected application
backend, each installed runtime passed 26 digital checks, 15 timing pairs, three
audited exports, seven tool controls, sixteen process-rule controls and nine
digital physical controls. Required hosted implementation steps passed on
`7feca0695f586ff84c8d2111b528076891a50e77`. The record retains the initial
antenna-diode coverage failure and its correction.

Chunk 3 is complete within its reference scope. The [production GF180-C batch](validation/gf180-production-geometry-2026-10-07.json)
passes main geometry, antenna, extracted timing and equivalence on counter, UART
and APB with unchanged RTL/constraints and PDK sources. The application generates
and captures the two corrected recipes. The separate [matched D batch](validation/gf180d-production-geometry-2026-10-07.json)
now also passes these reference gates, with the actual 11K technology and
extraction selection independently audited. The updated runtime includes all
four digital profiles. Each Linux and Windows installation passed 34 digital
checks, 18 timing pairs, four audited exports, seven tool controls, 16 process-rule
controls and 12 digital physical controls. Independent full-deck audits on each
OS's C/D counters pass main geometry and antenna while retaining density failures.
The [installed C/D UART/APB batch](validation/gf180-cd-installed-workloads-2026-10-07.json)
also passes geometry, antenna, all 12 library-corner timing checks and equivalence
on application source `1989dbf`, with unchanged design constraints. The installed
Windows catalog also passes selection, C/D save/reopen, corner reset and undo.
Its initial report-writer failure is retained; the corrected checker completed
the entire workflow and produced a source/runtime-bound report.

Windows setup failed twice with WSL service connection errors before the third,
unmodified full setup passed. Both failures are retained. Eight read-only
idle/startup cases, two full integrity checks and six saved-job dispatch trials
passed, but no root cause or reliability fix is established. Public-release
startup reliability remains open.

Hosted run `37652837883` passed on source
`1989dbf`; independent input, source and artifact audits passed 28 counter stages,
64 UART/APB stages across four profiles and 16 additional SKY130 corner stages.
The SKY130 export audit retains three numerically distinct interconnect
extractions and all 18 library/interconnect timing pairs. Hosted-upload omissions
were restored only by exact hash in a separate audit copy; original downloads
remain unchanged. Desktop build run `37652838673` passed all five jobs on the same
application source; exact consumer-package acceptance remains chunk 12 work.
The acceptance checker passed the full 1,444-test suite (63 skips); the subsequent
GUI report-only correction passed the actual installed-catalog workflow again.
Full density checks still report 555, 5,796 and 4,416 markers for each variant respectively;
these remain chunk 4 failures. No process or complete chip is qualified for tapeout.

Before each batch, freeze its exact inputs, numerical limits and negative
controls. After the batch, preserve commands, versions, input/output hashes,
native reports, measurements and failures. A new device/model/geometry/tool
revision requires appropriate requalification. A numerical agreement threshold
is not a circuit-performance specification; both must be declared where relevant.

The complete upstream inventory, general analog/RF numerical specifications,
representative full-chip designs, package choices and foundry/shuttle acceptance
target remain open. They have tests and blocking conditions in the matrix;
no guessed limits or synthetic acceptance evidence fill those gaps.

See [release targets](PUBLIC_RELEASE_TARGETS.md),
[digital qualification](DIGITAL_PLATFORM_QUALIFICATION.md),
[bundled PDK scope](PDK_GUIDE.md) and
[release gates](RELEASING.md) for the existing evidence boundaries.
