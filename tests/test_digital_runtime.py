"""Install integrity, failure states and cross-OS captured input regression tests.

These fixtures do not qualify an EDA engine; release CI runs the real package.
"""
import io
import json
import os
import shutil
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

    def test_native_setup_canonicalizes_state_directory_alias_before_journaling(self):
        data=self.package()
        if os.name=='nt':
            import ctypes
            short_path=ctypes.WinDLL('kernel32',use_last_error=True).GetShortPathNameW
            short_path.argtypes=[ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_uint32]
            short_path.restype=ctypes.c_uint32
            length=short_path(str(self.state.resolve()),None,0)
            if not length:self.skipTest('This Windows volume does not expose short directory names')
            buffer=ctypes.create_unicode_buffer(length)
            if not short_path(str(self.state.resolve()),buffer,length):
                self.skipTest('This Windows volume does not expose short directory names')
            alias=Path(buffer.value)
            if os.path.normcase(str(alias))==os.path.normcase(str(self.state.resolve())):
                self.skipTest('This Windows temporary directory has no short-name alias')
        else:
            alias=self.root/'state-alias';alias.symlink_to(self.state,target_is_directory=True)
        target=alias/'runtimes'/data['sha256'];journals=[];extract=runtime.extract
        def capture_extraction(archive,destination):
            journals.append(json.loads((self.state/'partial-install.json').read_text()))
            extract(archive,destination)
        with patch.object(runtime,'identity'),patch.object(runtime.host_platform,'libc_ver',return_value=('glibc','2.39')), \
             patch.object(runtime,'location',return_value={'kind':'linux','root':str(target),'sha256':data['sha256']}), \
             patch.object(runtime,'extract',side_effect=capture_extraction), \
             patch('icstudio.digital_setup_probe.qualify',side_effect=ValueError('proof failed')):
            with self.assertRaisesRegex(ValueError,'proof failed'):runtime.setup()
        self.assertEqual(len(journals),1)
        self.assertRegex(journals[0]['directory'],'^runtimes/'+data['sha256']+r'\.install-[0-9a-f]{32}$')
        self.assertTrue((target/'opt/icstudio/bin/yosys').is_file())
        self.assertFalse((self.state/'partial-install.json').exists())
        self.assertFalse(list(self.state.glob('ready-*.json')))

    def test_native_setup_rejects_target_outside_state_before_integrity_repair(self):
        data=self.package();valuable=self.root/'valuable';valuable.mkdir()
        project=valuable/'project.icproj';project.write_text('user data')
        with patch.object(runtime,'identity') as identity, \
             patch.object(runtime.host_platform,'libc_ver',return_value=('glibc','2.39')), \
             patch.object(runtime,'location',return_value={'kind':'linux','root':str(valuable),'sha256':data['sha256']}):
            with self.assertRaisesRegex(ValueError,'outside'):runtime.setup()
        identity.assert_not_called();self.assertEqual(project.read_text(),'user data')
        self.assertFalse(list(self.state.glob('ready-*.json')))

    @unittest.skipIf(os.name=='nt','Symlink creation may require Windows administrator permission')
    def test_native_setup_rejects_symlinked_target_and_parent_before_integrity_repair(self):
        data=self.package();valuable=self.root/'valuable';valuable.mkdir()
        project=valuable/'project.icproj';project.write_text('user data')
        target=self.state/'runtime';target.symlink_to(valuable,target_is_directory=True)
        parent=self.state/'runtimes';parent.symlink_to(valuable,target_is_directory=True)
        for path in (target,parent/data['sha256']):
            with self.subTest(path=path),patch.object(runtime,'identity') as identity, \
                 patch.object(runtime.host_platform,'libc_ver',return_value=('glibc','2.39')), \
                 patch.object(runtime,'location',return_value={'kind':'linux','root':str(path),'sha256':data['sha256']}):
                with self.assertRaisesRegex(ValueError,'symbolic link'):runtime.setup()
            identity.assert_not_called();self.assertEqual(project.read_text(),'user data')
        self.assertTrue(target.is_symlink());self.assertTrue(parent.is_symlink())
        self.assertFalse(list(self.state.glob('ready-*.json')))

    @unittest.skipUnless(os.name=='nt','Directory junctions are Windows-specific')
    def test_native_setup_rejects_junction_target_and_parent_before_integrity_repair(self):
        data=self.package();valuable=self.root/'valuable';valuable.mkdir()
        project=valuable/'project.icproj';project.write_text('user data')
        target=self.state/'runtime';parent=self.state/'runtimes'
        for path in (target,parent):
            subprocess.run(['cmd.exe','/c','mklink','/J',str(path),str(valuable)],check=True,capture_output=True)
        for path in (target,parent/data['sha256']):
            with self.subTest(path=path),patch.object(runtime,'identity') as identity, \
                 patch.object(runtime.host_platform,'libc_ver',return_value=('glibc','2.39')), \
                 patch.object(runtime,'location',return_value={'kind':'linux','root':str(path),'sha256':data['sha256']}):
                with self.assertRaisesRegex(ValueError,'junction'):runtime.setup()
            identity.assert_not_called();self.assertEqual(project.read_text(),'user data')
        self.assertTrue(target.is_junction());self.assertTrue(parent.is_junction())
        self.assertFalse(list(self.state.glob('ready-*.json')))

    def partial_install(self, data):
        directory=self.state/'runtimes'/(data['sha256']+'.install-'+'a'*32)
        directory.mkdir(parents=True);(directory/'partial-tool').write_text('fixture')
        record={'schema':1,'kind':'linux','sha256':data['sha256'],'directory':directory.relative_to(self.state).as_posix()}
        journal=self.state/'partial-install.json';journal.write_text(json.dumps(record))
        return directory,journal

    def test_cleanup_reacquires_setup_lock_and_removes_only_journaled_unpacking(self):
        data=self.package();directory,journal=self.partial_install(data)
        unowned=directory.with_name(data['sha256']+'.install-'+'b'*32);unowned.mkdir()
        with runtime.setup_lock(self.state):
            with self.assertRaisesRegex(ValueError,'already running'):
                runtime.cleanup_partial_install()
        self.assertTrue(directory.is_dir())
        self.assertTrue(runtime.cleanup_partial_install())
        self.assertFalse(directory.exists());self.assertFalse(journal.exists())
        self.assertTrue(unowned.is_dir(),'A directory without provenance must be retained')

    def test_partial_cleanup_rejects_unowned_paths(self):
        data=self.package();directory,journal=self.partial_install(data)
        record=json.loads(journal.read_text());record['directory']='../valuable'
        valuable=self.root/'valuable';valuable.mkdir();(valuable/'project.icproj').write_text('user data')
        journal.write_text(json.dumps(record))
        self.assertFalse(runtime.cleanup_partial_install())
        self.assertTrue(valuable.is_dir());self.assertTrue(directory.is_dir());self.assertTrue(journal.exists())

    def test_corrupt_archive_cannot_authorize_legacy_cleanup(self):
        data=self.package();directory,journal=self.partial_install(data);journal.unlink()
        (self.payload/'runtime.tar.gz').write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError,'damaged'):runtime.setup()
        self.assertTrue(directory.is_dir())

    @unittest.skipIf(os.name=='nt','Symlink creation may require Windows administrator permission')
    def test_partial_cleanup_rejects_symlinked_directory_and_parent(self):
        data=self.package();directory,journal=self.partial_install(data)
        valuable=self.root/'valuable';valuable.mkdir();(valuable/'project.icproj').write_text('user data')
        shutil.rmtree(directory);directory.symlink_to(valuable,target_is_directory=True)
        self.assertFalse(runtime.cleanup_partial_install());self.assertTrue((valuable/'project.icproj').is_file())
        directory.unlink();directory.parent.rmdir()
        directory.parent.symlink_to(valuable,target_is_directory=True)
        self.assertFalse(runtime.cleanup_partial_install());self.assertTrue((valuable/'project.icproj').is_file())

    @unittest.skipIf(os.name=='nt','Symlink creation may require Windows administrator permission')
    def test_legacy_cleanup_rejects_symlinked_directory_and_parent(self):
        data=self.package();directory,journal=self.partial_install(data);journal.unlink()
        valuable=self.root/'valuable';valuable.mkdir();(valuable/'project.icproj').write_text('user data')
        shutil.rmtree(directory);directory.symlink_to(valuable,target_is_directory=True)
        with runtime.setup_lock(self.state):
            self.assertEqual(runtime._cleanup_legacy_installs(self.state,data['sha256']),0)
        self.assertTrue((valuable/'project.icproj').is_file())
        directory.unlink();directory.parent.rmdir();directory.parent.symlink_to(valuable,target_is_directory=True)
        with runtime.setup_lock(self.state):
            self.assertEqual(runtime._cleanup_legacy_installs(self.state,data['sha256']),0)
        self.assertTrue((valuable/'project.icproj').is_file())

    @unittest.skipUnless(os.name=='nt','Directory junctions are Windows-specific')
    def test_partial_and_legacy_cleanup_reject_in_state_directory_and_parent_junctions(self):
        data=self.package();directory,journal=self.partial_install(data)
        record=journal.read_text();valuable=self.state/'valuable';valuable.mkdir()
        project=valuable/'project.icproj';project.write_text('user data')
        shutil.rmtree(directory)
        subprocess.run(['cmd.exe','/c','mklink','/J',str(directory),str(valuable)],check=True,capture_output=True)
        self.assertFalse(runtime.cleanup_partial_install())
        journal.unlink()
        with runtime.setup_lock(self.state):
            self.assertEqual(runtime._cleanup_legacy_installs(self.state,data['sha256']),0)
        self.assertTrue(directory.is_junction());self.assertEqual(project.read_text(),'user data')
        directory.rmdir();directory.parent.rmdir()
        preserved=valuable/directory.name;preserved.mkdir();(preserved/'partial-tool').write_text('user data')
        subprocess.run(['cmd.exe','/c','mklink','/J',str(directory.parent),str(valuable)],check=True,capture_output=True)
        journal.write_text(record)
        self.assertFalse(runtime.cleanup_partial_install())
        journal.unlink()
        with runtime.setup_lock(self.state):
            self.assertEqual(runtime._cleanup_legacy_installs(self.state,data['sha256']),0)
        self.assertTrue(directory.parent.is_junction());self.assertEqual(project.read_text(),'user data')
        self.assertEqual((preserved/'partial-tool').read_text(),'user data')

    @unittest.skipIf(os.name=='nt','Native Linux unpacking lifecycle')
    def test_retry_reclaims_partial_unpacking_after_worker_is_killed(self):
        from icstudio import digital_setup_probe
        data=self.package();started=self.root/'extract-started.json';entry=self.root/'interrupted-setup.py'
        entry.write_text('import json,sys,time\nfrom pathlib import Path\nfrom unittest.mock import patch\n'
            'sys.path.insert(0,'+repr(str(Path(__file__).resolve().parents[1]))+')\n'
            'from icstudio import digital_runtime as r\n'
            'def extract(archive,destination):\n'
            ' (destination/"partial-tool").write_text("fixture")\n'
            ' Path('+repr(str(started))+').write_text(json.dumps({"directory":str(destination)}))\n'
            ' while True:time.sleep(.02)\n'
            'with patch.object(r.host_platform,"libc_ver",return_value=("glibc","2.39")),patch.object(r,"extract",side_effect=extract):\n'
            ' r.setup()\n')
        worker=subprocess.Popen([sys.executable,str(entry)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        try:
            deadline=time.monotonic()+10
            while not started.is_file() and time.monotonic()<deadline and worker.poll() is None:time.sleep(.02)
            self.assertTrue(started.is_file(),'The controlled extraction did not start')
            directory=Path(json.loads(started.read_text())['directory'])
            worker.kill();worker.wait(timeout=5)
            self.assertTrue(directory.is_dir());self.assertTrue((self.state/'partial-install.json').is_file())
            # Older releases had this exact generated directory but no journal.
            (self.state/'partial-install.json').unlink()
            unrelated=directory.with_name('user-projects');unrelated.mkdir()
            other=directory.with_name('b'*64+'.install-'+'c'*32);other.mkdir()
            with patch.object(runtime,'identity'),patch.object(runtime.host_platform,'libc_ver',return_value=('glibc','2.39')), \
                 patch.object(digital_setup_probe,'qualify'):
                runtime.setup()
            self.assertFalse(directory.exists());self.assertFalse((self.state/'partial-install.json').exists())
            self.assertTrue(unrelated.is_dir());self.assertTrue(other.is_dir())
            self.assertTrue((Path(runtime.location(data)['root'])/'opt/icstudio/bin/yosys').is_file())
        finally:
            if worker.poll() is None:worker.kill();worker.wait(timeout=5)
            if worker.stdout:worker.stdout.close()

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

    def catalog(self, legacy=False):
        data=self.package();base=self.state/'runtime';folder=base/'opt/icstudio';folder.mkdir(parents=True,exist_ok=True)
        values={}
        for name in ('sky130hd','gf180','ihp-sg13g2'):
            record={'path':name+'/cells.lib','bytes':7,'sha256':'a'*64}
            values[name]={'version':1,'name':name,'revision':'fixture','directory':name,'corner':'typical',
                'corners':{'typical':[record['path']]},'root':'opt/icstudio/orfs/flow/platforms',
                'files':[record],'fingerprint':digest([record])}
        (folder/'platform.json').write_text(json.dumps(values['sky130hd']))
        (folder/'platforms.json').write_text(json.dumps({'schema':1,'default':'sky130hd','platforms':values}))
        if not legacy:data.update(platforms=list(values),default_platform='sky130hd')
        self.relock_catalog(folder,data)
        location={'kind':'linux','root':str(base),'sha256':data['sha256']}
        return data,location,folder

    def relock_catalog(self,folder,data):
        records={'opt/icstudio/'+name:file_digest(folder/name) for name in ('platform.json','platforms.json') if (folder/name).is_file()}
        (folder/'files.json').write_text(json.dumps(records));data['files_sha256']=file_digest(folder/'files.json')
        (folder/'runtime.json').write_text(json.dumps({'files_sha256':data['files_sha256']}))
        (self.payload/'manifest.json').write_text(json.dumps(data))

    def test_catalog_selection_preserves_all_platforms_and_returns_independent_locks(self):
        data,location,folder=self.catalog()
        with patch.object(runtime,'location',return_value=location):
            self.assertEqual(list(runtime.platforms(location)),data['platforms'])
            selected=runtime.platform(location,'gf180');selected['corner']='changed'
            self.assertEqual(runtime.platform(location,'gf180')['corner'],'typical')
            self.assertEqual(runtime.platform(location)['name'],'sky130hd')
            self.assertEqual(runtime.platform(location,'ihp-sg13g2')['root'],str((folder/'orfs/flow/platforms').resolve()))

    def test_new_catalog_cannot_fall_back_to_an_old_default_if_missing_or_tampered(self):
        data,location,folder=self.catalog()
        with patch.object(runtime,'location',return_value=location):
            path=folder/'platforms.json';path.write_text('{}')
            with self.assertRaisesRegex(ValueError,'changed or is missing'):runtime.platforms(location)
            path.unlink()
            with self.assertRaisesRegex(ValueError,'changed or is missing'):runtime.platforms(location)

    def test_catalog_membership_and_roots_are_validated_even_with_matching_file_hash(self):
        for fault in ('missing-platform','escaped-root','wrong-name','not-object'):
            with self.subTest(fault=fault):
                data,location,folder=self.catalog()
                path=folder/'platforms.json';catalog=json.loads(path.read_text())
                if fault=='missing-platform':del catalog['platforms']['ihp-sg13g2']
                elif fault=='escaped-root':catalog['platforms']['gf180']['root']='../outside'
                elif fault=='wrong-name':catalog['platforms']['gf180']['name']='sky130hd'
                else:catalog['platforms']['gf180']='invalid'
                path.write_text(json.dumps(catalog));self.relock_catalog(folder,data)
                with patch.object(runtime,'location',return_value=location):
                    with self.assertRaises(ValueError):runtime.platforms(location)

    def test_old_payload_only_offers_the_platform_it_contains(self):
        _,location,_=self.catalog(legacy=True)
        with patch.object(runtime,'location',return_value=location):
            self.assertEqual(list(runtime.platforms(location)),['sky130hd'])
            with self.assertRaisesRegex(ValueError,'does not include gf180'):runtime.platform(location,'gf180')

    def test_ready_requires_every_advertised_platform_to_have_completed_setup(self):
        data,location,_=self.catalog()
        record={'runtime':location,'manifest':digest(data),'backend':runtime.backend_identity(),'evidence':'fixture',
                'platforms':['sky130hd']}
        path=self.state/('ready-'+data['sha256']+'.json');path.write_text(json.dumps(record))
        with patch.object(runtime,'location',return_value=location):
            self.assertEqual(runtime.status()['state'],'setup')
            record['platforms']=data['platforms'];path.write_text(json.dumps(record))
            info=runtime.status();self.assertEqual(info['state'],'ready')
            self.assertIn('GF180',info['message']);self.assertIn('IHP',info['message'])

    def test_partial_setup_report_cannot_authorize_a_multi_platform_ready_record(self):
        data=self.package();data.update(platforms=['sky130hd','gf180','ihp-sg13g2'],default_platform='sky130hd')
        (self.payload/'manifest.json').write_text(json.dumps(data))
        with patch.object(runtime,'identity'),patch.object(runtime.host_platform,'libc_ver',return_value=('glibc','2.39')), \
             patch.object(runtime,'location',return_value={'kind':'linux','root':str(self.state/'runtime'),'sha256':data['sha256']}), \
             patch('icstudio.digital_setup_probe.qualify',return_value={'status':'PASS','platforms':['sky130hd']}):
            with self.assertRaisesRegex(ValueError,'every included platform'):runtime.setup()
        self.assertFalse(list(self.state.glob('ready-*.json')))


if __name__=='__main__': unittest.main()
