"""Recover the exact original package for reproducible correction comparisons.

Only the old manifest and replaced assets are duplicated. All remaining assets
must match its original hashes. This never rewrites the installed source.
"""
from contextlib import contextmanager
import json,shutil,tempfile
from pathlib import Path
from icstudio.model import file_digest

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'icstudio/assets/qualification/sky130-base-v1'
BASE_REVISION='b1f441fabee1ed85'
BASE_MANIFEST='6bbaae721ea855822a993017174bafbf272a22d696c58fe393bee81b2ff19d5c'
DEFAULT_MANIFEST='177e57626c06cb5d103aab04c4bc82983bc4ba96f2e08e4bc04006ade6cd8e2d'


@contextmanager
def original_package(source):
    source=Path(source).resolve()
    manifest=json.loads((source/'package.json').read_bytes())
    if manifest.get('revision')==BASE_REVISION:
        yield source
        return
    if file_digest(source/'package.json')!=DEFAULT_MANIFEST:
        raise ValueError('Use the reviewed original or included SKY130 package.')
    for rel,h in manifest['files'].items():
        path=(source/rel).resolve()
        if not path.is_relative_to(source) or file_digest(path)!=h:
            raise ValueError('Changed current SKY130 asset: '+rel)
    if file_digest(BASE/'package.json')!=BASE_MANIFEST:
        raise ValueError('Changed original SKY130 manifest.')
    original=json.loads((BASE/'package.json').read_bytes())
    with tempfile.TemporaryDirectory(prefix='icstudio-sky130-original-') as tmp:
        target=Path(tmp)
        for rel,h in {'package.json':BASE_MANIFEST,**original['files']}.items():
            src=BASE/rel if (BASE/rel).is_file() else source/rel
            if file_digest(src)!=h:raise ValueError('Original SKY130 source is unavailable: '+rel)
            dest=target/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
            if file_digest(dest)!=h:raise ValueError('Original SKY130 asset changed during copy: '+rel)
        yield target
