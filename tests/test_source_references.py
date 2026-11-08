import ast,hashlib,inspect,unittest
from unittest.mock import patch
from scripts import inventory_source_references as reader

class SourceReferenceTests(unittest.TestCase):
    def route(self,text,role='application-help'):
        row=dict(family='sample',repository='official/repo@fixed',repository_path='runtime/help.txt',path='runtime/help.txt',archive=None)
        key=tuple(row[k] for k in ('family','repository','repository_path','path','archive'))
        return row,{key:(hashlib.sha256(text).hexdigest(),role)}
    def test_entire_exact_content_required(self):
        raw=b'Authored user help.\n';row,registry=self.route(raw)
        with patch.object(reader,'REVIEWED',registry):
            self.assertFalse(reader.source_reference_views(row,raw)[0]['production_interface'])
            for changed in (raw+b'.subckt hidden a b\n',raw[:-1],b'.model hidden nmos\n'):
                with self.assertRaises(ValueError):reader.source_reference_views(row,changed)
    def test_every_identity_field_is_required(self):
        raw=b'Authored user help.\n';row,registry=self.route(raw)
        with patch.object(reader,'REVIEWED',registry):
            for field in row:self.assertIsNone(reader.source_reference_views(row|{field:'other'},raw))
    def test_unreviewed_text_file_stays_unsupported(self):
        self.assertIsNone(reader.source_reference_views(dict(family='arbitrary',path='help.txt'),b'No declaration.'))
    def test_versions_cannot_consume_trailing_model(self):
        self.assertEqual(reader.reference_facts('1.2.3\n','version-provenance')[0]['version'],'1.2.3')
        for text in ('1.2.3\n.model hidden nmos\n','1.2\n','1.2.3 garbage\n'):
            with self.assertRaises(ValueError):reader.reference_facts(text,'version-provenance')
    def test_release_identity_does_not_establish_equivalence(self):
        row=reader.reference_facts('open_pdks '+'a'*40+'\n','release-provenance')[0]
        self.assertFalse(row['independent_build_equivalence'])
        with self.assertRaises(ValueError):reader.reference_facts('open_pdks main\n','release-provenance')
    def test_diagnostics_and_counts_are_reported_not_reproduced(self):
        text='Module: JUNCAP200\nWARNING in file model.va, line 7: authored warning\nModel parameters (4)\n'
        rows=reader.reference_facts(text,'release-reference')
        self.assertFalse(next(r for r in rows if r['kind']=='documented-tool-diagnostic')['reproduced'])
        self.assertFalse(next(r for r in rows if r['kind']=='documented-interface-count')['independently_verified'])
        self.assertFalse(next(r for r in rows if r['kind']=='documented-module-reference')['model_binding_inferred'])
        self.assertEqual(next(r for r in rows if r['kind']=='documented-tool-diagnostic')['reported_line'],7)
    def test_diagnostic_text_is_hashed(self):
        text='WARNING in file model.va, line 2: distinct authored warning'
        row=next(r for r in reader.reference_facts(text,'release-reference') if r['kind']=='documented-tool-diagnostic')
        self.assertEqual(row['message_sha256'],hashlib.sha256(b'distinct authored warning').hexdigest())
        self.assertNotIn('distinct authored warning',repr(row))
    def test_reference_bounds_and_unknown_roles(self):
        for text,role in (('x\0','application-help'),('x'*100001,'application-help'),('text','model-library')):
            with self.assertRaises(ValueError):reader.reference_facts(text,role)
    def test_checks_survive_optimized_python(self):
        self.assertFalse(any(isinstance(n,ast.Assert) for n in ast.walk(ast.parse(inspect.getsource(reader)))))


    def test_audit_reference_source_and_target_bindings(self):
        from scripts import audit_source_dispositions as audit
        raw=b'Authored user help.\n';row,registry=self.route(raw);row['mode']='100644';row['family']='gf180-open-pdks';key=tuple(row.get(k) for k in ('family','repository','repository_path','path','archive'));registry={key:next(iter(registry.values()))}
        with patch.object(reader,'REVIEWED',registry):items,records,gaps,_=audit.supplemental([row],{},None,reader=lambda _:raw)
        self.assertEqual(gaps,[])
        for item in (i for i in items if i['id'].startswith('supplement:')):
            self.assertEqual(item['sources'],[audit.source_id(row)]);self.assertIn(item['id'],records[0]['item_ids']);self.assertEqual(set(item['dispositions']),set(audit.targets(row['family'])));self.assertTrue(all(not d['qualified'] and d['reason'] for d in item['dispositions'].values()))
    def test_audit_unreviewed_reference_file_remains_gap(self):
        from scripts import audit_source_dispositions as audit
        row=dict(family='gf180-open-pdks',repository='unreviewed',repository_path='runtime/new_help.txt',path='runtime/new_help.txt',mode='100644')
        _,records,gaps,_=audit.supplemental([row],{},None,reader=lambda _:b'Authored help.\n');self.assertEqual(records[0]['accounting'],'inventory-gap');self.assertTrue(gaps[0]['blocks_inventory_completion'])
    def test_audit_changed_reference_source_remains_gap(self):
        from scripts import audit_source_dispositions as audit
        raw=b'Authored user help.\n';row,registry=self.route(raw);row['mode']='100644';row['family']='gf180-open-pdks';key=tuple(row.get(k) for k in ('family','repository','repository_path','path','archive'));registry={key:next(iter(registry.values()))}
        with patch.object(reader,'REVIEWED',registry):_,records,gaps,_=audit.supplemental([row],{},None,reader=lambda _:raw+b'.model hidden nmos\n')
        self.assertEqual(records[0]['accounting'],'inventory-gap');self.assertIn('source bytes changed',gaps[0]['error'])

if __name__=='__main__':unittest.main()
