"""Recover the exact pre-MiM mapping package for saved and historical inputs."""
from contextlib import contextmanager
import json
from pathlib import Path
import shutil
import tempfile
from icstudio.model import file_digest

ROOT = Path(__file__).resolve().parents[1]
BASE = '42cafd2b1407783d361cfbb276abe3ba9e97b2c06a716af6c9069c8426852413'
PROMOTED = '9b328d315f7e48ca67c7a11450f74618c4026b8758fb553120acba0d698182db'
REVISION = '857acac277f431b3'


@contextmanager
def previous_mim(source):
    source = Path(source).resolve()
    if file_digest(source/'package.json') != PROMOTED:
        yield source
        return
    current = json.loads((source/'package.json').read_bytes())
    for name, expected in current['files'].items():
        path = (source/name).resolve()
        if not path.is_relative_to(source) or not path.is_file() or file_digest(path) != expected:
            raise ValueError('Changed current SKY130 MiM asset: ' + name)
    manifest = ROOT/'icstudio/assets/qualification/sky130-mim-base-v1/package.json'
    if file_digest(manifest) != BASE:
        raise ValueError('Changed retained SKY130 pre-MiM manifest.')
    old = json.loads(manifest.read_bytes())
    with tempfile.TemporaryDirectory(prefix='icstudio-mim-base-') as tmp:
        folder = Path(tmp)
        for name, expected in {'package.json':BASE, **old['files']}.items():
            src = manifest if name == 'package.json' else (source/name).resolve()
            if name != 'package.json' and not src.is_relative_to(source):
                raise ValueError('Unsafe retained SKY130 asset path.')
            if file_digest(src) != expected:
                raise ValueError('Previous SKY130 asset is unavailable: ' + name)
            dest = folder/name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            if file_digest(dest) != expected:
                raise ValueError('SKY130 asset changed during reconstruction: ' + name)
        yield folder
