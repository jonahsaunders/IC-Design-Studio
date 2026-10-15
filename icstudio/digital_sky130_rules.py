"""Mandatory partial SKY130 geometry checks and preserved, bounded evidence."""
from collections import Counter
import json
from pathlib import Path
import sys

from .digital_sky130_rules_lock import FILES, PROFILES, ROWS, STATES, BINDINGS, RECIPE, REVISION, SOURCE_LOCK_SHA256
from .model import atomic_write, file_digest

SCOPE = ('Six reviewed drawn-mask geometry/connectivity profiles and the 601-row periphery ledger. '
         'This is partial coverage: native decks, full antenna, density, error-catalog reconciliation, '
         'device/body LVS and electrical acceptance remain separate. SKY130 signoff is not qualified.')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(platform):
    policy = platform.get('sky130_rules')
    if policy is None:
        return
    from .digital import relative_path
    require(platform.get('name') == 'sky130hd' and isinstance(policy, dict) and
            set(policy) == {'recipe', 'directory', 'preparation_sha256'} and policy['recipe'] == RECIPE,
            'Unsupported SKY130 rule policy.')
    directory = relative_path(policy['directory'], directory=True)
    locks = {row['path']: row['sha256'] for row in platform.get('files', [])}
    require(locks.get(directory+'/preparation.json') == policy['preparation_sha256'],
            'SKY130 rule preparation is not bound to the platform.')
    require(all(locks.get(directory+'/'+name) == expected for name, expected in FILES.items()),
            'A required SKY130 rule resource is missing or changed.')


def resources(directory, preparation_sha256):
    """Authenticate all captured code and sources before any helper import."""
    directory = Path(directory).resolve()
    def checked(name, expected):
        path = (directory/name).resolve()
        require(path.is_relative_to(directory) and path.is_file() and file_digest(path) == expected,
                'Missing or changed SKY130 rule resource: '+name)
        return path
    preparation = checked('preparation.json', preparation_sha256)
    record = json.loads(preparation.read_bytes())
    require(record.get('schema') == 1 and record.get('recipe') == RECIPE and
            record.get('revision') == REVISION and record.get('qualified') is False and
            len(record.get('files', [])) == len(FILES) and
            {r['path']: r['sha256'] for r in record['files']} == FILES,
            'Incomplete or unsupported SKY130 rule preparation.')
    result = {name: checked(name, expected) for name, expected in FILES.items()}
    require(all(type(row['bytes']) is int and row['bytes'] == result[row['path']].stat().st_size
                for row in record['files']), 'SKY130 resource sizes changed.')
    return result | {'preparation.json': preparation}


def evaluate(report, gds_sha256, checkpoint_sha256, top, fingerprint, policy):
    """Validate report coverage without executing code supplied by a saved job."""
    require(isinstance(report, dict) and report.get('schema') == 1 and
            report.get('recipe') == RECIPE and report.get('policy') == policy and
            report.get('scope') == SCOPE and report.get('qualified') is False and
            report.get('chunk_complete') is False and report.get('status') == 'reviewed-profiles-pass',
            'SKY130 reviewed-profile evidence is incomplete or failed.')
    require(report.get('gds_sha256') == gds_sha256 and report.get('checkpoint_sha256') == checkpoint_sha256 and
            report.get('top') == top and report.get('platform_fingerprint') == fingerprint,
            'SKY130 rule evidence belongs to another layout, checkpoint, platform or design.')
    profiles = report.get('profiles', {})
    require(isinstance(profiles, dict) and profiles.keys() == PROFILES.keys(), 'A mandatory SKY130 profile is missing.')
    for name, expected in PROFILES.items():
        value = profiles[name]; checks = value.get('checks', [])
        require(value.get('schema') == 1 and value.get('status') == 'PASS' and value.get('qualified') is False and
                value.get('top') == top and value.get('gds_sha256') == gds_sha256 and
                value.get('checker_sha256') == expected['sha256'] and type(value.get('violations')) is int and
                value['violations'] == 0 and len(checks) == len(expected['checks']) and
                {row['rule'] for row in checks} == set(expected['checks']) and
                all(type(row.get('violations')) is int and row['violations'] == 0 for row in checks),
                'Failed, duplicate, changed or incomplete SKY130 profile: '+name)
    require(profiles['global_geometry'].get('layer_map_sha256') ==
            FILES['helpers/docs/qualification/sky130-layer-purposes.json'], 'Changed SKY130 layer-purpose map.')
    ledger = report.get('ledger', {}); rows = ledger.get('rows', [])
    require(ledger.get('schema') == 1 and ledger.get('status') == 'partial-rule-execution-reviewed' and
            ledger.get('qualified') is False and ledger.get('chunk_complete') is False and
            ledger.get('source_revision') == REVISION and ledger.get('source_lock_sha256') == SOURCE_LOCK_SHA256 and
            ledger.get('checker_sha256') == FILES['helpers/scripts/sky130_rule_execution.py'] and
            ledger.get('applicability_checker_sha256') == FILES['helpers/scripts/sky130_block_applicability.py'] and
            ledger.get('gds_sha256') == gds_sha256 and ledger.get('top') == top and
            len(rows) == len(ROWS) and {row['id'] for row in rows} == ROWS.keys(),
            'Incomplete or changed SKY130 manual ledger.')
    require(all(ledger.get(name) == profiles[name] for name in PROFILES), 'SKY130 ledger profiles differ.')
    for row in rows:
        identity = ROWS[row['id']]; state = row.get('disposition')
        require(all(row.get(key) == value for key, value in identity.items()), 'Changed SKY130 source row.')
        require(state in {STATES[row['id']], 'execution-review-required'}, 'Unreviewed SKY130 disposition promotion.')
        if row['id'] in BINDINGS:
            require(state == 'executed-reviewed' and row.get('execution') == BINDINGS[row['id']],
                    'Missing or changed SKY130 execution binding.')
        else:
            require('execution' not in row, 'An unbound SKY130 requirement claims execution.')
        if state == 'absent-operand':
            witnesses = row.get('witnesses', {})
            require(witnesses and all(type(value) is int and value == 0 for value in witnesses.values()),
                    'SKY130 absent-operand evidence is missing or nonzero.')
    counts = dict(Counter(row['disposition'] for row in rows))
    require(ledger.get('counts') == counts and all(type(v) is int for v in ledger['counts'].values()),
            'SKY130 ledger counts differ from its rows.')
    require(report.get('coverage') == dict(rows=len(rows), counts=counts, complete=False),
            'SKY130 partial coverage changed.')
    from .digital_sky130_scope import validate as validate_scope
    validate_scope(ledger)
    from .digital_sky130_pad_scope import validate as validate_pad_scope
    validate_pad_scope(ledger)
    from .digital_sky130_catalog_context import evaluate as evaluate_catalog_context
    evaluate_catalog_context(report.get('catalog_context'), gds_sha256, top)
    from .digital_sky130_catalog_labels import evaluate as evaluate_catalog_labels
    evaluate_catalog_labels(report.get('catalog_labels'), gds_sha256, top)
    from .digital_sky130_vpp import evaluate as evaluate_vpp
    evaluate_vpp(report.get('vpp_geometry'), gds_sha256, top)
    from .digital_sky130_boundary_interactions import evaluate as evaluate_boundary_interactions
    evaluate_boundary_interactions(report.get('boundary_interactions'), gds_sha256, top)
    from .digital_sky130_selected_devices import evaluate as evaluate_selected_devices
    evaluate_selected_devices(report.get('selected_devices'), gds_sha256, top)
    from .digital_sky130_conservative_bounds import evaluate as evaluate_conservative_bounds
    evaluate_conservative_bounds(report.get('conservative_bounds'), gds_sha256, top)
    from .digital_sky130_device_roots import evaluate as evaluate_device_roots
    evaluate_device_roots(report.get('device_roots'), gds_sha256, top)
    from .digital_sky130_special_subjects import evaluate as evaluate_special_subjects
    evaluate_special_subjects(report.get('special_subjects'), gds_sha256, top)
    from .digital_sky130_selected_targets import evaluate as evaluate_selected_targets
    evaluate_selected_targets(report.get('selected_targets'), gds_sha256, top)
    from .digital_sky130_frame_bounds import evaluate as evaluate_frame_bounds
    evaluate_frame_bounds(report.get('frame_bounds'), gds_sha256, top)
    from .digital_sky130_well_bounds import evaluate as evaluate_well_bounds
    evaluate_well_bounds(report.get('well_bounds'), gds_sha256, top)
    from .digital_sky130_scribe_bounds import evaluate as evaluate_scribe_bounds
    evaluate_scribe_bounds(report.get('scribe_bounds'), gds_sha256, top)
    from .digital_sky130_seal_geometry import evaluate as evaluate_seal_geometry
    evaluate_seal_geometry(report.get('seal_geometry'), gds_sha256, top)
    return report


def execute(r):
    policy = r.platform.get('sky130_rules')
    if policy is None:
        return None
    validate(r.platform)
    paths = resources(r.root/'platform'/policy['directory'], policy['preparation_sha256'])
    folder = r.root/'sky130-rule-checks'; folder.mkdir()  # Never reuse stale worker output.
    original = {key: dict(r.artifacts[key]) for key in ('gds', 'checkpoint')}
    for key, record in original.items():
        require(file_digest(r.root/record['path']) == record['sha256'], 'Changed SKY130 '+key+'.')
    request = dict(resources=str(r.root/'platform'/policy['directory']), policy=policy,
                   gds=str(r.root/original['gds']['path']), gds_sha256=original['gds']['sha256'],
                   checkpoint=str(r.root/original['checkpoint']['path']), checkpoint_sha256=original['checkpoint']['sha256'],
                   top=r.config['top'], platform_fingerprint=r.platform['fingerprint'], output=str(folder/'verified'))
    atomic_write(folder/'request.json', json.dumps(request, indent=2)+'\n')
    bootstrap = 'import sys\nsys.dont_write_bytecode=True\nsys.path.insert(0,'+repr(str(Path(__file__).resolve().parents[1]))+')\n'
    bootstrap += 'import json\nfrom pathlib import Path\nfrom icstudio.digital_sky130_rule_worker import execute\nexecute(json.loads(Path(sys.argv[1]).read_bytes()))\n'
    atomic_write(folder/'run.py', bootstrap)
    try:
        r.command([sys.executable, str(folder/'run.py'), str(folder/'request.json')],
                  'Checking reviewed SKY130 physical rules', cwd=folder, fraction=.98)
    finally:
        # Preserve diagnostics on engine failure as well as successful runs.
        for index, path in enumerate(sorted(p for p in folder.rglob('*') if p.is_file())):
            r.add_artifact('sky130_rule_file_'+str(index), path, allow_empty=True)
    report = json.loads((folder/'verified/report.json').read_bytes())
    for key, record in original.items():
        require(file_digest(r.root/record['path']) == record['sha256'], 'SKY130 '+key+' changed during rule checking.')
    resources(request['resources'], policy['preparation_sha256'])
    evaluate(report, original['gds']['sha256'], original['checkpoint']['sha256'], r.config['top'],
             r.platform['fingerprint'], policy)
    report['resources'] = {}
    for index, (name, path) in enumerate(sorted(paths.items())):
        key = 'sky130_rule_resource_'+str(index); r.add_artifact(key, path, allow_empty=True)
        report['resources'][name] = key
    r.save_json('sky130_rules', report, 'sky130-rule-checks/accepted.json')
    return report


def validate_saved(data, root):
    files = data['artifacts']; policy = data.get('environment', {}).get('sky130_rules')
    declared = data.get('physical', {}).get('sky130_rules')
    present = 'sky130_rules' in files or any(name.startswith('sky130_rule_') for name in files)
    if policy is None and declared is None and not present:
        return None  # No claim for historical jobs or platforms without this policy.
    require(isinstance(policy, dict) and policy.get('recipe') == RECIPE and
            set(policy) == {'recipe', 'directory', 'preparation_sha256'} and
            isinstance(declared, dict) and 'sky130_rules' in files and data.get('platform', {}).get('name') == 'sky130hd',
            'Missing SKY130 rule policy, declaration or retained report.')
    root = Path(root).resolve()
    def read(key):
        require(key in files, 'Missing SKY130 evidence artifact: '+key)
        item = files[key]; path = (root/item['path']).resolve()
        require(path.is_relative_to(root) and path.is_file() and file_digest(path) == item['sha256'],
                'Missing or changed SKY130 evidence artifact: '+key)
        return path
    report = json.loads(read('sky130_rules').read_bytes())
    require(report == declared, 'SKY130 saved declaration differs from the report.')
    for name in ('gds', 'checkpoint'):
        read(name)
    evaluate(report, files['gds']['sha256'], files['checkpoint']['sha256'], report.get('top'),
             data['platform']['fingerprint'], policy)
    from .digital_sky130_catalog_context import validate_saved as validate_catalog_context
    validate_catalog_context(report['catalog_context'], read('gds'))
    from .digital_sky130_catalog_labels import validate_saved as validate_catalog_labels
    validate_catalog_labels(report['catalog_labels'], read('gds'))
    from .digital_sky130_vpp import validate_saved as validate_vpp
    validate_vpp(report['vpp_geometry'], read('gds'))
    from .digital_sky130_boundary_interactions import validate_saved as validate_boundary_interactions
    validate_boundary_interactions(report['boundary_interactions'], read('gds'))
    from .digital_sky130_selected_devices import validate_saved as validate_selected_devices
    validate_selected_devices(report['selected_devices'], read('gds'))
    from .digital_sky130_conservative_bounds import validate_saved as validate_conservative_bounds
    validate_conservative_bounds(report['conservative_bounds'], read('gds'))
    from .digital_sky130_device_roots import validate_saved as validate_device_roots
    validate_device_roots(report['device_roots'], read('gds'))
    from .digital_sky130_special_subjects import validate_saved as validate_special_subjects
    validate_special_subjects(report['special_subjects'], read('gds'))
    from .digital_sky130_selected_targets import validate_saved as validate_selected_targets
    validate_selected_targets(report['selected_targets'], read('gds'))
    from .digital_sky130_frame_bounds import validate_saved as validate_frame_bounds
    validate_frame_bounds(report['frame_bounds'], read('gds'))
    from .digital_sky130_well_bounds import validate_saved as validate_well_bounds
    validate_well_bounds(report['well_bounds'], read('gds'))
    from .digital_sky130_scribe_bounds import validate_saved as validate_scribe_bounds
    validate_scribe_bounds(report['scribe_bounds'], read('gds'))
    from .digital_sky130_seal_geometry import validate_saved as validate_seal_geometry
    validate_seal_geometry(report['seal_geometry'], read('gds'))
    bindings = report.get('resources', {})
    expected = FILES | {'preparation.json': policy['preparation_sha256']}
    require(bindings.keys() == expected.keys() and len(set(bindings.values())) == len(expected),
            'Incomplete SKY130 resource evidence.')
    for name, sha in expected.items():
        key = bindings[name]
        require(key.startswith('sky130_rule_resource_') and file_digest(read(key)) == sha,
                'Changed pinned SKY130 evidence resource: '+name)
    preparation = json.loads(read(bindings['preparation.json']).read_bytes())
    require(preparation.get('schema') == 1 and preparation.get('recipe') == RECIPE and
            preparation.get('qualified') is False and preparation.get('revision') == REVISION and
            len(preparation.get('files', [])) == len(FILES) and
            {r['path']: r['sha256'] for r in preparation['files']} == FILES,
            'Changed SKY130 saved preparation.')
    return report
