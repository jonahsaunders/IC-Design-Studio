import ast,hashlib,inspect,unittest
from scripts import inventory_legacy_symbols as reader
X='K {type=primitive\nformat="@name @@A @P @@bus[1] @@bus[0] cell"\ntemplate="name=x1 P=VDD"\nextra="P"}\nB 5 0 0 1 1 {name=A dir=in}\nB 5 2 0 3 1 {name=bus[1:0] dir=out}\nT {name=FAKE} 0 0 0 0 0.2 0.2 {}\nL 4 0 0 1 1 {}'
Q='''<Component xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="Component.xsd" library="lib" names="cap" schematic_id="C"><Description>description</Description><Models><DefaultModel value="C"/><SpiceModel value="cap"/></Models><Netlists><NgspiceNetlist value="{name} {nets} {C}"/><CDLNetlist value="{NgspiceNetlist}"/></Netlists><Symbols><Symbol id="Standard"><File>{LIB}/Capacitor.sym</File></Symbol></Symbols><Parameters><Parameter name="w" unit="u" default_value="10.0" show="true"><Description>Width</Description></Parameter><Parameter name="C" unit="F" equation="w*1.e-3" show="true"><Description>Capacitance</Description></Parameter></Parameters></Component>'''
class LegacySymbolsTests(unittest.TestCase):
    def reject(self,parser,source):
        with self.assertRaises((ValueError,SyntaxError)):parser(source)
    def test_symbol_pin_names_and_directions(self):
        rows=reader.headerless_xschem(X);pins=[r for r in rows if r['kind']=='xschem-pin-declaration'];self.assertEqual([(r['name'],r['direction']) for r in pins],[('A','in'),('bus[1:0]','out')]);self.assertTrue(all(r['electrical_order_inferred'] is False for r in pins))
    def test_pin_attribute_and_model_references_stay_distinct(self):
        row=next(r for r in reader.headerless_xschem(X) if r['kind']=='xschem-netlist-template');self.assertEqual([r['kind'] for r in row['references']],['attribute','pin','attribute','pin','pin']);self.assertEqual(row['references'][2]['name'],'P');self.assertEqual(row['model_identifier'],'cell');self.assertFalse(row['model_binding_inferred']);self.assertEqual(row['references'][3]['declared_pin'],'bus[1:0]')
    def test_format_literal_text_not_retained(self):
        row=next(r for r in reader.headerless_xschem(X) if r['kind']=='xschem-netlist-template');self.assertEqual(row['expression_sha256'],hashlib.sha256(b'@name @@A @P @@bus[1] @@bus[0] cell').hexdigest());self.assertNotIn('expression',row)
    def test_quoted_and_comment_decoys_do_not_declare(self):
        rows=reader.headerless_xschem('# B 5 0 0 1 1 {name=DECOY dir=in}\n'+X);self.assertFalse(any(r['name'] in ('FAKE','DECOY') for r in rows));self.assertEqual(next(r for r in rows if r['kind']=='xschem-pin-declaration')['line'],6)
    def test_duplicate_and_missing_pins_reject(self):
        for text in (X+'\nB 5 0 0 1 1 {name=A dir=in}',X.replace('name=A dir=in','dir=in'),X.replace('name=A dir=in','name=A name=B dir=in')):self.reject(reader.headerless_xschem,text)
    def test_unknown_dynamic_attribute_or_record_reject(self):
        for text in (X+'\nC {hidden.sym} 0 0 0 0 {}',X.replace('type=primitive','type=primitive tcleval=hidden'),X.replace('name=A','name=$dynamic'),X.replace('P=VDD','P=[command]'),X.replace('L 4','Z 4')):self.reject(reader.headerless_xschem,text)
    def test_unknown_graphic_properties_do_not_hide_names(self):
        self.reject(reader.headerless_xschem,X.replace('L 4 0 0 1 1 {}','L 4 0 0 1 1 {name=hidden}'))
    def test_malformed_or_quoted_operator_reject(self):
        for text in (X.replace('K {','{K} {',1),X+'\nK {}',X[:-1],X.replace('L 4','"L" 4'),X.replace('L 4 0','L 4 nan')):self.reject(reader.headerless_xschem,text)
    def test_unresolved_pin_is_retained_diagnostic(self):
        rows=reader.headerless_xschem(X.replace('@@A','@@missing'));self.assertTrue(any(r['kind']=='xschem-source-diagnostic' and r['name']=='missing' for r in rows));self.assertTrue(any(r.get('diagnostic')=='unreferenced-declared-pin-bits' and r['identifiers']==['A'] for r in rows))
    def test_unresolved_attribute_is_retained_diagnostic(self):
        rows=reader.headerless_xschem(X.replace('@P ','@missing '));self.assertTrue(any(r.get('diagnostic')=='unresolved-template-attribute' for r in rows))
    def test_extra_parameter_and_bus_bounds(self):
        for text in (X.replace('extra="P"','extra="P missing"'),X.replace('bus[1:0] dir','bus[100000:0] dir'),X.replace('name=bus[1:0]','name=A[1:0]').replace('name=A dir','name=A[0] dir')):self.reject(reader.headerless_xschem,text)
    def test_arbitrary_format_expression_reject(self):
        for value in ('@name @@A [exec] cell','@name @@A cell extra','@name @@A tcleval(cell)'):
            self.reject(reader.headerless_xschem,X.replace('@name @@A @P @@bus[1] @@bus[0] cell',value))
    def test_qucs_named_items_and_equation_identity(self):
        rows=reader.qucs_component(Q);self.assertEqual([r['name'] for r in rows if r['kind']=='qucs-model'],['C','cap']);param=next(r for r in rows if r['kind']=='qucs-parameter' and r['name']=='C');self.assertEqual(param['equation']['expression_sha256'],hashlib.sha256(b'w*1.e-3').hexdigest());self.assertEqual(param['equation']['referenced_parameters'],['w']);self.assertFalse(param['equation']['evaluated'])
    def test_qucs_external_reference_has_no_order_inference(self):
        row=next(r for r in reader.qucs_component(Q) if r['kind']=='qucs-symbol-reference');self.assertEqual(row['references'],['{LIB}/Capacitor.sym']);self.assertFalse(row['electrical_order_inferred'])
    def test_qucs_identifier_digits_are_not_numeric_literals(self):
        source=Q.replace('name="w"','name="w2"').replace('w*1.e-3','w2*1.e-3+2*w2*40e-12')
        equation=next(r['equation'] for r in reader.qucs_component(source) if r['kind']=='qucs-parameter' and r['name']=='C')
        self.assertEqual(equation['referenced_parameters'],['w2']);self.assertEqual(equation['numeric_literals'],['1.e-3','2','40e-12']);self.assertFalse(equation['evaluated'])
    def test_qucs_comment_and_description_decoys(self):
        rows=reader.qucs_component(Q.replace('description','&lt;Parameter name="fake"/&gt;').replace('<Models>','<!-- <Parameter name="decoy"/> --><Models>'));self.assertFalse(any(r['name'] in ('fake','decoy') for r in rows))
    def test_qucs_unknown_named_children_or_attributes_reject(self):
        for text in (Q.replace('</Parameters>','<ParameterSet name="hidden"/></Parameters>'),Q.replace('<Models>','<Models extra="hidden">'),Q.replace('show="true"','future="hidden" show="true"',1),Q.replace('<SpiceModel','<OtherModel')):self.reject(reader.qucs_component,text)
    def test_qucs_duplicate_and_missing_identity_reject(self):
        for text in (Q.replace('names="cap"','names="cap,cap"'),Q.replace('name="C"','name="w"'),Q.replace('id="Standard"','id=""'),Q.replace('<File>{LIB}/Capacitor.sym</File>','')):self.reject(reader.qucs_component,text)
    def test_qucs_dynamic_equation_and_unknown_parameter_reject(self):
        for value in ('run(w)','w**2','missing*2','"text"','w if w else 0'):
            self.reject(reader.qucs_component,Q.replace('w*1.e-3',value.replace('"','&quot;')))
    def test_qucs_doctype_unknown_schema_and_mixed_content_reject(self):
        for text in ('<!DOCTYPE Component>'+Q,Q.replace('Component.xsd','unknown.xsd'),Q.replace('<Models>','<Models>hidden'),Q.replace('</Models>','</Models>hidden')):self.reject(reader.qucs_component,text)
    def test_guards_survive_optimized_execution(self):
        tree=ast.parse(inspect.getsource(reader));self.assertFalse(any(isinstance(n,ast.Assert) for n in ast.walk(tree)));self.assertFalse(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in ('eval','exec','compile') for n in ast.walk(tree)))

    def test_exact_nine_source_routes(self):
        self.assertEqual(len(reader.REVIEWED_SOURCES),9)
        for (family,repo,path),(archive,parser) in reader.REVIEWED_SOURCES.items():
            row=dict(family=family,repository=repo,repository_path=path,path=path)
            if archive:row['archive']=archive
            self.assertEqual(reader.legacy_symbol_views(row,Q if parser is reader.qucs_component else X),parser(Q if parser is reader.qucs_component else X))
    def test_route_rejects_different_family_revision_path_or_archive(self):
        for (family,repo,path),(archive,parser) in reader.REVIEWED_SOURCES.items():
            row=dict(family=family,repository=repo,repository_path=path,path=path)
            if archive:row['archive']=archive
            for mutation in ({'family':'unreviewed'},{'repository':repo+'-other'},{'path':'other/'+path},{'repository_path':'other/'+path},{'archive':'other.tar.zst'}):
                with self.subTest(path=path,mutation=mutation):self.assertIsNone(reader.legacy_symbol_views(row|mutation,Q if parser is reader.qucs_component else X))
    def test_audit_source_and_process_dispositions(self):
        from scripts import audit_source_dispositions as audit
        for family,repo,path in (('sky130A',reader.SKY_REPOSITORY,'sky130A/libs.tech/xschem/xschem_verilog_import/spm.sym'),('sky130B',reader.SKY_REPOSITORY,'sky130B/libs.tech/xschem/xschem_verilog_import/spm.sym'),('ihp-sg13g2',reader.IHP_REPOSITORY,reader.IHP_PATH)):
            row=dict(family=family,repository=repo,repository_path=path,path=path,mode='100644');text=Q if family=='ihp-sg13g2' else X
            if family!='ihp-sg13g2':row['archive']='common.tar.zst'
            items,records,gaps,_=audit.supplemental([row],{},None,reader=lambda _:text.encode())
            self.assertEqual(gaps,[]);declarations=[i for i in items if i['id'].startswith('supplement:')];self.assertTrue(declarations)
            for item in declarations:
                self.assertEqual(item['sources'],[audit.source_id(row)]);self.assertIn(item['id'],records[0]['item_ids'])
                self.assertEqual(set(item['dispositions']),set(audit.targets(family)))
                self.assertTrue(all(d['qualified'] is False and d['disposition']==('inapplicable' if family=='sky130B' else 'unimplemented') and d['reason'] for d in item['dispositions'].values()))
    def test_unreviewed_paths_remain_inventory_gaps(self):
        from scripts import audit_source_dispositions as audit
        for family,repo,path,text in (('sky130A',reader.SKY_REPOSITORY,'sky130A/unreviewed.sym',X),('ihp-sg13g2',reader.IHP_REPOSITORY,'ihp-sg13g2/unreviewed.xml.old',Q)):
            row=dict(family=family,repository=repo,repository_path=path,path=path,mode='100644')
            if family=='sky130A':row['archive']='common.tar.zst'
            _,records,gaps,_=audit.supplemental([row],{},None,reader=lambda _:text.encode())
            self.assertEqual(records[0]['accounting'],'inventory-gap');self.assertEqual(len(gaps),1);self.assertTrue(gaps[0]['blocks_inventory_completion'])
    def test_reviewed_malformed_symbols_remain_inventory_gaps(self):
        from scripts import audit_source_dispositions as audit
        for family,repo,path,text in (('sky130A',reader.SKY_REPOSITORY,'sky130A/libs.tech/xschem/xschem_verilog_import/spm.sym',X+'\nC {hidden.sym} 0 0 0 0 {}'),('ihp-sg13g2',reader.IHP_REPOSITORY,reader.IHP_PATH,Q.replace('<Models>','<Models hidden="name">'))):
            row=dict(family=family,repository=repo,repository_path=path,path=path,mode='100644')
            if family=='sky130A':row['archive']='common.tar.zst'
            _,records,gaps,_=audit.supplemental([row],{},None,reader=lambda _:text.encode())
            self.assertEqual(records[0]['accounting'],'inventory-gap');self.assertEqual(len(gaps),1);self.assertTrue(gaps[0]['blocks_inventory_completion'])

if __name__=='__main__':unittest.main()
