import json,os,sys,subprocess,tempfile,time,threading,unittest
from pathlib import Path
from unittest.mock import patch
from icstudio.model import example,clone,digest,save_project,load_project,atomic_write,History,design_digest
from icstudio.project_store import save_directory,load_directory
from icstudio import recovery,job_store
from icstudio.engines import execute

class ReliabilityTests(unittest.TestCase):
    def test_transient_windows_replace_errors_keep_original_until_commit(self):
        for code in (5,32,33):
            with self.subTest(winerror=code), tempfile.TemporaryDirectory() as td:
                f=Path(td)/'journal.json';f.write_bytes(b'original');replace=os.replace;attempts=[]
                error=PermissionError(13,'Windows reader holds the file');error.winerror=code
                def transient(source,destination):
                    self.assertEqual(f.read_bytes(),b'original')
                    self.assertEqual(Path(source).read_bytes(),b'committed')
                    attempts.append(source)
                    if len(attempts)<3:raise error
                    replace(source,destination)
                with patch('icstudio.model.os.replace',side_effect=transient),patch('icstudio.model.time.sleep') as pause:
                    atomic_write(f,b'committed')
                self.assertEqual(f.read_bytes(),b'committed');self.assertEqual(len(set(attempts)),1)
                self.assertEqual(pause.call_count,2);self.assertEqual(list(Path(td).iterdir()),[f])
    def test_persistent_windows_replace_error_is_bounded_and_keeps_original(self):
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/'journal.json';f.write_bytes(b'original')
            error=PermissionError(13,'Still locked');error.winerror=5
            with patch('icstudio.model.os.replace',side_effect=error) as replace,patch('icstudio.model.time.sleep') as pause:
                with self.assertRaisesRegex(OSError,'replace the destination'):atomic_write(f,b'new')
                self.assertEqual(replace.call_count,6);self.assertAlmostEqual(sum(c.args[0] for c in pause.call_args_list),.3)
            self.assertEqual(f.read_bytes(),b'original');self.assertEqual(list(Path(td).iterdir()),[f])
    def test_unrelated_permission_error_is_not_retried(self):
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/'journal.json';f.write_bytes(b'original')
            with patch('icstudio.model.os.replace',side_effect=PermissionError(13,'Denied')) as replace,patch('icstudio.model.time.sleep') as pause:
                with self.assertRaises(OSError):atomic_write(f,b'new')
                self.assertEqual(replace.call_count,1);pause.assert_not_called()
            self.assertEqual(f.read_bytes(),b'original')
    @unittest.skipUnless(os.name=='nt','Windows open handles deny atomic replacement')
    def test_real_windows_reader_releases_file_during_atomic_save(self):
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/'journal.json';f.write_bytes(b'original');reader=f.open('rb')
            timer=threading.Timer(.05,reader.close);timer.start()
            try:atomic_write(f,b'committed')
            finally:timer.join();reader.close()
            self.assertEqual(f.read_bytes(),b'committed');self.assertEqual(list(Path(td).iterdir()),[f])
    def test_failed_atomic_replace_keeps_original(self):
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/'save.icproj';p=example();save_project(p,f);old=f.read_bytes();p['name']='Changed'
            with patch('icstudio.model.os.replace',side_effect=OSError('disk failure')):
                with self.assertRaises(OSError):save_project(p,f)
            self.assertEqual(f.read_bytes(),old);self.assertEqual(len(list(Path(td).iterdir())),1)
    def test_recovery_sessions_and_corrupt_latest_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=example();f=recovery.write(p,root/'session-a');p['name']='Newer';recovery.write(p,root/'session-a');other=recovery.write(p,root/'session-b');f.write_text('{truncated')
            recovered,fallback=recovery.read(f);self.assertTrue(fallback);self.assertEqual(recovered['name'],'RC low-pass');self.assertEqual(len(recovery.candidates(root)),2)
            recovery.clear(f);self.assertTrue(other.exists())
    def test_directory_manifest_failure_keeps_prior_commit(self):
        with tempfile.TemporaryDirectory() as td:
            p=example();save_directory(p,td);p['cells'][0]['devices'][0]['value']='2.0';real=atomic_write
            def fail_manifest(path,data):
                if Path(path).name=='project.icstudio':raise OSError('interrupt')
                return real(path,data)
            with patch('icstudio.project_store.atomic_write',side_effect=fail_manifest):
                with self.assertRaises(OSError):save_directory(p,td)
            self.assertEqual(load_directory(td)['cells'][0]['devices'][0]['value'],'1.8')
    def test_rejected_edit_does_not_change_history_or_serial(self):
        h=History(example());before=clone(h.project)
        with self.assertRaises(ValueError):h.commit(lambda p:p.update(name=''))
        self.assertEqual(h.serial,before['revision']);self.assertEqual(h.project,before)
        h.commit(lambda p:p.update(name='A'));h.undo();h.commit(lambda p:p.update(name='B'));self.assertFalse(h.redo_stack);self.assertEqual(h.project['name'],'B')
    def test_cancelled_and_mismatched_results_are_never_replayed(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=example();job={'project':p,'cell':p['top']};atomic_write(root/'input.json',json.dumps(job))
            r={'project_id':p['id'],'cell_id':p['top'],'design_hash':design_digest(p),'x':[],'traces':{}};atomic_write(root/'result.json',json.dumps(r));job_store.state(root,'cancelled')
            with self.assertRaises(ValueError):job_store.read_result(root/'result.json',p['id'])
            job_store.state(root,'complete');self.assertEqual(job_store.read_result(root/'result.json',p['id']),r)
            r['design_hash']='wrong';atomic_write(root/'result.json',json.dumps(r))
            with self.assertRaises(ValueError):job_store.read_result(root/'result.json',p['id'])
    @unittest.skipIf(os.name=='nt','POSIX process-group regression; Windows uses taskkill /T')
    def test_timeout_terminates_engine_descendants(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'orphan.txt';code="import time;from pathlib import Path;time.sleep(1);Path("+repr(str(out))+").write_text('orphan')"
            parent='import subprocess,sys,time;subprocess.Popen([sys.executable,"-c",'+repr(code)+']);time.sleep(10)'
            with self.assertRaises(subprocess.TimeoutExpired):execute([sys.executable,'-c',parent],td,timeout=.15)
            time.sleep(1.1);self.assertFalse(out.exists(),'A child engine outlived the cancelled job')
