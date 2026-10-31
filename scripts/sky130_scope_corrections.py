"""Preserve earlier SKY130 measurements while reopening unsupported exclusions."""
import argparse
import hashlib
import json
from pathlib import Path

from icstudio.digital_sky130_scope import correct, REVIEW
from scripts import sky130_density_rule_scope as previous

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT/'docs/validation/sky130-density-scope-2026-10-14.json'
OUTPUT = ROOT/'docs/validation/sky130-scope-corrections-2026-10-14.json'


def build():
    prior = previous.build()
    if (json.dumps(prior, indent=2, ensure_ascii=False)+'\n').encode() != INPUT.read_bytes():
        raise ValueError('Earlier source-scope review no longer reproduces exactly.')
    files = ['icstudio/digital_sky130_scope.py', 'scripts/sky130_scope_corrections.py',
             'scripts/sky130_density_rule_scope.py']
    return dict(schema=1, chunk=6, status='source-scope-corrected-with-open-gates', qualified=False,
        chunk_complete=False, execution_mode='Source review; no new geometry execution or rule pass.',
        input=dict(path=INPUT.relative_to(ROOT).as_posix(), sha256=hashlib.sha256(INPUT.read_bytes()).hexdigest()),
        corrections=REVIEW, cases=[correct(case) for case in prior['cases']],
        source_files={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files},
        scope='Three unsupported absence decisions are reopened. All measured operands, executed checks, error-catalog coverage and other source rows are unchanged. Complete boundary and HVTR device-selection interpretation remain unresolved.')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true')
    args=parser.parse_args();data=(json.dumps(build(),indent=2,ensure_ascii=False)+'\n').encode()
    if args.check:
        if OUTPUT.read_bytes()!=data:raise ValueError('SKY130 source-scope correction differs from its inputs.')
    else:OUTPUT.write_bytes(data)
    print(json.dumps(dict(status='source-scope-corrections-reproduced',qualified=False,chunk_complete=False)))


if __name__=='__main__':main()
