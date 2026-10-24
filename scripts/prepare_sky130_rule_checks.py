"""Capture the pinned, partial SKY130 geometry gate inside a digital platform."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.digital_platform import inventory, verify
from icstudio.digital_sky130_rules_lock import FILES, RECIPE, REVISION
from icstudio.model import atomic_write, clone, digest, file_digest


def payload(bundle=None):
    """Read only authenticated manual sources, never the bundled reference GDS."""
    bundle = Path(bundle or ROOT/'tests/fixtures/sky130-filled-references-v1.zip')
    captured = {}
    with zipfile.ZipFile(bundle) as archive:
        names = archive.namelist()
        for name, expected in FILES.items():
            if name.startswith('sources/'):
                if names.count(name) != 1:
                    raise ValueError('Missing or duplicate SKY130 source: '+name)
                item = archive.getinfo(name)
                if item.file_size > 16*1024*1024:
                    raise ValueError('Oversized SKY130 source: '+name)
                data = archive.read(item)
            elif name == 'helpers/scripts/__init__.py':
                data = b''
            else:
                data = (ROOT/name.removeprefix('helpers/')).read_bytes()
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError('Changed pinned SKY130 resource: '+name)
            captured[name] = data
    return captured


def prepare(platform, output, *, bundle=None):
    verify(platform)
    if platform['name'] != 'sky130hd' or platform.get('sky130_rules'):
        raise ValueError('Attach the reviewed rules once to a captured SKY130 HD platform.')
    base = Path(platform['root']).resolve(); output = Path(output).resolve()
    if output == base or not output.is_relative_to(base) or output.exists():
        raise ValueError('Use a new SKY130 rule directory inside the platform.')
    captured = payload(bundle)  # Authenticate everything before writing.
    relative = output.relative_to(base).as_posix()
    added = [relative+'/'+name for name in [*captured, 'preparation.json']]
    original = [row['path'] for row in platform['files']]
    if set(added) & set(original):
        raise ValueError('SKY130 rule resources overlap the platform capture.')
    for name, data in captured.items():
        target = output/name; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    record = dict(schema=1, recipe=RECIPE, revision=REVISION, qualified=False,
                  files=inventory(output, sorted(captured)))
    atomic_write(output/'preparation.json', json.dumps(record, indent=2)+'\n')
    result = clone(platform)
    result['files'] = inventory(base, original+added)
    result['fingerprint'] = digest(result['files'])
    result['sky130_rules'] = dict(recipe=RECIPE, directory=relative,
                                preparation_sha256=file_digest(output/'preparation.json'))
    verify(result)
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('platform', 'output', 'manifest'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--bundle', type=Path)
    args = parser.parse_args()
    if args.manifest.exists():
        raise ValueError('Preserve the existing platform manifest.')
    result = prepare(json.loads(args.platform.read_bytes()), args.output, bundle=args.bundle)
    atomic_write(args.manifest, json.dumps(result, indent=2)+'\n')
