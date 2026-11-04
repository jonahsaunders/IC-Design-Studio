"""Recover the exact reviewed 5dda package from the explicit pw2dn candidate."""
from contextlib import contextmanager
import json,shutil,tempfile
from pathlib import Path
from icstudio.model import file_digest
from scripts.verify_frozen_mim import unlinked

ROOT=Path(__file__).resolve().parents[1]
BASE='125cde7c313ee18a05a7ec5c280d514b99aea521d6b39476e44f486ae494153b'
CURRENT='0c19e0ea5718a841045b597022d13f2dcb57e35cf8be9757b254fb465f2a35c4'
REVISION='47dbd4fe43bfa7e4'
PREDECESSOR=ROOT/'icstudio/assets/qualification/sky130-pw2dn-predecessor-v1/package.json'

def checked(root):
    root=unlinked(root).resolve();manifest=unlinked(root/'package.json')
    sha=file_digest(manifest);current=json.loads(manifest.read_bytes())
    if sha not in (BASE,CURRENT):raise ValueError('Expected exact reviewed SKY130 package.')
    for name,expected in current['files'].items():
        path=unlinked(root/name).resolve()
        if not path.is_relative_to(root) or file_digest(path)!=expected:
            raise ValueError('Changed current asset: '+name)
    return root,sha,current

@contextmanager
def predecessor(source,manifest=None):
    source,sha,current=checked(source)
    if manifest is not None and file_digest(unlinked(manifest))!=BASE:
        raise ValueError('Wrong predecessor manifest identity.')
    if sha==BASE:
        yield source
        return
    manifest=unlinked(manifest or PREDECESSOR).resolve()
    if file_digest(manifest)!=BASE:raise ValueError('Wrong predecessor manifest identity.')
    old=json.loads(manifest.read_bytes())
    with tempfile.TemporaryDirectory(prefix='pw2dn-predecessor-') as tmp:
        out=Path(tmp)
        for name,expected in old['files'].items():
            path=unlinked(source/name).resolve()
            if not path.is_relative_to(source) or current['files'].get(name)!=expected or file_digest(path)!=expected:
                raise ValueError('Changed predecessor asset: '+name)
            dest=out/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest)
            if file_digest(dest)!=expected:raise ValueError('Changed predecessor copy: '+name)
        shutil.copyfile(manifest,out/'package.json')
        if file_digest(out/'package.json')!=BASE:raise ValueError('Changed predecessor manifest copy.')
        yield out
