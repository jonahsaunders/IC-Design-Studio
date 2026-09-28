"""Opt-in native desktop acceptance with separately recorded human observations."""
import hashlib
import json
import sys
import traceback
from pathlib import Path


def main(output):
    from PySide6.QtCore import QSettings,QTimer,Qt
    from PySide6.QtWidgets import (QApplication,QDialog,QVBoxLayout,QLabel,QTableWidget,
        QTableWidgetItem,QComboBox,QPushButton,QFileDialog,QLineEdit,QHeaderView)
    from unittest.mock import patch
    from .gui import Studio
    from .build_identity import diagnostic_report
    from .model import atomic_write
    from .experimental_probe import run
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=True)
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    app=QApplication([]);app.setStyle('Fusion')
    from .release_acceptance import TASKS,blockers
    report=json.loads(diagnostic_report());report.update(acceptance_schema=1,status='pending',observations=[],package=None)
    if app.platformName() in ('offscreen','minimal'):
        report.update(status='blocked',reason='Run native acceptance on a real interactive desktop.')
        atomic_write(out/'desktop-acceptance.json',json.dumps(report,indent=2));return 2
    settings=QSettings(str(out/'profile/settings.ini'),QSettings.IniFormat);settings.setFallbacksEnabled(False)
    with patch('icstudio.gui.QSettings',return_value=settings),patch('icstudio.gui.QStandardPaths.writableLocation',return_value=str(out/'profile/data')):
        w=Studio(recover=False)
    w.show();w.live_check.setChecked(False)
    dialog=QDialog(w);dialog.setWindowTitle('Native desktop acceptance');dialog.resize(900,570)
    layout=QVBoxLayout(dialog)
    note=QLabel('This uses an isolated test profile. Exercise the open app, record what you observed, and save evidence. Unperformed checks stay pending.');note.setWordWrap(True);layout.addWidget(note)
    package=QPushButton('Identify the downloaded installer or archive…');layout.addWidget(package)
    def choose_package():
        path,_=QFileDialog.getOpenFileName(dialog,'Select the package tested')
        if path:
            with Path(path).open('rb') as stream:checksum=hashlib.file_digest(stream,'sha256').hexdigest()
            report['package']=dict(name=Path(path).name,sha256=checksum);package.setText(Path(path).name+' · '+checksum[:12])
    package.clicked.connect(choose_package)
    host=QComboBox();host.setAccessibleName('Acceptance machine class')
    for title,value in [('Choose the tested machine…',None),('Consumer Windows','windows'),('Consumer Ubuntu','ubuntu'),('Hosted / virtual test runner','hosted')]:host.addItem(title,value)
    layout.addWidget(host)
    environment=QLineEdit();environment.setPlaceholderText('OS edition/build, machine, monitors and display scales');environment.setAccessibleName('Acceptance environment');layout.addWidget(environment)
    tasks=list(TASKS.values())
    table=QTableWidget(len(tasks),3);table.setHorizontalHeaderLabels(['Observed task','Result','Notes / environment']);table.setWordWrap(True)
    table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch);table.horizontalHeader().setSectionResizeMode(2,QHeaderView.Stretch)
    table.setColumnWidth(1,115);layout.addWidget(table,1);fields=[]
    for i,task in enumerate(tasks):
        item=QTableWidgetItem(task);item.setFlags(item.flags()&~Qt.ItemIsEditable);table.setItem(i,0,item)
        status=QComboBox();status.addItems(['Not run','Passed','Failed','Blocked']);status.setAccessibleName(task+' result');table.setCellWidget(i,1,status)
        notes=QLineEdit();notes.setAccessibleName(task+' notes');table.setCellWidget(i,2,notes);table.setRowHeight(i,62);fields.append((status,notes))
    save=QPushButton('Save acceptance evidence');layout.addWidget(save)
    def save_report():
        report['observations']=[dict(id=key,task=task,status=status.currentText(),notes=notes.text()) for (key,task),(status,notes) in zip(TASKS.items(),fields)]
        report.update(host_class='consumer' if host.currentData() in ('windows','ubuntu') else host.currentData(),
                      consumer_platform=host.currentData(),environment_notes=environment.text())
        statuses={row['status'] for row in report['observations']}
        report['blockers']=blockers(report)
        complete=not report['blockers']
        report['status']='passed' if complete else 'failed' if 'Failed' in statuses or report.get('automated',{}).get('status')=='failed' else 'pending'
        atomic_write(out/'desktop-acceptance.json',json.dumps(report,indent=2))
        w.grab().save(str(out/'native-desktop.png'));dialog.grab().save(str(out/'observations.png'))
        note.setText('Evidence saved to '+str(out)+'. Overall status: '+report['status'])
    save.clicked.connect(save_report)
    def automated():
        try:report['automated']={**run(w,out),'status':'passed'}
        except Exception:report['automated']=dict(status='failed',error=traceback.format_exc())
        save_report();dialog.show();dialog.raise_()
    QTimer.singleShot(150,automated)
    return app.exec()
