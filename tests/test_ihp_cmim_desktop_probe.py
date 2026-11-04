"""Source-mode IHP capacitor producer, immutable fixture and fail-closed controls."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from icstudio.ihp_cmim_desktop_probe import FIELDS,FIXTURE,LICENSE,ORIGINAL,SOURCE,capture_ready,fixture,main,output_directory
from icstudio.model import file_digest,load_project

ROOT=Path(__file__).resolve().parents[1]
ASSET=ROOT/'icstudio/assets/qualification/ihp-cmim-reference'
NONCE='1234567890abcdef1234567890abcdef'


class CmimProducerTests(unittest.TestCase):
    def test_locked_fixture_contains_only_physical_metadata(self):
        data,source=fixture(ASSET)
        self.assertEqual(set(data),{'schema','source_project_sha256',*FIELDS})
        self.assertEqual(data['source_project_sha256'],ORIGINAL);self.assertEqual(source['mask_only_sha256'],FIXTURE)
        self.assertEqual(file_digest(ASSET/'SOURCE.json'),SOURCE);self.assertEqual(file_digest(ASSET/'LICENSE'),LICENSE)
        self.assertEqual(len(data['shapes']),29);self.assertFalse(data['layout_instances'])
        self.assertEqual({(p['name'],p['layer'],tuple(p['point'])) for p in data['layout_ports']},
                         {('C1','TopMetal1.drawing',(0,0)),('C2','Metal5.drawing',(3600,0))})

    def test_altered_fixture_source_or_license_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name in ('mask-only.json','SOURCE.json','LICENSE'):shutil.copyfile(ASSET/name,root/name)
            for name in ('mask-only.json','SOURCE.json','LICENSE'):
                path=root/name;before=path.read_bytes();path.write_bytes(before+b' ')
                with self.subTest(name=name),self.assertRaises(ValueError):fixture(root)
                path.write_bytes(before)
            fixture(root)

    def test_nonce_and_fresh_output_are_checked_before_gui(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'out'
            with self.assertRaisesRegex(ValueError,'Invalid execution identity'):main(['--out',str(out),'--execution-id','0'*31])
            self.assertFalse(out.exists());out.mkdir()
            with self.assertRaises(FileExistsError):main(['--out',str(out),'--execution-id',NONCE])
            with self.assertRaisesRegex(ValueError,'Unsafe output'):main(['--out',str(Path(tmp)/'tmpuxoell2b'/'out'),'--execution-id',NONCE])

    def test_frozen_producer_requires_managed_runtime_before_gui(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(sys,'frozen',True,create=True),\
             patch('icstudio.build_identity.identity',return_value={'commit':'a'*40,'dirty':False,'frozen':True}):
            out=Path(tmp)/'out';self.assertEqual(main(['--out',str(out),'--execution-id',NONCE]),1)
            report=json.loads((out/'report.json').read_bytes())
            self.assertIn('requires the included managed runtime',report['error']);self.assertIs(report['installed_acceptance'],False)

    def test_output_rejects_linked_ancestor_before_resolving(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent=Path(tmp)/'linked';out=parent/'out'
            visited=[]
            def linked(p):
                visited.append(p)
                if p==out:raise AssertionError('Must not inspect through a linked ancestor.')
                return p==parent
            with patch.object(Path,'is_symlink',autospec=True,side_effect=linked):
                with self.assertRaisesRegex(ValueError,'Linked output'):output_directory(out)
            self.assertIn(parent,visited);self.assertNotIn(out,visited)
            self.assertFalse(out.exists())

    def test_readiness_capture_binds_actual_record_and_rejects_unready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);key='a'*64;runtime={'kind':'linux','root':'/actual','sha256':key}
            status={'state':'ready','runtime':runtime,'evidence':'/checks/actual'}
            ready={'runtime':runtime,'evidence':'/checks/actual','manifest':'locked','backend':'locked'}
            path=root/('ready-'+key+'.json');path.write_text(json.dumps(ready))
            def capture(dest,resources,frozen):dest.mkdir();return {'runtime':runtime,'files':{}}
            with patch('icstudio.digital_runtime.status',return_value=status),patch('icstudio.digital_runtime.manifest',return_value={'sha256':key}),\
                 patch('icstudio.digital_runtime.state_root',return_value=root),patch('icstudio.ihp_cmim_desktop_probe.capture_runtime',side_effect=capture):
                saved,reported=capture_ready(root/'before',root,False)
                self.assertEqual(reported,status);self.assertEqual(saved['files']['ready.json'],file_digest(path))
                self.assertEqual((root/'before/ready.json').read_bytes(),path.read_bytes())
                path.write_text(json.dumps({**ready,'runtime':{'kind':'wrong'}}))
                with self.assertRaisesRegex(ValueError,'differs'):capture_ready(root/'after',root,False)
            with patch('icstudio.digital_runtime.status',return_value={'state':'setup'}):
                with self.assertRaisesRegex(ValueError,'not ready'):capture_ready(root/'unready',root,False)

    def test_real_source_gui_captures_fresh_reference_and_exact_masks(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'probe with spaces';env={k:v for k,v in os.environ.items() if not k.upper().startswith('GIT_')}
            env.update(QT_QPA_PLATFORM='offscreen',PYTHONDONTWRITEBYTECODE='1')
            # Seed a host profile whose delayed Layout restore would clear the schematic selection.
            host=Path(tmp)/'host-settings.ini'
            bootstrap='''
import json
from pathlib import Path
import runpy
import sys
from unittest.mock import patch
from PySide6.QtCore import QSettings
from icstudio import gui

path = Path(sys.argv.pop(1))
settings = QSettings(str(path), QSettings.IniFormat)
settings.setFallbacksEnabled(False)
settings.setValue('editor/workspaces/Last session', json.dumps(dict(
    mode=1, state='', splitter=[700, 700], filters=[], profile='Studio')))
settings.sync()
original = path.read_bytes()
try:
    with patch.object(gui, 'QSettings', return_value=settings):
        runpy.run_module('icstudio', run_name='__main__')
finally:
    settings.sync()
    if path.read_bytes() != original:
        raise AssertionError('The CMIM probe changed the host settings.')
'''
            command=[sys.executable,'-B','-c',bootstrap,str(host),'--ihp-cmim-acceptance','--execution-id',NONCE,'--out',str(out)]
            run=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
            self.assertEqual(run.returncode,0,run.stdout[-4000:]+run.stderr[-4000:]);report=json.loads((out/'report.json').read_bytes())
            self.assertEqual(report['status'],'passed');self.assertEqual(report['execution_id'],NONCE)
            for key in ('frozen','native_execution','qualified','installed_acceptance','full_family','release_ready','managed'):
                self.assertIs(report[key],False)
            self.assertIs(report['build']['frozen'],False);self.assertEqual(report['fixture_sha256'],FIXTURE)
            row=report['lifecycle'];self.assertEqual(row['top'],'coupon');self.assertEqual(row['project_name'],'IHP CMIM '+NONCE);self.assertEqual(row['nets'],{'c0':'C1','c1':'C2'})
            self.assertTrue(row['simulation_statement'].startswith('X'));self.assertIn('mm_ok=1',row['simulation_statement'])
            self.assertEqual((out/row['reference']).read_text(),row['reference_capture']['text'])
            self.assertIn(row['simulation_statement'],row['reference_capture']['text']);self.assertIn(NONCE,row['reference_capture']['text']);self.assertEqual(row['reference_sha256'],file_digest(out/row['reference']))
            project=load_project(out/row['project']);self.assertEqual(project,load_project(out/row['reopened_project']))
            cell=project['cells'][0];data,_=fixture(ASSET)
            for name in FIELDS:self.assertEqual(cell[name],data[name])
            self.assertEqual(len(cell['devices']),1);self.assertNotIn('native_spice',cell['devices'][0]);self.assertNotIn('lvs',cell['devices'][0]['model_ref'])
            for kind in ('project','reopened_project','schematic','gds','oasis'):
                self.assertEqual(file_digest(out/row[kind]),row[kind+'_sha256'])
            self.assertEqual(file_digest(out/'files.json'),report['files_sha256'])
            listed=json.loads((out/'files.json').read_bytes())
            self.assertIn('profile/settings.ini',listed)
            for name,expected in listed.items():self.assertEqual(file_digest(out/name),expected)


if __name__=='__main__':unittest.main()
