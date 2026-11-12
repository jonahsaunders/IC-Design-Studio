"""Reconstruct the exact second November 10 report without changing v1 history."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.reconstruct_source_dispositions import BASE, BASE_SHA, decode_verified, digest, require

PATCH = ROOT/'docs/qualification/source-dispositions-2026-11-10-v2.delta.json.gz'
PATCH_SHA = '84f25d5ad27fd4567cb6f7c29a6d5750ad55709a52098b79a0800fb1ea1c6e7c'
TARGET_SHA = '9d0a7241d984fa3b5ad309957e06339c995f88307302dd219e2f236d04c50a56'


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
