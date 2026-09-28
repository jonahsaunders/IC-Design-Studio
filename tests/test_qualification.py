import json
from pathlib import Path
import tempfile
import unittest

from icstudio.model import example, file_digest, save_project
from icstudio.qualification import status, content_identity, catalog


class QualificationTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name);(self.root/'examples').mkdir()
        self.project=example();save_project(self.project,self.root/'source.icproj')
        (self.root/'evidence.json').write_text('{"passed":true}')
        self.record=dict(title='Reference',summary='Bounded fixture',source='source.icproj',
            files={name:file_digest(self.root/name) for name in ('source.icproj','evidence.json')},
            checks=[dict(name='Check',status='Passed',scope='One fixture',
                assertions=[dict(file='evidence.json',path=['passed'],equals=True)])])
        self.write()

    def write(self):
        (self.root/'examples/qualification.json').write_text(json.dumps(dict(schema=1,references={'ref':self.record})))

    def test_copy_identity_and_edited_source(self):
        original=content_identity(self.project)
        self.project.update(id='independent',revision=9,reference_origin={'id':'ref'})
        self.assertEqual(content_identity(self.project),original)
        self.assertTrue(status('ref',self.project,self.root)['valid'])
        self.project['cells'][0]['devices'][0]['value']='123'
        result=status('ref',self.project,self.root)
        self.assertFalse(result['valid']);self.assertEqual(result['checks'][0]['status'],'Stale')

    def test_changed_missing_and_false_evidence(self):
        (self.root/'evidence.json').write_text('{"passed":false}')
        self.assertFalse(status('ref',root=self.root)['valid'])
        self.record['files']['evidence.json']=file_digest(self.root/'evidence.json');self.write()
        self.assertFalse(status('ref',root=self.root)['valid'])
        (self.root/'evidence.json').unlink()
        self.assertFalse(status('ref',root=self.root)['valid'])

    def test_unbound_evidence_and_escape_are_rejected(self):
        self.record['files'].pop('evidence.json');self.write()
        self.assertFalse(status('ref',root=self.root)['valid'])
        self.record['files']['../outside']='0'*64;self.write()
        self.assertFalse(status('ref',root=self.root)['valid'])

    def test_all_shipped_records_are_bound_and_evaluate(self):
        for key in catalog():
            with self.subTest(reference=key):
                result=status(key)
                self.assertTrue(result['valid'],result['errors'])
                self.assertFalse(result['signoff'])
