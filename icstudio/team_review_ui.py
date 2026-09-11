"""Revision-based team review inside the existing Tools collaboration dashboard."""
import uuid
from PySide6.QtCore import Qt, QRectF
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QComboBox,QPushButton,
    QTreeWidget,QTreeWidgetItem,QPlainTextEdit,QCheckBox,QInputDialog,QFileDialog,QDialog,QHeaderView)
from .model import clone,save_project,digest


class RevisionComparison(QDialog):
    def __init__(self,parent,before,after):
        super().__init__(parent)
        from .collaboration_dashboard import note
        from .collaboration_review_ui import GeometryView,description,show_schematics
        from .collaboration_document import diff, SCHEMATIC_FIELDS, STRUCTURE
        self.setWindowTitle('Compare design revisions');self.resize(1000,650)
        root=QVBoxLayout(self);root.addWidget(note('Changed geometry and objects. The left view is the saved checkpoint; the right view is the comparison revision.'))
        rows=diff(before,after)
        self.cells=QComboBox();self.cells.setAccessibleName('Changed cell');root.addWidget(self.cells)
        by={c['id']:c['name'] for c in before['cells']+after['cells']}
        for cid in dict.fromkeys(r['cell'] for r in rows):self.cells.addItem(by.get(cid,cid),cid)
        self.view_mode=QComboBox();self.view_mode.addItems(['Layout','Schematic']);self.view_mode.setAccessibleName('Comparison view')
        self.view_mode.setCurrentIndex(int(any(r['field'] in set(SCHEMATIC_FIELDS)|STRUCTURE for r in rows)));root.addWidget(self.view_mode)
        views=QHBoxLayout();self.views=[GeometryView('Checkpoint','#d58b2b'),GeometryView('Comparison','#427ce8')]
        for v in self.views:views.addWidget(v)
        root.addLayout(views,1);self.table=QTreeWidget();self.table.setHeaderLabels(['Object','Checkpoint','Comparison']);root.addWidget(self.table,1)
        self.table.setColumnWidth(0,200);self.table.setColumnWidth(1,340);self.table.header().setStretchLastSection(True)
        self.status=note('');root.addWidget(self.status)
        def draw():
            local=[r for r in rows if r['cell']==self.cells.currentData()];self.table.clear();groups=[[],[]]
            for r in local[:2000]:
                item=QTreeWidgetItem([r['field']+' / '+str(r['key']),description(r['before']),description(r['after'])])
                for col in range(3):item.setToolTip(col,item.text(col))
                self.table.addTopLevelItem(item)
                if r['field']=='shapes':
                    for i,key in enumerate(('before','after')):
                        if r[key]:groups[i].append(r[key])
            if self.view_mode.currentIndex()==1:
                show_schematics(self.views,[before,after],self.cells.currentData(),local)
                self.status.setText(f'{len(local)} changed objects or settings. Complete cell schematics shown; first 2,000 changes listed.' if len(local)>2000 else f'{len(local)} changed objects or settings. Changed objects are highlighted; wheel to zoom and drag to pan.')
                return
            points=[p for g in groups for s in g for p in s['points']]
            if len(points)>60000:groups=[[],[]];points=[]
            if points:
                xs,ys=zip(*points);box=QRectF(min(xs),min(ys),max(xs)-min(xs),max(ys)-min(ys));margin=max(box.width(),box.height(),100)*.15;box=box.adjusted(-margin,-margin,margin,margin)
            else:box=QRectF(-100,-100,200,200)
            for view,group in zip(self.views,groups):view.show_shapes(group,box)
            self.status.setText(f'{len(local)} changed objects in this cell. '+('First 2,000 listed; export the checkpoint for complete inspection.' if len(local)>2000 else 'Wheel to zoom; drag to pan.'))
        self.cells.currentIndexChanged.connect(draw);self.view_mode.currentIndexChanged.connect(draw);draw()


class TeamReviewPanel(QWidget):
    def __init__(self,studio,parent=None):
        super().__init__(parent);self.studio=studio;self.busy=False;self.client=None;self.data={};self.failed_request=None;self.loaded_version=None
        from .collaboration_dashboard import note
        root=QVBoxLayout(self);self.note=note('Join a live workspace to save checkpoints, discuss objects, and review exact revisions.');root.addWidget(self.note)
        row=QHBoxLayout();self.checkpoints=QComboBox();self.checkpoints.setAccessibleName('Review checkpoint');row.addWidget(self.checkpoints,1)
        self.add_button=self.button('Save checkpoint…',self.create,row);self.button('Refresh',self.load,row);root.addLayout(row)
        row=QHBoxLayout();self.other=QComboBox();self.other.setAccessibleName('Compare checkpoint with');row.addWidget(self.other,1)
        self.button('Compare revisions',self.compare,row);self.button('Save checkpoint copy…',self.export_checkpoint,row);root.addLayout(row)
        self.decisions=note('');root.addWidget(self.decisions)
        self.comments=QTreeWidget();self.comments.setHeaderLabels(['Author / object','Comment','State']);self.comments.setAccessibleName('Checkpoint discussions');root.addWidget(self.comments,1)
        self.comments.setMinimumHeight(160);self.comments.setWordWrap(True)
        self.comments.header().setSectionResizeMode(0,QHeaderView.ResizeToContents);self.comments.header().setSectionResizeMode(1,QHeaderView.Stretch);self.comments.header().setSectionResizeMode(2,QHeaderView.ResizeToContents)
        self.comments.itemDoubleClicked.connect(lambda *_:self.call(self.read_comment))
        self.comment=QPlainTextEdit();self.comment.setPlaceholderText('Ask a question or explain the change…');self.comment.setAccessibleName('New review comment');self.comment.setMaximumHeight(85);root.addWidget(self.comment)
        row=QHBoxLayout();self.anchor=QCheckBox('Attach to current selection');row.addWidget(self.anchor,1)
        self.anchor_kind=QComboBox();self.anchor_kind.addItems(['Object','Terminal','Highlighted net','Electrical finding']);self.anchor_kind.setAccessibleName('Comment attachment type');row.addWidget(self.anchor_kind)
        root.addLayout(row);row=QHBoxLayout()
        self.comment_button=self.button('Post comment',self.post_comment,row);self.button('Read comment',self.read_comment,row);self.button('Go to object',self.navigate,row);self.button('Resolve',self.resolve,row);root.addLayout(row)
        row=QHBoxLayout();self.decision=QComboBox();self.decision.setAccessibleName('Review decision')
        for label,value in [('Request review','review_requested'),('Approve checkpoint','approved'),('Request changes','changes_requested')]:self.decision.addItem(label,value)
        row.addWidget(self.decision,1);self.decision_button=self.button('Record decision',self.decide,row);root.addLayout(row)
        self.reports=QComboBox();self.reports.setAccessibleName('Shared verification result');root.addWidget(self.reports)
        row=QHBoxLayout();self.share_button=self.button('Share completed run…',self.share_report,row);self.button('Inspect result',self.inspect_report,row);self.button('Re-run saved input',self.rerun_report,row);root.addLayout(row)
        self.retry_button=self.button('Retry last action',self.retry,root);self.retry_button.hide()
        self.checkpoints.currentIndexChanged.connect(self.fill)

    def button(self,label,fn,layout):
        button=QPushButton(label);button.clicked.connect(lambda _=False:self.call(fn));layout.addWidget(button);return button

    def call(self,fn):
        try:return fn()
        except Exception as exc:self.note.setText(str(exc))

    def refresh_state(self):
        client=self.studio.live_client
        edit=bool(client and client.connected and client.info['role']!='view')
        for b in (self.add_button,self.comment_button,self.decision_button,self.share_button):b.setEnabled(edit and not self.busy)
        if self.client is not client:
            self.client=client;self.data={};self.loaded_version=None;self.checkpoints.clear();self.comments.clear();self.reports.clear();self.failed_request=None;self.retry_button.hide()
        if client and self.isVisible() and not self.busy and self.loaded_version!=client.info.get('review_version'):
            self.call(self.load)

    def showEvent(self,event):
        super().showEvent(event);self.refresh_state()

    def request(self,data,callback,mutation=False):
        client=self.studio.live_client
        if client is None:raise ValueError('Share or join a live workspace first.')
        if not client.info.get('review_api'):raise ValueError('This server needs the team-review update. Ask the host to update IC Design Studio.')
        if self.busy:raise ValueError('The previous review request is still running.')
        if mutation and self.failed_request and data is not self.failed_request[0]:raise ValueError('Retry the pending review action before submitting another one.')
        if mutation:data.setdefault('id',uuid.uuid4().hex)
        self.busy=True
        def finished(status,result):
            self.busy=False
            if self.studio.live_client is not client:return
            if status!=200:
                self.note.setText(result.get('error','Review request failed.'))
                if mutation and (not status or status>=500):self.failed_request=(data,callback);self.retry_button.show()
                else:self.failed_request=None;self.retry_button.hide()
                return
            self.failed_request=None;self.retry_button.hide();self.loaded_version=client.info.get('review_version')
            self.call(lambda:callback(result))
        try:client.transport.post(client.server,client.path+'/review',client.token,data,finished)
        except Exception:self.busy=False;raise

    def load(self):
        def loaded(data):
            self.loaded_version=data.get('review_version',self.loaded_version)
            selected=self.checkpoints.currentData();self.data=data;self.checkpoints.blockSignals(True);self.checkpoints.clear();self.other.clear();self.other.addItem('Compare with current design',None)
            for c in data['checkpoints']:
                label=c['name']+' · r'+str(c['revision']);self.checkpoints.addItem(label,c['id']);self.other.addItem(label,c['id'])
            self.checkpoints.setCurrentIndex(max(0,self.checkpoints.findData(selected)));self.checkpoints.blockSignals(False);self.fill()
            self.note.setText('Reviews belong to immutable checkpoints. New design edits do not inherit an earlier approval.')
        self.request({'action':'list'},loaded)

    def selected(self):
        key=self.checkpoints.currentData()
        if not key:raise ValueError('Save or select a checkpoint first.')
        return key

    def fill(self):
        key=self.checkpoints.currentData();self.comments.clear();self.reports.clear()
        for row in self.data.get('comments',[]):
            if row['checkpoint']==key:
                item=QTreeWidgetItem([row['author']+(' · attached object' if row['object'] else ''),row['text'],row['status']]);item.setData(0,Qt.UserRole,row);item.setToolTip(0,row['object']);item.setToolTip(1,row['text']);self.comments.addTopLevelItem(item)
        decisions=[r['author']+': '+r['status'].replace('_',' ')+((' · '+r['message']) if r['message'] else '') for r in self.data.get('decisions',[]) if r['checkpoint']==key]
        self.decisions.setText('\n'.join(decisions) or 'No review decision for this checkpoint yet.')
        for row in self.data.get('reports',[]):
            if row['checkpoint']==key:self.reports.addItem(row['name']+' · '+row['author'],row['id'])

    def create(self):
        client=self.studio.live_client
        if client is None:raise ValueError('Join a workspace first.')
        if client.pending or client.conflict or client.busy:raise ValueError('Wait for edits to synchronize before saving a checkpoint.')
        name,ok=QInputDialog.getText(self,'Save checkpoint','Checkpoint name',text='Design r'+str(client.revision))
        if ok:self.request(dict(action='create_checkpoint',revision=client.revision,name=name),lambda _:self.load(),True)

    def post_comment(self):
        data=dict(action='comment',checkpoint=self.selected(),text=self.comment.toPlainText(),cell='',object='')
        if self.anchor.isChecked():
            studio=self.studio;kind=self.anchor_kind.currentText()
            from .review_anchors import targets
            available=targets(studio.project,studio.cid,findings=kind=='Electrical finding')
            if kind=='Highlighted net':
                key='net:'+studio.net
                if key not in available:raise ValueError('Highlight a schematic net before attaching this comment.')
            elif kind in ('Terminal','Electrical finding'):
                prefix='terminal:' if kind=='Terminal' else 'finding:'
                choices={key:row for key,row in available.items() if key.startswith(prefix) and (kind!='Terminal' or any(i in studio.selection for i in row['objects']))}
                if not choices:raise ValueError('Select a component first.' if kind=='Terminal' else 'There are no electrical findings for this cell.')
                keys=list(choices);labels=[str(i+1)+' · '+choices[key]['label'] for i,key in enumerate(keys)]
                label,ok=QInputDialog.getItem(self,'Attach comment',kind,labels,0,False)
                if not ok:return
                key=keys[labels.index(label)]
            else:
                if len(studio.selection)!=1:raise ValueError('Select one object to attach the comment to.')
                key=studio.selection[0].removeprefix('pin:')
            data.update(cell=studio.cid,object=key)
        def posted(_):self.comment.clear();self.load()
        self.request(data,posted,True)

    def selected_comment(self):
        item=self.comments.currentItem()
        if item is None:raise ValueError('Select a comment first.')
        return item.data(0,Qt.UserRole)

    def resolve(self):
        row=self.selected_comment();self.request(dict(action='resolve_comment',comment=row['id'],version=row['version'],status='resolved'),lambda _:self.load(),True)

    def read_comment(self):
        row=self.selected_comment();self.studio.text_dialog('Comment by '+row['author'],row['text'])

    def navigate(self):
        row=self.selected_comment();studio=self.studio;cell=next((c for c in studio.project['cells'] if c['id']==row['cell']),None)
        if not studio.flush_inspector():return
        if cell is None or not row['object']:raise ValueError('This comment has no object available in the current design. Compare its checkpoint instead.')
        from .review_anchors import targets
        target=targets(studio.project,cell['id'],findings=row['object'].startswith('finding:')).get(row['object'])
        if target is None:raise ValueError('This object or finding changed after the checkpoint. Compare revisions to inspect it.')
        studio.cid=target.get('cell',cell['id']);studio.mode_combo.setCurrentIndex(0 if target['view']=='schematic' else 1);studio.net=target['net'];studio.refresh(True);studio.select(target['objects'],target['view'])

    def decide(self):
        self.request(dict(action='decide',checkpoint=self.selected(),status=self.decision.currentData(),text=self.comment.toPlainText()),lambda _:self.load(),True)

    def export_checkpoint(self):
        def received(data):
            path,_=QFileDialog.getSaveFileName(self,'Save checkpoint copy',data['name']+'.icproj','IC Studio project (*.icproj)')
            if path:save_project(data['project'],path)
        self.request(dict(action='checkpoint',checkpoint=self.selected()),received)

    def compare(self):
        other=self.other.currentData();current=clone(self.studio.project)
        def first(data):
            def show(after):self.comparison=RevisionComparison(self,data['project'],after);self.comparison.show()
            if other:self.request(dict(action='checkpoint',checkpoint=other),lambda second:show(second['project']))
            else:show(current)
        self.request(dict(action='checkpoint',checkpoint=self.selected()),first)

    def share_report(self):
        key=self.selected();rows=[r for r in self.studio.run_manager.rows if r['state']=='Complete' and r.get('result')]
        if not rows:raise ValueError('Complete a simulation before sharing its saved input and result.')
        choices=[str(i+1)+' · '+r['name'] for i,r in enumerate(rows)]
        name,ok=QInputDialog.getItem(self,'Share completed run','Run to share with this checkpoint',choices,0,False)
        if ok:
            row=rows[choices.index(name)];self.request(dict(action='share_report',checkpoint=key,name=row['name'][:100],job=row['job'],result=row['result']),lambda _:self.load(),True)

    def get_report(self,callback):
        key=self.reports.currentData()
        if not key:raise ValueError('Select a shared result first.')
        self.request(dict(action='report',report=key),callback)

    def inspect_report(self):
        def show(data):
            result=data['result'];specs=result.get('specifications',[]) or result.get('measurements',{}).get('measurements',[])
            text=data['name']+'\nSaved input: '+result.get('design_hash','')+'\nEngine: '+result.get('engine','')+'\n\n'
            text+='\n'.join(s['name']+': '+str(s.get('value',''))+' '+s.get('unit','')+' · '+s['status'] for s in specs)
            physical=result.get('silicon_report',{})
            text+='\n'+'\n'.join(s['name'].replace('_',' ')+': '+s['status']+(' · '+s['error'] if s.get('error') else '') for s in physical.get('stages',[]))
            text+='\n'+'\n'.join(m['name']+f": {m['before']:.6g} → {m['after']:.6g} {m['unit']}" for m in physical.get('comparison',[]))
            text+='\n\nShared by a teammate; the server stores provenance and does not independently run the verification.'
            self.studio.text_dialog('Shared verification result',text)
        self.get_report(show)

    def rerun_report(self):
        def run(data):
            original=data['job'];p=clone(original['project']);local=self.studio.project['pdk']
            if p['pdk'].get('package_lock')!=local.get('package_lock'):raise ValueError('Select the matching locked PDK revision before reproducing this run.')
            if local.get('package_root'):p['pdk']['package_root']=local['package_root']
            job=self.studio.prepare_simulation(original['settings'],original['engine'],p,original['cell'])
            if job['settings']['type']=='testbench':job['settings']['executable']=job['executable']
            job['shared_origin']={'input_hash':data['result']['design_hash'],'checkpoint':data['checkpoint']}
            self.studio.run_manager.enqueue(job,self.studio.jobs_dir,'Reproduce · '+data['name']);self.note.setText('Reproduction queued with the saved input and your local simulator.')
        self.get_report(run)

    def retry(self):
        if not self.failed_request:return
        data,callback=self.failed_request;self.request(data,callback,True)
