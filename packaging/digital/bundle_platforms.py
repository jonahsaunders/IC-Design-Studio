"""Capture all shipped digital platforms before pruning the build checkout."""
import json
from pathlib import Path
import shutil
import tempfile

from icstudio.digital_platform import BUNDLED_PLATFORMS, from_orfs, inventory, pin_flow, read_manifest, verify
from icstudio.model import digest
from scripts.prepare_sky130_digital import prepare


def bundle(root, *, sky130_cache=None):
    root=Path(root).resolve();orfs=root/'orfs';platform_root=orfs/'flow/platforms'
    platforms={name:from_orfs(orfs,name) for name in BUNDLED_PLATFORMS}
    flow=pin_flow(orfs)
    # Prepare against the complete upstream checkout while linked sibling
    # collateral is still present. Only then replace the packaged SKY130 views.
    with tempfile.TemporaryDirectory(prefix='.sky130-corners-',dir=root) as temporary:
        staging=Path(temporary)
        path=prepare(orfs,staging/'platform',sky130_cache or staging/'cache')
        sky130=read_manifest(path)
        for link in (platform_root/'sky130hd').rglob('*'):
            if link.is_symlink():
                target=link.resolve()
                if not target.is_relative_to(platform_root) or not target.is_file():
                    raise ValueError('Invalid platform link: '+str(link))
                content=link.read_bytes();link.unlink();link.write_bytes(content)
        shutil.copytree(Path(sky130['root'])/'sky130hd',platform_root/'sky130hd',dirs_exist_ok=True)
        sky130['root']=str(platform_root);verify(sky130)
        platforms['sky130hd']=sky130
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
        verify(platform)
        notices=platform_root/platform['name']/'redistribution';notices.mkdir()
        for name in ('Apache-2.0.txt','THIRD_PARTY_NOTICES.md'):
            shutil.copy2(root/'licenses'/name,notices/('LICENSE-'+name if name.endswith('.txt') else name))
        shutil.copy2(orfs/'LICENSE_BUILD_RUN_SCRIPTS',notices/'LICENSE-ORFS-build-scripts.txt')
        (notices/'upstream-lock.json').write_text(json.dumps({
            'repository':'https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts',
            'revision':platform['revision'],'original_platform_fingerprint':platform['fingerprint'],
            'scope':'Captured platform provenance before adding redistribution notices; additional PVT sources retain their own upstream locks.'},indent=2)+'\n')
        paths=[f['path'] for f in platform['files']]+[p.relative_to(platform_root).as_posix() for p in notices.iterdir()]
        platform['files']=inventory(platform_root,paths);platform['fingerprint']=digest(platform['files'])
        verify(platform);platform['root']='opt/icstudio/orfs/flow/platforms'
    flow['root']='opt/icstudio/orfs/flow'
    catalog={'schema':1,'default':'sky130hd','platforms':platforms}
    (root/'platforms.json').write_text(json.dumps(catalog,indent=2))
    # Older consumers can still read the default manifest from the same payload.
    (root/'platform.json').write_text(json.dumps(platforms[catalog['default']],indent=2))
    (root/'flow.json').write_text(json.dumps(flow,indent=2))
    return catalog
