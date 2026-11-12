"""Source-locked routes only; source-cache replay is explicit and nonexecuting."""
import ast
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import unittest
from unittest.mock import patch
from scripts import inventory_xschem_configs as reader

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT/'docs/qualification/xschem-config-facts-v1'
LOCK_SHA = '1c86478107e50c967926636e8a1c729e79180974a0a04cc007316828d91cfb7d'


def sha(raw):return hashlib.sha256(raw).hexdigest()


class XschemConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw=(FIXTURE/'source-lock.json').read_bytes()
        if sha(raw) != LOCK_SHA:raise ValueError('Changed configuration source lock')
        cls.lock=json.loads(raw)

    def route(self, text):
        raw=text.encode()
        row=dict(family='gf180mcu',repository='reviewed/repo@'+'a'*40,
                 repository_path='cells/xschem/xschemrc',path='cells/xschem/xschemrc',mode='100644',
                 bytes=len(raw),sha256=sha(raw),git_blob_sha1=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest())
        key=tuple(row.get(k) for k in ('family','repository','repository_path','path','archive','mode'))
        return row,raw,{key:(sha(raw),row['git_blob_sha1'],len(raw))}

    def test_three_exact_reviewed_identities_and_fact_fingerprints(self):
        self.assertEqual(len(reader.REVIEWED),3)
        self.assertFalse(self.lock['upstream_raw_source_redistributed'])
        total=0
        for source in self.lock['sources']:
            key=tuple(source.get(k) for k in ('family','repository','repository_path','path','archive','mode'))
            self.assertEqual(reader.REVIEWED[key],(source['sha256'],source['git_blob_sha1'],source['bytes']))
            raw=(FIXTURE/source['facts_file']).read_bytes();self.assertEqual(sha(raw),source['facts_sha256'])
            facts=json.loads(raw);self.assertEqual(len(facts),source['facts']);total+=len(facts)
            self.assertTrue(all(r['kind'].startswith('tcl-') for r in facts))
        self.assertEqual(total,110)

    def test_entire_source_identity_and_bytes_required(self):
        row,raw,registry=self.route('set model_path $env(PDK_ROOT)/models\n')
        with patch.object(reader,'REVIEWED',registry):
            self.assertEqual(reader.xschem_configuration_views(row,raw)[0]['name'],'model_path')
            for altered in (raw[:-1],raw+b'set hidden 1\n',raw.replace(b'models',b'modelx')):
                with self.assertRaisesRegex(ValueError,'source bytes changed'):reader.xschem_configuration_views(row,altered)
            for field in ('family','repository','repository_path','path','archive','mode'):
                self.assertIsNone(reader.xschem_configuration_views(row|{field:'other'},raw))
            for field in ('bytes','sha256','git_blob_sha1'):
                with self.assertRaisesRegex(ValueError,'ledger identity'):reader.xschem_configuration_views(row|{field:None},raw)

    def test_unreviewed_menu_and_ihp_config_are_not_adopted(self):
        for family,path in (('gf180mcu','cells/xschem/xschem-menu'),
                            ('ihp-sg13g2','ihp-sg13g2/libs.tech/xschem/xschemrc'),
                            ('ihp-sg13g2','ihp-sg13g2/libs.tech/xschem/xschem-menu')):
            self.assertFalse(any(k[0]==family and k[3]==path for k in reader.REVIEWED))
            self.assertIsNone(reader.xschem_configuration_views(dict(family=family,path=path),b'set fake 1'))

    def test_no_callback_completion_from_generic_tcl_parse(self):
        for text in ('button .b -command {set hidden 1}',
                     'proc dialog {} {button .b -command {set hidden 1}}'):
            with self.assertRaisesRegex(ValueError,'callback'):reader.configuration_facts(text)

    def test_dynamic_scripts_and_malformed_words_remain_unsupported(self):
        for text in ('eval $script','source "path"suffix','after 10 {set hidden 1}',
                     'set value {unfinished','proc worker {} {uplevel $script}'):
            with self.assertRaises(ValueError):reader.configuration_facts(text)

    def test_comments_cannot_invent_dependencies_and_values_are_unevaluated(self):
        text='# source fake\nset path $env(PDK_ROOT)/models\nsource $path\n'
        rows=reader.configuration_facts(text)
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['values'],[{'expression_sha256':sha(b'$env(PDK_ROOT)/models')}])
        self.assertEqual(rows[1]['name'],{'expression_sha256':sha(b'$path')})

    def test_all_conditional_assignments_remain_not_selected(self):
        rows=reader.configuration_facts('if {[info exists env(PDK)]} {set choice $env(PDK)} else {set choice fixed}\n')
        choices=[r for r in rows if r['kind']=='tcl-variable']
        self.assertEqual(len(choices),2)
        self.assertEqual([r['values'] for r in choices],[[{'expression_sha256':sha(b'$env(PDK)')}],['fixed']])

    def test_historical_stray_command_is_not_corrected_into_a_variable(self):
        source=next(s for s in self.lock['sources'] if s['family']=='gf180-ecosystem')
        rows=json.loads((FIXTURE/source['facts_file']).read_bytes())
        self.assertEqual([r['line'] for r in rows if r['kind']=='tcl-command-reference' and r['name']=='XSCHEM_LIBRARY_PATH'],[368])
        self.assertFalse(any(r['kind']=='tcl-variable' and r['line']==368 for r in rows))

    @unittest.skipUnless(os.environ.get('ICSTUDIO_SOURCE_CACHE'),'Real source replay requires the authenticated Git blob cache.')
    def test_actual_pinned_sources_and_independent_variable_dependency_readback(self):
        cache=Path(os.environ['ICSTUDIO_SOURCE_CACHE'])
        for source in self.lock['sources']:
            raw=(cache/source['git_blob_sha1']).read_bytes()
            rows=reader.xschem_configuration_views(source,raw)
            expected=json.loads((FIXTURE/source['facts_file']).read_bytes())
            self.assertEqual(rows,expected)
            from scripts.audit_source_dispositions import supplemental_views
            self.assertEqual(supplemental_views(source,raw),expected)
            # Independent line scan of these inspected simple configuration
            # sources, not a second call to the parser or any Tcl evaluation.
            variables=[];dependencies=[]
            for number,line in enumerate(raw.decode().splitlines(),1):
                if line.lstrip().startswith('#'):continue
                for match in re.finditer(r'(?:^|[;{])\s*(set|append|lappend)\s+(\S+)',line):
                    variables.append((number,match[1],sha(match[2].encode())))
                if line.strip().startswith('source '):
                    dependencies.append((number,sha(line.strip().split(None,1)[1].encode())))
            parsed_variables=[(r['line'],r['operation'],r['name_sha256']) for r in rows if r['kind'] in ('tcl-variable','tcl-dynamic-variable')]
            parsed_dependencies=[(r['line'],r['name']['expression_sha256']) for r in rows if r['kind']=='tcl-source-reference']
            self.assertEqual(sorted(parsed_variables),sorted(variables))
            self.assertEqual(parsed_dependencies,dependencies)

    def test_validation_is_not_disabled_by_optimized_python(self):
        self.assertFalse(any(isinstance(n,ast.Assert) for n in ast.walk(ast.parse(inspect.getsource(reader)))))


if __name__=='__main__':unittest.main()
