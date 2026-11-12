"""Stage the complete, source-locked public IHP checker bundles for release."""
from pathlib import Path
import os
import shutil

from icstudio import ihp_klayout_drc, ihp_klayout_lvs
from icstudio.digital_backend import stage_backend
from icstudio.model import file_digest

LVS_README_SHA256 = '8af59f21bc61f2d9e1ff6a9c06d5ab5830d0c15afaea3bd14df89e482795c2ec'


def _inventory(root, expected):
    files = {Path(name) for name in expected}
    dirs = {parent for path in files for parent in path.parents if parent != Path('.')}
    result = set()
    def visit(relative):
        with os.scandir(root / relative) as entries:
            for entry in entries:
                child = relative / entry.name
                if child not in files and child not in dirs:
                    raise ValueError('Unexpected IHP package dependency name.')
                if entry.is_symlink() or (hasattr(os.path, 'isjunction') and os.path.isjunction(entry.path)):
                    raise ValueError('Linked IHP package dependency.')
                if child in dirs:
                    if not entry.is_dir(follow_symlinks=False):
                        raise ValueError('Invalid IHP package dependency directory.')
                    visit(child)
                elif entry.is_file(follow_symlinks=False):
                    result.add(child.as_posix())
                else:
                    raise ValueError('Invalid IHP package dependency file.')
    visit(Path('.'))
    return result


def stage(source, destination):
    """Stage the native backend and both licensed checker source inventories."""
    destination = Path(destination)
    # Validate both locked inventories before creating a release backend.
    lvs = ihp_klayout_lvs.assets()
    drc = ihp_klayout_drc.assets()
    readme = ihp_klayout_lvs.SOURCE / 'README.md'
    if readme.is_symlink() or not readme.is_file() or file_digest(readme) != LVS_README_SHA256:
        raise ValueError('Missing or changed IHP LVS bundle README.')
    lvs = {name: (path, file_digest(path)) for name, path in lvs.items()}
    drc = {name: (path, file_digest(path)) for name, path in drc.items()}
    lvs['README.md'] = (readme, LVS_README_SHA256)
    stage_backend(source, destination)
    base = destination / 'assets/physical'
    ihp_klayout_lvs.copy_assets(base / 'ihp_klayout_lvs')
    ihp_klayout_drc.copy_assets(base / 'ihp_klayout_drc')
    shutil.copyfile(readme, base / 'ihp_klayout_lvs/README.md')
    for bundle, expected in (('ihp_klayout_lvs', lvs), ('ihp_klayout_drc', drc)):
        output = base / bundle
        if _inventory(output, expected) != set(expected):
            raise ValueError('IHP package dependency inventory changed: ' + bundle)
        for name, (path, want) in expected.items():
            if file_digest(path) != want or file_digest(output / name) != want:
                raise ValueError('IHP package dependency changed: ' + name)
