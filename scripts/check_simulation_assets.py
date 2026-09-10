"""Fail a launcher/build if its advertised offline models or engine are absent."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def check(root=ROOT, runtime=False):
    from icstudio.bundled_pdks import packages
    from icstudio.runtime_setup import check_ngspice, verify_runtime_files
    root = Path(root).resolve()
    assets = root / 'icstudio/assets'
    index = json.loads((assets / 'exchange/index.json').read_text(encoding='utf-8'))
    count = 0
    for library in index['libraries'].values():
        for relative, entry in library['files'].items():
            path = (assets / 'exchange' / relative).resolve()
            if not path.is_relative_to(assets / 'exchange') or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
                raise ValueError('Missing or changed bundled simulation asset: ' + relative)
            count += 1
    pdks = packages(assets / 'pdks', verify=True)
    if not {'sky130', 'gf180mcu'} <= {p['family'] for p in pdks}:
        raise ValueError('The release must include both SKY130 and GF180 simulation PDKs.')
    report = {'status': 'passed', 'exchange_files': count, 'pdks': pdks}
    if runtime:
        directory = assets / 'runtime/ngspice'
        if sys.platform == 'win32':
            verify_runtime_files(directory)
        report['runtime'] = check_ngspice(directory / ('ngspice.exe' if sys.platform == 'win32' else 'ngspice'))
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bundle', type=Path, default=ROOT)
    parser.add_argument('--runtime', action='store_true')
    args = parser.parse_args()
    print(json.dumps(check(args.bundle, args.runtime), indent=2))


if __name__ == '__main__':
    main()
