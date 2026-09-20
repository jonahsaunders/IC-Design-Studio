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
from scripts.prepare_release_payload import checksum, require, validate_desktop_report, validate_installer
from scripts.verify_packaged_vga import validate as validate_vga


def validate_statistical_qualification(directory, commit, run_id):
    """Bind the required workload artifact to this draft's source and CI run."""
    directory = Path(directory)
    gate_path = directory / 'campaign-gate.json'
    proof_path = directory / 'statistical-campaign-qualification' / 'qualification.json'
    require(gate_path.is_file() and proof_path.is_file(), 'Missing statistical campaign qualification evidence')
    gate, proof = json.loads(gate_path.read_text()), json.loads(proof_path.read_text())
    require(gate.get('commit') == commit and str(gate.get('run_id')) == str(run_id),
            'Statistical evidence must match the exact selected commit and workflow run')
    require(proof.get('qualification_status') == 'passed' and proof.get('trials') == 128 and
            proof.get('cases') == 1152 and proof.get('completed_cases') == 1152,
            'The complete 1152-case statistical workload must pass')
    fault = proof.get('fault', {})
    require(fault.get('exit_code') == -9 and fault.get('immutable_input_preserved') is True and
            fault.get('stale_publication_rejected') is True and proof.get('retried_cases', 0) > 0,
            'Statistical coordinator recovery and immutable inputs must be qualified')
    joint = proof.get('statistics', {}).get('joint', {})
    require(joint.get('trials') == 128 and joint.get('unresolved') == 0 and
            joint.get('passed', 0) + joint.get('failed', 0) == 128,
            'Statistical trial classifications must be complete')
    return {'schema': 1, 'status': 'passed', 'version': __version__, 'commit': commit,
            'run_id': str(run_id), 'gate_sha256': checksum(gate_path),
            'qualification_sha256': checksum(proof_path), 'cases': 1152,
            'trials': 128, 'joint': joint,
            'scope': 'One-host numerical sampling and coordinator recovery; no two-host or foundry yield qualification.'}


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
        platform = data['platform']
        prefix = f'IC-Design-Studio-{__version__}-'
        archive_name = prefix + ('Windows-x64-Portable.zip' if platform == 'Windows' else 'Linux-x86_64.tar.gz')
        required = {archive_name, prefix + f'Source-{platform}.zip', prefix + f'Evidence-{platform}.zip'}
        if platform == 'Windows': required.add(prefix + 'Windows-x64-Setup.exe')
        require(required <= data['assets'].keys(), 'Missing required desktop, corresponding source or evidence asset for ' + platform)
        require(data['distribution']['status'] == 'passed', 'Archive execution is not qualified')
        require(data['distribution']['archive'] == archive_name, 'Distribution evidence names the wrong platform archive')
        validate_desktop_report(data['distribution'].get('report', {}), commit)
        validate_vga(data['distribution'].get('vga', {}), commit)
        require(data['assets'].get(data['distribution']['archive']) == data['distribution']['archive_sha256'],
                'Archive execution and payload hashes differ')
        if data['platform'] == 'Windows':
            setup_name = prefix + 'Windows-x64-Setup.exe'
            validate_installer(data['installer'], commit, setup_name, data['assets'][setup_name])
            validate_vga(data['installer'].get('vga', {}), commit)
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
