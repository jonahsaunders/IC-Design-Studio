"""Evidence-bound execution of the reviewed thirteen-stage HD antenna supplement."""
from collections import Counter
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

from .model import atomic_write, file_digest

RECIPE = 'sky130-hd-staged-antenna-v1'
DECK_SHA256 = '92b0378b845c81f2e5ec46918f894988f8648fd0a8f4482441de325aa3cc18fc'
VERSION = 'KLayout 0.30.5'
COMPLETE = 'ICSTUDIO_ALL_ANTENNA_STAGES_COMPLETE'
SCOPE = ('Thirteen staged antenna checks on the captured SKY130 five-metal HD MOS layout. '
         'The reviewed supplemental deck retains its published met5 description discrepancy. '
         'Other devices, process options, complete physical coverage and foundry signoff remain unqualified.')
STAGES = ('poly', 'licon', 'li', 'mcon', 'met1', 'via', 'met2', 'via2', 'met3', 'via3', 'met4', 'via4', 'met5')
PARAMETERS = dict(zip(STAGES, zip(
    (50, 3, 75, 3, 400, 6, 400, 6, 400, 6, 400, 6, 400),
    (.180, 0, .100, 0, .350, 0, .350, 0, .800, 0, .800, 0, 1.200),
    (0, 0, 450, 18, 400, 36, 400, 36, 400, 36, 400, 36, 400),
    (0, 0, 0, 0, 2200, 0, 2200, 0, 2200, 0, 2200, 0, 2200))))
FIELDS = ('limit', 'thickness_um', 'diode_area_factor', 'diode_bonus')


def require(value, message):
    if not value:
        raise ValueError('SKY130 staged antenna: '+message)


def policy_check(policy):
    from .digital import relative_path
    require(isinstance(policy, dict) and set(policy) == {'recipe', 'deck', 'sha256'} and
            policy['recipe'] == RECIPE and policy['sha256'] == DECK_SHA256, 'unsupported policy')
    relative_path(policy['deck'])


def validate(platform):
    policy = platform.get('sky130_antenna')
    if policy is None:
        return
    policy_check(policy)
    require(platform.get('name') == 'sky130hd' and
            {r['path']: r['sha256'] for r in platform['files']}.get(policy['deck']) == DECK_SHA256,
            'missing or changed captured deck')


def measured(metrics, report_path, top):
    """Require all numerical settings and compare counts to the raw native database."""
    require(isinstance(metrics, dict) and metrics.get('status') == 'all-stages-executed' and
            metrics.get('qualified') is False, 'incomplete native execution')
    rows = metrics.get('stages')
    require(isinstance(rows, list) and len(rows) == 13 and
            all(isinstance(r, dict) for r in rows) and [r.get('stage') for r in rows] == list(STAGES),
            'missing, duplicate or reordered stages')
    for row in rows:
        require(all(type(row.get(key)) in (int, float) and row[key] == value
                    for key, value in zip(FIELDS, PARAMETERS[row['stage']])) and
                type(row.get('markers')) is int and row['markers'] >= 0, 'changed settings or invalid marker count')
    raw = ET.parse(report_path).getroot()
    require(raw.tag == 'report-database' and raw.findtext('top-cell') == top and
            raw.find('items') is not None, 'native report belongs to another design or is incomplete')
    categories = [c.findtext('name') for c in raw.findall('.//categories/category')]
    require(len(categories) == 13 and set(categories) == {'ar_q.'+s+'.1' for s in STAGES},
            'native report omits or duplicates a stage')
    counts = Counter()
    for item in raw.findall('./items/item'):
        category = item.findtext('category', '').strip("'")
        require(category in categories, 'unexpected native marker category')
        counts[category] += 1
    require(all(row['markers'] == counts['ar_q.'+row['stage']+'.1'] for row in rows),
            'native report and metrics disagree')
    return dict(stages=rows, violations=sum(counts.values()))


def evaluate(report, gds, checkpoint, top, fingerprint, policy):
    policy_check(policy)
    require(isinstance(report, dict) and report.get('schema') == 1 and report.get('recipe') == RECIPE and
            report.get('policy') == policy and report.get('scope') == SCOPE and
            report.get('qualified') is False and report.get('chunk_complete') is False and
            report.get('status') == 'PASS', 'missing or failed execution evidence')
    require(report.get('gds_sha256') == gds and report.get('checkpoint_sha256') == checkpoint and
            report.get('top') == top and report.get('platform_fingerprint') == fingerprint,
            'evidence belongs to another layout, checkpoint, platform or design')
    engine = report.get('engine', {})
    require(engine.get('version') == VERSION and isinstance(engine.get('sha256'), str) and
            re.fullmatch('[0-9a-f]{64}', engine['sha256']), 'missing or unsupported native engine identity')
    require(type(report.get('violations')) is int and report['violations'] == 0, 'antenna violations remain')
    return report


def execute(r):
    policy = r.platform.get('sky130_antenna')
    if policy is None:
        return None
    validate(r.platform)
    folder = r.root/'sky130-antenna-checks'; folder.mkdir()  # Stale evidence never satisfies a new run.
    report = dict(schema=1, recipe=RECIPE, policy=policy, scope=SCOPE, qualified=False,
                  chunk_complete=False, status='FAIL', top=r.config['top'],
                  platform_fingerprint=r.platform['fingerprint'])
    try:
        original = {key: dict(r.artifacts[key]) for key in ('gds', 'checkpoint')}
        for key, record in original.items():
            require(file_digest(r.root/record['path']) == record['sha256'], 'changed '+key+' input')
            report[key+'_sha256'] = record['sha256']
        source = (r.root/'platform'/policy['deck']).resolve()
        require(source.is_relative_to((r.root/'platform').resolve()) and
                file_digest(source) == DECK_SHA256, 'changed deck before execution')
        deck = folder/'check.drc'; shutil.copyfile(source, deck)
        tool = r.tools.get('klayout'); version = r.versions.get('klayout')
        require(tool and version == VERSION, 'the reviewed KLayout 0.30.5 native engine is required')
        report['engine'] = dict(version=version, sha256=file_digest(tool))
        command = [tool, '-b', '-r', str(deck)]
        for key, value in dict(input=r.root/original['gds']['path'], top_cell=r.config['top'],
                               report=folder/'report.lyrdb', metrics=folder/'metrics.json').items():
            command += ['-rd', key+'='+str(value)]
        atomic_write(folder/'request.json', json.dumps(dict(command=command, inputs=original), indent=2)+'\n')
        output = r.command(command, 'Checking all thirteen SKY130 antenna stages', cwd=folder, fraction=.98)
        atomic_write(folder/'native.log', output)
        require(COMPLETE in output.splitlines(), 'missing native completion marker')
        for key, record in original.items():
            require(file_digest(r.root/record['path']) == record['sha256'], key+' changed during execution')
        require(file_digest(deck) == file_digest(source) == DECK_SHA256 and
                file_digest(tool) == report['engine']['sha256'], 'engine or deck changed during execution')
        report.update(measured(json.loads((folder/'metrics.json').read_bytes()), folder/'report.lyrdb', r.config['top']))
        require(report['violations'] == 0, str(report['violations'])+' antenna violations remain')
        report['status'] = 'PASS'
        evaluate(report, original['gds']['sha256'], original['checkpoint']['sha256'],
                 r.config['top'], r.platform['fingerprint'], policy)
    except Exception as exc:
        report.update(status='FAIL', error=str(exc))
        raise
    finally:
        report['evidence'] = {}
        for path in sorted(p for p in folder.iterdir() if p.is_file()):
            key = 'sky130_antenna_'+path.stem
            r.add_artifact(key, path, allow_empty=True); report['evidence'][path.name] = key
        r.save_json('sky130_antenna', report, 'sky130-antenna-checks/accepted.json')
    return report


def validate_saved(data, root):
    files = data['artifacts']; policy = data.get('environment', {}).get('sky130_antenna')
    captured = data.get('environment', {}).get('platform')
    if isinstance(captured, dict):
        require(captured.get('sky130_antenna') == policy, 'policy differs from captured environment')
    declared = data.get('physical', {}).get('sky130_antenna')
    present = any(k == 'sky130_antenna' or k.startswith('sky130_antenna_') for k in files)
    if policy is None and declared is None and not present:
        return None
    policy_check(policy)
    require(isinstance(declared, dict) and data.get('platform', {}).get('name') == 'sky130hd',
            'missing declaration or wrong platform')
    root = Path(root).resolve()
    def read(key):
        require(key in files, 'missing retained artifact: '+key)
        item = files[key]; path = (root/item['path']).resolve()
        require(path.is_relative_to(root) and path.is_file() and file_digest(path) == item['sha256'],
                'changed retained artifact: '+key)
        return path
    report = json.loads(read('sky130_antenna').read_bytes())
    require(report == declared, 'declaration differs from retained report')
    for key in ('gds', 'checkpoint'):
        read(key)
    evaluate(report, files['gds']['sha256'], files['checkpoint']['sha256'], report.get('top'),
             data['platform']['fingerprint'], policy)
    require(data.get('versions', {}).get('klayout') == report['engine']['version'], 'changed native engine version')
    execution = data.get('execution', {}).get('native_environment', data.get('environment', {}))
    require(execution.get('executables', {}).get('klayout') == report['engine']['sha256'],
            'native engine differs from captured execution environment')
    evidence = report.get('evidence', {})
    names = {'check.drc', 'metrics.json', 'report.lyrdb', 'native.log', 'request.json'}
    require(evidence.keys() == names and len(set(evidence.values())) == len(names) and
            all(k.startswith('sky130_antenna_') for k in evidence.values()), 'incomplete raw evidence')
    paths = {name: read(key) for name, key in evidence.items()}
    require(file_digest(paths['check.drc']) == DECK_SHA256 and
            COMPLETE in paths['native.log'].read_text().splitlines(), 'changed deck or incomplete execution')
    result = measured(json.loads(paths['metrics.json'].read_bytes()), paths['report.lyrdb'], report['top'])
    require(all(report.get(k) == v for k, v in result.items()), 'retained native measurements differ')
    request = json.loads(paths['request.json'].read_bytes())
    inputs = request.get('inputs', {})
    require(inputs.keys() == {'gds', 'checkpoint'} and
            all(inputs[k].get('sha256') == files[k]['sha256'] for k in inputs), 'changed execution inputs')
    command = request.get('command', [])
    require(isinstance(command, list) and len(command) == 12 and all(isinstance(c, str) for c in command) and
            command[1:3] == ['-b', '-r'] and command[4::2] == ['-rd']*4 and
            [c.split('=', 1)[0] for c in command[5::2]] == ['input', 'top_cell', 'report', 'metrics'] and
            command[7] == 'top_cell='+report['top'], 'changed native invocation')
    return report
