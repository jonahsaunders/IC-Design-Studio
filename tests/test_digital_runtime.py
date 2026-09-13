"""Install integrity, failure states and cross-OS captured input regression tests.

These fixtures do not qualify an EDA engine; release CI runs the real package.
"""
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

from icstudio import digital, digital_backend as backend, digital_runtime as runtime
from icstudio.model import clone, digest, file_digest


class DigitalRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name); self.payload=self.root/'payload'; self.payload.mkdir()
        self.state=self.root/'state'; self.state.mkdir()
        self.env=patch.dict(os.environ,{'ICSTUDIO_DIGITAL_PAYLOAD':str(self.payload),'ICSTUDIO_DIGITAL_STATE':str(self.state)})
        self.env.start(); self.addCleanup(self.env.stop)

    def package(self):
        archive=self.payload/'runtime.tar.gz'
        with tarfile.open(archive,'w:gz') as out:
            item=tarfile.TarInfo('opt/icstudio/bin/yosys'); data=b'fixture'; item.size=len(data); out.addfile(item,io.BytesIO(data))
        meta={'schema':1,'system':'ubuntu-24.04-x86_64','archive':archive.name,'sha256':file_digest(archive)}
        (self.payload/'manifest.json').write_text(json.dumps(meta)); return meta

    def test_corrupt_package_never_creates_ready_record(self):
        self.package(); (self.payload/'runtime.tar.gz').write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError,'damaged'): runtime.setup()
        self.assertEqual(runtime.status()['state'],'setup')
        self.assertFalse(list(self.state.glob('ready-*.json')))

    def test_safe_extraction_rejects_escape_and_absolute_links(self):
        for name,link in [('../escape',''),('a','/tmp/escape'),('a','../../escape')]:
            archive=self.root/'bad.tar.gz'
            with tarfile.open(archive,'w:gz') as out:
                item=tarfile.TarInfo(name)
                if link: item.type=tarfile.SYMTYPE; item.linkname=link
                out.addfile(item)
            with self.assertRaises(tarfile.FilterError): runtime.extract(archive,self.root/'extract')

    @unittest.skipIf(os.name=='nt','Native tar symlink extraction is tested on Linux')
    def test_builder_normalizes_docker_system_links_before_publication(self):
        from scripts.build_digital_runtime import pack_filesystem
        raw=self.root/'root.tar'; packed=self.root/'root.tar.gz'
        with tarfile.open(raw,'w') as out:
            item=tarfile.TarInfo('etc/mtab'); item.type=tarfile.SYMTYPE; item.linkname='/proc/mounts'; out.addfile(item)
        pack_filesystem(raw,packed); runtime.extract(packed,self.root/'extracted')
        link=self.root/'extracted/etc/mtab'
        self.assertEqual(os.readlink(link),'../proc/mounts')
        self.assertTrue(link.resolve().is_relative_to(self.root/'extracted'))

    def test_worker_translation_preserves_user_text_and_original_project(self):
        project=digital.counter_project(); project['digital']['files'][0]['text']+='\n// C:\\User Files\\source.sv is not an infrastructure path\n'
        job={'project':project,'cell':project['top'],'settings':{'runtime':{'kind':'wsl'},'tools':{'yosys':'opt/icstudio/bin/yosys'},
             'flow':{'root':r'C:\Flow Files'},'upstream':{'root':r'C:\Old Run','result_sha256':'locked'}}}
        original=clone(job); native=backend.translate(job,'/','/var/tmp/job-123')
        self.assertEqual(job,original)
        self.assertEqual(native['project']['digital']['files'],job['project']['digital']['files'])
        self.assertEqual(native['settings']['tools']['yosys'],'/opt/icstudio/bin/yosys')
        self.assertEqual(native['settings']['upstream']['root'],'/var/tmp/job-123/upstream-input')
        self.assertEqual(native['settings']['host_source_hash'],digital.source_hash(project['digital']))
        self.assertNotIn('runtime',native['settings'])

    def test_failed_acceptance_never_marks_installation_ready(self):
        data=self.package()
        with patch.object(runtime,'identity'), patch.object(runtime.host_platform,'libc_ver',return_value=('glibc','2.39')), \
             patch('icstudio.digital_setup_probe.qualify',side_effect=ValueError('proof failed')):
            # Test native failure semantics on Windows too, without importing WSL.
            with patch.object(runtime,'location',return_value={'kind':'linux','root':str(self.state/'runtime'),'sha256':data['sha256']}):
                with self.assertRaisesRegex(ValueError,'proof failed'): runtime.setup()
        self.assertFalse(list(self.state.glob('ready-*.json')))

    @unittest.skipIf(os.name=='nt','Unix executable permissions are restored inside Linux')
    def test_native_flow_restores_scripts_after_windows_transfer(self):
        from icstudio.digital_platform import pin_flow
        flow=self.root/'flow'; (flow/'scripts').mkdir(parents=True)
        (flow/'Makefile').write_text('all:\n\t./scripts/run.sh\n')
        script=flow/'scripts/run.sh'; script.write_text('#!/bin/sh\nprintf ready\n'); script.chmod(0o600)
        data=flow/'scripts/data.txt'; data.write_text('not executable'); data.chmod(0o600)
        captured=pin_flow(flow)
        backend.restore_flow_permissions({'settings':{'flow':captured}})
        self.assertEqual(subprocess.check_output([str(script)]),b'ready')
        self.assertEqual(data.stat().st_mode & 0o111,0)
        self.assertEqual(pin_flow(flow)['fingerprint'],captured['fingerprint'])
        script.write_text('#!/bin/sh\nprintf changed\n'); script.chmod(0o600)
        with self.assertRaisesRegex(ValueError,'changed'):
            backend.restore_flow_permissions({'settings':{'flow':captured}})
        self.assertEqual(script.stat().st_mode & 0o111,0)

    def test_ready_record_expires_when_backend_changes(self):
        data=self.package(); location=runtime.location(data)
        # The test does not create or start a WSL distribution.
        location={'kind':'linux','root':str(self.state/'runtime'),'sha256':data['sha256']}
        folder=Path(location['root'])/'opt/icstudio'; folder.mkdir(parents=True); (folder/'runtime.json').write_text('{}')
        record={'runtime':location,'manifest':digest(data),'backend':runtime.backend_identity(),'evidence':'fixture'}
        (self.state/('ready-'+data['sha256']+'.json')).write_text(json.dumps(record))
        with patch.object(runtime,'location',return_value=location):
            self.assertEqual(runtime.status()['state'],'ready')
            with patch.object(runtime,'backend_identity',return_value='changed'):
                self.assertEqual(runtime.status()['state'],'setup')

    def test_cancel_marker_is_scoped_to_one_job(self):
        a=self.root/'a'; b=self.root/'b'; a.mkdir(); b.mkdir()
        backend.cancel(a)
        self.assertTrue((a/'digital-cancel').is_file()); self.assertFalse((b/'digital-cancel').exists())

    def test_fresh_wsl_list_does_not_block_import_but_import_errors_remain_errors(self):
        completed=subprocess.CompletedProcess(['wsl.exe'],1,'No installed distributions'.encode('utf-16-le'),b'')
        with patch.object(runtime.shutil,'which',return_value='wsl.exe'), patch.object(runtime.subprocess,'run',return_value=completed):
            self.assertEqual(runtime.wsl(['--list','--quiet'],empty_list_ok=True),'')
            with self.assertRaisesRegex(ValueError,'No installed distributions'):
                runtime.wsl(['--import','fixture','folder','archive','--version','2'],empty_list_ok=True)

    @unittest.skipUnless(os.name!='nt' and Path('/proc').is_dir(),'Process-tree supervision requires Linux procfs')
    def test_native_supervisor_cancels_descendants_in_separate_sessions(self):
        entry=self.root/'entry.py'; marker=self.root/'cancel'; child_ready=self.root/'child-ready'; child_stopped=self.root/'child-stopped'
        child=('import signal,time; from pathlib import Path; '
               'signal.signal(signal.SIGTERM,lambda *_:(Path('+repr(str(child_stopped))+').write_text("stopped"),exit(0))); '
               'Path('+repr(str(child_ready))+').write_text("ready"); time.sleep(60)')
        code=('import sys,subprocess,time\n'
              'sys.path.insert(0,'+repr(str(Path(__file__).resolve().parents[1]))+')\n'
              'from icstudio import digital_backend as b\n'
              'def child(work):\n'
              ' p=subprocess.Popen([sys.executable,"-c",'+repr(child)+'],start_new_session=True)\n'
              ' p.wait()\n'
              'b.native_run=child\n'
              'raise SystemExit(b.supervise())\n')
        entry.write_text(code)
        process=subprocess.Popen([sys.executable,str(entry),str(self.root),str(marker)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        try:
            deadline=time.monotonic()+10
            while not child_ready.exists() and time.monotonic()<deadline: time.sleep(.02)
            self.assertTrue(child_ready.exists(),'Native child did not start')
            marker.write_text('cancel')
            output,_=process.communicate(timeout=10)
            self.assertNotEqual(process.returncode,0,output.decode())
            self.assertTrue(child_stopped.exists(),'Child in a separate process session was left running')
        finally:
            marker.write_text('cancel')
            if process.poll() is None: process.terminate(); process.wait(timeout=5)
            if process.stdout: process.stdout.close()

    def test_custom_tools_do_not_select_managed_backend(self):
        from icstudio import digital_flow
        executable=self.root/'yosys'; executable.write_text('fixture')
        with patch.object(runtime,'installed',side_effect=AssertionError('Custom toolchain must be preserved')):
            job=digital_flow.prepare(digital.counter_project(),'synth',tools={'yosys':str(executable)})
        self.assertNotIn('runtime',job['settings'])


if __name__=='__main__': unittest.main()
