"""Capture the reviewed SKY130 isolation checker and an explicit default mode."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.digital_platform import inventory, verify
from icstudio.digital_sky130_isolation_lock import FILES, RECIPE, REVISION
from icstudio.model import atomic_write, clone, digest, file_digest


def payload(bundle=None):
    captured = {}
    with zipfile.ZipFile(bundle or ROOT/'tests/fixtures/sky130-filled-references-v1.zip') as archive:
        names = archive.namelist()
        for name, expected in FILES.items():
            if name.startswith('sources/'):
                if names.count(name) != 1 or archive.getinfo(name).file_size > 16*1024*1024:
                    raise ValueError('Missing, duplicate or oversized SKY130 isolation source: '+name)
                data = archive.read(name)
            elif name == 'helpers/scripts/__init__.py':
                data = b''
            else:
                data = (ROOT/name.removeprefix('helpers/')).read_bytes()
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError('Changed pinned SKY130 isolation resource: '+name)
            captured[name] = data
    return captured


def prepare(platform, output, *, nfet_in_dnwell, bundle=None):
    verify(platform)
    if platform['name'] != 'sky130hd' or platform.get('sky130_isolation') or type(nfet_in_dnwell) is not bool:
        raise ValueError('Attach isolation checking once to SKY130 HD with an explicit Boolean mode.')
    base = Path(platform['root']).resolve(); output = Path(output).resolve()
    if output == base or not output.is_relative_to(base) or output.exists():
        raise ValueError('Use a new SKY130 isolation directory inside the platform.')
    captured = payload(bundle)
    relative = output.relative_to(base).as_posix()
    original = [row['path'] for row in platform['files']]
    added = [relative+'/'+name for name in [*captured, 'preparation.json']]
    if set(added) & set(original):
        raise ValueError('SKY130 isolation resources overlap the platform capture.')
    for name, data in captured.items():
        path = output/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
    record = dict(schema=1, recipe=RECIPE, revision=REVISION, qualified=False,
                  files=inventory(output, sorted(captured)))
    atomic_write(output/'preparation.json', json.dumps(record, indent=2)+'\n')
    result = clone(platform); result['files'] = inventory(base, original+added)
    result['fingerprint'] = digest(result['files'])
    result['sky130_isolation'] = dict(recipe=RECIPE, directory=relative, nfet_in_dnwell=nfet_in_dnwell,
                                    preparation_sha256=file_digest(output/'preparation.json'))
    verify(result)
    return result
