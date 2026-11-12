import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from scripts import qualify_ihp_guard_vias as g

class GuardContractTests(unittest.TestCase):
    def test_finite_contract(self):
        self.assertEqual(g.CONTRACT['models'],['rsil','rppd','rhigh'])
        self.assertEqual(len(g.CONTRACT['coverage_cases']),7)
        self.assertEqual(g.CONTRACT['rotations_degrees'],[0,90])
        self.assertEqual(g.CONTRACT['terminal_vias'],0)
        self.assertFalse(g.CONTRACT['qualified'])
    def test_signed_generator_parameters_preserved(self):
        for token in ('50','+50','-50'):
            with self.subTest(token=token),TemporaryDirectory() as tmp:
                folder=Path(tmp)/'generate'
                with patch.object(g,'via_source_contract'),patch.object(g.subprocess,'run',side_effect=RuntimeError('stop-before-native')):
                    with self.assertRaisesRegex(RuntimeError,'stop-before-native'):
                        g.generate({'package_root':tmp},'rsil',2,7,folder,'not-executed',{'viagb':token})
                script=(folder/'generate.tcl').read_text()
                self.assertIn('vias 0 viagb '+token+' viagt 0 viagl 0 viagr 0',script)
    def test_unknown_parameters_rejected_before_execution(self):
        with patch.object(g,'via_source_contract'),patch.object(g.subprocess,'run') as native:
            with self.assertRaisesRegex(ValueError,'Unreviewed'):
                g.generate({},'rsil',2,7,Path('/not-used'),'not-used',{'viagb':'50; quit'})
            native.assert_not_called()
    def test_profile_rejects_changed_library(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'bin').mkdir();lib=root/'engine.so';lib.write_bytes(b'original')
            profile={'installed':{'bin/magic':{},'bin/netgen':{},'engine.so':{'sha256':g.file_digest(lib)}},'runtime_dependencies':{}}
            tools={'magic':str(root/'bin/magic'),'netgen':str(root/'bin/netgen')}
            g.verify_tool_profile(profile,tools)
            lib.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'Changed native profile'):g.verify_tool_profile(profile,tools)
    def test_profile_rejects_mixed_prefix(self):
        with self.assertRaisesRegex(ValueError,'same authenticated prefix'):
            g.verify_tool_profile({'installed':{},'runtime_dependencies':{}},{'magic':'/a/bin/magic','netgen':'/b/bin/netgen'})
    def guard_fixture(self):
        from tests.test_ihp_resistor_via_class import IhpResistorViaTests
        p=IhpResistorViaTests().fixture();c=p['cells'][0]
        c['shapes']=[s for s in c['shapes'] if s['layer'] not in ('Via1.drawing','Metal2.drawing')]
        c['shapes'].append(g.rect('Metal2.drawing',2000,-200,400,400))
        c['shapes'] += [g.rect('Via1.drawing',x,-40,80,80) for x in (2040,2280)]
        return p
    def test_guard_access_removes_lower_label_without_mask_change(self):
        p=self.guard_fixture();q=g.guard_access(p,{'viagb':'50'});g.same_masks(p,q)
        labels=[t for t in q['cells'][0]['layout_texts'] if t['text']=='B']
        self.assertEqual(len(labels),1);self.assertEqual(labels[0]['layer'],'Metal2.label')
        self.assertEqual(g.guard_audit(q)['B']['via1_cuts'],2)
    def test_redundant_cut_and_complete_selected_component_open(self):
        p=g.guard_access(self.guard_fixture(),{'viagb':'50'});one=g.clone(p)
        cuts=[s for s in one['cells'][0]['shapes'] if s['layer']=='Via1.drawing']
        one['cells'][0]['shapes'].remove(cuts[0]);self.assertEqual(g.guard_audit(one)['B']['via1_cuts'],1)
        opened=g.fault_layout(p,'guard-via-open')
        with self.assertRaisesRegex(ValueError,'M1/Via1/M2'):g.guard_audit(opened)
    def test_guard_contact_fault_independent_graph_rejects(self):
        p=g.guard_access(self.guard_fixture(),{'viagb':'50'})
        with self.assertRaisesRegex(ValueError,'contact support'):g.guard_audit(g.fault_layout(p,'guard-contact-open'))
    def test_profile_rejects_alternate_executable(self):
        with self.assertRaisesRegex(ValueError,'named profile entry'):
            g.verify_tool_profile({'installed':{'bin/magic':{},'bin/netgen':{}},'runtime_dependencies':{}},{'magic':'/a/bin/evil','netgen':'/a/bin/netgen'})
    def test_open_parser_requires_actual_body_open(self):
        with TemporaryDirectory() as tmp:
            p=Path(tmp)/'extracted.spice'
            p.write_text('X1 R1 R2 floating rsil w=2u l=7u\n')
            self.assertEqual(g.audit_open_extracted(p,'rsil',2,7,'body-open')['terminals'][2],'floating')
            for body in ('B','R1','R2'):
                p.write_text(f'X1 R1 R2 {body} rsil w=2u l=7u\n')
                with self.assertRaises(ValueError):g.audit_open_extracted(p,'rsil',2,7,'body-open')

if __name__=='__main__':unittest.main()
