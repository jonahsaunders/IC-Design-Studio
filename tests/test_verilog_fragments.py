import ast,hashlib,inspect,json,unittest
from scripts import inventory_verilog_fragments as reader
def schematic_text(body,extra=''):
    escaped=body.replace('{','\\{').replace('}','\\}')
    return 'v {xschem version=2.9.8 file_version=1.2\n* License\n}\nG {}\nK {}\nV {'+escaped+'}\nS {}\nE {}\nC {devices/ipin.sym} 0 0 0 0 {name=p1 lab=a[3:0]}\nC {devices/architecture.sym} 0 0 0 0 { nothing here, use global schematic properties }\n'+extra
class VerilogFragmentTests(unittest.TestCase):
    def reject(self,source):
        with self.assertRaises(ValueError):reader.fragment(source)
    def test_all_data_declarations_ranges_initializers_and_arrays(self):
        rows=reader.fragment("wire [31:0] a, b=32'h00; reg [7:0] memory[63:0];")
        data=[r for r in rows if r['kind']=='verilog-data-declaration'];self.assertEqual([r['name'] for r in data],['a','b','memory']);self.assertEqual(data[1]['initializer']['numeric_literals'],["32'h00"]);self.assertEqual(data[2]['unpacked_range']['numeric_literals'],['63','0'])
    def test_digit_identifier_not_numeric_literal(self):
        row=reader.fragment('wire w2 = w1 + 1;')[-1];self.assertEqual(row['initializer']['identifier_references'],['w1']);self.assertEqual(row['initializer']['numeric_literals'],['1'])
    def test_comments_and_strings_do_not_invent_declarations(self):
        rows=reader.fragment('/* wire fake; */ // reg decoy;\ninitial $display("wire ghost; begin : phantom end");');self.assertFalse(any(r['name'] in ('fake','decoy','ghost','phantom') for r in rows));self.assertEqual(len([r for r in rows if r['kind']=='verilog-system-task-reference']),1)
    def test_string_payload_is_hashed_not_copied(self):
        rows=reader.fragment('initial $display("message %t", $time);');self.assertNotIn('message %t',json.dumps(rows));self.assertEqual(rows[-1]['arguments'][0]['string_identities'][0]['sha256'],hashlib.sha256(b'"message %t"').hexdigest())
    def test_named_scopes_preserve_same_name_declarations(self):
        rows=reader.fragment('initial begin : outer reg a; begin : inner reg a; end end');data=[r for r in rows if r['kind']=='verilog-data-declaration'];self.assertEqual(len(data),2);self.assertNotEqual(data[0]['scope'],data[1]['scope']);self.assertEqual(data[1]['scope'][-2:],['outer','inner'])
    def test_if_else_contexts_are_distinct(self):
        rows=reader.fragment('always @(clk) begin if(en) out=a; else out=b; end');assign=[r for r in rows if r['kind']=='verilog-procedural-assignment'];self.assertEqual([r['control_context'][-1]['branch'] for r in assign],['then','else'])
    def test_case_wildcards_labels_and_default(self):
        rows=reader.fragment("always @(op) casex(op) 3'b1xx: out=1; default: out=0; endcase");branches=[r for r in rows if r['kind']=='verilog-case-branch'];self.assertEqual(branches[0]['labels'][0]['numeric_literals'],["3'b1xx"]);self.assertEqual(branches[1]['name'],'default');self.assertEqual([r['control_context'][-1]['branch'] for r in rows if r['kind']=='verilog-procedural-assignment'],[0,'default'])
    def test_concatenation_repetition_and_reduction(self):
        rows=reader.fragment("assign {carry,out} = { {3{1'b0}}, a[1:0] }; assign zero=~|out;");self.assertEqual(rows[1]['target_names'],['carry','out']);self.assertEqual(rows[1]['value']['numeric_literals'],['3',"1'b0",'1','0']);self.assertEqual(rows[2]['value']['operators'],['~|'])
    def test_array_index_is_not_assignment_target_name(self):
        row=reader.fragment('always @(clk) memory[addr]=data;')[-1];self.assertEqual(row['name'],'memory');self.assertEqual(row['target_names'],['memory']);self.assertEqual(row['target']['identifier_references'],['memory','addr'])
    def test_continuous_occurrences_not_collapsed(self):
        rows=reader.fragment('assign out=a; assign out=b;');self.assertEqual([r['name'] for r in rows if r['kind']=='verilog-continuous-assignment'],['out','out'])
    def test_event_edges_or_and_macro_delay(self):
        rows=reader.fragment('always @(posedge clk or negedge rst) out=a; initial begin #`DELAY out=0; @(negedge clk) $finish; end');process=next(r for r in rows if r['kind']=='verilog-process');self.assertEqual([r['edge'] for r in process['events']],['posedge','negedge']);delay=next(r for r in rows if r['kind']=='verilog-delay-control');self.assertEqual(delay['delay']['macro_references'],['DELAY'])
    def test_numeric_source_tokens_are_not_evaluated(self):
        row=reader.fragment("wire a=32'h0000_00FF; wire b=1e400;")[-1];self.assertEqual(row['initializer']['numeric_literals'],['1e400']);self.assertFalse(row['evaluated'])
    def test_invalid_based_literals_reject(self):
        for source in ("wire a=2'b22;","wire a=4'o9;","wire a=8'hGH;","wire a=1'dA;"):self.reject(source)
    def test_unknown_declaration_and_directive_grammar_reject(self):
        for source in ('module hidden(input a); endmodule','function hidden; endfunction','`include "other.v"','`define F(x) x','generate wire hidden; endgenerate','parameter P=1;'):self.reject(source)
    def test_unknown_statement_and_function_call_reject(self):
        for source in ('initial for(i=0;i<4;i=i+1) a=0;','wire a=run(b);','initial $system("run");','wire a=$unknown;'):self.reject(source)
    def test_dynamic_or_escaped_identifiers_remain_unreviewed(self):
        for source in ('wire \\escaped.name ;','wire {dynamic};','assign top.sub=1;'):self.reject(source)
    def test_missing_delimiters_and_trailing_tokens_reject(self):
        for source in ('wire a','always @(clk) begin a=1;','assign a=(b+1;','initial case(a) 1:a=0;','wire a; hidden'):self.reject(source)
    def test_unterminated_comment_and_string_reject(self):
        for source in ('/* wire hidden;','initial $display("wire hidden;);'):self.reject(source)
    def test_unreviewed_multiline_tokens_reject_before_source_lines_can_shift(self):
        for source in ('initial $display("one\\\ntwo");\nwire actual;',"wire [3\n'd1:0] x;\nwire actual;"):
            self.reject(source)
        rows=reader.fragment('initial $display("one\\ntwo");\nwire actual;');self.assertEqual(rows[-1]['line'],2)
    def test_quoted_keyword_or_unknown_character_reject(self):
        for source in ('"wire" a;','wire a=1; \\','wire a=1; `'):self.reject(source)
    def test_depth_and_token_bounds_remain_clean_errors(self):
        self.reject('wire a='+'('*70+'1'+')'*70+';');self.reject('assign '+'{'*70+'a'+'}'*70+'=1;');self.reject(' '*100001)
    def test_guard_checks_survive_optimized_python(self):
        tree=ast.parse(inspect.getsource(reader));self.assertFalse(any(isinstance(n,ast.Assert) for n in ast.walk(tree)));self.assertFalse(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in ('eval','exec','compile') for n in ast.walk(tree)))
    def test_macro_tokens_cannot_masquerade_as_keywords(self):
        for source in ('`wire hidden;', '`reg hidden;', '`always begin a=0; end','initial `begin a=1; `end','initial if(a) a=0; `else a=1;', 'always @(`posedge clk) a=1;', 'always @(clk `or rst) a=1;', 'initial begin a=1; `end'):
            with self.subTest(source=source):self.reject(source)
        row=reader.fragment('wire a=`wire;')[-1];self.assertEqual(row['initializer']['macro_references'],['wire'])
    def test_flat_bounded_expression_does_not_escape_through_recursive_readback(self):
        row=reader.fragment('wire a='+'b+'*1500+'b;')[-1];self.assertEqual(row['initializer']['identifier_references'],['b']);self.assertEqual(len(row['initializer']['operators']),1500)
    def test_object_macros_preserve_literals_and_reject_function_forms(self):
        rows=reader.macro_declarations('`define A 10 // comment\n`define B 5');self.assertEqual([(r['name'],r['value_literal']) for r in rows],[('A','10'),('B','5')])
        for text in ('`define F(x) x','`include "other.v"','`define A run()','`define A 1\n`define A 2'):
            with self.assertRaises(ValueError):reader.macro_declarations(text)
    def test_full_schematic_records_and_anonymous_annotation(self):
        rows=reader.schematic(schematic_text('wire b; assign b=a[0];'));self.assertEqual(rows[0]['instances'],2);anonymous=next(r for r in rows if r['kind']=='xschem-instance' and r['declared_instance_name'] is None);self.assertEqual(anonymous['symbol_reference'],'devices/architecture.sym');self.assertIn('annotation',anonymous['metadata_sha256'])
    def test_macro_source_and_target_linkage(self):
        extra='C {devices/verilog_preprocessor.sym} 0 0 0 0 {name=s1 string="`define DELAY 5\n"}'
        rows=reader.schematic(schematic_text('always begin #`DELAY a=0; end',extra));link=next(r for r in rows if r['kind']=='verilog-macro-reference');self.assertEqual((link['name'],link['declaration_instance']),('DELAY','s1'));self.assertFalse(link['expanded'])
        with self.assertRaisesRegex(ValueError,'unresolved embedded macro'):reader.schematic(schematic_text('always begin #`MISSING a=0; end',extra))
    def test_repeated_assignment_is_retained_without_correction(self):
        rows=reader.schematic(schematic_text('assign out=a; assign out=a;'));diagnostic=next(r for r in rows if r['kind']=='verilog-source-diagnostic');self.assertEqual(diagnostic['name'],'out');self.assertEqual(len(diagnostic['source_lines']),2);self.assertFalse(diagnostic['correction_inferred']);self.assertFalse(diagnostic['electrical_validity_inferred'])
    def test_graphic_text_does_not_create_verilog_declaration(self):
        rows=reader.schematic(schematic_text('wire real_name;','T {wire fake;} 0 0 0 0 1 1 {layer=5}'));self.assertEqual([r['name'] for r in rows if r['kind']=='verilog-data-declaration'],['real_name'])
    def test_literal_source_font_metadata_is_accounted(self):
        rows=reader.schematic(schematic_text('wire a;','T {data} 0 0 0 0 1 1 {font=monospace}'));self.assertEqual(len([r for r in rows if r['kind']=='xschem-graphic-record']),1)
        with self.assertRaises(ValueError):reader.schematic(schematic_text('wire a;','T {data} 0 0 0 0 1 1 {font=dynamic()}'))
    def test_unknown_schematic_embedded_properties_and_records_reject(self):
        for extra in ('C {devices/code.sym} 0 0 0 0 {name=s1 string="`define H 1"}','C {devices/architecture.sym} 0 0 0 0 {unknown body}','N 0 0 1 1 {}','C {devices/ipin.sym} 0 0 0 0 {name=p1 lab=B}'):
            with self.assertRaises(ValueError):reader.schematic(schematic_text('wire a;',extra))
    def test_nonverilog_block_and_truncated_outer_record_reject(self):
        source=schematic_text('wire a;')
        with self.assertRaises(ValueError):reader.schematic(source.replace('S {}','S {.model hidden nmos}'))
        with self.assertRaises(ValueError):reader.schematic(source.rstrip()[:-1])

    def route(self,raw,family='sky130A'):
        row=dict(family=family,repository='official/fixed@revision',repository_path=family+'/mips.sch',path=family+'/mips.sch',archive='common.tar.zst',mode='100644')
        key=tuple(row.get(k) for k in ('family','repository','repository_path','path','archive'))
        return row,{key:hashlib.sha256(raw).hexdigest()}
    def test_exact_identity_and_all_source_bytes_are_required(self):
        from unittest.mock import patch
        raw=schematic_text('wire a;').encode();row,registry=self.route(raw)
        with patch.object(reader,'REVIEWED',registry):
            self.assertEqual(reader.embedded_schematic_views(row,raw),reader.schematic(raw.decode()))
            for field in ('family','repository','repository_path','path','archive'):
                self.assertIsNone(reader.embedded_schematic_views(row|{field:'other'},raw))
            for changed in (raw+b'\n',raw[:-1],raw.replace(b'wire a;',b'wire b;')):
                with self.assertRaisesRegex(ValueError,'source bytes changed'):reader.embedded_schematic_views(row,changed)
    def test_audit_source_target_and_fact_linkage(self):
        from unittest.mock import patch
        from scripts import audit_source_dispositions as audit
        raw=schematic_text('wire actual; assign actual=a[0];').encode()
        for family in ('sky130A','sky130B'):
            row,registry=self.route(raw,family)
            with patch.object(reader,'REVIEWED',registry):items,records,gaps,_=audit.supplemental([row],{},None,reader=lambda _:raw)
            self.assertEqual(gaps,[])
            for item in (i for i in items if i['id'].startswith('supplement:')):
                self.assertEqual(item['sources'],[row['path']]);self.assertIn(item['id'],records[0]['item_ids']);self.assertEqual(set(item['dispositions']),{'sky130A'})
                disposition=item['dispositions']['sky130A'];self.assertEqual(disposition['disposition'],'unimplemented' if family=='sky130A' else 'inapplicable');self.assertFalse(disposition['qualified']);self.assertTrue(disposition['reason'])
    def test_pinned_unreviewed_module_cannot_close_from_component_count(self):
        from unittest.mock import patch
        from scripts import audit_source_dispositions as audit
        raw=schematic_text('module hidden; endmodule').encode();row,registry=self.route(raw)
        with patch.object(reader,'REVIEWED',registry):items,records,gaps,_=audit.supplemental([row],{},None,reader=lambda _:raw)
        self.assertEqual(records[0]['accounting'],'inventory-gap');self.assertEqual(len(gaps),1);self.assertIn('unreviewed top-level Verilog token module',gaps[0]['error']);self.assertTrue(gaps[0]['blocks_inventory_completion'])
    def test_literal_only_reader_still_rejects_reg_hidden(self):
        from scripts.inventory_schematic_views import versioned_literal
        with self.assertRaisesRegex(ValueError,'unenumerated embedded source block V'):versioned_literal(schematic_text('reg hidden;'))
    def test_audit_wrong_hash_remains_explicit_gap(self):
        from unittest.mock import patch
        from scripts import audit_source_dispositions as audit
        raw=schematic_text('wire a;').encode();row,registry=self.route(raw)
        with patch.object(reader,'REVIEWED',registry):items,records,gaps,_=audit.supplemental([row],{},None,reader=lambda _:raw+b'\n')
        self.assertEqual(records[0]['accounting'],'inventory-gap');self.assertIn('source bytes changed',gaps[0]['error']);self.assertFalse(any(i['id'].startswith('supplement:') for i in items))

if __name__=='__main__':unittest.main()
