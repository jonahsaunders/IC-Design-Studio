"""Both public geometry decks must finish with intact sources and input."""
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

import klayout.db as k
import klayout.rdb as rdb
from icstudio import ihp_klayout_drc as rules
from icstudio.model import file_digest


class PublicIHPDRCTests(unittest.TestCase):
    def test_npn_markers_require_full_unfiltered_native_check(self):
        from icstudio.ihp_npn_drc import check
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'layout.gds';tech=root/'rules.tech';tech.write_text('fixture')
            ly=k.Layout();ly.dbu=.001;c=ly.create_cell('coupon');c.shapes(ly.layer(8,0)).insert(k.Box(0,0,1000,1000));ly.write(str(source))
            with patch('icstudio.silicon_flow.magic_script') as engine:
                self.assertFalse(check('magic',tech,'drc(full)',source,'coupon',[],root/'no-npn')['required']);engine.assert_not_called()
            c.shapes(ly.layer(26,0)).insert(k.Box(0,0,1000,1000));ly.write(str(source))
            def engine(*args):
                folder=args[-2];folder.mkdir();(folder/'findings.tsv').write_text('Native unrelated island\t0,0,10,10\n')
                self.assertIn('drc ignore none',args[-1]);self.assertIn('drc listall why',args[-1])
                return 'STUDIO_DRC_COUNT 1\nSTUDIO_DRC_STYLE drc(full)\nSTUDIO_MAGIC_SCALE 0.005\n'
            with patch('icstudio.silicon_flow.magic_script',side_effect=engine):
                result=check('magic',tech,'drc(full)',source,'coupon',[],root/'npn')
            self.assertTrue(result['required']);self.assertEqual(result['violations'],1)
            self.assertEqual(result['findings'],[{'reason':'Native unrelated island','bbox_nm':[0,0,50,50]}])
            with patch('icstudio.silicon_flow.magic_script',return_value='STUDIO_DRC_COUNT 0\n'),self.assertRaisesRegex(ValueError,'did not finish'):
                check('magic',tech,'drc(full)',source,'coupon',[],root/'incomplete')

    def test_report_geometry_loads_in_a_fresh_process_without_opening_a_layout(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'native.lyrdb';report=rdb.ReportDatabase('native');report.top_cell_name='coupon'
            cell=report.create_cell('coupon');category=report.create_category('width')
            item=report.create_item(cell.rdb_id(),category.rdb_id())
            item.add_value(k.DEdgePair(k.DEdge(0,0,1,0),k.DEdge(0,.1,1,.1)));report.save(str(path))
            command=[sys.executable,'-c',
                'import sys;from icstudio.ihp_klayout_drc import read_report;r=read_report(sys.argv[1]);assert r["count"]==1 and r["findings"][0]["boxes_um"]==[[0.0,0.0,1.0,0.1]]',str(path)]
            result=subprocess.run(command,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))

    def test_written_oxide_covers_all_original_gate_rotations_and_missing_masks_fail(self):
        from icstudio.ihp_varactor_oxide import check
        from scripts.qualify_ihp_varactor_layouts import stream
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'coupon.gds'
            for size in ('small','large'):
                for nx in (1,10):
                    for angle in (0,90,180,270):
                        for fault in (None,'missing-oxide','oxide-gap'):
                            with self.subTest(size=size,nx=nx,angle=angle,fault=fault):
                                stream(source,size,nx,angle,fault);result=check(source,'varactor_coupon')
                                self.assertEqual(result['recognized_labels'],1)
                                self.assertGreater(result['gate_area_nm2'],0)
                                self.assertEqual(result['status'],'PASS' if fault is None else 'FAIL')
                                if fault=='oxide-gap':self.assertEqual(result['missing_area_nm2'],400)

    def test_complete_original_bundle_and_transfer_are_immutable(self):
        original={name:file_digest(p) for name,p in rules.assets().items()}
        self.assertIn('rule_decks/sg13g2_maximal.drc',original)
        self.assertIn('sg13g2_tech_mod.json',original)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);rules.copy_assets(root)
            self.assertEqual(original,{name:file_digest(p) for name,p in rules.assets(root).items()})
            rule=root/'rule_decks/sg13g2_maximal.drc';rule.write_bytes(rule.read_bytes()+b'\n')
            with self.assertRaisesRegex(ValueError,'changed IHP DRC'):rules.assets(root)
            lock=root/'SOURCE.json';data=json.loads(lock.read_bytes());data['files'].pop('rule_decks/sg13g2_maximal.drc')
            lock.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'source lock'):rules.assets(root)

    def engine(self,command,cwd,**kwargs):
        if command[-1]=='-v':return 'KLayout 0.30.5'
        options=dict(x.split('=',1) for x in command if '=' in x)
        name=Path(cwd).name;self.calls.append(name)
        self.assertEqual(options['input'],str(self.source.resolve()))
        self.assertEqual(options['topcell'],'coupon')
        self.assertFalse(any(n.startswith('no_') or n=='tables' for n in options))
        if self.fault=='crash' and name=='maximal':raise RuntimeError('native deck crashed')
        if not (self.fault=='missing-report' and name=='maximal'):
            report=rdb.ReportDatabase('native fixture');report.top_cell_name='other' if self.fault=='top' else 'coupon'
            cell=report.create_cell(report.top_cell_name);category=report.create_category('M1.a' if name=='main' else 'NW.e')
            for i in range(1 if name=='main' else 2):
                item=report.create_item(cell.rdb_id(),category.rdb_id());item.add_value(k.DBox(i,0,i+1,1))
            report.save(options['report'])
        if self.fault=='input' and name=='maximal':self.source.write_bytes(b'changed layout')
        if self.fault=='unfinished' and name=='maximal':return 'started\n'
        switches='\n'.join(s+' enabled: true' for s in ('FEOL','BEOL','OFFGRID','ANGLE','PIN','FORBIDDEN','RECOMMENDED'))
        if self.fault=='disabled':switches=switches.replace('FEOL enabled: true','FEOL enabled: false')
        return switches+'\n'+("KLayout DRC run for tables 'main' completed in 1 seconds" if name=='main' else 'KLayout DRC run for maximum ruleSet completed in 1 seconds')

    def run_fixture(self,fault=None):
        with tempfile.TemporaryDirectory() as temp:
            self.source=Path(temp)/'source.gds';self.source.write_bytes(b'captured input');self.fault=fault;self.calls=[]
            with patch('icstudio.engines.execute',side_effect=self.engine):
                return rules.drc('klayout',self.source,'coupon',Path(temp)/'out')

    def test_reports_from_both_decks_are_counted_without_filtering(self):
        result=self.run_fixture()
        self.assertEqual(self.calls,['main','maximal']);self.assertEqual(result['violations'],3)
        self.assertEqual([r['violations'] for r in result['decks']],[1,2])
        self.assertEqual(result['source_lock_sha256'],rules.LOCK_SHA256)

    def test_missing_unfinished_disabled_wrong_top_crashed_or_changed_input_cannot_pass(self):
        for fault in ('missing-report','unfinished','disabled','top','crash','input'):
            with self.subTest(fault=fault),self.assertRaises((ValueError,RuntimeError)):self.run_fixture(fault)

    def test_older_native_engine_cannot_silently_omit_new_rule_operations(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'source.gds';source.write_bytes(b'input')
            with patch('icstudio.engines.execute',return_value='KLayout 0.28.15'),self.assertRaisesRegex(ValueError,'0.30.5'):
                rules.drc('klayout',source,'coupon',Path(temp)/'out')


if __name__=='__main__':unittest.main()
