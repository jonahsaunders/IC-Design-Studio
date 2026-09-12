# Experimental engineering workflows — dev14

## Dev19 qualification increment

Use the [open-project workflow](OPEN_PROJECTS.md) to reproduce the external SKY130
overvoltage import and its explicit physical findings. [Review recovery](REVIEW_RECOVERY.md)
preserves submitted actions through lost acknowledgements and restart. Unowned
shape moves now avoid unrelated footprint grouping; the complete pipeline still
measures rendering, recovery and checks separately. The full offline-edit queue
and broader physical acceptance remain open.

This update connects everyday editing, physical implementation, verification
and team review. Existing projects remain readable; the new test plans and
constraint records are optional project data.

## Find the next action

In dev16, open **Schematic → Design workflow** or **Layout → Design workflow**. Select a circuit or its saved testbench to see
device-link status, missing connections, matching findings and the latest
physical comparison. The buttons open the existing editors and verification
tools. Checks update automatically after editing or switching cells. Select the saved testbench in the workflow; its corner and temperature remain visible. Old results are
marked stale and never become a pass for the new revision.

| Task | Entry point |
| --- | --- |
| Move by a precise distance | **Edit → Move selection precisely** |
| Cycle overlapping objects | **Alt-click**, or **Tab** over the canvas |
| Resolve parameterized physical instances | **Schematic-driven layout → Resolve parameter variants** |
| Place missing and update changed devices | **Schematic-driven layout → Select missing and changed devices** |
| Generate an analog reference bank | **Layout → Generate → Generate analog reference layout** |
| Create an amplifier | **File → Examples → New PDK amplifier**, then choose models and supply |
| Compare multiple tests and corners | **Analysis → Verification test plans** |
| Review with teammates | **Tools → Collaboration → Team review** |

Numeric moves have a positional preview, grid validation, cancel, and one undo
step. A changed revision, mode or selection disables an old preview. Connection
preservation rules run when applying. Selection keeps the viewport stable when
the properties area changes size.

## From a schematic change to layout

1. Open the circuit and review **Schematic-driven layout**.
2. If instances override cell parameters, choose **Resolve parameter variants**.
   Review the concrete cell variants before applying. Identical parameter sets
   share a variant; different values get separate physical masters. The resolved
   electrical topology and values must remain identical.
3. Select missing and changed devices. Review the placement and geometry proposal,
   including route and terminal updates. Unsupported devices require an explicit
   physical implementation. Removal of orphan geometry remains a separate choice.
4. Check connections and analog constraints. Generate or edit routes as needed.
5. Select the saved testbench and run physical verification. Inspect failed stages
   and findings, then compare schematic and post-layout measurements.
6. Save a named team checkpoint and attach the verified inputs and results.

Variant creation retains existing geometry. A changed footprint still needs the
ordinary geometry update and connection checks. Native SPICE instance overrides
that lack a supported physical parameter mapping produce an explicit error.

## Analog references and process qualification

The linked SKY130 recipes now cover a current mirror, differential pair and
five-transistor amplifier. The amplifier has saved operating-point and AC tests.
The reference bank places 2–8 standard, single-finger MOS devices, includes body
contacts, connects metal1 terminal columns to metal2 buses, and labels each port.
Equal pairs receive matching and symmetry constraints that check actual geometry
after edits. This is a spacious reference placement, with no statistical mismatch
or density optimization claim.

The technology-neutral amplifier template uses the selected catalog entries and
supply. Its dimensions, bias and measurement limits are starting values to review
for that technology. Only the explicitly pinned SKY130 reference below has the
associated physical regression gate.

The physical workflow rebuilds the package specified by
`examples/sky130-qualification-lock.json`, builds pinned Magic and Netgen, and runs
`scripts/qualify_analog_process.py` with ngspice. Its 45 cases are:

- 30 comparisons against independently written circuit netlists: two saved
  analyses per block at nominal/ss/ff, 27 °C, and nominal at 0 and 85 °C.
- Six complete nominal physical flows: schematic simulation, full declared DRC,
  LVS extraction, Netgen comparison, capacitance extraction and post-layout simulation.
- Nine deliberate faults: narrow metal, an opened signal route and altered gate
  length for each block. The expected stage must detect the physical defect;
  an unavailable tool or setup error does not count as successful detection.

CI retains the project inputs, process and tool provenance, decks, findings,
measurements and comparison reports. This qualifies those cases and that package,
not arbitrary designs, other PDKs, distributed resistance or fabrication signoff.

## Test plans and specifications

Save testbenches or ordinary analysis setups, then create a test plan. Choose the
tests, model corners and temperatures. A voltage sweep also needs a declared DC
supply target for every selected test. Plans support up to 200 cases; each job
gets an isolated input and the normal durable scheduler handles execution.

The matrix shows each requirement under each operating condition. Failures,
cancelled jobs, absent measurements and incomplete physical stages remain visible.
Double-click a condition to open its run and log. Physical results open the
physical verification view. Retry keeps the original saved inputs.

Select **Compare schematic and post-layout** for plans composed of saved
testbenches. The matrix then contains both sets of measurements plus the physical
stage results. Configure local Magic, Netgen and ngspice first.

Choose an earlier plan run as a baseline to see numeric changes. Deltas require
the same test identity, measurement definition, unit and operating condition.
Changed limits are a new requirement. CSV export includes conditions, values,
status, baseline, delta and the originating run identity.

## Team review

Dev15 adds [schematic and layout collaboration](SCHEMATIC_COLLABORATION.md), including
shared hierarchy, schematic comparison and comments on terminals, nets and ERC findings.

All collaboration tools remain inside **Tools → Collaboration**. Its new
**Team review** tab provides named immutable checkpoints, object comments,
resolved discussions, comparison views and revision-specific decisions. A new
design revision does not inherit an earlier approval.

Share a completed simulation or saved-testbench physical run with its checkpoint.
The server checks the input/result identities and stores portable settings.
Teammates can inspect the values and **Re-run saved input** with their local
simulators and matching locked PDK. Local executable paths are rebuilt locally;
the server does not independently attest to submitted simulation values.

Dev16 reviewers can comment, reply and record decisions without design editing.
Editors and the owner can also create checkpoints and share results; viewers can inspect them.
See [the current review guide](WORKFLOW_REVIEW_0.22.md) for discussion permissions. Comments
remain attached to their checkpoint even when an object is removed later. Use
the comparison view to inspect the earlier geometry. Request identities make
network retries idempotent. The dashboard scrolls on small displays.

The server currently bounds a workspace to 25 checkpoints / 64 MiB of checkpoint
projects, 500 comments and 16 shared results of at most 4 MiB each. Export evidence
and start a new workspace when these limits are reached. Update the server and
desktop client together to use the review API.

## Document services and recovery

`document.py` supplies change records shared by commit, undo and redo. Ordinary
shape moves copy the changed geometry and its ancestor lists, construct a sparse
undo patch, and refresh only the affected layout cache entries. Generated devices
and connected edits retain their constrained commands. General transactions
still use full isolated copies and validation.

`recovery_queue.py` coalesces rapid edits into one ordered writer. The UI says
**recovery pending** until a durable write completes. Validation, serialization
and filesystem synchronization happen in the worker; snapshot isolation is
created on the UI thread because legacy callers still own mutable metadata.
Save, project changes, folder changes and close fence outstanding writes. Failed
storage preserves the previous recovery file and exposes an explicit retry.

The native document bounds are 5,000 devices per master and 50,000 flattened
devices. The teaching solver retains its 500-device and matrix-size bounds;
larger circuits use ngspice. Both desktop CI targets execute a 1,001-device resistor
ladder and check the analytical midpoint voltage.

## Repeatable performance and acceptance evidence

Run `python scripts/benchmark_document.py --out build/document-benchmark` to
separate distinct geometry from repeated instances. One million distinct shapes
use four masters because the per-master limit remains 250,000 shapes. Measurements
on the development Linux host, with three timing samples per workload:

| Distinct stored shapes | Single-shape commit median | Undo median | Additional allocation during one edit |
| --- | ---: | ---: | ---: |
| 10,000 | 0.61 ms | 0.077 ms | 83 KB |
| 100,000 | 7.16 ms | 0.388 ms | 803 KB |
| 1,000,000 in four masters | 25.78 ms | 3.12 ms | 2.00 MB |

These are document-operation measurements, excluding painting, recovery and DRC.
Initial validation and copying of the million-shape project took about 14.9 s.
Repeated hierarchy with one stored shape is measured separately and is much
cheaper. There is no claim of interactive million-shape physical verification.

`scripts/benchmark_layout_pipeline.py` measures complete connected edits, paint,
the durable-recovery wait and declared-rule checks. On the same host its 10,000
shape run measured about 283 ms for the connected edit and 909 ms including paint,
recovery and checks. Snapshot copying and first-time connectivity construction
remain material costs.

The desktop acceptance gate is `tests/gui_professional_workflows.py`: actual
pointer gestures, previews, cancellation, undo, plan execution, baseline comparison
and reproduction of a shared simulation. `tests/gui_live_collaboration.py` exercises
three real desktop clients against HTTP, including object comments, checkpoints
and comparisons. `tests/gui_layout_stability.py` injects failed storage and then
requires a real durable recovery retry. All run in Windows/Linux CI.

Before calling a release commercially usable, observe designers independently
completing a parameter edit, layout update, failing-corner diagnosis and teammate
review. Record completion time, misclicks, recovery from errors and requests for
help. Automated acceptance does not substitute for that unperformed user study.
