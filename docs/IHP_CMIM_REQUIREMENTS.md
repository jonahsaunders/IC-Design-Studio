# IHP `cap_cmim` source applicability and remaining qualification

**Source applicability checklist, not acceptance.** This contract covers the standard two-terminal `cap_cmim` device only. RF `cap_rfcmim`, MOM, parasitic-capacitor symbols, and varactors have separate interfaces and are not substitutes. The process documentation captured for this assessment is IHP Open PDK documentation commit `f79c1aa616361a5980994feffda1e2766a4b500b` (2026-05-08); exact upstream Git blob IDs, SHA-256 hashes, source paths, and Apache-2.0 license are in [the source ledger](qualification/ihp-cmim-applicability-v1/source-ledger.json). This independently versioned documentation must be reconciled with the application's pinned package, not silently represented as the same revision. The checklist elaborates existing device-family requirements; it does not change acceptance gates or promote a matrix status.

The application package is IHP `cfb96b74cf33877e`, manifest SHA-256 `da58ba2de122d67d232ab20ca4fb353b70bdc68c00ef4279f9be7da640a68ae0`. Its public symbol exposes `c0`, `c1`, `w`, `l`, `m`, and `mm_ok` and emits an `X` call to the two-terminal subcircuit `cap_cmim`; the current default is 7 µm × 7 µm, `m=1`. The source LVS documentation describes a scalable rectangular Metal5/TopMetal1 device, uses `PLUS`/`MINUS`, and lists area, perimeter and multiplicity in its comparison model. The symbol's displayed capacitance is not a physical rating. Physical multiplicity is a number of devices and cannot be inferred from a positive fractional simulation multiplier.

The upstream LVS document identifies the layers as Metal5 and TopMetal1, but the pinned compact-model comment calls its top plate Metal3. Before any plate-dependent voltage claim, reconcile source revisions and map symbol pins, extracted nets and actual mask electrodes with independent physical evidence. Do not assume this comment proves the electrode mapping. The November 3
[physical/archive and process-control readback](IHP_CMIM_PROCESS_CONTROL.md) now
establishes the selected `c0`/`PLUS`/TopMetal1 and `c1`/`MINUS`/Metal5 mapping.
The nominal model comparison reproduces the voltage discrepancy and accounts for
the 300 K versus 27 °C reference difference; missing calibration/tolerances and
operating/reliability limits remain unresolved.

The [ordinary catalog reference integration](IHP_CMIM_LVS_REFERENCE.md) now passes both actual source checking routes and the Windows managed handoff. The original X simulation statement is preserved; Magic removes only its literal statistical selector, while public KLayout uses the pinned physical C form and independently derived per-unit area/perimeter. Changed or ambiguous sources/parameters fail. This closes the selected representation/linkage defect and retains strict native fault detection; exact installed acceptance, remaining physical classes and the applicability requirements below remain open.

## Available physical constraints and representation

The retained public DRC table specifies MIM minimum width 1.14 µm, minimum area 1.3 µm² and maximum area 5,625 µm² per device, MIM spacing 0.6 µm, and specific enclosure and contact constraints. Its main-rule table separately specifies Metal5 enclosure 0.6 µm, TopVia1 enclosure 0.36 µm and a *recommended*, not per-device maximum, 174,800 µm² total chip MIM area. Width and area restrictions must both hold; satisfying them alone is not a complete layout check. Multiple contact implementations, surrounding geometry, spacing, and connectivity must follow the full applicable rules and technology option. The public LVS document says this device is unavailable with Cu BEOL and describes Vmim as an alternative to TopVia1 within the device.

In the pinned Magic DRC file, MIM.a, MIM.b, MIM.c and MIM.f visibly implement corresponding width, spacing, enclosure and minimum-area checks. Its MIM.g maximum-area rule is explicitly left as a question, so a clean run of that deck alone does not demonstrate the published 5,625 µm² maximum. The application also includes a separately locked IHP KLayout maximal deck whose MIM.g rule selects MIM regions with area greater than 5,625 µm²; the IHP public-checker integration runs its main and maximal decks. That is an existing checker capability, not a missing implementation. The [November 2 complete imported-device boundary](IHP_MIM_G_BOUNDARY.md) now verifies the selected below/at/above-limit rectangles at both rotations and four meaningful native faults. Separate actual source-desktop routes show Magic as `NOT_CHECKED` and the public checker as `EXECUTED`; installed and other geometry-class coverage remain open. The pinned upstream Magic PCell has 2–30 µm `w/l` defaults and clamps in its check routine, but the defaults carry a work-in-progress warning. Treat those as generator behavior requiring version reconciliation, not a substitute for the physical rules or a calibrated electrical envelope.

Existing retained acceptance covers six selected size pairs, including 7 × 7 µm, and two rotations using an imported public PCell with native DRC/LVS and physical fault checks; it does not establish every legal size, contact arrangement, array or boundary. The current extracted-electrical source linkage covers that 7 × 7 µm native device at both rotations only. The extracted subcircuit is a device recognition result, not a plate/interconnect parasitic extraction.

## Measured source facts versus compact-model behavior

At process-control measurement condition A.k, the source gives area capacitance 1.35 minimum, 1.5 target, 1.65 maximum fF/µm² at 0 V and 100 kHz. Perimeter capacitance is a 40 aF/µm target at A.l, likewise 0 V and 100 kHz; the table does not supply perimeter min/max. A.k is distinct from adjacent A.k1, which uses 2 V on the top plate. The deterministic model sections use area coefficients 0.9, 1.0 and 1.1 times 1.5 fF/µm² and a 40 aF/µm perimeter coefficient. Exact source and measurement compatibility, perimeter separation and tolerance must be established before treating those coefficients as physical measurements.

The process table gives a breakdown minimum of 15 V and target of 23 V at A.y, with bottom plate 0 V and current forced into the top plate at 1 pA/µm². These are process-control breakdown measurements, **not a stated continuous operating-voltage or lifetime rating**. A.ah measures capacitance versus lower-plate voltage from −10 V to +10 V at 300 K and 1 MHz with top plate grounded. It gives target coefficients −26 ppm/V and +5 ppm/V², without min/max acceptance bounds. Its stated polynomial therefore predicts ratios 1.00076 at −10 V and 1.00024 at +10 V, relative to 0 V. These are condition-specific target predictions, not safe-use bounds or guarantees.

The pinned `cap_cmim` nominal model is a bias-independent geometric C element plus 55 mΩ series resistance; its source contains no corresponding voltage-dependent capacitance expression. That is a concrete applicability discrepancy against the documented target behavior, not proof of a violated guaranteed bound. Resolve the relevant electrode sign, model/source revision and a source-backed comparison tolerance or limitation before any voltage-coefficient qualification. Do not retrofit this conclusion into the completed 27 °C source-model integration result.

The process table's temperature targets are 3.6 ppm/K and 0.002 ppm/K²; A.ad measures capacitance at 0 V and 1 MHz over −40 to 125 °C with reference 300 K. The pinned model uses numerically corresponding coefficients `TC1=3.6e-6`, `TC2=2e-9` and `TNOM=27 °C`, which is 300.15 K, not exactly 300 K. This is a measurement range and coefficient description; it is not an independently established continuous electrical or reliability operating envelope. Reconcile reference temperature and target tolerance before any physical-temperature calibration claim.

## Corner, statistical, and reliability scope

The pinned public `cornerCAP.lib` declares deterministic `cap_typ`, `cap_bcs`, `cap_wcs`, separate mismatch sections and a typical statistical section. Statistical source expressions use Gaussian draws and `mm_ok`-controlled mismatch. The process table leaves the MIM matching coefficient entry blank. The existence of model expressions or a simulator draw does not supply measured matching calibration, seed/correlation rules, or a lifetime guarantee. Define and independently verify those only if supported by an applicable source; otherwise keep them explicitly unresolved. Do not silently treat lower/higher capacitor sections as correlated global process corners.

The process-control tables and A.k/A.l/A.y/A.ad/A.ah conditions and the pinned `capacitors_mod.lib`, `cornerCAP.lib`, mismatch/statistical files, symbol, and Magic sources were examined. Those scoped sources do not state a complete continuous operating voltage, lifetime/derating limit or general model-valid frequency/temperature envelope for this device. Other upstream sources, foundry documentation and calibration data have not been exhaustively reviewed; this is a bounded search result, not a claim that no such source exists.

## Closure checklist

1. **Version and interface:** retain the exact model, symbol, package, license and documentation sources; independently establish `c0/c1` to `PLUS/MINUS` and physical electrode mapping; verify save/reopen, export, multiplicity semantics and historical package locks.
2. **Geometry and DRC:** reconcile the versioned source rules with each actual checker. Cover legal/illegal width and area boundaries, rectangularity, relevant enclosure/spacing/contact variants, both rotations and multiplicity/array behavior. The selected complete imported rectangular MIM.g boundary and both source application routes are now verified; retain their exact scope and extend other required geometry classes and installed behavior. Magic-only results explicitly report that MIM.g was not checked. Preserve no-Cu option and distinguish required from recommended chip-level rules.
3. **Process-control electrical applicability:** independently implement the exact A.k/A.l and A.ad/A.ah measurement definitions, correct terminal orientation, reference temperature and specified values. First establish meaningful source-backed error bounds and model applicability. Resolve the documented voltage-coefficient discrepancy instead of replacing the reference, changing the coefficient, or treating target-only values as guaranteed limits. No additional numerical samples can close an unspecified tolerance.
4. **Corner/statistical behavior:** exercise all applicable deterministic and explicitly supported mismatch/statistical sections with reproducible seeds, parameter scope and observability; establish calibrated interpretation and correlation from suitable primary data or leave it unresolved. Do not infer full statistical validity from nominal model agreement.
5. **Extracted electrical/PEX:** retain exact editor/native masks and extracted device identities across the source-backed physical classes; compare the actual saved application's model and extracted network against independent references, including meaningful geometry/wiring faults. Separately establish whether plate/interconnect parasitics are required and verify a suitable PEX flow; the existing device-only extraction does not cover it.
6. **Installed and platform behavior:** run the actual frozen application, selected package and supported engine on both required hosts; for Windows IHP, exercise the real application-to-managed-Linux route with independently bound host/backend/runtime/model and raw-result receipts. Reopen prior package-locked documents and prove explicit corner selection and staged model identity. The present Linux source experiment and separate source GUI check do not satisfy this gate.
7. **Operating/reliability applicability:** identify source-backed normal bias, current, temperature, frequency, lifetime and derating restrictions, or record each as unresolved. Breakdown and measurement ranges are not safe operating limits. A complete-family claim remains open while mandatory applicability or evidence is missing.

The selected complete imported rectangular maximum-area boundary and explicit source application coverage reporting are now closed submilestones. A separate [minimum-boundary source experiment](IHP_CMIM_MINIMUM_BOUNDARIES.md) verifies ten modified imported rectangles around the width and area limits, two Magic positives and four exact fault causes. It adds one Vmim cut after the generator omits contacts at these sizes; the native MIM.d check covers TopVia1, not that Vmim layer. Measured enclosure is therefore not native enclosure-rule coverage, and the original producer assertion failure remains separately retained. The next physical work is extending these selected cases to the remaining enclosure, spacing, contact, array and other geometry classes, with separate installed acceptance. The default 2–30 µm PCell rectangles do not reach the maximum and their limits were not changed. No KLayout result is inferred from Magic. A separate high-value task is a source-faithful A.ah comparison at its stated setup, reported as a target/model discrepancy until a justified tolerance and plate mapping exist. Neither task alone closes the whole family.

The November 3 [shared-electrode spacing experiment](IHP_CMIM_SPACING_BOUNDARY.md)
closes one additional physical class: two complete imported 7 × 7 µm capacitors
on shared electrodes at 0.58/0.60/0.62 µm MIM gaps and both rotations, with exact
native findings, raw two-device extraction, strict LVS and four detected faults.
Its predeclared physical C reference and source-derived contact arrays retain
their separate scope. This does not establish independently wired electrodes,
other contact/enclosure variants, arbitrary arrays, parasitics or installed behavior.

The later [isolated-electrode experiment](IHP_CMIM_ISOLATED_SPACING.md) closes the
selected two-device/four-port 7 × 7 µm class at both rotations, including an
ordinary catalog pair and strict wrong-width fault. Its source-rule negative
exposed a real wide-metal false pass. The [versioned supplemental check](IHP_METAL_SPACING_SUPPLEMENT.md)
now catches it alongside the unchanged original decks. This adds a bounded class;
it does not extend acceptance to all spacing/contact/enclosure variants or installed execution.


The November 3 [reusable enclosure/contact workflow](IHP_CMIM_ENCLOSURES.md)
adds the finite Metal5 MIM.c and TopVia1 MIM.d boundary class with all twelve
layouts, six faults and independent native/Windows readback. It does not infer
a Vmim enclosure limit or qualify arbitrary contacts. The [public process
comparison](IHP_CMIM_PROCESS_CONTROL.md) now ships its small authenticated
historical electrode input, so a public checkout no longer requires the
separately retained full archive. Calibration and operating/reliability
requirements remain unresolved.


The November 3 [physical multiplicity workflow](IHP_CMIM_MULTIPLICITY.md) closes
the selected two-unit shared-electrode linkage: ordinary catalog m=2 and two
explicit m=1 references pass at both rotations; six reference/physical faults
are detected. Their actual captured references and raw extracted units agree
with independent literal RC at the declared finite numerical conditions across
three deterministic capacitor sections. Both-host readback passes. This adds
integer count and parallel series-resistance integration evidence; arbitrary
arrays, nested/statistical multiplicity, PEX, physical validity and installed
acceptance remain separate. Operating/reliability and calibration gaps remain.
