"""Guard against empty upstream matches, lost pins and changed source assets."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import klayout.db as db
from icstudio import ihp_klayout_lvs as ihp
from icstudio.model import example
from icstudio.layout_verification import reference, run
from scripts.qualify_ihp_pnp_layouts import audit_extracted, selected_reference


class IhpKLayoutLvsTests(unittest.TestCase):
    def layout(self, folder):
        ly=db.Layout();ly.dbu=.001;c=ly.create_cell('coupon')
        c.shapes(ly.layer(8,0)).insert(db.Box(-1000,-500,1000,500))
        c.shapes(ly.layer(8,2)).insert(db.Box(-50,-50,50,50))
        c.shapes(ly.layer(8,2)).insert(db.Text('E',db.Trans(0,0)))
        c.shapes(ly.layer(8,25)).insert(db.Text('E',db.Trans(0,0)))
        c.shapes(ly.layer(8,2)).insert(db.Text('C',db.Trans(500,0)))
        path=folder/'input.gds';ly.write(str(path));return path

    def test_pin_text_compatibility_preserves_masks_and_existing_labels(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);source=self.layout(folder);original=source.read_bytes()
            result=ihp.label_stream(source,folder/'converted.gds','coupon')
            self.assertEqual(source.read_bytes(),original)
            self.assertEqual(result['copied_pin_texts'],[dict(layer=8,text='C',x=500,y=0)])
            ly=db.Layout();ly.read(str(folder/'converted.gds'));c=ly.cell('coupon')
            self.assertEqual(sorted(s.text.string for s in c.shapes(ly.layer(8,25)).each() if s.is_text()),['C','E'])
            self.assertEqual(db.Region(c.shapes(ly.layer(8,0))).area(),2_000_000)
            self.assertEqual(db.Region(c.shapes(ly.layer(8,2))).area(),10_000)
            with self.assertRaises(ValueError):ihp.label_stream(source,folder/'missing.gds','absent')

    def test_bipolar_conversion_changes_only_prefix_and_rejects_empty_or_unknown(self):
        for model,pins,params in [('pnpMPA','C B E','A=1.4p P=5.4u m=1'),('npn13G2','C B E S','we=70n le=900n Nx=2 m=1')]:
            text=f'.SUBCKT coupon {pins}\nQ$1 {pins} {model} {params}\n.ENDS coupon\n'
            changed,record=ihp.bipolar_subcircuits(text)
            self.assertEqual(changed,text.replace('Q$1','X$1'));self.assertEqual(len(record),1)
        for text in ('.SUBCKT coupon\n.ENDS\n','Q1 C B E unknown A=1p P=4u','Q1 C B E npn13G2 we=70n le=900n','ERROR tool failed',
                     'Q1 C B E pnpMPA A=1.4p P=5.4u\nX1 C B E other A=1.4p P=5.4u'):
            with self.subTest(text=text),self.assertRaises(ValueError):ihp.bipolar_subcircuits(text)

    def test_exact_geometry_and_terminals_reject_an_upstream_comparison_false_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'netlist.spice';text=selected_reference(2,.7)['text'];path.write_text(text)
            audit_extracted(path,2,.7)
            for faulty in ('.SUBCKT coupon\n.ENDS\n',text.replace('1 C B E','1 E B C'),text.replace('a=1.4e-12','a=1.5e-12'),text.replace('p=5.4e-06','p=5.5e-06')):
                path.write_text(faulty)
                with self.subTest(faulty=faulty),self.assertRaises(ValueError):audit_extracted(path,2,.7)

    def test_pinned_npn_writer_fallback_retains_every_node_and_parameter(self):
        for model in ('npn13G2l','npn13G2v'):
            text=f'.SUBCKT coupon S B C E\n1$1 C B E S {model} we=70n le=1000n Nx=3 m=1\n.ENDS coupon\n'
            converted,changes=ihp.bipolar_subcircuits(text)
            self.assertEqual(converted,text.replace('1$1','X1$1'))
            ordered,record=ihp.order_top_ports(converted,'coupon',['C','B','E','S'])
            self.assertEqual(ordered,converted.replace('.SUBCKT coupon S B C E','.SUBCKT coupon C B E S'))
            self.assertEqual(record,dict(before=['S','B','C','E'],after=['C','B','E','S']))
            self.assertEqual(changes[0]['terminal_count'],4)
        for text in ('1$1 C B E S unknown we=70n le=1000n Nx=1 m=1',
                     '1$1 C B E pnpMPA A=1p P=4u',
                     '1$1 C B E S npn13G2L we=70n le=1000n Nx=1 m=1',
                     '1 C B E S npn13G2l we=70n le=1000n Nx=1 m=1',
                     '1$1 C B E S npn13G2l we=70n le=1000n Nx=1 m=1\nX1$1 C B E S npn13G2l we=70n le=1000n Nx=1 m=1'):
            with self.subTest(text=text),self.assertRaises(ValueError):ihp.bipolar_subcircuits(text)

    def test_top_order_requires_identical_unique_names_and_flat_circuit(self):
        for header in ('.SUBCKT coupon C B E', '.SUBCKT coupon S C B E GND',
                       '.SUBCKT coupon S C B B', '.SUBCKT wrong S C B E',
                       '.SUBCKT coupon S C B E\n.SUBCKT child C B E'):
            with self.subTest(header=header),self.assertRaises(ValueError):
                ihp.order_top_ports(header+'\n.ENDS\n','coupon',['C','B','E','S'])
        with self.assertRaises(ValueError):ihp.order_top_ports('.SUBCKT coupon C B E S\n.ENDS','coupon',['C','B','E','E'])

    def test_unfiltered_extraction_never_calls_alignment_or_comparison(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=self.layout(root)
            def engine(args,cwd,**kwargs):
                options=dict(v.split('=',1) for i,v in enumerate(args) if i and args[i-1]=='-rd')
                for name in ('net_only','no_simplify','top_lvl_pins'):self.assertEqual(options[name],'true')
                for name in ('purge','purge_nets','purge_devices','combine_devices'):self.assertEqual(options[name],'false')
                self.assertNotIn('schematic',options);self.assertNotIn('layout_netlist',options)
                Path(options['target_netlist']).write_text('.SUBCKT coupon C B E\nQ1 C B E pnpMPA A=1.4p P=5.4u m=1\n.ENDS\n')
                return 'NET_ONLY enabled: apply extraction netlist options and skip comparison.\nLVS Total Run time 1 seconds\n'
            with patch('icstudio.engines.execute',side_effect=engine):
                result=ihp.extract('klayout',source,'coupon',['C','B','E'],{},root/'good')
            audit_extracted(root/'good/extracted.spice',2,.7)
            self.assertEqual(result['interface_conversion'][0]['replacement'],'X1')
            with patch('icstudio.engines.execute',return_value='INFO : Congratulations! Netlists match.'):
                with self.assertRaisesRegex(ValueError,'did not complete'):ihp.extract('klayout',source,'coupon',['C','B','E'],{},root/'bad')

    def test_checked_assets_survive_transfer_and_reject_modification(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);ihp.copy_assets(root);ihp.assets(root)
            (root/'rule_decks/bjt_extraction.lvs').write_text('changed rule')
            with self.assertRaisesRegex(ValueError,'changed'):ihp.assets(root)
            lock=json.loads((root/'SOURCE.json').read_text());lock['files']={'../outside':{'sha256':'0'*64}}
            (root/'SOURCE.json').write_text(json.dumps(lock))
            with self.assertRaisesRegex(ValueError,'Unsafe'):ihp.assets(root)

    def test_wrong_process_or_unknown_engine_is_blocked(self):
        p=example('empty');ref=reference('.subckt coupon C B E\nX1 C B E pnpMPA a=1.4p p=5.4u\n.ends','coupon')
        for engine in ('unknown','ihp-klayout'):
            with tempfile.TemporaryDirectory() as temp:
                report=run(p,p['top'],temp,{},ref,lvs_extractor=engine)
                self.assertEqual(report['status'],'blocked')
                self.assertTrue(all(s['status']=='not_run' for s in report['stages'][1:]))


if __name__=='__main__':unittest.main()
