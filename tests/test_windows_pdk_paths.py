"""A long Windows profile must preserve PDK installation and locked model I/O."""
import hashlib,json,os,shutil,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from icstudio.model import example,file_digest
from icstudio.pdks import PDKRegistry,model_lines,stage_model_deck


@unittest.skipUnless(os.name=='nt','Windows extended-length filesystem paths')
class WindowsPDKPathTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(tempfile.mkdtemp(prefix='icstudio-pdk-path-')).resolve()
        self.addCleanup(shutil.rmtree,Path('\\\\?\\'+str(self.root)))
        self.extended=lambda p:Path('\\\\?\\'+str(p))
        self.relative='/'.join(['models','nested_'+'a'*55,'nested_'+'b'*55,'device_'+'c'*55+'.spice'])
        self.payload=b'.model checked_d D is=1e-14\n'

    def source(self,name='source'):
        folder=self.root/name
        path=folder/self.relative;self.extended(path).parent.mkdir(parents=True)
        self.extended(path).write_bytes(self.payload)
        tech=example('empty')['pdk'];tech['simulation']={'includes':[{'path':self.relative}]}
        record=dict(schema=1,id='path-pdk',revision='v1',technology=tech,
                    files={self.relative:hashlib.sha256(self.payload).hexdigest()})
        self.extended(folder/'package.json').write_text(json.dumps(record),encoding='utf-8')
        return folder

    def test_install_verify_stage_reuse_and_tamper_beyond_legacy_limit(self):
        source=self.source();registry=PDKRegistry(self.root/('profile with spaces '+'p'*75)/'registry')
        key=registry.install(source/'package.json');technology=registry.technology(key)
        path=registry.root/key/self.relative;self.assertGreater(len(str(path)),260)
        self.assertEqual(file_digest(path),hashlib.sha256(self.payload).hexdigest())
        self.assertEqual(registry.install(source/'package.json'),key)
        self.assertEqual(registry.entries()[0]['id'],'path-pdk')
        self.assertFalse(technology['package_root'].startswith('\\\\?\\'))
        text='* Long PDK source\n'+'\n'.join(model_lines(technology))+'\n.end\n'
        out=self.root/'run';staged=stage_model_deck(technology,text,out)
        self.assertIn('.include pdk-models/',staged)
        self.assertEqual(next((out/'pdk-models').iterdir()).read_bytes(),self.payload)
        self.extended(path).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'missing or changed'):registry.verify(key)

    def test_deep_registry_metadata_can_reopen_and_remove_recoverably(self):
        source=self.source();root=self.root/('deep_'+'x'*90)/('deep_'+'y'*90)/('deep_'+'z'*70)
        registry=PDKRegistry(root);key=registry.install(source/'package.json')
        self.assertGreater(len(str(root/'package.json')),260)
        self.assertEqual(PDKRegistry(root).verify(key)['revision'],'v1')
        archived=registry.remove(key)
        self.assertEqual(registry.entries(),[])
        self.assertEqual(file_digest(archived/self.relative),hashlib.sha256(self.payload).hexdigest())

    def test_copy_failure_leaves_no_partial_revision_or_staging_folder(self):
        source=self.source();registry=PDKRegistry(self.root/('profile_'+'p'*100))
        with patch('icstudio.pdks.shutil.copyfile',side_effect=OSError('injected copy failure')):
            with self.assertRaisesRegex(OSError,'injected'):registry.install(source/'package.json')
        self.assertEqual(list(self.extended(registry.root).iterdir()),[])
        self.assertEqual(file_digest(source/self.relative),hashlib.sha256(self.payload).hexdigest())

    def test_long_paths_do_not_permit_asset_escape(self):
        source=self.source();manifest=self.extended(source/'package.json');record=json.loads(manifest.read_text())
        record['files']={'../outside.spice':hashlib.sha256(self.payload).hexdigest()}
        (self.root/'outside.spice').write_bytes(self.payload);manifest.write_text(json.dumps(record))
        registry=PDKRegistry(self.root/('profile_'+'p'*100))
        with self.assertRaisesRegex(ValueError,'Unsafe'):registry.install(source/'package.json')
        self.assertEqual(registry.entries(),[])


if __name__=='__main__':unittest.main()
