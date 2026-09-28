"""Check Windows and Ubuntu observations against an exact release and package bytes."""
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.model import file_digest
from icstudio.release_acceptance import blockers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', required=True)
    for platform in ('windows', 'ubuntu'):
        parser.add_argument('--'+platform, type=Path, required=True, help='Observed desktop-acceptance.json')
        parser.add_argument('--'+platform+'-package', type=Path, required=True)
    args = parser.parse_args(); result = {}
    for platform in ('windows', 'ubuntu'):
        path = getattr(args, platform)
        record = json.loads(path.read_text(encoding='utf-8'))
        checksum = file_digest(getattr(args, platform+'_package'))
        reasons = blockers(record, args.commit, checksum, platform)
        result[platform] = dict(status='blocked' if reasons else 'passed', blockers=reasons,
                                evidence_sha256=file_digest(path), package_sha256=checksum)
    passed = all(v['status'] == 'passed' for v in result.values())
    print(json.dumps(dict(commit=args.commit, passed=passed, platforms=result), indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
