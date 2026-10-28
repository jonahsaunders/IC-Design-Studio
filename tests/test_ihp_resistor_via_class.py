"""Independent conductor/open-node controls for the selected IHP via class."""
from pathlib import Path
import tempfile,unittest
from icstudio.layout import rect
from icstudio.model import clone
from scripts.qualify_standard_mos import load_technology
from scripts import qualify_ihp_resistor_layouts as ihp


class IhpResistorViaTests(unittest.TestCase):
    def test_via_class_authenticates_exact_source_rule_and_rejects_ordinal_options(self):
        tech,_=load_technology('ihp-sg13g2');contract=ihp.via_source_contract(tech)
        self.assertEqual(contract['minimum_area_nm2'],144000)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'libs.tech/magic';source.mkdir(parents=True)
            for name in ihp.VIA_SOURCE_HASHES:(source/name).write_bytes((Path(tech['package_root'])/'libs.tech/magic'/name).read_bytes())
            ihp.via_source_contract(dict(package_root=str(root)))
            rule=source/'ihp-sg13g2-drc.tech';rule.write_bytes(rule.read_bytes()+b'\n')
            with self.assertRaisesRegex(ValueError,'Changed reviewed'):ihp.via_source_contract(dict(package_root=str(root)))
            for value in (2,-1,True,'1'):
                with self.subTest(vias=value),self.assertRaisesRegex(ValueError,'Boolean'):ihp.generate({},'rsil',2,7,root/'unused','unused',value)

    def fixture(self):
        layers=[dict(name=name,gds=gds,datatype=dt) for name,gds,dt in
                [('Activ.drawing',1,0),('GatPoly.drawing',5,0),('Cont.drawing',6,0),
                 ('Metal1.drawing',8,0),('Metal1.label',8,1),('Metal2.drawing',10,0),
                 ('Metal2.label',10,1),('Via1.drawing',19,0)]]
        c=dict(id='c',ports=['R1','R2','B'],layout_ports=[],layout_texts=[],shapes=[])
        p=dict(pdk=dict(grid=5,layers=layers,interoperability=dict(port_layers={
            'Metal1.drawing':'Metal1.label','Metal2.drawing':'Metal2.label'})),cells=[c])
        for name,y in [('R1',1000),('R2',-1000)]:
            for layer,x,b,w,h in [('Metal1.drawing',-250,y-250,500,500),('GatPoly.drawing',-250,y-250,500,500),
                                 ('Cont.drawing',-80,y-80,160,160),('Via1.drawing',-100,y-100,200,200),
                                 ('Metal2.drawing',-180,y-150,360,300)]:c['shapes'].append(rect(layer,x,b,w,h))
            c['layout_ports'].append(dict(name=name,layer='Metal1.drawing',point=[0,y]))
            c['layout_texts'].append(dict(text=name,layer='Metal1.label',x=0,y=y,rotation=0))
        for layer in ('Metal1.drawing','Activ.drawing'):c['shapes'].append(rect(layer,2000,-200,400,400))
        c['shapes'].append(rect('Cont.drawing',2120,-80,160,160))
        c['layout_ports'].append(dict(name='B',layer='Metal1.drawing',point=[2200,0]))
        c['layout_texts'].append(dict(text='B',layer='Metal1.label',x=2200,y=0,rotation=0))
        return p

    def test_minimum_area_landing_changes_only_m2_by_exact_rule(self):
        p=self.fixture();q,changes=ihp.m2_landing(p)
        self.assertEqual([v['extension_each_side_nm'] for v in changes],[60,60])
        self.assertEqual([v['landing_area_nm2'] for v in changes],[144000,144000])
        a,b=ihp.regions(p),ihp.regions(q)
        for pair in a:
            if pair!=(10,0):self.assertTrue((a[pair]^b[pair]).is_empty())
        self.assertTrue((a[(10,0)]-b[(10,0)]).is_empty())
        self.assertEqual(ihp.m2_landing(q)[1],[])

    def test_upper_access_has_only_one_label_per_port_and_preserves_masks(self):
        p=self.fixture();q=ihp.upper_access(p);ihp.same_masks(p,q)
        for name in ('R1','R2'):
            texts=[v for v in q['cells'][0]['layout_texts'] if v['text']==name]
            self.assertEqual(len(texts),1);self.assertEqual(texts[0]['layer'],'Metal2.label')
        self.assertEqual(ihp.terminal_stack_audit(q)['B']['port_layer'],'Metal1.drawing')

    def test_graph_detects_real_via_body_and_lower_material_opens(self):
        p=ihp.upper_access(self.fixture())
        for fault,expected in [('missing-via','R1 has no complete'),('body-open','B has no contact')]:
            q=ihp.missing_via(p) if fault=='missing-via' else ihp.altered(p,fault)
            with self.assertRaisesRegex(ValueError,expected):ihp.terminal_stack_audit(q)
            for key in ('layout_texts','layout_ports'):self.assertEqual(p['cells'][0][key],q['cells'][0][key])
        q=clone(p);q['cells'][0]['shapes']=[s for s in q['cells'][0]['shapes'] if s['layer']!='Activ.drawing']
        with self.assertRaisesRegex(ValueError,'lower material'):ihp.terminal_stack_audit(q)

    def test_fault_audit_requires_actual_open_node_and_unchanged_model_dimensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'extracted.spice'
            for fault,line in [('missing-via','X0 floating R2 B rppd w=2u l=7u'),('body-open','X0 R1 R2 floating rppd w=2u l=7u')]:
                path.write_text(line+'\n');ihp.audit_open_extracted(path,'rppd',2,7,fault)
                for wrong in (line.replace('floating','B'),line.replace('rppd','rsil'),line.replace('2u','2.005u'),line+'\n'+line):
                    path.write_text(wrong+'\n')
                    with self.subTest(fault=fault,line=wrong),self.assertRaises(ValueError):ihp.audit_open_extracted(path,'rppd',2,7,fault)


if __name__=='__main__':unittest.main()
