import ast
import hashlib
import inspect
import unittest
from scripts import inventory_physical_layers as reader

def macro(body,extra=''):
    import html
    return '<klayout-macro><interpreter>dsl</interpreter><dsl-interpreter-name>d25-dsl-xml</dsl-interpreter-name><text>'+html.escape(body)+'</text>'+extra+'</klayout-macro>'

D25='M = input(1, 0)\nDerived = M - M\nz(Derived, name:"metal", zstart: 0.000, height: .5, color: 0xff0000)'
XS='m = layer("1/0")\nt = .5\nmat = mask(m).grow(t)\nz = 0\noxide = deposit(t, .2)\nplanarize(:to => z, :into => oxide)\noutput("300/0", mat)'
ITF='TECHNOLOGY = demo\nDIELECTRIC ox { THICKNESS=1.0 ER=4.1 }\nCONDUCTOR m { THICKNESS=.5 WMIN=.1 SMIN=.1 RPSQ=.2 }\nVIA v { FROM=m TO=m AREA=.1 RPV=2 }'

class PhysicalLayersTests(unittest.TestCase):
    def test_python_literals_and_safe_reference(self):
        rows=reader.python_layers('layer = {"a": (1, 0), "b": (2, 3)}\nprint(layer["a"])')
        self.assertEqual([(r['name'],r.get('layer'),r.get('datatype')) for r in rows],[('layer',None,None),('a',1,0),('b',2,3),('a',None,None)])
        self.assertFalse(rows[-1]['executed'])
    def test_python_comments_cannot_create_keys(self):
        rows=reader.python_layers('# "fake": (2, 0)\nlayer={"actual":(1,0)}')
        self.assertEqual([r['name'] for r in rows],['layer','actual'])
    def test_python_dynamic_or_unknown_statements_reject(self):
        for source in ('layer={**other}','layer={"a":pair}','layer={"a":(1,False)}','layer={f"a":(1,0)}','import pya\nlayer={"a":(1,0)}','layer={"a":(1,0)}\nexec("hidden")','layer={"a":(1,0)}\nprint(layer["missing"])'):
            with self.subTest(source=source),self.assertRaises(ValueError):reader.python_layers(source)
    def test_python_duplicates_reject_instead_of_losing_keys(self):
        with self.assertRaises(ValueError):reader.python_layers('layer={"a":(1,0),"a":(2,0)}')
    def test_map_preserves_purposes_and_label_targets(self):
        rows=reader.layer_map('M NET,PIN 1 0\nNAME M/LABEL 1 10\nNAME COMP 63 0\nDIEAREA ALL 0 0')
        self.assertEqual(rows[0]['purposes'],['NET','PIN']);self.assertEqual(rows[1]['name'],'M');self.assertEqual(rows[1]['purpose'],'LABEL');self.assertIsNone(rows[2]['purpose'])
    def test_map_unknown_or_truncated_fields_reject(self):
        for source in ('M NET 1','M FUTURE 1 0','NAME M/FUTURE 1 0','M NET $layer 0','M NET 1 0 extra','"M" NET 1 0'):
            with self.subTest(source=source),self.assertRaises(ValueError):reader.layer_map(source)
    def test_d25_layers_and_displays_are_unevaluated_facts(self):
        rows=reader.d25(macro(D25));self.assertEqual(len([r for r in rows if r['kind']=='d25-layer-declaration']),2)
        view=next(r for r in rows if r['kind']=='d25-display-layer');self.assertEqual(view['source_layer'],'Derived');self.assertEqual(view['zstart_literal'],'0.000');self.assertFalse(view['geometry_evaluated'])
    def test_d25_quoted_comment_decoy_and_unknown_interpreter(self):
        rows=reader.d25(macro('# Hidden = input(99,0)\n'+D25, '<description>Fake = input(5,0)</description>'))
        self.assertFalse(any(r['name'] in ('Hidden','Fake') for r in rows))
        with self.assertRaises(ValueError):reader.d25(macro(D25).replace('d25-dsl-xml','ruby'))
    def test_d25_missing_target_and_dynamic_body_reject(self):
        for source in (D25.replace('M - M','Missing - M'),D25+'\neval("more")',D25.replace('input(1, 0)','input(variable, 0)'),D25.replace('name:"metal"','name:"#{dynamic}"')):
            with self.subTest(source=source),self.assertRaises(ValueError):reader.d25(macro(source))
    def test_d25_extra_execution_and_xml_entities_reject(self):
        with self.assertRaises(ValueError):reader.d25(macro(D25,'<prolog>run</prolog>'))
        with self.assertRaises(ValueError):reader.d25('<!DOCTYPE a [<!ENTITY b "a">]>'+macro(D25))
        with self.assertRaises(ValueError):reader.d25(macro(D25,'<text>Hidden=input(99,0)</text>'))
    def test_xsection_complete_input_and_output_names(self):
        rows=reader.xsection(XS);self.assertEqual(rows[0]['layer'],1);self.assertEqual(rows[-1]['name'],'mat');self.assertEqual(rows[-1]['layer'],300)
        self.assertTrue(all(r.get('geometry_evaluated',False) is False for r in rows))
    def test_xsection_expressions_are_hashed_and_reassignments_preserved(self):
        rows=reader.xsection('z=0\nt=.5\nz=z+t')
        self.assertEqual([r['assignment_index'] for r in rows if r['name']=='z'],[0,1])
        self.assertEqual(rows[-1]['expression_sha256'],hashlib.sha256(b'z+t').hexdigest());self.assertEqual(rows[-1]['references'],['z','t'])
    def test_xsection_unknown_functions_missing_targets_reject(self):
        for source in ('x=eval("more")','m=layer("1/0")\nx=mask(m).grow(missing)','output("1/0", missing)','m=layer("$dynamic")','m=layer("1/0"); hidden=bulk','source "external"'):
            with self.subTest(source=source),self.assertRaises(ValueError):reader.xsection(source)
    def test_xsection_comment_and_string_decoys_do_not_add_names(self):
        rows=reader.xsection('# fake=layer("99/0")\n'+XS)
        self.assertFalse(any(r['name']=='fake' for r in rows))
        with self.assertRaises(ValueError):reader.xsection('fake="hidden=layer(1)"')
    def test_itf_named_attributes_and_reference_links(self):
        rows=reader.itf(ITF);links=[r for r in rows if r['kind']=='itf-layer-reference'];self.assertEqual([r['name'] for r in links],['m','m']);self.assertTrue(all(r['target_lines']==[3] for r in links))
    def test_itf_repeated_source_names_are_not_merged(self):
        rows=reader.itf(ITF+'\nDIELECTRIC ox {THICKNESS=1 ER=4.1}')
        self.assertEqual(len([r for r in rows if r['kind']=='itf-stack-declaration' and r['name']=='ox']),2)
        diag=next(r for r in rows if r['kind']=='itf-source-diagnostic');self.assertEqual(diag['lines'],[2,5]);self.assertFalse(diag['correction_inferred'])
    def test_itf_missing_unknown_or_dynamic_fields_reject(self):
        for source in ('TECHNOLOGY=a\nVIA v { AREA=1 }','TECHNOLOGY=a\nDIELECTRIC d {THICKNESS=x ER=1}','TECHNOLOGY=a\nDIELECTRIC d {THICKNESS=1 ER=1 FUTURE=1}','TECHNOLOGY=a\nDIELECTRIC d {THICKNESS=1 ER=1 ER=2}','TECHNOLOGY=a\nIF dynamic {CONDUCTOR hidden {}}'):
            with self.subTest(source=source),self.assertRaises(ValueError):reader.itf(source)
    def test_itf_comment_decoys_and_unknown_target_remain_explicit(self):
        rows=reader.itf('$ DIELECTRIC hidden {THICKNESS=1 ER=1}\n'+ITF.replace('TO=m','TO=missing'))
        self.assertFalse(any(r['name']=='hidden' for r in rows));link=next(r for r in rows if r['kind']=='itf-layer-reference' and r['name']=='missing');self.assertEqual(link['target_lines'],[]);self.assertFalse(link['runtime_binding_inferred'])
    def test_unrecognized_format_and_empty_sources_reject(self):
        self.assertIsNone(reader.physical_views(dict(path='unreviewed.txt'),''))
        for parse in (reader.python_layers,reader.layer_map,reader.xsection,reader.itf):
            with self.subTest(parser=parse.__name__),self.assertRaises(ValueError):parse('')
    def test_optimized_mode_does_not_remove_validation(self):
        tree=ast.parse(inspect.getsource(reader));self.assertFalse(any(isinstance(n,ast.Assert) for n in ast.walk(tree)))
        self.assertFalse(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in ('exec','eval','compile') for n in ast.walk(tree)))

    def test_physical_route_requires_exact_source_identity(self):
        row=dict(family='gf180mcu',repository=reader.GF_REPOSITORY,path='tech/klayout/gf180mcu.map',repository_path='tech/klayout/gf180mcu.map')
        self.assertEqual(reader.physical_views(row,'M NET 1 0')[0]['name'],'M')
        for key,value in (('path','different/gf180mcu.map'),('repository_path','different/gf180mcu.map'),('family','ihp-sg13g2'),('repository',reader.GF_REPOSITORY.replace('@','@unreviewed-'))):
            with self.subTest(field=key):self.assertIsNone(reader.physical_views(row|{key:value},'M NET 1 0'))

    def test_unreviewed_physical_path_is_an_inventory_gap(self):
        from scripts import audit_source_dispositions as audit
        for suffix,text in (('.map','M NET 1 0'),('.xs',XS),('.lyd25',macro(D25)),('.itf',ITF),('.py','layer={"a":(1,0)}')):
            row=dict(family='gf180mcu',repository=reader.GF_REPOSITORY,path='unreviewed/layers'+suffix,repository_path='unreviewed/layers'+suffix,mode='100644',git_blob_sha1='a'*40)
            with self.subTest(suffix=suffix):
                _,records,gaps,_=audit.supplemental([row],{},None,reader=lambda _:text.encode())
                self.assertEqual(records[0]['accounting'],'inventory-gap');self.assertEqual(len(gaps),1);self.assertTrue(gaps[0]['blocks_inventory_completion'])

    def test_physical_source_and_both_gf_target_dispositions(self):
        from scripts import audit_source_dispositions as audit
        row=dict(family='gf180mcu',repository=reader.GF_REPOSITORY,path='tech/klayout/gf180mcu.map',repository_path='tech/klayout/gf180mcu.map',mode='100644',git_blob_sha1='a'*40)
        items,records,gaps,_=audit.supplemental([row],{},None,reader=lambda _:b'M NET 1 0')
        self.assertEqual(gaps,[]);item=next(i for i in items if i['kind']=='layer-purpose-mapping')
        self.assertEqual(item['sources'],[audit.source_id(row)]);self.assertEqual(set(item['dispositions']),{'gf180mcuC','gf180mcuD'})
        self.assertTrue(all(d['disposition']=='unimplemented' and d['qualified'] is False and d['reason'] for d in item['dispositions'].values()))
        self.assertIn(item['id'],records[0]['item_ids'])

    def test_ihp_source_and_target_disposition(self):
        from scripts import audit_source_dispositions as audit
        path='ihp-sg13g2/libs.tech/klayout/tech/sg13g2.map'
        row=dict(family='ihp-sg13g2',repository=reader.IHP_REPOSITORY,path=path,repository_path=path,mode='100644',git_blob_sha1='a'*40)
        items,_,gaps,_=audit.supplemental([row],{},None,reader=lambda _:b'M NET 1 0')
        self.assertEqual(gaps,[]);item=next(i for i in items if i['kind']=='layer-purpose-mapping')
        self.assertEqual(item['sources'],[audit.source_id(row)]);self.assertEqual(set(item['dispositions']),{'ihp-sg13g2'})
        self.assertEqual(item['dispositions']['ihp-sg13g2']['disposition'],'unimplemented');self.assertFalse(item['dispositions']['ihp-sg13g2']['qualified'])

    def test_malformed_reviewed_source_remains_gap(self):
        from scripts import audit_source_dispositions as audit
        row=dict(family='gf180mcu',repository=reader.GF_REPOSITORY,path='tech/klayout/gf180mcu.map',repository_path='tech/klayout/gf180mcu.map',mode='100644',git_blob_sha1='a'*40)
        _,records,gaps,_=audit.supplemental([row],{},None,reader=lambda _:b'M FUTURE 1 0')
        self.assertEqual(records[0]['accounting'],'inventory-gap');self.assertEqual(len(gaps),1);self.assertTrue(gaps[0]['blocks_inventory_completion'])

if __name__=='__main__':unittest.main()
