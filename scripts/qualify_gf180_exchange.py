"""Fresh GF180 bandgap exchange, full DRC/LVS, and physical negative controls.

The unfilled core is expected to fail density. A passing regression for that
case means the exact known findings were reproduced, never that the core is
DRC clean. Only the filled candidate with the explicit correction must be clean.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.model import file_digest
from scripts.qualification_evidence import Report, Blocked
from scripts.qualify_reference_exchange import layout_routes, geometry_equal
from scripts.verify_gf180_banba_physical import verify, locked_checkout, PV_COMMIT
from scripts.fill_gf180_banba import build

EXAMPLE = ROOT / 'examples/gf180-banba/layout'
CORE_DENSITY = {'PL.8': 64, 'M1.4': 148, 'M2.4': 102}


def rule_counts(result):
    counts = Counter()
    for row in result['drc']['reports'].values():
        counts.update(row['rules'])
    return dict(counts)


def accept(result, expected_rules, lvs=True):
    """A launch/parser error is never an expected physical defect."""
    if (result['drc']['exit_code'] != 0 and not result['drc'].get('completed_with_findings')) or result['lvs']['exit_code'] != 0:
        raise ValueError('A verification engine failed; this is not a detected design defect.')
    if rule_counts(result) != expected_rules:
        raise ValueError('Unexpected DRC findings: ' + repr(rule_counts(result)))
    if result['lvs']['passed'] != lvs:
        raise ValueError('Unexpected strict LVS outcome.')
    return dict(expected_design_drc='passed' if not expected_rules else 'failed',
                observed_design_drc='passed' if result['drc']['passed'] else 'failed',
                expected_rules=expected_rules, observed_rules=rule_counts(result),
                lvs=result['lvs'], gds_sha256=result['gds_sha256'], tools=result['tools'],
                correction=result.get('density_deck_correction'))


def remove_layer(source, target, pair):
    import klayout.db as db
    layout = db.Layout(); layout.read(str(source)); index = layout.find_layer(*pair)
    if index is None: raise ValueError('Fault layer does not exist.')
    count = 0
    for cell in layout.each_cell():
        count += cell.shapes(index).size(); cell.shapes(index).clear()
    if not count: raise ValueError('Fault removed no geometry.')
    layout.write(str(target))


def qualify(args):
    report = Report(args.out, 'gf180-bandgap-exchange')
    state = {}
    def preflight():
        locked_checkout(args.pv, PV_COMMIT)
        state['klayout'] = report.tool('klayout', args.klayout, ['-b', '-v'])
        return dict(pv_commit=PV_COMMIT, physical_variant='B: 4LM, MIM B 2fF, top metal 11K',
                    simulation_package='gf180mcuD model subset; not the physical stack',
                    original_gds_sha256=file_digest(EXAMPLE / 'banba-layout.gds'),
                    original_project_sha256=file_digest(EXAMPLE / 'banba-layout.icproj'))
    report.case('gf180-prerequisites', preflight)
    if not state:
        report.blocked('gf180-physical', 'GF180 prerequisites unavailable.', True)
        return report.finish()
    def check(path, name, corrected=True):
        return verify(SimpleNamespace(out=report.output / name, pv=args.pv,
                      klayout=Path(state['klayout']), gds=path, include_dummy_poly=corrected,
                      drc_lvs_only=True, open_pdks=None, magic=None, ngspice=None))
    def exchange():
        state['paths'], details = layout_routes(EXAMPLE / 'banba-layout.gds', report.output / 'exchange', state['klayout'])
        return details
    report.case('bandgap-layout-exchange', exchange)
    # All routes receive geometric/interface comparison. Fresh physical checks
    # use the original and both independently reopened final stream formats.
    for name in ('original', 'reimported-gds', 'reimported-oas', 'restored-edit'):
        def action(name=name):
            if name not in state.get('paths', {}): raise Blocked('Layout exchange did not complete.')
            return accept(check(state['paths'][name], 'core-' + name), CORE_DENSITY)
        report.case('bandgap-core-' + name, action)
    def filled():
        result = build(EXAMPLE / 'banba-layout.gds', report.output / 'fill', 600)
        state['filled'] = report.output / 'fill/banba-density.gds'
        geometry_equal(EXAMPLE / 'density/banba-density.gds', state['filled'])
        return result
    report.case('bandgap-regenerated-fill', filled)
    def filled_check(name, expected, corrected=True, remove=None):
        if 'filled' not in state: raise Blocked('Filled candidate was not generated.')
        source = state['filled']
        if remove:
            source = report.output / (name + '.gds')
            remove_layer(state['filled'], source, remove)
        return accept(check(source, name, corrected), expected)
    report.case('bandgap-filled-clean', lambda: filled_check('filled-clean', {}))
    report.case('bandgap-unmodified-deck-findings', lambda: filled_check('unmodified-deck', {'PL.8': 64}, False))
    report.case('bandgap-reject-missing-poly-fill', lambda: filled_check('missing-poly', {'PL.8': 64}, remove=(30, 4)))
    report.case('bandgap-reject-missing-m2-fill', lambda: filled_check('missing-m2', {'M2.4': 102}, remove=(36, 4)))
    def missing_vias():
        source = report.output / 'missing-vias.gds'
        remove_layer(EXAMPLE / 'banba-layout.gds', source, (35, 0))
        result = check(source, 'missing-vias')
        if result['lvs']['exit_code'] or result['lvs']['passed']:
            raise ValueError('Missing-via geometry did not yield a completed LVS mismatch.')
        return dict(observed_lvs='failed', lvs=result['lvs'], drc=result['drc'], source_sha256=file_digest(source))
    report.case('bandgap-reject-missing-vias', missing_vias)
    report.blocked('bandgap-distributed-rc-and-fill-coupling',
                   'The archived Magic RC flow is unqualified and its technology does not extract dummy-fill coupling. DRC/LVS do not establish parasitic accuracy.')
    report.blocked('virtuoso-bandgap', 'Requires a licensed Virtuoso installation with the matching physical PDK.')
    return report.finish()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--pv', type=lambda p: Path(p).resolve(), required=True)
    parser.add_argument('--klayout', default=shutil.which('klayout'))
    return qualify(parser.parse_args())


if __name__ == '__main__':
    raise SystemExit(main())
