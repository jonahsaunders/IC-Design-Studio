"""Isolation boxes must retain real contacts, three terminal roles and geometry."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import klayout.db as k
from icstudio import ihp_isolation_lvs as iso, ihp_klayout_lvs as ihp
from icstudio.catalog import create_device
from icstudio.catalog_migration import emit
from icstudio.layout_verification import verification_stream
from icstudio.model import clone
from scripts.qualify_standard_mos import load_technology
from scripts.qualify_ihp_isolation_layouts import stream, SIZES, audit_native, detected


class IsolationLvsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.tech,_=load_technology('ihp-sg13g2')

    def test_real_catalog_export_maps_outer_geometry_and_keeps_three_roles(self):
        d=create_device(self.tech,'sg13g2_pr/isolbox.sym','D1');d['nets']={'isosub':'IS','nwell':'NW','sub!':'B'}
        d['model_params'].update(w=6e-6,l=12e-6)
        result,records=iso.geometry(emit(d,self.tech),self.tech)
        self.assertIn(' IS NW B isolbox a=7.2e-11 p=3.6e-05',result)
        self.assertEqual(records[0]['terminal_count'],3)
        self.assertEqual(len(records[0]['source']),2)

    def test_public_and_native_formats_keep_all_values_and_polarities(self):
        text='.subckt t IS NW B\nD1 IS NW B isolbox a=36p p=24u\n.ends t\n'
        a,proof=iso.geometry(text,self.tech);b,native=iso.geometry(text,extracted=True)
        self.assertEqual(a,b);self.assertIn('XICSTUDIO_ISO_D1 IS NW B isolbox a=36p p=24u',a)
        self.assertEqual(iso.geometry(a,self.tech)[0],a)
        self.assertEqual(iso.geometry(a,extracted=True)[0],a)

    def test_no_missing_roles_or_unknown_parameters_are_discarded(self):
        base='X1 IS NW B isolbox w=6u l=6u'
        invalid=[base.replace('IS NW B','IS NW'),base.replace('X1','R1'),base+' m=2',base+' mf=2',
                 base+' aw=4p',base+' xd=1u',base+' W=8u',base.replace('w=6u','w=nan'),
                 base.replace('w=6u','w={size}'),base.replace('w=6u','w=0'),base.replace('w=6u','w=2.1u'),
                 base.replace('w=6u','w=1e200').replace('l=6u','l=1e200'),base.replace(' l=6u',''),
                 'D1 IS NW B isolbox a=0 p=24u','D1 IS NW B isolbox a=36p p=24u extra=1']
        for text in invalid:
            with self.subTest(text=text),self.assertRaises(ValueError):iso.geometry(text,self.tech)
        with self.assertRaises(ValueError):iso.geometry(base,extracted=True)

    def test_changed_model_symbol_or_pin_contract_is_rejected(self):
        for field in ('model_source','source'):
            tech=clone(self.tech);entry=tech['simulation']['catalog']['sg13g2_pr/isolbox.sym']
            tech['package_lock']['files'][entry[field]]='0'*64
            with self.assertRaisesRegex(ValueError,'Changed IHP isolation'):iso.geometry('X1 a b c isolbox w=6u l=6u',tech)
        tech=clone(self.tech);tech['simulation']['catalog']['sg13g2_pr/isolbox.sym']['pin_order']=['sub!','nwell','isosub']
        with self.assertRaisesRegex(ValueError,'three-terminal'):iso.geometry('X1 a b c isolbox w=6u l=6u',tech)

    def test_unrelated_models_processes_and_circuit_local_names(self):
        text='D1 a b ordinary area=1\n';self.assertEqual(iso.geometry(text,self.tech),(text,[]))
        text='X1 a b c isolbox w=6u l=6u\n';self.assertEqual(iso.geometry(text,{}),(text,[]))
        two=''.join(f'.subckt {name} a b c\n{text}.ends {name}\n' for name in ('first','second'))
        self.assertEqual(len(iso.geometry(two,self.tech)[1]),2)
        collision='D1 a b c isolbox a=36p p=24u\nXICSTUDIO_ISO_D1 a b c other\n'
        with self.assertRaisesRegex(ValueError,'Duplicate instance'):iso.geometry(collision,extracted=True)

    def test_source_correction_is_private_and_hash_checked(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);ihp.copy_assets(root)
            path=root/'rule_decks/diode_connections.lvs';before=path.read_bytes()
            proof=iso.extractor_connections(root);after=path.read_bytes()
            self.assertIn(b'isolbox_n_tie = nact_nwell.and(isolbox_recog)',after)
            self.assertIn(b'connect(isolbox_n_tie, cont_drw)',after)
            self.assertEqual(proof['source_sha256'],iso.CONNECTION_SHA256)
            self.assertEqual((ihp.SOURCE/'rule_decks/diode_connections.lvs').read_bytes(),before)
            with self.assertRaises(ValueError):iso.extractor_connections(root)

    def test_stream_keeps_child_recognition_without_globalizing_local_nets(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);ly=k.Layout();ly.dbu=.001;top=ly.create_cell('top');child=ly.create_cell('child')
            child.shapes(ly.layer(63,0)).insert(k.Text('isolbox',k.Trans(0,0)))
            child.shapes(ly.layer(8,2)).insert(k.Text('private',k.Trans(0,0)))
            top.insert(k.CellInstArray(child.cell_index(),k.Trans(1000,1000)))
            for n,x in [('IS',0),('NW',1000),('B',2000)]:top.shapes(ly.layer(8,2)).insert(k.Text(n,k.Trans(x,0)))
            ly.write(str(root/'input.gds'))
            proof=verification_stream(root/'input.gds','top',['IS','NW','B'],root/'flat.gds',pin_layers={(8,2)},recognition_label=iso.recognition_label)
            self.assertEqual(proof['retained_recognition_labels'],1);self.assertEqual(proof['removed_noninterface_labels'],1)
            self.assertEqual(iso.recognition_inventory(root/'flat.gds','top'),[dict(text='isolbox',x=1000,y=1000)])
            self.assertFalse(iso.recognition_label(63,1,'isolbox'));self.assertFalse(iso.recognition_label(63,0,'isolbox_net'))

    def test_inner_tap_type_annotations_survive_without_becoming_port_labels(self):
        from icstudio.ihp_tap_lvs import recognition_label as tap_label
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);ly=k.Layout();ly.dbu=.001;top=ly.create_cell('top');child=ly.create_cell('tap')
            child.shapes(ly.layer(63,0)).insert(k.Text('sub!',k.Trans(0,0)))
            child.shapes(ly.layer(40,0)).insert(k.Box(-390,-390,390,390))
            child.shapes(ly.layer(8,2)).insert(k.Text('private',k.Trans(0,0)))
            top.insert(k.CellInstArray(child.cell_index(),k.Trans(1000,1000)))
            top.shapes(ly.layer(8,2)).insert(k.Text('B',k.Trans(0,0)))
            ly.write(str(root/'input.gds'))
            proof=verification_stream(root/'input.gds','top',['B'],root/'out.gds',pin_layers={(8,2)},recognition_label=tap_label)
            self.assertEqual(proof['retained_recognition_labels'],1);self.assertEqual(proof['removed_noninterface_labels'],1)
            self.assertTrue(tap_label(63,0,'WELL'));self.assertFalse(tap_label(8,2,'sub!'));self.assertFalse(tap_label(63,0,'sub!_net'))

    def test_selected_geometries_and_rotations_preserve_public_ring_area(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'input.gds'
            for w,l in SIZES:
                for rotation in (0,90,180,270):
                    proof=stream(path,w,l,rotation);ly=k.Layout();ly.read(str(path));c=ly.top_cell()
                    well=k.Region(c.shapes(ly.layer(31,0))).merged()
                    self.assertEqual(well.area(),w*l-(w-2100)*(l-2100))
                    self.assertEqual(well.holes().area(),(w-2100)*(l-2100))
                    self.assertEqual(len(iso.recognition_inventory(path,'isolation')),1)
                    if w==l==6000:self.assertEqual(len(proof['public_mask_equivalence']),5)

    def test_native_audit_rejects_swaps_lost_bulk_and_changed_area(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'native.cir';base='.SUBCKT isolation IS NW B\nD1 IS NW B isolbox a=36p p=24u\n.ENDS isolation\n'
            path.write_text(base);audit_native(path,6000,6000,'D')
            for changed in (base.replace('D1 IS NW B','D1 B NW IS'),base.replace('D1 IS NW B','D1 IS NW'),base.replace('36p','35p'),base+base):
                path.write_text(changed)
                with self.assertRaises(ValueError):audit_native(path,6000,6000,'D')

    def test_tool_failures_do_not_satisfy_physical_controls(self):
        with tempfile.TemporaryDirectory() as temp:
            for stage in ('preflight','layout_export','lvs_extraction','lvs'):
                result=dict(status='failed',stages=[dict(name=n,status='failed' if n==stage else 'passed',error='process terminated') for n in ('preflight','layout_export','drc','lvs_extraction','lvs','integrity')])
                self.assertFalse(detected(result,Path(temp),'well-open'))

    def test_contact_width_control_requires_the_native_body_contact_rule(self):
        result=dict(status='failed',stages=[dict(name=n,status='failed' if n=='drc' else 'passed') for n in ('preflight','layout_export','drc','lvs_extraction','lvs','integrity')],findings=[dict(message="'CntB.a': edge-pair: (1,1;1,2)|(2,2;2,1)")])
        self.assertTrue(detected(result,Path('.'),'contact-width'))
        result['findings'][0]['message']="'M1.a': unrelated metal fault"
        self.assertFalse(detected(result,Path('.'),'contact-width'))

    def test_mixed_native_audit_requires_the_internal_tap_and_all_device_geometry(self):
        from scripts.qualify_ihp_isolation_context import audit
        text='.SUBCKT inmos B NW G S D\nM1 D G S internal sg13_lv_nmos L=.13u W=.15u AS=.1005p AD=.1005p PS=1.34u PD=1.34u rfmode=0\nD2 internal NW B isolbox a=36p p=24u\nR3 S internal ptap1 A=.6084p P=3.12u\n.ENDS inmos\n'
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'native.cir';path.write_text(text);audit(path)
            for changed in (text.replace('R3 S internal ptap1 A=.6084p P=3.12u\n',''),text.replace('S internal sg13','S B sg13'),text.replace('D2 internal NW B','D2 internal B NW'),text.replace('.6084p','.7p'),text.replace('rfmode=0','rfmode=1')):
                path.write_text(changed)
                with self.assertRaises(ValueError):audit(path)

    def test_mixed_fixture_keeps_the_public_channel_and_tap_dimensions(self):
        from scripts.qualify_ihp_isolation_context import stream as context_stream
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'input.gds';context_stream(path)
            ly=k.Layout();ly.read(str(path));c=ly.cell('nmos')
            channel=k.Region(c.shapes(ly.layer(1,0)))&k.Region(c.shapes(ly.layer(5,0)))
            self.assertEqual(channel.area(),150*130)
            tap=k.Region(ly.cell('ptap1').shapes(ly.layer(1,0)))
            self.assertEqual(tap.area(),780*780)
            iso_cell=ly.cell('isolbox$1')
            self.assertEqual(k.Region(iso_cell.shapes(ly.layer(31,0))).bbox().area(),6000*6000)


if __name__=='__main__':unittest.main()
