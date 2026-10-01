# The path forward

## Current dev25 priorities

The [current source extensions](ANALOG_IMPLEMENTATION_EXTENSIONS.md) add native
bus/array semantics, reviewed physical specialization with regeneration, bounded
SKY130 parallel-device recipes and stronger process-RC integrity checks. The
older limits and numerical evidence below retain their original source scope.

The [integrated analog workflow](ANALOG_CLOSURE.md) is available in source:
saved extraction models, explicit MOS-device semantics, constrained layout ECOs,
durable verification campaigns and transactional scripted edits. The
[dev25 update](UPDATE_0.22_DEV25.md) continues from that implementation. Older
milestones below retain their original scope and are not an unimplemented-feature
list.
Dev25 adds saved amplifier diagnostics, seeded statistical campaign results and
bounded calibrated hierarchy; the [reference guide](ANALOG_REFERENCE_WORKFLOW.md)
defines their supported configurations.

The current acceptance sequence is:

1. Qualify the exact candidate on all seven required hosted jobs, then collect clean
   Windows/Linux, physical LAN/VPN and signing-policy observations. Keep earlier
   drafts tied to their own commits. See [release gates](RELEASE_FOLLOWUPS.md)
   and [release status](RELEASE_STATUS.md) for current candidates. The historical
   dev25 draft at `a88cfe1cfe20254638b7bd97ec9128e843578282` passed the six
   hosted gates required at that checkpoint. Its [acceptance handoff](DEV25_ACCEPTANCE_HANDOFF.md)
   retains the corresponding manual checks; later source needs fresh gates.
2. Maintain the [76-case process-RC qualification](validation/dev25/process-rc.json)
   on the selected candidate, using saved benches, operating conditions and
   deliberate geometry/netlist faults with pinned Magic, Netgen and ngspice.
   That retained baseline used a flat, unaliased process path with numeric
   interconnect R, MOS and MiM subcircuits. Current source additionally supports
   bounded physical-hierarchy flattening in the disposable extraction workspace,
   unambiguous aliases and supported native/model-backed R/C devices. Maintain
   the [newer integrity and engine regressions](ANALOG_IMPLEMENTATION_EXTENSIONS.md#process-rc-integrity)
   alongside conserved-capacitance and AC checks. Broader device/process coverage
   still requires separate support and qualification.
3. Maintain the [216-pair amplifier qualification](validation/dev25/two-stage-opamp.json)
   across its 27 conditions, four saved fixtures and matched-pair layout update.
   Extend load, bias and geometry support only with new unchanged-requirement
   schematic/extracted comparisons and physical checks.
4. Preserve the [1,152-case statistical baseline](validation/dev25/statistical-campaign.json)
   and its final-source smoke, durable recovery and uncertainty reporting.
   Run the [two-host protocol](CAMPAIGN_WORKER_ACCEPTANCE.md); physical worker
   hosts and shared-filesystem locking still need separate evidence.
5. Qualify calibrated extraction across its supported hierarchy while preserving port
   maps, instance parameters, coupling scope, revision identity and failure gates.

Consumer hardware, two-host campaign behavior and foundry signoff cannot be
inferred from source tests. Remaining longer-term work also includes HVI
conversion warnings, broader detector PVT/transient checks, general offline
editing, managed internet hosting and measured desktop responsiveness.

The [dev25 desktop measurements](validation/dev25/desktop-scale.json) provide
a historical correctness and timing baseline for two workloads under offscreen Qt 6.8.3.
The three-level amplifier bank's median schematic/layout edits are 137/206 ms;
the synthetic 500-device, 10,000-shape workload takes 1.70/1.74 s. Reduce that
large-edit latency before claiming responsiveness acceptance. The
[experimental follow-up](DESKTOP_RESPONSIVENESS.md) removes redundant copying
and icon drawing and introduces a 1,500 ms regression ceiling for every measured
edit/undo/redo sample. Later [recovery and workflow measurements](RELIABLE_DESIGN_WORKFLOWS.md)
and [selection-rendering measurements](INTERACTIVE_RENDERING_PERFORMANCE.md)
retain their own hosts and narrower performance claims. Sub-200 ms native editing remains a further goal.
Repeat the checks on native consumer displays;
offscreen repaint timings do not measure hardware presentation latency.

## Experimental dev21: workflow and recovery

The [dev21 update](UPDATE_0.22_DEV21.md) adds component shortcuts, a persistent
workflow panel, hover selection, unsent review draft recovery, reuse of isolated
recovery snapshots and an explicit native desktop acceptance tool. Remaining
work includes consumer hardware acceptance, broader physical qualification,
general offline design editing and further measured responsiveness improvements.

## Experimental dev20: detector consistency and runnable HSA bench

The [real-project workflow](OPEN_PROJECTS.md) adds bounded Xschem array import,
reviewed layout attachment, exact layout text exchange and a pinned overvoltage
regression. The external detector now passes strict full-circuit LVS with a verified upstream
extraction correction, and its HSA bench uses first-point startup hints. [Submitted review actions](REVIEW_RECOVERY.md)
now survive restart. Unowned layout selections avoid rebuilding unrelated
footprint groups on each move.

The next acceptance work is concrete: investigate the remaining source-to-GDS HVI
conversion warnings and broaden detector PVT/transient coverage; run physical LAN/VPN and consumer Windows/Linux checks; establish signing policy;
then broaden recovery performance and offline editing. Hosted or loopback tests
do not close the hardware acceptance items. Older milestones below are history.

Our goal is an independent open design environment that makes circuit intent, experiments and physical implementation easy to follow. Compatibility with Xschem, ngspice, KLayout, Magic and Netgen remains part of that direction. This roadmap expresses priorities and acceptance criteria, not promised delivery dates.

## Experimental dev18 implementation

[Guided network hosting](LIVE_COLLABORATION.md#host-a-session-on-your-network)
creates encrypted sessions with invitation-scoped trust, connection checks and
saved host restart. Schematic notes support direct selection, text editing,
dragging, deletion and undo, including in shared sessions. The next hosting work
is qualification across physical LAN/VPN devices and firewall configurations;
managed internet hosting and relay service remain separate work.

## Experimental dev17 implementation

The [local server button](LIVE_COLLABORATION.md#start-a-local-server-with-a-button)
starts the included collaboration service, handles its key automatically and
restarts saved local workspaces from the dashboard. This local-server mode is
limited to the same computer; the later network-hosting wizard and reachable
HTTPS team servers support other computers.

## Experimental dev16 implementation

The [workflow and review update](WORKFLOW_REVIEW_0.22.md) adds automatic workflow
checks, selected testbench context, visual ECO inspection, reviewer permissions
and threaded checkpoint discussions. Subsequent work added analog reference
qualification, durable submitted-review recovery and unsent drafts. Broader
matched layouts, a general offline design-edit queue, notifications and further
editing-latency improvements remain open.

## Experimental dev14 implementation

The [engineering workflow guide](PROFESSIONAL_WORKFLOWS.md) records the implemented document services, editing improvements, parameter variants, analog references, test matrices and team review, with measured performance and explicit qualification limits. The remaining priorities below continue beyond this increment.

## Foundation already available

The current application has native schematic/layout editing, buses and instance arrays, reusable cells, saved simulation setups, waveform tools, analog optimization and campaigns, reviewed Xschem exchange, locked PDK adapters, linked physical geometry and bounded extraction. It also includes the [digital workspace](DIGITAL_WORKSPACE.md), [VGA Playground](VGA_PLAYGROUND.md), [mixed-signal SAR](MIXED_SIGNAL_SAR.md) and [Student Hub](STUDENT_HUB.md). See [release status](RELEASE_STATUS.md) for tested source/package identities; the older milestones above retain their original scope.

## 1. Make releases dependable

**Next priority.** Run fresh-machine acceptance on Windows and Linux, including import, first simulation, save/reopen, model paths with spaces, cancellation, recovery and upgrade settings. Add signed Windows distributions when signing infrastructure is available. Qualify scaling, keyboard navigation, screen-reader names, text contrast and the macOS source workflow.

**Done when:** each advertised platform has a reproducible install-to-result test and attached evidence. “Built” and “executed successfully” are separate release states.

## 2. Make native design a strong destination

Progress in [0.21.1.dev1](UPDATE_0.21.1.md): a small parameterized hierarchy now covers repeated connected moves, exact undo/redo, stable identities and reviewed exchange after source removal. Exported ports reuse their own net labels, avoiding collisions with other nets and repeated label growth. Broader editing and exchange qualification remains open.

Extend the supported native bus/array, parameterized hierarchy, symbol and model-expression subsets with explicit preservation contracts. Improve connection-preserving move/stretch behavior on dense designs, with previews and predictable undo. Broaden migration fixtures across common open libraries, and improve the review of unsupported constructs.

**Done when:** a representative hierarchical project can be imported, migrated, edited, exported, reimported and compared without unexplained topology or parameter changes. Native projects remain usable without Xschem installed.

## 3. Make each PDK workflow reproducible

Add managed, pinned downloads with progress, interruption/retry, storage estimates and revision rollback. Expand model and symbol adapters, guided OSDI provisioning, device-family smoke circuits and corner evidence. Make PDK capabilities searchable and pair physical recipes with matching extraction/rule decks.

**Done when:** every advertised process/device subset lists its model revision, tested engine build, representative circuit results, physical support and known exclusions. Registration alone never becomes a “qualified” badge.

## 4. Close the electrical–physical loop

Progress in [0.22.0.dev1](UPDATE_0.22.md): connected translation/stretching with physical component guards, queued multilayer route proposals with vias, bounded length tuning and shields, a declarative PCell library, and captured relative KLayout rule dependencies. New geometry is traced to design and technology inputs. Broader process device qualification and calibrated hierarchical extraction remain open.

Extend parametric device coverage and routing feedback. Improve hierarchical extraction, calibrated resistance/capacitance, coupling support, DRC/LVS cross-probing and review of stale physical links. Build process-specific tests around reusable blocks rather than isolated shapes.

**Done when:** a declared process flow can trace a schematic change through regenerated geometry, verification, extraction and before/after specification results with reproducible inputs.

## 5. Deepen experiments and reporting

Build on the existing [analog optimizer](ANALOG_OPTIMIZER.md): adaptive/Bayesian search, reusable device characterization, sensitivity, saved diagnostic fixtures and statistical campaigns are implemented within documented bounds. Broaden reference circuits, distributions, correlation studies, reporting and waveform retention without treating sampled pass fractions as manufacturing yield. Extend convergence diagnostics and scheduling. Advanced periodic and harmonic-balance analyses need engine support, explicit semantics and reference circuits; they remain future work.

**Done when:** every new analysis has a numerical reference, a clear failure state, progress/cancellation behavior and saved inputs that reproduce the result.

## 6. Scale and collaborate

Progress in [0.22.0.dev1](UPDATE_0.22.md): hierarchical file XOR by layer/datatype, exact area summaries, saved reference snapshots, geometry queries, tiled density and bounded fill/rounding. A reproducible 10,000-square GDS/OASIS workload checks the comparison path. This does not establish large-layout interactive viewport performance.

Profile large schematics, geometry and waveform sets and continue measured rendering/indexing improvements. Extend reusable libraries, project diffs, plugin/adapter boundaries and regression automation. Build beyond existing submitted-review and draft recovery toward general offline design editing and richer review coordination. Trusted campaign workers already support qualified shared filesystems; [two-host acceptance](CAMPAIGN_WORKER_ACCEPTANCE.md) remains separate from local tests. Managed remote compute and automatic internet deployment remain future work.

**Done when:** published workload definitions and measured responsiveness justify the supported scale. Collaboration preserves revision identity, result provenance and recoverable edits.

## How to help

Small real examples are especially useful: a wire move that breaks a net, a symbol that cannot migrate, a model corner that fails, or a layout finding that is hard to locate. Open a focused issue using the repository templates. Proposals should describe the user's task, the expected behavior and a minimal acceptance example. See [CONTRIBUTING.md](../CONTRIBUTING.md).
