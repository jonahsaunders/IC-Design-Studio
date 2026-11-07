import ast,inspect,unittest
from scripts import inventory_schematic_views as reader
X='V {}\nG {}\nS {}\nC {devices/iopin} 0 0 0 0 {name=p1 lab=A}\nC {sky130_fd_pr/nfet} 20 -1.5 0 1 {name=X0 w=1.5e+06u l=500000u}'
V='v {xschem version=2.9.8 file_version=1.2\n* License\n}\nG {}\nK {}\nV {}\nS {}\nE {}\nC {devices/title.sym} 0 0 0 0 {name=l1 author="Author prose"}\nC {devices/ipin.sym} 0 0 0 0 {name=p1 lab=bus[3:0] verilog_type=wire}'
class SchematicViewsTests(unittest.TestCase):
    def reject(self,text):
        with self.assertRaises(ValueError):reader.headerless_generated(text)
    def test_exact_instance_symbol_and_literal_dimensions(self):
        row=reader.headerless_generated(X)[-1];self.assertEqual(row['name'],'X0');self.assertEqual(row['symbol_reference'],'sky130_fd_pr/nfet');self.assertEqual(row['literal_properties'],{'w':'1.5e+06u','l':'500000u'});self.assertFalse(row['model_binding_inferred']);self.assertFalse(row['geometry_evaluated'])
    def test_label_and_power_attributes_remain_distinct(self):
        rows=reader.headerless_generated(X.replace('w=1.5e+06u l=500000u','VGND=GND VPWR=VDD'));self.assertEqual(rows[4]['literal_properties'],{'lab':'A'});self.assertEqual(rows[5]['literal_properties'],{'VGND':'GND','VPWR':'VDD'})
    def test_bus_and_hash_label_names_are_literal(self):
        row=reader.headerless_generated(X.replace('lab=A','lab=bus[31:0]'))[4];self.assertEqual(row['literal_properties']['lab'],'bus[31:0]');self.assertEqual(reader.headerless_generated(X.replace('lab=A','lab=a_404_1133#'))[4]['literal_properties']['lab'],'a_404_1133#')
    def test_unknown_dynamic_or_hidden_properties_reject(self):
        for extra in ('model=unknown','lab=[command]','foo=bar','tclcommand="run"','value="C {fake}"'):
            self.reject(X.replace('lab=A',extra))
    def test_duplicate_missing_names_and_properties_reject(self):
        for source in (X.replace('name=X0','name=p1'),X.replace('name=X0',''),X.replace('lab=A','lab=A lab=B'),X.replace('w=1.5e+06u l=500000u','w=1u')):self.reject(source)
    def test_unknown_or_quoted_operator_reject(self):
        for source in (X+'\nN 0 0 1 1 {}',X.replace('C {','T {',1),X.replace('C {','"C" {',1),X+'\n# C {hidden} 0 0 0 0 {name=bad}') :self.reject(source)
    def test_nonempty_header_and_unknown_order_stay_gaps(self):
        for source in (X.replace('V {}','V {reg hidden;}'),X.replace('G {}','K {}'),X.replace('S {}',''),X.replace('V {}','v {xschem version=2.9.8 file_version=1.2}')):self.reject(source)
    def test_truncated_record_and_extra_fields_reject(self):
        for source in (X[:-1],X+' extra',X.replace('20 -1.5 0 1','20 -1.5 4 1'),X.replace('20 -1.5 0 1','20 -1.5 0 2')):self.reject(source)
    def test_numeric_and_source_bounds(self):
        self.reject(X.replace('20 -1.5','1e999999999999999999999999999999999999 -1.5'));self.reject(' '*2_000_001)
    def test_valid_multiline_header_is_byte_preserved(self):
        source='v {xschem version=2.9.8 file_version=1.2\n* Copyright\n* License "text"\n}\nG {}\n'
        prepared,diagnostics=reader.preserve_version_header(source);self.assertEqual(prepared,source);self.assertEqual(diagnostics,[])
    def test_valid_one_line_header_is_unchanged(self):
        source='v {xschem version=3 file_version=1.2}\nG {}\n';self.assertEqual(reader.preserve_version_header(source),(source,[]))
    def test_existing_orphan_diagnostic_is_preserved(self):
        source='v {xschem version=3 file_version=1.2}\n* Copyright\n* License\n\n}\nG {}\n';prepared,diagnostics=reader.preserve_version_header(source);self.assertEqual(diagnostics[0]['line'],5);self.assertEqual(diagnostics[0]['name'],'unmatched-header-comment-close');self.assertTrue(diagnostics[0]['blocks_device_qualification']);self.assertEqual(prepared.splitlines()[4],'')
    def test_star_strings_after_record_are_not_header_comments(self):
        source='v {xschem version=3 file_version=1.2}\nG {}\nT {* fake\n}\n';self.assertEqual(reader.preserve_version_header(source),(source,[]))
    def test_optimized_mode_keeps_guards(self):
        self.assertFalse(any(isinstance(n,ast.Assert) for n in ast.walk(ast.parse(inspect.getsource(reader)))))
    def test_versioned_literal_names_and_metadata(self):
        rows=reader.versioned_literal(V);self.assertEqual(rows[0]['instances'],2);self.assertEqual(rows[-1]['literal_properties'],{'lab':'bus[3:0]','verilog_type':'wire'});self.assertNotIn('Author prose',repr(rows));self.assertIn('author',rows[-2]['metadata_sha256'])
    def test_versioned_embedded_source_is_explicit_gap(self):
        with self.assertRaisesRegex(ValueError,'unenumerated embedded source block V'):reader.versioned_literal(V.replace('V {}','V {wire hidden;}'))
        with self.assertRaisesRegex(ValueError,'embedded or unreviewed component'):reader.versioned_literal(V.replace('lab=bus[3:0]','tclcommand="run"'))
    def test_versioned_graphics_are_hashed_not_declarations(self):
        rows=reader.versioned_literal(V+'\nL 5 0 0 10 10 {}\nP 5 3 0 0 1 1 2 2 {fill=true}\nT {C fake} 0 0 0 0 1 1 {layer=5}')
        self.assertEqual([r['name'] for r in rows if r['kind']=='xschem-graphic-record'],['L','P','T']);self.assertFalse(any(r['name']=='fake' for r in rows))
    def test_versioned_unknown_truncated_and_duplicate_records_fail(self):
        for text in (V+'\nC {devices/ipin.sym} 0 0 0 0 {name=p1 lab=B}',V+'\nP 5 4 0 0 1 1 2 2 {fill=true}',V.replace('name=p1','name=p1 name=p2'),V.replace('G {}','G {}\nG {}')):
            with self.assertRaises(ValueError):reader.versioned_literal(text)
    def test_header_license_data_does_not_introduce_hidden_records(self):
        text=V.replace('* License','* License C fake')
        self.assertEqual(reader.versioned_literal(text)[0]['instances'],2)
        with self.assertRaises(ValueError):reader.versioned_literal(V.replace('* License','C {hidden}'))

    def test_exact_reviewed_source_dispatch_and_mismatch(self):
        self.assertEqual(len(reader.REVIEWED_SOURCES),33)
        path='sky130A/libs.tech/xschem/mips_cpu/controller.sch';row=dict(family='sky130A',repository=reader.SKY_REPOSITORY,repository_path=path,path=path,archive='common.tar.zst')
        self.assertEqual(reader.reviewed_schematic_views(row,V),reader.versioned_literal(V))
        for changed in ({'family':'sky130B'},{'repository':reader.SKY_REPOSITORY+'-other'},{'path':'other.sch'},{'repository_path':'other.sch'},{'archive':'other.tar.zst'}):
            with self.subTest(changed=changed):self.assertIsNone(reader.reviewed_schematic_views(row|changed,V))
    def test_reviewed_source_target_dispositions(self):
        from scripts import audit_source_dispositions as audit
        for family in ('sky130A','sky130B'):
            path=family+'/libs.tech/xschem/mips_cpu/controller.sch';row=dict(family=family,repository=reader.SKY_REPOSITORY,repository_path=path,path=path,archive='common.tar.zst',mode='100644')
            items,records,gaps,_=audit.supplemental([row],{},None,reader=lambda _:V.encode());self.assertEqual(gaps,[])
            for item in (i for i in items if i['id'].startswith('supplement:')):
                self.assertEqual(item['sources'],[path]);self.assertIn(item['id'],records[0]['item_ids']);self.assertEqual(set(item['dispositions']),{'sky130A'})
                d=item['dispositions']['sky130A'];self.assertFalse(d['qualified']);self.assertEqual(d['disposition'],'unimplemented' if family=='sky130A' else 'inapplicable');self.assertTrue(d['reason'])
    def test_embedded_source_cannot_close_from_component_count(self):
        from scripts import audit_source_dispositions as audit
        path='sky130A/libs.tech/xschem/mips_cpu/dmem.sch';row=dict(family='sky130A',repository=reader.SKY_REPOSITORY,repository_path=path,path=path,archive='common.tar.zst',mode='100644')
        _,records,gaps,_=audit.supplemental([row],{},None,reader=lambda _:V.replace('V {}','V {reg hidden;}').encode())
        self.assertEqual(records[0]['accounting'],'inventory-gap');self.assertEqual(len(gaps),1);self.assertIn('unenumerated embedded source block V',gaps[0]['error']);self.assertNotIn('Unterminated',gaps[0]['error'])
    def test_ihp_gap_does_not_mislabel_valid_header(self):
        from scripts import audit_source_dispositions as audit
        row=dict(family='ihp-sg13g2',repository=reader.IHP_REPOSITORY,repository_path=reader.IHP_PATH,path=reader.IHP_PATH,mode='100644')
        _,records,gaps,_=audit.supplemental([row],{},None,reader=lambda _:V.encode());self.assertEqual(records[0]['accounting'],'inventory-gap');self.assertIn('valid multiline version header is preserved',gaps[0]['error']);self.assertTrue(gaps[0]['blocks_inventory_completion'])
    def test_generic_header_fix_retains_historical_diagnostic(self):
        from scripts import audit_source_dispositions as audit
        source='v {xschem version=3 file_version=1.2}\n* License\n}\nC {devices/ipin.sym} 0 0 0 0 {name=p1 lab=A}'
        facts=audit.schematic_views(source);self.assertEqual(facts[0]['name'],'unmatched-header-comment-close');self.assertEqual(facts[0]['line'],3);self.assertTrue(facts[0]['blocks_device_qualification'])

if __name__=='__main__':unittest.main()
