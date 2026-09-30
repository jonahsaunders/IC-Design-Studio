"""A native learning hub and a persistent guide beside the circuit/RTL editors."""
import html
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QPushButton,
    QListWidget,QListWidgetItem,QTextBrowser,QPlainTextEdit,QComboBox,QProgressBar,QDockWidget,
    QLineEdit,QFileDialog,QFormLayout,QDialogButtonBox,QSplitter)

from .model import digest, load_project, save_project, uid
from .student_hub import (Portfolio,curriculum,earned,complete,missing_prerequisites,next_lesson,
                         prepare_lesson,campaign_jobs,evaluate)
from .ui_style import palette


def label(text='',role=None):
    widget=QLabel(text);widget.setWordWrap(True);widget.setTextFormat(Qt.PlainText)
    if role:widget.setProperty('role',role)
    return widget


class StudentHub(QDialog):
    def __init__(self,studio):
        super().__init__(studio);self.studio=studio;self.data=curriculum()
        self.portfolio=Portfolio(studio.data_dir/'student-hub');self.path_id='foundations'
        self.setWindowTitle('Student Hub · IC Design Studio');self.resize(1180,810);self.setMinimumSize(850,650)
        self.by_id={l['id']:l for l in self.data['lessons']}
        t=palette(studio.dark)
        self.setStyleSheet(f'QListWidget#studentLessons::item {{padding:12px 8px; margin:3px; border:1px solid {t["line"]}; border-radius:6px;}} '
                          f'QListWidget#studentLessons::item:selected {{background:{t["tint"]};color:{t["text"]};}}')
        root=QVBoxLayout(self);root.setContentsMargins(24,20,24,18);root.setSpacing(12)
        head=QHBoxLayout();head.addWidget(label('Student Hub','title'),1)
        self.total=label('','muted');head.addWidget(self.total)
        resume=QPushButton('Continue learning');resume.setProperty('role','primary');resume.clicked.connect(lambda:self.call(self.continue_learning));head.addWidget(resume);root.addLayout(head)
        root.addWidget(label('Build real circuits. Predict the behavior, test your design, and keep the evidence.','muted'))
        cards=QHBoxLayout();root.addLayout(cards);self.cards={}
        for path in self.data['paths']:
            button=QPushButton();button.setMinimumHeight(80);button.setCheckable(True)
            button.setAccessibleName(path['title']+' learning path');button.clicked.connect(lambda _,key=path['id']:self.choose_path(key))
            button.setStyleSheet(f'QPushButton {{text-align:left;border-top:3px solid {path["color"]};padding:12px;}} QPushButton:checked {{background:{t["tint"]};}}')
            self.cards[path['id']]=button;cards.addWidget(button,1)
        row=QHBoxLayout();root.addLayout(row)
        self.heading=label('','section');row.addWidget(self.heading,1)
        for title,fn in [('Advanced project',lambda:self.choose_path('capstone')),('Feature map',lambda:studio.open_editor_doc('STUDENT_HUB.md')),
                         ('Engine setup',self.setup),('Export learning record',self.export)]:
            b=QPushButton(title);b.clicked.connect(lambda _,fn=fn:self.call(fn));row.addWidget(b)
        self.search=QLineEdit();self.search.setPlaceholderText('Find a lesson or feature in this path…');self.search.setAccessibleName('Find a student lesson');self.search.textChanged.connect(self.fill);root.addWidget(self.search)
        split=QSplitter();root.addWidget(split,1)
        self.lessons=QListWidget();self.lessons.setObjectName('studentLessons');self.lessons.setAccessibleName('Learning progression');split.addWidget(self.lessons)
        right=QWidget();rv=QVBoxLayout(right);rv.setContentsMargins(18,0,0,0)
        self.details=QTextBrowser();self.details.setOpenLinks(False);self.details.anchorClicked.connect(lambda url:self.select_lesson(url.toString()));rv.addWidget(self.details,1)
        self.details.document().setDefaultStyleSheet(f'a {{color:{t["accent"]};}} li {{margin-bottom:5px;}}')
        self.progress=QProgressBar();self.progress.setTextVisible(False);self.progress.setAccessibleName('Lesson completion');rv.addWidget(self.progress)
        self.start=QPushButton();self.start.setProperty('role','primary');self.start.clicked.connect(lambda:self.call(self.start_selected));rv.addWidget(self.start)
        split.addWidget(right);split.setSizes([400,700]);self.lessons.currentRowChanged.connect(self.detail)
        self.status=label('Progress is saved on this computer. Simulation checks and written reflections are recorded separately.','muted');root.addWidget(self.status)
        self.guide=LessonGuide(self);studio.addDockWidget(Qt.RightDockWidgetArea,self.guide);self.guide.hide()
        self.fill()

    def call(self,fn):
        try:return fn()
        except Exception as exc:self.status.setText(str(exc));self.guide.feedback.setText(str(exc))

    def choose_path(self,key):
        self.path_id=key;self.search.clear();self.fill()

    def selected(self):
        item=self.lessons.currentItem();return self.by_id[item.data(Qt.UserRole)] if item else None

    def fill(self,*_):
        previous=self.selected();key=previous['id'] if previous else None;state=self.portfolio.state
        self.lessons.blockSignals(True);self.lessons.clear()
        self.total.setText(f'{sum(complete(state,l) for l in self.data["lessons"])} / 28 lessons earned')
        for path in self.data['paths']:
            ls=[l for l in self.data['lessons'] if l['path']==path['id']];n=sum(complete(state,l) for l in ls)
            self.cards[path['id']].setText(path['title']+f'\n{n} / {len(ls)} lessons · '+path['level'])
            self.cards[path['id']].setChecked(path['id']==self.path_id)
        if self.path_id=='capstone':self.heading.setText('ADVANCED PROJECT · '+self.data['capstone']['subtitle'])
        else:self.heading.setText(next(p['subtitle'] for p in self.data['paths'] if p['id']==self.path_id))
        query=self.search.text().casefold()
        for l in self.data['lessons']:
            if l['path']!=self.path_id or query not in ' '.join([l['title'],l['summary'],*l['skills']]).casefold():continue
            count=len(earned(state,l));missing=missing_prerequisites(state,l,self.data)
            status='Completed' if complete(state,l) else 'Prerequisites needed' if missing else 'In progress' if count else 'Ready to start'
            item=QListWidgetItem(f'{l["title"]}\n{status} · {count}/{len(l["steps"])} steps · {l["minutes"]} min')
            item.setData(Qt.UserRole,l['id']);self.lessons.addItem(item)
            if key==l['id']:self.lessons.setCurrentItem(item)
        if self.lessons.currentRow()<0:self.lessons.setCurrentRow(0)
        self.lessons.blockSignals(False);self.detail()

    def detail(self,*_):
        l=self.selected();self.start.setEnabled(bool(l))
        if not l:self.details.setPlainText('No matching lessons. Clear the search to explore this path.');self.progress.setValue(0);return
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
        self.start.setText(('Practice lesson' if missing else 'Resume lesson' if self.portfolio.workspace(l) else 'Start lesson')+' →')

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
                if not path.is_file():raise ValueError('Saved lesson project is missing. Restore it at '+str(path))
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
        path,_=QFileDialog.getSaveFileName(self,'Export learning record','student-portfolio.json','Learning record (*.json)')
        if path:self.portfolio.export(path,self.data);self.status.setText('Learning record exported, including saved lesson projects and evidence references.')

    def closeEvent(self,event):
        try:self.guide.save_note()
        except Exception as exc:self.status.setText(str(exc));event.ignore();return
        super().closeEvent(event)


class LessonGuide(QDockWidget):
    def __init__(self,hub):
        super().__init__('STUDENT LESSON GUIDE',hub.studio);self.setObjectName('studentLessonGuide')
        self.hub=hub;self.studio=hub.studio;self.lesson=None;self.filling=False
        self.setMinimumWidth(300);self.setAllowedAreas(Qt.LeftDockWidgetArea|Qt.RightDockWidgetArea)
        body=QWidget();v=QVBoxLayout(body);v.setContentsMargins(14,12,14,12);v.setSpacing(9);self.setWidget(body)
        self.title=label('','section');v.addWidget(self.title)
        self.steps=QComboBox();self.steps.setAccessibleName('Guided lesson step');v.addWidget(self.steps)
        self.instructions=QTextBrowser();self.instructions.setMinimumHeight(110);v.addWidget(self.instructions,1)
        self.answer=QComboBox();self.answer.setAccessibleName('Knowledge check answer');v.addWidget(self.answer)
        self.notes=QPlainTextEdit();self.notes.setPlaceholderText('Record your observations and reasoning…');self.notes.setAccessibleName('Lesson reflection');self.notes.setMaximumHeight(160);v.addWidget(self.notes)
        self.check_button=QPushButton('Check this step');self.check_button.setProperty('role','primary');self.check_button.clicked.connect(lambda:self.call(self.check));v.addWidget(self.check_button)
        self.feedback=label('');self.feedback.setTextInteractionFlags(Qt.TextSelectableByMouse);v.addWidget(self.feedback)
        controls=QGridLayout();v.addLayout(controls);self.controls={}
        for i,(title,fn) in enumerate([('Open workspace',self.workspace),('Open RTL',self.rtl),('Run lesson',self.run),('Results',self.results),
                                     ('Save work',self.save_work),('Cancel lesson runs',self.cancel),('Student Hub',self.show_hub),('Engine setup',hub.setup)]):
            b=QPushButton(title);b.clicked.connect(lambda _,fn=fn:self.call(fn));controls.addWidget(b,i//2,i%2);self.controls[title]=b
        self.qualify=QPushButton('Run qualification · four cases');self.qualify.clicked.connect(lambda:self.call(self.qualification));v.addWidget(self.qualify)
        self.steps.currentIndexChanged.connect(self.step_changed)
        self.note_timer=QTimer(self);self.note_timer.setSingleShot(True);self.note_timer.setInterval(600)
        self.note_timer.timeout.connect(lambda:self.call(self.save_note));self.notes.textChanged.connect(self.note_changed)
        self.active_step=None;self.note_dirty=False
        self.studio.run_manager.completed.connect(self.finished)

    def call(self,fn):
        try:return fn()
        except Exception as exc:self.feedback.setText(str(exc))

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
        self.controls['Run lesson'].setEnabled(lesson['starter']!='layout')
        self.controls['Results'].setEnabled(lesson['starter']!='layout')
        self.controls['Open RTL'].setEnabled(lesson['path'] in ('digital','mixed','capstone'))

    def step_changed(self,index):
        if not self.lesson or index<0:return
        try:self.save_note()
        except Exception as exc:self.feedback.setText(str(exc));return
        step=self.lesson['steps'][index];self.active_step=step;self.filling=True
        self.instructions.setPlainText(step['instructions'])
        self.answer.clear();self.answer.addItem('Choose an answer…',None)
        for i,text in enumerate(step.get('options',[])):self.answer.addItem(text,i)
        self.answer.setVisible(step['kind']=='quiz');self.notes.setVisible(step['kind']=='reflection')
        self.notes.setPlainText(self.hub.portfolio.state.get('lessons',{}).get(self.lesson['id'],{}).get('notes',{}).get(step['id'],''))
        self.note_dirty=False;self.filling=False
        self.check_button.setText('Record reflection' if step['kind']=='reflection' else 'Check this step')
        missing=missing_prerequisites(self.hub.portfolio.state,self.lesson,self.hub.data)
        self.feedback.setText('Practice mode: checks give feedback; earn prerequisite lessons before progression credit.' if missing else
                              'Previously earned for a captured design.' if step['id'] in earned(self.hub.portfolio.state,self.lesson) else '')

    def note_changed(self):
        if not self.filling:self.note_dirty=True;self.note_timer.start()

    def save_note(self):
        self.note_timer.stop()
        if self.lesson and self.active_step and self.note_dirty:
            self.hub.portfolio.save_note(self.lesson,self.active_step,self.notes.toPlainText());self.note_dirty=False

    def check(self):
        self.flush();self.save_note();s=self.studio
        evidence=evaluate(self.active_step,self.lesson,s.project,s.run_manager.rows,s.path,self.answer.currentData(),self.notes.toPlainText())
        self.hub.portfolio.award(self.lesson,self.active_step,evidence,self.hub.data)
        old=self.steps.currentIndex();self.hub.fill();self.open_lesson(self.lesson)
        self.feedback.setText('Reflection recorded.' if self.lesson['steps'][old]['kind']=='reflection' else 'Checkpoint passed. Evidence saved.')
        if complete(self.hub.portfolio.state,self.lesson):self.feedback.setText('Lesson complete. Open Student Hub to continue or review your evidence.')

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
        self.flush();s=self.studio;job=prepare_lesson(s.project,self.hub.tools())
        job['student_lesson']=self.lesson['id'];s.run_manager.enqueue(job,s.jobs_dir,'Student · '+self.lesson['title'])
        self.feedback.setText('Lesson simulation queued. Keep editing or inspect Results when it completes.')

    def qualification(self):
        self.flush();jobs=campaign_jobs(self.studio.project,self.hub.tools())
        for job in jobs:job['student_lesson']=self.lesson['id']
        self.studio.run_manager.enqueue_many(jobs,self.studio.jobs_dir,['Student qualification · '+j['student_campaign']['case'] for j in jobs])
        self.feedback.setText('Four acceptance cases queued. The open design is unchanged. Check the qualification step after all finish.')

    def finished(self,row,result):
        if self.lesson and row['job'].get('student_lesson')==self.lesson['id']:
            self.feedback.setText(row['name']+' · '+row['state']+'. '+('Check the current step to assess the evidence.' if result else row.get('log','')[-350:]))

    def results(self):
        self.require_project();s=self.studio
        if s.project.get('mixed_signal'):
            from .mixed_signal_ui import show
            show(s);return
        from .digital_design import config
        if config(s.project,s.project['top']):self.rtl();return
        rows=[r for r in s.run_manager.rows if r.get('result') and r['job']['project']['id']==s.project['id']]
        if not rows:raise ValueError('Run the lesson first.')
        result=rows[-1]['result'];index=next((i for i,r in enumerate(s.jobs) if r==result),None)
        if index is None:s.add_result(result)
        else:s.run_combo.setCurrentIndex(index)
        s.results_dock.show();s.results_tabs.setCurrentIndex(0)

    def save_work(self):
        self.flush()
        if self.studio.save():
            self.hub.portfolio.attach(self.lesson,self.studio.project,self.studio.path)
            self.feedback.setText('Lesson project saved. Resume it from Student Hub on your next visit.')

    def cancel(self):
        self.require_project()
        rows=[r for r in self.studio.run_manager.rows if r['job'].get('student_lesson')==self.lesson['id'] and r['state'] in ('Queued','Running')]
        self.studio.run_manager.cancel(rows)

    def show_hub(self):
        self.save_note();self.hub.select_lesson(self.lesson['id']);self.hub.show();self.hub.raise_()

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
        hub.guide.save_note();hub.portfolio=Portfolio(hub.portfolio.root)
    hub.fill();hub.show();hub.raise_();return hub


def install(studio):
    action=studio.action(studio.task_menus['File'],'Student Hub…',lambda:show(studio))
    studio.task_menus['File'].insertAction(studio.task_menus['File'].actions()[0],action)
    studio.action(studio.task_menus['Help'],'Student learning paths',lambda:show(studio))
