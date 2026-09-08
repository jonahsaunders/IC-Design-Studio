# 0.13 capability ledger

| Area | Implemented | Boundary / follow-up |
|---|---|---|
| Familiar workspace | Existing editable Xschem/Virtuoso schematic and symbol profiles; Virtuoso/KLayout layout profiles; clearer active capture tools and compact controls | Inspired conventions, not vendor emulation or interoperability certification |
| Schematic selection | Tab/Alt-click overlap cycle, device/wire/label filters, labelled pin snap targets | Filters are session-local; Manhattan wire geometry retained |
| Schematic editing | Existing move/stretch/copy, repeated placement, bulk parameters, extraction; active-cell previews and spatial wire queries | 500 devices and 5,000 wires per cell; no bus-harness editor |
| Symbol editing | Existing vector tools/styles; dropdown terminal metadata, optional pins, initial fit, cached vector drawing | 1,000 primitives, ±500 coordinates; shared cell definitions |
| Interface update | Explicit rename/add/remove/order mapping, per-instance added connections, physical port assignment, saved-bench review, revision-bound Apply, one Undo | One cell interface per review; removals can leave intentional stubs/internal circuitry; rerun checks |
| Electrical policy | Project-stored severity/scope; hierarchical primitive checks, directions, scalar buses, optional terminals, physical-port findings | Not a complete analog rule engine, timing analysis or LVS |
| Cross-probing | Instance occurrence paths, root-net propagation, placement/terminal status, navigation to either view, placement assistance and contact-based guidance | Shared-cell editing; explicit terminal assignments; no arbitrary device recognition or automatic routed closure |
| Performance | Reproducible 500-device/2,000-wire, 1,000-primitive and 10,000-shape workloads; topology/hover/drawing caches with edit/undo invalidation | Synthetic offscreen host measurements; no raised capacity or production-size qualification |
| Xschem exchange | Existing declarative symbols and mirror-aware schematic package exchange; required-pin metadata retained | Package locks remain enforced; arbitrary scripts/OpenAccess are unsupported |
| Process verification | Existing analog/process flows; reviewed SKY130 port rename exercised through real DRC/LVS and pre/post-layout comparison | Bounded engineering recipes and capacitance extraction; no fabrication signoff |
| Layout breadth | Complete existing 0.11 editor and 0.10 analog workflows retained | See CAPABILITY_MATRIX_0.11.md; differential-pair layout, advanced constraints/routing and broader PCells remain future work |
| Distribution | Complete source, Linux x86_64 bundle, PDK locks, examples, current/historical evidence and continuation patch | Fresh-OS, graphics-session, experienced-user and Windows qualification not executed |

Exact test results and historical qualification boundaries are recorded in the
handoff's verification/RELEASE-RESULTS.json. Earlier capability matrices describe
their original releases; this ledger supersedes their interface/check limits.
