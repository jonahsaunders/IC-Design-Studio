import copy
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts import audit_source_dispositions as audit


def choice(qualification='qualification'):
    return dict(disposition='unimplemented',reason='No complete adapter exists.',**{qualification:False})


def semantic_fixture():
    source=dict(family='gf180mcu',path='models/cap.spice',repository='public/pdk@pin',repository_path='models/cap.spice',git_blob_sha1='a'*40,mode='100644',bytes=20)
    key=audit.source_id(source)
    interface=dict(id=key+':0',source=key,family='gf180mcu',kind='subckt',name='cap',dispositions={t:choice() for t in ('gf180mcuC','gf180mcuD')})
    report=dict(qualified=False,chunk_complete=False,files=[source|dict(role='spice',reason='Parsed source.')],
                sources=[source|dict(id=key,sha256='b'*64,parser='spice',interfaces=[interface['id']])],
                interfaces=[interface],libraries=[],process_options=[])
    return report,[source]


def sky_fixture():
    path='sky130A/libs.ref/pr/spice/cap.spice';decl=dict(kind='spice_subcircuit',name='cap',prefix='X',terminals=['p','n'],parent=None)
    node=dict(node='sky130A',options=['MIM'],stdcells={'cells':'revision'})
    report=dict(qualified=False,chunk_complete=False,files=[dict(path=path,process='sky130A',library='pr',semantic={'declarations':[decl]}),
             dict(path='sky130A/.config/nodeinfo.json',process='sky130A',library='(technology/support)',nodeinfo=node)],
             semantic_reconciliation=dict(analog_catalog=[],identifiers=[dict(process='sky130A',library='pr',name='cap',declarations=[dict(path=path,kind='spice_subcircuit')],disposition='primitive_or_internal_model_without_exact_catalog_binding')],
             process_options=[dict(path='sky130A/.config/nodeinfo.json',process='sky130A',declared_options=['MIM'],options=[dict(category='stdcells',name='cells',upstream_value='revision',release_library_present=False,disposition='technology_integration_metadata_not_library_archive')])]))
    return report


class SourceDispositionsTests(unittest.TestCase):
    def rejected_semantic(self,change):
        report,files=semantic_fixture();change(report)
        with self.assertRaises((ValueError,KeyError)):audit.semantic_items(report,files)

    def test_source_and_item_links_pass_without_device_qualification(self):
        report,files=semantic_fixture();items,_,_=audit.semantic_items(report,files)
        self.assertEqual(len(items),1)
        self.assertTrue(all(not d['qualified'] for d in items[0]['dispositions'].values()))

    def test_missing_graph_file(self):self.rejected_semantic(lambda r:r['files'].clear())
    def test_duplicate_graph_file(self):self.rejected_semantic(lambda r:r['files'].append(copy.deepcopy(r['files'][0])))
    def test_missing_source(self):self.rejected_semantic(lambda r:r['sources'].clear())
    def test_duplicate_interface(self):self.rejected_semantic(lambda r:r['interfaces'].append(copy.deepcopy(r['interfaces'][0])))
    def test_orphan_interface(self):self.rejected_semantic(lambda r:r['sources'][0]['interfaces'].clear())
    def test_source_family_reassignment(self):
        def change(r):r['interfaces'][0].update(family='ihp-sg13g2',dispositions={'ihp-sg13g2':choice()})
        self.rejected_semantic(change)
    def test_missing_target(self):self.rejected_semantic(lambda r:r['interfaces'][0]['dispositions'].pop('gf180mcuD'))
    def test_missing_option_target(self):
        def change(r):r['process_options']=[dict(kind='process-variant',name='C',source_interface=r['interfaces'][0]['id'],dispositions={'gf180mcuC':choice('qualified')})]
        self.rejected_semantic(change)
    def test_unsupported_supported_claim(self):self.rejected_semantic(lambda r:r['interfaces'][0]['dispositions']['gf180mcuC'].update(disposition='supported'))
    def test_missing_reason(self):self.rejected_semantic(lambda r:r['interfaces'][0]['dispositions']['gf180mcuC'].update(reason=''))
    def test_qualification_promotion(self):self.rejected_semantic(lambda r:r.update(qualified=True))
    def test_slib_context_cannot_close_symbols(self):
        report,files=semantic_fixture();extra=files[0]|dict(path='cells/foo.slib',repository_path='cells/foo.slib')
        files.append(extra);report['files'].append(extra|dict(role='other-source-context',reason='Opaque source.'))
        with self.assertRaisesRegex(ValueError,'silently classified'):audit.semantic_items(report,files)

    def test_reviewed_report_pin_rejects_rebound_declaration(self):
        report,_=semantic_fixture();original=gzip.compress(json.dumps(report).encode());digest=hashlib.sha256(original).hexdigest()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'report.json.gz';path.write_bytes(original);audit.checked_report(path,digest)
            report['interfaces'][0]['name']='substituted';path.write_bytes(gzip.compress(json.dumps(report).encode()))
            with self.assertRaisesRegex(ValueError,'changed reviewed report'):audit.checked_report(path,digest)

    def test_changed_blob_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            raw=b'.subckt cap p n\n.ends\n';digest=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
            row=dict(path='cap.spice',git_blob_sha1=digest,bytes=len(raw));path=Path(folder)/digest;path.write_bytes(raw)
            self.assertEqual(audit.blob(row,folder),raw);path.write_bytes(raw.replace(b'cap',b'bad'))
            with self.assertRaisesRegex(ValueError,'changed source blob'):audit.blob(row,folder)

    def test_sky_source_identity_and_conservative_reason(self):
        items,_=audit.sky_items(sky_fixture());self.assertEqual(items[0]['dispositions']['sky130A']['disposition'],'unimplemented')
    def test_sky_substituted_identifier(self):
        report=sky_fixture();report['semantic_reconciliation']['identifiers'][0]['name']='substitute'
        with self.assertRaises(ValueError):audit.sky_items(report)
    def test_sky_real_unrelated_source(self):
        report=sky_fixture();report['semantic_reconciliation']['identifiers'][0]['declarations'][0]['path']='sky130A/.config/nodeinfo.json'
        with self.assertRaises(ValueError):audit.sky_items(report)
    def test_sky_missing_option(self):
        report=sky_fixture();report['semantic_reconciliation']['process_options'][0]['options'].clear()
        with self.assertRaisesRegex(ValueError,'missing SKY option'):audit.sky_items(report)
    def test_sky_changed_option_value(self):
        report=sky_fixture();report['semantic_reconciliation']['process_options'][0]['options'][0]['upstream_value']='unknown'
        with self.assertRaises(ValueError):audit.sky_items(report)
    def test_unknown_sky_code(self):
        with self.assertRaises(ValueError):audit.sky_choice('supported')

    def test_json_cells_pins_and_case_preserved(self):
        rows=audit.json_views('{"cell A":{"pin P":{"direction":"input"}},"cell a":{"pg_pin VSS":{"pg_type":"primary_ground"}}}','cells.lib.json')
        self.assertEqual([(r['kind'],r['name']) for r in rows],[('json-cell','A'),('json-pin','P'),('json-cell','a'),('json-pg_pin','VSS')])
    def test_json_duplicate_and_nonfinite_rejected(self):
        for text in ('{"x":1,"x":2}','{"x":NaN}','{"x":Infinity}','{"x":1e400}'):
            with self.subTest(text=text),self.assertRaises(ValueError):audit.strict_json(text)
    def test_factual_nested_prose_hashed(self):
        out=audit.factual({'x':['long descriptive source text',{'d':'another phrase'}]})
        self.assertNotIn('descriptive',json.dumps(out));self.assertIn('value_sha256',json.dumps(out))
    def test_conditional_json_preserves_libraries_and_options(self):
        text='{\n#ifdef MIM\n"options": [\n"MIM_2P0",\n#endif\n"METAL5"\n],\n"stdcells": {\n"gf_cells": "COMMIT"\n}\n}'
        rows=audit.conditional_json_views(text)
        self.assertEqual({r['name'] for r in rows},{'MIM','MIM_2P0','METAL5','gf_cells'})
    def test_macro_unknown_language_is_gap(self):
        with self.assertRaises(ValueError):audit.macro_views('<klayout-macro><interpreter>opaque</interpreter><text>name</text></klayout-macro>')
    def test_macro_quoted_and_percent_decoys(self):
        text='puts "options[\'fake\']"\nwords = %w{options[\'fake2\']}\nopts["real"] = true\n'
        self.assertEqual([r['name'] for r in audit.ruby_views(text) if r['kind']=='macro-option-reference'],['real'])
    def test_macro_declared_choices(self):
        rows=audit.ruby_views('drc.add_selection("variant", "Variants", %w[A B C D], "Title", "Prompt")\n')
        self.assertEqual(rows[0]['name'],'variant');self.assertEqual(rows[0]['choices'],['A','B','C','D'])
    def test_template_mapping_does_not_execute_regex(self):
        text='templates=[{"regex":danger(),"pcell_library":"Lib","pcell_name":"cap","params":[{"name":"w","type":"string"}],"default_params":{"w":"2u"}}]'
        row=audit.template_views(text)[0];self.assertEqual(row['name'],'cap');self.assertEqual(row['parameters'],[dict(name='w',type='string')]);self.assertNotIn('danger',json.dumps(row))
    def test_qucs_component_model_and_external_symbol(self):
        text='<Component names="cell" library="lib" schematic_id="c"><Models><SpiceModel value="model"/></Models><Symbols><Symbol id="s"><File>{ROOT}/s.sym</File></Symbol></Symbols><Netlists><CDL value="opaque expression"/></Netlists><Parameters><Parameter name="w" default_value="1u"/></Parameters></Component>'
        rows=audit.xml_views(text);self.assertEqual({r['kind'] for r in rows},{'qucs-component','qucs-model','qucs-symbol-reference','qucs-netlist-template','qucs-parameter'})
        self.assertNotIn('opaque expression',json.dumps(rows))
    def test_digital_label_not_invented_pin_order(self):
        text='<circuit><version>2</version><visualElements><visualElement><elementName>In</elementName><elementAttributes><entry><string>Label</string><string>A</string></entry></elementAttributes><pos x="0" y="10"/></visualElement></visualElements><wires/></circuit>'
        row=audit.xml_views(text)[1];self.assertEqual(row['label'],'A');self.assertIn('not-inferred',row['terminal_order'])
    def test_unknown_xml_is_gap(self):
        with self.assertRaises(ValueError):audit.xml_views('<unknown><name>device</name></unknown>')

    def test_qucs_aliases_are_separate_named_items(self):
        rows=audit.xml_views('<Component names="nmoscl_2, nmoscl_4"/>')
        self.assertEqual([r['name'] for r in rows],['nmoscl_2','nmoscl_4'])
    def test_digital_inverted_label_preserved(self):
        text='<circuit><version>2</version><visualElements><visualElement><elementName>Out</elementName><elementAttributes><entry><string>Label</string><string>~Q</string></entry></elementAttributes><pos x="0" y="10"/></visualElement></visualElements></circuit>'
        self.assertEqual(audit.xml_views(text)[1]['label'],'~Q')
    def test_macro_hidden_code_is_gap(self):
        with self.assertRaisesRegex(ValueError,'prolog'):audit.macro_views('<klayout-macro><interpreter>python</interpreter><prolog>declare()</prolog><text>pass</text></klayout-macro>')
    def test_ruby_block_comment_does_not_invent_mapping(self):
        text='=begin\nAuthor\'s note "\nconnect(fake, fake2)\n=end\nconnect(real, other)\n'
        rows=audit.ruby_views(text);self.assertEqual(len(rows),1);self.assertEqual(rows[0]['argument_identifiers'],['other','real'])
    def test_ruby_block_comment_marker_inside_string(self):
        text='puts "\n=begin\nnot code\n=end\n"\nconnect(real, other)\n'
        self.assertEqual([r['name'] for r in audit.ruby_views(text)],['connect'])
    def test_ruby_command_literal_is_opaque_not_fake_code(self):
        rows=audit.ruby_views('value = `echo #{pid} connect(fake, fake2)`\nconnect(real, other)\n')
        self.assertEqual([r['argument_identifiers'] for r in rows if r['kind']=='ruby-mapping-or-dependency'],[['other','real']])
        self.assertEqual(sum(r['kind']=='ruby-command-literal' for r in rows),1)
    def test_paramset_names_and_parameter_overrides(self):
        text='// paramset fake target\nparamset real base\n parameter real w = 1u;\n .width = w;\nendparamset\n'
        row=audit.veriloga_extra(text)[0];self.assertEqual((row['name'],row['base_model']),('real','base'));self.assertEqual(row['parameters'][0]['name'],'w');self.assertEqual(row['overrides'][0]['name'],'width')
        with self.assertRaises(ValueError):audit.veriloga_extra(text.replace('endparamset',''))
    def test_make_targets_keep_literal_library_names(self):
        rows=audit.make_views('TARGETS = cap \\\n resistor\nPLUGINS = $(TARGETS:%=%.so)\nexport TARGETS\nall: $(PLUGINS)\n\tbuild\n')
        self.assertEqual(rows[0]['literal_tokens'],['cap','resistor']);self.assertIsNone(rows[1]['literal_tokens']);self.assertEqual(rows[-1]['kind'],'build-target-template')
    def test_xschem_header_diagnostic_retains_real_instance(self):
        text='v {xschem version=3.4.7}\n* Author\'s note\n}\nG {}\nC {dev.sym} 0 0 0 0 {name=X1 model=real}\n'
        rows=audit.schematic_views(text);self.assertEqual(rows[0]['kind'],'source-diagnostic');self.assertEqual(rows[1]['name'],'X1')
        with self.assertRaises(ValueError):audit.schematic_views(text+'}\n')
    def test_unknown_family_rejected(self):
        with self.assertRaises(ValueError):audit.targets('unknown')
        self.assertEqual(audit.targets('sky130B'),('sky130A',))
    def test_opaque_production_view_is_gap_with_reason(self):
        raw=b'opaque named device';digest=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        row=dict(family='gf180mcu',path='production.opaque',repository='public/pdk@pin',repository_path='production.opaque',mode='100644',bytes=len(raw),git_blob_sha1=digest)
        items,records,gaps,_=audit.supplemental([row],{},None,reader=lambda _:raw)
        self.assertEqual(len(gaps),1);self.assertTrue(gaps[0]['blocks_inventory_completion']);self.assertEqual(records[0]['accounting'],'inventory-gap');self.assertEqual(items[0]['dispositions']['gf180mcuD']['disposition'],'unimplemented')


if __name__=='__main__':unittest.main()
