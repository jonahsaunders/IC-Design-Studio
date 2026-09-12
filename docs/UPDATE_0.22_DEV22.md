# Experimental dev22: inductor creator

**Tools → Inductor creator…** now creates square spiral inductors with a live
layout preview. Controls include turns, trace width and spacing, inner opening,
lead length, mapped metal/via stack, via arrays, origin, rotation and mirroring.

Create a linked schematic L with named P/N terminals or use an existing standard
L. New devices use the estimated DC inductance; existing values change only
when explicitly requested. Dimensions and device links are saved in the project.
Reopen a selected footprint to regenerate it with stable shape/terminal IDs,
or use the placement checklist. Creation and regeneration support undo/redo.

The tool checks grid, width, spacing, via fit/enclosure, collisions, layer locks
and stale previews. Regeneration protects attached terminal routes and ports.
Intact saved windings have explicit two-terminal connectivity treatment;
unintended winding contacts and stale geometry remain findings. Drawing, DRC
and GDSII/OASIS export keep the full winding geometry.

The Mohan current-sheet result is an **estimated DC inductance**, not a
calibrated RF model. Lead/underpass contributions, Q, substrate losses and
self-resonance are outside its scope. Use process DRC and qualified EM/device
extraction before fabrication. Interconnect RC estimators reject these windings.

See the [creator guide](INDUCTOR_CREATOR.md) for controls, regeneration behavior,
formula reference and reproducible tests. The desktop probe runs from source
and within installed/frozen packages, including the existing native DPI gates.
The experimental draft workflow waits for desktop, physical and interoperability
checks on its exact commit. This update does not promote experimental to main.
