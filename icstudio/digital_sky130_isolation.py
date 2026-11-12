"""Explicit SKY130 x.29 policy, execution and retained export evidence."""
import json
from pathlib import Path
import sys

from .digital_sky130_isolation_lock import FILES, RECIPE, REVISION, RULE
from .model import atomic_write, file_digest

SCOPE = ('SKY130 x.29: C3 NFET gate containment in drawn deep nwell when explicitly requested. '
         'Bulk mode retains measurements as NOT_REQUESTED. Other well rules, body connectivity, '
         'electrical checks and complete physical qualification remain separate.')
POLICY_KEYS = {'recipe', 'directory', 'preparation_sha256', 'nfet_in_dnwell'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def valid_policy(policy):
    from .digital import relative_path
    require(isinstance(policy, dict) and set(policy) == POLICY_KEYS and
            policy['recipe'] == RECIPE and type(policy['nfet_in_dnwell']) is bool,
            'Missing or invalid explicit SKY130 isolation policy.')
    relative_path(policy['directory'], directory=True)


def validate(platform):
    policy = platform.get('sky130_isolation')
    if policy is None:
        return
    valid_policy(policy)
    require(platform.get('name') == 'sky130hd', 'Isolation checking requires a SKY130 HD platform.')
    locks = {row['path']: row['sha256'] for row in platform.get('files', [])}
    expected = FILES | {'preparation.json': policy['preparation_sha256']}
    require(all(locks.get(policy['directory']+'/'+name) == sha for name, sha in expected.items()),
            'A required SKY130 isolation resource is missing or changed.')


def selected(config):
    platform = config.get('platform', {}); settings = config.get('physical', {})
    policy = platform.get('sky130_isolation')
    if 'nfet_in_dnwell' in settings:
        require(type(settings['nfet_in_dnwell']) is bool, 'Isolation must be enabled or disabled explicitly.')
        require(policy is not None, 'Import a SKY130 platform with isolation checking before selecting its mode.')
    if policy is None:
        return None
    validate(platform)
    return dict(policy, nfet_in_dnwell=settings.get('nfet_in_dnwell', policy['nfet_in_dnwell']))


def resources(directory, preparation_sha256):
    directory = Path(directory).resolve()
    def checked(name, sha):
        path = (directory/name).resolve()
        require(path.is_relative_to(directory) and path.is_file() and file_digest(path) == sha,
                'Missing or changed SKY130 isolation resource: '+name)
        return path
    preparation = checked('preparation.json', preparation_sha256)
    record = json.loads(preparation.read_bytes())
    require(record.get('schema') == 1 and record.get('recipe') == RECIPE and
            record.get('revision') == REVISION and record.get('qualified') is False and
            len(record.get('files', [])) == len(FILES) and
            {r['path']: r['sha256'] for r in record['files']} == FILES,
            'Incomplete SKY130 isolation preparation.')
    result = {name: checked(name, sha) for name, sha in FILES.items()}
    require(all(type(row['bytes']) is int and row['bytes'] == result[row['path']].stat().st_size
                for row in record['files']), 'Changed SKY130 isolation resource sizes.')
    return result | {'preparation.json': preparation}


def evaluate(report, gds_sha256, checkpoint_sha256, top, fingerprint, policy):
    valid_policy(policy)
    require(isinstance(report, dict) and report.get('schema') == 1 and report.get('recipe') == RECIPE and
            report.get('rule') == RULE and report.get('revision') == REVISION and report.get('scope') == SCOPE and
            report.get('qualified') is False and report.get('policy') == policy and
            report.get('gds_sha256') == gds_sha256 and report.get('checkpoint_sha256') == checkpoint_sha256 and
            report.get('top') == top and report.get('platform_fingerprint') == fingerprint,
            'Changed SKY130 isolation evidence identity or scope.')
    measurement = report.get('measurement', {})
    count_keys = ('nfet_gates', 'pfet_gates', 'dnwell_polygons', 'raw_dnwell_shapes',
                  'raw_dnwell_texts', 'nfet_not_contained')
    require(isinstance(measurement, dict) and set(measurement) == {'top', 'outside_examples_nm', *count_keys} and
            measurement['top'] == top and all(type(measurement[k]) is int and measurement[k] >= 0 for k in count_keys),
            'Missing or invalid SKY130 isolation measurements.')
    outside = measurement['nfet_not_contained']; examples = measurement['outside_examples_nm']
    require(outside <= measurement['nfet_gates'] and
            measurement['raw_dnwell_texts'] <= measurement['raw_dnwell_shapes'] and
            isinstance(examples, list) and len(examples) == min(20, outside) and
            all(isinstance(box, list) and len(box) == 4 and all(type(v) is int for v in box) and
                box[0] < box[2] and box[1] < box[3] for box in examples) and examples == sorted(examples),
            'Inconsistent SKY130 isolation measurements.')
    enabled = policy['nfet_in_dnwell']
    expected = ('FAIL' if outside else 'PASS') if enabled else 'NOT_REQUESTED'
    require(report.get('enforced') is enabled and report.get('status') == expected,
            'SKY130 isolation status does not match its explicit mode and measurements.')
    require(expected != 'FAIL', 'Required SKY130 NMOS isolation failed.')
    return report


def execute(r):
    policy = selected(r.config)
    if policy is None:
        return None
    paths = resources(r.root/'platform'/policy['directory'], policy['preparation_sha256'])
    folder = r.root/'sky130-isolation'; folder.mkdir()
    original = {key: dict(r.artifacts[key]) for key in ('gds', 'checkpoint')}
    request = dict(resources=str(r.root/'platform'/policy['directory']), policy=policy,
                   gds=str(r.root/original['gds']['path']), gds_sha256=original['gds']['sha256'],
                   checkpoint=str(r.root/original['checkpoint']['path']), checkpoint_sha256=original['checkpoint']['sha256'],
                   top=r.config['top'], platform_fingerprint=r.platform['fingerprint'], output=str(folder/'verified'))
    atomic_write(folder/'request.json', json.dumps(request, indent=2)+'\n')
    bootstrap = 'import sys\nsys.dont_write_bytecode=True\nsys.path.insert(0,'+repr(str(Path(__file__).resolve().parents[1]))+')\n'
    bootstrap += 'import json\nfrom pathlib import Path\nfrom icstudio.digital_sky130_isolation_worker import execute\nexecute(json.loads(Path(sys.argv[1]).read_bytes()))\n'
    atomic_write(folder/'run.py', bootstrap)
    try:
        r.command([sys.executable, str(folder/'run.py'), str(folder/'request.json')],
                  'Checking SKY130 NMOS isolation', cwd=folder, fraction=.98)
    finally:
        for index, path in enumerate(sorted(p for p in folder.rglob('*') if p.is_file())):
            r.add_artifact('sky130_isolation_file_'+str(index), path, allow_empty=True)
    report = json.loads((folder/'verified/report.json').read_bytes())
    for key, record in original.items():
        require(file_digest(r.root/record['path']) == record['sha256'], 'Changed SKY130 isolation '+key+'.')
    resources(request['resources'], policy['preparation_sha256'])
    evaluate(report, original['gds']['sha256'], original['checkpoint']['sha256'], r.config['top'],
             r.platform['fingerprint'], policy)
    report['resources'] = {}
    for index, (name, path) in enumerate(sorted(paths.items())):
        key = 'sky130_isolation_resource_'+str(index); r.add_artifact(key, path, allow_empty=True)
        report['resources'][name] = key
    for key, name in [('request_artifact', 'request.json'), ('raw_artifact', 'verified/report.json')]:
        report[key] = next(k for k, v in r.artifacts.items() if v['path'] == (folder/name).relative_to(r.root).as_posix())
    r.save_json('sky130_isolation', report, 'sky130-isolation/accepted.json')
    return report


def validate_saved(data, root):
    root = Path(root).resolve(); files = data['artifacts']
    policy = data.get('environment', {}).get('sky130_isolation')
    declared = data.get('physical', {}).get('sky130_isolation')
    present = any(key.startswith('sky130_isolation') for key in files)
    # Original jobs bind the setting even if every evidence declaration was removed.
    if (root/'input.json').is_file():
        from .digital_design import config
        job = json.loads((root/'input.json').read_bytes())
        try:
            value = config(job['project'], job['cell'])
        except (KeyError, TypeError, StopIteration) as error:
            raise ValueError('Invalid captured job inputs for SKY130 isolation validation.') from error
        require(isinstance(value, dict), 'Captured inputs have no digital configuration.')
        require(selected(value) == policy, 'SKY130 isolation policy differs from the captured inputs.')
        if declared is not None:
            require(declared.get('top') == value['top'], 'SKY130 isolation evidence belongs to another design.')
    if policy is None and declared is None and not present:
        return None
    valid_policy(policy)
    require(isinstance(declared, dict) and data.get('platform', {}).get('name') == 'sky130hd',
            'Missing SKY130 isolation declaration or platform.')
    def read(key):
        require(key in files, 'Missing SKY130 isolation artifact: '+str(key))
        item = files[key]; path = (root/item['path']).resolve()
        require(path.is_relative_to(root) and path.is_file() and file_digest(path) == item['sha256'],
                'Changed SKY130 isolation artifact: '+key)
        return path
    report = json.loads(read('sky130_isolation').read_bytes())
    require(report == declared, 'SKY130 isolation declaration differs from its report.')
    read('gds'); read('checkpoint')
    evaluate(report, files['gds']['sha256'], files['checkpoint']['sha256'], report.get('top'),
             data['platform']['fingerprint'], policy)
    expected = FILES | {'preparation.json': policy['preparation_sha256']}
    bindings = report.get('resources', {})
    require(bindings.keys() == expected.keys() and len(set(bindings.values())) == len(expected),
            'Incomplete SKY130 isolation resource evidence.')
    for name, sha in expected.items():
        key = bindings[name]
        require(key.startswith('sky130_isolation_resource_') and file_digest(read(key)) == sha,
                'Changed SKY130 isolation resource: '+name)
    raw = json.loads(read(report.get('raw_artifact')).read_bytes())
    require(raw == {k: v for k, v in report.items() if k not in ('resources', 'request_artifact', 'raw_artifact')},
            'SKY130 isolation measurements differ from the worker output.')
    request = json.loads(read(report.get('request_artifact')).read_bytes())
    require(all(request.get(key) == report[key] for key in
                ('policy', 'gds_sha256', 'checkpoint_sha256', 'top', 'platform_fingerprint')),
            'SKY130 isolation request differs from the accepted result.')
    return report
