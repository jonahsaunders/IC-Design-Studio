# Layout capability matrix — 0.11.0

The product goal is familiar everyday interaction plus a broad layout toolset.
Full coverage of commercial Virtuoso Layout Suite tiers and KLayout is a
multi-release goal. This matrix describes IC Design Studio, not certification
of compatibility with either product. Vendor assets and proprietary APIs are
not bundled. “Bounded” means available only within the stated contract.

| Area | Status in 0.11 | Remaining work |
|---|---|---|
| Native desktop, dark/light views, docking | Implemented; named workspaces and linked views | Real desktop-driver/platform qualification |
| Library / cell / view navigation | Current project browser, PDK library link, existing hierarchy tree | Multi-library workspaces, cross-project references, OpenAccess interoperability |
| Keyboard workflow | Three editable profiles, command search, repeat, cancel, finish | Broader customizable mouse gestures and vendor-trained user acceptance |
| Layer palette | Independent V/S/L, colors/patterns, search, per-process revision preferences | Layer groups, richer purpose definitions, complete display-file import/export |
| Selection | Object filters, overlap cycling, crossing/inside marquee | Rich queries, arbitrary hierarchy-path selections and advanced partial selection |
| Drawing and properties | Rectangle, polygon, path, rulers; contextual width/net; bulk local-shape properties | Arc/curve tools, richer path styles and specialized mask primitives |
| Geometry processing | Existing Booleans/transforms/alignment; new size/chop, edge/vertex editing | Hole-handle editing, arbitrary-angle edge constraints and broader processing recipes |
| Placement | Linked or geometry-only physical cells; cursor preview and rotation | General constraint-driven placement and automated packing |
| Hierarchy editing | Shared-cell context, breadcrumbs, independent variants | Direct array-element context and full occurrence-specific editing |
| Arrays and flattening | Geometry arrays can resolve; geometry-only instances can flatten | Electrical flattening with complete schematic/net/port migration |
| Routing | Manual paths, net assignment, snapping, process-specific automatic via on layer transition | Obstacle-aware routing, shove, bus/differential pairs, length matching and rerouting |
| Connectivity | Explicit terminals/ports, net highlighting, open guides, local connected-layout checks | Continuous extraction, richer schematic-driven routing and automatic connectivity repair |
| Constraints and analog layout | Existing 1:1 mirror footprint/orientation/alignment checks | General symmetry, matching, common-centroid, guard-ring and constraint management |
| Parametric devices | Existing qualified SKY130 recipes and bounded GF180 3.3 V MOS/inverter generation | Extensible PCell runtime, broader devices, GF180 multifinger/voltage families, IHP geometry |
| Physical verification | Actual full Magic DRC and Netgen LVS; exact findings, filtering and stale-result gates | Broad engine/deck adapters, incremental interactive DRC and enterprise verification workflows |
| Extraction / simulation | Existing capacitance extraction, ngspice, saved benches, pre/post comparison | Distributed resistance, RF/EM extraction and statistical mismatch qualification |
| GDS / OASIS | Existing KLayout-backed import/export and hierarchy review | Full format fidelity qualification, broader file ecosystem and large database streaming |
| Scripting / automation | Existing Python SDK, plugin/CLI surfaces | Stable comprehensive editor API, macro IDE, scripting debugger and KLayout macro compatibility |
| Collaboration / data management | Local project identity, history, save/reopen and handoff | Shared libraries, multi-user editing, design revision server and permissions |
| Scale / portability | Selection-time hierarchy cache; measured synthetic benchmark; packaged Linux probes | Production-size memory/render benchmarks, fresh Linux desktop and Windows release qualification |

## Acceptance priorities for subsequent releases

1. Qualify the shipped Linux app on a fresh machine and with practicing layout
   engineers. Measure completion of selection, routing, hierarchy, property and
   verification tasks and correct the observed friction.
2. Introduce a saved constraint model with explicit units, scope and violations.
   Deliver a complete differential-pair slice with matching/symmetry placement,
   contacts, routes, undo, full DRC/LVS and a saved electrical fixture.
3. Extend the router with obstacle and spacing awareness and tested via/width
   rules. Add continuous connectivity and clear unresolved-constraint reporting.
4. Broaden technology/PCell support only when exact geometry contracts and
   independent process evidence exist. Retain immutable PDK asset revisions.
5. Expand database performance and interoperability, then stabilize the public
   editor scripting API with versioned examples and failure contracts.

Official reference families used to organize the roadmap:

- Cadence Virtuoso Layout Suite: https://www.cadence.com/en_US/home/resources/datasheets/virtuoso-layout-suite-ds.html
- KLayout advanced editing: https://www.klayout.de/doc/manual/editor_advanced.html
- KLayout programming: https://www.klayout.de/doc/programming/introduction.html

These references establish the breadth of the target. They do not imply that
IC Design Studio implements each documented feature or accepts proprietary
Cadence databases, SKILL programs or all KLayout macros.
