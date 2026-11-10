"""Exact retained source bytes, independent readback and negative boundaries."""
import ast
import hashlib
import inspect
import json
from pathlib import Path
import re
import unittest
from scripts import inventory_source_manifests as reader

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/'docs/qualification/source-manifest-wrappers-v1'
LOCK_SHA='ad1a466ca31f6bd5c4717ef143acc5cf8b8ee83c097cb80d9ca5080d3c96af65'


class SourceManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw=(FIXTURE/'source-lock.json').read_bytes()
        if reader.sha(raw)!=LOCK_SHA:raise ValueError('changed source lock')
        cls.lock=json.loads(raw)

    def test_exact_sources_and_independent_readback(self):
        self.assertEqual(len(self.lock['sources']),3)
        self.assertEqual(reader.sha((FIXTURE/'Apache-2.0.txt').read_bytes()),self.lock['license_sha256'])
        total=0
        for source in self.lock['sources']:
            raw=(FIXTURE/source['local_path']).read_bytes();rows=reader.source_manifest_views(source,raw)
            self.assertEqual(reader.sha(raw),source['sha256']);self.assertEqual(len(raw),source['bytes'])
            total+=len(rows)
            from scripts.audit_source_dispositions import supplemental_views
            self.assertEqual(supplemental_views(source,raw),rows)
            if source['role']=='setup-tool-manifest':
                self.assertEqual([r['name'] for r in rows],['klayout','magic','netgen','irsim','librelane','qflow','xschem','xcircuit'])
                self.assertEqual([r['name'] for r in rows],raw.decode().split())
                self.assertTrue(all(not r['installed_capability'] for r in rows))
            else:
                text=raw.decode();self.assertIn('Copyright 2022 Efabless Corporation',text)
                self.assertIn('Apache License, Version 2.0',text)
                # Independent literal XML field and preprocessor line readback,
                # not the production ElementTree decoder.
                fields=dict(re.findall(r'^\s*<([\w-]+)>([^<\r\n]*)</\1>\s*$',text,re.M))
                fields.update({name:'' for name in re.findall(r'^\s*<([\w-]+) />\s*$',text,re.M)})
                self.assertEqual({r['name']:r['value'] for r in rows if r['kind']=='klayout-macro-metadata'},fields)
                directives=[(i,line.strip().split()[-1]) for i,line in enumerate(text.splitlines(),1) if '# %include' in line]
                self.assertEqual([(r['line'],r['name']) for r in rows if r['kind']=='klayout-include-reference'],directives)
                self.assertEqual(len(directives),1);self.assertFalse(rows[-1]['device_rule_implementation'])
        self.assertEqual(total,40)

    def test_whole_source_bytes_and_ledger_identity(self):
        for row in self.lock['sources']:
            raw=(FIXTURE/row['local_path']).read_bytes()
            for changed in (raw[:-1],raw+b'\n',raw.replace(b'klayout',b'KLayouT')):
                with self.assertRaisesRegex(ValueError,'source bytes'):reader.source_manifest_views(row,changed)
            for field in ('bytes','sha256'):
                with self.assertRaisesRegex(ValueError,'ledger identity'):reader.source_manifest_views(row|{field:None},raw)
            if 'git_blob_sha1' in row:
                with self.assertRaisesRegex(ValueError,'Git source'):reader.source_manifest_views(row|{'git_blob_sha1':'0'*40},raw)
            else:
                with self.assertRaisesRegex(ValueError,'release source'):reader.source_manifest_views(row|{'process':'other'},raw)

    def test_all_route_identity_fields_required(self):
        for row in self.lock['sources']:
            raw=(FIXTURE/row['local_path']).read_bytes()
            for field in ('family','repository','repository_path','path','archive','mode'):
                self.assertIsNone(reader.source_manifest_views(row|{field:'other'},raw))

    def test_unsupported_sources_stay_unclaimed(self):
        for path in ('gmon.out','gate_list.txt','realgeom','configure','sky130.lvs'):
            self.assertIsNone(reader.source_manifest_views(dict(path=path),b'anything'))

    def test_manifest_rejects_commands_empty_and_duplicates(self):
        for text in ('','magic\nmagic\n','magic;exec\n','magic --flag\n','# comment\n','../magic\n','magic\n\n'):
            with self.assertRaises(ValueError):reader.manifest_facts(text)

    def test_include_only_body_rejects_code_and_extra_directives(self):
        text=(FIXTURE/'sky130.lylvs').read_bytes().decode()
        for replacement in ('logger.info("run")','# %include ../other.lvs','# %include sky130.lvs\n# %include sky130.lvs','# %eval sky130.lvs'):
            with self.assertRaises(ValueError):reader.include_macro_facts(text.replace('# %include sky130.lvs',replacement))

    def test_macro_configuration_and_xml_entities_rejected(self):
        text=(FIXTURE/'sky130.lylvs').read_bytes().decode()
        for altered in (text.replace('<autorun>false','<autorun>true'),text.replace('<prolog />','<prolog>run</prolog>'),text.replace('<version />','<version /><version />'),text.replace('<doc />','<doc><nested /></doc>'),'<!DOCTYPE x>'+text):
            with self.assertRaises(ValueError):reader.include_macro_facts(altered)

    def test_validation_survives_optimized_python(self):
        self.assertFalse(any(isinstance(n,ast.Assert) for n in ast.walk(ast.parse(inspect.getsource(reader)))))


if __name__=='__main__':unittest.main()
