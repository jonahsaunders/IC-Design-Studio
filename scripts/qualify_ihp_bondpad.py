"""Written IHP pad geometry versus the exact public square PCell branch.

The source oracle records rectangle API calls from the unchanged public method
using a deliberately limited CNI recording adapter. It is not a native CNI PCell
run, process DRC, LVS or an electrical model. Native public DRC is optional and
retains every finding from both decks without filtering chip-context failures.
"""
import argparse
import ast
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.ihp_bondpad import SOURCE, SOURCE_LOCK, install, verify_sources
from icstudio.interchange import export_layout, import_layout
from icstudio.model import clone, example, file_digest, load_project, save_project, scalar

CASES = tuple(dict(diameter_nm=d, hwquota=q, x_nm=125, y_nm=-325, rotation=r)
              for d, q in ((80000, 1), (80000, .5), (80000, 2), (80010, 1))
              for r in (0, 90, 180, 270))


def upstream_rectangles(parameters, root=SOURCE):
    """Execute the authenticated genLayout function with rectangle-only calls.

    The CNI/import/materialization path is intentionally not claimed. Unsupported
    calls fail: the recorder supplies only the selected square, stack=nil,
    fill=nil, FlipChip=no, addFillerEx=nil branch. Public floor/grid arithmetic
    is executed from its own pinned definitions, independently of the app recipe.
    """
    verify_sources(root); root = Path(root)
    tech = json.loads((root/'sg13g2_tech.json').read_bytes())['techParams']
    rows = []; properties = {}
    namespace = dict(math=math, acos=math.acos, sqrt=math.sqrt, Numeric=scalar,
                     Layer=lambda name, purpose='drawing': name+'.'+purpose,
                     Box=lambda *bounds: bounds,
                     dbCreateRect=lambda owner, layer, box: rows.append((layer, box)),
                     dbReplaceProp=lambda owner, name, value: properties.__setitem__(name, value),
                     nth=lambda index, sequence: sequence[index],
                     SG13_IGRID=1/tech['grid'], SG13_GRID=tech['grid'], SG13_EPSILON=tech['epsilon1'])
    utility = ast.parse((root/'utility_functions.py').read_text(encoding='utf-8'))
    funcs = [n for n in utility.body if isinstance(n, ast.FunctionDef) and n.name in ('fix', 'GridFix', 'tog')]
    if {n.name for n in funcs} != {'fix', 'GridFix', 'tog'}:
        raise ValueError('Public grid function set changed.')
    exec(compile(ast.Module(body=funcs, type_ignores=[]), '<pinned public grid>', 'exec'), namespace)
    tree = ast.parse((root/'bondpad_code.py').read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'bondpad')
    function = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'genLayout')
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<pinned public square pad>', 'exec'), namespace)
    instance = SimpleNamespace(tech=SimpleNamespace(getTechParams=lambda: tech),
                               padType='bondpad', diameter=str(parameters['diameter_nm']*1e-9),
                               passEncl='2.1u', hwquota=float(Fraction(str(parameters['hwquota']))),
                               shape='square', topMetal='TM2', bottomMetal='3', stack='nil',
                               fill='nil', FlipChip='no', addFillerEx='nil')
    namespace['genLayout'](instance)
    if properties != {'pin#': 1, 'ignore': 'TRUE'} or len(rows) != 3:
        raise ValueError('Unexpected public pad outputs/properties.')
    return rows


def expected(parameters):
    """Public rectangles, public GDS layer map, exact right-angle transform."""
    import klayout.db as db
    root = ET.fromstring((SOURCE/'sg13g2.lyp').read_bytes())
    mapping = {p.findtext('name'): tuple(map(int, p.findtext('source').split('/')))
               for p in root.iter('properties') if p.findtext('name') in
               ('TopMetal2.drawing', 'TopMetal2.pin', 'Passiv.drawing', 'dfpad.drawing')}
    if mapping != {'TopMetal2.drawing': (134, 0), 'TopMetal2.pin': (134, 2),
                   'Passiv.drawing': (9, 0), 'dfpad.drawing': (41, 0)}:
        raise ValueError('Changed public pad layer meanings.')
    tr = db.Trans(parameters.get('rotation', 0)//90, False,
                  parameters.get('x_nm', 0), parameters.get('y_nm', 0))
    masks = {}
    for name, box in upstream_rectangles(parameters):
        if '.' not in name:
            name += '.drawing'
        if name not in mapping:
            raise ValueError('Unexpected source mask: '+name)
        masks[mapping[name]] = db.Region(tr*db.Box(*[round(v*1000) for v in box]))
    return masks


def check_stream(path, parameters, port='PAD', top='top'):
    import klayout.db as db
    before = file_digest(path); layout = db.Layout(); layout.read(str(path)); cell = layout.cell(top)
    if cell is None or len(list(layout.each_cell())) != 1 or any(cell.each_inst()) or layout.dbu != .001:
        raise ValueError('Require one flat pad cell at the 1 nm database unit.')
    wanted = expected(parameters); actual = {}; labels = []
    for index in layout.layer_indexes():
        info = layout.get_info(index); pair = (info.layer, info.datatype)
        for shape in cell.shapes(index).each():
            if shape.is_text():
                text = shape.text; labels.append((pair, text.string, text.x, text.y))
            else:
                actual.setdefault(pair, db.Region()).insert(shape.polygon)
    if set(actual) != set(wanted):
        raise ValueError('Written pad mask set differs from the public square branch.')
    for pair in wanted:
        if not (actual[pair] ^ wanted[pair]).is_empty():
            raise ValueError('Written pad geometry differs on mask '+str(pair))
    anchor = (parameters.get('x_nm', 0), parameters.get('y_nm', 0))
    if labels != [((134, 2), port, *anchor)]:
        raise ValueError('Written pad must retain its one explicit named terminal anchor.')
    if not any(poly.inside(db.Point(*anchor)) for poly in actual[(134, 0)].each()):
        raise ValueError('Pad terminal is outside its written top-metal conductor.')
    if before != file_digest(path):
        raise ValueError('Written pad changed during audit.')
    return dict(sha256=before, masks=len(wanted), terminal_order=[port], terminal_point_nm=list(anchor),
                source_lock_sha256=SOURCE_LOCK, oracle='Pinned public square genLayout with rectangle-call recorder',
                electrical_model=False, qualified=False)


def project(technology, parameters):
    p = example('empty'); p['pdk'] = clone(technology); p['cells'][0]['ports'] = ['PAD']
    record = install(p, p['top'], 'PAD', parameters)
    return p, record


def technology():
    import icstudio
    root = Path(icstudio.__file__).resolve().parent/'assets/pdks/ihp-sg13g2'
    package = json.loads((root/'package.json').read_bytes()); tech = clone(package['technology'])
    tech.update(package_root=str(root), package_lock={k: package[k] for k in ('id', 'revision', 'files')})
    return tech


def native_pair(positive, negative):
    """Recognize the exact native category string, retaining all other findings."""
    # KLayout's report category API includes single quotes in this public
    # category name. Accept its literal form and the unquoted spelling only.
    detected = any(row.get('violations', 0) > 0 and
                   bool({'Pad.i', "'Pad.i'"} & set(row['categories']))
                   for row in negative['decks'])
    return dict(positive=positive, missing_tm2=negative, expected_control_rule='Pad.i', control_detected=detected,
                positive_clean=positive['violations'] == 0,
                scope='One default square pad and missing-TM2 fault. All public findings retained; no chip-context exceptions.')


def qualify(output, *, klayout=None):
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    verify_sources(); tech = technology(); records = []
    for index, parameters in enumerate(CASES):
        folder = output/str(index); folder.mkdir()
        p, record = project(tech, parameters)
        save_project(p, folder/'pad.icproj'); reopened = load_project(folder/'pad.icproj')
        if reopened != p:
            raise ValueError('Saved pad project changed.')
        for extension in ('gds', 'oas'):
            path = folder/('pad.'+extension); export_layout(reopened, path)
            result = check_stream(path, parameters)
            imported, _ = import_layout(path)
            if imported['cells'][0]['ihp_bondpads'] != p['cells'][0]['ihp_bondpads']:
                raise ValueError('Pad source record changed during application stream exchange.')
            records.append(dict(case=index, parameters=parameters, format=extension, **result))
    drc = None
    if klayout:
        import klayout.db as db
        from icstudio.ihp_klayout_drc import drc as run_drc
        positive = run_drc(klayout, output/'0/pad.gds', 'top', output/'public-drc')
        layout = db.Layout(); layout.read(str(output/'0/pad.gds'))
        layout.top_cell().shapes(layout.layer(134, 0)).clear()
        control = output/'missing-tm2.gds'; layout.write(str(control))
        negative = run_drc(klayout, control, 'top', output/'public-drc-missing-tm2')
        drc = native_pair(positive, negative)
    native_failed = bool(klayout) and (not drc['positive_clean'] or not drc['control_detected'])
    status = 'failed-selected-native-geometry-gate' if native_failed else 'selected-native-geometry-pass' if klayout else 'selected-written-geometry-pass'
    report = dict(schema=1, chunk=7, status=status, cases=records,
                  source_lock_sha256=SOURCE_LOCK, source_commit=verify_sources()['commit'],
                  package_revision=tech['package_lock']['revision'], public_drc=drc,
                  drc_executed=bool(klayout), electrical_model=False, qualified=False, chunk_complete=False,
                  scope=__doc__)
    (output/'record.json').write_bytes((json.dumps(report, indent=2)+'\n').encode())
    if native_failed:
        raise ValueError('Selected native pad gate failed: positive DRC must be clean and the missing-TM2 control must produce Pad.i. All findings retained.')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--klayout', type=Path)
    args = parser.parse_args()
    for name in list(os.environ):
        if name.upper().startswith('GIT_'):
            del os.environ[name]
    report = qualify(args.output, klayout=args.klayout)
    print(json.dumps({key: report[key] for key in ('status', 'drc_executed', 'qualified', 'chunk_complete')}))
