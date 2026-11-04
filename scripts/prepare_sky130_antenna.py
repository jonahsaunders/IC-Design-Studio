"""Attach the reviewed staged antenna deck to a captured SKY130 HD platform."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.digital_platform import inventory, verify
from icstudio.digital_sky130_antenna import DECK_SHA256, RECIPE
from icstudio.model import atomic_write, clone, digest, file_digest


def prepare(platform, output):
    verify(platform)
    if platform['name'] != 'sky130hd' or platform.get('sky130_antenna'):
        raise ValueError('Attach the staged antenna policy once to a captured SKY130 HD platform.')
    base = Path(platform['root']).resolve(); output = Path(output).resolve()
    source = ROOT/'scripts/sky130_staged_antenna.drc'
    if output == base or not output.is_relative_to(base) or output.exists():
        raise ValueError('Use a new antenna deck path inside the platform.')
    if file_digest(source) != DECK_SHA256:
        raise ValueError('Changed reviewed SKY130 antenna deck.')
    name = output.relative_to(base).as_posix()
    if name.casefold() in {r['path'].casefold() for r in platform['files']}:
        raise ValueError('Antenna deck overlaps a captured resource.')
    output.parent.mkdir(parents=True, exist_ok=True); output.write_bytes(source.read_bytes())
    result = clone(platform)
    result['files'] = inventory(base, [r['path'] for r in platform['files']]+[name])
    result['fingerprint'] = digest(result['files'])
    result['sky130_antenna'] = dict(recipe=RECIPE, deck=name, sha256=DECK_SHA256)
    verify(result)
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('platform', 'output', 'manifest'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    if args.manifest.exists():
        raise ValueError('Preserve the existing platform manifest.')
    value = prepare(json.loads(args.platform.read_bytes()), args.output)
    atomic_write(args.manifest, json.dumps(value, indent=2)+'\n')
