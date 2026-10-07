"""Versioned implementation recipes derived from unchanged, captured PDK files."""
from pathlib import Path

from .model import atomic_write, file_digest

GF180_C = 'gf180-9t-5lm-9k-geometry-v1'
GF180_VARIABLES = {'TRACK_OPTION': '9t', 'METAL_OPTION': '5LM_1TM', 'KVALUE': '9', 'POWER_OPTION': '5v0'}
PATCHES = (
    {'variable': 'PDN_TCL', 'name': 'pdn', 'path': 'openROAD/pdn/pdn_grid_strategy_9t_6M.cfg',
     'before': '-split_cuts {Metal3 0.128}', 'after': '-split_cuts {Metal3 0.520}',
     'source_sha256': '92f6fdbd12e900f95e159a146fbeae4d99d419ee778c158233a82946577ee0c1',
     'result_sha256': '78971b000b024eca49e18456f68ac63d510c05245a5ad752b633ac051f882b10'},
    {'variable': 'TAPCELL_TCL', 'name': 'tapcell', 'path': 'openROAD/tapcell.tcl',
     'before': '-distance 100', 'after': '-distance 14',
     'source_sha256': 'df82d8f3904bc6de86e441be3766b9b6e8d9a7a22d1e9219faa9244d9b830638',
     'result_sha256': 'a327a990e6543beae316ed6df1bfd6ab3533b7170ea5797ec020396af097e7d3'},
)


def validate(platform):
    recipe = platform.get('orfs', {}).get('geometry_recipe')
    if recipe is None:
        return
    if (recipe != GF180_C or platform['name'] != 'gf180'
            or platform.get('orfs', {}).get('variables') != GF180_VARIABLES):
        raise ValueError('The selected geometry recipe requires GF180-C 9t / 5LM / 9K / 5 V.')
    prefix = platform.get('directory', '.')
    records = {r['path']: r for r in platform.get('files', [])}
    for patch in PATCHES:
        name = patch['path'] if prefix == '.' else prefix + '/' + patch['path']
        if records.get(name, {}).get('sha256') not in (patch['source_sha256'], patch['result_sha256']):
            raise ValueError('The GF180 geometry recipe requires its pinned source file: ' + name +
                             '. Import a matching platform or use an explicitly defined custom manifest.')


def generate(r, settings):
    """Return make overrides; original platform files and their locks stay intact."""
    recipe = r.platform.get('orfs', {}).get('geometry_recipe')
    if recipe is None:
        return []
    validate(r.platform)
    root = (r.root / 'platform').resolve()
    directory = root / r.platform.get('directory', '.')
    records = {r['path']: r for r in r.platform['files']}
    changes = []; options = []
    for patch in PATCHES:
        source = (directory / patch['path']).resolve()
        if not source.is_relative_to(root):
            raise ValueError('A geometry recipe source escapes the captured platform.')
        relative = source.relative_to(root).as_posix()
        source_hash = file_digest(source)
        if source_hash != records[relative]['sha256']:
            raise ValueError('A captured geometry recipe source changed: ' + relative)
        item = {'variable': patch['variable'], 'source': relative, 'source_sha256': source_hash}
        if patch['variable'] == 'PDN_TCL' and settings.get('pdn_tcl', '').strip():
            item.update(status='user_override', artifact='pdn_tcl')
        else:
            text = source.read_text(encoding='utf-8')
            if source_hash == patch['source_sha256']:
                if text.count(patch['before']) != 1:
                    raise ValueError('The pinned geometry replacement is not unique: ' + relative)
                text = text.replace(patch['before'], patch['after'])
            path = r.root / ('platform_' + patch['name'] + '.tcl')
            atomic_write(path, text)
            if file_digest(path) != patch['result_sha256']:
                raise ValueError('The generated geometry recipe differs from its reviewed content.')
            key = 'platform_recipe_' + patch['name']
            r.add_artifact(key, path)
            item.update(status='generated', artifact=key, result_sha256=file_digest(path),
                        before=patch['before'], after=patch['after'])
            options.append(patch['variable'] + '=' + str(path))
        changes.append(item)
    r.save_json('platform_geometry_recipe', {'schema': 1, 'recipe': recipe,
        'scope': 'Captured implementation defaults; final-layout rule and design qualification are separate.',
        'changes': changes}, 'platform_geometry_recipe.json')
    return options
