"""Bounded exact-source declaration checks, not native KLayout acceptance."""
import ast
from collections import Counter
import gzip
import hashlib
import inspect
import json
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

from scripts import audit_source_dispositions as audit
from scripts import inventory_klayout_wrappers as reader

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT/'docs/qualification/klayout-wrapper-sources-v1'
LOCK_SHA = 'b30c6d5e9b740e0461c6bfd7d83829131eb4e12614cd2a375c90d67c41587614'


class KLayoutWrapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = (FIXTURES/'source-lock.json').read_bytes()
        if hashlib.sha256(raw).hexdigest() != LOCK_SHA:
            raise ValueError('Changed reviewed source lock')
        cls.lock = json.loads(raw)
        cls.sources = cls.lock['files']
        cls.raw = {(s['family'], s['path']): (FIXTURES/s['local_path']).read_bytes() for s in cls.sources}

    def read(self, source):
        return self.raw[(source['family'], source['path'])]

    def test_all_six_original_source_identities_and_licenses(self):
        self.assertEqual(len(self.sources), 6)
        self.assertEqual(hashlib.sha256((FIXTURES/'Apache-2.0.txt').read_bytes()).hexdigest(), self.lock['license_sha256'])
        for source in self.sources:
            raw = self.read(source)
            self.assertEqual(len(raw), source['bytes'])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), source['sha256'])
            self.assertEqual(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest(), source['git_blob_sha1'])
            self.assertIn(b'Apache License, Version 2.0', raw)
            self.assertEqual(source['license'], 'Apache-2.0')
            self.assertEqual(len(reader.klayout_wrapper_views(source, raw)), [14, 2, 2, 56, 1, 9][self.sources.index(source)])

    def test_raw_line_readback_preserves_every_literal_dependency(self):
        total = 0
        for source in self.sources:
            text = self.read(source).decode()
            if source['path'].endswith('.lylvs'):
                text = ET.fromstring(text).findtext('text')
            # Independent split-based readback of the exact, inspected sources.
            expected = []
            for line, value in enumerate(text.splitlines(), 1):
                tokens = value.strip().removeprefix('#').strip().split()
                if tokens and tokens[0] == '%include':
                    self.assertEqual(len(tokens), 2)
                    expected.append((line, tokens[1]))
            actual = [r for r in reader.klayout_wrapper_views(source, self.read(source)) if r['kind'] == 'klayout-preprocessor-include']
            self.assertEqual([(r['line'], r['name']) for r in actual], expected)
            self.assertTrue(all(not r['executed'] and not r['dependency_replayed'] for r in actual))
            total += len(actual)
        self.assertEqual(total, 20)

    def test_macro_retains_all_assignments_and_repeated_variant_options(self):
        source = self.sources[3]
        rows = reader.klayout_wrapper_views(source, self.read(source))
        expected_assignments = ['layout_path', 'options', 'net_name', 'net_dir', 'net_dir', 'net_dir',
                                '$schematic', '$lvs_sub', '$run_mode']
        expected_assignments += ['$metal_top', '$metal_level', '$mim_option']*4
        expected_assignments += ['$topcell', '$spice_net_names', '$spice_comments', '$verbose', '$simplify',
                                 '$net_only', '$top_lvl_pins', '$combine', '$purge', '$purge_nets',
                                 '$implicit_connect', '$schematic_translate']
        self.assertEqual([r['name'] for r in rows if r['kind'] == 'macro-assignment'], expected_assignments)
        options = Counter(r['name'] for r in rows if r['kind'] == 'macro-option-reference')
        self.assertEqual(options, Counter(dict(netlist=2, sub_name=1, run_mode=1, variant=4,
                         top_cell_name=2, verbose=1, simplify=1, net_only=1, top_lvl_pins=1,
                         combine=1, purge=1, purge_nets=1, implicit_connect=1, schematic_translate=1)))
        self.assertEqual([r['name'] for r in rows if r['kind'] == 'ruby-mapping-or-dependency'], ['require', 'require'])
        self.assertTrue(all(r['line_scope'] == 'embedded-text' for r in rows[1:]))
        self.assertFalse(rows[0]['executed'])

    def test_logging_and_empty_stubs_do_not_invent_rules(self):
        for index, role in ((1, 'logger-only-stub'), (2, 'logger-only-stub'), (4, 'license-only-stub')):
            source = self.sources[index]; rows = reader.klayout_wrapper_views(source, self.read(source))
            self.assertEqual(rows[0]['name'], role)
            self.assertFalse(rows[0]['device_rule_implementation'])
            self.assertFalse(any(r['kind'] in ('extracted-device', 'klayout-preprocessor-include') for r in rows))

    def test_changed_truncated_appended_and_hidden_code_rejects(self):
        for source in self.sources:
            raw = self.read(source)
            for changed in (raw[:-1], raw+b'connect(a,b)\n', raw.replace(b'Copyright', b'copyright'), raw+b'# %include hidden.lvs\n'):
                with self.subTest(path=source['path']), self.assertRaisesRegex(ValueError, 'source bytes changed'):
                    reader.klayout_wrapper_views(source, changed)

    def test_every_route_field_is_exact_and_unknown_sources_remain_unsupported(self):
        for source in self.sources:
            for field in ('family', 'repository', 'repository_path', 'path', 'archive', 'mode'):
                self.assertIsNone(reader.klayout_wrapper_views(source|{field:'unreviewed'}, self.read(source)))
            for field in ('sha256', 'git_blob_sha1', 'bytes'):
                with self.assertRaisesRegex(ValueError, 'ledger identity'):
                    reader.klayout_wrapper_views(source|{field:None}, self.read(source))

    def test_wrapper_grammar_rejects_code_and_role_substitution(self):
        for text, role in (("logger.info('x'); connect(a,b)", 'logger-only-stub'),
                           ("logger.info('#{system(1)}')", 'logger-only-stub'),
                           ('# %include x.lvs\n', 'license-only-stub'),
                           ('# comment\n', 'dependency-wrapper'),
                           ('eval(code)', 'logger-only-stub')):
            with self.assertRaises(ValueError): reader.wrapper_facts(text, 'a/test.lvs', role)
        with self.assertRaises(ValueError): reader.wrapper_facts('x\0', 'a.lvs', 'logger-only-stub')

    def test_directive_grammar_rejects_dynamic_absolute_and_escaping_targets(self):
        for text in ('# %include $path', '# %include /outside.lvs', '# %include ../../outside.lvs',
                     '# %include a.lvs trailing', '# %unknown file', '# %include a//b.lvs'):
            with self.assertRaises(ValueError): reader.includes(text, 'a/wrapper.lvs')
        self.assertEqual(reader.includes("logger.info('# %include fake.lvs')\n# prose include absent.lvs", 'a.lvs'), [])

    def test_macro_interpreter_and_hidden_prolog_are_not_silently_accepted(self):
        original = self.read(self.sources[3]).decode()
        for text in (original.replace('lvs-dsl-xml', 'unknown-dsl'),
                     original.replace('<prolog/>', '<prolog>hidden()</prolog>'),
                     original.replace('<epilog/>', '<epilog>hidden()</epilog>')):
            with self.assertRaises(ValueError): reader.wrapper_facts(text, 'macro.lylvs', 'lvs-macro')

    def test_audit_links_all_facts_without_qualification_promotion(self):
        items, records, gaps, _ = audit.supplemental(self.sources, {}, None, reader=self.read)
        self.assertEqual(gaps, [])
        self.assertEqual(len(records), 6)
        facts = [r for r in items if r['id'].startswith('supplement:')]
        self.assertEqual(len(facts), 84)
        for source, record in zip(self.sources, records):
            self.assertEqual(record['accounting'], 'supplemental-declarations')
            self.assertEqual(record['sha256'], source['sha256'])
            expected = [r['id'] for r in facts if r['sources'] == [audit.source_id(source)]]
            self.assertEqual(record['item_ids'][1:], expected)
        for row in facts:
            self.assertTrue(all(not d['qualified'] and d['disposition'] == 'unimplemented' and d['reason']
                                for d in row['dispositions'].values()))

    def test_audit_changed_sources_stay_explicit_gaps(self):
        _, records, gaps, _ = audit.supplemental(self.sources, {}, None, reader=lambda s:self.read(s)+b'\n')
        self.assertEqual(len(gaps), 6)
        self.assertTrue(all(r['accounting'] == 'inventory-gap' for r in records))
        self.assertTrue(all(r['blocks_inventory_completion'] for r in gaps))

    def test_checks_survive_optimized_python(self):
        tree = ast.parse(inspect.getsource(reader))
        self.assertFalse(any(isinstance(node, ast.Assert) for node in ast.walk(tree)))
        self.assertFalse(any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and
                             node.func.id in ('eval', 'exec', 'compile') for node in ast.walk(tree)))


if __name__ == '__main__':
    unittest.main()
