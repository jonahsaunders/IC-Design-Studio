"""Resistor physical evidence rejects topology, dimension and source mistakes."""
from pathlib import Path
import json,shutil,tempfile,unittest
from unittest.mock import patch
from icstudio.layout import kdb,rect
from icstudio.model import clone,file_digest
from scripts.qualify_ihp_resistor_layouts import altered,rotated,regions,same_masks,audit_extracted
from scripts import qualify_gf180_resistor_layouts as gf


class ResistorLayoutQualificationTests(unittest.TestCase):
    def fixture(self,gf180=False):
        metal,contact=((34,0),(33,0)) if gf180 else ((8,0),(6,0))
        p={'pdk':{'layers':[dict(name='m1',gds=metal[0],datatype=0),dict(name='co',gds=contact[0],datatype=0)]},
           'cells':[{'shapes':[rect('m1',-500,1700,1000,600),rect('m1',-500,-2300,1000,600),
                rect('m1',-2500,-3000,500,6000),rect('m1',2000,-3000,500,6000),
                rect('m1',-2500,-3000,5000,500),rect('m1',-2500,2500,5000,500),
                rect('co',-80,1920,160,160),rect('co',-80,-2080,160,160),
                rect('co',-2330,-80,160,160),rect('co',2170,-80,160,160)],
                'layout_ports':[dict(name=n,layer='m1',point=pt) for n,pt in [('R1',[0,2000]),('R2',[0,-2000]),('B',[-2250,0])]],
                'layout_texts':[dict(text=n,layer='m1',x=pt[0],y=pt[1],rotation=0) for n,pt in [('R1',[0,2000]),('R2',[0,-2000]),('B',[-2250,0])]]}]}
        return p,metal,contact

    def test_open_controls_remove_only_contacts_of_the_selected_conductor(self):
        for gf180 in (False,True):
            p,metal,contact=self.fixture(gf180)
            for fault,count in [('terminal-open',1),('body-open',2)]:
                q=altered(p,fault,metal,contact);a,b=regions(p),regions(q)
                self.assertEqual((a[contact]-b[contact]).area(),count*160*160)
                self.assertTrue((a[metal]^b[metal]).is_empty())
                self.assertEqual(p['cells'][0]['layout_ports'],q['cells'][0]['layout_ports'])
                self.assertEqual(p['cells'][0]['layout_texts'],q['cells'][0]['layout_texts'])
            q=clone(p);q['cells'][0]['shapes']=[s for s in q['cells'][0]['shapes'] if s['layer']!='co']
            with self.assertRaisesRegex(ValueError,'No contacts'):altered(q,'terminal-open',metal,contact)

    def test_short_control_connects_the_two_terminals_and_leaves_body_separate(self):
        db=kdb()
        for gf180 in (False,True):
            p,metal,contact=self.fixture(gf180);q=altered(p,'terminal-short',metal,contact)
            endpoints=[db.Point(0,y) for y in (2000,-2000)];body=db.Point(-2250,0)
            self.assertFalse(any(all(v.inside(pt) for pt in endpoints) for v in regions(p)[metal].each()))
            connected=[v for v in regions(q)[metal].each() if all(v.inside(pt) for pt in endpoints)]
            self.assertEqual(len(connected),1);self.assertFalse(connected[0].inside(body))
            self.assertTrue((regions(p)[contact]^regions(q)[contact]).is_empty())

    def test_rotation_preserves_holes_geometry_and_ports_after_four_turns(self):
        p,metal,contact=self.fixture();q=clone(p)
        # Exercise polygon holes as well as the rectangle primitive.
        ring=next(v for v in regions(q)[metal].each() if v.holes())
        from icstudio.layout import shape_from_polygon
        q['cells'][0]['shapes'].append(shape_from_polygon(ring,'m1'))
        original=clone(q)
        for _ in range(4):q=rotated(q)
        same_masks(original,q)
        self.assertEqual(original['cells'][0]['layout_ports'],q['cells'][0]['layout_ports'])
        self.assertEqual(original['cells'][0]['layout_texts'],q['cells'][0]['layout_texts'])

    def test_independent_extraction_audit_rejects_wrong_model_body_and_subpercent_dimensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'extracted.spice'
            for fn,model,width,length in [(audit_extracted,'rhigh','w','l'),(gf.audit_extracted,'npolyf_u','r_width','r_length')]:
                line=f'X0 R1 R2 B {model} {width}=2u {length}=7u'
                p.write_text('.subckt coupon R1 R2 B\n'+line+'\n.ends\n');fn(p,model,2,7)
                for wrong in (line.replace('R2 B','B R2'),line.replace(model,'other'),line.replace('2u','2.005u'),line.replace('7u','7.005u'),line+'\n'+line):
                    p.write_text(wrong+'\n')
                    with self.subTest(model=model,line=wrong),self.assertRaises(ValueError):fn(p,model,2,7)

    def test_pinned_public_generator_reproduces_each_documented_variant(self):
        lock=json.loads((gf.SOURCE/'upstream-lock.json').read_bytes())
        self.assertEqual(lock['flags']['gf180mcuC'],['METALS5','MIM','THICKMET0P9','HRPOLY1K'])
        self.assertEqual(lock['flags']['gf180mcuD'],['METALS5','MIM','THICKMET1P1','HRPOLY1K'])
        self.assertEqual(file_digest(gf.SOURCE/'LICENSE'),lock['files']['LICENSE'])
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            for target in gf.TARGETS:
                folder,record=gf.prepare_source(out,target)
                self.assertEqual(record['upstream'],lock)
                text=(folder/'generator.tcl').read_text()
                self.assertIn('set PDKNAME '+target,text);self.assertNotIn('#ifdef',text)
                self.assertNotIn('source_draw_contact',text)  # Original source is retained; repairs belong to the local invocation.
            source=out/'changed';shutil.copytree(gf.SOURCE,source)
            (source/'common/pdk.tcl').write_bytes((source/'common/pdk.tcl').read_bytes()+b'\n')
            with patch.object(gf,'SOURCE',source),self.assertRaisesRegex(ValueError,'Changed public generator'):gf.prepare_source(out,'gf180mcuC')


if __name__=='__main__':unittest.main()
