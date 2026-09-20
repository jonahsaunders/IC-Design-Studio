"""Paged campaign summaries; waveforms are loaded only for an inspected case."""
import json
import threading
from pathlib import Path
from PySide6.QtCore import Qt, QProcess, QTimer, QThread, Signal
from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSpinBox, QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QFileDialog)
from .verification_campaigns import Campaign, PAGE_SIZE, _command
from .model import clone


class CampaignCapture(QThread):
    captured=Signal(str)
    failed=Signal(str)

    def __init__(self,studio,project,plan,directory,prepare):
        super().__init__(studio);self.project=project;self.plan=plan;self.directory=directory;self.prepare=prepare
        self.cancelled=threading.Event()

    def run(self):
        from .verification_campaigns import create
        def prepare(*args):
            if self.cancelled.is_set():raise InterruptedError('Campaign preparation cancelled.')
            return self.prepare(*args)
        try:
            create(self.directory,self.project,self.plan,prepare);self.captured.emit(str(self.directory))
        except Exception as exc:self.failed.emit(str(exc))

    def shutdown(self):
        self.cancelled.set();self.wait(5000)


def prepare_campaign(studio,plan,directory,note):
    """Read GUI tool preferences once, then capture disk jobs off the GUI thread."""
    project=clone(studio.project);templates=[]
    def key(settings,engine,cell):
        return (engine,cell,json.dumps({k:v for k,v in settings.items() if k not in ('corner','temperature')},sort_keys=True))
    for entry in plan['entries']:
        settings=clone(entry['settings'])
        if plan.get('compare_layout'):settings['type']='silicon'
        prototype=studio.prepare_simulation(settings,entry['engine'],clone(project),entry['cell'])
        templates.append((key(settings,entry['engine'],entry['cell']),prototype))
    def prepare(settings,engine,snapshot,cell):
        prototype=next(value for identity,value in templates if identity==key(settings,engine,cell))
        job=clone(prototype);job['project']=clone(snapshot);job['settings'].update(clone(settings))
        if engine=='digital':
            from .digital_design import config,set_config
            set_config(job['project'],cell,clone(config(prototype['project'],cell)))
        return job
    thread=CampaignCapture(studio,project,plan,directory,prepare)
    captures=getattr(studio,'_campaign_captures',[]);captures.append(thread);studio._campaign_captures=captures
    note.setText('Capturing immutable campaign inputs. You can keep editing while preparation finishes.')
    thread.captured.connect(lambda path:(note.setText('Campaign captured.'),show(studio,path)))
    thread.failed.connect(note.setText)
    thread.finished.connect(lambda:captures.remove(thread) if thread in captures else None)
    QApplication.instance().aboutToQuit.connect(thread.shutdown)
    thread.start();return thread


class CampaignWindow(QDialog):
    def __init__(self, studio, directory):
        super().__init__(studio)
        self.studio=studio;self.campaign=Campaign(directory);self.offset=0;self.process=None;self.rows=[];self.error=''
        self.setWindowTitle('Verification campaign · '+self.campaign.manifest['name']);self.resize(1050,660)
        root=QVBoxLayout(self)
        self.note=QLabel('');self.note.setWordWrap(True);root.addWidget(self.note)
        controls=QHBoxLayout();root.addLayout(controls)
        self.workers=QSpinBox();self.workers.setRange(1,16);self.workers.setValue(2);self.workers.setAccessibleName('Concurrent campaign workers')
        controls.addWidget(QLabel('Workers'));controls.addWidget(self.workers)
        self.start=QPushButton('Run / resume');self.start.clicked.connect(lambda:self.call(self.run));controls.addWidget(self.start)
        self.pause=QPushButton('Pause');self.pause.clicked.connect(lambda:self.call(self.stop));controls.addWidget(self.pause)
        self.retry=QPushButton('Retry failures');self.retry.clicked.connect(lambda:self.call(lambda:self.run(True)));controls.addWidget(self.retry)
        self.failed=QCheckBox('Failures only');self.failed.toggled.connect(self.filter_changed);controls.addWidget(self.failed)
        self.table=QTableWidget(0,7);self.table.setHorizontalHeaderLabels(['Case','Test','Conditions','State','Attempt','Passed / failed','Details'])
        self.table.setAccessibleName('Campaign results, one hundred cases per page')
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers);self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents);self.table.horizontalHeader().setSectionResizeMode(6,QHeaderView.Stretch)
        root.addWidget(self.table,1)
        row=QHBoxLayout();root.addLayout(row)
        self.previous=QPushButton('Previous 100');self.previous.clicked.connect(lambda:self.move(-1));row.addWidget(self.previous)
        self.page_label=QLabel();row.addWidget(self.page_label)
        self.next=QPushButton('Next 100');self.next.clicked.connect(lambda:self.move(1));row.addWidget(self.next)
        self.inspect=QPushButton('Inspect saved case');self.inspect.clicked.connect(lambda:self.call(self.open_case));row.addWidget(self.inspect)
        export=QPushButton('Export summaries…');export.clicked.connect(lambda:self.call(self.export));row.addWidget(export)
        self.table.itemActivated.connect(lambda *_:self.call(self.open_case))
        self.table.itemSelectionChanged.connect(lambda:self.inspect.setEnabled(self.table.currentRow()>=0))
        self.timer=QTimer(self);self.timer.setInterval(1000);self.timer.timeout.connect(lambda:self.call(self.refresh));self.timer.start()
        QApplication.instance().aboutToQuit.connect(self.shutdown)
        self.refresh()

    def call(self, action):
        try:return action()
        except Exception as exc:self.error=str(exc);self.note.setText(self.error)

    def refresh(self):
        counts=self.campaign.counts();selected=self.table.currentRow()
        self.rows=self.campaign.page(self.offset, failures_only=self.failed.isChecked())
        self.table.setRowCount(len(self.rows))
        for i,row in enumerate(self.rows):
            summary=json.loads(row['summary']) if row['summary'] else {}
            detail=row['error'] or '; '.join(v['name']+': '+v['status'] for v in summary.get('requirements',[]) if v['status']!='PASS')
            labels=json.loads(row['labels']);conditions='RTL simulation' if labels.get('temperature') is None else f"{labels['corner']} · {labels['temperature']:g} °C"
            if labels.get('voltage') is not None:conditions+=f" · {labels['voltage']:g} V"
            values=[row['case_index'],row['name'],conditions,row['state'],row['attempts'],
                    f"{summary.get('passed',0)} / {summary.get('failed',0)}" if summary else '',detail]
            for j,value in enumerate(values):
                item=QTableWidgetItem(str(value));item.setToolTip(str(value));self.table.setItem(i,j,item)
        if 0<=selected<len(self.rows):self.table.selectRow(selected)
        self.previous.setEnabled(self.offset>0)
        self.next.setEnabled(bool(self.campaign.page(self.offset+PAGE_SIZE,1,self.failed.isChecked())))
        self.page_label.setText(f'{self.offset+1 if self.rows else 0}–{self.offset+len(self.rows)} · {counts["total"]} total')
        active=self.process is not None and self.process.state()!=QProcess.NotRunning
        self.start.setEnabled(not active);self.retry.setEnabled(not active);self.pause.setEnabled(active or bool(counts.get('Running')))
        self.inspect.setEnabled(self.table.currentRow()>=0)
        self.note.setText(self.error or ('Paused · ' if counts['paused'] else '')+' · '.join(f'{counts.get(key,0)} {key.lower()}' for key in ('Queued','Running','Complete','Failed','Interrupted'))+
                          '\nSaved inputs and individual waveforms remain available after closing this window. '+str(self.campaign.path))

    def filter_changed(self):
        self.offset=0;self.call(self.refresh)

    def move(self, direction):
        self.offset=max(0,self.offset+direction*PAGE_SIZE);self.call(self.refresh)

    def run(self, retry_failed=False):
        if self.process is not None and self.process.state()!=QProcess.NotRunning:return
        self.error='';self.campaign.resume(retry_failed)
        process=QProcess(self);self.process=process;self.output=''
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.readyReadStandardOutput.connect(self.read)
        process.finished.connect(self.finished)
        process.errorOccurred.connect(lambda error:self.note.setText('Campaign worker could not start. Check the application installation.') if error==QProcess.FailedToStart else None)
        command=_command('--campaign','run',str(self.campaign.path),'--workers',str(self.workers.value()),'--trust-project')
        process.start(command[0],command[1:]);self.refresh()

    def read(self):
        if self.process is not None:self.output=(self.output+bytes(self.process.readAllStandardOutput()).decode('utf-8','replace'))[-16000:]

    def finished(self, code, *_):
        self.read();self.refresh()
        if code:self.error=self.output or 'Campaign worker stopped. Saved cases can be resumed.';self.note.setText(self.error)

    def stop(self):
        self.campaign.pause()
        if self.process is not None and self.process.state()!=QProcess.NotRunning:self.process.terminate()
        self.refresh()

    def shutdown(self):
        if self.process is not None and self.process.state()!=QProcess.NotRunning:
            self.stop();self.process.waitForFinished(5000)

    def closeEvent(self,event):
        if self.process is not None and self.process.state()!=QProcess.NotRunning:self.stop()
        self.timer.stop()
        super().closeEvent(event)

    def showEvent(self,event):
        self.timer.start();self.call(self.refresh);super().showEvent(event)

    def open_case(self):
        index=self.table.currentRow()
        if index<0:raise ValueError('Select a saved case.')
        row=self.campaign.row(self.rows[index]['case_index'])
        from .analog_run_ui import RunInspector
        self.inspector=RunInspector(self.studio,row);self.inspector.show()

    def export(self):
        path,_=QFileDialog.getSaveFileName(self,'Export campaign summaries','campaign.csv','CSV (*.csv)')
        if path:self.campaign.export(path)


def show(studio, directory):
    # Keep independent campaigns alive across project switches; their inputs are
    # immutable and never loaded into the editable document by this window.
    windows=getattr(studio,'_campaign_windows',[])
    window=next((w for w in windows if w.campaign.path==Path(directory).resolve()),None)
    if window is None:
        window=CampaignWindow(studio,directory);windows.append(window);studio._campaign_windows=windows
    window.show();window.raise_();return window
