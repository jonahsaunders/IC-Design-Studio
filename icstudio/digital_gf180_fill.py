"""Captured GF180 C/D standard-cell block fill and post-fill typical extraction.

The opt-in recipe is bounded to 9-track, 5-metal blocks. Geometry, device LVS,
equivalence and timing remain explicit acceptance checks. Chip/scribe fill,
additional RC corners and field calibration require separate qualification.
"""
import json
from pathlib import Path
import re
import shutil

from .model import atomic_write, file_digest
from .digital_fill_spef import require

RECIPE = 'gf180-9t-5lm-block-density-v1'
SCOPE = ('Standard-cell block fill; typical interconnect with quasistatic floating M1. '
         'Run full layout rules, device connectivity, equivalence and timing on this result. '
         'Chip/scribe boundaries, other interconnect corners and field accuracy are not qualified.')


def implementation_options(r, settings):
    if not settings.get('gf180_fill'):
        return []
    from .digital_recipes import validate, GF180_RECIPES, PATCHES
    validate(r.platform)
    require(r.platform.get('name') in GF180_RECIPES and
            r.platform.get('orfs', {}).get('geometry_recipe') == GF180_RECIPES[r.platform['name']][0],
            'GF180 block fill requires the captured C/D 9-track 5-metal geometry recipe.')
    require(not r.platform.get('extraction') and not r.config.get('macros'),
            'GF180 block fill currently supports typical interconnect and standard cells only.')
    require(not settings.get('pdn_tcl', '').strip() and not settings.get('macro_placements'),
            'GF180 block fill requires its captured power grid and standard-cell-only placement.')
    directory = r.root/'platform'/r.platform.get('directory', '.')
    source = directory/PATCHES[0]['path']
    require(file_digest(source) in (PATCHES[0]['source_sha256'], PATCHES[0]['result_sha256']),
            'GF180 fill power-grid source changed.')
    text = source.read_text().split('define_pdn_grid')[0]
    text += 'define_pdn_grid -name {block} -voltage_domains {CORE} -pins {Metal5}\n'
    text += 'add_pdn_stripe -grid {block} -layer {Metal1} -width {0.900} -pitch {5.040} -offset {0} -followpins\n'
    for layer in ('Metal2', 'Metal3', 'Metal4', 'Metal5'):
        dimensions = ('-width {22.400} -pitch {89.600} -offset {22.400}' if layer == 'Metal2' else
                      '-width {3.920} -pitch {13.440} -offset {6.720}' if layer == 'Metal4' else
                      '-width {3.360} -pitch {13.440} -offset {6.720}')
        text += 'add_pdn_stripe -grid {block} -layer {'+layer+'} '+dimensions+'\n'
    for lower, upper in zip(('Metal1', 'Metal2', 'Metal3', 'Metal4'), ('Metal2', 'Metal3', 'Metal4', 'Metal5')):
        text += 'add_pdn_connect -grid {block} -layers {'+lower+' '+upper+'}'+(' -max_rows {1}' if lower == 'Metal1' else '')+'\n'
    path = r.root/'fill_pdn.tcl'; atomic_write(path, text); r.add_artifact('fill_pdn', path)
    cells = ['gf180mcu_fd_sc_mcu9t5v0__fillcap_'+str(n) for n in (64, 32, 16, 8, 4)]
    cells += ['gf180mcu_fd_sc_mcu9t5v0__fill_'+str(n) for n in (2, 1)]
    r.save_json('fill_recipe', dict(schema=1, recipe=RECIPE, scope=SCOPE,
        settings=settings, platform_fingerprint=r.platform['fingerprint'],
        power_grid=r.artifacts['fill_pdn'], filler_cells=cells), 'fill_recipe.json')
    return ['PDN_TCL='+str(path), 'FILL_CELLS='+' '.join(cells)]


def write_fill(source, target, top_name, settings):
    import klayout.db as k
    layout = k.Layout(); layout.read(str(source)); tops = list(layout.top_cells())
    require(layout.dbu == .001 and len(tops) == 1 and tops[0].name == top_name,
            'GF180 fill requires the captured unique top and 1 nm layout grid.')
    top = tops[0]
    def box(values):
        nm = [round(v*1000) for v in values]
        require(all(abs(v*1000-n) < 1e-6 for v, n in zip(values, nm)), 'Fill bounds must use the 1 nm grid.')
        return k.Box(*nm)
    bounds = box(settings['die_area']); core = box(settings['core_area'])
    require(bounds.width()*bounds.height() <= 1_000_000_000_000, 'GF180 block fill is limited to 1 mm².')
    def masks(ly):
        cell = ly.top_cell()
        return {(ly.get_info(i).layer, ly.get_info(i).datatype): k.Region(cell.begin_shapes_rec(i)).merged()
                for i in ly.layer_indexes()}
    before = masks(layout); empty = k.Region()
    require(all(before.get((n, 4), empty).is_empty() for n in (22, 30, 34, 36, 42, 46, 81)),
            'This fill recipe requires an unfilled input layout.')
    require(all(before.get(p, empty).is_empty() for p in ((11, 17), (86, 17))),
            'Unsupported memory geometry requires a separate fill recipe.')
    require(not top.bbox().empty() and (k.Region(top.bbox())-k.Region(bounds)).is_empty(),
            'Written layout extends outside the captured die area.')
    blocked = k.Region(core.enlarged(3000))
    obstacles = [((34, 0), 2000), ((30, 0), 1000), ((36, 0), 1000)]
    obstacles += [(p, 6000) for p in ((75, 0), (220, 0), (96, 1), (152, 5), (122, 5), (173, 5))]
    for pair, distance in obstacles: blocked += before.get(pair, empty).sized(distance)
    blocked.merge(); candidates = k.Region()
    for iy, y in enumerate(range(bounds.bottom+1600, bounds.top-4100, 3200)):
        for ix, x in enumerate(range(bounds.left+1600, bounds.right-4100, 3200)):
            xx = x+(iy % 2)*500; yy = y+(ix % 2)*500
            candidates.insert(k.Box(xx, yy, xx+2000, yy+2000))
    selected = candidates.not_interacting(blocked)
    require(not selected.is_empty() and selected.count() <= 100000 and selected.space_check(980).is_empty(),
            'No bounded, correctly spaced perimeter fill could be generated.')
    require((selected-k.Region(bounds.enlarged(-1600))).is_empty(), 'Fill extends beyond its captured boundary.')
    for pair, distance in obstacles:
        other = before.get(pair, empty)
        require((selected & other).is_empty() and selected.separation_check(other, distance).is_empty(),
                'Generated fill violates a required circuit or marker clearance.')
    top.shapes(layout.layer(34, 4)).insert(selected); top.shapes(layout.layer(63, 0)).insert(bounds)
    options = k.SaveLayoutOptions(); options.gds2_write_timestamps = False; layout.write(str(target), options)
    reread = k.Layout(); reread.read(str(target)); after = masks(reread)
    require(reread.top_cell().bbox() == bounds, 'Written filled layout changed its extent.')
    for pair in before.keys() | after.keys():
        if pair not in ((34, 4), (63, 0)):
            require((before.get(pair, empty) ^ after.get(pair, empty)).is_empty(), 'Fill changed a circuit mask.')
    require((after[(34, 4)] ^ selected).is_empty(), 'Written fill differs from its checked geometry.')
    return sorted([p.bbox().left, p.bbox().bottom, p.bbox().right, p.bbox().top] for p in selected.each())


def execute(r, settings):
    if not settings.get('gf180_fill'):
        return
    require('fill_recipe' in r.artifacts, 'Fill implementation recipe was not captured.')
    source_keys = ('gds', 'spef', 'checkpoint', 'def', 'netlist', 'lef')
    originals = {key: dict(r.artifacts[key]) for key in source_keys}
    folder = r.root/'fill'; folder.mkdir()
    boxes = write_fill(r.root/originals['gds']['path'], folder/'filled.gds', r.config['top'], settings)
    kvalue = {'gf180': '9', 'gf180d': '11'}[r.platform['name']]
    rules_name = r.platform.get('directory', '.')+'/openROAD/rcx/gf180mcu_1p5m_1tm_'+kvalue+'k_sp_smim_OPTB_typ.rules'
    lock = next((f for f in r.platform['files'] if f['path'] == rules_name), None)
    rules = r.root/'platform'/rules_name
    require(lock is not None and file_digest(rules) == lock['sha256'], 'Matching captured GF180 extraction rules are missing.')
    request = dict(source=str(r.root/originals['checkpoint']['path']), directory=str(folder),
                   rules=str(rules), boxes=boxes, die_nm=[round(v*1000) for v in settings['die_area']])
    atomic_write(folder/'request.json', json.dumps(request, indent=2)+'\n')
    shutil.copyfile(Path(__file__).with_name('digital_fill_odb.py'), folder/'extract.py')
    r.command([r.tools['openroad'], '-no_init', '-exit', '-python', str(folder/'extract.py')],
              'Extracting the filled GF180 layout', cwd=folder, fraction=.96)
    shapes = json.loads((folder/'represented.json').read_text())
    require([row['box_nm'] for row in shapes['added']] == boxes and
            shapes['total_nets']-shapes['original_nets'] == len(boxes), 'Native extraction did not represent every fill square.')
    before_def = (folder/'before.def').read_text(); after_def = (folder/'represented.def').read_text()
    records = re.findall(r'^\s*- ICSTUDIO_FLOAT_\d+\b.*?;\n', after_def, re.M | re.S)
    require(len(records) == len(boxes), 'Native database lost floating fill nets.')
    for record in records: after_def = after_def.replace(record, '', 1)
    normalize = lambda text: re.sub(r'^NETS \d+ ;$', 'NETS COUNT ;', text, flags=re.M)
    require(normalize(before_def) == normalize(after_def), 'Fill representation changed original placement or wires.')
    from .digital_fill_spef import reduce
    reduction = reduce(folder/'parasitics.spef', folder/'timing.spef', [row['net'] for row in shapes['added']])
    atomic_write(folder/'reduction.json', json.dumps(reduction, indent=2, allow_nan=False)+'\n')
    for key, record in originals.items():
        require(file_digest(r.root/record['path']) == record['sha256'], 'A fill input changed during extraction.')
        r.artifacts['fill_original_'+key] = record
    for name in ('request.json', 'extract.py', 'represented.json', 'before.def', 'represented.def',
                 'represented.odb', 'parasitics.spef', 'reduction.json'):
        r.add_artifact('fill_'+name.replace('.', '_'), folder/name)
    r.add_artifact('gds', folder/'filled.gds'); r.add_artifact('spef', folder/'timing.spef')
    r.add_artifact('lef', folder/'filled.lef')
    r.save_json('fill', dict(schema=1, recipe=RECIPE, status='generated_and_extracted', scope=SCOPE,
        platform_fingerprint=r.platform['fingerprint'], settings=settings,
        source=originals, gds=r.artifacts['gds'], spef=r.artifacts['spef'], lef=r.artifacts['lef'],
        rules=lock, squares=len(boxes), coupling_threshold_ff=0, sta_coupling_factor=1.,
        extraction_model='typical interconnect; zero-charge quasistatic floating conductors',
        model_artifacts={key: value for key, value in r.artifacts.items() if key.startswith('fill_')},
        acceptance='Layout rules, connectivity, equivalence and timing are separate required checks.'), 'fill.json')


def verify(upstream, config):
    artifacts = upstream.get('artifacts', {})
    if not config.get('physical', {}).get('gf180_fill') and 'fill' not in artifacts:
        return
    require('fill' in artifacts, 'Run physical finish with GF180 fill before extracted timing or export.')
    report = json.loads((Path(upstream['root'])/artifacts['fill']['path']).read_text())
    from .digital_physical import DEFAULTS
    expected = {**DEFAULTS, **config.get('physical', {})}
    require({k:v for k,v in report.get('settings', {}).items() if k != 'threads'} ==
            {k:v for k,v in expected.items() if k != 'threads'}, 'Fill settings differ from the current design.')
    require(report.get('schema') == 1 and report.get('recipe') == RECIPE and
            report.get('status') == 'generated_and_extracted' and
            report.get('platform_fingerprint') == config['platform']['fingerprint'] and
            report.get('gds') == artifacts.get('gds') and report.get('spef') == artifacts.get('spef') and
            report.get('lef') == artifacts.get('lef') and
            report.get('source', {}).get('netlist') == artifacts.get('netlist'),
            'Fill evidence does not match the final geometry, parasitics or netlist.')
    require(report.get('model_artifacts') and all(artifacts.get(key) == value for key, value in report['model_artifacts'].items()),
            'The captured floating-fill model is incomplete.')
