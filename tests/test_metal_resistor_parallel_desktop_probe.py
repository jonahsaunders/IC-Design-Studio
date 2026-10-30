"""Additive array probe boundaries and actual source Qt lifecycle."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from icstudio.metal_resistor_parallel_desktop_probe import CASES,MODELS,CONTRACT_SHA,HISTORICAL_CONTRACT_SHA,main,native_array,widened_vertices
from icstudio.model import file_digest,load_project

ROOT=Path(__file__).resolve().parents[1]
NONCE='123456789abcdef0123456789abcdef0'


def environment():
    values={k:v for k,v in os.environ.items() if not k.upper().startswith('GIT_')}
    values['QT_QPA_PLATFORM']='offscreen';return values


class ProbeBoundaries(unittest.TestCase):
    def test_frozen_contract_scope_and_exact_last_unit_edit(self):
        historical=ROOT/'docs/qualification/sky130-metal-parallel-installed-v1.json'
        self.assertEqual(file_digest(historical),HISTORICAL_CONTRACT_SHA)
        path=ROOT/'docs/qualification/sky130-metal-parallel-installed-v2.json'
        self.assertEqual(file_digest(path),CONTRACT_SHA);spec=json.loads(path.read_bytes())
        self.assertEqual(spec['gui'],json.loads(historical.read_bytes())['gui'])
        self.assertEqual(len(CASES),spec['gui']['clean_native_layouts'])
        self.assertEqual(spec['gui']['queued_jobs'],43)
        for points in ([[10000,-500],[12000,5500]],[[10000,0],[10000,5000],[12000,5000],[12000,0]]):
            before=[row[:] for row in points];self.assertEqual(widened_vertices(points),[[13000 if x==12000 else x,y] for x,y in points]);self.assertEqual(points,before)
        for points in ([[5000,0],[7000,5000]],[[10000,0],[12000,0]],[[10000,0],[12000,1],[10000,2]]):
            with self.assertRaises(ValueError):widened_vertices(points)

    def test_native_requires_actual_separate_units_and_exact_two_net_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'native.spice';top='metal_parallel_m1_m3_r0_'+NONCE[:12]
            valid=f'.subckt {top} R1 R2\n'+''.join(f'R{i} R1 R2 sky130_fd_pr__res_generic_m1 w=2 l=5\n' for i in range(3))+f'.ends {top}\n'
            path.write_text(valid);self.assertEqual(native_array(path,top,'m1',3)['unit_count'],3)
            wrong=[valid.replace('R2 sky130','floating sky130',1),valid.replace('R2 R1 R2','R1 R1 R2'),valid.replace('w=2','w=2 m=3',1),valid.replace('w=2','w=nan',1),valid.replace('l=5','l=4',1),valid.replace('res_generic_m1','res_generic_m2',1)]
            for text in wrong:
                path.write_text(text)
                with self.assertRaises(ValueError):native_array(path,top,'m1',3)
            path.write_text(valid.replace('w=2','w=3',1));native_array(path,top,'m1',3,[2,2,3])
            with self.assertRaises(ValueError):native_array(path,top,'m1',3)

    def test_frozen_custom_runtime_is_rejected_before_gui(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(sys,'frozen',True,create=True):
            out=Path(tmp)/'out';self.assertEqual(main(['--out',str(out),'--execution-id',NONCE,'--magic','external']),1)
            report=json.loads((out/'report.json').read_bytes());self.assertIn('requires included engines',report['error'])
            self.assertFalse(report['native_execution']);self.assertFalse(report['installed_acceptance']);self.assertFalse(report['full_family'])

    def test_nonce_and_fresh_output_are_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'out'
            with self.assertRaisesRegex(ValueError,'Invalid execution identity'):main(['--out',str(out),'--execution-id','0'*31])
            self.assertFalse(out.exists());out.mkdir()
            with self.assertRaises(FileExistsError):main(['--out',str(out),'--execution-id',NONCE])


class SourceQtProbeTests(unittest.TestCase):
    def test_actual_last_unit_rectangle_and_polygon_inspector(self):
        code=r'''
import sys
from pathlib import Path
from PySide6.QtCore import QSettings,QStandardPaths
from PySide6.QtWidgets import QApplication
from icstudio.gui import Studio
from icstudio.layout import rect
from icstudio.model import clone,example
from icstudio.metal_resistor_parallel_desktop_probe import edit_last_width,content
root=Path(sys.argv[1]);QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(root/'settings'))
QStandardPaths.writableLocation=staticmethod(lambda kind:str(root/'profile'/str(kind.value)))
app=QApplication([]);studio=Studio(recover=False);studio.maybe_save=lambda:True
try:
 for kind in ('rect','polygon'):
  project=example('empty');shape=rect('metal1',10000,-500,2000,6000)
  if kind=='polygon':shape.update(kind='polygon',points=[[10000,-500],[10000,5500],[12000,5500],[12000,-500]],holes=[])
  project['cells'][0]['shapes']=[shape];studio.set_project(project);before=clone(content(studio.project))
  edited=edit_last_width(app,studio,shape);assert max(v[0] for v in studio.cell['shapes'][0]['points'])==13000
  assert edited['before_points']==shape['points'];studio.undo();assert content(studio.project)==before
 print('ACTUAL_LAST_UNIT_INSPECTOR_PASS')
finally:studio.close();app.processEvents()
'''
        with tempfile.TemporaryDirectory() as tmp:
            run=subprocess.run([sys.executable,'-B','-X','pycache_prefix='+str(Path(tmp)/'unused-cache'),'-c',code,tmp],cwd=ROOT,env=environment(),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
            self.assertEqual(run.returncode,0,run.stdout[-3000:]+run.stderr[-3000:]);self.assertIn('ACTUAL_LAST_UNIT_INSPECTOR_PASS',run.stdout)

    def test_real_gui_array_exports_routes_history_and_reopen(self):
        import klayout.db as db
        from icstudio.catalog import binding_for,parameter_values
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'probe with spaces';command=[sys.executable,'-B','-X','pycache_prefix='+str(Path(tmp)/'unused-cache'),'-m','icstudio.metal_resistor_parallel_desktop_probe','--mode','lifecycle','--out',str(out),'--execution-id',NONCE]
            run=subprocess.run(command,cwd=ROOT,env=environment(),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=300)
            self.assertEqual(run.returncode,0,run.stdout[-6000:]+run.stderr[-6000:]);report=json.loads((out/'report.json').read_bytes())
            self.assertEqual(report['status'],'passed');self.assertEqual(report['binding_lifecycle'],[])
            for key in ('frozen','native_execution','qualified','release_ready','full_family','installed_acceptance'):self.assertIs(report[key],False)
            self.assertEqual([(v['model'],v['multiplicity'],v['rotation']) for v in report['lifecycle']],list(CASES))
            for row in report['lifecycle']:
                model,count,angle=row['model'],row['multiplicity'],row['rotation'];self.assertEqual(row['case'],f'{model}-m{count}-r{angle}')
                self.assertEqual(row['top'],f'metal_parallel_{model}_m{count}_r{angle}_{NONCE[:12]}')
                project=load_project(row['project']);cell=project['cells'][0];device=cell['devices'][0]
                self.assertEqual(parameter_values(binding_for(project['pdk'],device),device),dict(w=2,l=5,mult=count))
                line=next(v.split() for v in Path(row['reference']).read_text().splitlines() if v.startswith('R_R1 '))
                self.assertEqual(line[1:4],['R1','R2','sky130_fd_pr__res_generic_'+model]);self.assertEqual(set(line[4:]),{'w=2','l=5','m='+str(count)})
                for member in ('gds','oas'):
                    self.assertEqual(file_digest(row[member]),row[member+'_sha256']);layout=db.Layout();layout.read(row[member]);top=layout.cell(row['top']);self.assertIsNotNone(top)
                    layer=67+MODELS.index(model);marker=db.Region(top.begin_shapes_rec(layout.layer(layer,13))).merged();conductor=db.Region(top.begin_shapes_rec(layout.layer(layer,20))).merged()
                    self.assertEqual(marker.count(),count);self.assertEqual(marker.area(),count*2000*5000);self.assertEqual((conductor-marker).merged().count(),2)
            self.assertEqual([r['model'] for r in report['eco_lifecycle']],list(MODELS))
            for row in report['eco_lifecycle']:
                self.assertEqual([v['multiplicity'] for v in row['events']],[3,16,2,1])
                for event in row['events']:
                    folder=Path(event['folder']);states={key:load_project(folder/(key+'.icproj')) for key in ('before','requested','proposed','applied','undo','restored','reopened')}
                    self.assertEqual(states['proposed']['cells'],states['applied']['cells']);self.assertEqual(states['restored']['cells'],states['reopened']['cells']);self.assertEqual(states['undo']['cells'],states['requested']['cells'])
                    cell=states['reopened']['cells'][0];self.assertEqual({p['pin']:p['id'] for p in cell['layout_pins']},row['initial_pin_ids'])
                    self.assertEqual([s for s in cell['shapes'] if s['id'] in ('parallel-route-a','parallel-route-b')],row['routes'])
                    self.assertEqual(sum(s.get('device_id')==cell['devices'][0]['id'] for s in cell['shapes']),2 if event['multiplicity']==1 else 2*event['multiplicity']+2)
            files=json.loads((out/'files.json').read_bytes())
            self.assertEqual(files,{p.relative_to(out).as_posix():file_digest(p) for p in out.rglob('*') if p.is_file() and p not in (out/'files.json',out/'report.json')})
            self.assertEqual(file_digest(out/'files.json'),report['files_sha256'])


if __name__=='__main__':unittest.main()
