"""Correct inherited default-only VPP descriptions in a new, explicit package.

Original model/symbol/license assets and historical recipes are unchanged.
This changes no device interface, availability, model, or operating claim.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BASE_SHA256 = '0c19e0ea5718a841045b597022d13f2dcb57e35cf8be9757b254fb465f2a35c4'
PARENT = 'sky130_fd_pr/vpp_cap.sym'
NOTE = 'ICSTUDIO-VPP-DESCRIPTIONS.json'
INHERITED = ('Fixed 11.5 x 11.7 um VPP model: c0, c1, substrate b, M5 shield. '
             'W/L are not model geometry inputs; use the fixed layout and positive mult.')
VARIANTS = (
    '04p4x04p6_m1m2m3_shieldl1m5_floatm4',
    '06p8x06p1_l1m1m2m3_shieldpom4',
    '06p8x06p1_m1m2m3_shieldl1m4',
    '08p6x07p8_m1m2m3_shieldl1m5_floatm4',
    '11p3x11p8_l1m1m2m3m4_shieldm5',
    '11p5x11p7_l1m1m2m3_shieldm4',
    '11p5x11p7_l1m1m2m3m4_shieldpom5',
    '11p5x11p7_m1m2m3_shieldl1m5_floatm4',
    '11p5x11p7_m1m2m3m4_shieldl1m5',
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()


def corrected(raw):
    """Only the exact reviewed manifest can supply these catalog identities."""
    from icstudio.model import digest
    require(sha(raw) == BASE_SHA256, 'Unreviewed VPP-description base package.')
    package = json.loads(raw)
    catalog = package['technology']['simulation']['catalog']
    expected = {PARENT[:-4]+'__sky130_fd_pr__cap_vpp_'+name+'.sym' for name in VARIANTS}
    require({key for key, row in catalog.items() if row.get('alternate_of') == PARENT} == expected,
            'Changed VPP alternate inventory.')
    changes = []
    for key in sorted(expected):
        row = catalog[key]
        require(row['notes'].count(INHERITED) == 1, 'Changed inherited VPP description.')
        before = list(row['notes'])
        row['notes'].remove(INHERITED)
        changes.append(dict(catalog_key=key, model=row['model'],
                            available=not bool(row['unavailable']),
                            previous_notes_sha256=sha(json_bytes(before)),
                            corrected_notes_sha256=sha(json_bytes(row['notes']))))
    note = dict(schema=1, base_manifest_sha256=BASE_SHA256,
                base_revision=package['revision'], changes=changes,
                correction='Removed inherited default-only geometry and shield description from derived VPP choices.',
                interfaces_changed=False, model_assets_changed=False,
                availability_changed=False, qualified=False, chunk_complete=False)
    note_raw = json_bytes(note)
    require(NOTE not in package['files'], 'VPP-description note already exists.')
    package['files'][NOTE] = sha(note_raw)
    package['technology']['revision'] = ''
    package['revision'] = package['technology']['revision'] = digest(
        {'files': package['files'], 'technology': package['technology']})[:16]
    return json_bytes(package), note_raw


def prepare(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    require(not output.exists(), 'Choose a new VPP-description package directory.')
    original = (source/'package.json').read_bytes()
    changed, note = corrected(original)
    package = json.loads(original)
    paths = {}
    for relative, expected in package['files'].items():
        path = (source/relative).resolve()
        require(path.is_relative_to(source) and path.is_file() and sha(path.read_bytes()) == expected,
                'Missing or changed original asset: '+relative)
        paths[relative] = path
    output.mkdir(parents=True)
    for relative, path in paths.items():
        destination = (output/relative).resolve()
        require(destination.is_relative_to(output), 'Asset escapes output.')
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
        require(sha(destination.read_bytes()) == package['files'][relative],
                'Changed copied VPP-description asset: '+relative)
    (output/NOTE).write_bytes(note)
    (output/'package.json').write_bytes(changed)
    require((source/'package.json').read_bytes() == original and all(
        sha(path.read_bytes()) == package['files'][relative] for relative, path in paths.items()),
        'Original VPP-description package changed during preparation.')
    require((output/'package.json').read_bytes() == changed and (output/NOTE).read_bytes() == note,
            'VPP-description output readback differs.')
    require(all(sha((output/relative).read_bytes()) == expected
                for relative, expected in package['files'].items()),
            'Original asset changed in prepared VPP-description output.')
    return dict(schema=1, base_manifest_sha256=BASE_SHA256,
                manifest_sha256=sha(changed), revision=json.loads(changed)['revision'],
                corrected_choices=9, available_choices=8, unavailable_choices=1,
                original_assets=len(paths), qualified=False, chunk_complete=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.input, args.output), indent=2))
