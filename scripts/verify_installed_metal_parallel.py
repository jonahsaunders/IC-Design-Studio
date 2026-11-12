"""Join exact-candidate GUI/native and DC/AC array evidence from one installation.

This is one platform's selected installed-array workflow, not full-family or
chunk completion. Both platforms and all existing release gates remain required.
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
GUI_COUNTS = dict(lifecycle=30, native_layouts=30, fresh_native_jobs=42, queued_jobs=43,
    width_faults=5, drc_faults=1, repairs=6, blocked=1, eco_models=5, eco_transitions=20, late_lock_rejections=5)
COUNTS = dict(fresh_gui_native_inputs=30, electrical_contexts=30, electrical_analyses=60,
              electrical_path_samples=3870)
SCOPE_FIELDS = ('qualified', 'release_ready', 'full_family', 'chunk_complete', 'signoff')


def reaudit(root):
    from scripts.audit_installed_metal_parallel import audit
    return audit(root, reviewed_source=ROOT)


def verify(gui_root, electrical_root, expected_commit):
    require(re.fullmatch('[0-9a-f]{40}', expected_commit or ''), 'Select an exact candidate.')
    gr, er = [common.unlinked(path).resolve() for path in (gui_root, electrical_root)]
    require(gr != er and gr not in er.parents and er not in gr.parents,
            'Subgate evidence roots must be distinct and disjoint.')
    sources = {}
    for name in ('scripts/verify_installed_metal_parallel.py', 'scripts/audit_installed_metal_parallel.py',
                 'scripts/verify_frozen_metal_parallel.py', 'scripts/installed_metal_parallel_inputs.py',
                 'scripts/qualify_installed_metal_parallel.py'):
        sources[name] = sha(ROOT/name)
        require(hashlib.sha256(common.git_blob(expected_commit, name)).hexdigest() == sources[name],
                'Aggregate, checker or producer differs from the selected candidate.')
    gui, invocation = load(gr/'verification.json'), load(gr/'invocation.json')
    require(gui.get('schema') == 1 and gui.get('status') == 'PASS' and
            gui.get('gate') == 'metal-parallel-installed-gui-queued-layout' and gui.get('counts') == GUI_COUNTS,
            'Complete installed array GUI acceptance is required.')
    nonce = gui.get('execution_id', '')
    require(re.fullmatch('[0-9a-f]{32}', nonce) and invocation.get('execution_id') == nonce and
            gui.get('expected_commit') == invocation.get('expected_commit') == expected_commit,
            'GUI candidate or execution identity differs.')
    require(all(gui.get(k) is False for k in ('qualified', 'release_ready', 'full_family')),
            'GUI subgate overstates qualification scope.')
    binding = load(er/'inputs.json')
    require(binding.get('mode') == 'installed' and binding.get('expected_commit') == expected_commit and
            binding.get('execution_id') == nonce and Path(binding['gui_root']).resolve() == gr/'probe' and
            Path(binding['supplied_root']).resolve() == gr, 'Electrical inputs belong to another GUI execution.')
    for key, name in (('report_sha256', 'probe/report.json'), ('files_sha256', 'probe/files.json'),
                      ('verification_sha256', 'verification.json'), ('invocation_sha256', 'invocation.json')):
        require(binding.get(key) == sha(gr/name), 'Bound installed GUI receipt changed: '+key)
    require(gui.get('report_sha256') == binding['report_sha256'] and gui.get('files_sha256') == binding['files_sha256'],
            'GUI receipt no longer describes its actual probe.')
    qualification, saved = load(er/'qualification.json'), load(er/'audit.json')
    require(qualification.get('schema') == 1 and qualification.get('mode') == 'installed' and
            qualification.get('status') == 'PASS' and qualification.get('expected_commit') == expected_commit and
            qualification.get('pilot') is False, 'Full installed electrical selection is required.')
    actual = reaudit(er)
    require(actual == saved, 'Independent electrical audit changed or was substituted.')
    require(actual.get('schema') == 1 and actual.get('status') == 'PASS' and actual.get('mode') == 'installed' and
            actual.get('expected_commit') == expected_commit and actual.get('gui_execution_id') == nonce and
            actual.get('installed_electrical_acceptance') is True and actual.get('counts') == COUNTS,
            'Independent audit lacks the complete selected installed-array acceptance.')
    require(all(actual.get(name) is False for name in SCOPE_FIELDS), 'Electrical subgate overstates its scope.')
    require(actual.get('qualification_sha256') == sha(er/'qualification.json') and
            actual.get('inputs_sha256') == sha(er/'inputs.json') and actual.get('manifest_sha256') == sha(er/'manifest.json'),
            'Electrical audit no longer binds its actual evidence.')
    receipts = {}
    for label, path, names in (('gui', gr, ('verification.json', 'invocation.json', 'probe/report.json', 'probe/files.json')),
        ('electrical', er, ('qualification.json', 'manifest.json', 'audit.json', 'inputs.json'))):
        receipts[label] = dict(root=str(path), files={name: sha(path/name) for name in names})
    return dict(schema=1, status='PASS', gate='metal-parallel-installed-selected-workflow',
        expected_commit=expected_commit, gui_execution_id=nonce, installed_selected_workflow_acceptance=True,
        **{name: False for name in SCOPE_FIELDS}, scope=__doc__, gui_counts=GUI_COUNTS, electrical_counts=COUNTS,
        receipts=receipts, source_files=sources)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('gui', 'electrical', 'out'): parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--expected-commit', required=True)
    args = parser.parse_args(); out = common.unlinked(args.out).resolve()
    require(not out.exists(), 'Use a fresh aggregate receipt path.'); out.parent.mkdir(parents=True, exist_ok=True)
    try: result = verify(args.gui, args.electrical, args.expected_commit)
    except Exception as exc:
        out.write_text(json.dumps(dict(schema=1, status='FAIL', expected_commit=args.expected_commit,
            installed_selected_workflow_acceptance=False, **{name: False for name in SCOPE_FIELDS},
            error=str(exc)), indent=2)+'\n', encoding='utf-8')
        raise
    out.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
