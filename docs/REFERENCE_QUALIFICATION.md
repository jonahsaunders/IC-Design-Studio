# Reference qualification

Generated from `examples/qualification.json`. Run `python scripts/update_qualification.py` after reviewing evidence changes.

**Archived qualification · Banba first schematic**

Initial optimization example; the saved startup overshoot requirement fails.

| Check | Status | Scope |
|---|---|---|
| Resistor search | Passed | 27 nominal-process simulations at three temperatures. |
| Startup overshoot | Failed | 2.719 V peak exceeds the saved 0.75 V limit. |
| Physical verification | Not run | Schematic example; no physical layout qualification. |

Archive results apply to the recorded source and tools. They do not qualify edits, packaged releases or fabrication signoff.

**Archived qualification · Banba second schematic**

Schematic simulation only. The archived nominal result is 600.616 mV at 44.40 microamps.

| Check | Status | Scope |
|---|---|---|
| Saved PVT checks | Passed | 20 corner/supply cases and startup checks; inspect the retained conditions. |
| Physical verification | Not run | Use the separate layout example for extracted evidence. |

Archive results apply to the recorded source and tools. They do not qualify edits, packaged releases or fabrication signoff.

**Archived qualification · Banba routed layout**

103 devices in an 852.1 by 566.5 micrometre editable core (0.482715 square millimetres). Full extracted qualification remains blocked.

| Check | Status | Scope |
|---|---|---|
| Native connectivity | Passed | 56 nets; saved matching and geometry checks are separately retained. |
| Unfilled core LVS | Passed | Pinned GF180 four-metal / MIM B deck; 103 devices. |
| Unfilled core density | Failed | 314 density findings; core geometry and antenna checks pass. |
| 600 micrometre fill DRC/LVS | Passed | 3.625 square millimetres. Includes the documented dummy-poly density-deck correction. |
| 550 micrometre fill DRC/LVS | Passed | 3.253175 square millimetres; 10.26% smaller than the retained 600 micrometre halo. Same dummy-poly correction; core masks unchanged. |
| Core capacitance-only PVT | Passed | 20 operating points and 60 startup transients; no distributed resistance. |
| Distributed RC | Blocked | Extractor output has incomplete device-terminal resistance graphs. |
| Fill coupling | Blocked | The retained Magic technology does not extract dummy-fill coupling. |
| Fabrication signoff | Not run | Process-owner review and a complete chip floorplan remain required. |

Archive results apply to the recorded source and tools. They do not qualify edits, packaged releases or fabrication signoff.
