"""Real Windows long paths must not turn intact saved engine results into corruption."""
import hashlib,json,os,shutil,tempfile,unittest
from pathlib import Path

from icstudio import digital,digital_backend,digital_flow
from icstudio.model import clone,design_digest,file_digest,io_path
from icstudio.job_store import read_result


@unittest.skipUnless(os.name=='nt','Windows extended-length filesystem paths')
class WindowsDigitalPathTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(tempfile.mkdtemp(prefix='icstudio-long-path-')).resolve()
        # Create the fixture independently of Studio's helper, including cleanup.
        self.extended=Path('\\\\?\\'+str(self.root))
        self.addCleanup(shutil.rmtree,self.extended)
        self.relative='/'.join(['physical','results','sky130hd','circuit_'+'a'*55,*['stage_'+'b'*50]*3,'checkpoint.odb'])
        self.path=self.root/self.relative
        target=self.extended/self.relative;target.parent.mkdir(parents=True);target.write_bytes(b'intact checkpoint')
        self.assertGreater(len(str(self.path)),260)
        self.project=digital.counter_project();self.settings={'type':'digital','stage':'lint'}
        self.record={'path':self.relative,'bytes':17,'sha256':hashlib.sha256(b'intact checkpoint').hexdigest()}
        self.result={'result_type':'digital','project_id':self.project['id'],'cell_id':self.project['top'],
            'design_hash':design_digest(self.project),'settings':self.settings,
            'digital_result':{'stage':'lint','summary':'Captured tool output','artifacts':{'log':self.record},
                'source_hash':digital.source_hash(self.project['digital'])}}
        self.job={'project':self.project,'cell':self.project['top'],'settings':self.settings}
        (self.root/'result.json').write_text(json.dumps(self.result))
        (self.root/'input.json').write_text(json.dumps(self.job))
        (self.root/'status.json').write_text('{"status":"complete"}')

    def test_capture_reopen_and_tamper_detection_beyond_legacy_limit(self):
        self.assertEqual(digital_flow.artifact(self.root,self.path),self.record)
        self.assertEqual(file_digest(self.path),self.record['sha256'])
        self.assertEqual(read_result(self.root/'result.json',self.project['id']),self.result)
        (self.extended/self.relative).write_bytes(b'tampered checkpoint')
        with self.assertRaisesRegex(ValueError,'missing or changed'):
            read_result(self.root/'result.json',self.project['id'])

    def test_upstream_transfer_keeps_all_nested_artifacts(self):
        target=self.root/'staged inputs'
        target.mkdir()
        upstream={'root':str(self.root),'result_sha256':file_digest(self.root/'result.json'),
                  'artifacts':clone(self.result['digital_result']['artifacts'])}
        job=clone(self.job);job['settings']['upstream']=upstream
        digital_backend.stage_inputs(job,target)
        copied=target/'upstream-input'
        self.assertEqual(file_digest(copied/self.relative),self.record['sha256'])
        self.assertEqual(json.loads((copied/'result.json').read_text()),self.result)
        digital_flow.validate_result(self.result,copied)
        # Portable manifest names are unchanged, and escaping the run stays invalid.
        invalid=clone(self.result);invalid['digital_result']['artifacts']['log']['path']='../outside.odb'
        with self.assertRaisesRegex(ValueError,'relative digital artifact path'):
            digital_flow.validate_result(invalid,copied)

    def test_path_conversion_preserves_unc_and_existing_extended_paths(self):
        self.assertEqual(str(io_path(r'\\server\share\folder\file')),r'\\?\UNC\server\share\folder\file')
        self.assertEqual(io_path(self.extended),self.extended)


if __name__=='__main__':unittest.main()
