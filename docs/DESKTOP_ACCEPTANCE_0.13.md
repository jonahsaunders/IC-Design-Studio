# Fresh-desktop and experienced-user acceptance

Status: **not executed** in the 0.13 build environment. Automated Qt/offscreen
tests and clean-directory extraction do not establish fresh-machine usability.
Use the companion JSON template for actual sessions; leave unrun tasks unrun.

## Desktop gate

Use a fresh Linux x86_64 environment matching LINUX_SETUP.md, extract the complete
bundle and launch from a directory containing spaces. Record distribution,
glibc, X11/Wayland, graphics adapter/driver, monitor resolution and scale. Test
100% and 200% scaling with the actual display server. Run the packaged
`--release-test /absolute/path/to/evidence` without forcing offscreen rendering.
Configure real engine paths and a supplied PDK; repeat a saved simulation and
physical flow. Keep the report, screenshots, launch errors and tool versions.

The desktop gate needs clean launch, readable dialogs, working text input and
shortcuts, correct pointer alignment at each scale, background worker completion,
project reopening, and no data loss. A graphics/loader failure is a failure to
investigate, not a reason to relabel an offscreen result as desktop acceptance.

## User sessions

Recruit at least one regular Xschem user and one experienced analog schematic designer. Record
experience and the chosen preset. Give each a copy of the amplifier example and
these tasks, without a live walkthrough. Measure completion time, wrong actions,
recoveries and requested help. Ask what they expected where behavior differed.

1. Find a resistor in the browser and place/rotate it; cancel another placement.
2. Wire a connection, flip a bend, undo a bend and finish on an exact pin.
3. Select an overlapping wire, then stretch a device and undo it.
4. Enter the amplifier schematic, edit a parameter and return to its fixture.
5. Open its symbol; find terminal order, direction, required status and artwork.
6. Rename `input`, add a sense terminal and review the affected views/bench.
7. Cancel once, reopen the review, make an explicit mapping and Apply; Undo once.
8. Run electrical checks, navigate a finding, fix it, and change one rule severity.
9. Follow a net into the child using cross-probe; inspect a missing placement or
   physical port and the connection-guidance controls.
10. Simulate the saved amplifier bench, save/reopen, and verify the connections.

Acceptance requires all tasks to be completable, no unintended electrical
changes, no lost work and no blocking clipping. Track assistance/time as baseline
measurements rather than inventing a performance threshold after seeing results.
Triage repeated command-discovery failures for the next GUI revision. Publish
the actual session evidence before claiming familiarity has been validated.
