"""Retain exact earlier GF180 manifests when adding public high-voltage models."""
from contextlib import contextmanager
from pathlib import Path
import json,shutil,tempfile
from icstudio.model import file_digest
ROOT=Path(__file__).resolve().parents[1]
BASE={'gf180mcuC':'6a3261b805a335644279b0e4e38e84166eb0840a0771dff8aff2f162c7f65f9f',
      'gf180mcuD':'a0a6fea3d56d49b318c415b12928297900f66c34acbd1aa9d8d0746f6f4fc444'}
PROMOTED={'gf180mcuC':'abfbf8702d759247ad77075c72c7b042a6f9b89d2629f5c194a925a0d4f6194c',
          'gf180mcuD':'d46a592f236f5a42356db52e861b17f1412ec826cd19a73452f1aa3a50a1e6ae'}
REVISIONS={'gf180mcuC':'b661a751abfc662a','gf180mcuD':'2f92b1f05da58bd7'}
RETAINED=ROOT/'icstudio/assets/qualification/gf180-hv-base-v1'


@contextmanager
def previous_hv(source):
    source=Path(source).resolve();h=file_digest(source/'package.json')
    target=next((t for t,v in PROMOTED.items() if h==v),None)
    if target is None:
        yield source
        return
    current=json.loads((source/'package.json').read_bytes())
    for rel,expected in current['files'].items():
        p=(source/rel).resolve()
        if not p.is_relative_to(source) or not p.is_file() or file_digest(p)!=expected:
            raise ValueError('Changed current GF180 high-voltage asset: '+rel)
    manifest=RETAINED/target/'package.json'
    if file_digest(manifest)!=BASE[target]:raise ValueError('Changed retained GF180 high-voltage base manifest.')
    old=json.loads(manifest.read_bytes())
    with tempfile.TemporaryDirectory(prefix='icstudio-hv-base-') as tmp:
        dest=Path(tmp)
        for rel,expected in {'package.json':BASE[target],**old['files']}.items():
            src=manifest if rel=='package.json' else (source/rel).resolve()
            if rel!='package.json' and not src.is_relative_to(source):raise ValueError('Unsafe retained GF180 asset path.')
            if file_digest(src)!=expected:raise ValueError('Changed retained GF180 asset: '+rel)
            p=dest/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,p)
            if file_digest(p)!=expected:raise ValueError('GF180 source changed during copy: '+rel)
        yield dest
