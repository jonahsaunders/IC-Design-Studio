"""Bounded declaration/decoy controls; no PostScript or Tcl execution."""
import ast
import hashlib
import inspect
import unittest

from scripts import inventory_xcircuit as reader
from scripts import audit_source_dispositions as audit

HEADER='%! PostScript set of library objects for XCircuit\n% Version: 3.10\n% Library name is: fixture\n% XCircuitLib library objects\n'
DEFINITION='/fixture::device {\nbegingate\n(A) {/Times-Roman cf} 2 4 0 1 0 0 pinlabel\nendgate\n} def\n'
BASE=HEADER+DEFINITION+'% EndLib\n'


class XCircuitTests(unittest.TestCase):
    def accepted(self,text,expected):
        output=reader.library(text)
        self.assertEqual([(o['name'],[p['name'] for p in o['ports']]) for o in output['objects']],expected)

    def rejected(self,text):
        with self.assertRaisesRegex(ValueError,'XCircuit declarations:'):
            reader.library(text)

    def test_literal_symbol_and_pin(self):self.accepted(BASE,[('fixture::device',['A'])])
    def test_comment_decoy(self):self.accepted(BASE.replace(DEFINITION,'% /fake {begingate endgate} def\n'+DEFINITION),[('fixture::device',['A'])])
    def test_quoted_decoy(self):self.accepted(BASE.replace('endgate','(/fake {pinlabel} def) {/Times-Roman cf} 2 4 0 1 0 0 label\nendgate'),[('fixture::device',['A'])])
    def test_escaped_pin(self):self.accepted(BASE.replace('(A)',r'(A\(0\))'),[('fixture::device',['A(0)'])])
    def test_octal_pin(self):self.accepted(BASE.replace('(A)',r'(\101)'),[('fixture::device',['A'])])
    def test_repeated_label_preserved(self):self.accepted(BASE.replace('endgate','(A) {/Times-Roman cf} 2 4 0 1 10 0 pinlabel\nendgate'),[('fixture::device',['A','A'])])
    def test_dynamic_pin(self):self.rejected(BASE.replace('begingate','<</@pin (A)>> begingate').replace('(A) {/Times-Roman','@pin {/Times-Roman'))
    def test_duplicate_symbol(self):self.rejected(BASE.replace('% EndLib',DEFINITION+'% EndLib'))
    def test_unterminated_string(self):self.rejected(BASE.replace('(A)','(A'))
    def test_unterminated_object(self):self.rejected(BASE.replace('} def','def'))
    def test_dynamic_execution(self):self.rejected(BASE.replace('endgate','exec endgate'))
    def test_unknown_operator(self):self.rejected(BASE.replace('endgate','unreviewed_operator endgate'))
    def test_data_after_trailer(self):self.rejected(BASE+'unreviewed_operator')
    def test_unknown_palette(self):self.rejected(BASE.replace('% EndLib','1.0 0.0 /fixture::missing libinst\n% EndLib'))
    def test_literal_def_decoy(self):self.rejected(BASE.replace('} def','} /def'))
    def test_string_def_decoy(self):self.rejected(BASE.replace('} def','} (def)'))
    def test_literal_endgate_decoy(self):self.rejected(BASE.replace('endgate','endgate /endgate'))
    def test_string_endgate_decoy(self):self.rejected(BASE.replace('endgate','endgate (endgate)'))
    def test_nested_body_procedure(self):self.rejected(BASE.replace('endgate','{/hidden {begingate endgate} def} endgate'))
    def test_nested_body_dictionary(self):self.rejected(BASE.replace('endgate','<</hidden (model)>> endgate'))
    def test_nested_body_array(self):self.rejected(BASE.replace('endgate','[/hidden (model)] endgate'))
    def test_misplaced_style(self):self.rejected(BASE.replace('endgate','{/Times-Roman cf} endgate'))
    def test_nested_parameter_procedure(self):self.rejected(BASE.replace('begingate','<</@model {/hidden {begingate endgate} def}>> begingate'))
    def test_nested_parameter_dictionary(self):self.rejected(BASE.replace('begingate','<</@model <</hidden (model)>>>> begingate'))
    def test_nested_parameter_array(self):self.rejected(BASE.replace('begingate','<</@model [(hidden)]>> begingate'))
    def test_literal_cf_decoy(self):self.rejected(BASE.replace('/Times-Roman cf','/Times-Roman /cf'))
    def test_string_cf_decoy(self):self.rejected(BASE.replace('/Times-Roman cf','/Times-Roman (cf)'))
    def test_nested_style(self):self.rejected(BASE.replace('/Times-Roman cf','/Times-Roman {cf}'))

    def test_empty_library_and_empty_marked_label_are_explicit_errors(self):
        self.rejected(HEADER+'% EndLib\n')
        self.rejected(HEADER+'/fixture::device {begingate mark ctmk 4 0 1 0 0 infolabel endgate} def\n% EndLib\n')

    def test_checks_do_not_depend_on_python_assert(self):
        self.assertFalse(any(isinstance(node,ast.Assert) for node in ast.walk(ast.parse(inspect.getsource(reader)))))

    def test_adapter_retains_template_diagnostic_and_expression_identity(self):
        template='(spice:X%i %pMISSING sky130_fd_pr__cap) {/Times-Roman cf} 2 4 0 1 0 0 infolabel'
        source=BASE.replace('endgate',template+'\nendgate')
        rows=reader.xcircuit_views(source)
        diag=next(r for r in rows if r['kind']=='xcircuit-template-pin-diagnostic')
        self.assertEqual(diag['identifiers'],['MISSING']);self.assertFalse(diag['correction_inferred'])
        info=next(r for r in rows if r['kind']=='xcircuit-netlist-template')
        self.assertEqual(info['expression_sha256'],hashlib.sha256(template.encode()).hexdigest())
        self.assertFalse(info['evaluated']);self.assertFalse(info['model_binding_inferred'])
        pin=next(r for r in rows if r['kind']=='xcircuit-pin-label');self.assertFalse(pin['electrical_port_order_inferred'])

    def test_literal_parameter_options_are_named_unevaluated_facts(self):
        source=BASE.replace('begingate','<</@model (cap_a) (lindex {cap_a cap_b} 0) pop>> begingate')
        options=[r for r in reader.xcircuit_views(source) if r['kind']=='xcircuit-parameter-option']
        self.assertEqual([r['name'] for r in options],['cap_a','cap_b'])
        self.assertTrue(all(r['selection_evaluated'] is False for r in options))

    def test_audit_routing_keeps_source_and_conservative_dispositions(self):
        for family in ('sky130A','sky130B'):
            row=dict(family=family,path=family+'/libs.tech/xcircuit/fixture.lps',mode='100644',repository='fixture@pin',repository_path='fixture.lps',git_blob_sha1='a'*40,bytes=len(BASE))
            items,records,gaps,_=audit.supplemental([row],{},None,reader=lambda _:BASE.encode())
            self.assertEqual(gaps,[]);self.assertEqual(records[0]['sha256'],hashlib.sha256(BASE.encode()).hexdigest())
            pins=[r for r in items if r['kind']=='xcircuit-pin-label'];self.assertEqual(len(pins),1)
            self.assertEqual(pins[0]['sources'],[audit.source_id(row)])
            choice=pins[0]['dispositions']['sky130A'];self.assertEqual(choice['disposition'],'unimplemented' if family=='sky130A' else 'inapplicable');self.assertFalse(choice['qualified'])

    def test_audit_retains_unsupported_format_as_gap(self):
        row=dict(family='sky130A',path='sky130A/libs.tech/xcircuit/fixture.lps',mode='100644',repository='fixture@pin',repository_path='fixture.lps',git_blob_sha1='a'*40)
        _,records,gaps,_=audit.supplemental([row],{},None,reader=lambda _:BASE.replace('} def','} /def').encode())
        self.assertEqual(records[0]['accounting'],'inventory-gap');self.assertEqual(len(gaps),1);self.assertTrue(gaps[0]['blocks_inventory_completion'])


if __name__=='__main__':unittest.main()
