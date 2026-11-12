# Optional corner-safe IHP resistor guard routing

For `rsil`, `rppd` or `rhigh`, set W/L to **2/7 µm**, then choose:

- Resistor terminal access: **Metal1**
- Body guard routing: **Corner-safe Metal2 body (2/7 um only)**

The default remains the existing native Metal1 body. The new option is a
separate corrected routing recipe, not unchanged native PDK masks. It adds
0.25 µm² of Metal2 at the guard corners and redistributes the vertical via
rows, changing 56 guard vias to 54. The three device models, horizontal vias,
contacts, resistor geometry and all other masks are unchanged. The body
access is Metal2; both resistor terminals remain Metal1.

Only the three exact 2/7 µm templates are supported. Other dimensions,
multiplicity/bend options or simultaneous Metal2 resistor-terminal access
are rejected. Changing the option or dimensions marks a linked footprint
stale; use regeneration/ECO and check connections. Existing routes and top
port labels stay at their coordinates when regenerating, so changing body
access can require moving/reassigning the body port and reconnecting routes.

Templates preserve the authenticated local native experiment's source,
contract, model, mask and tool identities. Original native all-side 100%
corner DRC failures remain recorded separately. The corrected profile passed
42 rotated layouts and 105 fault controls before app integration; those are
geometric source results, not installed-app acceptance or full-family signoff.

Source GUI lifecycle and backend transfer tests are additional checks. The
original installed probe does not exercise this option. The separate probe below
is implemented, but an exact installed candidate must still run it successfully.

## Separate installed gate

`--ihp-guard-corner-acceptance` is the packaged Qt lifecycle producer. Its report
never grants installed acceptance. `scripts/verify_frozen_ihp_guard_corner.py`
requires an exact selected clean build, authenticates executable, shipped Python
backend, templates, package and managed runtime, independently reads all six
saved/streamed layouts and the 18 rejection/backward-compatibility controls plus
two historical projects, then launches 21 fresh managed native jobs. These are
six DRC/strict-LVS/extraction positives and 15 controls on the three unrotated
layouts: complete 54-cut body-via removal, body-contact removal, R1/R2 short,
reference width and reference model. The R1/R2 short must fail with the actual
collapsed interface; open controls require successful extraction and floating B,
not an arbitrary process failure. Every native job retains raw inputs/outputs.

This separate 6/15 installed matrix does not replace the original 60/165 IHP
gate or claim to reproduce all 42/105 local geometric experiment cases. Linux
and Windows workflows invoke it additionally with a 900-second overall deadline
and retain separate evidence directories. The original gates/deadlines remain
unchanged. No installed run has been performed for this new option locally;
only source GUI/readback and the separately documented native prototype runs
are established until an exact candidate completes the hosted gates.
