"""Recover the exact pre-alternative manifests for reproducible old recipes."""
from contextlib import contextmanager
from functools import wraps
import json,shutil,tempfile
from pathlib import Path
from icstudio.model import file_digest
ROOT=Path(__file__).resolve().parents[1]
PROMOTED={
    'sky130A':'44b2626b09d983b06e65bfb620ec372633811643ebdb71f1e3319dca2656f9d0',
    'gf180mcuC':'6a3261b805a335644279b0e4e38e84166eb0840a0771dff8aff2f162c7f65f9f',
    'gf180mcuD':'a0a6fea3d56d49b318c415b12928297900f66c34acbd1aa9d8d0746f6f4fc444',
}


@contextmanager
def base_models(source):
    from scripts.sky130_li_source import previous_li
    with previous_li(source) as old:
        with _base_models(old) as base:yield base


@contextmanager
def _base_models(source):
    from scripts.prepare_alternate_models import BASE
    source=Path(source).resolve();h=file_digest(source/'package.json')
    target=next((t for t,v in PROMOTED.items() if h==v),None)
    if target is None:
        yield source
        return
    current=json.loads((source/'package.json').read_bytes())
    for rel,expected in current['files'].items():
        p=(source/rel).resolve()
        if not p.is_relative_to(source) or file_digest(p)!=expected:raise ValueError('Changed current alternate-model asset: '+rel)
    manifest=ROOT/'icstudio/assets/qualification/alternate-base-v1'/target/'package.json'
    if file_digest(manifest)!=BASE[target]:raise ValueError('Changed retained alternate base manifest.')
    old=json.loads(manifest.read_bytes())
    with tempfile.TemporaryDirectory(prefix='icstudio-alternate-base-') as tmp:
        dest=Path(tmp)
        for rel,expected in {'package.json':BASE[target],**old['files']}.items():
            src=manifest if rel=='package.json' else (source/rel).resolve()
            if rel!='package.json' and not src.is_relative_to(source):raise ValueError('Unsafe retained asset path.')
            if file_digest(src)!=expected:raise ValueError('Retained alternate asset changed: '+rel)
            out=dest/rel;out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,out)
            if file_digest(out)!=expected:raise ValueError('Retained alternate copy changed: '+rel)
        yield dest


def base_input(prepare):
    @wraps(prepare)
    def wrapped(source,output):
        if Path(output).exists():raise ValueError('Choose a new package directory; the output already exists.')
        with base_models(source) as original:return prepare(original,output)
    return wrapped
