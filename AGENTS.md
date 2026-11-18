# IC Design Studio development priorities

## Tapeout first

Deliver the shortest reproducible path from an editable design to an accepted
tapeout handoff. Treat complete tapeout functionality as a release goal for
each declared process, variant, and flow. Use the
[release targets](docs/PUBLIC_RELEASE_TARGETS.md) for the required evidence and
the [PDK matrix](docs/qualification/pdk-matrix.json) for current coverage.

1. **Start with one end-to-end SKY130A target.** Use the existing SKY130 HD
   UART as the first digital fixture. Choose a named foundry or
   shuttle flow and lock its accepted stack, libraries, decks, template, tool
   versions, and submission checks. Rebuild from a clean checkout, run the
   actual preflight, and prioritize the first failure that prevents a complete
   handoff. Use the pinned inverter and two-stage amplifier to exercise analog
   schematic, layout, extraction, and post-layout comparison in parallel when
   their inputs are available. [Existing digital fixtures](docs/DIGITAL_PLATFORM_QUALIFICATION.md) ·
   [Example shuttle requirements](https://tinytapeout.com/specs/)
2. **Close the chip-level gaps on the chosen target.** Cover hierarchy and
   interfaces, functional simulation and equivalence, floorplan and power,
   placement, clocking and routing, extracted setup and hold across required
   modes and PVT/RC corners, and post-layout analog specifications. Check final
   streamed geometry for DRC, LVS, extraction, antenna, density/fill, ERC,
   latch-up/ESD, EM/IR, I/O, and packaging wherever the target requires them.
   Use accepted engines and decks. Add deliberate faults for failure modes
   that could otherwise report success. Surface failed checks in the editor
   with the exact rule, net or geometry, and the source revision.
3. **Prove the handoff before expanding.** Run the accepted downstream checks
   on the exact exported package and independently verify streamed hierarchy
   and pins. Include the final geometry, netlists,
   constraints, parasitics, reports, reviewed waivers, provenance, and checksums
   required by the submission profile. Verify the normal desktop workflow on
   native Windows and Ubuntu and run the [release gates](docs/RELEASING.md) on
   the same candidate. Record external acceptance for the exact submission
   before calling that scope tapeout-ready. Public-deck tests count as reference
   evidence. Record missing tools, decks, or approvals as blockers.
4. **Extend the proven path by flow and process.** Qualify representative
   analog and mixed-signal submissions, then repeat the handoff for GF180MCU C,
   GF180MCU D, and IHP SG13G2. Reuse the same preflight, review, and export
   machinery. Bind numeric and physical evidence to each process, option, and
   flow independently. Compare any fabricated reference with its simulated
   requirements when silicon measurements become available.

## Match competing workflows, then exceed them

Track parity by tasks users can finish. Record the reference tool and version,
fixture, expected output, remaining gap, and passing evidence for each task.
Use [Features to add](FEATURES_TO_ADD.md) as the feature inventory. Cite its
stable IDs in implementation and qualification work, and start with the
highest-impact gap on the active tapeout path.

| Workflow | Compare against | Measure |
| --- | --- | --- |
| Analog and custom IC | Cadence Virtuoso, ADE, and Spectre. Xschem and ngspice. | Hierarchical capture, parameterized devices, reusable testbenches, corners and statistical runs, and schematic-to-extracted agreement against design specs. |
| Custom layout and verification | Virtuoso Layout Suite, Pegasus, and Quantus. KLayout, Magic, and Netgen. | Constraint-aware placement and routing, schematic/layout cross-probing, geometry and connectivity round trips, rule coverage, and time to diagnose and fix a real violation. |
| Digital implementation and signoff | Cadence Genus, Innovus, Tempus, and Voltus. Yosys, OpenROAD, OpenSTA, and ORFS. | RTL simulation and equivalence, routability, setup and hold, power and area, and deterministic handoff at the same constraints. |
| Mixed-signal, RF, and exchange | Licensed Cadence workflows and appropriate open references. | Co-simulation, model and netlist fidelity, periodic and noise analyses, and transfer of design intent through documented interchange formats. |

[Cadence custom IC workflow](https://www.cadence.com/en_US/home/resources/datasheets/virtuoso-layout-suite-ds.html) ·
[Cadence digital flow](https://www.cadence.com/en_US/home/solutions/advanced-node-solutions/digital-advanced-node.html) ·
[ngspice documentation](https://ngspice.sourceforge.io/docs.html) ·
[KLayout verification](https://klayout.de/doc/manual/lvs_overview.html) ·
[OpenROAD Flow](https://openroad-flow-scripts.readthedocs.io/en/latest/mainREADME.html)

Build original interfaces around the same engineering outcomes. Follow Apple's
guidance for keyboard access, visible focus, clear feedback, and reversible edits.
Use lawful reference designs, licensed engines where available, and documented
formats. Report competitive results only for workloads actually compared.
[Apple's design principles](https://developer.apple.com/design/human-interface-guidelines/design-principles/) ·
[Apple's accessibility guidance](https://developer.apple.com/design/human-interface-guidelines/accessibility)

Aim to win first on setup-to-first-result, time to fix a verification failure,
reproducible handoffs, and recovery after interrupted work. Use the same design,
hardware, constraints, and process inputs for comparisons. Report median and
tail latency, resource use, output correctness, and quality of results. Count
a speed gain only when the design requirements still pass. Extend parity and
demonstrated advantages across analog, digital, and mixed-signal workloads.

## Move quickly and preserve evidence

- Keep one lead tapeout target and a short list of its blocking deliverables.
  Ship small changes through the app's normal entry points. Integrate existing
  engines and reuse the repository's adapters before writing new engines.
- Run focused source and desktop checks during iteration. Run independent
  checks and packaging concurrently when both can consume verified shared
  inputs. Reuse pinned tools and builds with exact identity checks. Continue
  independent work while hosted jobs run. Run the full required gates for the
  selected candidate and retain installed evidence separately.
- Measure time to first useful failure and to a testable installer, including
  queue and setup time. Fix the largest measured bottleneck and measure again.
  Evaluate the Windows core-test and packaging overlap described in the
  [roadmap](docs/ROADMAP.md#make-feedback-faster-alongside-feature-work).
- Update the qualification tracker with the current target, exact artifacts,
  passed gates, next blocker, and its next executable check. Use dates and
  forecasts only where the remaining dependencies and evidence support them.

## Qualification progress tracking

The user wants progress on chunks 1–12 tracked and updated whenever we work on
this project. Keep `docs/QUALIFICATION_PROGRESS.md` current when evidence,
completion gates, blockers, priorities or forecasts change. Use
`docs/qualification/pdk-matrix.json`, `docs/PDK_QUALIFICATION_PLAN.md` and the
referenced validation records as the authoritative qualification sources.

Record the snapshot date and relevant code commit. Separate verified results,
preliminary work and forecasts. Keep forecasts conditional, explain their
confidence and revise them when new evidence changes the outlook. Do not infer
overall completion from test counts or from the number of closed chunks. Do not
change a completion gate or promote a partial device to make the tracker look
more complete. Preserve the historical scope of each acceptance record.

Update the tracker during project work; the user chose this instead of scheduled
background checks. A documentation-only tracker update need not interrupt long
running CI jobs by triggering a new push. Preserve it locally and include it in
the next appropriate project push, reporting that distinction to the user.

The user also wants every completed work response for the current and future
chunks to include that chunk's estimated completion percentage. State its
uncertainty and distinguish engineering estimates from verified acceptance.
Keep the estimate in the progress tracker consistent with the final response;
do not increase it merely because more tests were run.

For local source feedback, follow `docs/CI_FEEDBACK.md`: run WSL suites from a
verified source snapshot on native Linux storage, not the Windows-mounted
checkout. On Windows, use a short writable temporary path and verify ordinary-
user junction-test prerequisites before launching the lane. Keep all source
identity checks, timeouts and protection tests intact; no Windows administrator
access is needed. Retain environment failures and final acceptance separately.
