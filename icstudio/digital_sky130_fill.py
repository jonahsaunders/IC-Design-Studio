"""Optional local SKY130 metal fill with independent database/stream checks.

The recipe targets the public 80% grown-metal screening profile. It makes no
claim about complete foundry density, generated masks or fill-aware parasitics.
"""
import json
from pathlib import Path
import re
import shutil
import sys
import xml.etree.ElementTree as ET

from .model import atomic_write, file_digest

RECIPE = 'sky130-local-metal-fill-v1'
LYT_SHA256 = '8f1b3d1679f3d195658bea0359eb01f32694628858eda1a8a5c6bf1b30da836a'
METALS = {f'met{i}': (fill, 67+i) for i, fill in enumerate((36, 41, 34, 51, 59), 1)}
SCOPE = ('Local metal fill on the five-metal SKY130A HD stack. Every exported fill rectangle is '
    'compared with the implementation database; widths, area, spacing, grid and signal clearance '
    'are independently checked. Full 700 um windows use the two retained public 80% grown-metal '
    'profiles. Smaller blocks require surrounding layout; clipped edge observations are diagnostic. '
    'This is not complete density, generated-mask, electrical or foundry signoff. Routed OpenRCX '
    'SPEF is retained, but floating-fill coupling has not been qualified.')


def require(condition, message):
    if not condition: raise ValueError('SKY130 fill: '+message)


def rules():
    layers = {}
    for i, (name, (fill, _)) in enumerate(METALS.items(), 1):
        layers[name] = dict(layer=fill, name=name, dir='H' if i % 2 else 'V', datatype=0,
            space_to_outline=2, **{'non-opc': dict(datatype=0, width=[2.0],
                height=[1.0] if i == 1 else [2.0], space_to_fill=.4 if i < 5 else 1.6,
                space_to_non_fill=.28 if i < 3 else .4 if i < 5 else 1.6)})
    return dict(layers=layers, outline=dict(layer=237, datatype=0))


def technology(raw):
    import hashlib
    require(hashlib.sha256(raw).hexdigest() == LYT_SHA256, 'unsupported stream technology; import the reviewed SKY130 HD platform')
    root = ET.fromstring(raw); mapping = root.find('.//lefdef/layer-map')
    require(mapping is not None and mapping.text.startswith('layer_map(') and mapping.text.endswith(')'),
            'missing stream layer map')
    mapping.text = mapping.text[:-1]+''.join(';'+repr(name+'.FILL : '+str(pair[0])+'/28')
                                             for name, pair in METALS.items())+')'
    require(root.findtext('.//lefdef/produce-fills') == 'true' and
            root.findtext('.//lefdef/special-fills-suffix-string') == '.FILL', 'unsupported fill reader settings')
    return ET.tostring(root, encoding='unicode')+'\n'


def implementation_options(r, settings):
    if not settings.get('sky130_fill'): return []
    require(r.platform['name'] == 'sky130hd' and r.platform.get('sky130_rules'),
            'choose a SKY130 HD platform with the local physical checkers')
    require(not settings.get('gf180_fill') and not settings.get('ihp_fill'), 'choose one process fill option')
    folder = r.root/'sky130-fill'; folder.mkdir()
    source = r.root/'platform'/r.platform.get('directory', '.')/'sky130hd.lyt'
    source_name = source.relative_to(r.root/'platform').as_posix()
    require(any(x['path'] == source_name and x['sha256'] == LYT_SHA256 for x in r.platform['files']),
            'stream technology is not captured by the selected platform')
    atomic_write(folder/'technology.lyt', technology(source.read_bytes()))
    shutil.copyfile(source, folder/'source.lyt')
    atomic_write(folder/'rules.json', json.dumps(rules(), indent=2)+'\n')
    for key, path in (('sky130_fill_technology', folder/'technology.lyt'), ('sky130_fill_rules', folder/'rules.json'),
                      ('sky130_fill_source_technology', folder/'source.lyt')):
        r.add_artifact(key, path)
    return ['USE_FILL=1', 'FILL_CONFIG='+str(folder/'rules.json'), 'KLAYOUT_TECH_FILE='+str(folder/'technology.lyt')]


def geometry(path, inventory):
    import klayout.db as k
    from .digital_sky130_oxide_density import windows
    require(inventory.get('schema') == 1 and set(inventory.get('fills', {})) == set(METALS), 'incomplete database inventory')
    bounds = inventory.get('die_nm'); windows(bounds)
    require(bounds is not None, 'missing independent layout bounds')
    layout = k.Layout(); layout.read(str(path))
    require(len(layout.top_cells()) == 1 and layout.top_cell().name == inventory.get('top') and
            abs(layout.dbu-.001) < 1e-12, 'wrong layout, top or database units')
    top = layout.top_cell(); die = k.Region(k.Box(*bounds)); measurements = {}
    for i, (name, (fill_layer, drawing_layer)) in enumerate(METALS.items(), 1):
        boxes = inventory['fills'][name]
        require(isinstance(boxes, list) and all(isinstance(b, list) and len(b) == 4 and
                all(type(n) is int for n in b) and b[0] < b[2] and b[1] < b[3] for b in boxes), 'invalid fill rectangles')
        require(boxes == sorted(boxes) and len({tuple(b) for b in boxes}) == len(boxes), 'duplicate or unordered fill records')
        actual = []; iterator = top.begin_shapes_rec(layout.layer(fill_layer, 28))
        while not iterator.at_end():
            shape = iterator.shape()
            require(not shape.is_text() and (shape.is_box() or shape.is_polygon()) and shape.polygon.is_box(),
                    'nonrectangular streamed fill')
            polygon = shape.polygon.transformed(iterator.trans()); b = polygon.bbox()
            require(polygon.is_box(), 'transformed fill is not rectangular')
            actual.append([b.left, b.bottom, b.right, b.top]); iterator.next()
        require(sorted(actual) == boxes, 'streamed '+name+' fill differs from the implementation database')
        fill = k.Region([k.Box(*b) for b in boxes]); signal = k.Region(top.begin_shapes_rec(layout.layer(drawing_layer, 20))).merged()
        spacing = 400 if i < 5 else 1600; clearance = 280 if i < 3 else 400 if i < 5 else 1600
        failures = dict(grid=sum(any(n % 5 for n in b) for b in boxes),
            shape=sum(b[2]-b[0] != 2000 or b[3]-b[1] != (1000 if i == 1 else 2000) for b in boxes),
            outside=(fill-die).count(), spacing=fill.space_check(spacing).count(),
            signal_overlap=(fill & signal).count(), clearance=fill.separation_check(signal, clearance).count())
        require(not any(failures.values()), name+' fill geometry failed: '+str(failures))
        measurements[name] = dict(rectangles=len(boxes), area_nm2=fill.area(), violations=failures)
    require(sum(x['rectangles'] for x in measurements.values()) > 0, 'engine produced no fill')
    return measurements


def abstract(source, inventory):
    text = Path(source).read_text(); top = inventory['top']; x0, y0, _, _ = inventory['die_nm']
    require(re.findall(r'^MACRO (\S+)\s*$', text, re.M) == [top] and
            not re.search(r'^\s*ORIGIN\s+', text, re.M) and text.count('\n  OBS\n') == 1, 'unsupported abstract format')
    start = text.index('\n  OBS\n')+len('\n  OBS\n'); end = text.index('\n  END\n', start-1)
    lines = []
    for name, boxes in inventory['fills'].items():
        if not boxes: continue
        lines.append('    LAYER '+name+' ;')
        for x1, y1, x2, y2 in boxes:
            lines.append('     RECT '+' '.join(f'{n/1000:.3f}' for n in (x1-x0, y1-y0, x2-x0, y2-y0))+' ;')
    return text[:end]+'\n'+'\n'.join(lines)+text[end:]


def density_status(report):
    from .digital_sky130_oxide_density import evaluate
    evaluate(report, report.get('gds_sha256'), report.get('top'))
    if any(v['full_window_findings'] for v in report['summaries'].values()): return 'FAIL'
    return 'sampled-full-windows-pass' if report['full_windows'] else 'surrounding-layout-required'


def execute(r, settings, reviewed):
    if not settings.get('sky130_fill'): return None
    folder = r.root/'sky130-fill'; worker = folder/'inventory.py'
    shutil.copyfile(Path(__file__).with_name('digital_sky130_fill_inventory.py'), worker)
    r.command([r.tools['openroad'], '-no_init', '-exit', '-python', str(worker),
               str(r.root/r.artifacts['checkpoint']['path']), str(folder/'inventory.json')],
              'Checking SKY130 fill against the implementation database', fraction=.98)
    request = dict(gds=str(r.root/r.artifacts['gds']['path']), inventory=str(folder/'inventory.json'),
                   output=str(folder/'geometry.json'))
    atomic_write(folder/'request.json', json.dumps(request, indent=2)+'\n')
    script = 'import sys,json\nfrom pathlib import Path\nsys.path.insert(0,'+repr(str(Path(__file__).resolve().parents[1]))+')\n'
    script += 'from icstudio.digital_sky130_fill import geometry\nr=json.loads(Path(sys.argv[1]).read_bytes())\n'
    script += 'Path(r["output"]).write_text(json.dumps(geometry(r["gds"],json.loads(Path(r["inventory"]).read_bytes())),indent=2)+"\\n")\n'
    atomic_write(folder/'check.py', script)
    r.command([sys.executable, str(folder/'check.py'), str(folder/'request.json')],
              'Checking final SKY130 fill geometry and stream layers', fraction=.98)
    inventory = json.loads((folder/'inventory.json').read_bytes())
    require(inventory['checkpoint_sha256'] == r.artifacts['checkpoint']['sha256'], 'inventory belongs to another checkpoint')
    require(reviewed is not None and reviewed['oxide_density']['measurements']['bounds_nm'] == inventory['die_nm'],
            'density was not measured on the independent implementation bounds')
    status = density_status(reviewed['oxide_density'])
    require(status != 'FAIL', 'a full public density window is below 80%; inspect the density report')
    original_lef = dict(r.artifacts['lef']); r.artifacts['sky130_fill_source_lef'] = original_lef
    atomic_write(folder/'filled.lef', abstract(r.root/original_lef['path'], inventory)); r.add_artifact('lef', folder/'filled.lef')
    for name in ('inventory.py', 'inventory.json', 'request.json', 'check.py', 'geometry.json'):
        r.add_artifact('sky130_fill_'+name.replace('.', '_'), folder/name)
    report = dict(schema=1, recipe=RECIPE, status='generated-and-checked', qualified=False, scope=SCOPE,
        top=r.config['top'], platform_fingerprint=r.platform['fingerprint'],
        inputs={key: r.artifacts[key]['sha256'] for key in ('gds', 'checkpoint', 'lef', 'def', 'netlist')},
        geometry=json.loads((folder/'geometry.json').read_bytes()), density_status=status,
        density_sha256=r.artifacts['sky130_rules']['sha256'], full_windows=reviewed['oxide_density']['full_windows'],
        evidence={key: dict(value) for key, value in r.artifacts.items() if key.startswith('sky130_fill_')})
    r.save_json('sky130_fill', report, 'sky130-fill/report.json')
    return report


def validate_saved(data, root):
    root = Path(root).resolve(); files = data['artifacts']; settings = data.get('physical', {}).get('settings', {})
    requested = settings.get('sky130_fill', False)
    present = any(k == 'sky130_fill' or k.startswith('sky130_fill_') for k in files)
    if data.get('platform', {}).get('name') != 'sky130hd' and not requested and not present: return None
    if (root/'input.json').is_file():
        from .digital_design import config
        job = json.loads((root/'input.json').read_bytes())
        require(isinstance(job.get('project'), dict) and 'cell' in job, 'the captured job inputs are incomplete')
        require(config(job['project'], job['cell']).get('physical', {}).get('sky130_fill', False) == requested,
                'fill setting differs from captured inputs')
    if not requested and not present: return None
    require(requested is True and data.get('platform', {}).get('name') == 'sky130hd', 'missing or changed fill setting')
    def read(key):
        require(key in files, 'missing artifact: '+key)
        item = files[key]; path = (root/item['path']).resolve()
        require(path.is_relative_to(root) and path.is_file() and file_digest(path) == item['sha256'], 'changed artifact: '+key)
        return path
    report = json.loads(read('sky130_fill').read_bytes())
    require(report == data.get('physical', {}).get('sky130_fill') and report.get('schema') == 1 and
            report.get('recipe') == RECIPE and report.get('status') == 'generated-and-checked' and
            report.get('qualified') is False and report.get('scope') == SCOPE and
            report.get('platform_fingerprint') == data['platform']['fingerprint'], 'changed fill declaration')
    require(report.get('inputs') == {key: files[key]['sha256'] for key in ('gds','checkpoint','lef','def','netlist')}, 'different implemented artifacts')
    for key in report['inputs']: read(key)
    expected_keys = {'sky130_fill_'+n for n in ('technology', 'source_technology', 'rules', 'source_lef', 'inventory_py', 'inventory_json', 'request_json', 'check_py', 'geometry_json')}
    require(set(report.get('evidence', {})) == expected_keys, 'incomplete fill evidence')
    for key, item in report['evidence'].items():
        # Exported evidence uses relocated paths; bind content and read the new path.
        require(files.get(key, {}).get('sha256') == item.get('sha256'), 'changed evidence: '+key); read(key)
    require(json.loads(read('sky130_fill_rules').read_bytes()) == rules(), 'changed fill recipe')
    require(read('sky130_fill_technology').read_text() == technology(read('sky130_fill_source_technology').read_bytes()), 'changed fill stream mapping')
    inventory = json.loads(read('sky130_fill_inventory_json').read_bytes())
    require(inventory['top'] == report['top'] and inventory['checkpoint_sha256'] == files['checkpoint']['sha256'], 'changed fill inventory identity')
    require(geometry(read('gds'), inventory) == report['geometry'] == json.loads(read('sky130_fill_geometry_json').read_bytes()), 'fill measurement differs')
    require(read('lef').read_text() == abstract(read('sky130_fill_source_lef'), inventory), 'fill is missing from the macro abstract')
    reviewed = json.loads(read('sky130_rules').read_bytes()); density = reviewed['oxide_density']
    require(files['sky130_rules']['sha256'] == report['density_sha256'] and
            density['gds_sha256'] == files['gds']['sha256'] and density['top'] == report['top'] and
            density['measurements']['bounds_nm'] == inventory['die_nm'] and
            density_status(density) == report['density_status'] != 'FAIL' and density['full_windows'] == report['full_windows'],
            'missing, failed or different density evidence')
    return report
