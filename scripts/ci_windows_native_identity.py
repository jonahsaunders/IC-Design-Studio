"""Record and verify the exact native build inputs used by Windows CI."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ('native/solver.cpp', 'scripts/build_native.py',
          'scripts/ci_windows_native.ps1', 'scripts/ci_windows_native_identity.py',
          'icstudio/iccore.dll')


def digest(path):
    if not path.is_file():
        raise ValueError(f'Required native build file missing: {path}')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(root, compiler):
    root = Path(root).resolve()
    compiler = Path(compiler).resolve(strict=True)
    return {'schema': 1, 'root': str(root), 'compiler': str(compiler),
            'compiler_sha256': digest(compiler),
            'files': {name: digest(root / name) for name in INPUTS}}


def verify(root, receipt):
    if not isinstance(receipt, dict) or set(receipt) != {'schema', 'root', 'compiler', 'compiler_sha256', 'files'}:
        raise ValueError('Invalid native build identity receipt')
    if type(receipt['schema']) is not int or receipt['schema'] != 1:
        raise ValueError('Unsupported native build identity receipt')
    if not isinstance(receipt['compiler'], str) or not Path(receipt['compiler']).is_absolute():
        raise ValueError('Invalid native compiler path')
    current = record(root, receipt['compiler'])
    if current != receipt:
        raise ValueError('Native binary, compiler, source inputs, or checkout changed since build')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--compiler')
    args = parser.parse_args()
    receipt = ROOT / 'build/ci-native/identity.json'
    if args.verify:
        verify(ROOT, json.loads(receipt.read_text(encoding='utf-8')))
    else:
        if not args.compiler:
            parser.error('--compiler is required when recording')
        value = record(ROOT, args.compiler)
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
