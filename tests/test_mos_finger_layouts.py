"""Shared channels, four-terminal access, parameter semantics and regeneration."""
from decimal import Decimal
import importlib.util
from pathlib import Path
import tempfile
import unittest
from icstudio.layout import kdb,polygon
from icstudio.layout_eco import regenerate
from icstudio.model import clone,load_project,save_project
from icstudio.process_adapters import ADAPTERS
from scripts.qualify_standard_mos import load_technology
from scripts.qualify_mos_finger_layouts import TARGETS,FAULTS,sizes,fixture,altered,channel_audit,shared_diffusion_audit


class MosFingerLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.techs={t:load_technology(t)[0] for t in TARGETS}

    def region(self,cell,layer,exclude_body=False):
        result=kdb().Region()
        for shape in cell['shapes']:
            if shape['layer']==layer and not (exclude_body and 'fingers:body:' in shape.get('generator_role','')):
                result.insert(polygon(shape))
        return result.merged()

    def test_total_width_is_divided_into_shared_channels_before_parallel_copying(self):
        for target in TARGETS:
            for polarity in ('n','p'):
                for size in sizes(target):
                    width,length,fingers,copies=size;p=fixture(self.techs[target],target,polarity,size);c=p['cells'][0]
                    ls=ADAPTERS[target].layers(p['pdk']);active=self.region(c,ls['diff'],True);gates=self.region(c,ls['poly'])
                    channels=(active&gates).merged();self.assertEqual(channels.count(),fingers*copies)
                    self.assertEqual(active.count(),copies,'Channels must share diffusion within each complete copy.')
                    self.assertEqual((active-gates).merged().count(),(fingers+1)*copies)
                    for channel in channels.each():
                        self.assertEqual(channel.bbox().height(),int(Decimal(str(width))*1000/fingers))
                        self.assertEqual(channel.bbox().width(),round(length*1000))
                    self.assertEqual({pin['pin'] for pin in c['layout_pins']},{'d','g','s','b'})
                    for key,spacing in (('m1',180 if target=='ihp-sg13g2' else 230),('m2',210 if target=='ihp-sg13g2' else 280)):
                        self.assertTrue(self.region(c,ls[key]).space_check(spacing).is_empty(),(target,size,key))
                    roles=[s['generator_role'] for s in c['shapes']];self.assertEqual(len(roles),len(set(roles)))

    def test_invalid_counts_per_channel_grid_and_width_are_rejected(self):
        for target in TARGETS:
            p=fixture(self.techs[target],target,'n',(3,1,3,1));d=p['cells'][0]['devices'][0]
            impl=ADAPTERS[target].implementation();key='ng' if target=='ihp-sg13g2' else 'nf'
            for number in ('0','-1','1.5','9'):
                wrong=clone(d);wrong['model_params'][key]=number
                with self.subTest(target=target,number=number),self.assertRaises(ValueError):impl.specification(p['pdk'],wrong)
            for width,fingers in (('.3u','8'),('1u','3'),('.665u','2'),('10.005u','1')):
                wrong=clone(d);wrong['params']['w']=width;wrong['model_params'][key]=fingers
                with self.subTest(target=target,width=width,fingers=fingers),self.assertRaises(ValueError):impl.specification(p['pdk'],wrong)

    def test_custom_binding_must_emit_the_actual_finger_count(self):
        from icstudio.catalog import binding_for
        for target in TARGETS:
            p=fixture(self.techs[target],target,'n',(3,1,3,1));d=p['cells'][0]['devices'][0];binding=binding_for(p['pdk'],d)
            key='ng' if target=='ihp-sg13g2' else 'nf';binding['parameters']['unused_count']=dict(default='1',positive=True)
            binding['emit_parameters'][key]='unused_count'
            with self.assertRaises(ValueError):ADAPTERS[target].implementation().specification(p['pdk'],d)

    def test_editing_fingers_retains_terminal_identity_and_reopens(self):
        for target in TARGETS:
            p=fixture(self.techs[target],target,'p',(3,1,3,3));c=p['cells'][0];d=c['devices'][0];impl=ADAPTERS[target].implementation()
            pins={pin['pin']:pin['id'] for pin in c['layout_pins']};key='ng' if target=='ihp-sg13g2' else 'nf'
            for fingers,width,copies in ((8,8,16),(2,.8,1),(1,1,1),(3,3,3)):
                d['model_params'].update({key:str(fingers),'m':str(copies)});d['params']['w']=str(width)+'u'
                self.assertTrue(impl.audit(p,c['id']));regenerate(p,c['id'],d['id']);self.assertFalse(impl.audit(p,c['id']))
                self.assertEqual({pin['pin']:pin['id'] for pin in c['layout_pins']},pins)
                if fingers>1:self.assertEqual(c['pdk_layouts'][0]['fingers']['count'],fingers)
                else:self.assertNotIn('fingers',c['pdk_layouts'][0])
                with tempfile.TemporaryDirectory() as td:
                    path=Path(td)/'fingers.icproj';save_project(p,path);other=load_project(path)
                    self.assertEqual(other['cells'][0]['pdk_layouts'],c['pdk_layouts'])

    def test_fault_controls_modify_geometry_without_modifying_schematic(self):
        for target in TARGETS:
            p=fixture(self.techs[target],target,'n',(3,1,3,3));before=clone(p);c=p['cells'][0]
            for fault in FAULTS:
                other=altered(p,target,fault)['cells'][0]
                self.assertEqual(other['devices'],c['devices']);self.assertEqual(other['layout_ports'],c['layout_ports'])
                change=len(other['shapes'])-len(c['shapes'])
                if fault.startswith('reference-'):self.assertEqual(change,0)
                elif fault=='gate-source-short':self.assertEqual(change,1)
                elif fault=='missing-finger':self.assertEqual(change,-2)
                elif fault=='all-body-contacts-open':self.assertEqual(change,-12)
                else:self.assertEqual(change,-1)
            self.assertEqual(p,before)

    def test_same_total_width_does_not_hide_the_wrong_finger_distribution(self):
        good='.subckt parallel_coupon D G S B\n'+''.join(f'X{i} D G S B nfet_03v3 w=1u l=1u\n' for i in range(6))+'.ends\n'
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'native.spice';path.write_text(good,encoding='utf-8')
            self.assertEqual(channel_audit(path,'gf180mcuC','n',(3,1,3,2))['units'],6)
            for wrong in ((3,1,2,2),(3,1,6,2),(6,1,6,1)):
                # The last case has the same aggregate width and same channels,
                # but a different copy/finger grouping that extraction cannot
                # infer from electrical topology alone; only observable channel
                # count/dimensions are part of this readback contract.
                if wrong==(6,1,6,1):
                    self.assertEqual(channel_audit(path,'gf180mcuC','n',wrong)['units'],6)
                else:
                    with self.assertRaises(ValueError):channel_audit(path,'gf180mcuC','n',wrong)
            path.write_text(good.replace('w=1u','w=2u',1),encoding='utf-8')
            with self.assertRaises(ValueError):channel_audit(path,'gf180mcuC','n',(3,1,3,2))

    def test_exported_diffusion_distinguishes_fingers_from_electrically_equivalent_copies(self):
        from icstudio.interchange import export_layout
        for target in TARGETS:
            for polarity in ('n','p'):
                p=fixture(self.techs[target],target,polarity,(3,1,3,2))
                with tempfile.TemporaryDirectory() as td:
                    path=Path(td)/'fingers.gds';export_layout(p,path)
                    result=shared_diffusion_audit(path,target,polarity,(3,1,3,2))
                    self.assertEqual((result['groups'],result['fingers_per_group'],result['channels']),(2,3,6))
                    with self.assertRaisesRegex(ValueError,'groups'):
                        shared_diffusion_audit(path,target,polarity,(1,1,1,6))
                    with self.assertRaisesRegex(ValueError,'gate-finger count'):
                        shared_diffusion_audit(path,target,polarity,(3,1,2,2))
                    with self.assertRaisesRegex(ValueError,'dimensions'):
                        shared_diffusion_audit(path,target,polarity,(6,1,3,2))


if __name__=='__main__':unittest.main()
