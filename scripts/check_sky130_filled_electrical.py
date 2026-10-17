"""Read back final filled-reference application and nominal electrical evidence.

This gate deliberately does not infer complete physical or foundry qualification.
OpenRCX models checkpoint routing, not the GDS-only floating-fill polygons.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from icstudio.digital_design import config
from icstudio.digital_flow import validate_result
from icstudio.digital_implementation import logic_identity
from icstudio.digital_macro import verify_inputs
from icstudio.digital_rc import spef_metrics
from icstudio.digital_reports import eqy_report, timing_report
from icstudio.model import file_digest

ROOT = Path(__file__).resolve().parents[1]
SCOPE = ('Final filled-reference partial application checks, nominal routed OpenRCX timing, '
         'and sequential RTL equivalence. GDS-only fill, process/RC corners, power integrity, '
         'complete required rules and foundry signoff remain outside this gate.')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_bytes())


def electrical_binding(finish, result, job, finish_sha256, final_sdc_sha256):
    """Cross-stage identity checks, independent of absolute execution paths."""
    data = result['digital_result']; stage = data['stage']; original = finish['digital_result']
    require(stage in ('timing', 'equivalence') and job['settings'] == result['settings'],
            'Electrical stage or captured settings differ.')
    upstream = result['settings'].get('upstream', {})
    require(upstream.get('result_sha256') == finish_sha256 and
            upstream.get('artifacts') == original['artifacts'] and upstream.get('stage') == 'finish',
            'Electrical run does not consume this exact final finish result.')
    cfg = config(job['project'], job['cell'])
    require(data.get('logic_hash') == original.get('logic_hash') == logic_identity(cfg) and
            data.get('platform') == original.get('platform') and
            result['project_id'] == finish['project_id'] and result['cell_id'] == finish['cell_id'],
            'Electrical source, technology or design identity changed.')
    require(data['artifacts']['netlist']['sha256'] == original['artifacts']['netlist']['sha256'],
            'Electrical run used a different final netlist.')
    require(data[stage].get('status') == 'PASS' and data.get('verdict') == 'PASS',
            'Electrical stage did not pass.')
    if stage == 'timing':
        require(cfg.get('timing_corners') == ['typical'] and
                data['artifacts'].get('spef', {}).get('sha256') == original['artifacts']['spef']['sha256'],
                'Nominal timing corner or final SPEF differs.')
        constraints = [f for f in cfg['files'] if f['role'] == 'constraint']
        require(len(constraints) == 1 and
                hashlib.sha256(constraints[0]['text'].encode()).hexdigest() == final_sdc_sha256,
                'Timing did not use the actual final implementation constraints.')


def replay_electrical(folder, data):
    """Derive verdicts again from engine files, never from a summary alone."""
    folder = Path(folder)
    if data['stage'] == 'timing':
        report = timing_report(folder/'timing-corners/typical', require_parasitics=True)
        require(report['status'] == 'PASS' and report['summary'] == data['timing']['summary'] and
                len(data['timing']['corners']) == 1, 'Raw timing evidence does not reproduce the reported pass.')
        return dict(status='PASS', summary=report['summary'], annotation=report['parasitic_annotation'])
    require(data['stage'] == 'equivalence', 'Unsupported electrical evidence stage.')
    report = eqy_report(folder/'proof')
    require(report == data['equivalence'] and report['status'] == 'PASS',
            'Raw formal evidence does not reproduce the reported proof.')
    # An inconclusive induction strategy can retain an induction trace before
    # PDR proves the same partition. Preserve it; only actual completed proofs
    # count, and eqy_report rejects a FAIL strategy even beside a PASS.
    return dict(status='PASS', partitions=len(report['partitions']),
                retained_strategy_traces=report['counterexamples'])


def verify_case(directory, case):
    directory = Path(directory).resolve()
    reference = next(r for r in read(ROOT/'docs/validation/sky130-fill-progress-2026-10-11.json')['references']
                     if r['case'] == case)
    audit = read(directory/'audit.json')
    require(audit.get('case') == case and audit.get('status') == 'final-reference-application-and-nominal-electrical-pass'
            and audit.get('qualified') is False and audit.get('chunk_complete') is False,
            'Missing complete bounded electrical run.')
    finish_root = directory/'finish'; finish = read(finish_root/'result.json')
    validate_result(finish, finish_root)
    cfg = verify_inputs(finish, read(finish_root/'input.json'))
    artifacts = finish['digital_result']['artifacts']
    require(artifacts['gds']['sha256'] == reference['gds_sha256'] == audit['source_gds_sha256'] and
            artifacts['checkpoint']['sha256'] == reference['checkpoint_sha256'] == audit['source_checkpoint_sha256'],
            'Final filled GDS or checkpoint is not the accepted reference input.')
    require(finish['digital_result']['physical']['sky130_rules']['status'] == 'reviewed-profiles-pass' and
            finish['digital_result']['physical']['sky130_antenna']['status'] == 'PASS' and
            finish['digital_result']['physical']['checks']['status'] == 'PASS',
            'A required partial physical gate did not pass.')
    snapshots = audit['snapshots']
    for state in ('original', 'filled'):
        folder = finish_root/state; snapshot = snapshots[state]
        for key, name in (('netlist_sha256', 'netlist.v'), ('spef_sha256', 'parasitics.spef')):
            require(file_digest(folder/name) == snapshot[key], 'Changed exported circuit snapshot.')
        require(spef_metrics(folder/'parasitics.spef', cfg['top']) == snapshot['metrics'],
                'Invalid or changed nominal RC extraction.')
    def spef(path):
        return '\n'.join(line for line in path.read_text().splitlines() if not line.startswith('*DATE '))
    require(spef(finish_root/'original/parasitics.spef') == spef(finish_root/'filled/parasitics.spef') and
            audit.get('routed_spef_identical_except_date') is True,
            'Nominal routed parasitics changed; independent electrical review is required.')
    require(snapshots['filled']['netlist_sha256'] == artifacts['netlist']['sha256'] and
            snapshots['filled']['spef_sha256'] == artifacts['spef']['sha256'] and
            snapshots['filled']['checkpoint_sha256'] == artifacts['checkpoint']['sha256'],
            'Final snapshots and application inputs differ.')
    with zipfile.ZipFile(directory/'macro.zip') as archive:
        require(len(archive.namelist()) == len(set(archive.namelist())), 'Duplicate macro members.')
        macro = json.loads(archive.read('macro.json'))
        require(macro['top'] == cfg['top'] and macro['input_key'] == finish['digital_result']['input_key'] and
                macro['environment'] == finish['digital_result']['environment'], 'Exported macro identity changed.')
        for key, entry in macro['artifacts'].items():
            require(key in artifacts and {k: v for k, v in entry.items() if k != 'path'} ==
                    {k: v for k, v in artifacts[key].items() if k != 'path'} and
                    hashlib.sha256(archive.read(entry['path'])).hexdigest() == entry['sha256'],
                    'Exported final macro artifact is missing or changed.')
        require({'gds', 'checkpoint', 'netlist', 'spef', 'sdc', 'sky130_rules', 'sky130_antenna', 'physical_checks'}
                <= macro['artifacts'].keys(), 'Final macro lost required evidence.')
    final_sdc = artifacts['sdc']['sha256']; finish_hash = file_digest(finish_root/'result.json')
    electrical = {}
    for stage in ('timing', 'equivalence'):
        folder = directory/stage; result = read(folder/'result.json'); job = read(folder/'input.json')
        validate_result(result, folder)
        electrical_binding(finish, result, job, finish_hash, final_sdc)
        data = result['digital_result']
        require(file_digest(folder/'result.json') == audit['electrical'][stage]['result_sha256'] and
                read(folder/data['artifacts'][stage]['path']) == data[stage],
                'Saved electrical result differs from its report or run binding.')
        electrical[stage] = replay_electrical(folder, data)
    return dict(case=case, top=cfg['top'], status='bounded-electrical-pass', qualified=False, chunk_complete=False,
                gds_sha256=artifacts['gds']['sha256'], checkpoint_sha256=artifacts['checkpoint']['sha256'],
                netlist_sha256=artifacts['netlist']['sha256'], spef_sha256=artifacts['spef']['sha256'],
                macro_sha256=file_digest(directory/'macro.zip'),
                final_sdc_sha256=final_sdc, finish_result_sha256=finish_hash, electrical=electrical,
                scope=SCOPE)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True, type=Path)
    parser.add_argument('--case', required=True, choices=('counter', 'uart', 'apb'))
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(); result = verify_case(args.directory, args.case)
    text = json.dumps(result, indent=2)+'\n'
    if args.output: args.output.write_bytes(text.encode())
    print(text)


if __name__ == '__main__':
    main()
