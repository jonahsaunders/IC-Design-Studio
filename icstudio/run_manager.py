"""Independent, durable simulation jobs with a bounded local scheduler."""
import json, os, subprocess, sys, time
from pathlib import Path
from PySide6.QtCore import QObject, QProcess, QTimer, Signal
from . import job_store
from .model import atomic_write, clone, now, uid


class RunManager(QObject):
    changed=Signal()
    completed=Signal(object,object)

    def __init__(self,parent=None,limit=2):
        super().__init__(parent);self.rows=[];self.limit=limit;self.scheduling=False

    @property
    def busy(self):return any(r['state'] in ('Queued','Running','Stopping') for r in self.rows)

    @property
    def processes(self):return [r['process'] for r in self.rows if r.get('process') is not None]

    def enqueue(self,job,root,name):
        path=Path(root)/job['project']['id']/(now().replace(':','-')+'_'+uid());path.mkdir(parents=True)
        atomic_write(path/'input.json',json.dumps(job,allow_nan=False))
        atomic_write(path/'run.json',json.dumps({'name':name,'created':now(),'order':time.time_ns()}))
        row={'id':path.name,'name':name,'job':clone(job),'path':path,'state':'Queued','progress':0,'elapsed':0.,'log':'','buffer':'','process':None,'started':None}
        self.rows.append(row);job_store.state(path,'queued');self.changed.emit();self.pump();return row

    def enqueue_many(self,jobs,root,names):
        if len(jobs)!=len(names):raise ValueError('Every case needs a name.')
        self.scheduling=True;self.blockSignals(True);out=[]
        try:
            for job,name in zip(jobs,names):out.append(self.enqueue(job,root,name))
        finally:self.scheduling=False;self.blockSignals(False);self.changed.emit();self.pump()
        return out

    def pump(self):
        if self.scheduling:return
        self.scheduling=True
        try:
            for row in self.rows:
                if len(self.processes)>=self.limit:break
                if row['state']=='Queued':self.launch(row)
        finally:self.scheduling=False
        self.changed.emit()

    def launch(self,row):
        proc=QProcess(self);row.update(process=proc,state='Running',started=time.monotonic())
        job_store.state(row['path'],'running');proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.setWorkingDirectory(str(Path(__file__).resolve().parents[1]))
        proc.readyReadStandardOutput.connect(lambda:self.read(row))
        proc.finished.connect(lambda code,status:self.finish(row,code))
        proc.errorOccurred.connect(lambda error:self.start_error(row,error))
        args=['--worker',str(row['path']/'input.json'),str(row['path']/'result.json')]
        if not getattr(sys,'frozen',False):args=[str(Path(__file__).resolve().parents[1]/'main.py')]+args
        proc.start(sys.executable,args)

    def start_error(self,row,error):
        if error==QProcess.FailedToStart:
            row['log']+='Worker could not start. Check the application installation.\n';self.finish(row,-1)

    def read(self,row):
        if row['process'] is None:return
        row['buffer']+=bytes(row['process'].readAllStandardOutput()).decode('utf-8',errors='replace')
        while '\n' in row['buffer']:
            line,row['buffer']=row['buffer'].split('\n',1)
            try:
                msg=json.loads(line)
                if 'progress' in msg:row['progress']=max(0,min(100,round(float(msg['progress'])*100)))
                text=msg.get('error') or msg.get('message')
                if text:row['log']+=str(text)+'\n'
            except (ValueError,TypeError):row['log']+=line+'\n'
        self.changed.emit()

    def finish(self,row,code):
        if row['process'] is None:return  # FailedToStart and finished may both fire.
        self.read(row);proc=row['process'];row['process']=None;proc.deleteLater()
        row['elapsed']=time.monotonic()-row['started'];row['log']+=row.pop('buffer','');row['buffer']=''
        result=None
        if row['state']=='Stopping':row['state']='Cancelled'
        elif code==0:
            try:
                result=job_store.read_result(row['path']/'result.json',row['job']['project']['id'],False)
                row.update(state='Complete',progress=100,result=result)
            except Exception as exc:row['state']='Failed';row['log']+=str(exc)+'\n'
        else:row['state']='Failed'
        job_store.state(row['path'],row['state'].lower(),exit_code=code,elapsed=row['elapsed'])
        atomic_write(row['path']/'output.log',row['log'])
        self.completed.emit(row,result);self.pump()

    def cancel(self,rows):
        for row in rows:
            if row['state']=='Queued':row['state']='Cancelled';job_store.state(row['path'],'cancelled')
            elif row['state']=='Running':
                row['state']='Stopping';proc=row['process']
                if os.name=='nt':subprocess.run(['taskkill','/PID',str(proc.processId()),'/T','/F'],capture_output=True)
                else:proc.terminate()
                QTimer.singleShot(2500,lambda row=row:self.kill_if_stopping(row))
        self.changed.emit();self.pump()

    def kill_if_stopping(self,row):
        if row['state']=='Stopping' and row.get('process') is not None:row['process'].kill()

    def load(self,root,project_id):
        if self.busy:raise ValueError('Stop the active simulations before switching projects.')
        self.rows=[]
        for path in sorted((Path(root)/project_id).glob('*/input.json'),key=lambda p:p.stat().st_mtime_ns)[-2000:]:
            try:
                job=json.loads(path.read_text());status=json.loads((path.parent/'status.json').read_text())
                if job['project']['id']!=project_id:continue
                state=status['status'].title()
                if state in ('Running','Queued','Stopping'):state='Interrupted'
                meta=json.loads((path.parent/'run.json').read_text()) if (path.parent/'run.json').exists() else {}
                row={'id':path.parent.name,'name':meta.get('name',job['settings']['type'].upper()),'job':job,'path':path.parent,'state':state,'progress':100 if state=='Complete' else 0,'elapsed':status.get('elapsed',0),'log':(path.parent/'output.log').read_text() if (path.parent/'output.log').exists() else '', 'buffer':'','process':None,'started':None}
                if state=='Complete':row['result']=job_store.read_result(path.parent/'result.json',project_id)
                self.rows.append(row)
            except (OSError,ValueError,KeyError):continue
        self.changed.emit()
