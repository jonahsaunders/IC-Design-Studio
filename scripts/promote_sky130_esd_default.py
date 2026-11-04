"""Construct the corrected ESD default from the exact reviewed predecessor.

This changes only the finite simulation binding; device-family qualification,
ESD ratings and installed acceptance remain separate requirements.
"""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.model import digest, file_digest
from scripts import sky130_esd_revision_bridge as bridge

MARKER = 'ICSTUDIO-ESD-NVT-DEFAULT.json'
PROOF = {**bridge.PROOF, 'status': 'candidate-default-binding', 'candidate_default': True,
         'default_promoted': False,
         'scope': 'Finite corrected ESD simulation binding only; no ESD rating, physical, family, or installed qualification.'}


def prepare(source, output):
    bridge.prepare(source, output)
    output = Path(output)
    package = json.loads((output / 'package.json').read_bytes())
    del package['files'][bridge.MARKER]
    (output / bridge.MARKER).unlink()
    content = bridge._bytes(PROOF)
    (output / MARKER).write_bytes(content)
    package['files'][MARKER] = hashlib.sha256(content).hexdigest()
    package['technology']['revision'] = ''
    package['revision'] = package['technology']['revision'] = digest(
        dict(files=package['files'], technology=package['technology']))[:16]
    (output / 'package.json').write_bytes(bridge._bytes(package))
    return {'revision': package['revision'], 'manifest_sha256': file_digest(output / 'package.json')}


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', required=True)
    ap.add_argument('--output', required=True)
    args = ap.parse_args()
    print(json.dumps(prepare(args.source, args.output), indent=2))
