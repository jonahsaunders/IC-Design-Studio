"""Fail before expensive acceptance if the selected immutable commit changed."""
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def validate_candidate(event_name, event, expected_sha, actual_sha):
    for label, value in [('event', expected_sha), ('checkout', actual_sha)]:
        if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{40}', value):
            raise ValueError(f'The {label} commit must be a full lowercase 40-character Git SHA.')
    if actual_sha != expected_sha:
        raise ValueError('Checkout differs from the event commit; acceptance cannot mix source identities.')
    if event_name == 'workflow_dispatch':
        requested = event.get('inputs', {}).get('candidate_sha', '')
        if not isinstance(requested, str) or not re.fullmatch(r'[0-9a-f]{40}', requested):
            raise ValueError('Set candidate_sha to the full lowercase 40-character commit of the selected branch or tag.')
        if requested != expected_sha:
            raise ValueError('The selected branch/tag no longer matches candidate_sha. Select a matching ref and dispatch again.')
    elif event_name != 'push' or not event.get('ref', '').startswith('refs/tags/v'):
        raise ValueError('Exhaustive acceptance requires a selected manual candidate or a version tag.')
    return {'schema': 1, 'status': 'passed', 'commit': actual_sha,
            'event': event_name, 'ref': event.get('ref', ''),
            'scope': 'Source identity only; no qualification claim.'}


def main():
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
    actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, env=env, text=True).strip()
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text(encoding='utf-8'))
    result = validate_candidate(os.environ['GITHUB_EVENT_NAME'], event, os.environ['GITHUB_SHA'], actual)
    result['ref'] = os.environ.get('GITHUB_REF', result['ref'])
    print(json.dumps(result, indent=2))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as stream:
            stream.write(f"Acceptance candidate: `{actual}`. Every gate must produce fresh evidence for this source.\n")


if __name__ == '__main__':
    main()
