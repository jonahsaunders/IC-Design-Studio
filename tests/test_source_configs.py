"""Protect declaration coverage from quoted decoys and opaque source syntax."""
import unittest
from scripts import inventory_source_configs as reader


class SourceConfigTests(unittest.TestCase):
    def test_tcl_quoted_decoys_are_not_declarations(self):
        rows=reader.tcl_views('puts "set fake value; proc absent {} {}"\nset env(REAL) cell\n')
        self.assertEqual([r['name'] for r in rows if r['kind']=='tcl-variable'],['env(REAL)'])
        self.assertFalse(any(r['kind']=='tcl-procedure' for r in rows))

    def test_tcl_nested_branches_and_procedure_parameters(self):
        rows=reader.tcl_views('proc cell {w {l 2}} {\nif {$w} {set model a} elseif {$l} {set model b} else {set model c}\n}\n')
        self.assertEqual([r['name'] for r in rows if r['kind']=='tcl-variable'],['model']*3)
        self.assertEqual(rows[0]['name'],'cell')
        self.assertEqual(rows[0]['arguments'][0],'w')

    def test_tcl_switch_branches_and_data(self):
        rows=reader.tcl_views('switch -- $name {a {set real one} b - default {set fallback two}}\nset data {set decoy three}\n')
        self.assertEqual([r['name'] for r in rows if r['kind']=='tcl-variable'],['real','fallback','data'])

    def test_tcl_invalid_or_dynamic_scripts_fail(self):
        for text in ('set x {unterminated','set x "bad"tail','set x [unclosed',
                     'eval $dynamic','uplevel 1 $body','if $expr $body','switch $name $cases'):
            with self.subTest(text=text),self.assertRaises(ValueError):reader.tcl_views(text)

    def test_tcl_comment_containing_braces_is_not_code(self):
        rows=reader.tcl_views('# proc ignored { broken\nset real value\n')
        self.assertEqual(rows[0]['name'],'real')

    def test_tcl_try_handlers_are_read(self):
        rows=reader.tcl_views('try {set a 1} on error {result opts} {set b 2} finally {set c 3}')
        self.assertEqual([r['name'] for r in rows if r['kind']=='tcl-variable'],['a','b','c'])

    def test_tcl_substitutions_are_code_but_braced_values_are_data(self):
        rows=reader.tcl_views('set data "[set real 1]"\nset data [proc actual {} {}]\nset data {[set decoy 1]}\nset data [list {]}]\n')
        self.assertIn('real',[r['name'] for r in rows if r['kind']=='tcl-variable'])
        self.assertEqual([r['name'] for r in rows if r['kind']=='tcl-procedure'],['actual'])
        self.assertNotIn('decoy',[r['name'] for r in rows])
        with self.assertRaises(ValueError):reader.tcl_views('proc ${model} {} {}')

    def test_tcl_namespace_and_each_global_are_named(self):
        rows=reader.tcl_views('namespace eval cells {proc cell {} {global Winopts Opts; variable width 1 length 2}}')
        self.assertEqual(next(r for r in rows if r['kind']=='tcl-procedure')['scope'],['cells'])
        self.assertEqual([r['name'] for r in rows if r['kind']=='tcl-variable'],['Winopts','Opts','width','length'])

    def test_tcl_optional_else_expansion_and_dictionary_body(self):
        rows=reader.tcl_views('if {$x} {set a 1} {set b 2}\ndict for {k v} $d {set actual $v}\nunits {*}$curunits')
        self.assertEqual([r['name'] for r in rows if r['kind']=='tcl-variable'],['a','b','actual'])

    def test_tcl_literal_pcell_default_keys(self):
        rows=reader.tcl_views('proc cap_defaults {} {return {w 2 l 3 compatible {cap_a cap_b}}}')
        self.assertEqual([r['name'] for r in rows if r['kind']=='tcl-pcell-default'],['w','l','compatible'])

    def test_tcl_expression_substitutions_and_opaque_evaluation(self):
        rows=reader.tcl_views('if {[set actual 1]} {set branch 2}\nexpr {1+[set another 3]}')
        self.assertEqual([r['name'] for r in rows if r['kind']=='tcl-variable'],['actual','branch','another'])
        for source in ('apply {{} {set hidden 1}}','after 0 {proc hidden {} {}}'):
            with self.subTest(source=source),self.assertRaises(ValueError):reader.tcl_views(source)

    def test_tracks_require_all_records_and_finite_values(self):
        self.assertEqual(reader.tracks('M1 X 0.2 0.4\n')[0]['name'],'M1')
        for text in ('M1 X 0 1\nM1 X 0 1','M1 Z 0 1','M1 X 0 inf','unknown'):
            with self.subTest(text=text),self.assertRaises(ValueError):reader.tracks(text)

    def test_magic_labels_keep_explicit_port_index(self):
        text='magic\ntech gf180\n<< labels >>\nrlabel metal1 0 0 1 1 0 A\nport 7 nsew signal input\n<< end >>\n'
        rows=reader.magic_cell(text,'cell.mag');port=next(r for r in rows if r['kind']=='magic-port')
        self.assertEqual((port['name'],port['index']),('A',7))
        with self.assertRaises(ValueError):reader.magic_cell(text.replace('rlabel metal1 0 0 1 1 0 A\n',''),'cell.mag')
        with self.assertRaises(ValueError):reader.magic_cell(text.replace('<< end >>','newmodel unknown'),'cell.mag')

    def test_parameters_are_not_operating_envelopes(self):
        rows=reader.parameter_file('; description\nlambda .01\nresistance n-channel static 2 .4 12\n')
        self.assertEqual([r['name'] for r in rows],['lambda','n-channel'])
        with self.assertRaises(ValueError):reader.parameter_file('lambda NaN')

    def test_qflow_static_template_and_conditions(self):
        rows=reader.qflow_shell('#ifdef METALS4\nset flopcell=LIBRARY__dff ;# comment\n#endif\n')
        self.assertEqual({r['name'] for r in rows},{'METALS4','flopcell'})
        with self.assertRaises(ValueError):reader.qflow_shell('source dynamic.sh')

    def test_placement_rules_and_settings(self):
        rows=reader.qflow_parameters('RULES\nlayer metal1 .1 .2 horizontal\nENDRULES\nTWSC*feedThruWidth : 46 layer 1\n')
        self.assertEqual([r['name'] for r in rows],['metal1','TWSC*feedThruWidth'])
        with self.assertRaises(ValueError):reader.qflow_parameters('RULES\n')

    def test_rc_table_zero_widths_and_literal_layers(self):
        text='Extraction Rules for OpenRCX\nLayerCount 5\nMetal 5 UNDER\nWIDTH Table 0 entries:\nMetal 1 OVER 0\nDIST count 1 width .2\n0 .1 .2 .3\nEND DIST\nEND DensityModel 0\n'
        rows=reader.openrcx(text)
        self.assertEqual([r['name'] for r in rows if r['kind']=='rc-metal-table'],['5','1'])
        self.assertEqual(next(r for r in rows if r['kind']=='rc-distance-table')['observed_rows'],1)
        with self.assertRaises(ValueError):reader.openrcx(text+'new_model name\n')
        with self.assertRaises(ValueError):reader.openrcx(text.replace('END DIST\n',''))


if __name__=='__main__':unittest.main()
