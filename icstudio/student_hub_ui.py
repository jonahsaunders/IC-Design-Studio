"""A native learning hub and a persistent guide beside the circuit/RTL editors."""
import html
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QEvent
from PySide6.QtGui import QKeySequence, QShortcut, QFontDatabase
from PySide6.QtWidgets import (QDialog,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QPushButton,
    QListWidget,QListWidgetItem,QListView,QTextBrowser,QPlainTextEdit,QComboBox,QProgressBar,QDockWidget,
    QLineEdit,QFileDialog,QFormLayout,QDialogButtonBox,QSplitter,QMenu,QScrollArea,QMessageBox,QTabWidget,QInputDialog)

from .model import digest, load_project, save_project, uid
from .student_hub import (Portfolio,curriculum,earned,complete,missing_prerequisites,next_lesson,
                         prepare_lesson,campaign_jobs,evaluate)
from .ui_style import palette, stylesheet
from .student_learning import study_guide, notes_html, overview_html, export_portfolio


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
    QTextBrowser:focus, QPlainTextEdit:focus, QLineEdit:focus, QListWidget:focus, QComboBox:focus {{border:2px solid {t['accent']};}}
    QLineEdit {{min-height:{round(22*scale/100)}px;}}
    QListWidget::item {{padding:10px 8px;}}
    QProgressBar {{max-height:8px;}}
    '''


class StudentHub(QWidget):
    def __init__(self,studio):
        super().__init__(studio);self.studio=studio;self.data=curriculum()
        self.material=study_guide(self.data)
        from .student_inverter import inventory, expand
        profiles,self.pdk_errors=inventory(studio.pdk_registry,studio.project['pdk'])
        self.inverter_profiles={p['token']:p for p in profiles}
        self.data,self.material=expand(self.data,self.material,profiles)
        self.portfolio=Portfolio(studio.data_dir/'student-hub');self.path_id='foundations'
        self.setWindowTitle('Student Hub · IC Design Studio');self.resize(1180,780)
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
        menu=QMenu(self.more);self.more_menu=menu;self.more.setMenu(menu)
        for title,fn in [('Continue learning',self.continue_learning),('Feature map',lambda:studio.open_editor_doc('STUDENT_HUB.md')),('Engine setup…',self.setup),
                         ('Export learning record…',self.export),('Export portfolio report…',lambda:self.export(report=True)),
                         ('Locate lesson project…',self.locate),('Reload progress',self.reload_progress)]:
            menu.addAction(title,lambda checked=False,fn=fn:self.call(fn))
        sizes=menu.addMenu('Text size');self.text_size_menu=sizes
        for scale in (100,125,150,200):sizes.addAction(f'{scale}%',lambda checked=False,scale=scale:self.set_text_scale(scale))
        head.addWidget(self.more);root.addLayout(head)
        self.total=label('','muted');root.addWidget(self.total)
        root.addWidget(label('Learn the idea → repair a design → check the evidence → explain your decisions.','muted'))
        self.path_picker=QComboBox();self.path_picker.setAccessibleName('Learning path');root.addWidget(self.path_picker)
        self.process_panel=QWidget();pv=QVBoxLayout(self.process_panel);pv.setContentsMargins(0,0,0,0)
        pr=QHBoxLayout();pv.addLayout(pr);pr.addWidget(label('Inverter process'))
        self.process_picker=QComboBox();self.process_picker.setAccessibleName('Inverter PDK revision');pr.addWidget(self.process_picker,1)
        self.process_picker.setMinimumContentsLength(8);self.process_picker.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        for item in profiles:self.process_picker.addItem(item['name'],item['token'])
        saved=studio.settings.value('student/inverterProfile','');index=self.process_picker.findData(saved)
        if index>=0:self.process_picker.setCurrentIndex(index)
        actions=QHBoxLayout();pv.addLayout(actions);actions.addWidget(button('PDK setup',studio.pdk_manager))
        actions.addWidget(button('Set up physical tools',studio.physical_setup))
        actions.addWidget(button('Reload PDKs',lambda:self.call(self.reload_pdks)));actions.addStretch()
        self.process_status=label('','muted');pv.addWidget(self.process_status);root.addWidget(self.process_panel)
        self.process_picker.currentIndexChanged.connect(self.process_changed)
        self.path_list=QListWidget();self.path_list.setAccessibleName('Learning paths');self.path_list.setMinimumWidth(175)
        self.path_list.setMaximumWidth(250);self.path_list.setWordWrap(True)
        self.path_titles={p['id']:p['title'] for p in self.data['paths']}
        self.path_titles['capstone']='Advanced project'
        for key,title in self.path_titles.items():
            item=QListWidgetItem(title);item.setData(Qt.UserRole,key);self.path_list.addItem(item)
            self.path_picker.addItem(title,key)
        self.path_list.currentRowChanged.connect(lambda i:self.choose_path(self.path_list.item(i).data(Qt.UserRole)) if i>=0 else None)
        self.path_picker.currentIndexChanged.connect(lambda i:self.choose_path(self.path_picker.itemData(i)))
        panes=QHBoxLayout();root.addLayout(panes,1);panes.addWidget(self.path_list)
        self.split=QSplitter();self.split.setChildrenCollapsible(False);panes.addWidget(self.split,1)
        left=QWidget();lv=QVBoxLayout(left);lv.setContentsMargins(0,0,0,0);self.split.addWidget(left)
        self.heading=label('','subtitle');lv.addWidget(self.heading)
        self.search=QLineEdit();self.search.setPlaceholderText('Search all lessons…');self.search.setAccessibleName('Search all learning paths');self.search.textChanged.connect(self.fill)
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
        self.guide.arrange_actions()
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
        self.path_id=key
        if self.search.text():self.search.clear()
        else:self.fill()

    def process_changed(self,*_):
        self.studio.settings.setValue('student/inverterProfile',self.process_picker.currentData())
        self.fill()

    def reload_pdks(self):
        from .student_inverter import inventory, expand
        self.guide.save_note();selected=self.process_picker.currentData()
        profiles,self.pdk_errors=inventory(self.studio.pdk_registry,self.studio.project['pdk'])
        self.inverter_profiles={p['token']:p for p in profiles}
        self.data=curriculum();self.material=study_guide(self.data)
        self.data,self.material=expand(self.data,self.material,profiles)
        self.by_id={l['id']:l for l in self.data['lessons']}
        self.process_picker.blockSignals(True);self.process_picker.clear()
        for p in profiles:self.process_picker.addItem(p['name'],p['token'])
        self.process_picker.setCurrentIndex(max(0,self.process_picker.findData(selected)));self.process_picker.blockSignals(False)
        self.fill()

    def selected(self):
        item=self.lessons.currentItem();return self.by_id.get(item.data(Qt.UserRole)) if item else None

    def fill(self,*_):
        previous=self.selected();key=previous['id'] if previous else None;state=self.portfolio.state
        from .student_inverter import readiness
        self.process_panel.setVisible(self.path_id=='inverter')
        item=self.inverter_profiles.get(self.process_picker.currentData())
        self.process_status.setText((readiness(item) if item else 'Register a PDK to start.')+
                                   ('\n'+ '\n'.join(self.pdk_errors) if self.pdk_errors else ''))
        self.lessons.blockSignals(True);self.lessons.clear()
        available=[l for l in self.data['lessons'] if not l.get('inverter_profile') or self.inverter_profiles[l['inverter_profile']]['ready']]
        selected_available=[l for l in available if not l.get('inverter_profile') or l['inverter_profile']==self.process_picker.currentData()]
        summary=f'{sum(complete(state,l) for l in selected_available)} of {len(selected_available)} lessons complete · selected inverter PDK'
        if len(available)!=len(selected_available):
            summary+=f'\n{sum(complete(state,l) for l in available)} of {len(available)} across all available PDK revisions'
        self.total.setText(summary)
        self.total.setToolTip('The learning-path counts use the selected inverter PDK. Inverter progress is separate for each revision; the overall count includes every available revision.')
        self.path_list.blockSignals(True);self.path_picker.blockSignals(True)
        for i in range(self.path_list.count()):
            item=self.path_list.item(i);path_key=item.data(Qt.UserRole)
            ls=[l for l in self.data['lessons'] if l['path']==path_key and (path_key!='inverter' or l['inverter_profile']==self.process_picker.currentData())];n=sum(complete(state,l) for l in ls)
            title=self.path_titles[path_key]
            item.setText(title+f'\n{n} of {len(ls)} complete');self.path_picker.setItemText(i,title+f' · {n}/{len(ls)}')
            if path_key==self.path_id:self.path_list.setCurrentRow(i);self.path_picker.setCurrentIndex(i)
        self.path_list.blockSignals(False);self.path_picker.blockSignals(False)
        if self.path_id=='capstone':self.heading.setText(self.data['capstone']['subtitle'])
        else:self.heading.setText(next(p['subtitle'] for p in self.data['paths'] if p['id']==self.path_id))
        words=self.search.text().casefold().split()
        for l in self.data['lessons']:
            path_title=self.path_titles[l['path']]
            if words:
                search_text=' '.join([l['title'],l['summary'],path_title,*l['skills']]).casefold()
                if not all(word in search_text for word in words):continue
            elif l['path']!=self.path_id:continue
            if l['path']=='inverter' and l['inverter_profile']!=self.process_picker.currentData():continue
            count=len(earned(state,l));missing=missing_prerequisites(state,l,self.data)
            status='Completed' if complete(state,l) else 'Prerequisites needed' if missing else 'In progress' if count else 'Ready to start'
            title=f'{l["title"]}\n{path_title}' if words else l['title']
            item=QListWidgetItem(f'{title}\n{status} · {count}/{len(l["steps"])} steps · {l["minutes"]} min')
            item.setToolTip(item.text())
            item.setData(Qt.UserRole,l['id']);self.lessons.addItem(item)
            if key==l['id']:self.lessons.setCurrentItem(item)
        if words:
            matches=self.lessons.count()
            self.heading.setText(f'{matches} matching '+('lesson' if matches==1 else 'lessons'))
        if self.lessons.currentRow()<0:self.lessons.setCurrentRow(0)
        self.lessons.blockSignals(False);self.detail()

    def detail(self,*_):
        l=self.selected();self.start.setEnabled(bool(l))
        self.progress.setVisible(bool(l))
        if not l:
            self.details.setPlainText('No matching lessons. Try another topic or clear the search to return to your learning path.')
            self.progress.setValue(0);self.progress_text.setText('');self.start.setText('Start lesson');return
        state=self.portfolio.state;missing=missing_prerequisites(state,l,self.data);done=earned(state,l)
        esc=html.escape
        direct=[k for k in l['requires'] if k in missing] or missing[:1]
        pre='<br>'.join(f'<a href="{k}">{esc(self.by_id[k]["path"].title()+" · "+self.by_id[k]["title"])}</a>' for k in direct)
        rows=''.join(f'<li><b>{esc(s["title"])}</b> · {"Earned" if s["id"] in done else {"quiz":"Knowledge check","check":"Workspace check","reflection":"Written reflection"}[s["kind"]]}</li>' for s in l['steps'])
        cap='<p>This milestone continues the same sensor project. Earlier repairs are preserved.</p>' if l['path']=='capstone' else ''
        teaching=self.material['lessons'][l['id']]
        self.details.setHtml(f'<h2>{esc(l["title"])}</h2><p>{esc(l["summary"])}</p>{cap}<p><b>Skills</b><br>{esc(" · ".join(l["skills"]))}</p>'+
            overview_html(teaching)+
            (f'<p><b>Complete first</b><br>{pre}</p><p>{len(missing)} prerequisite lesson(s) remaining. You can practice now; earn progression credit after the prerequisites.</p>' if missing else '<p>Ready for guided work in the real editor.</p>')+
            f'<ol>{rows}</ol><p>Expected time: {l["minutes"]} minutes. Earlier earned steps remain a record of the design that passed at that time.</p>')
        self.progress.setRange(0,len(l['steps']));self.progress.setValue(len(done));self.progress.setFormat('%v of %m steps earned')
        self.progress_text.setText(f'{len(done)} of {len(l["steps"])} steps complete')
        self.start.setText('Practice lesson' if missing else 'Review lesson' if complete(state,l) else 'Resume lesson' if self.portfolio.workspace(l) else 'Start lesson')
        if l.get('inverter_profile') and not self.inverter_profiles[l['inverter_profile']]['ready']:
            self.start.setEnabled(False);self.start.setText('Set up this PDK to start')
            self.details.setHtml(self.details.toHtml()+notes_html(teaching))

    def select_lesson(self,key):
        if key not in self.by_id:return
        if self.by_id[key].get('inverter_profile'):
            self.process_picker.blockSignals(True)
            self.process_picker.setCurrentIndex(self.process_picker.findData(self.by_id[key]['inverter_profile']))
            self.process_picker.blockSignals(False)
        self.path_id=self.by_id[key]['path'];self.search.clear();self.fill()
        for i in range(self.lessons.count()):
            if self.lessons.item(i).data(Qt.UserRole)==key:self.lessons.setCurrentRow(i);break

    def continue_learning(self):
        data=self.data
        if self.path_id=='inverter':data={**data,'lessons':[l for l in data['lessons'] if l.get('inverter_profile')==self.process_picker.currentData()]}
        else:data={**data,'lessons':[l for l in data['lessons'] if not l.get('inverter_profile') or self.inverter_profiles[l['inverter_profile']]['ready']]}
        lesson=next_lesson(self.portfolio.state,data)
        if lesson:self.select_lesson(lesson['id']);self.start_selected()
        else:self.status.setText('This process course is complete. Choose another PDK or continue with the other learning paths.' if self.path_id=='inverter' else
                                'All learning paths and the advanced project are complete. Revisit any lesson or export your portfolio report.')

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
                if l.get('inverter_profile'):
                    from .student_inverter import create as inverter
                    project=inverter(self.inverter_profiles[l['inverter_profile']])
                elif l.get('analog_project') and l['analog_project']!='bandgap':
                    from .student_analog import choose_technology
                    project=create(l['starter'], choose_technology(self.inverter_profiles, s.project['pdk']))
                else:project=create(l['starter'])
                path=self.portfolio.root/'projects'/(l['workspace']+'-'+uid()+'.icproj')
                path.parent.mkdir(parents=True,exist_ok=True);save_project(project,path);self.portfolio.attach(l,project,path)
            if s.set_project(project,path) is False:return
        s.show_design_workspace()
        self.guide.open_lesson(l);self.guide.show();self.guide.raise_()
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
        from .digital_tools import normalize_executable
        return {n:normalize_executable(self.studio.settings.value('student/tools/'+n,self.studio.settings.value('mixed_signal/'+n,self.studio.settings.value('engine/'+n,'')))) for n in ('ngspice','iverilog','vvp','magic','netgen')}

    def digital_selection(self):
        from .digital_tools import selection
        selected=selection(self.studio.settings)
        if selected['toolchain']=='custom':
            selected['tools'].update({n:v for n,v in self.tools().items() if n in ('iverilog','vvp') and v})
        return selected

    def setup(self, missing=()):
        from .digital_tools import normalize_executable
        old=getattr(self,'_engine_setup_dialog',None)
        if old and old.isVisible():
            old.raise_()
            if missing: old.paths[missing[0]].setFocus()
            return old
        dialog=QDialog(self);dialog.setWindowTitle('Student simulation engines');v=QVBoxLayout(dialog)
        v.addWidget(label('Foundations and Analog use the included teaching solver. Digital lessons use the Included or Custom selection in Digital tools. Mixed Signal and the advanced project require native local ngspice and Icarus (iverilog and vvp).'))
        from .digital_setup_ui import show as digital_setup
        v.addWidget(button('Digital tools setup…',lambda:digital_setup(self.studio)))
        v.addWidget(label('Choose native local executables for simulation, or leave them blank to search PATH. IHP lessons automatically use the included simulator and compiled models. Leave Magic and Netgen blank to use the included physical tools. Prepare them with Set up physical tools in the Hub. Custom paths must point to native executables.'))
        form=QFormLayout();v.addLayout(form);edits={}
        for name,value in self.tools().items():
            row=QHBoxLayout();edit=QLineEdit(value);edit.setPlaceholderText(name+' on PATH');edit.setAccessibleName(name+' executable');row.addWidget(edit);browse_button=QPushButton('Browse…');browse_button.setAccessibleName('Browse for '+name+' executable');browse_button.setAutoDefault(False);row.addWidget(browse_button)
            def browse(_=False,edit=edit,name=name):
                path,_=QFileDialog.getOpenFileName(dialog,'Select '+name)
                if path:edit.setText(path)
            browse_button.clicked.connect(browse);form.addRow(name,row);edits[name]=edit
        native_status=label();native_status.setAccessibleName('Student native engine prerequisite status');v.addWidget(native_status)
        def check_native():
            from .mixed_signal import resolve_tools, NativeEngineSetupError
            try:resolve_tools({name:edit.text() for name,edit in edits.items()},'Student Hub → Engine setup')
            except NativeEngineSetupError as exc:native_status.setText(str(exc));return False
            native_status.setText('Native mixed-signal executables found. Run a lesson to check their behavior.');return True
        v.addWidget(button('Check native mixed-signal engines',check_native))
        v.addWidget(button('Native engine installation guide',lambda:self.studio.open_editor_doc('MIXED_SIGNAL_SAR.md')))
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);v.addWidget(buttons)
        def save():
            for name,edit in edits.items():self.studio.settings.setValue('student/tools/'+name,normalize_executable(edit.text()))
            dialog.accept()
        buttons.accepted.connect(save);buttons.rejected.connect(dialog.reject)
        dialog.paths=edits;dialog.native_status=native_status;dialog.check_native=check_native
        self._engine_setup_dialog=dialog;check_native();dialog.show()
        if missing:edits[missing[0]].setFocus()
        return dialog

    def export(self,report=False):
        self.guide.save_note()
        # Export the open lesson's current work, including pending editor fields.
        record=self.portfolio.workspace(self.guide.lesson) if self.guide.lesson else None
        if record and record['project_id']==self.studio.project['id']:
            if not self.guide.save_work():return
        if report:
            path,_=QFileDialog.getSaveFileName(self,'Export portfolio report','student-portfolio.html','Portfolio report (*.html)')
            if path:
                export_portfolio(self.portfolio,path,self.data,self.material)
                feedback(self.status,'Portfolio report exported. Open the HTML file in a browser to read or print it.')
        else:
            path,_=QFileDialog.getSaveFileName(self,'Export learning record','student-portfolio.json','Learning record (*.json)')
            if path:self.portfolio.export(path,self.data);feedback(self.status,'Learning record exported, including saved lesson projects and evidence references.')

    def reject(self):
        try:self.guide.save_note()
        except Exception as exc:feedback(self.status,str(exc),True);return
        self.studio.show_design_workspace()

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
        self.lesson_tabs=QTabWidget();self.lesson_tabs.setAccessibleName('Lesson teaching and task');v.addWidget(self.lesson_tabs,1)
        self.design_notes=QTextBrowser();self.design_notes.setAccessibleName('Concept, worked example and interview preparation')
        self.instructions=QTextBrowser();self.instructions.setAccessibleName('Step instructions')
        self.lesson_tabs.addTab(self.design_notes,'Learn');self.lesson_tabs.addTab(self.instructions,'Do this step')
        self.lesson_tabs.setMinimumHeight(220)
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
        self.inverter_actions=QWidget();iv=QGridLayout(self.inverter_actions);iv.setContentsMargins(0,0,0,0);v.addWidget(self.inverter_actions)
        self.inverter_controls_layout=iv;self.inverter_buttons=[]
        for i,(title,fn) in enumerate([('Open inverter',self.open_inverter),('Build layout',self.build_inverter),
                                     ('Add DRC fault',lambda:self.inverter_edit('drc')),('Add LVS fault',lambda:self.inverter_edit('lvs')),
                                     ('Repair lesson fault',lambda:self.inverter_edit('repair'))]):
            control=button(title,lambda fn=fn:self.call(fn));iv.addWidget(control,i//2,i%2);self.inverter_buttons.append(control)
        self.inverter_actions.hide()
        self.analog_action=button('Edit testbench…',lambda:self.call(self.analog_project_action))
        self.analog_action.hide();v.addWidget(self.analog_action)
        self.qualify=button('Run four acceptance cases',lambda:self.call(self.qualification));v.addWidget(self.qualify)
        self.steps.currentIndexChanged.connect(self.step_changed)
        self.note_timer=QTimer(self);self.note_timer.setSingleShot(True);self.note_timer.setInterval(600)
        self.note_timer.timeout.connect(lambda:self.call(self.save_note));self.notes.textChanged.connect(self.note_changed)
        self.active_step=None;self.note_dirty=False
        self.studio.run_manager.completed.connect(self.finished)
        self.studio.run_manager.changed.connect(self.update_run_state)
        self.control_columns=None
        self.scroll.viewport().installEventFilter(self)

    def arrange_actions(self):
        # Font metrics vary by OS, fallback font and accessibility settings.
        # Reflow from actual control widths, not a particular zoom threshold.
        if not hasattr(self,'control_columns'):return
        width=self.scroll.viewport().width()-28
        buttons=list(self.controls.values())
        needed=sum(max(b.sizeHint().width() for b in buttons[col::2]) for col in (0,1))+self.controls_layout.horizontalSpacing()
        columns=2 if needed<=width else 1
        inv=self.inverter_buttons
        inv_columns=2 if sum(max(b.sizeHint().width() for b in inv[col::2]) for col in (0,1))+self.inverter_controls_layout.horizontalSpacing()<=width else 1
        while self.inverter_controls_layout.count():self.inverter_controls_layout.takeAt(0)
        for i,control in enumerate(inv):self.inverter_controls_layout.addWidget(control,i//inv_columns,i%inv_columns)
        if columns==self.control_columns:return
        self.control_columns=columns
        while self.controls_layout.count():self.controls_layout.takeAt(0)
        for i,control in enumerate(buttons):self.controls_layout.addWidget(control,i//columns,i%columns)

    def eventFilter(self,watched,event):
        if watched is self.scroll.viewport() and event.type()==QEvent.Resize:self.arrange_actions()
        return super().eventFilter(watched,event)

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
        self.design_notes.setHtml(notes_html(self.hub.material['lessons'][lesson['id']]))
        self.steps.blockSignals(True);self.steps.clear()
        done=earned(self.hub.portfolio.state,lesson)
        for i,step in enumerate(lesson['steps']):self.steps.addItem(f'{i+1}. '+step['title']+(' ✓' if step['id'] in done else ''))
        index=next((i for i,s in enumerate(lesson['steps']) if s['id'] not in done),len(lesson['steps'])-1)
        self.steps.setCurrentIndex(index);self.steps.blockSignals(False);self.step_changed(index)
        self.lesson_tabs.setCurrentIndex(0 if not done else 1)
        self.qualify.setVisible(lesson['id']=='c-qualify')
        self.inverter_actions.setVisible(lesson['path']=='inverter')
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
        self.lesson_tabs.setCurrentIndex(1)
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
        self.update_run_state()

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
        if 'device_metrics' in evidence:
            point=evidence['device_metrics']
            feedback(self.feedback,f'Checkpoint passed. ID = {point["id"]*1e6:.3g} µA; gm = {point["gm"]*1e6:.3g} µS; gm/ID = {point["gmid"]:.3g} V⁻¹; headroom = {point.get("headroom",0):.3g} V. Evidence saved.')
        elif 'bias_readings' in evidence:
            point=evidence['bias_readings']
            feedback(self.feedback,f'Iout {point["output_A"]*1e6:.2f} µA · ID/W {point["density_uA_per_um"]:.3f} µA/µm · headroom {point["headroom_V"]*1000:.0f} mV. Saved.')
        elif 'bias_comparison' in evidence:
            a,b=(evidence['bias_comparison'][name] for name in ('simple','cascode'))
            feedback(self.feedback,f'Output resistance {a["resistance_ohm"]/1e6:.2f} → {b["resistance_ohm"]/1e6:.2f} MΩ. 5% flatness knee {a["compliance_V"]:.2f} → {b["compliance_V"]:.2f} V. Estimated saturation floor {a["saturation_floor_V"]:.2f} → {b["saturation_floor_V"]:.2f} V. Saved.')
        elif 'bias_corners' in evidence:
            points=evidence['bias_corners']
            feedback(self.feedback,f'{sum(p["passes"] for p in points)} of {len(points)} cases meet the operating target. All measured cases saved.')
        elif 'bandgap_runs' in evidence:
            measured=evidence['bandgap_runs']
            span=measured['temperature_span_V']
            detail=f' Temperature span {span*1000:.1f} mV.' if span is not None else ''
            feedback(self.feedback,f'{measured["cases"]} cases passed.{detail} Measurements saved.')
        elif 'analog_runs' in evidence:
            point=evidence['analog_runs'][0].get('gmid')
            if point:
                feedback(self.feedback,f'M2 measured {point["gm_S"]*1e6:.3g} µS gm, {point["current_A"]*1e6:.3g} µA ID and {point["gm_over_id"]:.3g} V⁻¹ gm/ID. Evidence saved.')
            else:
                feedback(self.feedback,f'All {len(evidence["analog_runs"])} testbenches meet the targets. Measurements saved to your learning record.')
        elif 'lesson_measurements' in evidence:
            measured=evidence['lesson_measurements']
            if 'after_Hz' in measured:
                feedback(self.feedback,f'Bandwidth {measured["before_Hz"]/1e9:.2f} → {measured["after_Hz"]/1e9:.2f} GHz. Route resistance {measured["route_ohm"]:.1f} Ω. Saved.')
            elif 'f0_Hz' in measured:
                feedback(self.feedback,f'f₀ = {measured["f0_Hz"]/1e3:.3g} kHz · Q = {measured["q"]:.3g}. Measurements saved.')
            else:
                feedback(self.feedback,'All four slopes and center responses checked. Measurements saved.')
        elif 'measurements' in evidence:
            feedback(self.feedback,'Checkpoint passed. '+ '; '.join(f'{key}: {value}' for key,value in evidence['measurements'].items())+'. Generic geometry evidence saved.')
        elif 'inverter_measurements' in evidence:
            parts=[]
            for key,value in evidence['inverter_measurements'].items():
                parts.append(f'{key} = {value*1e12:.4g} ps' if key in ('tPHL','tPLH') else
                             f'{key} = {value:g}' if key=='checked_cycles' else f'{key} = {value:.4g} V')
            feedback(self.feedback,'Checkpoint passed. '+ '; '.join(parts)+'. Process-model evidence saved.')
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
        self.require_project();s=self.studio
        if not s.leave_digital_workspace():return
        show_layout=self.lesson['starter'].startswith('layout')
        if self.lesson['starter']=='layout-decisions':
            from .student_layout_decisions import focus
            s.cid=focus(s.project,self.active_step['id'])
        elif self.lesson['starter'] in ('ahuja-study','miller-study'):
            s.cid=next(c['id'] for c in s.project['cells'] if c['name']=='two_stage_opamp')
        elif self.lesson.get('analog_project'):
            from .student_analog import focus_cell
            step=self.active_step['id']
            s.cid=focus_cell(s.project,self.lesson['analog_project'],step)
            show_layout=step in ('layout','bias-layout','post-layout')
        else:
            s.cid=s.project.get('mixed_signal',{}).get('analog_cell',s.project['top'])
        s.mode_combo.setCurrentIndex(1 if show_layout else 0);s.refresh(True)
        self.show();self.raise_()

    def analog_project_action(self):
        self.flush();self.require_idle();s=self.studio
        if self.lesson.get('analog_project')=='bandgap' and self.active_step['id'] in ('accuracy','startup'):
            from .student_bandgap_lab import core_cell
            if not s.leave_digital_workspace():return
            s.cid=core_cell(s.project)['id'];s.mode_combo.setCurrentIndex(0);s.refresh(True)
            self.show();self.raise_()
            return
        if self.lesson.get('analog_project')=='bandgap' and self.active_step['id']=='layout':
            from .student_bandgap_lab import core_cell
            from .student_bandgap_layout import generate
            replace=bool(core_cell(s.project)['shapes'])
            if replace and QMessageBox.question(self,'Regenerate bandgap layout?',
                'Regeneration replaces the current geometry. You can undo it in the editor.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Yes:
                return
            s.commit(lambda p:generate(p,replace=replace),'Generate GF180 bandgap layout')
            self.workspace()
            self.update_run_state()
            feedback(self.feedback,'Layout generated. Inspect the device rows, supply buses, and vias.')
            return
        if self.lesson.get('bandgap'):
            from .student_bandgap_ui import BandgapDialog
            self.frequency_dialog=BandgapDialog(s,self.lesson['bandgap'])
            self.frequency_dialog.show()
            return
        if self.lesson['starter'] in ('ahuja-study','miller-study'):
            from .student_frequency_ui import AhujaDialog, MillerDialog
            dialog=MillerDialog if self.lesson['starter']=='miller-study' else AhujaDialog
            self.frequency_dialog=dialog(s)
            self.frequency_dialog.show()
            return
        from .student_analog import _get_bench, run_names
        kind=self.lesson['analog_project'];step=self.active_step['id']
        if step=='layout':
            self.workspace()
            return s.two_stage_layout_dialog()
        if step=='bias-layout':
            self.workspace()
            return s.analog_bank_dialog()
        if step=='post-layout':
            return s.migrate_pdk_dialog()
        names=run_names(kind,step)
        name=('tia_ac' if kind=='tia' else 'opamp_ac') if step=='fixture' else names[0]
        key=_get_bench(s.project,name)['id']
        s.open_testbenches()
        s.testbench_combo.setCurrentIndex(s.testbench_combo.findData(key))
        return s.edit_testbench()

    def open_inverter(self):
        from .student_inverter import context
        self.flush();_,cell=context(self.studio.project,self.lesson)
        if not self.studio.leave_digital_workspace():return
        self.studio.cid=cell['id'];self.studio.mode_combo.setCurrentIndex(1 if self.lesson['inverter_stage'] in ('layout','drc','lvs','handoff') else 0)
        self.studio.refresh(True)

    def build_inverter(self):
        from .student_inverter import build_layout
        self.flush();self.require_idle();self.studio.commit(build_layout,'Build lesson inverter layout');self.open_inverter()
        feedback(self.feedback,'Process geometry created. Inspect the ports, then run DRC and LVS in the following lessons.')

    def inverter_edit(self,kind):
        from .student_inverter import fault,repair
        self.flush();self.require_idle()
        self.studio.commit(repair if kind=='repair' else lambda p:fault(p,kind),'Repair lesson fault' if kind=='repair' else 'Add '+kind.upper()+' practice fault')
        self.open_inverter();feedback(self.feedback,'Lesson fault repaired. Run again to verify.' if kind=='repair' else 'Practice fault added. Run the matching DRC or LVS lesson and inspect its report.')

    def rtl(self):
        self.require_project();from .digital_design import config
        s=self.studio;cid=s.project.get('mixed_signal',{}).get('digital_cell',s.project['top'])
        if not config(s.project,cid):raise ValueError('This lesson has no RTL cell.')
        s.cid=cid;s.digital_window().workspace.switch_cell(cid);self.show();self.raise_()

    def run(self):
        self.flush();self.require_idle();s=self.studio
        if self.lesson['starter']=='layout-decisions':
            from .student_layout_decisions import prepare
            job=prepare(s.project,self.active_step['id'])
        elif self.lesson.get('analog_project'):
            from .student_analog import prepare
            jobs=prepare(s.project,self.lesson['analog_project'],self.active_step['id'],self.hub.tools())
            for job in jobs:job['student_lesson']=self.lesson['id']
            names=[job['student_analog']['bench'] for job in jobs]
            s.run_manager.enqueue_many(jobs,s.jobs_dir,['Student · '+name for name in names])
            feedback(self.feedback,'Queued '+', '.join(names)+'. Check this step when the runs finish.')
            return
        elif self.lesson.get('inverter_profile'):
            from .student_inverter import prepare
            job=prepare(s.project,self.lesson,self.hub.tools())
        else:
            from .digital_design import config
            from .mixed_signal import NativeEngineSetupError
            if not s.project.get('mixed_signal') and config(s.project,s.project['top']):
                from .digital_setup_ui import ensure_lesson
                if not ensure_lesson(self,self.run):return
                selected=self.hub.digital_selection()
                job=prepare_lesson(s.project,selected['tools'],toolchain=selected['toolchain'])
            else:
                try:job=prepare_lesson(s.project,self.hub.tools())
                except NativeEngineSetupError as exc:
                    self.hub.setup(exc.missing);feedback(self.feedback,str(exc),True);return
        job['student_lesson']=self.lesson['id'];s.run_manager.enqueue(job,s.jobs_dir,'Student · '+self.lesson['title'])
        feedback(self.feedback,'Lesson run queued. Checks apply to the captured design; edits require a new run.')

    def qualification(self):
        from .mixed_signal import NativeEngineSetupError
        self.flush();self.require_idle()
        try:jobs=campaign_jobs(self.studio.project,self.hub.tools())
        except NativeEngineSetupError as exc:
            self.hub.setup(exc.missing);feedback(self.feedback,str(exc),True);return
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
        is_layout=self.lesson['starter'].startswith('layout')
        can_run=bound and not active and not is_layout
        starter=self.lesson['starter']
        kind=self.lesson.get('analog_project')
        self.analog_action.hide()
        bandgap=self.lesson.get('bandgap')
        self.controls['Open RTL'].setVisible(not kind and not bandgap and starter not in ('layout-decisions','lc-bode','ahuja-study','miller-study'))
        self.controls['Run lesson'].setText('Run lesson')
        if kind and self.active_step:
            from .student_analog import run_names
            step=self.active_step['id'];names=run_names(kind,step)
            can_run=can_run and bool(names)
            self.controls['Run lesson'].setVisible(bool(names))
            self.controls['Run lesson'].setText('Run post-layout checks' if step=='post-layout' else 'Run testbenches')
            if kind=='bias' and step=='corners':
                self.controls['Run lesson'].setText('Run nine PVT cases')
            from .process_adapters import capabilities
            needs_full_pdk=step=='post-layout' and not capabilities(self.studio.project['pdk'])['external_verification']
            if kind=='bandgap':
                names={'accuracy':'Run temperature sweep','startup':'Run startup cases','post-layout':'Run extracted comparison'}
                if step in names:self.controls['Run lesson'].setText(names[step])
                if step=='layout':
                    from .student_bandgap_lab import core_cell
                    existing=bound and core_cell(self.studio.project)['shapes']
                    self.analog_action.setText('Regenerate layout…' if existing else 'Generate layout')
                elif step in ('accuracy','startup'):self.analog_action.setText('Open bandgap circuit')
                else:self.analog_action.setText('Open temperature model…')
                self.analog_action.setEnabled(bound and not active);self.analog_action.show()
            elif step in ('fixture','bias','layout','bias-layout','schematic') or needs_full_pdk:
                self.analog_action.setText({'layout':'Generate core layout…','bias-layout':'Generate bias mirror layout…',
                                            'post-layout':'Migrate PDK revision…'}.get(step,'Edit testbench…'))
                self.analog_action.setEnabled(bound and not active);self.analog_action.show()
        elif starter=='layout-decisions' and self.active_step:
            from .student_layout_decisions import EXTRACTION_STEPS
            run_step=self.active_step['id'] in EXTRACTION_STEPS
            can_run=bound and not active and run_step
            self.controls['Run lesson'].setVisible(run_step)
            self.controls['Run lesson'].setText('Compare route RC')
        elif starter in ('ahuja-study','miller-study') or bandgap:
            can_run=False
            self.controls['Run lesson'].hide()
            self.analog_action.setText('Open temperature study…' if bandgap else 'Open loop comparison…')
            self.analog_action.setEnabled(bound)
            self.analog_action.show()
        else:
            self.controls['Run lesson'].show()
            if starter=='lc-bode':
                self.controls['Run lesson'].setText('Run AC sweep')
        self.controls['Run lesson'].setEnabled(can_run);self.qualify.setEnabled(can_run)
        self.controls['Cancel lesson runs'].setEnabled(bool(active));self.controls['Cancel lesson runs'].setVisible(bool(active))
        result_rows=[r for r in rows if r.get('result') and r['job'].get('student_lesson')==self.lesson['id']]
        if kind and self.active_step:
            result_rows=[r for r in result_rows if r['job'].get('student_analog',{}).get('stage')==self.active_step['id']]
        self.controls['Results'].setEnabled(bound and bool(result_rows))
        for name in ('Open workspace','Save work'):self.controls[name].setEnabled(bound)
        self.controls['Open RTL'].setEnabled(bound and self.lesson['path'] in ('digital','mixed','capstone'))
        self.check_button.setEnabled(bound)
        self.run_progress.setVisible(bool(active))
        if active:
            self.run_progress.setRange(0,100);self.run_progress.setValue(round(sum(r.get('progress',0) for r in active)/len(active)))
            self.run_status.setText(' · '.join(f'{sum(r["state"]==state for r in active)} {state.lower()}' for state in ('Running','Queued','Stopping') if any(r['state']==state for r in active)))
        elif not bound:self.run_status.setText('Resume this lesson from Student Hub to use its workspace.')
        elif rows:self.run_status.setText('Latest run: '+rows[-1]['state'])
        elif kind or bandgap or starter in ('layout-decisions','ahuja-study','miller-study'):self.run_status.setText('Ready to run.' if can_run else '')
        else:self.run_status.setText('Ready to run.' if not is_layout else 'This lesson checks the layout without simulation.')

    def finished(self,row,result):
        if self.lesson and row in self.lesson_rows() and row['job'].get('student_lesson')==self.lesson['id']:
            feedback(self.feedback,row['name']+' · '+row['state']+'. '+('Open Results or check this step.' if result else row.get('log','')[-350:]),row['state']=='Failed')
        self.update_run_state()

    def results(self):
        self.require_project();s=self.studio
        rows=[r for r in self.lesson_rows() if r.get('result') and r['job'].get('student_lesson')==self.lesson['id']]
        if not rows:raise ValueError('Run this lesson first.')
        latest=rows[-1]
        if self.lesson['starter']=='lc-bode':
            from .student_frequency_ui import FilterDialog
            self.frequency_dialog=FilterDialog(s,latest['job']['project'],latest['result'])
            self.frequency_dialog.show()
            return
        if self.lesson.get('analog_project'):
            from .analog_run_ui import RunInspector
            step=self.active_step['id']
            by_bench={r['job']['student_analog']['bench']:r for r in rows if r['job']['student_analog']['stage']==step}
            if not by_bench:raise ValueError('Run this step’s testbenches first.')
            if self.lesson['analog_project']=='bias' and step=='corners':
                from .student_bias_ui import BiasCornersDialog
                saved=by_bench['cascode_bias']
                self.bias_inspector=BiasCornersDialog(s,saved['job']['project'],saved['result'])
                self.bias_inspector.show();return
            if self.lesson['analog_project']=='bandgap':
                from .student_bandgap_lab_ui import BandgapLabResults
                self.bias_inspector=BandgapLabResults(s,next(iter(by_bench.values()))['result'])
                self.bias_inspector.show();return
            if len(by_bench)>1:
                selected,ok=QInputDialog.getItem(self,'Testbench results','Open saved testbench',list(by_bench),0,False)
                if not ok:return
            else:selected=next(iter(by_bench))
            self.bias_inspector=RunInspector(s,by_bench[selected]);self.bias_inspector.show()
            return
        if any(step.get('rule',{}).get('type')=='device_metrics' for step in self.lesson['steps']):
            from .analog_run_ui import RunInspector
            self.bias_inspector=RunInspector(s,latest);self.bias_inspector.show();return
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
        if result.get('rc_comparison') and self.lesson['starter']=='layout-decisions':
            s.open_engineering_tab(s.rc_tab)
        if result.get('silicon_report'):s.open_silicon()

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
        self.save_note();show(self.studio);self.hub.select_lesson(self.lesson['id']);self.hub.start.setFocus()

    def closeEvent(self,event):
        try:self.save_note()
        except Exception as exc:self.feedback.setText(str(exc));event.ignore();return
        super().closeEvent(event)


def show(studio):
    studio.app_workspaces.setCurrentIndex(1)
    return studio.app_workspaces.hub()


def install(studio):
    studio.action(studio.task_menus['View'],'Student Hub',lambda:show(studio))
    studio.action(studio.task_menus['Help'],'Student learning paths',lambda:show(studio))
