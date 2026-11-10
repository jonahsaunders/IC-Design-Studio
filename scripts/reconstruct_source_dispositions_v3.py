"""Reconstruct the exact third November 10 report without changing v1 history."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.reconstruct_source_dispositions import BASE, BASE_SHA, decode_verified, digest, require

PATCH = ROOT/'docs/qualification/source-dispositions-2026-11-10-v3.delta.json.gz'
PATCH_SHA = 'e64538d28e8d6ded351f19889415f7c516a80eb32b446fdaab997c5cdeb1f772'
TARGET_SHA = '426b8e9b69c270dab32e5aba29e6302c99ee44d4e8c6df26714bd6cb34189448'


def reconstruct(output, base=BASE, patch=PATCH):
    output = Path(output)
    require(not output.exists() and not output.is_symlink(), 'choose a fresh output')
    raw = decode_verified(Path(base).read_bytes(), Path(patch).read_bytes(),
                          base_sha=BASE_SHA, patch_sha=PATCH_SHA, target_sha=TARGET_SHA)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream:
        stream.write(raw)
    return {'status':'PASS_EXACT_REPORT_RECONSTRUCTION','sha256':digest(raw),
            'bytes':len(raw),'qualified':False,'inventory_complete':False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--base', type=Path, default=BASE)
    parser.add_argument('--delta', type=Path, default=PATCH)
    args = parser.parse_args()
    print(json.dumps(reconstruct(args.output, args.base, args.delta), sort_keys=True))
