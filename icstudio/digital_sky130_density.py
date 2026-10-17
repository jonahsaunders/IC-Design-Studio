"""Mandatory public-window density evidence, independent of fill generation.

This project acceptance policy uses the two existing public growth profiles.
It does not supply missing foundry definitions or qualify clipped boundaries.
"""
import json
from pathlib import Path
import shutil

from . import digital_sky130_oxide_density as oxide
from .model import file_digest

ASSETS = Path(__file__).parent/'assets/verification/sky130/density'
ASSET_HASHES = {
    'LICENSE': 'c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4',
    'met_density_tiled.drc': oxide.SOURCE['sha256'],
    'source-lock.json': '6be44a472f40c7d17e6e4bd226ca77e54b37b85a84ec32ea3574188bd52fb7ee',
}
POLICY = dict(recipe='sky130-mandatory-public-density-v1', source=oxide.SOURCE,
    window_nm=oxide.WINDOW_NM, step_nm=oxide.STEP_NM,
    minimum_percent=oxide.MINIMUM_PERCENT, growth_nm=oxide.PROFILES, assets=ASSET_HASHES)
SCOPE = ('Mandatory project density policy for every new SKY130 HD Finish, independent of the '
    'fill-generation setting. Both retained public growth profiles must pass every full 700 um '
    'window, stepped 70 um from independently captured layout bounds. Clipped observations are '
    'diagnostic. A block without full windows requires surrounding layout and receives no density '
    'acceptance. These public profiles do not establish foundry applicability, final-mask density, '
    'metal-5 density, complete-chip boundaries or complete physical qualification.')


def require(condition, message):
    if not condition: raise ValueError('SKY130 density: '+message)


def resources():
    for name, digest in ASSET_HASHES.items():
        require((ASSETS/name).is_file() and file_digest(ASSETS/name) == digest,
                'missing or changed source: '+name)
    return ASSETS


def report_for(observation, inputs, top):
    oxide.evaluate(observation, inputs['gds'], top)
    require(observation['measurements']['bounds_nm'] is not None,
            'independent implementation bounds are required')
    failures = sum(x['full_window_findings'] for x in observation['summaries'].values())
    status = ('FAIL' if failures else 'sampled-full-windows-pass' if observation['full_windows']
              else 'surrounding-layout-required')
    return dict(schema=1, policy=POLICY, scope=SCOPE, qualified=False,
        acceptance_established=False, top=top, inputs=inputs, status=status,
        full_windows=observation['full_windows'], full_window_findings=failures,
        observation=observation)


def execute(r):
    if r.platform['name'] != 'sky130hd': return None
    folder = r.root/'sky130-density'; folder.mkdir()
    for name in ASSET_HASHES:
        shutil.copyfile(resources()/name, folder/name)
        r.add_artifact('sky130_density_'+name.replace('.', '_'), folder/name)
    inputs = {}
    for key in ('gds', 'checkpoint', 'sky130_pin_inventory'):
        require(key in r.artifacts, 'missing input: '+key)
        inputs[key] = r.artifacts[key]['sha256']
        require(file_digest(r.root/r.artifacts[key]['path']) == inputs[key], 'changed input: '+key)
    from .digital_sky130_rules import density_bounds
    bounds = density_bounds(r.artifacts, r.root, r.config['top'], inputs['checkpoint'])
    require(bounds is not None, 'independent implementation bounds are required')
    observation = oxide.audit(r.root/r.artifacts['gds']['path'], bounds)
    report = report_for(observation, inputs, r.config['top'])
    # Preserve failed measurements too, before stopping Finish.
    r.save_json('sky130_density', report, 'sky130-density/report.json')
    require(report['status'] != 'FAIL',
            'a full public density window is below 80%; inspect sky130-density/report.json')
    return report


def validate_saved(data, root):
    root = Path(root).resolve(); files = data['artifacts']
    policy = data.get('environment', {}).get('sky130_density')
    declared = data.get('physical', {}).get('sky130_density')
    present = any(k == 'sky130_density' or k.startswith('sky130_density_') for k in files)
    if (root/'input.json').is_file():
        captured = json.loads((root/'input.json').read_bytes()).get('environment', {})
        require(captured.get('sky130_density') == policy, 'policy differs from captured inputs')
    if policy is None and declared is None and not present: return None
    require(policy == POLICY and data.get('platform', {}).get('name') == 'sky130hd',
            'missing or changed mandatory policy')
    def read(key):
        require(key in files, 'missing artifact: '+key)
        item = files[key]; path = (root/item['path']).resolve()
        require(path.is_relative_to(root) and path.is_file() and file_digest(path) == item['sha256'],
                'missing or changed artifact: '+key)
        return path
    for name, digest in ASSET_HASHES.items():
        require(file_digest(read('sky130_density_'+name.replace('.', '_'))) == digest,
                'changed retained public source: '+name)
    inputs = {key: file_digest(read(key)) for key in ('gds', 'checkpoint', 'sky130_pin_inventory')}
    from .digital_sky130_rules import density_bounds
    top = declared.get('top') if isinstance(declared, dict) else None
    bounds = density_bounds(files, root, top, inputs['checkpoint'])
    require(bounds is not None, 'independent implementation bounds are required')
    actual = oxide.audit(read('gds'), bounds)
    expected = report_for(actual, inputs, top)
    saved = json.loads(read('sky130_density').read_bytes())
    require(saved == declared == expected, 'saved evidence differs from the actual layout or policy')
    require(expected['status'] != 'FAIL', 'failed full public density windows prevent export')
    return expected
