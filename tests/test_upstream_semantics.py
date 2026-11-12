"""Adversarial semantic source controls; no network or upstream execution."""
import tempfile
import struct
import unittest
from collections import defaultdict
from pathlib import Path

from scripts.inventory_upstream_semantics import (
    authenticated_bytes, dependency_edges, dispositions, extraction, interpret, gds_interfaces,
    lef, liberty, parse_spice_interfaces, pcells, process_options,
    reconcile_libraries, slib_symbols, source_kind, symbol, verilog,
)
from scripts.reconcile_primitive_inventory import git_hash


class UpstreamSemanticsTests(unittest.TestCase):
    def test_slib_preserves_declared_identity_case_and_pin_sequence(self):
        text = '''/* symbol("fake") { pin("NO",0,0,R); } */
symbol ("Adder_2") {
 set_minimum_boundary (-120*SCALE,-40*SCALE,120*SCALE,40*SCALE);
 line (-100*SCALE,-40*SCALE,-100*SCALE,40*SCALE);
 pin ("Z",130*SCALE,20*SCALE,ANY_ROTATION);
 pin ("a",-130*SCALE,-20*SCALE,ANY_ROTATION);
 pin ("A",-130*SCALE,20*SCALE,ANY_ROTATION);
} // pin("BAD",0,0,R);
'''
        rows = interpret('slib-symbol', text, 'misleading_filename.slib')
        self.assertEqual([r['name'] for r in rows], ['Adder_2'])
        self.assertEqual(rows[0]['terminals'], ['Z', 'a', 'A'])
        self.assertEqual([p['declaration_index'] for p in rows[0]['terminal_declarations']], [0, 1, 2])
        self.assertEqual(rows[0]['terminal_declarations'][0]['line'], 5)
        self.assertEqual(rows[0]['terminal_order'], 'source-declaration-order-not-electrical-port-order')
        self.assertFalse(rows[0]['graphical_expressions_evaluated'])
        self.assertNotIn('pins', rows[0])

    def test_slib_multiple_symbols_are_all_retained(self):
        rows = slib_symbols('symbol("first"){pin("D[1]",0,0,R);} symbol("second"){pin("B",0,0,R);}')
        self.assertEqual([(r['name'], r['terminals']) for r in rows], [('first', ['D[1]']), ('second', ['B'])])

    def test_slib_dynamic_or_unknown_calls_are_explicit_errors(self):
        for text in ('symbol(dynamic){}', 'symbol("C"){pin(dynamic,0,0,R);}',
                     'symbol("C"){generate_pins();}', 'symbol("C"){system("execute");}',
                     'symbol("C"){pin("P",position(),0,R);}',
                     'if(enabled){symbol("C"){pin("P",0,0,R);}}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                slib_symbols(text)

    def test_slib_duplicate_and_truncated_records_fail(self):
        for text in ('symbol("C"){} symbol("C"){}',
                     'symbol("C"){pin("P",0,0,R);pin("P",1,0,R);}',
                     'symbol("C"){pin("P",0,0,R);', 'symbol("C"){pin("P",0,,R);}',
                     'symbol("C"){pin("P",0,0);}', 'symbol("C"){pin("P",0,0,R)}',
                     'symbol("C"){} /* unterminated', 'symbol("C){pin("P",0,0,R);}',
                     '/* symbol("decoy"){} */'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                slib_symbols(text)

    def test_slib_quoted_pin_decoy_and_escaped_identity_do_not_create_pins(self):
        with self.assertRaises(ValueError):
            slib_symbols('symbol("C"){text("pin(\\\"FAKE\\\",0,0,R)",0,0);pin("P",0,0,R);}')
        with self.assertRaises(ValueError):
            slib_symbols(r'symbol("C"){pin("\u0050",0,0,R);}')

    def test_slib_library_view_preserves_order_without_support_claim(self):
        item = slib_symbols('symbol("C"){pin("B",0,0,R);pin("A",0,0,R);}')[0]
        item.update(id='symbol:0', source='gf180-ecosystem:libraries/L/latest/a.slib',
                    family='gf180-ecosystem', library_scope='L')
        row = reconcile_libraries([item], dict(profiles={}))[0]
        self.assertEqual(row['views'], {'slib-symbol': ['symbol:0']})
        self.assertEqual([p['name'] for p in row['symbol_terminal_declarations'][0]['pins']], ['B', 'A'])
        self.assertEqual(row['disposition'], 'unimplemented')
        self.assertIn('subckt', row['missing_views'])
        entry = dict(model='C', prefix='X', source='a.slib', pin_order=['B','A'], emit_parameters={}, unavailable='')
        package = dict(by_blob={'blob':['a.slib']}, catalog_names={'c':{'device':entry}},
                       catalog_sources={'a.slib':{'device':entry}}, active_index={})
        result = dispositions(dict(family='gf180-ecosystem', git_blob_sha1='blob'), item,
                              {'gf180mcuC':package, 'gf180mcuD':package})
        for target in ('gf180mcuC', 'gf180mcuD'):
            self.assertEqual(result[target]['disposition'], 'unimplemented')
            self.assertIn('not an electrical port order', result[target]['reason'])

    def test_gds_block_padding_is_narrowly_validated(self):
        def record(kind,dtype=0,data=b''):
            return struct.pack('>HBB',4+len(data),kind,dtype)+data
        core=record(0,2,b'\x00\x03')+record(1,2,b'\x00'*24)+record(2,6,b'LIB\x00')+record(5,2,b'\x00'*24)+record(6,6,b'CELL')+record(7)+record(4)
        self.assertEqual(gds_interfaces(core)[0][0]['name'],'CELL')
        padded=core+b'\x00'*((-len(core))%2048)
        self.assertEqual(gds_interfaces(padded)[1],len(padded)-len(core))
        for invalid in (core+b'\x00',core+b'AB',core[:-4],padded+b'\x00'*2048):
            with self.assertRaises(ValueError):gds_interfaces(invalid)

    def test_changed_missing_and_symlink_sources_fail(self):
        data = b'.subckt a p n\n.ends a\n'
        row = dict(path='models/a.spice', mode='100644', bytes=len(data), git_blob_sha1=git_hash('blob',data))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/row['git_blob_sha1']
            with self.assertRaises(FileNotFoundError):authenticated_bytes(row,directory)
            path.write_bytes(data)
            self.assertEqual(authenticated_bytes(row,directory),data)
            path.write_bytes(data+b'* changed')
            with self.assertRaises(ValueError):authenticated_bytes(row,directory)
            with self.assertRaises(ValueError):authenticated_bytes(dict(row,mode='120000'),directory)

    def test_liberty_preserves_pvt_pins_and_ignores_string_decoys(self):
        text = '''library("L") { nom_voltage:1.2; nom_temperature:25;
        operating_conditions(tt) { voltage:1.2; temperature:25; process:1; }
        cell(C) { pin(A) { comment:"direction: output; cell(FAKE) { }"; direction:input; }
        pg_pin(VDD) { pg_type:primary_power; } } }'''
        rows = liberty(text)
        self.assertEqual([r['name'] for r in rows if r['kind']=='cell'],['C'])
        self.assertEqual(next(r for r in rows if r['name']=='A')['attributes']['direction'],'input')
        self.assertEqual(rows[0]['pvt']['nom_voltage'],'1.2')
        self.assertEqual(next(r for r in rows if r['kind']=='pin')['context'][-1]['name'],'C')

    def test_liberty_multiline_escaped_strings_and_truncation(self):
        rows=liberty('cell(A) { statetable("X", "Y") { table:"a \\\n b"; } pin(P) { direction:input; } }')
        self.assertEqual([r['name'] for r in rows],['A','P'])
        for text in ('cell(A) {', 'cell(A) {} }', 'cell(A) { comment:"unterminated; }'):
            with self.assertRaises(ValueError):liberty(text)

    def test_lef_token_format_and_property_definition(self):
        text='PROPERTYDEFINITIONS MACRO label STRING ; END PROPERTYDEFINITIONS\nMACRO real # comment\n PIN A PORT LAYER M1 ; END END A END real'
        self.assertEqual(lef(text)[0]['pins'],['A'])
        self.assertEqual(lef('MACRO real PIN A PORT END END A END real')[0]['name'],'real')
        with self.assertRaises(ValueError):lef('MACRO real PIN A PORT END END real')
        with self.assertRaises(ValueError):lef('MACRO real')

    def test_verilog_strings_comments_and_numeric_literals(self):
        rows=verilog('module actual(A); wire q=1\'b0; initial $display("module fake(F); endmodule"); endmodule // module nope(N);')
        self.assertEqual([r['name'] for r in rows],['actual'])
        with self.assertRaises(ValueError):verilog('module actual(A); initial $display("unterminated module fake(F);')

    def test_ruby_decoys_dynamic_mapping_and_unreviewed_literals(self):
        text='puts "extract_devices(mos4(\'FAKE\'), {})"\nx=1 # extract_devices(mos4(\'BAD\'), {})\nextract_devices(MOS.new("nmos"), {"G" => gate, "S" => source})'
        rows=extraction(text)
        self.assertEqual([r['name'] for r in rows],['nmos'])
        self.assertEqual(rows[0]['layer_roles'],['G','S'])
        self.assertTrue(extraction('extract_devices(factory(name), {})')[0]['dynamic'])
        for text in ("puts %q{extract_devices(mos4('FAKE'), {})}","x=<<~TEXT\nextract_devices(mos4('FAKE'), {})\nTEXT"):
            with self.assertRaises(ValueError):extraction(text)

    def test_process_variant_tokens_inside_quotes_cannot_be_supported(self):
        branch='if options["variant"] == "C"\n$metal_top="9K"\n$metal_level="5LM"\n$mim_option="B"\nend'
        self.assertEqual(extraction("puts '"+branch+"'"),[])
        self.assertEqual(extraction(branch)[0]['options'],dict(metal_top='9K',metal_level='5LM',mim_option='B'))

    def test_pcell_ast_never_executes_and_retains_expression_defaults(self):
        text='''raise RuntimeError("must never execute")
moduleNames = ['inductor2_code', 'bondpad_code']
class Device:
 def init(self):
  self.param("width", self.TypeDouble, "Width", default=minimum)
  self.handle.add_choice("5V", "5V")
  self.layout().register_pcell("device", Device())
'''
        rows=pcells(text)
        self.assertEqual({r['name'] for r in rows if r['kind']=='pcell-registration'},{'inductor2','bondpad','device'})
        default=next(r for r in rows if r['kind']=='pcell-parameters')['parameters'][0]['keywords']['default']
        self.assertEqual(default['referenced_names'],['minimum'])
        self.assertEqual(default['expression_kind'],'Name')

    def test_descriptive_pcell_literals_are_fingerprints_not_source_text(self):
        rows=pcells('class C:\n def f(self):\n  self.param("w", self.TypeDouble, "Long descriptive parameter prose", default=0.5, unit="um")\n')
        args=rows[0]['parameters'][0]['arguments']
        self.assertEqual(args[1]['literal_type'],'str')
        self.assertNotIn('literal',args[1])

    def test_reused_pcell_choice_handle_tracks_its_parameter(self):
        text='class C:\n def f(self):\n  self.h=self.param("voltage",self.TypeList,"Voltage")\n  self.h.add_choice("5V","5V")\n  self.h=self.param("metal",self.TypeList,"Metal")\n  self.h.add_choice("M5","M5")\n'
        choices=pcells(text)[0]['choices']
        self.assertEqual([c['parameter'] for c in choices],['voltage','metal'])

    def test_zero_port_cdl_and_empty_bondpad_are_not_models(self):
        rows=interpret('cdl','.subckt helper\n.ends\n.subckt bondpad PAD\n.param size=80u\n.ends bondpad\n','x.cdl')
        self.assertEqual(rows[0]['pins'],[])
        self.assertEqual(rows[1]['element_count'],0)
        self.assertEqual(rows[1]['local_parameters'],['size'])

    def test_wrong_endl_name_remains_explicit_source_diagnostic(self):
        parsed,diagnostics=parse_spice_interfaces('.lib actual\n.model diode d\n.endl other\n','a.spice')
        self.assertEqual(parsed['definitions'][0]['name'],'diode')
        self.assertTrue(diagnostics[0]['blocks_semantic_completion'])
        with self.assertRaises(ValueError):parse_spice_interfaces('.lib a\n.model d d\n','a.spice')

    def test_zero_terminal_veriloga_preserves_empty_interface(self):
        rows=interpret('veriloga','module corner();\nendmodule\n','corner.va')
        self.assertEqual(rows[0]['terminals'],[])

    def test_xschem_pin_order_and_qucs_coordinates_remain_distinct(self):
        text='G {}\nv {xschem version=3.1}\nK {type=nmos}\nB 5 0 0 1 1 {name=G sim_pinnumber=2}\nB 5 0 0 1 1 {name=D sim_pinnumber=1}\n'
        self.assertEqual(symbol(text)[0]['pins'],['D','G'])
        rows=symbol('<PortSym x="1" y="2" /><Text text="G" />')
        self.assertNotIn('pins',rows[0])
        self.assertIn('terminal_mapping',rows[0])

    def test_all_production_view_types_selected(self):
        for path,kind in [('cells/a.lib','liberty'),('cells/a.slib','slib-symbol'),('libs.ref/a.cdl','cdl'),('libs.ref/a.lef','lef'),('libs.ref/a.gds','gds'),('libs.ref/a.v','verilog'),('libs.tech/verilog-a/a.va','veriloga')]:
            self.assertEqual(source_kind(dict(path=path)),kind)
        self.assertIsNone(source_kind(dict(path='tests/a.spice')))

    def test_missing_views_case_and_bus_context_are_explicit(self):
        base=dict(source='gf180-ecosystem:libraries/L/latest/a.lib',family='gf180-ecosystem',library_scope='L',line=1)
        items=[dict(base,id='1',kind='cell',name='Gate'),dict(base,id='2',kind='lef-macro',name='gate',pins=['A']),
               dict(base,id='3',kind='bus',name='D',context=[dict(kind='cell',name='Gate')],attributes=dict(direction='input'))]
        profiles=dict(profiles={'gf180':dict(target='gf180mcuC',corners={'typical':['lib/L__tt.lib']})})
        rows=reconcile_libraries(items,profiles)
        gate=next(r for r in rows if r['name']=='Gate')
        self.assertEqual(gate['case_distinct_candidates'],['gate'])
        self.assertIn('lef-macro',gate['missing_views'])
        self.assertEqual(gate['liberty_terminal_declarations'][0]['pins'][0]['kind'],'bus')
        self.assertEqual(gate['disposition'],'unimplemented')

    def test_missing_includes_remain_unimplemented(self):
        files=[dict(family='gf180mcu',path='models/root.spice',repository='R@1')]
        items=[dict(id='a',family='gf180mcu',source='gf180mcu:models/root.spice',kind='model-include',name='missing.spice')]
        self.assertEqual(dependency_edges(items,files)[0]['disposition'],'unimplemented')

    def test_wrong_family_pvt_basename_never_becomes_supported(self):
        item=dict(kind='library',name='unrelated',source='ihp-sg13g2:unrelated/L__tt_025C_5v00.lib',id='x',family='ihp-sg13g2',library_scope='L',pvt={'nom_voltage':'99','nom_temperature':'25'})
        profiles=dict(profiles={'gf180':dict(target='gf180mcuC',corners={'typical':['lib/L__tt_025C_5v00.lib']},orfs={'corners':{'typical':{'PWR_NETS_VOLTAGES':'VDD 5.0'}}})})
        rows=process_options([item],profiles)
        self.assertEqual(rows[0]['selected_by_profiles'],[])
        self.assertEqual(rows[0]['disposition'],'unimplemented')
        item['family']='gf180-ecosystem'
        item['source']='gf180-ecosystem:libraries/L/latest/liberty/L__tt_025C_5v00.lib'
        rows=process_options([item],profiles)
        self.assertFalse(rows[0]['selected_by_profiles'][0]['declared_pvt_compatible'])
        self.assertEqual(rows[0]['disposition'],'unimplemented')

    def test_physical_variant_inapplicability_requires_explicit_target_difference(self):
        profiles=dict(profiles={key:dict(target=target,orfs={'variables':{'KVALUE':thickness,'METAL_OPTION':'5LM_1TM'}})
                               for key,target,thickness in [('gf180','gf180mcuC','9'),('gf180d','gf180mcuD','11')]})
        item=dict(kind='process-variant',name='C',id='x',options=dict(metal_top='9K',metal_level='5LM',mim_option='B'))
        row=process_options([item],profiles)[0]
        self.assertEqual(row['dispositions']['gf180mcuC']['disposition'],'supported')
        self.assertEqual(row['dispositions']['gf180mcuD']['disposition'],'inapplicable')
        item['options']['metal_top']='11K'
        self.assertEqual(process_options([item],profiles)[0]['dispositions']['gf180mcuC']['disposition'],'unimplemented')

    def test_name_match_wrong_prefix_or_order_is_not_supported(self):
        entry=dict(model='foo',prefix='X',source='foo.sym',pin_order=['a','b'],emit_parameters={},unavailable='')
        definition=dict(id='definition',source='foo.spice',name='foo',kind='subckt',line=1,prefix='X')
        pack=dict(by_blob={'blob':['foo.spice']},catalog_names={'foo':{'device':entry}},catalog_sources={},
                  active_index={('foo.spice','foo','subckt',1):[definition]})
        bundled={'gf180mcuC':pack,'gf180mcuD':pack}
        row=dict(family='gf180mcu',git_blob_sha1='blob')
        interface=dict(kind='subckt',name='foo',line=1,prefix='D',pins=['a','b'],parameters=[],element_count=1)
        self.assertEqual(dispositions(row,interface,bundled)['gf180mcuC']['disposition'],'unimplemented')
        interface.update(prefix='X',pins=['b','a'])
        self.assertEqual(dispositions(row,interface,bundled)['gf180mcuC']['disposition'],'unimplemented')
        interface['pins']=['a','b']
        self.assertEqual(dispositions(row,interface,bundled)['gf180mcuC']['disposition'],'supported')
        interface['element_count']=0
        self.assertEqual(dispositions(row,interface,bundled)['gf180mcuC']['disposition'],'unimplemented')


if __name__ == '__main__':unittest.main()
