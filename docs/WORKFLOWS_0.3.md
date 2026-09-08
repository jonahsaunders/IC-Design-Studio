# Working with IC Design Studio 0.3

The application remains a native desktop program. Dark mode and the slim US-style resistor, capacitor and voltage-source artwork are retained. New commands are also searchable through Ctrl+K.

## Parameters, symbols, buses and annotations

Use **Design → Schematic tools → Cell parameters**. Enter one `name = value` per line, such as `resistance = 10k`. A device value may reference it as `{resistance * 2}`. Expressions accept numbers, parameter names, addition, subtraction, multiplication, division and parentheses; they cannot execute Python. Hierarchical instances can override cell defaults through **Instance parameters**. Simulation resolves each instance in its own scope. Parameterized SPICE exports are flattened to preserve the resolved values.

**Edit active cell symbol** opens a native drawing pad with line, rectangle and ellipse tools. Drag to draw on the 5-unit grid. Use Place pin and the port selector to position each declared cell port. Save updates the symbol on every instance of that cell. Undo stroke and Clear artwork act within the editor; the project’s undo history records the committed symbol change. Cell ports are declared through the existing Edit cell ports command.

**Connect selection to bus** assigns one selected component pin to each signal of a range such as `data[3:0]`. Selection order determines bit order. This is an explicit collection of named scalar nets; it is not a full bus-wire/tap editor. **Add annotation** and **Manage annotations** create, edit and remove schematic notes.

**File → Export structural Verilog** emits the cell hierarchy, parameter references, pin connections and declared analog black boxes. This is a structural connectivity handoff. It does not translate analog devices into behavioral HDL or make an analog design digitally synthesizable.

## Simulation studies

Choose the base analysis in the Inspector’s Analysis tab. Open **Analysis → Parameter sweep / PVT / Monte Carlo**.

- A parameter sweep changes a numeric active-cell target, such as `R1.value`, `MN1.params.w` or `V1.source.high`, over a comma-separated list of values.
- PVT forms the Cartesian product of declared PDK corners, supply voltages and temperatures. Its target must be a DC voltage source such as `VDD.value`. Additional process corners must exist in the active PDK descriptor and its model-section mapping; the application does not invent foundry corners.
- Tolerance Monte Carlo uses a fixed random seed and a user-declared relative standard deviation. The desktop form varies one target with a normal distribution. The CLI supports multiple independent targets and normal or uniform distributions. A uniform distribution is parameterized by its standard deviation, not its half-width. Invalid sampled component values stop the job rather than being silently clipped. Foundry mismatch and correlated statistical models are not supplied.

Measurements include final sample, minimum, maximum, sample mean, sample RMS, peak-to-peak and the x coordinate of the largest-magnitude sample. The Studies tab shows each measurement and aggregate mean, extrema and sample standard deviation. CLI specifications can add lower/upper measurement limits for a pass fraction. The UI’s mean/RMS metrics are sample-based, not time-weighted integrals over adaptive time steps.

**Open selected waveform** loads the full result for a case. **Export study CSV** exports the case table. Each case retains its input snapshot, settings, result and hashes in the local run directory. Cancellation stops the worker and does not publish a partial aggregate. **Rerun saved study** reuses the last study specification with the current analysis and selected engine. Recent saved runs are restored when the same project is opened.

The built-in solver supports explicit resistor `tc1` and `tc2` coefficients about 27°C. MOS temperature sweeps and bound PDK device models require ngspice. A pulse source’s DC value is inactive; sweep `source.high` or `source.low` instead. **ngspice device noise** supplies an output net and independent voltage input source for the external engine. Its noise coverage depends on the model deck.

Examples:

```sh
python main.py --cli study examples/rc.icproj --spec examples/rc-sweep.json --output runs/sweep.json
python main.py --cli study examples/rc.icproj --spec examples/rc-monte-carlo.json --output runs/tolerance.json
```

## Physical cells and editing

**Design → Physical cells → Create reusable layout cell** creates a recipe-backed metal ring, interdigitated finger pattern or generic MOS geometry. MOS geometry uses the selected schematic MOS device. **Regenerate active layout cell** changes the saved recipe and replaces the cell’s generated shapes in one undoable transaction. Recipes are application-owned; these are not imported KLayout PCell code or qualified foundry generators.

**Place physical cell / array** stores an explicit physical instance with position, quarter-turn rotation, array dimensions and pitches. Physical hierarchy and arrays are written as actual GDSII/OASIS instances. Select visible instance geometry to move, rotate, duplicate or delete that instance; edit its source cell to change its contents.

**Common-centroid placement** creates a 2×2 A/B/B/A arrangement from two reusable unit cells. Its stored constraint checks instance-origin centroids during DRC. Equal electrical sizing, shape symmetry, dummies and interconnect matching remain the designer’s responsibility. This is not a general analog constraint solver.

**Routing and terminals → Route between coordinates** tries Manhattan routes with up to two bends and checks exact polygon clearance against other-net obstacles on the chosen layer. It respects the specified width and technology grid. It does not create vias or route across layers automatically. **Erase layout area** subtracts a rectangle from shapes on the active cell and chosen layer, preserving the remaining geometry and holes. Rectangle drawing provides additive paint; continuous paint strokes are not implemented.

## Physical checks and post-layout work

Open `examples/physical_rc.icproj` for a small, reproducible teaching fixture. Three conductor strips and four explicit physical terminal assignments represent an RC network’s connections. Its parasitic coefficients are illustrative, not calibrated foundry data.

**Assign physical terminal** links a schematic pin to a point on a conductor. The physical connectivity worker determines polygon contact on declared conductor/via layers. It reports missing or unlanded terminals, opens, shorts, labels inconsistent with terminal nets and labeled islands without a terminal connection. Testbench voltage/current sources do not require silicon footprints.

These checks compare **declared terminals and physical connectivity**. They do not recognize semiconductor devices from masks or compare extracted transistor dimensions. Full LVS requires a qualified device-extraction deck and an external engine. The existing Netgen command accepts separate schematic and extracted decks plus a setup file.

**Estimate ground capacitance** uses per-layer `cap_f_per_um2` and `edge_f_per_um` coefficients. It merges overlapping geometry and derives the net from connected physical terminals, including unlabeled conductors. **Simulate with estimated parasitics** adds those lumped ground capacitors to an immutable circuit snapshot and runs the selected simulator. It retains the extraction hash and marks the result stale after an edit. Compare a pre-layout AC/transient run with the subsequent estimate using Compare previous. The estimate excludes coupling capacitance and distributed resistance.

**Tools → Extract layout through Magic** runs the documented external flow on an installed Magic engine with a matching technology file. The LVS profile and full-RC profile use different commands. The RC sequence includes extresist and writes the exact extraction script, hashes, log and produced SPICE decks. This adapter’s command profiles have tests; Magic and foundry decks were not available for actual extraction qualification in this delivery.

**Simulate extracted SPICE testbench** runs an explicit SPICE deck using ngspice and shows returned node voltages. Add the appropriate sources, models and analysis directives to your extracted deck/testbench first. The exact top-level deck is snapshotted; included dependencies must be locked separately. The application does not automatically prove this external deck’s equivalence to the current schematic.

```sh
python main.py --cli check examples/physical_rc.icproj --kind connectivity
python main.py --cli parasitics examples/physical_rc.icproj --output runs/extraction.json
python main.py --cli post-layout examples/physical_rc.icproj --output runs/post-layout.json
python main.py --cli extract --executable /path/to/magic --gds design.gds --technology process.tech --top top --profile rc --output extraction-output
```

## PDK revisions and project folders

**Tools → Installed PDK revisions** installs a local package whose `package.json` declares an ID, revision, technology descriptor and SHA256 for every included asset. Installations are side by side. Activating an older installed revision is a rollback. Modified assets fail verification before activation/model loading. An existing revision cannot be replaced by different content under the same identity.

The example `examples/pdk-educational/package.json` demonstrates the format. A simulation binding declares includes, optional corner-to-library-section maps, device model names, SPICE prefixes, explicit pin order and optional `parameter_scale` factors for width/length. Scale factors allow a model expecting micrometres to receive correctly converted SI schematic dimensions. Model paths must belong to the locked package. Reproducible handoffs copy declared model assets and use relocatable deck/project paths. Package capability declarations are provider metadata, not application-issued foundry qualification.

No SKY130, GF180MCU or IHP process package is bundled or qualified. This installer accepts prepared local packages; it does not build open_pdks, fetch multi-gigabyte assets, compile OSDI models or resolve an arbitrary PDK dependency graph.

**File → Project folders** saves a readable project manifest, immutable content-addressed cell files and a dependency lock. The manifest is the atomic commit point: interrupted writes leave the previous complete snapshot readable. Old cell snapshots remain available on disk; automatic garbage collection is not provided. Opening a folder loads that snapshot into the editor. Use Save project folder again to publish a new folder snapshot; the ordinary Save command continues to write an `.icproj` file.

## Continued external edits

**File → Review imported layout changes** compares matching cell/layer geometry with XOR, requires matching units and known layers, and displays the proposed changes before applying them as an undoable transaction. Changed physical geometry is flattened and loses shape-level device/net metadata. Schematic devices and explicit terminal assignments are retained for rechecking. Text-label differences are reported separately and are not applied automatically. An edit to the active project invalidates an open import review.

**Import edited Xschem package** reads continued edits to a Studio-generated package with its `project.icproj` metadata. It resolves known symbol prototypes, component values, names, positions, quarter-turn rotations and connected pin nets. Newer exports lock symbol files; changed/missing symbols are rejected for explicit reconciliation. Opaque graphic records/properties are retained as metadata. Arbitrary external symbol libraries, mirrored symbols, independently edited pulse edge times and script execution are unsupported. This is a bounded package importer, not a universal Xschem round trip.

## Validation boundary

Read `TEST_REPORT.md` for executed tests and `RELEASE_STATUS.md` for the full outstanding requirements. Windows execution, signed installers/updates, managed WSL/remote workers, foundry DRC/LVS/extraction, million-shape GUI performance, accessibility certification and external-user pilots remain release gates.
