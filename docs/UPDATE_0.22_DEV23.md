# Experimental dev23: inductor design and characterization

The creator now supports square, rectangular, hexagonal, octagonal and circular
spirals. Existing dev22 square recipes retain their geometry and recognition.
Rectangles have separate X/Y openings and a thin-strip partial-inductance model;
regular spirals use their own Mohan current-sheet coefficients.

**Target L** searches a bounded range of turns, trace widths, spacings and
on-grid openings. Candidates show inductance, error, footprint and turns, and
state when none meets tolerance. Selecting one runs placement checks before
creation. Rectangle search retains the selected opening aspect ratio.

Preview generation and design validation run in bounded background workers.
Obsolete results cannot enable creation; invalid input keeps the previous
geometry visible. Field errors expose explicit suggested adjustments. Preview
annotations show winding dimensions, layers and ports. Saved recipes still
support atomic creation, regeneration and undo/redo.

Declared conductor sheet resistance and per-cut via resistance enable DC R
estimates. **Simulate with estimated series R** adds an approximate resistor only
to simulation/export copies, shared by the teaching solver and SPICE writer.
Existing schematic inductance is preserved unless the estimate checkbox is
selected. Changed coefficients, geometry or inductance require regeneration.

**EM results** exports GDS geometry, context, P/N ports, a recipe fingerprint
and explicitly supplied physical stackup. It imports differential impedance
JSON or supported Touchstone 1.x S-parameters, displays L(f), R(f), Q(f) and a
bracketed SRF, and retains evidence through project save/reopen. Changes to
geometry, surrounding metal or materials make characterization stale.

This is an exchange workflow, not an included EM solver. DC estimates and
synthetic acceptance fixtures do not qualify RF or fabrication performance.
Differential/center-tapped configurations and transformers remain separate
electrical topologies; this update adds the five two-terminal shapes.

See the [creator guide](INDUCTOR_CREATOR.md) for formats, controls and verification
commands, and [release status](RELEASE_STATUS.md) for local and hosted evidence.
