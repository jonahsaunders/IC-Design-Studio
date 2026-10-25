"""Bind fresh installed resistor editor/extraction and electrical acceptance.

This receipt covers the finite LI/M1--M4 editor and M1--M4 electrical selection.
It does not qualify an entire device family, operating envelope or foundry flow.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import verify_frozen_mim as common

require, load, sha = common.require, common.load, common.sha
GUI_COUNTS = dict(lifecycle=30, binding_lifecycle=15, native_layouts=30,
                  fresh_native_jobs=42, queued_jobs=43, width_faults=5,
                  drc_faults=1, repairs=6, blocked=1)
COUNTS = dict(contexts=90, logical_variants=48, fresh_gui_native_inputs=24,
              dc_conditions=720, ac_conditions=720, transient_conditions=720,
              noise_conditions=120, detected_branch_controls=4680)
SCOPE_FIELDS = ('qualified', 'release_ready', 'full_family', 'chunk_complete', 'signoff')


def reaudit(root):
    from scripts.audit_installed_sky130_metal_resistors import audit
    return audit(root, reviewed_source=ROOT)


def verify(gui_root, electrical_root, expected_commit):
    require(re.fullmatch('[0-9a-f]{40}', expected_commit or ''), 'Select an exact candidate.')
    gr, er = [common.unlinked(path).resolve() for path in (gui_root, electrical_root)]
    require(gr != er and gr not in er.parents and er not in gr.parents,
            'Subgate evidence roots must be distinct and disjoint.')
    sources = {}
    for name in ('scripts/verify_installed_metal_resistors.py',
                 'scripts/audit_installed_sky130_metal_resistors.py',
                 'scripts/verify_frozen_metal_resistors.py',
                 'scripts/installed_metal_resistor_inputs.py'):
        sources[name] = sha(ROOT/name)
        require(hashlib.sha256(common.git_blob(expected_commit, name)).hexdigest() == sources[name],
                'Aggregate or independent checker differs from the selected candidate.')
    gv, invocation = load(gr/'verification.json'), load(gr/'invocation.json')
    require(gv.get('schema') == 1 and gv.get('status') == 'PASS' and
            gv.get('gate') == 'metal-resistor-installed-gui-queued-layout' and
            gv.get('counts') == GUI_COUNTS, 'Complete installed GUI acceptance is required.')
    nonce = gv.get('execution_id', '')
    require(re.fullmatch('[0-9a-f]{32}', nonce) and invocation.get('execution_id') == nonce and
            gv.get('expected_commit') == invocation.get('expected_commit') == expected_commit,
            'GUI candidate or execution identity differs.')
    require(all(gv.get(k) is False for k in ('qualified', 'release_ready', 'full_family')),
            'GUI subgate overstates qualification scope.')
    binding = load(er/'inputs.json')
    require(binding.get('mode') == 'installed' and binding.get('expected_commit') == expected_commit and
            binding.get('execution_id') == nonce and
            Path(binding['gui_root']).resolve() == gr/'probe' and
            Path(binding['supplied_root']).resolve() == gr, 'Electrical input belongs to another GUI execution.')
    for key, name in (('report_sha256', 'probe/report.json'), ('files_sha256', 'probe/files.json'),
                      ('verification_sha256', 'verification.json'), ('invocation_sha256', 'invocation.json')):
        require(binding.get(key) == sha(gr/name), 'Bound GUI receipt changed: '+key)
    require(gv.get('report_sha256') == binding['report_sha256'] and
            gv.get('files_sha256') == binding['files_sha256'], 'GUI receipt no longer describes its probe.')
    eq, saved = load(er/'qualification.json'), load(er/'audit.json')
    require(eq.get('schema') == 1 and eq.get('mode') == 'installed' and eq.get('status') == 'PASS' and
            eq.get('expected_commit') == expected_commit and eq.get('pilot') is False,
            'Full installed electrical selection is required.')
    actual = reaudit(er)
    require(saved == actual, 'Independent electrical audit changed or was substituted.')
    require(actual.get('schema') == 1 and actual.get('status') == 'PASS' and
            actual.get('mode') == 'installed' and actual.get('expected_commit') == expected_commit and
            actual.get('gui_execution_id') == nonce and actual.get('installed_electrical_acceptance') is True and
            actual.get('counts') == COUNTS, 'Independent audit lacks full selected installed acceptance.')
    require(all(actual.get(k) is False for k in SCOPE_FIELDS), 'Electrical subgate overstates qualification scope.')
    require(actual.get('qualification_sha256') == sha(er/'qualification.json') and
            actual.get('inputs_sha256') == sha(er/'inputs.json') and
            actual.get('manifest_sha256') == sha(er/'manifest.json'), 'Electrical audit receipt differs.')
    receipts = {}
    for label, root, names in (
        ('gui', gr, ('verification.json', 'invocation.json', 'probe/report.json', 'probe/files.json')),
        ('electrical', er, ('qualification.json', 'manifest.json', 'audit.json', 'inputs.json')),
    ):
        receipts[label] = dict(root=str(root), files={name: sha(root/name) for name in names})
    return dict(schema=1, status='PASS', gate='metal-resistor-installed-selected-workflow',
        expected_commit=expected_commit, gui_execution_id=nonce,
        installed_selected_workflow_acceptance=True, **{name:False for name in SCOPE_FIELDS},
        scope=__doc__, gui_counts=GUI_COUNTS, electrical_counts=COUNTS,
        receipts=receipts, source_files=sources)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('gui', 'electrical', 'out'):
        parser.add_argument('--'+key, type=Path, required=True)
    parser.add_argument('--expected-commit', required=True)
    args = parser.parse_args()
    output = common.unlinked(args.out).resolve()
    require(not output.exists(), 'Use a fresh aggregate receipt path.')
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = verify(args.gui, args.electrical, args.expected_commit)
    except Exception as exc:
        output.write_text(json.dumps(dict(schema=1, status='FAIL', expected_commit=args.expected_commit,
            installed_selected_workflow_acceptance=False, **{name:False for name in SCOPE_FIELDS},
            error=str(exc)), indent=2)+'\n', encoding='utf-8')
        raise
    output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
