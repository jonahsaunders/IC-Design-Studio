"""A native learning hub and a persistent guide beside the circuit/RTL editors."""
import html
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut, QFontDatabase
from PySide6.QtWidgets import (QDialog,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QPushButton,
    QListWidget,QListWidgetItem,QListView,QTextBrowser,QPlainTextEdit,QComboBox,QProgressBar,QDockWidget,
    QLineEdit,QFileDialog,QFormLayout,QDialogButtonBox,QSplitter,QMenu,QScrollArea,QMessageBox)

from .model import digest, load_project, save_project, uid
from .student_hub import (Portfolio,curriculum,earned,complete,missing_prerequisites,next_lesson,
                         prepare_lesson,campaign_jobs,evaluate)
from .ui_style import palette, stylesheet


def label(text='',role=None):
    widget=QLabel(text);widget.setWordWrap(True);widget.setTextFormat(Qt.PlainText)
    if role:widget.setProperty('role',role)
    return widget


def button(text, callback, role=None):
    widget=QPushButton(text)
    # Enter in search must never open a project or an unrelated utility dialog.
    widget.setAutoDefault(False);widget.setDefault(False)
    if role:widget.setProperty('role',role)
    widget.clicked.connect(lambda _=False:callback())
    return widget


def feedback(widget,text,error=False):
    widget.setText(text);widget.setProperty('role','error' if error else 'muted')
    widget.style().unpolish(widget);widget.style().polish(widget)
    widget.setAccessibleName(text)


def student_style(dark,scale):
    t=palette(dark);size=round(14*scale/100)
    family=QFontDatabase.systemFont(QFontDatabase.GeneralFont).family().replace('"','')
    return stylesheet(dark)+f'''
    QWidget {{font-family:"{family}";font-size:{size}px;}}
    QLabel[role="section"], QLabel[role="subtitle"] {{font-size:{size}px;}}
    QLabel[role="title"] {{font-size:{round(24*scale/100)}px;}}
    QTextBrowser {{background:{t['panel']};color:{t['text']};border:0;padding:4px;}}
    QPushButton[role="primary"]:focus {{border:2px solid {t['text']};}}
    QTextBrowser:focus, QPlainTextEdit:focus, QListWidget:focus {{border:2px solid {t['accent']};}}
    QListWidget::item {{padding:10px 8px;}}
    QProgressBar {{max-height:8px;}}
    '''


class StudentHub(QDialog):
    def __init__(self,studio):
        super().__init__(studio);self.studio=studio;self.data=curriculum()
        self.portfolio=Portfolio(studio.data_dir/'student-hub');self.path_id='foundations'
        self.setWindowTitle('Student Hub · IC Design Studio');self.resize(1180,780);self.setMinimumSize(720,560)
        self.text_scale=int(studio.settings.value('student/textScale',100))
        if self.text_scale not in (100,125,150,200):self.text_scale=100
        self.by_id={l['id']:l for l in self.data['lessons']}
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0)
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);outer.addWidget(self.scroll)
        body=QWidget();self.scroll.setWidget(body)
        root=QVBoxLayout(body);root.setContentsMargins(20,16,20,16);root.setSpacing(12)
        head=QHBoxLayout();head.addWidget(label('Student Hub','title'),1)
        self.resume=button('Continue learning',lambda:self.call(self.continue_learning));head.addWidget(self.resume)
        self.more=button('More',lambda:None);self.more.setAccessibleName('Student Hub options')
        menu=QMenu(self.more);self.more.setMenu(menu)
        for title,fn in [('Continue learning',self.continue_learning),('Feature map',lambda:studio.open_editor_doc('STUDENT_HUB.md')),('Engine setup…',self.setup),
                         ('Export learning record…',self.export),('Locate lesson project…',self.locate),('Reload progress',self.reload_progress)]:
            menu.addAction(title,lambda fn=fn:self.call(fn))
        sizes=menu.addMenu('Text size')
        for scale in (100,125,150,200):sizes.addAction(f'{scale}%',lambda scale=scale:self.set_text_scale(scale))
        head.addWidget(self.more);root.addLayout(head)
        self.total=label('','muted');root.addWidget(self.total)
        self.path_picker=QComboBox();self.path_picker.setAccessibleName('Learning path');root.addWidget(self.path_picker)
        self.path_list=QListWidget();self.path_list.setAccessibleName('Learning paths');self.path_list.setMinimumWidth(175)
        self.path_list.setMaximumWidth(250);self.path_list.setWordWrap(True)
        for path in [*self.data['paths'],dict(id='capstone',title='Advanced project')]:
            item=QListWidgetItem(path['title']);item.setData(Qt.UserRole,path['id']);self.path_list.addItem(item)
            self.path_picker.addItem(path['title'],path['id'])
        self.path_list.currentRowChanged.connect(lambda i:self.choose_path(self.path_list.item(i).data(Qt.UserRole)) if i>=0 else None)
        self.path_picker.currentIndexChanged.connect(lambda i:self.choose_path(self.path_picker.itemData(i)))
        panes=QHBoxLayout();root.addLayout(panes,1);panes.addWidget(self.path_list)
        self.split=QSplitter();self.split.setChildrenCollapsible(False);panes.addWidget(self.split,1)
        left=QWidget();lv=QVBoxLayout(left);lv.setContentsMargins(0,0,0,0);self.split.addWidget(left)
        self.heading=label('','subtitle');lv.addWidget(self.heading)
        self.search=QLineEdit();self.search.setPlaceholderText('Find a lesson…');self.search.setAccessibleName('Find a student lesson');self.search.textChanged.connect(self.fill)
        lv.addWidget(self.search);self.search.setClearButtonEnabled(True)
        self.search.returnPressed.connect(lambda:self.lessons.setFocus())
        self.find_shortcut=QShortcut(QKeySequence.Find,self);self.find_shortcut.activated.connect(self.search.setFocus)
        self.lessons=QListWidget();self.lessons.setWordWrap(True);self.lessons.setObjectName('studentLessons');self.lessons.setAccessibleName('Learning progression');lv.addWidget(self.lessons,1)
        self.lessons.setResizeMode(QListView.Adjust);self.lessons.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.lessons.setMinimumHeight(120)
        self.lessons.itemActivated.connect(lambda _:self.call(self.start_selected))
        right=QWidget();rv=QVBoxLayout(right);rv.setContentsMargins(18,0,0,0)
        self.details=QTextBrowser();self.details.setOpenLinks(False);self.details.anchorClicked.connect(lambda url:self.select_lesson(url.toString()));rv.addWidget(self.details,1)
        self.details.setAccessibleName('Lesson overview');self.details.setMinimumWidth(240)
        self.progress_text=label('','muted');rv.addWidget(self.progress_text)
        self.progress=QProgressBar();self.progress.setTextVisible(False);self.progress.setAccessibleName('Lesson completion');rv.addWidget(self.progress)
        self.start=button('Start lesson',lambda:self.call(self.start_selected),'primary');rv.addWidget(self.start)
        self.split.addWidget(right);self.split.setSizes([320,600]);self.lessons.currentRowChanged.connect(self.detail)
        self.status=label('Progress is saved on this computer. Simulation checks and written reflections are recorded separately.','muted');root.addWidget(self.status)
        self.guide=LessonGuide(self);studio.addDockWidget(Qt.RightDockWidgetArea,self.guide);self.guide.hide()
        self.apply_theme();self.fill();self.search.setFocus()

    def apply_theme(self):
        style=student_style(self.studio.dark,self.text_scale)
        self.setStyleSheet(style);self.guide.setStyleSheet(style)
        columns=1 if self.text_scale>=150 else 2
        for i,control in enumerate(self.guide.controls.values()):self.guide.controls_layout.addWidget(control,i//columns,i%columns)
        self.details.document().setDefaultStyleSheet(f'a {{color:{palette(self.studio.dark)["accent"]};}} li {{margin-bottom:8px;}}')
        self.adapt_layout()
        scroll=self.details.verticalScrollBar().value();self.detail();self.details.verticalScrollBar().setValue(scroll)

    def set_text_scale(self,scale):
        self.text_scale=scale;self.studio.settings.setValue('student/textScale',scale);self.apply_theme();self.detail()

    def adapt_layout(self):
        compact=self.width()<1050 or self.text_scale>125
        self.path_list.setVisible(not compact);self.path_picker.setVisible(compact)
        self.resume.setVisible(self.width()>=850 and self.text_scale<=125)
        vertical=self.width()<850 or self.text_scale>=150
        orientation=Qt.Vertical if vertical else Qt.Horizontal
        if self.split.orientation()!=orientation:
            self.split.setOrientation(orientation);self.split.setSizes([220,420] if vertical else [320,600])

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'split'):self.adapt_layout()

    def call(self,fn):
        try:return fn()
        except Exception as exc:feedback(self.status,str(exc),True)

    def choose_path(self,key):
        if key is None:return
        self.path_id=key;self.search.clear();self.fill()

    def selected(self):
        item=self.lessons.currentItem();return self.by_id[item.data(Qt.UserRole)] if item else None

    def fill(self,*_):
        previous=self.selected();key=previous['id'] if previous else None;state=self.portfolio.state
        self.lessons.blockSignals(True);self.lessons.clear()
        self.total.setText(f'{sum(complete(state,l) for l in self.data["lessons"])} of {len(self.data["lessons"])} lessons complete · Four paths and an advanced project')
        self.path_list.blockSignals(True);self.path_picker.blockSignals(True)
        for i in range(self.path_list.count()):
            item=self.path_list.item(i);path_key=item.data(Qt.UserRole)
            ls=[l for l in self.data['lessons'] if l['path']==path_key];n=sum(complete(state,l) for l in ls)
            title=self.path_picker.itemText(i).split(' · ')[0]
            item.setText(title+f'\n{n} of {len(ls)} complete');self.path_picker.setItemText(i,title+f' · {n}/{len(ls)}')
            if path_key==self.path_id:self.path_list.setCurrentRow(i);self.path_picker.setCurrentIndex(i)
        self.path_list.blockSignals(False);self.path_picker.blockSignals(False)
        if self.path_id=='capstone':self.heading.setText(self.data['capstone']['subtitle'])
        else:self.heading.setText(next(p['subtitle'] for p in self.data['paths'] if p['id']==self.path_id))
        query=self.search.text().casefold()
        for l in self.data['lessons']:
            if l['path']!=self.path_id or query not in ' '.join([l['title'],l['summary'],*l['skills']]).casefold():continue
            count=len(earned(state,l));missing=missing_prerequisites(state,l,self.data)
            status='Completed' if complete(state,l) else 'Prerequisites needed' if missing else 'In progress' if count else 'Ready to start'
            item=QListWidgetItem(f'{l["title"]}\n{status} · {count}/{len(l["steps"])} steps · {l["minutes"]} min')
            item.setToolTip(item.text())
            item.setData(Qt.UserRole,l['id']);self.lessons.addItem(item)
            if key==l['id']:self.lessons.setCurrentItem(item)
        if self.lessons.currentRow()<0:self.lessons.setCurrentRow(0)
        self.lessons.blockSignals(False);self.detail()

    def detail(self,*_):
        l=self.selected();self.start.setEnabled(bool(l))
        if not l:
            self.details.setPlainText('No matching lessons. Clear the search to explore this path.')
            self.progress.setValue(0);self.progress_text.setText('');self.start.setText('Start lesson');return
        state=self.portfolio.state;missing=missing_prerequisites(state,l,self.data);done=earned(state,l)
        esc=html.escape
        direct=[k for k in l['requires'] if k in missing] or missing[:1]
        pre='<br>'.join(f'<a href="{k}">{esc(self.by_id[k]["path"].title()+" · "+self.by_id[k]["title"])}</a>' for k in direct)
        rows=''.join(f'<li><b>{esc(s["title"])}</b> · {"Earned" if s["id"] in done else {"quiz":"Knowledge check","check":"Workspace check","reflection":"Written reflection"}[s["kind"]]}</li>' for s in l['steps'])
        cap='<p>This milestone continues the same sensor project. Earlier repairs are preserved.</p>' if l['path']=='capstone' else ''
        self.details.setHtml(f'<h2>{esc(l["title"])}</h2><p>{esc(l["summary"])}</p>{cap}<p><b>Skills</b><br>{esc(" · ".join(l["skills"]))}</p>'+
            (f'<p><b>Complete first</b><br>{pre}</p><p>{len(missing)} prerequisite lesson(s) remaining. You can practice now; earn progression credit after the prerequisites.</p>' if missing else '<p>Ready for guided work in the real editor.</p>')+
            f'<ol>{rows}</ol><p>Expected time: {l["minutes"]} minutes. Earlier earned steps remain a record of the design that passed at that time.</p>')
        self.progress.setRange(0,len(l['steps']));self.progress.setValue(len(done));self.progress.setFormat('%v of %m steps earned')
        self.progress_text.setText(f'{len(done)} of {len(l["steps"])} steps complete')
        self.start.setText('Practice lesson' if missing else 'Review lesson' if complete(state,l) else 'Resume lesson' if self.portfolio.workspace(l) else 'Start lesson')

    def select_lesson(self,key):
        if key not in self.by_id:return
        self.path_id=self.by_id[key]['path'];self.search.clear();self.fill()
        for i in range(self.lessons.count()):
            if self.lessons.item(i).data(Qt.UserRole)==key:self.lessons.setCurrentRow(i);break

    def continue_learning(self):
        lesson=next_lesson(self.portfolio.state,self.data)
        if lesson:self.select_lesson(lesson['id']);self.start_selected()
        else:self.status.setText('All four paths and the advanced project are complete. Revisit any lesson or export your learning record.')

    def start_selected(self):
        from .student_projects import create
        l=self.selected()
        if not l:return
        self.guide.save_note()
        record=self.portfolio.workspace(l);s=self.studio
        if not record or s.project['id']!=record['project_id']:
            if not s._replace_document():return
            if record:
                path=Path(record['path'])
                if not path.is_file():raise ValueError('Saved lesson project is missing. Choose More → Locate lesson project to find it.')
                project=load_project(path)
                if project['id']!=record['project_id']:raise ValueError('The saved lesson file was replaced with a different project.')
            else:
                project=create(l['starter']);path=self.portfolio.root/'projects'/(l['workspace']+'-'+uid()+'.icproj')
                path.parent.mkdir(parents=True,exist_ok=True);save_project(project,path);self.portfolio.attach(l,project,path)
            s.set_project(project,path)
        self.guide.open_lesson(l);self.hide();self.guide.show();self.guide.raise_()
        s.resizeDocks([self.guide],[390],Qt.Horizontal)
        s.resizeDocks([s.inspector,self.guide],[260,620],Qt.Vertical)
        from .digital_design import config
        if not s.project.get('mixed_signal') and config(s.project,s.project['top']):self.guide.rtl()
        else:self.guide.workspace()
        self.guide.steps.setFocus()

    def locate(self):
        lesson=self.selected();record=self.portfolio.workspace(lesson) if lesson else None
        if not record:raise ValueError('Start this lesson before locating its project.')
        path,_=QFileDialog.getOpenFileName(self,'Locate '+lesson['title'],str(Path(record['path']).parent),'IC Studio project (*.icproj)')
        if not path:return
        self.relink(lesson,path)
        feedback(self.status,'Lesson project found. Resume the lesson to open it.')

    def relink(self,lesson,path):
        project=load_project(path);record=self.portfolio.workspace(lesson)
        if not record or project['id']!=record['project_id']:
            raise ValueError('This file belongs to a different project. Choose the original lesson project.')
        self.portfolio.attach(lesson,project,path);self.fill()

    def reload_progress(self):
        # Keep a local draft if another window saved unrelated progress. Never
        # overwrite a concurrently edited reflection without a deliberate choice.
        fresh=Portfolio(self.portfolio.root);g=self.guide
        if g.note_dirty and g.lesson and g.active_step:
            def note(state):return state.get('lessons',{}).get(g.lesson['id'],{}).get('notes',{}).get(g.active_step['id'],'')
            if note(fresh.state)!=note(self.portfolio.state):
                choice=self.resolve_reflection(g.notes.toPlainText(),note(fresh.state))
                if choice is None:return False
                if choice=='saved':
                    g.filling=True;g.notes.setPlainText(note(fresh.state));g.filling=False;g.note_dirty=False
                    feedback(g.note_status,'Saved reflection loaded.')
        self.portfolio=fresh;g.save_note();self.fill()
        feedback(self.status,'Progress reloaded. Your reflection draft is saved.')
        return True

    def resolve_reflection(self,local,saved):
        dialog=QMessageBox(self);dialog.setWindowTitle('Reflection changed in another window')
        dialog.setText('Choose which reflection to keep. Cancel preserves your unsaved draft.')
        dialog.setDetailedText('Your draft:\n'+local+'\n\nSaved reflection:\n'+saved)
        keep=dialog.addButton('Keep my draft',QMessageBox.AcceptRole)
        load=dialog.addButton('Use saved reflection',QMessageBox.DestructiveRole)
        cancel=dialog.addButton(QMessageBox.Cancel);dialog.setDefaultButton(cancel);dialog.exec()
        return 'local' if dialog.clickedButton() is keep else 'saved' if dialog.clickedButton() is load else None

    def tools(self):
        return {n:self.studio.settings.value('student/tools/'+n,self.studio.settings.value('mixed_signal/'+n,'')) for n in ('ngspice','iverilog','vvp')}

    def setup(self):
        dialog=QDialog(self);dialog.setWindowTitle('Student simulation engines');v=QVBoxLayout(dialog)
        v.addWidget(label('Foundations and Analog use the included teaching solver. Digital requires local Icarus (iverilog and vvp). Mixed Signal and the advanced project also require local ngspice.'))
        v.addWidget(label('Choose native local executables, or leave fields blank to find them on PATH. The managed digital container/WSL runtime is not used by these lessons.'))
        form=QFormLayout();v.addLayout(form);edits={}
        for name,value in self.tools().items():
            row=QHBoxLayout();edit=QLineEdit(value);edit.setPlaceholderText(name+' on PATH');row.addWidget(edit);button=QPushButton('Browse…');row.addWidget(button)
            def browse(_=False,edit=edit,name=name):
                path,_=QFileDialog.getOpenFileName(dialog,'Select '+name)
                if path:edit.setText(path)
            button.clicked.connect(browse);form.addRow(name,row);edits[name]=edit
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);v.addWidget(buttons)
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject)
        if dialog.exec()==QDialog.Accepted:
            for name,edit in edits.items():self.studio.settings.setValue('student/tools/'+name,edit.text().strip())

    def export(self):
        self.guide.save_note()
        # Export the open lesson's current work, including pending editor fields.
        record=self.portfolio.workspace(self.guide.lesson) if self.guide.lesson else None
        if record and record['project_id']==self.studio.project['id']:
            if not self.guide.save_work():return
        path,_=QFileDialog.getSaveFileName(self,'Export learning record','student-portfolio.json','Learning record (*.json)')
        if path:self.portfolio.export(path,self.data);feedback(self.status,'Learning record exported, including saved lesson projects and evidence references.')

    def reject(self):
        try:self.guide.save_note()
        except Exception as exc:feedback(self.status,str(exc),True);return
        super().reject()

    def closeEvent(self,event):
        try:self.guide.save_note()
        except Exception as exc:self.status.setText(str(exc));event.ignore();return
        super().closeEvent(event)


class LessonGuide(QDockWidget):
    def __init__(self,hub):
        super().__init__('Lesson guide',hub.studio);self.setObjectName('studentLessonGuide')
        self.hub=hub;self.studio=hub.studio;self.lesson=None;self.filling=False
        self.setMinimumWidth(300);self.setAllowedAreas(Qt.LeftDockWidgetArea|Qt.RightDockWidgetArea)
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);self.setWidget(self.scroll)
        body=QWidget();v=QVBoxLayout(body);v.setContentsMargins(14,12,14,12);v.setSpacing(10);self.scroll.setWidget(body)
        self.title=label('','subtitle');v.addWidget(self.title)
        self.steps=QComboBox();self.steps.setAccessibleName('Guided lesson step');self.steps.setMinimumContentsLength(10)
        self.steps.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon);v.addWidget(self.steps)
        self.instructions=QTextBrowser();self.instructions.setAccessibleName('Step instructions');self.instructions.setMinimumHeight(120);self.instructions.setMaximumHeight(260);v.addWidget(self.instructions)
        self.answer_label=label('Your answer');v.addWidget(self.answer_label)
        self.answer=QComboBox();self.answer.setAccessibleName('Knowledge check answer');self.answer.setMinimumContentsLength(10)
        self.answer.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon);v.addWidget(self.answer);self.answer_label.setBuddy(self.answer)
        self.notes_label=label('Your reflection');v.addWidget(self.notes_label)
        self.notes=QPlainTextEdit();self.notes.setPlaceholderText('Record your observations and reasoning…');self.notes.setAccessibleName('Lesson reflection');self.notes.setMinimumHeight(100);self.notes.setMaximumHeight(220);v.addWidget(self.notes);self.notes_label.setBuddy(self.notes)
        self.note_status=label('','muted');v.addWidget(self.note_status)
        self.check_button=button('Check this step',lambda:self.call(self.check),'primary');v.addWidget(self.check_button)
        self.feedback=label('');self.feedback.setTextInteractionFlags(Qt.TextSelectableByMouse);v.addWidget(self.feedback)
        self.next_button=button('Next step',lambda:self.call(self.advance),'secondary');v.addWidget(self.next_button);self.next_button.hide()
        self.run_status=label('','muted');v.addWidget(self.run_status)
        self.run_progress=QProgressBar();self.run_progress.setTextVisible(False);self.run_progress.setAccessibleName('Lesson run progress');v.addWidget(self.run_progress);self.run_progress.hide()
        self.controls_layout=QGridLayout();v.addLayout(self.controls_layout);self.controls={}
        for i,(title,fn) in enumerate([('Open workspace',self.workspace),('Open RTL',self.rtl),('Run lesson',self.run),('Results',self.results),
                                     ('Save work',self.save_work),('Cancel lesson runs',self.cancel),('Student Hub',self.show_hub),('Engine setup',hub.setup)]):
            b=button(title,lambda fn=fn:self.call(fn));self.controls_layout.addWidget(b,i//2,i%2);self.controls[title]=b
        self.qualify=button('Run four acceptance cases',lambda:self.call(self.qualification));v.addWidget(self.qualify)
        v.addStretch(1)
        self.steps.currentIndexChanged.connect(self.step_changed)
        self.note_timer=QTimer(self);self.note_timer.setSingleShot(True);self.note_timer.setInterval(600)
        self.note_timer.timeout.connect(lambda:self.call(self.save_note));self.notes.textChanged.connect(self.note_changed)
        self.active_step=None;self.note_dirty=False
        self.studio.run_manager.completed.connect(self.finished)
        self.studio.run_manager.changed.connect(self.update_run_state)

    def call(self,fn):
        try:return fn()
        except Exception as exc:feedback(self.feedback,str(exc),True)

    def require_project(self):
        record=self.hub.portfolio.workspace(self.lesson) if self.lesson else None
        if not record or record['project_id']!=self.studio.project['id']:
            raise ValueError('This guide belongs to another project. Resume the lesson from Student Hub.')

    def flush(self):
        self.require_project();s=self.studio
        window=getattr(s,'_digital_window',None)
        if window and window.dirty and not window.attempt(window.apply):raise ValueError('Correct the pending RTL edits first.')
        if not s.flush_inspector():raise ValueError('Correct the pending property edit first.')

    def open_lesson(self,lesson):
        self.save_note();self.lesson=lesson;self.title.setText(lesson['title']);self.active_step=None
        self.steps.blockSignals(True);self.steps.clear()
        done=earned(self.hub.portfolio.state,lesson)
        for i,step in enumerate(lesson['steps']):self.steps.addItem(f'{i+1}. '+step['title']+(' ✓' if step['id'] in done else ''))
        index=next((i for i,s in enumerate(lesson['steps']) if s['id'] not in done),len(lesson['steps'])-1)
        self.steps.setCurrentIndex(index);self.steps.blockSignals(False);self.step_changed(index)
        self.qualify.setVisible(lesson['id']=='c-qualify')
        self.controls['Open RTL'].setEnabled(lesson['path'] in ('digital','mixed','capstone'))
        self.update_run_state()

    def step_changed(self,index):
        if not self.lesson or index<0:return
        try:self.save_note()
        except Exception as exc:
            self.steps.blockSignals(True)
            self.steps.setCurrentIndex(self.lesson['steps'].index(self.active_step) if self.active_step else -1)
            self.steps.blockSignals(False);feedback(self.feedback,str(exc),True);return
        step=self.lesson['steps'][index];self.active_step=step;self.filling=True
        self.instructions.setPlainText(step['instructions'])
        self.answer.clear();self.answer.addItem('Choose an answer…',None)
        for i,text in enumerate(step.get('options',[])):self.answer.addItem(text,i)
        self.answer.setVisible(step['kind']=='quiz');self.notes.setVisible(step['kind']=='reflection')
        self.answer_label.setVisible(step['kind']=='quiz');self.notes_label.setVisible(step['kind']=='reflection');self.note_status.setVisible(step['kind']=='reflection')
        self.notes.setPlainText(self.hub.portfolio.state.get('lessons',{}).get(self.lesson['id'],{}).get('notes',{}).get(step['id'],''))
        self.note_dirty=False;self.filling=False
        self.note_status.setText('Draft saved on this computer.')
        self.check_button.setText('Record reflection' if step['kind']=='reflection' else 'Check this step')
        missing=missing_prerequisites(self.hub.portfolio.state,self.lesson,self.hub.data)
        feedback(self.feedback,'Practice mode: checks give feedback; earn prerequisite lessons before progression credit.' if missing else
                 'Previously earned for a captured design.' if step['id'] in earned(self.hub.portfolio.state,self.lesson) else '')
        self.update_next()

    def note_changed(self):
        if not self.filling:
            self.note_dirty=True;self.note_status.setText('Saving draft…');self.note_timer.start()

    def save_note(self):
        self.note_timer.stop()
        if self.lesson and self.active_step and self.note_dirty:
            try:self.hub.portfolio.save_note(self.lesson,self.active_step,self.notes.toPlainText())
            except Exception:
                feedback(self.note_status,'Draft not saved. Keep this window open and retry.',True);raise
            self.note_dirty=False;feedback(self.note_status,'Draft saved on this computer.')

    def check(self):
        self.flush();self.save_note();s=self.studio
        evidence=evaluate(self.active_step,self.lesson,s.project,s.run_manager.rows,s.path,self.answer.currentData(),self.notes.toPlainText())
        self.hub.portfolio.award(self.lesson,self.active_step,evidence,self.hub.data)
        index=self.steps.currentIndex();self.hub.fill()
        self.steps.setItemText(index,f'{index+1}. '+self.active_step['title']+' ✓')
        feedback(self.feedback,'Reflection recorded.' if self.active_step['kind']=='reflection' else 'Checkpoint passed. Evidence saved.')
        if complete(self.hub.portfolio.state,self.lesson):feedback(self.feedback,'Lesson complete. Continue learning or review your work.')
        self.update_next()

    def update_next(self):
        done=earned(self.hub.portfolio.state,self.lesson)
        self.next_button.setVisible(bool(self.active_step and self.active_step['id'] in done))
        self.next_button.setText('Continue learning' if complete(self.hub.portfolio.state,self.lesson) else 'Next step')

    def advance(self):
        if complete(self.hub.portfolio.state,self.lesson):self.hub.continue_learning();return
        done=earned(self.hub.portfolio.state,self.lesson)
        index=next((i for i,s in enumerate(self.lesson['steps']) if s['id'] not in done),None)
        if index is not None:self.steps.setCurrentIndex(index);self.steps.setFocus()

    def workspace(self):
        self.require_project();s=self.studio;s.leave_digital_workspace()
        s.cid=s.project.get('mixed_signal',{}).get('analog_cell',s.project['top'])
        s.mode_combo.setCurrentIndex(1 if self.lesson['starter']=='layout' else 0);s.refresh(True)
        self.show();self.raise_()

    def rtl(self):
        self.require_project();from .digital_design import config
        s=self.studio;cid=s.project.get('mixed_signal',{}).get('digital_cell',s.project['top'])
        if not config(s.project,cid):raise ValueError('This lesson has no RTL cell.')
        s.cid=cid;s.digital_window().workspace.switch_cell(cid);self.show();self.raise_()

    def run(self):
        self.flush();self.require_idle();s=self.studio;job=prepare_lesson(s.project,self.hub.tools())
        job['student_lesson']=self.lesson['id'];s.run_manager.enqueue(job,s.jobs_dir,'Student · '+self.lesson['title'])
        feedback(self.feedback,'Lesson simulation queued. You can keep editing while it runs.')

    def qualification(self):
        self.flush();self.require_idle();jobs=campaign_jobs(self.studio.project,self.hub.tools())
        for job in jobs:job['student_lesson']=self.lesson['id']
        self.studio.run_manager.enqueue_many(jobs,self.studio.jobs_dir,['Student qualification · '+j['student_campaign']['case'] for j in jobs])
        feedback(self.feedback,'Four acceptance cases queued. Check the qualification step after all finish.')

    def lesson_rows(self):
        record=self.hub.portfolio.workspace(self.lesson) if self.lesson else None
        if not record:return []
        return [r for r in self.studio.run_manager.rows if r['job'].get('student_lesson') and
                r['job']['project']['id']==record['project_id']]

    def require_idle(self):
        if any(r['state'] in ('Queued','Running','Stopping') for r in self.lesson_rows()):
            raise ValueError('This lesson project already has an active run. Wait for it to finish or cancel it first.')

    def update_run_state(self):
        if not self.lesson:return
        record=self.hub.portfolio.workspace(self.lesson)
        bound=bool(record and record['project_id']==self.studio.project['id'])
        rows=self.lesson_rows();active=[r for r in rows if r['state'] in ('Queued','Running','Stopping')]
        can_run=bound and not active and self.lesson['starter']!='layout'
        self.controls['Run lesson'].setEnabled(can_run);self.qualify.setEnabled(can_run)
        self.controls['Cancel lesson runs'].setEnabled(bool(active));self.controls['Cancel lesson runs'].setVisible(bool(active))
        self.controls['Results'].setEnabled(bound and any(r.get('result') and r['job'].get('student_lesson')==self.lesson['id'] for r in rows))
        for name in ('Open workspace','Save work'):self.controls[name].setEnabled(bound)
        self.controls['Open RTL'].setEnabled(bound and self.lesson['path'] in ('digital','mixed','capstone'))
        self.check_button.setEnabled(bound)
        self.run_progress.setVisible(bool(active))
        if active:
            self.run_progress.setRange(0,100);self.run_progress.setValue(round(sum(r.get('progress',0) for r in active)/len(active)))
            self.run_status.setText(' · '.join(f'{sum(r["state"]==state for r in active)} {state.lower()}' for state in ('Running','Queued','Stopping') if any(r['state']==state for r in active)))
        elif not bound:self.run_status.setText('Resume this lesson from Student Hub to use its workspace.')
        elif rows:self.run_status.setText('Latest run: '+rows[-1]['state'])
        else:self.run_status.setText('Ready to run.' if self.lesson['starter']!='layout' else 'This lesson checks the layout without simulation.')

    def finished(self,row,result):
        if self.lesson and row in self.lesson_rows() and row['job'].get('student_lesson')==self.lesson['id']:
            feedback(self.feedback,row['name']+' · '+row['state']+'. '+('Open Results or check this step.' if result else row.get('log','')[-350:]),row['state']=='Failed')
        self.update_run_state()

    def results(self):
        self.require_project();s=self.studio
        rows=[r for r in self.lesson_rows() if r.get('result') and r['job'].get('student_lesson')==self.lesson['id']]
        if not rows:raise ValueError('Run this lesson first.')
        latest=rows[-1]
        if s.project.get('mixed_signal'):
            from .mixed_signal_ui import show
            dialog=show(s);dialog.runs.setCurrentIndex(dialog.runs.findData(latest['id']));return
        from .digital_design import config
        if config(s.project,s.project['top']):
            self.rtl();window=s.digital_window();window.runs.setCurrentIndex(window.runs.findData(latest['id']));window.reveal_results();return
        result=latest['result'];index=next((i for i,r in enumerate(s.jobs) if r==result),None)
        if index is None:s.add_result(result)
        else:s.run_combo.setCurrentIndex(index)
        s.results_dock.show();s.results_tabs.setCurrentIndex(0)

    def save_work(self):
        self.flush();self.save_note()
        if self.studio.save():
            self.hub.portfolio.attach(self.lesson,self.studio.project,self.studio.path)
            feedback(self.feedback,'Lesson project saved. Resume it from Student Hub on your next visit.');return True
        return False

    def cancel(self):
        rows=[r for r in self.lesson_rows() if r['state'] in ('Queued','Running')]
        self.studio.run_manager.cancel(rows)

    def show_hub(self):
        self.save_note();self.hub.select_lesson(self.lesson['id']);self.hub.show();self.hub.raise_();self.hub.start.setFocus()

    def closeEvent(self,event):
        try:self.save_note()
        except Exception as exc:self.feedback.setText(str(exc));event.ignore();return
        super().closeEvent(event)


def show(studio):
    hub=getattr(studio,'_student_hub',None)
    if hub is None:
        hub=StudentHub(studio);studio._student_hub=hub
        studio.task_menus['View'].addAction(hub.guide.toggleViewAction())
    else:
        hub.reload_progress()
    hub.fill();hub.show();hub.raise_();return hub


def install(studio):
    action=studio.action(studio.task_menus['File'],'Student Hub…',lambda:show(studio))
    studio.task_menus['File'].insertAction(studio.task_menus['File'].actions()[0],action)
    studio.action(studio.task_menus['Help'],'Student learning paths',lambda:show(studio))
