# IHP catalog capacitor references for physical verification

A freshly placed standard IHP `cap_cmim` now supplies the physical reference
required by the selected checker. Simulation export remains unchanged. The
previous application emitted an X instance with the simulation-only `mm_ok`
selector for both routes: the same complete 7 × 7 µm layout passed geometry
checks but failed LVS through both Magic and public KLayout.

The conversion follows the locked symbol and model, validates the catalog's
ordered `c0/c1` terminals, and records the source identities with each checked
reference. Magic retains X and omits the literal Boolean statistical selector.
The public KLayout route uses C and the pinned reader's per-unit `A=w*l` and
`P=2*(w+l)` definitions, keeping multiplicity separate. Dimensions come from the
schematic reference, never from the extracted result. Native comparison rules
and tolerances are unchanged.

Requested catalog LVS export uses the physical C view. An already-C reference
must use the public IHP KLayout checker; selecting Magic returns an actionable
error. Existing imported explicit LVS tokens remain supported. The projection
rejects changed sources, unknown or duplicated properties, unresolved
expressions, invalid dimensions, contradictory supplied area/perimeter and
projected C-instance name collisions within a subcircuit. A valid repeated projection
preserves its text and still records the checked-source receipt.

## Source acceptance

The unchanged published source reproduces both native failures. The repaired
source passes the ordinary catalog-to-job path with the default device through
both extractors, the rotated default through KLayout, and all six retained
complete maximum-area boundary layouts. The seven selected zero-finding contexts pass; the two oversized
layouts fail exactly MIM.g while strict LVS passes. The original simulation
reference remains byte-identical, and attaching a fresh catalog device changes
no physical mask.

Four meaningful physical faults remain rejected: incorrect width produces a
completed native property mismatch, reversed electrodes fail top-level pin
matching, missing contacts lose the actual top port, and a short merges the
physical electrodes. Three malformed-reference controls fail before native
execution. The actual Linux source desktop displays the matching current result and
public MIM.g execution. The separate [boundary contract](IHP_MIM_G_BOUNDARY.md)
retains its own evidence and package scope.

Independent raw-result review and restored source/baseline retention pass.
Both actual Windows managed source routes also pass, with all 203 returned
native artifacts independently verified. The original setup receipt remains
unchanged and correctly reports a changed backend: this explicitly selected
source-runtime reuse does not establish ordinary setup readiness. The
[acceptance record](validation/ihp-cmim-catalog-reference-2026-11-02.json) pins
the sources, results, failed attempts and recoverable archives. It does not establish installed
acceptance, a continuous geometry/electrical envelope, physical fractional
multiplicity, statistical calibration, other capacitor families, or complete
family qualification. The new [installed acceptance gate](IHP_CMIM_INSTALLED_ACCEPTANCE.md)
requires the frozen GUI and both native routes on each supported host; its
implementation does not establish an installed pass. The remaining
[device requirements](IHP_CMIM_REQUIREMENTS.md) and chunk 7 gate are unchanged.
