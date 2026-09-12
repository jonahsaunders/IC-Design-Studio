"""Desktop sessions for claimed concurrent layout partitions."""
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QLabel,QPushButton,QFileDialog,
    QInputDialog,QComboBox,QLineEdit,QFormLayout,QPlainTextEdit)
from .model import clone, digest
from .layout_collaboration import Session


class CollaborationMixin:
    def make_ui(self):
        super().make_ui();self.layout_session=None
        self.collaboration_timer=QTimer(self);self.collaboration_timer.setInterval(60000)
        self.collaboration_timer.timeout.connect(self.renew_layout_claims)

    def make_actions(self):
        # Both collaboration modes are reached through Tools → Collaboration.
        super().make_actions()

    def set_project(self,p,path=None):
        if getattr(self,'layout_session',None):self.shared_layout_leave()
        return super().set_project(p,path)

    def closeEvent(self,event):
        super().closeEvent(event)
        if event.isAccepted():self.shared_layout_leave()

    def shared_layout_start(self,create):
        if not self.idle_edit():return
        if self.layout_session:raise ValueError('Leave the current shared workspace first.')
        root=QFileDialog.getExistingDirectory(self,'Choose shared workspace directory')
        if not root:return
        name,ok=QInputDialog.getText(self,'Editor identity','Your editor name')
        if not ok:return
        if create:session=Session.create(root,self.project,name)
        else:
            session=Session.join(root,name)
            if not self.maybe_save():return
            self.set_project(clone(session.base))
        self.layout_session=session;self.collaboration_timer.start();self.shared_layout_dialog()

    def renew_layout_claims(self):
        if self.layout_session:
            try:self.layout_session.renew()
            except Exception as exc:self.statusBar().showMessage('Ownership renewal failed: '+str(exc),60000)

    def shared_layout_leave(self):
        session=getattr(self,'layout_session',None)
        if session:
            # A disconnected filesystem must never trap an editor in the UI.
            try:session.release()
            except Exception as exc:self.statusBar().showMessage('Claims will expire automatically: '+str(exc),10000)
            self.layout_session=None;self.collaboration_timer.stop()

    def _session(self):
        if not self.layout_session:raise ValueError('Create or join a shared workspace first.')
        if self.layout_session.base['id']!=self.project['id']:raise ValueError('This session belongs to another project.')
        return self.layout_session

    def _shared_install(self,q,title):
        if digest(q)!=digest(self.project):self.commit(lambda p:(p.clear(),p.update(clone(q))),title)
        self.statusBar().showMessage(title+' · shared revision '+str(self._session().revision),10000)

    def shared_layout_publish(self):
        if self.idle_edit():self._shared_install(self._session().publish(self.project),'Publish shared design')

    def shared_layout_refresh(self):
        if self.idle_edit():self._shared_install(self._session().refresh(self.project),'Refresh shared design')

    def shared_layout_dialog(self):
        session=self._session();dlg=QDialog(self);dlg.setWindowTitle('Shared schematic and layout editing');dlg.resize(780,570);v=QVBoxLayout(dlg)
        label=QLabel('Editor: '+session.editor+'\n'+str(session.root)+'\nClaim cells or separate layers before editing. Publication rejects expired claims, changes outside your partition and concurrent conflicts. Schematic edits require a whole-cell claim. Cell creation, symbol/port interfaces and project settings require a whole-project claim.');label.setWordWrap(True);v.addWidget(label)
        status=QPlainTextEdit();status.setReadOnly(True);status.setAccessibleName('Shared layout ownership');v.addWidget(status)
        form=QFormLayout();cells=QComboBox()
        cells.addItem('Whole project (hierarchy and settings)', '*')
        for c in self.project['cells']:cells.addItem(c['name'],c['id'])
        cells.setCurrentIndex(cells.findData(self.cid));layers=QLineEdit();layers.setPlaceholderText('Blank = whole cell; otherwise metal1, metal2');form.addRow('Cell',cells);form.addRow('Layers',layers);v.addLayout(form)
        error=QLabel();error.setWordWrap(True);v.addWidget(error)
        def refresh():
            s=session.status();by={c['id']:c['name'] for c in s['project']['cells']}
            status.setPlainText('Shared revision '+str(s['revision'])+'\n'+'\n'.join(c['editor']+' · '+by.get(c['cell_id'], 'Whole project')+' · '+(', '.join(c['layers']) if c['layers'] is not None else 'whole cell') for c in s['claims']))
        def act(fn):
            try:fn();refresh();error.clear()
            except Exception as exc:error.setText(str(exc))
        for title,fn in [('Claim partition',lambda:session.claim(cells.currentData(),[s.strip() for s in layers.text().split(',')] if layers.text().strip() else None)),('Release my claims for this cell',lambda:session.release(cells.currentData())),('Publish changes',self.shared_layout_publish),('Refresh shared design',self.shared_layout_refresh),('Refresh ownership',lambda:None)]:
            button=QPushButton(title);button.clicked.connect(lambda checked=False,fn=fn:act(fn));v.addWidget(button)
        refresh();self._collaboration_dialog=dlg;dlg.show();return dlg
