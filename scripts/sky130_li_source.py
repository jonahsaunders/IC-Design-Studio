"""Reconstruct the pre-LI manifest without changing saved project identities."""
from contextlib import contextmanager
from functools import wraps
import json,shutil,tempfile
from pathlib import Path
from icstudio.model import file_digest
ROOT=Path(__file__).resolve().parents[1]
BASE='44b2626b09d983b06e65bfb620ec372633811643ebdb71f1e3319dca2656f9d0'
PROMOTED='42cafd2b1407783d361cfbb276abe3ba9e97b2c06a716af6c9069c8426852413'
REVISION='1901822ae8f81ae1'


@contextmanager
def previous_li(source):
    from scripts.sky130_mim_source import previous_mim
    with previous_mim(source) as old:
        with _previous_li(old) as base:yield base


@contextmanager
def _previous_li(source):
    source=Path(source).resolve()
    if file_digest(source/'package.json')!=PROMOTED:
        yield source
        return
    current=json.loads((source/'package.json').read_bytes())
    for name,h in current['files'].items():
        p=(source/name).resolve()
        if not p.is_relative_to(source) or not p.is_file() or file_digest(p)!=h:raise ValueError('Changed current SKY130 LI asset: '+name)
    manifest=ROOT/'icstudio/assets/qualification/sky130-li-base-v1/package.json'
    if file_digest(manifest)!=BASE:raise ValueError('Changed retained SKY130 LI base manifest.')
    old=json.loads(manifest.read_bytes())
    with tempfile.TemporaryDirectory(prefix='icstudio-li-base-') as tmp:
        folder=Path(tmp)
        for name,h in {'package.json':BASE,**old['files']}.items():
            src=manifest if name=='package.json' else (source/name).resolve()
            if name!='package.json' and not src.is_relative_to(source):raise ValueError('Unsafe LI base asset path.')
            if file_digest(src)!=h:raise ValueError('Retained LI source asset changed: '+name)
            dest=folder/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
            if file_digest(dest)!=h:raise ValueError('LI source changed during copy: '+name)
        yield folder


def base_input(prepare):
    @wraps(prepare)
    def wrapped(source,output):
        if Path(output).exists():raise ValueError('Choose a new SKY130 LI package directory.')
        with previous_li(source) as old:return prepare(old,output)
    return wrapped
