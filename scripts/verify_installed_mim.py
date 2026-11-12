"""Bind three successful installed MiM subgates to one candidate and GUI export.

This receipt covers the selected editor, native/public geometry and sixty-context
linear-model workflow. It does not close the complete MiM family, its remaining
physical classes, silicon calibration, reliability or foundry qualification.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import verify_frozen_mim as gui

require, load, sha = gui.require, gui.load, gui.sha
COUNTS = dict(contexts=60, ac_samples=480, op_points=60, bias_faults=180,
              domain_rejections=5, bias_invariance_contexts=40, fresh_gui_native_inputs=4)


def scoped(value, fields):
    require(all(value.get(key) is False for key in fields), 'Subgate overstates its qualification scope.')


def inventory(root, name, exclusions):
    path = root/name
    require(load(path) == gui.inventory(root, exclusions), 'Subgate evidence inventory changed: '+str(root))
    return sha(path)


def verify(gui_root, public_root, electrical_root, expected_commit):
    require(re.fullmatch('[0-9a-f]{40}', expected_commit or ''), 'Select an exact candidate.')
    roots = [gui.unlinked(p).resolve() for p in (gui_root, public_root, electrical_root)]
    require(len(set(roots)) == 3, 'Subgate evidence roots must be distinct.')
    gr, pr, er = roots
    sources = {}
    for name in ('scripts/verify_installed_mim.py', 'scripts/verify_frozen_mim.py'):
        sources[name] = sha(ROOT/name)
        require(hashlib.sha256(gui.git_blob(expected_commit, name)).hexdigest() == sources[name],
                'Aggregate checker differs from the selected candidate.')
    gv, invocation = load(gr/'verification.json'), load(gr/'invocation.json')
    require(gv.get('schema') == 1 and gv.get('status') == 'PASS' and
            gv.get('gate') == 'mim-installed-gui-queued-layout', 'Frozen GUI acceptance is missing.')
    nonce = gv.get('execution_id', '')
    require(re.fullmatch('[0-9a-f]{32}', nonce) and invocation.get('execution_id') == nonce and
            gv.get('expected_commit') == invocation.get('expected_commit') == expected_commit,
            'GUI candidate or execution identity differs.')
    scoped(gv, ('qualified', 'release_ready', 'full_mim_installed'))
    probe = gr/'probe'
    require(gv['report_sha256'] == sha(probe/'report.json') and gv['files_sha256'] ==
            inventory(probe, 'files.json', ('files.json', 'report.json')), 'GUI report or inventory differs.')

    record, pv = load(pr/'record.json'), load(pr/'verification.json')
    binding = load(er/'inputs.json')
    require(record.get('schema') == 1 and record.get('binding') == binding and
            binding.get('mode') == 'installed' and binding.get('expected_commit') == expected_commit and
            binding.get('execution_id') == nonce, 'Public and electrical checks use different GUI inputs.')
    require(Path(binding['gui_root']).resolve() == probe and Path(binding['supplied_root']).resolve() == gr,
            'Subgate receipt belongs to another GUI output root.')
    for key, path in (('report_sha256', probe/'report.json'), ('files_sha256', probe/'files.json'),
                      ('verification_sha256', gr/'verification.json'), ('invocation_sha256', gr/'invocation.json')):
        require(binding.get(key) == sha(path), 'Subgate GUI receipt changed: '+key)
    require(list(binding['cases']) == list(gui.CASES), 'Four ordered GUI/native cases are required.')
    original = load(probe/'report.json')
    require([v.get('case') for v in original['lifecycle']] == list(gui.CASES) and
            [v.get('case') for v in original['physical']] == list(gui.CASES), 'Original GUI cases differ.')
    for item, native in zip(original['lifecycle'], original['physical']):
        case = binding['cases'][item['case']]
        require(case['plate'] == item['plate'] and case['rotation'] == item['rotation'] and
                case['top'] == item['top'] == native['top'] and case['job_id'] == native['job_id'] and
                case['design_hash'] == native['design_hash'] and case['job_directory'] == native['job_directory'],
                'Subgate case differs from the original GUI/native job.')
        job = gui.confined(probe, native['job_directory'])
        for field, filename in (('input_sha256', 'input.json'), ('result_sha256', 'result.json')):
            require(case[field] == native[field] == sha(job/filename), 'Original native job receipt changed.')
        require(set(case['files']) == set(case['hashes']) == {'project', 'reference', 'schematic', 'gds', 'native'},
                'Incomplete GUI/native file binding.')
        expected_files = {kind: gui.confined(probe, item[kind]) for kind in ('project', 'reference', 'schematic', 'gds')}
        expected_files['native'] = gui.confined(probe, native['evidence_directory'])/'lvs-extraction/extracted.spice'
        for kind, path in case['files'].items():
            require(gui.confined(probe, path) == expected_files[kind] and sha(expected_files[kind]) == case['hashes'][kind],
                    'Fresh GUI/native input changed or belongs to another case.')
    require(sha(gui.unlinked(binding['application']['path'])) == binding['application']['sha256'],
            'Installed application changed before aggregate acceptance.')
    for value in (record, pv):
        require(value.get('status') == 'PASS' and value.get('gate') == 'mim-installed-public-drc' and
                value.get('mode') == 'installed' and value.get('installed') is True, 'Public DRC did not qualify installed inputs.')
        scoped(value, ('qualified', 'release_ready', 'full_mim_installed'))
    require(pv.get('expected_commit') == expected_commit and pv.get('gui_execution_id') == nonce and
            pv.get('execution_id') == record.get('execution_id') and
            pv.get('positive_layouts') == 4 and pv.get('detected_geometry_controls') == 1 and
            pv.get('raw_categories_per_layout') == 255, 'Public DRC coverage or identity differs.')
    require(pv['record_sha256'] == sha(pr/'record.json') and pv['files_sha256'] == record['files_sha256'] ==
            inventory(pr, 'files.json', ('files.json', 'record.json', 'verification.json')),
            'Public DRC receipt or inventory changed.')

    eq, ea = load(er/'qualification.json'), load(er/'audit.json')
    require(eq.get('schema') == ea.get('schema') == 1 and eq.get('gate') == 'mim-installed-electrical60' and
            eq.get('expected_commit') == expected_commit and eq.get('pilot') is False,
            'Full installed electrical selection is required.')
    scoped(eq, ('release_ready',))
    for value in (eq, ea):
        require(value.get('status') == 'PASS' and value.get('mode') == 'installed' and
                value.get('installed_electrical_acceptance') is True, 'Electrical qualification and independent audit must pass.')
        scoped(value, ('qualified', 'signoff', 'full_mim_installed'))
    require(ea.get('counts') == COUNTS and ea['qualification_sha256'] == sha(er/'qualification.json') and
            ea['inputs_sha256'] == eq['inputs_sha256'] == sha(er/'inputs.json'), 'Electrical coverage or receipt differs.')
    require(eq['context_identity']['gui_execution_id'] == nonce and
            eq['context_identity']['inputs_sha256'] == sha(er/'inputs.json'), 'Electrical context belongs to another GUI execution.')
    inventory(er, 'manifest.json', ('manifest.json', 'audit.json'))
    receipts = {}
    for label, root, names in (
        ('gui', gr, ('verification.json', 'invocation.json', 'probe/report.json', 'probe/files.json')),
        ('public', pr, ('record.json', 'files.json', 'verification.json')),
        ('electrical', er, ('qualification.json', 'manifest.json', 'audit.json', 'inputs.json')),
    ):
        receipts[label] = dict(root=str(root), files={name: sha(root/name) for name in names})
    return dict(schema=1, status='PASS', gate='mim-installed-selected-workflow', expected_commit=expected_commit,
                gui_execution_id=nonce, installed_selected_workflow_acceptance=True, qualified=False,
                release_ready=False, full_mim_installed=False, signoff=False, scope=__doc__,
                cases=binding['cases'], counts=COUNTS, receipts=receipts, source_files=sources)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('gui', 'public', 'electrical', 'out'):
        parser.add_argument('--'+key, type=Path, required=True)
    parser.add_argument('--expected-commit', required=True)
    args = parser.parse_args()
    output = gui.unlinked(args.out).resolve()
    require(not output.exists(), 'Use a fresh aggregate receipt path.')
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = verify(args.gui, args.public, args.electrical, args.expected_commit)
    except Exception as exc:
        output.write_text(json.dumps(dict(schema=1, status='FAIL', expected_commit=args.expected_commit,
            installed_selected_workflow_acceptance=False, full_mim_installed=False, qualified=False,
            release_ready=False, signoff=False, error=str(exc)), indent=2)+'\n', encoding='utf-8')
        raise
    output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
