"""Recover the exact pre-tap package without rebinding saved projects."""
from contextlib import contextmanager
from functools import wraps
import json,shutil,tempfile
from pathlib import Path
from icstudio.model import file_digest
ROOT=Path(__file__).resolve().parents[1]
BASE='ba1fbda134f02ad703126527993fa5d01c5d3afcc71161afc35c065d3df227ab'
PROMOTED='f1bd520184204ce71add7b7b9bf640b7daae9987bd52230473d91141bc53859b'
REVISION='c0a32344f73be40d'


@contextmanager
def previous_taps(source):
    source=Path(source).resolve()
    from scripts.ihp_npn_source import PROMOTED as NPN_DEFAULT,previous_npn
    if file_digest(source/'package.json')==NPN_DEFAULT:
        with previous_npn(source) as old:
            with previous_taps(old) as original:yield original
        return
    if file_digest(source/'package.json')!=PROMOTED:
        yield source
        return
    current=json.loads((source/'package.json').read_bytes())
    for name,h in current['files'].items():
        p=(source/name).resolve()
        if not p.is_relative_to(source) or not p.is_file() or file_digest(p)!=h:raise ValueError('Changed current IHP tap asset: '+name)
    manifest=ROOT/'icstudio/assets/qualification/ihp-tap-base-v1/package.json'
    if file_digest(manifest)!=BASE:raise ValueError('Changed retained IHP tap base manifest.')
    old=json.loads(manifest.read_bytes())
    with tempfile.TemporaryDirectory(prefix='icstudio-tap-base-') as tmp:
        folder=Path(tmp)
        for name,h in {'package.json':BASE,**old['files']}.items():
            src=manifest if name=='package.json' else (source/name).resolve()
            if name!='package.json' and not src.is_relative_to(source):raise ValueError('Unsafe IHP tap base asset path.')
            if file_digest(src)!=h:raise ValueError('Retained IHP tap source changed: '+name)
            dest=folder/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
            if file_digest(dest)!=h:raise ValueError('IHP tap source changed during copy: '+name)
        yield folder


def base_input(prepare):
    @wraps(prepare)
    def wrapped(source,output):
        if Path(output).exists():raise ValueError('Choose a new IHP tap package directory.')
        with previous_taps(source) as old:return prepare(old,output)
    return wrapped
