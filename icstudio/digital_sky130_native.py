"""Generic SKY130 native geometry checks, bound to the final exported layout.

Names, dimensions and pins come from the design. No shuttle template or
interface is imposed. This stage does not establish complete physical signoff.
"""
from collections import Counter
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

from .model import atomic_write, file_digest

ASSETS = Path(__file__).parent / 'assets/verification/sky130'
DECK_SHA256 = 'aeba6ab5137923f2258714ab5d91ce99ca6a6f932bea55dedfe6f79aca697ba1'
LICENSE_SHA256 = '3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986'
CATEGORIES_SHA256 = '68c8729ce82d1081df6b850e7b162180c78539b1f72b1424ed519fc5edceca13'
REVISION = '6c401ed5134a6466c7eed3e5524ebaacad4cea2a'
FLAGS = dict(feol='true', beol='true', offgrid='true', seal='false',
             floating_met='false', sram_exclude='false', info='false')
POLICY = dict(recipe='sky130-generic-native-block-v1', deck_sha256=DECK_SHA256,
              revision=REVISION, flags=FLAGS)
SCOPE = ('Generic SKY130 AL-backend FEOL, BEOL and off-grid geometry on the exact final GDS. '
         'Block context: seal checking is deferred to complete-chip qualification. '
         'The deck floating-metal option is off; Studio device-root connectivity and LVS remain '
         'separate obligations. SRAM_EXCLUDE is false, but upstream built-in cell filters remain. '
         'Density, antenna, LVS, special-device coverage and full signoff are not established by this report.')


def require(condition, message):
    if not condition:
        raise ValueError('SKY130 native geometry: ' + message)


def resources():
    for name, expected in (('sky130A_mr.drc', DECK_SHA256), ('GPL-3.0.txt', LICENSE_SHA256),
                           ('categories.json', CATEGORIES_SHA256)):
        require(file_digest(ASSETS/name) == expected, 'missing or changed source: '+name)
    return ASSETS


def measured(path, top):
    root = ET.parse(path).getroot()
    require(root.tag == 'report-database' and root.findtext('top-cell') == top,
            'report has the wrong format or top cell')
    categories = [x.text for x in root.findall('./categories/category/name')]
    expected = json.loads((ASSETS/'categories.json').read_bytes())
    require(file_digest(ASSETS/'categories.json') == CATEGORIES_SHA256, 'rule inventory changed')
    require(sorted(categories) == expected and len(set(categories)) == len(categories),
            'missing, duplicate or changed rule categories')
    items = root.find('items')
    require(items is not None, 'missing violation inventory')
    counts = Counter()
    for item in items:
        require(item.tag == 'item' and item.findtext('category'), 'invalid violation record')
        category = item.findtext('category').strip("'")
        require(category in categories, 'violation has an unknown category')
        counts[category] += 1
    return dict(markers=sum(counts.values()), categories=len(categories), violations=dict(sorted(counts.items())))


def execute(r):
    if r.platform['name'] != 'sky130hd':
        return None
    source = resources()
    folder = r.root/'sky130-native'
    folder.mkdir()
    for name in ('sky130A_mr.drc', 'GPL-3.0.txt', 'categories.json'):
        shutil.copyfile(source/name, folder/name)
    gds = r.root/r.artifacts['gds']['path']
    for key in ('gds', 'checkpoint'):
        require(file_digest(r.root/r.artifacts[key]['path']) == r.artifacts[key]['sha256'], key+' changed')
    engine_sha256 = file_digest(r.tools['klayout'])
    variables = dict(input=str(gds), top_cell=r.config['top'], report=str(folder/'report.lyrdb'),
                     thr='1', **FLAGS)
    command = [r.tools['klayout'], '-b', '-r', str(folder/'sky130A_mr.drc')]
    for name, value in variables.items():
        command += ['-rd', name+'='+value]
    request = dict(policy=POLICY, command=command, inputs={k:r.artifacts[k] for k in ('gds', 'checkpoint')})
    atomic_write(folder/'request.json', json.dumps(request, indent=2)+'\n')
    text = r.command(command, 'Checking generic SKY130 transistor, wiring and grid rules', cwd=folder, fraction=.97)
    atomic_write(folder/'native.log', text)
    require('release 2026.03.30_01.00' in text.splitlines(), 'native checker did not finish')
    values = measured(folder/'report.lyrdb', r.config['top'])
    for key in ('gds', 'checkpoint'):
        require(file_digest(r.root/r.artifacts[key]['path']) == r.artifacts[key]['sha256'],
                key+' changed during verification')
    for name in ('sky130A_mr.drc', 'GPL-3.0.txt', 'categories.json'):
        require(file_digest(folder/name) == file_digest(source/name), 'source changed during verification')
    require(file_digest(r.tools['klayout']) == engine_sha256, 'engine changed during verification')
    evidence = {}
    for name in ('sky130A_mr.drc', 'GPL-3.0.txt', 'categories.json', 'request.json', 'native.log', 'report.lyrdb'):
        key = 'sky130_native_'+name.replace('.', '_').replace('-', '_')
        r.add_artifact(key, folder/name)
        evidence[name] = key
    report = dict(schema=1, policy=POLICY, status='PASS' if values['markers'] == 0 else 'FAIL',
                  scope=SCOPE, qualified=False, top=r.config['top'], **values,
                  gds_sha256=r.artifacts['gds']['sha256'], checkpoint_sha256=r.artifacts['checkpoint']['sha256'],
                  platform_fingerprint=r.platform['fingerprint'], evidence=evidence,
                  engine=dict(version=r.versions['klayout'], sha256=engine_sha256))
    r.save_json('sky130_native', report, 'sky130-native/report.json')
    require(report['status'] == 'PASS', 'final layout has '+str(values['markers'])+' violations; inspect the retained report')
    return report


def validate_saved(data, root):
    root = Path(root).resolve()
    files = data['artifacts']
    policy = data.get('environment', {}).get('sky130_native')
    declared = data.get('physical', {}).get('sky130_native')
    present = any(k == 'sky130_native' or k.startswith('sky130_native_') for k in files)
    if (root/'input.json').is_file():
        captured = json.loads((root/'input.json').read_bytes()).get('environment', {})
        require(captured.get('sky130_native') == policy, 'policy differs from captured inputs')
    if policy is None and declared is None and not present:
        return None  # Historical results retain their original, narrower scope.
    require(policy == POLICY and data.get('platform', {}).get('name') == 'sky130hd', 'missing or changed policy')
    def read(key):
        require(key in files, 'missing retained artifact: '+key)
        item = files[key]
        path = (root/item['path']).resolve()
        require(path.is_relative_to(root) and path.is_file() and file_digest(path) == item['sha256'],
                'missing or changed retained artifact: '+key)
        return path
    report = json.loads(read('sky130_native').read_bytes())
    require(report == declared and report.get('schema') == 1 and report.get('policy') == POLICY and
            report.get('scope') == SCOPE and report.get('qualified') is False and report.get('status') == 'PASS',
            'incomplete, changed or failed declaration')
    for key in ('gds', 'checkpoint'):
        read(key)
        require(report.get(key+'_sha256') == files[key]['sha256'], 'report belongs to another '+key)
    require(report.get('platform_fingerprint') == data['platform']['fingerprint'], 'platform changed')
    names = {'sky130A_mr.drc', 'GPL-3.0.txt', 'categories.json', 'request.json', 'native.log', 'report.lyrdb'}
    evidence = report.get('evidence', {})
    require(evidence.keys() == names and len(set(evidence.values())) == len(names), 'incomplete raw evidence')
    paths = {name:read(key) for name, key in evidence.items()}
    require(file_digest(paths['sky130A_mr.drc']) == DECK_SHA256 and
            file_digest(paths['GPL-3.0.txt']) == LICENSE_SHA256 and
            paths['categories.json'].read_bytes() == (ASSETS/'categories.json').read_bytes(), 'source changed')
    require('release 2026.03.30_01.00' in paths['native.log'].read_text().splitlines(), 'native run incomplete')
    values = measured(paths['report.lyrdb'], report.get('top'))
    require(values['markers'] == 0 and all(report.get(k) == v for k, v in values.items()), 'measurements differ')
    request = json.loads(paths['request.json'].read_bytes())
    inputs=request.get('inputs', {})
    require(request.get('policy') == POLICY and inputs.keys() == {'gds','checkpoint'} and
            all(inputs[k].get('sha256') == files[k]['sha256'] for k in inputs),
            'request differs from exported inputs')
    command = request.get('command', [])
    require(isinstance(command, list) and len(command) == 4+2*(4+len(FLAGS)) and
            command[1:3] == ['-b','-r'] and command[4::2] == ['-rd']*(4+len(FLAGS)), 'invalid command')
    variables = dict(v.split('=',1) for v in command[5::2])
    require(set(variables) == {'input','top_cell','report','thr',*FLAGS} and variables['top_cell'] == report['top'] and
            variables['thr'] == '1' and all(variables[k] == v for k,v in FLAGS.items()), 'execution options changed')
    execution = data.get('execution', {}).get('native_environment', data.get('environment', {}))
    require(report['engine']['version'] == data.get('versions', {}).get('klayout') and
            report['engine']['sha256'] == execution.get('executables', {}).get('klayout'), 'engine identity changed')
    return report
