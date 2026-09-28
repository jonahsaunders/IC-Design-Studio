"""Malformed evidence and infrastructure errors must never certify a design."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts.qualification_evidence import Report, Blocked, command, parse_magic_drc, compare_lvs, require_tool
from scripts.qualify_gf180_exchange import accept


class QualificationEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_missing_tool_is_blocked(self):
        with self.assertRaises(Blocked):
            require_tool(str(self.root / 'missing-engine'), 'missing-engine')

    def test_missing_empty_or_conflicting_magic_reports_fail_closed(self):
        good = 'QUAL_DRC_COUNT 0\nQUAL_DRC_STYLE drc(full)\nQUAL_MAGIC_COMPLETE\n'
        findings = self.root / 'findings.tsv'
        with self.assertRaises(ValueError): parse_magic_drc(good, findings)
        findings.write_text('')
        self.assertEqual(parse_magic_drc(good, findings)['status'], 'passed')
        for log in ('', good.replace('QUAL_MAGIC_COMPLETE', ''), good.replace('drc(full)', 'drc(fast)'),
                    good + 'QUAL_DRC_COUNT 0\n', good + 'QUAL_MAGIC_ERROR bad technology\n',
                    good.replace('COUNT 0', 'COUNT 1')):
            with self.subTest(log=log), self.assertRaises(ValueError): parse_magic_drc(log, findings)
        findings.write_text('Metal1 width\t0,0,1,1\n')
        with self.assertRaises(ValueError): parse_magic_drc(good, findings)
        result = parse_magic_drc(good.replace('COUNT 0', 'COUNT 1'), findings)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['findings'][0]['box'], [0, 0, 1, 1])
        findings.write_text('Metal1 width\t0,0,nan,1\n')
        with self.assertRaises(ValueError): parse_magic_drc(good.replace('COUNT 0', 'COUNT 1'), findings)

    def test_lvs_launch_errors_are_not_negative_control_success(self):
        for name in ('reference', 'extracted', 'setup'):
            (self.root / name).write_text('fixture')
        directory = self.root / 'lvs'; directory.mkdir(); (directory / 'lvs.log').write_text('fixture')
        def compare(log):
            with patch('scripts.qualification_evidence.netgen_lvs', return_value=log):
                return compare_lvs('netgen', self.root / 'reference', self.root / 'extracted',
                                   'top', self.root / 'setup', directory, expect_match=False)
        for log in ('', 'Cannot open reference', 'Circuits match uniquely.\nCell pin lists are equivalent.'):
            with self.subTest(log=log), self.assertRaises(ValueError): compare(log)
        self.assertFalse(compare('Netlists do not match.')['matched'])

    def test_timeout_and_nonzero_diagnostics_are_preserved(self):
        for index, error in enumerate((subprocess.TimeoutExpired(['engine'], 1), RuntimeError('engine exited 7'))):
            directory = self.root / str(index)
            with patch('scripts.qualification_evidence.execute', side_effect=error), self.assertRaises(type(error)):
                command(['engine', '--check'], directory)
            self.assertIn(str(error), (directory / 'engine.log').read_text())
            self.assertEqual(json.loads((directory / 'engine.command.json').read_text()), ['engine', '--check'])

    def test_required_blocked_case_cannot_pass_and_optional_scope_remains_visible(self):
        report = Report(self.root / 'required', 'fixture')
        report.case('valid', lambda: {'violations': 0})
        report.blocked('missing-engine', 'Unavailable', required=True)
        self.assertEqual(report.finish(), 1)
        self.assertEqual(report.data['status'], 'blocked')
        self.assertFalse(report.data['complete_scope'])
        report = Report(self.root / 'optional', 'fixture')
        report.case('valid', lambda: {})
        report.blocked('licensed-tool', 'Unavailable')
        self.assertEqual(report.finish(), 0)
        self.assertFalse(report.data['complete_scope'])
        self.assertIn('licensed-tool', (report.output / 'compatibility.md').read_text())
        manifest = json.loads((report.output / 'manifest.json').read_text())
        self.assertIn('qualification.json', manifest)

    def test_known_density_defect_requires_completed_engine_and_exact_rules(self):
        def result():
            return dict(drc=dict(exit_code=1, completed_with_findings=True, passed=False,
                                 reports={'density': dict(rules={'PL.8': 64})}),
                        lvs=dict(exit_code=0, passed=True), gds_sha256='fixture', tools={})
        self.assertEqual(accept(result(), {'PL.8': 64})['observed_design_drc'], 'failed')
        for change in ('crash', 'wrong-rule', 'lvs-failed'):
            r = result()
            if change == 'crash': r['drc']['completed_with_findings'] = False
            if change == 'wrong-rule': r['drc']['reports']['density']['rules'] = {'M1.4': 64}
            if change == 'lvs-failed': r['lvs']['passed'] = False
            with self.subTest(change=change), self.assertRaises(ValueError): accept(r, {'PL.8': 64})

    def test_oasis_presentation_limit_never_ignores_label_or_geometry_changes(self):
        import klayout.db as db
        from scripts.qualify_open_project import geometry_equal
        layout=db.Layout();layout.dbu=.001;top=layout.create_cell('top');layer=layout.layer(68,16)
        label=db.Text('VDD',db.Trans(1,False,100,200));label.size=500
        top.shapes(layer).insert(label)
        top.shapes(layer).insert(db.Box(0,0,500,500))
        first=self.root/'source.gds';second=self.root/'stream.oas'
        layout.write(str(first));layout.write(str(second))
        with self.assertRaisesRegex(ValueError,'text changed'):geometry_equal(first,second)
        result=geometry_equal(first,second,text_presentation=False)
        self.assertEqual(result['presentation_changed_cell_layers'],1)
        for defect in ('name','anchor','geometry'):
            changed=db.Layout();changed.read(str(second));cell=changed.top_cell();idx=changed.find_layer(68,16)
            for shape in cell.shapes(idx).each():
                if shape.is_text():
                    t=shape.text
                    if defect=='name':t.string='VSS'
                    if defect=='anchor':t.x+=100
                    shape.text=t
            if defect=='geometry':cell.shapes(idx).insert(db.Box(600,0,700,500))
            target=self.root/(defect+'.oas');changed.write(str(target))
            with self.subTest(defect=defect),self.assertRaises(ValueError):
                geometry_equal(first,target,text_presentation=False)

    def test_pin_membership_comes_from_stream_purpose_and_ambiguity_fails(self):
        import klayout.db as db
        from scripts.qualification_evidence import stream_pin_contract
        layout=db.Layout();cell=layout.create_cell('top')
        cell.shapes(layout.layer(69,5)).insert(db.Text('internal',db.Trans()))
        cell.shapes(layout.layer(69,16)).insert(db.Text('extra_pin',db.Trans(500,0)))
        path=self.root/'pins.gds';layout.write(str(path))
        self.assertEqual(stream_pin_contract(path,'top',[(69,16)],[(69,5)]),
                         {'pins':['extra_pin'],'labels':['internal']})
        cell.shapes(layout.layer(69,16)).insert(db.Text('internal',db.Trans()))
        layout.write(str(path))
        with self.assertRaisesRegex(ValueError,'Ambiguous'):
            stream_pin_contract(path,'top',[(69,16)],[(69,5)])


if __name__ == '__main__': unittest.main()
