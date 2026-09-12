# Inductor creator

Open **Tools → Inductor creator…** on `experimental` (0.22.0.dev22 or later).
The tool creates an editable square spiral, a return conductor on the other
layer of a mapped via stack, via arrays at both ends of that return, and P/N
terminal pads. The preview shows both conductor layers and the terminal names.

## Create and link

1. Choose **New schematic inductor**, or select an existing standard schematic
   `L` in the **Link to** list. Imported native subcircuits need their own
   supported physical implementation.
2. Set turns, trace width, spacing, inner opening and lead length. Dimensions
   and origin coordinates are in µm. Select the via stack, spiral metal, via
   rows/columns, rotation and mirroring. Scroll the form on smaller screens.
3. Review the preview, outer winding dimensions, via count and estimated DC L.
   Invalid geometry disables creation and explains the problem.
4. Choose **Create inductor**. The app switches to layout and selects the new
   footprint. Creation is one undoable edit, including the linked schematic L.

For a new L, give it a unique name beginning with L and two distinct net names.
The tool creates attached schematic labels and sets its value to the estimate.
For an existing L, its schematic value stays unchanged unless **Set schematic
L to the estimate** is checked. The tool does not solve dimensions from a target
inductance. It requires a declared via mapping and does not invent PDK data.

## Move and regenerate

Select the complete footprint to move it with connected editing. Select one of
its shapes and reopen **Tools → Inductor creator…** to edit its saved recipe.
Selecting the schematic L and choosing **Place / regenerate…** also opens the
creator. The selected device appears in the dialog automatically.

Regeneration preserves the footprint's translated origin and keeps shape and
terminal IDs when their roles remain. Changing dimensions can move terminals;
the tool rejects changes that would detach an existing route or cell port.
Keep those terminal positions or explicitly detach the affected route first.
It also rejects locked layers and a design that changed after previewing.
Undo manual edits to generated winding shapes before regenerating them.

Recipes survive project save/reopen. GDSII and OASIS export retain the complete
winding, return conductor and via geometry. The normal matching export sidecar
also preserves the project's generator metadata.

## Estimate and verification scope

The estimate uses equation (2) and the square coefficients in Table II of
[Mohan et al., *Simple Accurate Expressions for Planar Spiral Inductances*,
IEEE JSSC 34(10), 1999](https://web.stanford.edu/~boyd/papers/pdf/inductance_expressions.pdf)
([DOI](https://doi.org/10.1109/4.792620)). With dimensions in metres:

\[
L=\frac{\mu_0 n^2 d_{avg}\,1.27}{2}
\left[\ln\left(\frac{2.07}{\rho}\right)+0.18\rho+0.13\rho^2\right],
\quad d_{avg}=\frac{d_{out}+d_{in}}2,
\quad \rho=\frac{d_{out}-d_{in}}{d_{out}+d_{in}}.
\]

Here `d_out = d_in + 2*n*width + 2*(n-1)*spacing`. The outer dimension excludes
terminal leads. The default 3 turns, 10 µm width, 3 µm spacing and 80 µm opening
give a 152 µm outer winding and an estimate of about 1.638 nH.

This is a DC winding estimate. It excludes lead/underpass contributions,
substrate loss, frequency-dependent resistance, Q and self-resonance. No
process-calibrated RF accuracy is claimed. Use the actual process rule deck
and a qualified EM/device extraction model before fabrication or RF signoff.
Octagons, differential coils, transformers and automatic target-L sizing are
outside this version.

The app recognizes the intact saved recipe as a two-terminal inductor for
terminal-connectivity checks. Its continuous winding is not counted as an
ordinary wire between P and N. Full metal remains in drawing, DRC and export.
External shorts remain detectable. Contacts to the winding outside its terminal
pads produce `INDUCTOR.TAP`; changed or incomplete recipes produce
`INDUCTOR.STALE` and lose that device-boundary treatment. This is explicit
generator recognition, not foundry LVS. Interconnect capacitance and distributed
RC estimators refuse cells containing these inductors because they do not
characterize the winding's device parasitics.

## Reproduce acceptance

```sh
python -m unittest discover -s tests -p test_inductor.py -v
QT_QPA_PLATFORM=offscreen python tests/gui_inductor.py --out build/inductor-evidence
```

The same desktop probe runs through experimental acceptance and the frozen
release probe. It covers the actual Tools action, compact preview, creation,
undo/redo, saved regeneration, estimate opt-in, locks and stale previews.
Windows native DPI and Linux X11 package jobs retain their own screenshots and
reports. Core coverage also checks physical continuity, short/tap detection,
transformed hierarchy, exported metal, via enclosure and incremental/full
finding agreement.
