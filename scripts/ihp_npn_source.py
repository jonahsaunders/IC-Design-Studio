"""Recover the pre-NPN default without rebinding existing IHP projects."""
from contextlib import contextmanager
import json, shutil, tempfile
from pathlib import Path
from icstudio.model import file_digest

ROOT=Path(__file__).resolve().parents[1]
BASE='f1bd520184204ce71add7b7b9bf640b7daae9987bd52230473d91141bc53859b'
PROMOTED='da58ba2de122d67d232ab20ca4fb353b70bdc68c00ef4279f9be7da640a68ae0'
REVISION='cfb96b74cf33877e'


@contextmanager
def previous_npn(source):
    source=Path(source).resolve()
    if file_digest(source/'package.json')!=PROMOTED:
        yield source
        return
    current=json.loads((source/'package.json').read_bytes())
    for name,expected in current['files'].items():
        path=(source/name).resolve()
        if not path.is_relative_to(source) or not path.is_file() or file_digest(path)!=expected:
            raise ValueError('Changed current IHP NPN asset: '+name)
    manifest=ROOT/'icstudio/assets/qualification/ihp-npn-default-base-v1/package.json'
    if file_digest(manifest)!=BASE:raise ValueError('Changed retained IHP pre-NPN manifest.')
    old=json.loads(manifest.read_bytes())
    with tempfile.TemporaryDirectory(prefix='icstudio-npn-base-') as temp:
        folder=Path(temp)
        for name,expected in {'package.json':BASE,**old['files']}.items():
            src=manifest if name=='package.json' else (source/name).resolve()
            if name!='package.json' and not src.is_relative_to(source):raise ValueError('Unsafe retained IHP asset path.')
            if file_digest(src)!=expected:raise ValueError('Previous IHP asset is unavailable: '+name)
            target=folder/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,target)
            if file_digest(target)!=expected:raise ValueError('IHP asset changed during reconstruction: '+name)
        yield folder
