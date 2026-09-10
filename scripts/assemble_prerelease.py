"""Accept matching successful desktop payloads and write final release checksums."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio import __version__
from scripts.prepare_release_payload import checksum, require


def assemble(inputs, output, commit):
    inputs, output = Path(inputs).resolve(), Path(output).resolve()
    require(not output.exists(), 'Use a new prerelease output directory')
    records = list(inputs.rglob(f'IC-Design-Studio-{__version__}-Validation-*.json'))
    require(len(records) == 2, 'Both platform validation records are required')
    platforms, files = set(), {}
    for record in records:
        data = json.loads(record.read_text())
        require(data['status'] == 'passed' and data['version'] == __version__ and data['commit'] == commit,
                'Release evidence must match the exact selected version and commit')
        require(data['platform'] in ('Windows', 'Linux') and data['platform'] not in platforms,
                'Duplicate or unsupported platform')
        platforms.add(data['platform'])
        require(data['distribution']['status'] == 'passed', 'Archive execution is not qualified')
        require(data['assets'].get(data['distribution']['archive']) == data['distribution']['archive_sha256'],
                'Archive execution and payload hashes differ')
        if data['platform'] == 'Windows':
            require(data['installer']['status'] == 'passed', 'Windows installer execution is not qualified')
        for name, expected in data['assets'].items():
            require(Path(name).name == name and name not in files, 'Invalid or duplicate asset name')
            path = record.parent / name
            require(path.is_file() and checksum(path) == expected, 'Missing or changed release asset: ' + name)
            files[name] = path
        require(record.name not in files, 'Duplicate validation record')
        files[record.name] = record
    output.mkdir(parents=True)
    for name, path in files.items():
        shutil.copyfile(path, output / name)
    sums = ''.join(checksum(output / name) + '  ' + name + '\n' for name in sorted(files))
    (output / f'SHA256SUMS-{__version__}.txt').write_text(sums, encoding='utf-8')
    return sorted(files)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    args = parser.parse_args()
    print(json.dumps(assemble(args.input, args.output, args.commit), indent=2))
