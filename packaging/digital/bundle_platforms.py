"""Capture all shipped digital platforms before pruning the build checkout."""
import json
from pathlib import Path
import shutil

from icstudio.digital_platform import BUNDLED_PLATFORMS, from_orfs, pin_flow, verify


def bundle(root):
    root=Path(root).resolve();orfs=root/'orfs';platform_root=orfs/'flow/platforms'
    platforms={name:from_orfs(orfs,name) for name in BUNDLED_PLATFORMS}
    flow=pin_flow(orfs)
    # Materialize linked collateral while all sibling platforms are present.
    # The content locks remain unchanged and are verified after pruning.
    for name in platforms:
        for link in (platform_root/name).rglob('*'):
            if link.is_symlink():
                target=link.resolve()
                if not target.is_relative_to(platform_root) or not target.is_file():
                    raise ValueError('Invalid platform link: '+str(link))
                content=link.read_bytes();link.unlink();link.write_bytes(content)
    for directory in platform_root.iterdir():
        if directory.name not in platforms and directory.is_dir():
            if directory.is_symlink():directory.unlink()
            elif directory.resolve().is_relative_to(platform_root):shutil.rmtree(directory)
            else:raise ValueError('Platform directory escapes the build checkout.')
    for platform in platforms.values():
        verify(platform);platform['root']='opt/icstudio/orfs/flow/platforms'
    flow['root']='opt/icstudio/orfs/flow'
    catalog={'schema':1,'default':'sky130hd','platforms':platforms}
    (root/'platforms.json').write_text(json.dumps(catalog,indent=2))
    # Older consumers can still read the default manifest from the same payload.
    (root/'platform.json').write_text(json.dumps(platforms[catalog['default']],indent=2))
    (root/'flow.json').write_text(json.dumps(flow,indent=2))
    return catalog
