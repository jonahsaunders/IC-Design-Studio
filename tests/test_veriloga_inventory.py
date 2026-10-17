import unittest
from scripts.inventory_veriloga_models import declarations,reconcile


class VerilogAInventoryTests(unittest.TestCase):
    def test_conditional_module_names_and_original_lines_survive_comments(self):
        text='/*\nmodule fake(a,b);\n*/\n`ifdef XYCE\nmodule OTHER(d,g,s,b);\n`else\nmodule MAIN(d,g,s,b);\n`endif\nendmodule\n'
        rows=declarations(text,'source.va')
        self.assertEqual([(r['module'],r['line']) for r in rows],[('OTHER',5),('MAIN',7)])
        self.assertNotEqual(rows[0]['conditions'],rows[1]['conditions'])
        self.assertEqual(rows[1]['terminals'],['d','g','s','b'])

    def test_incomplete_unknown_or_duplicate_terminal_syntax_is_not_guessed(self):
        for text in ('`endif\n','`ifdef TEST\n','module dynamic(a, a);\n','module dynamic #(`PARAMS) (a,b);\n'):
            with self.subTest(text=text),self.assertRaises(ValueError):declarations(text,'source.va')

    def test_missing_external_model_type_is_not_a_pass(self):
        spice={'definitions':[dict(prefix='N',model_type='psp',id='one'),dict(prefix='N',model_type='absent',id='two'),dict(prefix='M',model_type='nmos',id='three')]}
        rows=declarations('module PSP(d,g,s,b);\nmodule UNUSED(a,b);\n','source.va')
        result=reconcile(spice,rows)
        self.assertEqual(result['missing'],['absent']);self.assertEqual(result['additional_declarations'],['UNUSED'])
        self.assertEqual(result['references']['psp'],['one'])


if __name__=='__main__':unittest.main()
