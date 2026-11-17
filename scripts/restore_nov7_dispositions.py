"""Restore the fourth November 7 source-disposition report from its retained predecessor."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.reconstruct_source_dispositions import decode_verified

FOLDER = ROOT / 'docs/qualification'
BASE = FOLDER / 'source-dispositions-2026-11-07-v3.json.gz'
DELTA = FOLDER / 'source-dispositions-2026-11-07-v4.delta.json.gz'
BASE_SHA = '25211fa622eb200bf1c9680083a5acf9b63b65bb0a4c56cc20f885a18dfa62e0'
DELTA_SHA = '40edf7ca6aa4b268c7547ddb7dfb1d4bf3788a29227881d0729a56d7fdef1cf4'
REPORT_SHA = '5d9a6a7d87702787e4608c956e2f6765ff21a15c29fd68a9d5d006fa78d3a29c'


def restore(output):
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    data = decode_verified(BASE.read_bytes(), DELTA.read_bytes(), BASE_SHA, DELTA_SHA, REPORT_SHA)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream:
        stream.write(data)
    return len(data)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    output = parser.parse_args().output
    print(f'Restored {restore(output)} bytes to {output} (SHA-256 {REPORT_SHA})')
