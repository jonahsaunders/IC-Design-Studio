import unittest
from scripts import inventory_source_configs as reader

class XCircuitRCReaderTests(unittest.TestCase):
    def test_literal_case_options_recurse_with_exact_lines_and_conditions(self):
        rows=reader.config_views('sky130A.xcircuitrc','proc pick {name} {\n case $name in \\\n first {set first_value 1} \\\n default {set fallback 0}\n}\n')
        options=[r for r in rows if r['kind']=='tcl-case-option']
        self.assertEqual([(r['name'],r['line']) for r in options],[('first',3),('default',4)])
        variables=[r for r in rows if r['kind']=='tcl-variable']
        self.assertEqual([(r['name'],r['line']) for r in variables],[('first_value',3),('fallback',4)])
        self.assertEqual([r['conditional_context'][0]['name'] for r in variables],['first','default'])
        self.assertTrue(all(r['conditional_context'][0]['selection_evaluated'] is False for r in variables))

    def test_nested_case_preserves_both_branch_contexts(self):
        rows=reader.config_views('a.xcircuitrc','case $x in outer {case $y in inner {set model cell}}')
        variable=next(r for r in rows if r['kind']=='tcl-variable')
        self.assertEqual([r['name'] for r in variable['conditional_context']],['outer','inner'])

    def test_library_names_and_load_slots_are_literal_facts(self):
        rows=reader.config_views('a.xcircuitrc','library make analog\nlibrary 3 load sky130_fd_pr')
        self.assertEqual([(r['kind'],r['name']) for r in rows],[('xcircuit-library-declaration','analog'),('xcircuit-library-reference','sky130_fd_pr')])
        self.assertEqual(rows[1]['library_index'],'3')

    def test_quoted_braced_and_comment_decoys_are_data(self):
        rows=reader.config_views('a.xcircuitrc','# case $x in fake {set absent 1}\nset quoted "case fake in ghost {library make absent}"\nset braced {case fake in ghost {library make absent}}\ncase $x in real {set actual 1}')
        self.assertEqual([r['name'] for r in rows if r['kind']=='tcl-case-option'],['real'])
        self.assertFalse(any(r['kind'].startswith('xcircuit-library-') for r in rows))
        self.assertEqual([r['name'] for r in rows if r['kind']=='tcl-variable'],['quoted','braced','actual'])

    def test_missing_bodies_or_case_delimiters_fail(self):
        for text in ('case','case $x in','case $x in a','case $x in a {} default','case $x a {}','case $x in a {'):
            with self.subTest(text=text),self.assertRaises(ValueError):reader.config_views('a.xcircuitrc',text)
        self.assertEqual(len([r for r in reader.config_views('a.xcircuitrc','case $x in a {}') if r['kind']=='tcl-case-option']),1)

    def test_dynamic_or_unsupported_case_forms_remain_gaps(self):
        for text in ('case $x in $model {}','case $x in [set model n] {}','case $x in a $body','case $x in a "set v 1"','case $x in {a b} {}','case $x in {a {set x 1}}','case $x in a* {}','case $x in a {} a {}','case $x in a - default {}'):
            with self.subTest(text=text),self.assertRaises(ValueError):reader.config_views('a.xcircuitrc',text)

    def test_unknown_nested_commands_and_dynamic_libraries_remain_gaps(self):
        for text in ('case $x in a {unknown_script {proc hidden {} {}}}','case $x in a {eval $body}','library make $model','library 1 load [set model n]','library make','library 2 load','library unknown n','library $slot load n','config execute unknown','namespace eval n {set hidden 1}'):
            with self.subTest(text=text),self.assertRaises(ValueError):reader.config_views('a.xcircuitrc',text)

    def test_command_substitution_inside_case_body_is_accounted(self):
        rows=reader.config_views('a.xcircuitrc','case $x in a {set ratio [* 2 [/ $l .35]]}')
        self.assertEqual({r['name'] for r in rows if r.get('conditional_context')},{'ratio','*','/'})
        self.assertTrue(all(r['conditional_context'][0]['name']=='a' for r in rows if r.get('conditional_context')))

    def test_literal_read_is_not_fabricated_assignment(self):
        row=next(r for r in reader.config_views('a.xcircuitrc','case $x in option {set 6.363}') if r['kind']=='tcl-variable')
        self.assertEqual(row['name'],'6.363');self.assertEqual(row['values'],[])

    def test_multiline_conditional_body_locations_match_source(self):
        rows=reader.config_views('a.xcircuitrc','proc p {} {\n if {$x} {\n return one\n } elseif {$y} {\n return two\n } else {\n return three\n }\n}')
        self.assertEqual([r['line'] for r in rows if r['kind']=='tcl-command-reference' and r['name']=='return'],[3,5,7])

if __name__=='__main__':unittest.main()
