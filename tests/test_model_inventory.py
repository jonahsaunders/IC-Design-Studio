"""Inventory omissions, scope errors and source changes must remain visible."""
import json,tempfile,unittest
from pathlib import Path
from icstudio.model import file_digest
from scripts.inventory_device_models import parse,active_definitions,alternatives,inventory


class ModelInventoryTests(unittest.TestCase):
    def test_continuations_conditions_and_internal_definitions_keep_source_identity(self):
        p=parse('* comment\n.lib tt\n.subckt outer d g\n+ s b w=1\n.if (w>1)\n.model internal nmos\n.else\n.model internal pmos\n.endif\n.ends outer\n.endl tt\n','a.lib')
        self.assertEqual(p['definitions'][0]['pins'],['d','g','s','b'])
        self.assertEqual(p['definitions'][0]['line'],3)
        self.assertEqual(p['definitions'][0]['parameters'],['w'])
        first,second=p['definitions'][1:]
        self.assertEqual(first['parent'],'outer');self.assertNotEqual(first['conditions'],second['conditions'])
        self.assertNotEqual(first['id'],second['id'])

    def test_library_selection_and_included_model_scope(self):
        root=Path('/synthetic').resolve()
        parsed={'a.lib':parse('.lib tt\n.subckt outer d s\n.include inner.lib\n.ends\n.endl tt\n.lib ss\n.model cold d\n.endl ss\n','a.lib'),
                'inner.lib':parse('.model inner d\n','inner.lib')}
        rows=active_definitions(root,parsed,[('a.lib','tt')])
        self.assertEqual([(r['id'].split(':')[-1],r['scope']) for r in rows],[('outer',''),('inner','outer')])
        self.assertEqual([r['id'].split(':')[-1] for r in active_definitions(root,parsed,[('a.lib','ss')])],['cold'])
        with self.assertRaisesRegex(ValueError,'Missing model library'):active_definitions(root,parsed,[('a.lib','ff')])

    def test_unclosed_scope_cycle_and_escape_are_rejected(self):
        for text in ('.lib tt\n','.subckt x a b\n','.if (1)\n','.ends\n','.endif\n','+ orphan\n'):
            with self.subTest(text=text),self.assertRaises(ValueError):parse(text,'bad')
        root=Path('/synthetic').resolve()
        for text,pattern in (('.include a.lib\n','Recursive'),('.include ../outside.lib\n','escapes')):
            with self.assertRaisesRegex(ValueError,pattern):active_definitions(root,{'a.lib':parse(text,'a.lib')},[('a.lib',None)])

    def test_mismatched_ends_label_is_recorded_without_losing_following_definition(self):
        p=parse('.subckt named a b\n.ends oldname\n.model next d\n','a.lib')
        self.assertEqual(p['diagnostics'],[dict(line=2,kind='ends-name-mismatch',declared='named',ending='oldname')])
        self.assertIsNone(p['definitions'][1]['parent'])

    def test_qualified_alternate_names_are_not_silently_double_prefixed(self):
        entry={'symbol':{'attributes':{'format':'@name @pinlist sky130_fd_pr__@model area=@area','available_models':'sky130_fd_pr__diode'}}}
        row=alternatives(entry)[0];self.assertEqual(row['model'],'sky130_fd_pr__diode')
        self.assertEqual(row['literal_format_expansion'],'sky130_fd_pr__sky130_fd_pr__diode')
        self.assertTrue(row['requires_namespace_adapter'])
        entry['symbol']['attributes']['available_models']='diode'
        self.assertFalse(alternatives(entry)[0]['requires_namespace_adapter'])
        entry['symbol']['attributes']['available_models']='[exec malicious]'
        with self.assertRaises(ValueError):alternatives(entry)

    def test_missing_active_model_and_alternates_are_distinct_from_inventory_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);model=root/'a.lib';model.write_text('.lib tt\n.model diode d\n.endl tt\n.lib ss\n.model other d\n.endl ss\n')
            package={'revision':'fixture','files':{'a.lib':file_digest(model)},'technology':{'simulation':{
                'includes':[{'path':'a.lib','sections':{'nominal':'tt','slow':'ss'}}],
                'catalog':{'one':{'model':'diode','prefix':'D','symbol':{'attributes':{'format':'@name @pinlist @model','available_models':'diode absent'}}}}}}}
            path=root/'package.json';path.write_text(json.dumps(package))
            report=inventory(root);self.assertEqual(report['status'],'GAPS')
            self.assertEqual(report['missing_active_catalog_models'][0]['absent_in_corners'],['slow'])
            self.assertEqual(next(a for a in report['alternatives'] if a['model']=='absent')['definitions'],[])
            model.write_text(model.read_text()+'* changed\n')
            with self.assertRaisesRegex(ValueError,'Changed locked'):inventory(root)


if __name__=='__main__':unittest.main()
