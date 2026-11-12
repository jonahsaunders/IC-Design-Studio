import ast
import hashlib
import inspect
import json
import unittest
from scripts import inventory_cvc_models as reader


class CVCModelsTests(unittest.TestCase):
    def test_literal_types_names_and_numeric_tokens(self):
        rows=reader.model_rules('MN n Vth=0.2 Vgs=1.8 Vds=1.8\nMP p Vth=-.2\nD d\nC c\nQ q\nR r R=l/w')
        self.assertEqual([(r['checker_type'],r['name']) for r in rows],[('MN','n'),('MP','p'),('D','d'),('C','c'),('Q','q'),('R','r')])
        self.assertEqual(rows[1]['attributes'][0]['literal'],'-.2')
        self.assertTrue(all(r['operating_envelope_inferred'] is False and r['simulator_model_binding_inferred'] is False for r in rows))

    def test_numeric_facts_do_not_round_or_create_physical_limits(self):
        rows=reader.model_rules('MN n Vth=1e-400 Vgs=1e400 Vds=1.12345678901234567890123456789')
        self.assertEqual([a['literal'] for a in rows[0]['attributes']],['1e-400','1e400','1.12345678901234567890123456789'])
        self.assertTrue(all(a['evaluated'] is False for a in rows[0]['attributes']))

    def test_expression_identity_without_source_expression_redistribution(self):
        row=reader.model_rules('R r R=l/w*120')[0];value=row['attributes'][0]
        self.assertEqual(value['expression_sha256'],hashlib.sha256(b'l/w*120').hexdigest())
        self.assertEqual(value['identifiers'],['l','w']);self.assertEqual(value['operators'],['/','*']);self.assertEqual(value['numeric_factors'],['120'])
        self.assertNotIn('l/w*120',json.dumps(row))

    def test_checker_switch_override_is_explicit(self):
        value=reader.model_rules('R short model=switch_on')[0]['attributes'][0]
        self.assertEqual(value['literal'],'switch_on');self.assertFalse(value['simulator_model_binding_inferred'])

    def test_column_one_comment_decoy_and_blank_lines(self):
        rows=reader.model_rules('#MN hidden Vth=.1\n\n  \nD Actual\n')
        self.assertEqual([(r['name'],r['line']) for r in rows],[('Actual',4)])

    def test_unknown_or_missing_named_declarations_fail(self):
        for text in ('MN','N n','NMOS n Vth=.2','D "fake"','D $dynamic','D cell[0]','D name extra','D good\nfuture model'):
            with self.subTest(text=text),self.assertRaises(ValueError):reader.model_rules(text)

    def test_arbitrary_grammar_and_comment_positions_fail(self):
        for text in ('D d # hidden',' # D hidden\nD d','include other','MN n condition=(L>1) Vth=.2','R r R=(l/w)','R r R=w/l','R r R=l/w*120+2','R r R=eval(x)','R r model=switch_off','MN n Vth=[set x .2]','MN n Vth=.2;D fake','MN n Vth=.2 Vgs=NaN','MN n Vth=".2"','MN n Vth = .2'):
            with self.subTest(text=text),self.assertRaises(ValueError):reader.model_rules(text)

    def test_duplicate_names_and_attributes_remain_explicit(self):
        for text in ('D d\nD d','D d\nQ d','MN n Vth=.2 Vth=.3','R r R=l/w R=l/w*120'):
            with self.subTest(text=text),self.assertRaises(ValueError):reader.model_rules(text)

    def test_names_preserve_literal_case_without_aliasing(self):
        rows=reader.model_rules('D lower\nD LOWER')
        self.assertEqual([r['name'] for r in rows],['lower','LOWER'])

    def test_record_and_numeric_input_bounds(self):
        for text in ('D '+'x'*257,'MN n Vth='+'1'*300,'D n\n'+' '*100001):
            with self.subTest(size=len(text)),self.assertRaises(ValueError):reader.model_rules(text)

    def test_path_route_does_not_capture_other_models_files(self):
        for process in ('sky130A','sky130B'):self.assertEqual(len(reader.cvc_views(process+'/libs.tech/openlane/cvc/models','D d')),1)
        for path in ('models','sky130A/libs.tech/openlane/cvc/cvcrc','other/libs.tech/openlane/cvc/models','sky130A/libs.ref/models'):
            with self.subTest(path=path):self.assertIsNone(reader.cvc_views(path,'D d'))

    def test_parser_has_no_assert_or_execution_primitives(self):
        tree=ast.parse(inspect.getsource(reader))
        self.assertFalse(any(isinstance(n,ast.Assert) for n in ast.walk(tree)))
        self.assertFalse(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in ('eval','exec','compile') for n in ast.walk(tree)))

    def test_audit_source_and_process_dispositions(self):
        from scripts import audit_source_dispositions as audit
        for family in ('sky130A','sky130B'):
            path=family+'/libs.tech/openlane/cvc/models';row=dict(family=family,path=path,repository='release@pin',repository_path=path,mode='100644')
            items,records,gaps,_=audit.supplemental([row],{},None,reader=lambda _:b'D named')
            self.assertEqual(gaps,[]);item=next(i for i in items if i['kind']=='cvc-checker-model-declaration')
            self.assertEqual(item['sources'],[audit.source_id(row)]);self.assertIn(item['id'],records[0]['item_ids'])
            choice=item['dispositions']['sky130A'];self.assertEqual(choice['disposition'],'unimplemented' if family=='sky130A' else 'inapplicable');self.assertFalse(choice['qualified'])
            self.assertFalse(item['facts']['simulator_model_binding_inferred']);self.assertFalse(item['facts']['operating_envelope_inferred'])

    def test_unreviewed_cvc_path_or_wrong_family_remains_gap(self):
        from scripts import audit_source_dispositions as audit
        for family,path in (('sky130A','sky130A/unreviewed/models'),('gf180mcu','sky130A/libs.tech/openlane/cvc/models'),('sky130B','sky130A/libs.tech/openlane/cvc/models')):
            row=dict(family=family,path=path,repository='release@pin',repository_path=path,mode='100644')
            with self.subTest(family=family,path=path):
                _,records,gaps,_=audit.supplemental([row],{},None,reader=lambda _:b'D named')
                self.assertEqual(records[0]['accounting'],'inventory-gap');self.assertEqual(len(gaps),1);self.assertTrue(gaps[0]['blocks_inventory_completion'])

    def test_malformed_cvc_source_remains_gap(self):
        from scripts import audit_source_dispositions as audit
        path='sky130A/libs.tech/openlane/cvc/models';row=dict(family='sky130A',path=path,repository='release@pin',repository_path=path,mode='100644')
        _,records,gaps,_=audit.supplemental([row],{},None,reader=lambda _:b'MN missing Vth=dynamic')
        self.assertEqual(records[0]['accounting'],'inventory-gap');self.assertEqual(len(gaps),1);self.assertTrue(gaps[0]['blocks_inventory_completion'])


if __name__=='__main__':unittest.main()
