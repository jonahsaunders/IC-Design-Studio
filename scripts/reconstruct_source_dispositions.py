"""Lossless storage reconstruction only; never rerun or promote qualification."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.inventory_upstream_views import compressed

BASE_SHA = 'ff2a08f3698dcf09d01c38f77bb9f76866e981401ae380e02efac9bc8084a442'
TARGET_SHA = '263b17bf6dc2c010e230ded19bb4e0c8c4cc3712b7a321ffc84d5be10d7d7216'
PATCH_SHA = '418fe4b99877317afade4a3717d712ea68b66d2591cd68433635e6499df01503'
BASE = ROOT/'docs/qualification/source-dispositions-2026-11-08-v1.json.gz'
PATCH = ROOT/'docs/qualification/source-dispositions-2026-11-10-v1.delta.json.gz'


def require(test, message):
    if not test:
        raise ValueError('Report reconstruction: '+message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def apply_delta(base, patch):
    require(set(patch) == {'schema','scope','base_sha256','target_sha256','replacements','lists'}, 'delta fields')
    require(patch['schema'] == 1, 'delta schema')
    replacements = patch['replacements']; edits = patch['lists']
    require(set(replacements) <= set(base) and set(edits) <= set(base) and not set(replacements)&set(edits), 'unknown/overlapping keys')
    result = dict(base)
    result.update(replacements)
    for key, edit in edits.items():
        require(set(edit) == {'remove','replace','insert'}, 'list edit fields')
        original = base[key]
        require(type(original) is list, 'non-list edit')
        removed = edit['remove']; changed = edit['replace']; inserted = edit['insert']
        require(all(type(i) is int and 0 <= i < len(original) for i in removed) and len(set(removed)) == len(removed), 'invalid removals')
        require(all(str(int(i)) == i and 0 <= int(i) < len(original) for i in changed), 'invalid replacements')
        require(all(str(int(i)) == i and 0 <= int(i) <= len(original) and type(v) is list and v for i,v in inserted.items()), 'invalid insertions')
        require(not set(removed)&{int(i) for i in changed}, 'replace removed row')
        removed = set(removed); rows = []
        for index in range(len(original)+1):
            rows.extend(inserted.get(str(index), []))
            if index < len(original) and index not in removed:
                rows.append(changed.get(str(index), original[index]))
        result[key] = rows
    return result


def decode_verified(base_raw, patch_raw, base_sha=BASE_SHA, patch_sha=PATCH_SHA, target_sha=TARGET_SHA):
    require(digest(base_raw) == base_sha, 'wrong historical base')
    require(digest(patch_raw) == patch_sha, 'wrong delta bytes')
    patch = json.loads(gzip.decompress(patch_raw))
    require(patch['base_sha256'] == base_sha and patch['target_sha256'] == target_sha, 'delta identity differs')
    result = compressed(apply_delta(json.loads(gzip.decompress(base_raw)), patch))
    require(digest(result) == target_sha, 'reconstructed target differs')
    return result


def reconstruct(output, base=BASE, patch=PATCH):
    output = Path(output)
    require(not output.exists() and not output.is_symlink(), 'choose a fresh output')
    raw = decode_verified(Path(base).read_bytes(), Path(patch).read_bytes())
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation cannot replace historical evidence or a raced-in file.
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
