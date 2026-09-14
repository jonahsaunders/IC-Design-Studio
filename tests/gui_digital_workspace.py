"""Workspace geometry, indexed physical selection and durable queue lifecycle."""
import json,os,sys,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')


def main():
    from PySide6.QtCore import QObject,Signal
    from PySide6.QtWidgets import QApplication,QComboBox,QLabel
    from PySide6.QtTest import QTest
    from icstudio.digital import counter_project
    from icstudio.digital_planning import controller_type
    from icstudio.model import clone,digest
    from icstudio.gui import Studio
    app=QApplication.instance() or QApplication([]);app.setStyle('Fusion')
    class Queue(QObject):
        completed=Signal(object,object)
        def __init__(self):super().__init__();self.rows=[]
        def enqueue(self,job,root,name):
            row={'id':str(len(self.rows)),'state':'Queued','job':job,'name':name,'path':Path(root),'log':''};self.rows.append(row);return row
        def cancel(self,rows):
            for row in rows:row['state']='Cancelled'
    class Window(QObject):
        def apply(self):return True
    with tempfile.TemporaryDirectory() as td:
        p=counter_project();w=Window();q=Queue();w.studio=SimpleNamespace(project=p,run_manager=q,jobs_dir=td,settings=SimpleNamespace(value=lambda *a:''))
        w.project_id=p['id'];w.cell_id=p['top'];w.config=p['digital'];w.workspace=SimpleNamespace(tools=lambda:{})
        w.simulator=QComboBox();w.simulator.addItem('Icarus','icarus');w.runs=QComboBox();w.message=QLabel()
        def prepare(project,stage,simulator,tools,**kw):
            return {'project':clone(project),'cell':kw['cell_id'],'environment':{},'settings':{'stage':stage}}
        with patch('icstudio.digital_flow.prepare',side_effect=prepare):
            flow=controller_type()(w);flow.start('simulate');QTest.qWait(20)
            assert flow.active and flow.record['steps'][0]['state']=='Running'
            flow.stop();assert flow.active_row is None and flow.record['state']=='Cancelled'
            # A queued cancellation emits no completed signal; resume must still work.
            p['digital']['files'][0]['text']+='\n// subsequent draft'
            flow.resume();QTest.qWait(20);row=q.rows[-1]
            assert 'subsequent draft' not in row['job']['project']['digital']['files'][0]['text']
            row['state']='Complete';q.completed.emit(row,{'digital_result':{'verdict':'PASS'}});QTest.qWait(20)
            assert flow.record['state']=='Complete'
            restored=controller_type()(w);restored.restore();assert restored.record['state']=='Complete'
            assert json.loads(flow.path.read_text())['steps'][0]['state']=='Complete'
    out=ROOT/'build/digital-workspace-ui';out.mkdir(parents=True,exist_ok=True)
    os.environ['XDG_DATA_HOME']=str(out/'profile/data');os.environ['XDG_CONFIG_HOME']=str(out/'profile/config')
    s=Studio(recover=False);s.set_project(counter_project());s.resize(1280,850);s.show();d=s.digital_window();QTest.qWait(200)
    assert s.centralWidget() is d and not s.toolbar.isVisible()
    assert all(not dock.isVisible() for dock,_ in s._digital_panels)
    assert s.minimumSizeHint().width()<=1280
    d.shell.mode(1);d.result_tabs.setCurrentWidget(d.workspace.timing_split);QTest.qWait(50)
    assert d.workspace.timing.isVisible() and d.workspace.linked_physical.isVisible()
    assert all(size>0 for size in d.workspace.timing_split.sizes())
    d.shell.mode(2)
    geometry={'die':[0,0,100,100],'components':[{'name':f'u{i}','master':'inv','x':i%150*.6,'y':i//150*.6,'width':.5,'height':.5} for i in range(22500)],
              'segments':[{'net':'clock','layer':'met2','points':[[0,50],[100,50]]}], 'pins':[]}
    d.workspace.physical.load(geometry);assert len(d.workspace.physical.objects)==22500
    d.workspace.physical.highlight(['u22499']);assert d.workspace.physical.scene().selectedItems()
    d.workspace.physical.set_filters(density=True,layer='met2');QTest.qWait(50);s.grab().save(str(out/'physical-density-dark.png'))
    s.toggle_theme();QTest.qWait(50);s.grab().save(str(out/'physical-density-light.png'))
    d.shell.mode(0);s.grab().save(str(out/'source-light.png'))
    s.leave_digital_workspace();assert s.centralWidget() is not d
    assert s.digital_window() is d;QTest.qWait(50)
    s.saved_hash=digest(s.project);s.close();QTest.qWait(20)
    print(json.dumps({'status':'passed','checks':['Captured flow resume','Queued cancellation','Persistent plan state','Central workspace lifecycle','1280px layout','Simultaneous timing and physical panes','22,500 indexed instances','Density/layer controls','Light and dark modes']}))


if __name__=='__main__':main()
