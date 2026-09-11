"""Reviewed command locations. One submenu level at most; retain QAction identities."""

GROUPS = {
 'File': ['New project…','Open project…','Save','Save as…','Close project','Projects…','Quit'],
 'File/Recovery': ['Retry recovery save','Choose recovery folder…'],
 'File/Import': ['Import GDSII / OASIS…','Import edited Xschem package…','Import Magic layout…','Import SPICE circuit…','Import SPICE component…','Review imported layout changes…','Open project folder…'],
 'File/Export': ['Export reproducible handoff…','Export SPICE deck…','Export GDSII / OASIS…','Export Xschem package…','Export waveform CSV…','Save canvas image…','Export structural Verilog…','Export saved SPICE testbench…','Save project folder…'],
 'File/Examples': ['New PDK inverter…','New PDK ring oscillator…','New PDK current mirror','New PDK differential pair','New PDK amplifier'],
 'Edit': ['Undo','Redo','Duplicate','Delete selection','Rotate clockwise','Rotate counterclockwise','Command palette…'],
 'Design': ['Add cell…','Instantiate cell…','Set active cell as top','Edit cell ports…','Cell parameters…','Rename active cell…','Make cell from selection…','Library / cell / view browser…','Project settings…'],
 'Design/Manage project': ['Rename project…','Duplicate project…','Delete project…','Delete active cell…'],
 'Schematic': ['Place component…','Place wire','Place net label…','Place ground','Move','Stretch','Copy','Mirror','Bulk parameters…','Component properties…','Instance parameters…','Enter schematic','Return to parent','Check and Save'],
 'Schematic/Symbols': ['New custom symbol…','Edit selected symbol…','Edit active cell symbol…','Enter symbol','Generate / edit active symbol','Replace selected PDK device…'],
 'Schematic/Annotations': ['Manage annotations…','Add annotation…','Connect selection to bus…'],
 'Schematic/Selection filter': ['Devices','Wires','Labels'],
 'Layout': ['Rectangle','Polygon','Path','Move by reference','Copy by reference','Stretch edge','Edit vertex','Rotate layout clockwise','Rotate layout counterclockwise','Layout properties…','Align layout selection…','Layout drawing settings…','Repeat last layout command'],
 'Layout/Geometry': ['Union','Subtract from first','Intersection','Exclusive OR','Erase layout area…','Transform layout selection…','Size selected geometry…','Chop selected geometry…','Edit path vertices…'],
 'Layout/Cells and arrays': ['Create reusable layout cell…','Regenerate active layout cell…','Place physical cell / array…','Create layout array…','Place linked physical instance…','Enter selected physical cell','Return to parent cell','Edit selected cell in context','Return from context','Place physical cell…','Make selected instance a cell variant…','Resolve selected array','Flatten selected physical instances'],
 'Layout/Generate': ['Common-centroid placement…','Generate generic MOS geometry…','Generate metal guard ring…','Generate PDK device layout…','Generate inverter layout…','Generate current mirror layout…','Generate analog reference layout…'],
 'Route': ['Place via','Place via…','Route linked terminals…','Route between coordinates…','Assign physical terminal…','Assign cell layout port…','Stretch path segment…','Stretch path with mouse','Cut wire','Rejoin two wires','Toggle junction at pointer'],
 'Simulate': ['Run analysis','Cancel job','Save / edit testbench…','Run saved testbench','Saved testbenches','Simulate extracted SPICE testbench…','ngspice device noise…','Simulate with estimated parasitics','Simulation runtime…'],
 'Simulate/Studies': ['Parameter sweep / PVT / Monte Carlo…','Rerun saved study','Configure saved-bench characterization…','Run saved-bench characterization'],
 'Verify': ['Electrical rule check','Electrical check rules…','Geometry DRC (generic rules)','Device mapping audit','Inspect whole net','Schematic / layout cross-probe…','Check linked layout and show connections','Physical terminal connectivity','Physical workflow'],
 'Verify/Physical verification': ['Verify custom inverter through silicon','Verify saved testbench layout','Compare netlists with Netgen…','Create PDK reference circuit…','Extract layout through Magic…','Estimate ground capacitance'],
 'Tools': ['Engine diagnostics and paths…','Layout keyboard profile…','Schematic command profile…','Convert GDS through Magic…'],
 'Tools/Technology': ['Import technology descriptor…','Technology and qualification status','Installed PDK revisions…','PDK manager…','Relink project PDK folder…','Migrate PDK revision…'],
 'View': ['Fit design','Fit layout','Ruler','Toggle light / dark'],
 'Window': ['Project','Inspector','Results','Focus canvas','Reset workspace','Save named workspace…','Restore named workspace…'],
 'Help': ['Searchable help…','About and release status','Keyboard shortcuts and wiring','Compatibility matrix'],
}

# These entries invoke exactly the same operation as the retained primary entry.
ALIASES = {'Check electrical rules':'Electrical rule check',
           'Cross-probe hierarchy…':'Schematic / layout cross-probe…'}


def title(action):
    return action.text().replace('&', '').split('\t')[0]
