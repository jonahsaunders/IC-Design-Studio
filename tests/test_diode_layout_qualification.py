"""Diode physical evidence must preserve polarity, perimeter and real faults."""
from pathlib import Path
import tempfile,unittest
from icstudio.model import clone
from icstudio.layout import kdb,rect
from scripts.qualify_diode_layouts import (MODELS,altered,audit_extracted,center_is_anode,
    detected_fault,label_ports,layers,regions,same_masks,selected_reference)


class DiodeLayoutQualificationTests(unittest.TestCase):
    def fixture(self,target):
        m,c=layers(target);label=25 if target=='ihp-sg13g2' else 10
        return {'pdk':{'grid':5,'layers':[dict(name='m1',gds=m[0],datatype=m[1]),dict(name='co',gds=c[0],datatype=c[1]),dict(name='label',gds=m[0],datatype=label)],
            'interoperability':{'port_layers':{'m1':'label'}}},'cells':[{'id':'cell','ports':[],
            'shapes':[rect('m1',-500,-500,1000,1000),rect('m1',-2500,-3000,500,6000),rect('m1',2000,-3000,500,6000),
                rect('m1',-2500,-3000,5000,500),rect('m1',-2500,2500,5000,500),
                rect('co',-110,-110,220,220),rect('co',-2330,-110,220,220),rect('co',2170,-110,220,220)],
            'layout_texts':[dict(text='D1',layer='label',x=0,y=0,rotation=0),dict(text='D2',layer='label',x=-2250,y=0,rotation=0)]}]}

    def test_ports_follow_junction_doping_and_leave_all_masks_intact(self):
        db=kdb()
        for target,names in MODELS.items():
            for name in names:
                p=self.fixture(target);original=clone(p);label_ports(p,name,target);same_masks(original,p)
                self.assertEqual({t['text'] for t in p['cells'][0]['layout_texts']},{'A','K'})
                points={v['name']:v['point'] for v in p['cells'][0]['layout_ports']}
                center='A' if name in ('dpantenna','diode_pd2nw_03v3','diode_pd2nw_06v0') else 'K'
                self.assertEqual(points[center],[0,0]);self.assertNotEqual(points['K' if center=='A' else 'A'],[0,0])
                for v in p['cells'][0]['layout_ports']:
                    self.assertTrue(any(poly.inside(db.Point(*v['point'])) for poly in regions(p)[layers(target)[0]].each()))
        with self.assertRaises(ValueError):center_is_anode('unknown')

    def test_polarity_ambiguity_fails_before_native_verification(self):
        p=self.fixture('ihp-sg13g2');p['cells'][0]['shapes'].append(rect('m1',10000,10000,500,500))
        with self.assertRaisesRegex(ValueError,'one diode'):label_ports(p,'dantenna','ihp-sg13g2')

    def test_controls_change_only_selected_contact_or_metal_masks(self):
        db=kdb()
        for target in MODELS:
            for model in MODELS[target][:2]:
                p=self.fixture(target);label_ports(p,model,target);a=regions(p);metal,contact=layers(target)
                pins={v['name']:db.Point(*v['point']) for v in p['cells'][0]['layout_ports']}
                for fault,pin in [('anode-open','A'),('cathode-open','K')]:
                    q=altered(p,fault,target);b=regions(q);conductor=next(poly for poly in a[metal].each() if poly.inside(pins[pin]))
                    self.assertTrue((a[metal]^b[metal]).is_empty());self.assertTrue((b[contact]-a[contact]).is_empty())
                    removed=a[contact]-b[contact];self.assertFalse(removed.is_empty());self.assertTrue((removed-db.Region(conductor)).is_empty())
                    self.assertEqual(q['cells'][0]['layout_ports'],p['cells'][0]['layout_ports'])
                b=regions(altered(p,'terminal-short',target));self.assertTrue((a[contact]^b[contact]).is_empty())
                self.assertTrue(any(all(poly.inside(pt) for pt in pins.values()) for poly in b[metal].each()))

    def test_exact_geometry_audit_rejects_the_real_flat_writer_perimeter_bug(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'extracted.spice'
            for target,model in [('gf180mcuC','diode_nd2ps_03v3'),('gf180mcuD','diode_pd2nw_06v0'),('ihp-sg13g2','dantenna')]:
                text=selected_reference(target,model,2,7)['text'];path.write_text(text);audit_extracted(path,target,model,2,7)
                faults=[text.replace('1 A K','1 K A'),text.replace(model,'wrong_model'),text.replace('.ends','D_extra A K other area=1p pj=4u\n.ends')]
                if target.startswith('gf180'):
                    faults += [text.replace('pj=1.8e-05','pj=18p'),text.replace('pj=1.8e-05','pj=18.001u'),text.replace('area=1.4e-11','area=14.001p')]
                else:faults += [text.replace('w=2u','w=2.001u'),text.replace('l=7u','l=7.001u')]
                for wrong in faults:
                    self.assertNotEqual(text,wrong);path.write_text(wrong)
                    with self.subTest(target=target,wrong=wrong),self.assertRaises(ValueError):audit_extracted(path,target,model,2,7)

    def test_native_top_pin_mismatch_counts_but_setup_failure_never_does(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);(folder/'lvs').mkdir();(folder/'lvs-extraction').mkdir()
            (folder/'lvs-extraction/extracted.spice').write_text('.subckt coupon A K\nX0 A K dantenna w=2u l=7u\n.ends\n')
            (folder/'lvs/lvs.log').write_text('Netlists match uniquely.\nFinal result: Top level cell failed pin matching.\n')
            report={'status':'failed','stages':[dict(name=n,status='failed' if n=='lvs' else 'passed') for n in ('preflight','layout_export','drc','lvs_extraction','lvs','integrity')]}
            self.assertTrue(detected_fault(report,folder))
            for name in ('preflight','layout_export','lvs_extraction','integrity'):
                q=clone(report);next(s for s in q['stages'] if s['name']==name)['status']='failed'
                self.assertFalse(detected_fault(q,folder))


if __name__=='__main__':unittest.main()
