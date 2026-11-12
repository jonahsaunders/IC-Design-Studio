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

    def test_irsim_device_declarations_are_source_facts(self):
        rows=reader.parameter_file('device nfet Nfet_A\ndevice pfet pfet_b\ndevice capacitor cap_c 2.0E-7\ndevice resistor res_d -1.25\n')
        self.assertEqual(rows,[
            dict(kind='simulator-device-declaration',name='Nfet_A',device_type='nfet',declared_value=None,declared_value_literal=None,line=1),
            dict(kind='simulator-device-declaration',name='pfet_b',device_type='pfet',declared_value=None,declared_value_literal=None,line=2),
            dict(kind='simulator-device-declaration',name='cap_c',device_type='capacitor',declared_value=2e-7,declared_value_literal='2.0E-7',line=3),
            dict(kind='simulator-device-declaration',name='res_d',device_type='resistor',declared_value=-1.25,declared_value_literal='-1.25',line=4)])

    def test_irsim_numeric_literal_survives_float_rounding(self):
        rows=reader.parameter_file('device resistor tiny 1e-400\ndevice capacitor exact 0.12345678901234567890123456789\n')
        self.assertEqual(rows[0]['declared_value_literal'],'1e-400')
        self.assertEqual(rows[1]['declared_value_literal'],'0.12345678901234567890123456789')
        self.assertEqual(rows[0]['declared_value'],0.0)

    def test_irsim_comments_do_not_create_devices(self):
        rows=reader.parameter_file('; device nfet decoy\n# device pfet absent\nlambda .005 ; device nfet ignored\ndevice nfet actual ; device pfet second\n')
        self.assertEqual([r['name'] for r in rows],['lambda','actual'])
        self.assertEqual(rows[-1]['line'],4)

    def test_irsim_device_arity_and_type_are_explicit(self):
        for text in ('device','device nfet','device bjt unknown','device nfet n 1',
                     'device pfet p 1','device capacitor c','device resistor r',
                     'device capacitor c 1 trailing','device resistor r 1 2'):
            with self.subTest(text=text),self.assertRaises(ValueError):reader.parameter_file(text)

    def test_irsim_device_names_and_values_are_literal_and_finite(self):
        for text in ('device nfet "quoted"','device nfet $dynamic','device nfet cell[0]',
                     'device resistor r NaN','device resistor r Infinity','device resistor r 1e400',
                     'device resistor r 0x10','device resistor r 1_000','device capacitor c 2u',
                     'device resistor r (1+2)','device resistor r "1"','device nfet n;\ndevice $kind other'):
            with self.subTest(text=text),self.assertRaises(ValueError):reader.parameter_file(text)

    def test_irsim_duplicate_and_case_ambiguous_devices_fail(self):
        for text in ('device nfet n\ndevice nfet n','device nfet n\ndevice pfet n',
                     'device nfet n\ndevice nfet N'):
            with self.subTest(text=text),self.assertRaises(ValueError):reader.parameter_file(text)

    def test_irsim_existing_parameter_and_resistance_fields_unchanged(self):
        rows=reader.parameter_file('lambda .005\ndevice nfet n\nresistance n-channel static .8 .2 3335\n')
        self.assertEqual(rows[0],dict(kind='simulator-parameter',name='lambda',value=.005,line=1))
        self.assertEqual(rows[2],dict(kind='simulator-resistance-setting',name='n-channel',mode='static',values=[.8,.2,3335.0],line=3))

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
