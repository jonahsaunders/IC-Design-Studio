"""Inspect public Nikon template integrity; exit 2 until full signoff is qualified."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from icstudio import digital_sky130_alignment as checks

SOURCE_LOCK_SHA256 = '48b8d636f9686ce6801b251667fc5ffdd8b88d80cb8a820e29cd23edf1634c76'
ORACLE_MANIFEST_SHA256 = '6ab7f86e04ee7757c17b3931da8b92a42db172b94a443c4033723ae893a2c013'


def source_proof(directory=None):
    directory = Path(directory) if directory else ROOT/'tests/fixtures/sky130-public-seal-v1'
    digest = lambda data: hashlib.sha256(data).hexdigest()
    lock_bytes = (directory/'source-lock.json').read_bytes()
    checks.require(digest(lock_bytes) == SOURCE_LOCK_SHA256, 'Changed public seal source lock.')
    lock = json.loads(lock_bytes)
    for item in lock['files']:
        data = (directory/item['name']).read_bytes()
        checks.require(len(data) == item['size'] and digest(data) == item['sha256'] and
                       hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest() == item['git_blob'],
                       'Changed public seal source: '+item['name'])
    pinned = {
        'docs/rules/errors.csv': 'd613c19c0f5de3938980ce98b0e50e0cfb9b537b2cfdb32a3b9b4b03236ef9ed',
        'docs/rules/gds_layers.csv': 'a424c152e2d300992f743f17abdb6fb72402c4c9a4bbdcdbab439757fd0c89b5',
    }
    tables = {}
    with zipfile.ZipFile(ROOT/'tests/fixtures/sky130-filled-references-v1.zip') as archive:
        for name, sha in pinned.items():
            data = archive.read('sources/'+name)
            checks.require(digest(data) == sha, 'Changed pinned SKY130 table.')
            tables[name] = list(csv.DictReader(io.StringIO(data.decode('utf-8'))))
    layers = {row['Layer name']: row for row in tables['docs/rules/gds_layers.csv'] if row['Purpose'] == 'mask'}
    errors = tables['docs/rules/errors.csv']; bindings = {}
    for name, (layer, negative, first) in checks.MASKS.items():
        alias = 'ctm1' if name == 'cctm1' else name
        checks.require(layers[alias]['GDS layer:datatype'] == str(layer)+':0' and layers[alias]['Purpose'] == 'mask',
                       'Changed Nikon mask purpose: '+name)
        if first is None: continue
        for offset, phrase in ((0, 'in the nikon cross has the wrong polarity'),
                               (1, 'is missing from the nikon cross in the layout.')):
            key = 'r'+str(first+offset)
            row = next(r for r in errors if r['ID'] == key)
            checks.require(row['Name'] == name+'.nikon' and row['Description'].endswith(phrase),
                           'Changed Nikon error catalog binding: '+key)
            bindings[key] = dict(catalog=row, gds_map=layers[alias], negative_template=negative)
    return dict(source_lock_sha256=SOURCE_LOCK_SHA256, source=checks.SOURCE,
                source_files=lock['files'], catalog_sources=pinned, bindings=bindings,
                scope=checks.SCOPE, qualified=False, chunk_complete=False,
                catalog_decisions_changed=0)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('gds', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    checks.require(args.output.resolve() != args.gds.resolve(), 'The alignment report cannot overwrite its input layout.')
    report = checks.audit(args.gds)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(report['status']+': '+str(report['matched_mask_windows'])+' matching mask windows; '
          +str(report['mismatched_mask_windows'])+' mismatches. Full signoff remains unqualified.')
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
