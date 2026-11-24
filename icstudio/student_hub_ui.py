"""A native learning hub and a persistent guide beside the circuit/RTL editors."""
import html
from collections import Counter
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QSize, QSignalBlocker
from PySide6.QtGui import QActionGroup, QIcon, QKeySequence, QShortcut, QFontDatabase
from PySide6.QtWidgets import (QDialog,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QButtonGroup,QSizePolicy,
    QListWidget,QListWidgetItem,QListView,QTextBrowser,QPlainTextEdit,QComboBox,QProgressBar,QDockWidget,
    QLineEdit,QFileDialog,QFormLayout,QDialogButtonBox,QSplitter,QMenu,QScrollArea,QMessageBox,QTabWidget,QInputDialog,
    QBoxLayout)

from .model import digest, load_project, save_project, uid
from .student_hub import (DIFFICULTIES,Portfolio,curriculum,earned,complete,missing_prerequisites,next_lesson,
                         prepare_lesson,campaign_jobs,evaluate)
from .ui_style import icon, palette, stylesheet
from .student_learning import (study_guide, notes_html, overview_html, export_portfolio,
                               answer_choices, challenge_text, evidence_label, lesson_run_step, preparation_html, question_text,
                               review_html, task_html, solution_html)
from .student_world_map import LessonTrail, WorldMap


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


def resisty_button(callback, subject):
    widget = button('Ask Resisty…', callback, 'secondary')
    widget.setIcon(icon('resisty'))
    widget.setIconSize(QSize(24, 24))
    widget.setAccessibleName('Ask Resisty, the AI helper, about ' + subject)
    return widget


def feedback(widget,text,error=False,*,role='muted'):
    widget.setText(text);widget.setProperty('role','error' if error else role)
    widget.style().unpolish(widget);widget.style().polish(widget)
    widget.setAccessibleName(text)


def student_style(dark,scale):
    t=palette(dark);size=round(14*scale/100)
    family=QFontDatabase.systemFont(QFontDatabase.GeneralFont).family().replace('"','')
    return stylesheet(dark)+f'''
    QWidget {{font-family:"{family}";font-size:{size}px;}}
    QLabel[role="section"], QLabel[role="subtitle"] {{font-size:{size}px;}}
    QLabel[role="title"] {{font-size:{round(25*scale/100)}px;font-weight:600;}}
    QLabel[role="question"] {{font-size:{round(19*scale/100)}px;font-weight:600;}}
    QLabel[role="correct"] {{color:{'#a0e8d2' if dark else '#11644d'};}}
    QTextBrowser {{background:{t['panel']};color:{t['text']};border:0;padding:4px;}}
    QPushButton[role="primary"]:focus {{border:2px solid {t['text']};}}
    QTextBrowser:focus, QPlainTextEdit:focus, QLineEdit:focus, QListWidget:focus, QComboBox:focus {{border:2px solid {t['accent']};}}
    QLineEdit {{min-height:{round(22*scale/100)}px;}}
    QListWidget::item {{padding:10px 8px;}}
    QPushButton[role="answer"] {{background:{t['field']};border:1px solid {t['line']};padding:0;}}
    QPushButton[role="answer"]:hover {{background:{t['hover']};}}
    QPushButton[role="answer"]:checked {{background:{t['tint']};border-color:{t['accent']};}}
    QPushButton[role="answer"]:focus {{border:2px solid {t['accent']};}}
    QLabel[role="answerText"] {{background:transparent;}}
    QLabel[role="hintAdvice"]:focus {{outline:0;border:1px solid {t['accent']};}}
    QProgressBar {{max-height:8px;}}
    QWidget#studentViewModes {{background:{t['bg']};border:1px solid {t['line']};border-radius:10px;}}
    QPushButton[role="hubMode"] {{min-height:42px;min-width:60px;padding:0 14px;border:2px solid transparent;border-radius:7px;}}
    QPushButton[role="hubMode"]:checked {{background:{t['panel']};color:{t['text']};border-color:{t['line']};font-weight:600;}}
    QLabel[role="worldTitle"] {{font-size:{round(17*scale/100)}px;font-weight:600;}}
    QLabel[role="worldCount"] {{font-weight:600;}}
    QPushButton[role="worldCard"] {{border:2px solid {t['line']};border-radius:12px;padding:0;}}
    QPushButton[role="hubBack"] {{min-height:32px;}}
    QWidget[role="lessonRoute"] {{border-left:2px solid {t['line']};}}
    QPushButton[role="trailLesson"] {{background:{t['field']};border:2px solid {t['line']};border-radius:9px;padding:0;}}
    QPushButton[role="trailLesson"]:hover {{background:{t['hover']};}}
    QPushButton[role="trailLesson"]:checked {{background:{t['tint']};border-color:{t['accent']};}}
    QLabel[role="trailTitle"] {{font-weight:600;}}
    QLabel[role="trailMark"] {{color:{t['muted']};background:{t['bg']};border-radius:8px;min-width:29px;min-height:28px;font-weight:600;}}
    QLabel[role="trailMark"][done="true"] {{color:{'#a0e8d2' if dark else '#11644d'};}}
    QPushButton[role="hubMode"]:focus, QPushButton[role="worldCard"]:focus,
    QPushButton[role="trailLesson"]:focus, QPushButton[role="hubBack"]:focus {{border:2px solid {t['text']};}}
    '''


def quiz_selector(combo, steps):
    combo.setMinimumContentsLength(12)
    combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
    with QSignalBlocker(combo):
        combo.clear()
        for index, step in enumerate(steps, 1):
            combo.addItem(f'{index}. {step["title"]}', step['id'])
    combo.setVisible(len(steps) > 1)


LESSON_MODES = {'independent': 'Do It Yourself', 'guided': 'Step by Step'}


def learning_mode_picker():
    combo = QComboBox()
    combo.setAccessibleName('Learning mode')
    for key, caption in LESSON_MODES.items():
        combo.addItem(caption, key)
    combo.setCurrentIndex(combo.findData('guided'))
    caption = label('Learning mode')
    caption.setBuddy(combo)
    return caption, combo


class LessonSolution(QDialog):
    def __init__(self, studio):
        super().__init__(studio)
        self.resize(620, 445)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.steps = QComboBox()
        self.steps.setMinimumContentsLength(14)
        self.steps.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.steps.setAccessibleName('Checkpoint solution')
        form.addRow('Checkpoint', self.steps)
        layout.addLayout(form)
        self.body = QTextBrowser()
        self.body.setAccessibleName('Worked solution for the selected checkpoint')
        layout.addWidget(self.body, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)
        self.steps.currentIndexChanged.connect(self.render)

    def open_lesson(self, lesson, practice, notes, step=None):
        self.lesson, self.practice, self.notes = lesson, practice, notes
        self.setWindowTitle('Solution · '+lesson['title'])
        with QSignalBlocker(self.steps):
            self.steps.clear()
            for index, item in enumerate(lesson['steps'], 1):
                self.steps.addItem(f'{index}. {item["title"]}', item['id'])
            self.steps.setCurrentIndex(max(0, self.steps.findData((step or {}).get('id'))))
        self.render(self.steps.currentIndex())
        self.show()
        self.raise_()
        self.activateWindow()
        self.steps.setFocus()

    def render(self, index):
        if index >= 0:
            self.body.setHtml(solution_html(self.lesson['steps'][index], self.practice, self.notes))


class QuestionHints(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.rows = []
        for _ in range(4):
            question = label('', 'answerText')
            question.setAttribute(Qt.WA_TransparentForMouseEvents)
            reveal = QPushButton()
            reveal.setProperty('role', 'answer')
            reveal.setAutoDefault(False)
            reveal.setCheckable(True)
            reveal.setAccessibleDescription('Show or hide the answer')
            marker = label('▸', 'muted')
            marker.setAttribute(Qt.WA_TransparentForMouseEvents)
            button_layout = QHBoxLayout(reveal)
            button_layout.setContentsMargins(10, 8, 10, 8)
            button_layout.addWidget(marker, 0, Qt.AlignTop)
            button_layout.addWidget(question, 1)
            policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            policy.setHeightForWidth(True)
            reveal.setSizePolicy(policy)
            answer = label('', 'hintAdvice')
            answer.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
            answer.setFocusPolicy(Qt.TabFocus)
            answer.setContentsMargins(10, 2, 10, 6)
            for text in (question, answer):
                text_policy = text.sizePolicy()
                text_policy.setHorizontalPolicy(QSizePolicy.Ignored)
                text.setSizePolicy(text_policy)
            reveal.toggled.connect(answer.setVisible)
            reveal.toggled.connect(lambda expanded, marker=marker:marker.setText('▾' if expanded else '▸'))
            layout.addWidget(reveal)
            layout.addWidget(answer)
            self.rows.append((reveal, question, answer))
        self.set_entries(())

    def collapse(self):
        for reveal, _, answer in self.rows:
            reveal.setChecked(False)
            answer.hide()

    def set_entries(self, entries):
        self.collapse()
        for index, (reveal, question, answer) in enumerate(self.rows):
            prompt, advice = entries[index] if index < len(entries) else ('', '')
            question.setText(prompt)
            reveal.setAccessibleName(prompt)
            reveal.setVisible(bool(prompt))
            answer.setText(advice)


class PredictionPreview(QScrollArea):
    """Try a curriculum question before opening the lesson project."""
    def __init__(self, ask_ai):
        super().__init__()
        self.setWidgetResizable(True)
        self.setAccessibleName('Practice prediction')
        body = QWidget()
        self.setWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(12, 14, 12, 14)
        layout.setSpacing(10)
        self.questions = QComboBox()
        self.questions.setAccessibleName('Knowledge check question')
        layout.addWidget(self.questions)
        self.title = label('', 'muted')
        self.question = label('', 'question')
        layout.addWidget(self.title)
        layout.addWidget(self.question)
        self.hint_button = QPushButton('Hints')
        self.hint_button.setCheckable(True)
        self.hint_button.setAutoDefault(False)
        self.hint_button.setAccessibleDescription('Reveal or collapse student questions and advice')
        self.ask_button = resisty_button(lambda:ask_ai(self.lesson,self.step), 'this knowledge check')
        self.hints = QuestionHints()
        self.hint_button.toggled.connect(self.toggle_hints)
        from .analog_widgets import FlowActions
        actions = FlowActions()
        actions.addWidget(self.hint_button)
        actions.addWidget(self.ask_button)
        layout.addLayout(actions)
        layout.addWidget(self.hints)
        self.choices = QVBoxLayout()
        layout.addLayout(self.choices)
        self.answers = QButtonGroup(self)
        self.answers.idClicked.connect(self.answer)
        self.result = label()
        layout.addWidget(self.result)
        layout.addStretch()
        self.step = None
        self.lesson = None
        self.steps = []
        self.advice = {}
        self.practice = {}
        self.mode = 'guided'
        self.questions.currentIndexChanged.connect(self.select_question)
        self.hints.hide()

    def toggle_hints(self, visible):
        if not visible:
            self.hints.collapse()
        self.hints.setVisible(visible)

    def set_lesson(self, lesson, advice, practice):
        if lesson is self.lesson:
            return bool(self.steps)
        self.lesson = lesson
        self.advice = advice
        self.practice = practice
        self.steps = [step for step in (lesson or {}).get('steps', []) if step['kind'] == 'quiz']
        quiz_selector(self.questions, self.steps)
        self.select_question(self.questions.currentIndex())
        return bool(self.steps)

    def set_learning_mode(self, mode):
        self.mode = mode
        self.question.setText(question_text(self.step, self.practice, mode == 'guided') if self.step else '')

    def select_question(self, index):
        step = self.steps[index] if index >= 0 else None
        self.step = step
        self.hint_button.setChecked(False)
        self.hint_button.setVisible(step is not None)
        self.ask_button.setVisible(step is not None)
        self.hints.set_entries(self.advice.get(step['id'], ()) if step else ())
        for choice in self.answers.buttons():
            self.answers.removeButton(choice)
            self.choices.removeWidget(choice)
            choice.hide()
            choice.deleteLater()
        self.title.setText(step['title'] if step else '')
        self.set_learning_mode(self.mode)
        self.result.clear()
        if step is None:
            return
        for index, option in answer_choices(step,self.lesson):
            choice = QPushButton()
            choice.setAutoDefault(False)
            choice.setCheckable(True)
            choice.setAccessibleName(option)
            choice.setProperty('role', 'answer')
            # A wrapped label keeps long circuit predictions readable at large text sizes.
            caption = label(option, 'answerText')
            caption.setAttribute(Qt.WA_TransparentForMouseEvents)
            row = QVBoxLayout(choice)
            row.setContentsMargins(12, 8, 12, 8)
            row.addWidget(caption)
            policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            policy.setHeightForWidth(True)
            choice.setSizePolicy(policy)
            self.answers.addButton(choice, index)
            self.choices.addWidget(choice)
        feedback(self.result, 'Choose an answer to practice. Start the lesson to earn credit.')
        self.verticalScrollBar().setValue(0)

    def answer(self, index):
        correct = index == self.step['answer']
        verdict = 'Correct.' if correct else 'Try again.'
        message = (f'{verdict} {self.step["explanation"]}' if correct or self.mode == 'guided'
                   else 'Try again. Open Hints for a clue.')
        feedback(self.result, message, role='correct' if correct else 'error')
        self.ensureWidgetVisible(self.result)


class StudentHub(QWidget):
    def __init__(self,studio,menu=None):
        super().__init__(studio);self.studio=studio;self.data=curriculum()
        self.material=study_guide(self.data)
        from .student_inverter import inventory, expand
        profiles,self.pdk_errors=inventory(studio.pdk_registry,studio.project['pdk'])
        self.inverter_profiles={p['token']:p for p in profiles}
        self.data,self.material=expand(self.data,self.material,profiles)
        self.portfolio=Portfolio(studio.data_dir/'student-hub');self.path_id='foundations'
        self.mode=studio.settings.value('student/viewMode','map')
        if self.mode not in ('map','list'):self.mode='map'
        self.map_overview=True
        self.search_origin=None
        self.setWindowTitle('Student Hub · IC Design Studio');self.resize(1180,780)
        self.text_scale=int(studio.settings.value('student/textScale',100))
        if self.text_scale not in (100,125,150,200):self.text_scale=100
        self.by_id={l['id']:l for l in self.data['lessons']}
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0)
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);outer.addWidget(self.scroll)
        body=QWidget();self.scroll.setWidget(body)
        root=QVBoxLayout(body);root.setContentsMargins(20,16,20,16);root.setSpacing(12)
        head=QHBoxLayout()
        mark=QLabel()
        mark.setPixmap(QIcon(str(Path(__file__).parent/'assets'/'app.svg')).pixmap(QSize(48,48),self.devicePixelRatioF()))
        head.addWidget(mark,0,Qt.AlignVCenter)
        head.setSpacing(12)
        intro=QVBoxLayout();intro.setSpacing(3)
        intro.addWidget(label('Student Hub','title'))
        self.total=label('','muted');intro.addWidget(self.total)
        head.addLayout(intro,1)
        self.resume=button('Continue learning',lambda:self.call(self.continue_learning),'secondary')
        head.addWidget(self.resume,0,Qt.AlignTop)
        menu=menu if menu is not None else QMenu(self)
        self.more_menu=menu
        for title,fn in [('Continue learning',self.continue_learning),('Feature map',lambda:studio.open_editor_doc('STUDENT_HUB.md')),('Engine setup…',self.setup),
                         ('Export learning record…',self.export),('Export portfolio report…',lambda:self.export(report=True)),
                         ('Locate lesson project…',self.locate),('Switch open project PDK…',studio.switch_pdk_dialog),('Reload progress',self.reload_progress)]:
            if title in ('Engine setup…','Export learning record…','Locate lesson project…'):
                menu.addSeparator()
            menu.addAction(title,lambda checked=False,fn=fn:self.call(fn))
        menu.addSeparator()
        sizes=menu.addMenu('Text size');self.text_size_menu=sizes
        size_group=QActionGroup(sizes)
        for scale in (100,125,150,200):
            action=sizes.addAction(f'{scale}%',lambda checked=False,scale=scale:self.set_text_scale(scale))
            action.setCheckable(True);action.setData(scale);size_group.addAction(action)
            action.setChecked(scale==self.text_scale)
        root.addLayout(head)
        self.controls=QBoxLayout(QBoxLayout.LeftToRight);self.controls.setSpacing(8);root.addLayout(self.controls)
        modes=QWidget();modes.setObjectName('studentViewModes')
        segments=QHBoxLayout(modes);segments.setContentsMargins(3,3,3,3);segments.setSpacing(1)
        self.modes=QButtonGroup(self);self.mode_buttons={}
        for key,title in [('map','Map'),('list','List')]:
            control=button(title,lambda key=key:self.set_mode(key),'hubMode');control.setCheckable(True)
            control.setAccessibleName(f'{title} view');control.setChecked(key==self.mode)
            self.modes.addButton(control);self.mode_buttons[key]=control;segments.addWidget(control,1)
        self.controls.addWidget(modes)
        self.search=QLineEdit();self.search.setPlaceholderText('Search all lessons…');self.search.setAccessibleName('Search all learning paths')
        self.search.setClearButtonEnabled(True)
        self.status_filter=QComboBox();self.status_filter.setAccessibleName('Filter lessons by progress')
        self.status_filter.addItems(['All statuses','Ready to start','In progress','Completed',
                                     'Prerequisites needed','PDK setup needed'])
        self.controls.addWidget(self.status_filter)
        self.difficulty_filter=QComboBox();self.difficulty_filter.setAccessibleName('Filter lessons by difficulty')
        self.difficulty_filter.addItems(['All difficulties',*DIFFICULTIES])
        self.controls.addWidget(self.difficulty_filter)
        self.controls.addWidget(self.search,1)
        self.cross_world_button=button('Cross-world paths…',self.open_cross_world_paths,'secondary')
        root.addWidget(self.cross_world_button,0,Qt.AlignLeft)
        self.map_heading=label('World map','title');root.addWidget(self.map_heading)
        self.world_header=QWidget();world_row=QHBoxLayout(self.world_header);world_row.setContentsMargins(0,0,0,0)
        self.back=button('‹  World map',self.show_map,'hubBack');self.back.setAccessibleName('Back to world map')
        world_row.addWidget(self.back,0,Qt.AlignTop)
        world_intro=QVBoxLayout();world_intro.setSpacing(2);world_row.addLayout(world_intro,1)
        self.world_title=label('','title');world_intro.addWidget(self.world_title)
        self.world_progress=label('','muted');world_intro.addWidget(self.world_progress)
        root.addWidget(self.world_header)
        self.path_picker=QComboBox();self.path_picker.setAccessibleName('Learning path');root.addWidget(self.path_picker)
        self.path_titles={p['id']:p['title'] for p in self.data['paths']}
        self.path_titles['capstone']='Advanced project'
        self.world_map=WorldMap(self.path_titles);self.world_map.world_opened.connect(self.open_world)
        self.world_map.card_focused.connect(lambda card:self.scroll.ensureWidgetVisible(card,0,12))
        root.addWidget(self.world_map)
        self.process_panel=QWidget();pv=QVBoxLayout(self.process_panel);pv.setContentsMargins(0,0,0,0)
        pr=QHBoxLayout();pv.addLayout(pr);pr.addWidget(label('Inverter process'))
        self.process_picker=QComboBox();self.process_picker.setAccessibleName('Inverter PDK revision');pr.addWidget(self.process_picker,1)
        self.process_picker.setMinimumContentsLength(8);self.process_picker.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        for item in profiles:self.process_picker.addItem(item['name'],item['token'])
        saved=studio.settings.value('student/inverterProfile','');index=self.process_picker.findData(saved)
        if index>=0:self.process_picker.setCurrentIndex(index)
        actions=QBoxLayout(QBoxLayout.LeftToRight);self.process_actions=actions
        pv.addLayout(actions);actions.addWidget(button('PDK setup',studio.pdk_manager))
        actions.addWidget(button('Set up physical tools',studio.physical_setup))
        actions.addWidget(button('Reload PDKs',lambda:self.call(self.reload_pdks)));actions.addStretch()
        self.process_status=label('','muted');pv.addWidget(self.process_status);root.addWidget(self.process_panel)
        self.process_picker.currentIndexChanged.connect(self.process_changed)
        self.path_list=QListWidget();self.path_list.setAccessibleName('Learning paths');self.path_list.setMinimumWidth(175)
        self.path_list.setMaximumWidth(250);self.path_list.setWordWrap(True)
        for key,title in self.path_titles.items():
            item=QListWidgetItem(title);item.setData(Qt.UserRole,key);self.path_list.addItem(item)
            self.path_picker.addItem(title,key)
        self.path_list.currentRowChanged.connect(lambda i:self.choose_path(self.path_list.item(i).data(Qt.UserRole)) if i>=0 else None)
        self.path_picker.currentIndexChanged.connect(lambda i:self.choose_path(self.path_picker.itemData(i)))
        self.lesson_panel=QWidget();root.addWidget(self.lesson_panel,1)
        panes=QHBoxLayout(self.lesson_panel);panes.setContentsMargins(0,0,0,0)
        self.path_sidebar=QWidget()
        sidebar=QVBoxLayout(self.path_sidebar);sidebar.setContentsMargins(0,0,0,0)
        sidebar.addWidget(label('Learning paths','subtitle'));sidebar.addWidget(self.path_list,1)
        panes.addWidget(self.path_sidebar)
        self.split=QSplitter();self.split.setChildrenCollapsible(False);panes.addWidget(self.split,1)
        left=QWidget();lv=QVBoxLayout(left);lv.setContentsMargins(0,0,0,0);self.split.addWidget(left)
        self.lesson_title=label('Lessons','subtitle');lv.addWidget(self.lesson_title)
        self.heading=label('','muted');lv.addWidget(self.heading)
        self.search.returnPressed.connect(self.focus_results)
        self.find_shortcut=QShortcut(QKeySequence.Find,self);self.find_shortcut.activated.connect(self.search.setFocus)
        self.clear_search_shortcut=QShortcut(QKeySequence(Qt.Key_Escape),self.search)
        self.clear_search_shortcut.setContext(Qt.WidgetShortcut)
        self.clear_search_shortcut.setEnabled(False)
        self.clear_search_shortcut.activated.connect(self.search.clear)
        self.lessons=QListWidget();self.lessons.setWordWrap(True);self.lessons.setObjectName('studentLessons');self.lessons.setAccessibleName('Learning progression');lv.addWidget(self.lessons,1)
        self.lessons.setResizeMode(QListView.Adjust);self.lessons.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.lessons.setMinimumHeight(120)
        self.lessons.itemActivated.connect(lambda _:self.call(self.start_selected))
        self.trail=LessonTrail();self.trail.lesson_selected.connect(self.set_current_lesson);lv.addWidget(self.trail,1)
        right=QWidget();rv=QVBoxLayout(right);rv.setContentsMargins(18,0,0,0)
        self.preview=QTabWidget();self.preview.setDocumentMode(True);self.preview.tabBar().setDrawBase(False)
        self.preview.setAccessibleName('Lesson preview');rv.addWidget(self.preview,1)
        self.details=QTextBrowser();self.details.setOpenLinks(False);self.details.anchorClicked.connect(lambda url:self.select_lesson(url.toString()))
        self.preview.addTab(self.details,'Overview')
        self.study_notes=QTextBrowser();self.study_notes.setAccessibleName('Lesson study notes')
        self.preview.addTab(self.study_notes,'Study notes')
        self.prediction=PredictionPreview(self.ask_ai)
        self.preview.addTab(self.prediction,'Quick check')
        self.details.setAccessibleName('Lesson overview');self.details.setMinimumWidth(240)
        self.progress_text=label('','muted');rv.addWidget(self.progress_text)
        self.progress=QProgressBar();self.progress.setTextVisible(False);self.progress.setAccessibleName('Lesson completion');rv.addWidget(self.progress)
        from .analog_widgets import FlowActions
        self.preview_mode_label,self.preview_mode=learning_mode_picker()
        self.preview_mode.currentIndexChanged.connect(
            lambda _:self.set_learning_mode(self.selected(),self.preview_mode.currentData()))
        self.preview_solution=button('Show solution…',lambda:self.call(self.preview_answer),'secondary')
        self.solution_dialog=None
        choices=FlowActions()
        for widget in (self.preview_mode_label,self.preview_mode,self.preview_solution):
            choices.addWidget(widget)
        rv.addLayout(choices)
        self.start=button('Start lesson',lambda:self.call(self.start_selected),'primary');rv.addWidget(self.start)
        self.reset_filters=button('Clear filters',self.clear_filters,'secondary');rv.addWidget(self.reset_filters)
        self.split.addWidget(right);self.split.setSizes([320,600]);self.lessons.currentRowChanged.connect(self.detail)
        self.search.textChanged.connect(self.search_changed);self.status_filter.currentIndexChanged.connect(self.fill)
        self.difficulty_filter.currentIndexChanged.connect(self.fill)
        self.status=label('Progress is saved on this computer. Simulation checks and written reflections are recorded separately.','muted');root.addWidget(self.status)
        self.guide=LessonGuide(self);studio.addDockWidget(Qt.RightDockWidgetArea,self.guide);self.guide.hide()
        self.apply_theme();self.fill();self.search.setFocus()

    def apply_theme(self):
        style=student_style(self.studio.dark,self.text_scale)
        self.setStyleSheet(style);self.guide.setStyleSheet(style)
        if self.solution_dialog:
            self.solution_dialog.setStyleSheet(style)
        if self.guide.step_images_dialog:
            self.guide.step_images_dialog.setStyleSheet(style)
        self.world_map.set_theme(self.studio.dark,self.text_scale)
        link_style=f'a {{color:{palette(self.studio.dark)["accent"]};}} li {{margin-bottom:8px;}}'
        self.details.document().setDefaultStyleSheet(link_style)
        self.guide.instructions.document().setDefaultStyleSheet(link_style)
        self.adapt_layout()
        scroll=self.details.verticalScrollBar().value();self.detail();self.details.verticalScrollBar().setValue(scroll)

    def set_text_scale(self,scale):
        self.text_scale=scale;self.studio.settings.setValue('student/textScale',scale);self.apply_theme();self.detail()
        for action in self.text_size_menu.actions():
            action.setChecked(action.data()==scale)

    def adapt_layout(self):
        compact=self.width()<1050 or self.text_scale>125
        self.path_sidebar.setVisible(self.mode=='list' and not compact);self.path_picker.setVisible(self.mode=='list' and compact)
        self.controls.setDirection(QBoxLayout.TopToBottom if self.width()<760 or self.text_scale>=150 else QBoxLayout.LeftToRight)
        self.process_actions.setDirection(QBoxLayout.TopToBottom if self.text_scale>=150 and self.width()<1050 else QBoxLayout.LeftToRight)
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
        self.map_overview=False
        self.path_id=key
        self.search_origin=None
        if self.search.text():self.search.clear()
        else:self.fill()

    def open_cross_world_paths(self):
        from .student_paths_ui import CrossWorldPaths
        dialog = CrossWorldPaths(self)
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.show()
        return dialog

    def active_path(self):
        return self.studio.settings.value('student/crossWorldPath','',str)

    def path_handoff(self,lesson):
        from .student_paths import ROUTES, handoff
        route = ROUTES.get(self.active_path())
        if route and lesson:
            return handoff(route,lesson['id'],self.portfolio.state,self.by_id)
        return None

    def next_path_lesson(self,lesson):
        from .student_paths import ROUTES, milestones
        route = ROUTES.get(self.active_path())
        if route:
            results = milestones(route,self.portfolio.state,self.by_id)
            for index, (current, following) in enumerate(zip(route.milestones,route.milestones[1:])):
                if current.lesson==lesson['id'] and all(results[:index+1]):
                    return following.lesson
        return None

    def set_mode(self,mode):
        self.mode=mode
        self.mode_buttons[mode].setChecked(True)
        self.studio.settings.setValue('student/viewMode',mode)
        self.fill()

    def open_world(self,key):
        self.choose_path(key)
        self.focus_results()

    def show_map(self):
        self.map_overview=True
        self.clear_filters()
        self.world_map.cards[self.path_id].setFocus()

    def focus_results(self):
        if not self.world_map.isHidden():
            self.world_map.cards[self.path_id].setFocus()
        elif not self.trail.isHidden() and self.selected():
            self.trail.rows[self.selected()['id']].setFocus()
        elif self.reset_filters.isVisible():
            self.reset_filters.setFocus()
        elif not self.lessons.isHidden():
            self.lessons.setFocus()

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

    def search_changed(self,text):
        self.clear_search_shortcut.setEnabled(bool(text))
        if text.strip():
            if self.search_origin is None:
                self.search_origin=(self.selected() or {}).get('id','')
            self.fill()
        else:
            origin,self.search_origin=self.search_origin,None
            self.fill(lesson_id=origin)

    def clear_filters(self):
        origin,self.search_origin=self.search_origin,None
        with QSignalBlocker(self.status_filter), QSignalBlocker(self.difficulty_filter), QSignalBlocker(self.search):
            self.status_filter.setCurrentIndex(0)
            self.difficulty_filter.setCurrentIndex(0)
            self.search.clear()
        self.clear_search_shortcut.setEnabled(False)
        self.fill(lesson_id=origin)
        self.search.setFocus()

    def fill(self,*_,lesson_id=None):
        previous=self.selected();key=lesson_id or (previous['id'] if previous else None);state=self.portfolio.state
        from .student_inverter import readiness
        profile=self.process_picker.currentData()
        words=self.search.text().casefold().split()
        filter_status=self.status_filter.currentText() if self.status_filter.currentIndex() else None
        difficulty=self.difficulty_filter.currentText() if self.difficulty_filter.currentIndex() else None
        all_worlds=bool(words or (self.mode=='map' and self.map_overview and (filter_status or difficulty)))
        overview=self.mode=='map' and self.map_overview and not all_worlds
        route=self.mode=='map' and not self.map_overview and not words
        self.world_map.setVisible(overview);self.map_heading.setVisible(overview)
        self.world_header.setVisible(self.mode=='map' and not self.map_overview)
        self.lesson_panel.setVisible(not overview)
        self.trail.setVisible(route);self.lessons.setVisible(not route)
        self.lesson_title.setText('Topics & lessons' if route else 'Lessons')
        self.process_panel.setVisible(not overview and self.path_id=='inverter')
        self.adapt_layout()
        item=self.inverter_profiles.get(profile)
        self.process_status.setText((readiness(item) if item else 'Register a PDK to start.')+
                                   ('\n'+ '\n'.join(self.pdk_errors) if self.pdk_errors else ''))
        self.lessons.blockSignals(True);self.lessons.clear()
        available=[l for l in self.data['lessons'] if not l.get('inverter_profile') or self.inverter_profiles[l['inverter_profile']]['ready']]
        selected_available=[l for l in available if not l.get('inverter_profile') or l['inverter_profile']==profile]
        summary=f'{sum(complete(state,l) for l in selected_available)} of {len(selected_available)} lessons complete'
        self.total.setText(summary)
        self.total.setToolTip('The learning-path counts use the selected inverter PDK. Inverter progress is separate for each revision; the overall count includes every available revision.')
        workspace_uses=Counter(lesson['workspace'] for lesson in self.data['lessons'])
        world_rows={path:[] for path in self.path_titles}
        all_rows=[]
        for lesson in self.data['lessons']:
            if lesson.get('inverter_profile',profile)!=profile:continue
            count=len(earned(state,lesson))
            if lesson.get('inverter_profile') and not self.inverter_profiles[lesson['inverter_profile']]['ready']:
                status='PDK setup needed'
            elif count==len(lesson['steps']):
                status='Completed'
            elif missing_prerequisites(state,lesson,self.data):
                status='Prerequisites needed'
            elif (count or any(state['lessons'].get(lesson['id'],{}).get('notes',{}).values())
                  or (workspace_uses[lesson['workspace']]==1 and self.portfolio.workspace(lesson))):
                status='In progress'
            else:
                status='Ready to start'
            row=(lesson,status,count)
            world_rows[lesson['path']].append(row);all_rows.append(row)
        self.path_list.blockSignals(True);self.path_picker.blockSignals(True)
        for i in range(self.path_list.count()):
            item=self.path_list.item(i);path_key=item.data(Qt.UserRole)
            rows=world_rows[path_key];n=sum(status=='Completed' for _,status,_ in rows)
            title=self.path_titles[path_key]
            statuses={status for _,status,_ in rows}
            world_status=next(iter(statuses)) if len(statuses)==1 else ''
            if not rows:world_status='PDK setup needed' if path_key=='inverter' else 'No lessons yet'
            self.world_map.cards[path_key].set_progress(n,len(rows),world_status)
            item.setText(title+f'\n{n} of {len(rows)} complete');self.path_picker.setItemText(i,title+f' · {n}/{len(rows)}')
            if path_key==self.path_id:
                self.path_list.setCurrentRow(i);self.path_picker.setCurrentIndex(i)
                self.world_title.setText(title);self.world_progress.setText(f'{n} of {len(rows)} lessons complete')
        self.path_list.blockSignals(False);self.path_picker.blockSignals(False)
        self.world_map.update()
        if self.path_id=='capstone':self.heading.setText(self.data['capstone']['subtitle'])
        else:self.heading.setText(next(p['subtitle'] for p in self.data['paths'] if p['id']==self.path_id))
        rows=all_rows if all_worlds else world_rows[self.path_id]
        for l,status,count in rows:
            path_title=self.path_titles[l['path']]
            if words:
                search_text=' '.join([l['title'],l['summary'],l['difficulty'],path_title,*l['skills']]).casefold()
                if not all(word in search_text for word in words):continue
            if filter_status and filter_status!=status:continue
            if difficulty and l['difficulty']!=difficulty:continue
            title=f'{l["title"]}\n{path_title}' if all_worlds else l['title']
            item=QListWidgetItem(f'{title}\n{l["difficulty"]} · {status} · {count}/{len(l["steps"])} steps · {l["minutes"]} min')
            item.setToolTip(item.text())
            item.setData(Qt.UserRole,l['id']);self.lessons.addItem(item)
            if key==l['id']:self.lessons.setCurrentItem(item)
        if all_worlds or filter_status or difficulty:
            matches=self.lessons.count()
            self.heading.setText(f'{matches} matching '+('lesson' if matches==1 else 'lessons'))
        if route:self.trail.set_lessons(self.path_id,world_rows[self.path_id],filter_status,difficulty)
        if self.lessons.currentRow()<0:self.lessons.setCurrentRow(0)
        self.lessons.blockSignals(False);self.detail()

    def detail(self,*_):
        l=self.selected();self.start.setEnabled(bool(l))
        if l and not self.trail.isHidden():self.trail.select(l['id'])
        self.progress.setVisible(bool(l))
        filtered=bool(self.search.text().strip() or self.status_filter.currentIndex() or self.difficulty_filter.currentIndex())
        self.reset_filters.setVisible(not l and filtered)
        self.preview.setTabEnabled(1,bool(l))
        key=l['id'] if l else ''
        self.preview.setTabEnabled(2,self.prediction.set_lesson(l,self.material['hints'].get(key,{}),
                                                               self.material['practice'].get(key,{})))
        for widget in (self.preview_mode_label,self.preview_mode,self.preview_solution):
            widget.setVisible(bool(l))
        if not l:
            self.preview.setCurrentIndex(0);self.study_notes.clear()
            self.details.setPlainText('No matching lessons. Clear the filters to see this learning path.' if filtered else
                                      'No lessons are available for this selection.')
            self.progress.setValue(0);self.progress_text.setText('');self.start.setText('Start lesson');return
        self.sync_preview_mode(self.learning_mode(l))
        state=self.portfolio.state;missing=missing_prerequisites(state,l,self.data);done=earned(state,l)
        esc=html.escape
        direct=[k for k in l['requires'] if k in missing] or missing[:1]
        pre='<br>'.join(f'<a href="{k}">{esc(self.by_id[k]["path"].title()+" · "+self.by_id[k]["title"])}</a>' for k in direct)
        rows=''.join(f'<li><b>{esc(s["title"])}</b> · {"Earned" if s["id"] in done else esc(evidence_label(s))}</li>' for s in l['steps'])
        cap='<p>This milestone continues the same sensor project. Earlier repairs are preserved.</p>' if l['path']=='capstone' and not l.get('signal_lab') else ''
        goal=f'<p><b>{esc(l["goal"])}</b></p>' if l.get('goal') else ''
        teaching=self.material['lessons'][l['id']]
        from .student_paths_ui import handoff_html
        handoff=handoff_html(self.path_handoff(l))
        self.study_notes.setHtml(f'<h2>{esc(l["title"])}</h2>'+notes_html(teaching,l)+preparation_html(l))
        self.details.setHtml(f'<h2>{esc(l["title"])}</h2><p><b>{l["difficulty"]}</b> · {l["minutes"]} min</p><p>{esc(l["summary"])}</p>{goal}{cap}<p><b>Skills</b><br>{esc(" · ".join(l["skills"]))}</p>'+
            handoff+overview_html(teaching)+preparation_html(l)+
            (f'<p><b>Complete first</b><br>{pre}</p><p>{len(missing)} prerequisite lesson(s) remaining. You can practice now; earn progression credit after the prerequisites.</p>' if missing else '<p>Ready for guided work in the real editor.</p>')+
            f'<ol>{rows}</ol><p>Earlier earned steps remain a record of the design that passed at that time.</p>')
        self.progress.setRange(0,len(l['steps']));self.progress.setValue(len(done));self.progress.setFormat('%v of %m steps earned')
        self.progress_text.setText(f'{len(done)} of {len(l["steps"])} steps complete')
        self.start.setText('Practice lesson' if missing else 'Review lesson' if complete(state,l) else 'Resume lesson' if self.portfolio.workspace(l) else 'Start lesson')
        if l.get('inverter_profile') and not self.inverter_profiles[l['inverter_profile']]['ready']:
            self.start.setEnabled(False);self.start.setText('Set up this PDK to start')
            self.details.setHtml(self.details.toHtml()+notes_html(teaching,l))

    def ask_ai(self,lesson,step):
        if lesson and step:
            if self.learning_mode(lesson)=='independent':
                practice=self.material['practice'][lesson['id']]
                step={**step,'instructions':challenge_text(step,practice)}
            return self.call(lambda:self.studio.ask_lesson(lesson,step))

    def learning_mode(self,lesson):
        mode=self.studio.settings.value('student/learningMode/'+lesson['id'],'guided',str)
        return mode if mode in LESSON_MODES else 'guided'

    def sync_preview_mode(self,mode):
        with QSignalBlocker(self.preview_mode):
            self.preview_mode.setCurrentIndex(self.preview_mode.findData(mode))
        self.prediction.set_learning_mode(mode)

    def set_learning_mode(self,lesson,mode):
        if not lesson or mode not in LESSON_MODES:
            return
        self.studio.settings.setValue('student/learningMode/'+lesson['id'],mode)
        current=self.selected()
        if current and current['id']==lesson['id']:
            self.sync_preview_mode(mode)
        if self.guide.lesson and self.guide.lesson['id']==lesson['id']:
            self.guide.sync_learning_mode(mode)
            self.guide.lesson_tabs.setCurrentWidget(self.guide.instructions)

    def preview_answer(self):
        if lesson:=self.selected():
            step=self.prediction.step if self.preview.currentWidget() is self.prediction else None
            return self.show_solution(lesson,step)

    def show_solution(self,lesson,step=None):
        if self.solution_dialog is None:
            self.solution_dialog=LessonSolution(self.studio)
            self.solution_dialog.setStyleSheet(student_style(self.studio.dark,self.text_scale))
        key=lesson['id']
        self.solution_dialog.open_lesson(lesson,self.material['practice'][key],self.material['lessons'][key],step)
        return self.solution_dialog

    def select_lesson(self,key):
        if key not in self.by_id:return
        if self.by_id[key].get('inverter_profile'):
            with QSignalBlocker(self.process_picker):
                self.process_picker.setCurrentIndex(self.process_picker.findData(self.by_id[key]['inverter_profile']))
        self.path_id=self.by_id[key]['path']
        if self.mode=='map':self.map_overview=False
        with QSignalBlocker(self.status_filter), QSignalBlocker(self.difficulty_filter), QSignalBlocker(self.search):
            self.status_filter.setCurrentIndex(0);self.difficulty_filter.setCurrentIndex(0);self.search.clear()
        self.search_origin=None;self.clear_search_shortcut.setEnabled(False)
        self.fill(lesson_id=key)

    def set_current_lesson(self,key):
        for i in range(self.lessons.count()):
            if self.lessons.item(i).data(Qt.UserRole)==key:self.lessons.setCurrentRow(i);break

    def continue_learning(self):
        data=self.data
        if self.path_id=='inverter':data={**data,'lessons':[l for l in data['lessons'] if l.get('inverter_profile')==self.process_picker.currentData()]}
        else:data={**data,'lessons':[l for l in data['lessons'] if not l.get('inverter_profile') or self.inverter_profiles[l['inverter_profile']]['ready']]}
        state=self.portfolio.state
        recent=self.studio.settings.value('student/lastLesson','',str)
        lesson=next((item for item in data['lessons'] if item['id']==recent and
                     not complete(state,item) and not missing_prerequisites(state,item,data)),None)
        if lesson is None:lesson=next_lesson(state,data)
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
                if not path.is_file():raise ValueError('Saved lesson project is missing. Open the Student Hub menu and choose Locate lesson project.')
                project=load_project(path)
                if project['id']!=record['project_id']:raise ValueError('The saved lesson file was replaced with a different project.')
            else:
                if l.get('inverter_profile'):
                    from .student_inverter import create as inverter
                    project=inverter(self.inverter_profiles[l['inverter_profile']])
                elif l.get('analog_project') and l['analog_project'] not in ('bandgap','interview'):
                    from .student_analog import choose_technology
                    project=create(l['starter'], choose_technology(self.inverter_profiles, s.project['pdk']))
                else:project=create(l['starter'])
                path=self.portfolio.root/'projects'/(l['workspace']+'-'+uid()+'.icproj')
                path.parent.mkdir(parents=True,exist_ok=True);save_project(project,path);self.portfolio.attach(l,project,path)
            if s.set_project(project,path) is False:return
        if self.mode=='map' and (self.map_overview or self.search.text().strip()):
            self.select_lesson(l['id'])
        s.show_design_workspace()
        self.guide.open_lesson(l);self.guide.show();self.guide.raise_()
        s.resizeDocks([self.guide],[390],Qt.Horizontal)
        s.resizeDocks([s.inspector,self.guide],[260,620],Qt.Vertical)
        from .digital_design import config
        if not s.project.get('mixed_signal') and config(s.project,s.project['top']):self.guide.rtl()
        else:self.guide.workspace()
        s.settings.setValue('student/lastLesson',l['id'])
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
        feedback(self.status,'Progress is up to date.')
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
        v.addWidget(label('Many lessons use the included teaching solver. Signal experiments that use native SPICE need ngspice. Digital lessons use the Included or Custom selection in Digital tools. The SAR and sensor-acquisition benches use ngspice and Icarus (iverilog and vvp).'))
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
        def start_smoke():
            from threading import Thread
            from concurrent.futures import Future
            from .mixed_signal import resolve_tools, native_smoke_test, NativeEngineSetupError
            try:
                tools=resolve_tools({name:edit.text() for name,edit in edits.items()},'Student Hub → Engine setup')
            except NativeEngineSetupError as exc:
                native_status.setText(str(exc))
                return
            smoke_button.setEnabled(False)
            feedback(native_status,'Checking compile, RTL simulation and SPICE operating point…')
            future=Future()
            def worker():
                try:
                    native_smoke_test(tools)
                except Exception as exc:
                    future.set_exception(exc)
                else:
                    future.set_result(None)
            timer=QTimer(dialog)
            timer.setInterval(100)
            def poll():
                if not future.done():
                    return
                timer.stop()
                msg=future.exception()
                feedback(native_status,f'Engine check failed. {msg}' if msg else
                         'Icarus, VVP and ngspice completed the engine check.',bool(msg))
                smoke_button.setEnabled(True)
                timer.deleteLater()
            timer.timeout.connect(poll)
            Thread(target=worker,daemon=True).start()
            timer.start()
        smoke_button=button('Test native engines',start_smoke)
        v.addWidget(smoke_button)
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
        self.difficulty_label=label('','muted');v.addWidget(self.difficulty_label)
        self.target_label=label('','muted');self.target_label.hide();v.addWidget(self.target_label)
        self.steps=QComboBox();self.steps.setAccessibleName('Guided lesson step');self.steps.setMinimumContentsLength(10)
        self.steps.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon);v.addWidget(self.steps)
        from .analog_widgets import FlowActions
        mode_label,self.mode_picker=learning_mode_picker()
        modes=FlowActions()
        modes.addWidget(mode_label);modes.addWidget(self.mode_picker);v.addLayout(modes)
        self.mode_picker.currentIndexChanged.connect(
            lambda _:hub.set_learning_mode(self.lesson,self.mode_picker.currentData()))
        from .student_testbench import WORKFLOWS
        self.bench_workflow_label=label('Testbench workflow')
        self.bench_workflow=QComboBox();self.bench_workflow.setAccessibleName('Testbench workflow')
        for key,name in WORKFLOWS.items():self.bench_workflow.addItem(name,key)
        self.bench_workflow_label.setBuddy(self.bench_workflow)
        v.addWidget(self.bench_workflow_label);v.addWidget(self.bench_workflow)
        self.bench_workflow_label.hide();self.bench_workflow.hide()
        self.bench_workflow.currentIndexChanged.connect(self.change_bench_workflow)
        self.lesson_tabs=QTabWidget();self.lesson_tabs.setAccessibleName('Lesson teaching and task');v.addWidget(self.lesson_tabs,1)
        self.design_notes=QTextBrowser();self.design_notes.setAccessibleName('Concept, worked example and interview preparation')
        self.instructions=QTextBrowser();self.instructions.setAccessibleName('Step instructions')
        self.instructions.setOpenLinks(False)
        self.instructions.anchorClicked.connect(self.step_image_link)
        self.step_images_dialog=None
        self.lesson_tabs.addTab(self.design_notes,'Learn');self.lesson_tabs.addTab(self.instructions,'Do this step')
        hints_page=QScrollArea();hints_page.setWidgetResizable(True)
        hints_body=QWidget();hints_layout=QVBoxLayout(hints_body);hints_page.setWidget(hints_body)
        self.hint_question=QComboBox();self.hint_question.setAccessibleName('Knowledge check for hints')
        self.hints=QuestionHints();hints_layout.addWidget(self.hint_question);hints_layout.addWidget(self.hints)
        hints_layout.addStretch()
        self.hints_index=self.lesson_tabs.addTab(hints_page,'Hints')
        self.review_notes=QTextBrowser()
        self.review_notes.setAccessibleName('Follow-up exercise and evidence to discuss')
        self.lesson_tabs.addTab(self.review_notes,'Try another case')

        self.hint_question.currentIndexChanged.connect(self.show_question_hints)
        self.lesson_tabs.setMinimumHeight(220)
        self.ask_button=resisty_button(lambda:self.call(self.ask_ai),'this lesson step')
        self.solution_button=button('Show solution…',lambda:self.call(self.show_solution),'secondary')
        self.ask_button.hide();self.solution_button.hide()
        help_actions=FlowActions()
        help_actions.addWidget(self.ask_button);help_actions.addWidget(self.solution_button)
        v.addLayout(help_actions)
        self.answer_label=label('Your answer');v.addWidget(self.answer_label)
        self.answer=QComboBox();self.answer.setAccessibleName('Knowledge check answer');self.answer.setMinimumContentsLength(10)
        self.answer.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon);v.addWidget(self.answer);self.answer_label.setBuddy(self.answer)
        self.notes_label=label('Your reflection');v.addWidget(self.notes_label)
        self.notes=QPlainTextEdit();self.notes.setPlaceholderText('Record your observations and reasoning…');self.notes.setAccessibleName('Lesson reflection');self.notes.setMinimumHeight(100);self.notes.setMaximumHeight(220);v.addWidget(self.notes);self.notes_label.setBuddy(self.notes)
        self.note_status=label('','muted');v.addWidget(self.note_status)
        self.controls={}
        for title,fn in [('Open workspace',self.workspace),('Open RTL',self.rtl),('Open VGA Playground',self.open_vga),
                         ('Mixed-signal experiment…',self.mixed_signal_setup),('Run lesson',self.run),
                         ('Results',self.results),('Cancel lesson runs',self.cancel),('Save work',self.save_work),
                         ('Student Hub',self.show_hub),('Engine setup',hub.setup)]:
            self.controls[title]=button(title,lambda fn=fn:self.call(fn))
        editors=FlowActions();v.addLayout(editors)
        for name in ('Open workspace','Open RTL','Open VGA Playground','Mixed-signal experiment…'):
            editors.addWidget(self.controls[name])
        self.inverter_actions=QWidget();iv=FlowActions(self.inverter_actions);v.addWidget(self.inverter_actions)
        self.inverter_buttons=[]
        for title,fn in [('Open inverter',self.open_inverter),('Build layout',self.build_inverter),
                         ('Add DRC fault',lambda:self.inverter_edit('drc')),('Add LVS fault',lambda:self.inverter_edit('lvs')),
                         ('Repair lesson fault',lambda:self.inverter_edit('repair'))]:
            control=button(title,lambda fn=fn:self.call(fn));iv.addWidget(control);self.inverter_buttons.append(control)
        self.inverter_actions.hide()
        self.analog_action=button('Edit testbench…',lambda:self.call(self.analog_project_action))
        self.analog_action.hide();v.addWidget(self.analog_action)
        self.layout_action=button('Edit lesson layout…',lambda:self.call(self.layout_study_action))
        self.layout_action.hide();v.addWidget(self.layout_action)
        self.signal_action=button('Edit experiment…',lambda:self.call(self.signal_study_action))
        self.signal_action.hide();v.addWidget(self.signal_action)
        self.qualify=button('Run qualification',lambda:self.call(self.qualification));v.addWidget(self.qualify)
        runs=FlowActions();v.addLayout(runs)
        for name in ('Run lesson','Results','Cancel lesson runs'):
            runs.addWidget(self.controls[name])
        self.run_status=label('','muted');v.addWidget(self.run_status)
        self.run_progress=QProgressBar();self.run_progress.setTextVisible(False);self.run_progress.setAccessibleName('Lesson run progress');v.addWidget(self.run_progress);self.run_progress.hide()
        self.check_button=button('Check this step',lambda:self.call(self.check),'primary');v.addWidget(self.check_button)
        self.feedback=label('');self.feedback.setTextInteractionFlags(Qt.TextSelectableByMouse);v.addWidget(self.feedback)
        self.next_button=button('Next step',lambda:self.call(self.advance),'secondary');v.addWidget(self.next_button);self.next_button.hide()
        self.handoff_button=button('Add handoff to reflection',lambda:self.call(self.add_handoff),'secondary')
        v.addWidget(self.handoff_button);self.handoff_button.hide()
        footer=FlowActions();v.addLayout(footer)
        for name in ('Save work','Student Hub','Engine setup'):
            footer.addWidget(self.controls[name])
        self.steps.currentIndexChanged.connect(self.step_changed)
        self.note_timer=QTimer(self);self.note_timer.setSingleShot(True);self.note_timer.setInterval(600)
        self.note_timer.timeout.connect(lambda:self.call(self.save_note));self.notes.textChanged.connect(self.note_changed)
        self.active_step=None;self.note_dirty=False;self.practice_passed=False
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
        self.difficulty_label.setText(lesson['difficulty'])
        self.target_label.setText(lesson.get('goal',''));self.target_label.setVisible(bool(lesson.get('goal')))
        self.ask_button.show();self.solution_button.show()
        self.sync_learning_mode(self.hub.learning_mode(lesson))
        if lesson.get('bench_project'):
            choice=self.studio.settings.value('student/benchWorkflow/'+lesson['bench_project'],'graphical')
            with QSignalBlocker(self.bench_workflow):
                self.bench_workflow.setCurrentIndex(max(0,self.bench_workflow.findData(choice)))
        self.design_notes.setHtml(notes_html(self.hub.material['lessons'][lesson['id']],lesson))
        self.review_notes.setHtml(review_html(lesson))
        questions=[step for step in lesson['steps'] if step['kind']=='quiz']
        quiz_selector(self.hint_question,questions)
        self.lesson_tabs.setTabEnabled(self.hints_index,bool(questions))
        self.steps.blockSignals(True);self.steps.clear()
        done=earned(self.hub.portfolio.state,lesson)
        for i,step in enumerate(lesson['steps']):self.steps.addItem(f'{i+1}. '+step['title']+(' ✓' if step['id'] in done else ''))
        index=next((i for i,s in enumerate(lesson['steps']) if s['id'] not in done),len(lesson['steps'])-1)
        self.steps.setCurrentIndex(index);self.steps.blockSignals(False);self.step_changed(index)
        self.inverter_actions.setVisible(lesson['path']=='inverter')
        self.update_run_state()

    def step_changed(self,index):
        if not self.lesson or index<0:return
        try:self.save_note()
        except Exception as exc:
            self.steps.blockSignals(True)
            self.steps.setCurrentIndex(self.lesson['steps'].index(self.active_step) if self.active_step else -1)
            self.steps.blockSignals(False);feedback(self.feedback,str(exc),True);return
        step=self.lesson['steps'][index];self.active_step=step;self.filling=True;self.practice_passed=False
        self.update_task()
        self.lesson_tabs.setCurrentIndex(1)
        preceding=next((s['id'] for s in reversed(self.lesson['steps'][:index+1]) if s['kind']=='quiz'),None)
        with QSignalBlocker(self.hint_question):
            self.hint_question.setCurrentIndex(max(0,self.hint_question.findData(preceding)))
        self.show_question_hints()
        self.answer.clear();self.answer.addItem('Choose an answer…',None)
        for i,text in answer_choices(step,self.lesson):self.answer.addItem(text,i)
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

    def sync_learning_mode(self,mode):
        with QSignalBlocker(self.mode_picker):
            self.mode_picker.setCurrentIndex(self.mode_picker.findData(mode))
        self.update_task()

    def update_task(self):
        if self.step_images_dialog:
            self.step_images_dialog.close()
        if self.active_step:
            practice=self.hub.material['practice'][self.lesson['id']]
            guided=self.mode_picker.currentData()=='guided'
            content=task_html(self.active_step,practice,guided,workflow=self.bench_workflow.currentData())
            from .student_paths_ui import handoff_html
            handoff = self.hub.path_handoff(self.lesson)
            self.handoff_button.setVisible(bool(self.active_step['kind']=='reflection' and handoff and handoff['reading']))
            content = handoff_html(handoff) + content
            if guided:
                content='<p><a href="step-images">Show step images…</a></p>'+content
            self.instructions.setHtml(content)

    def add_handoff(self):
        from .student_paths import handoff_note
        item = self.hub.path_handoff(self.lesson)
        if self.active_step['kind']!='reflection' or not item or not item['reading']:
            return
        text = handoff_note(item)
        if text not in self.notes.toPlainText():
            self.notes.appendPlainText(text)
            self.save_note()
        self.notes.setFocus()

    def change_bench_workflow(self,*_):
        if self.lesson and self.lesson.get('bench_project'):
            self.studio.settings.setValue('student/benchWorkflow/'+self.lesson['bench_project'],
                                          self.bench_workflow.currentData())
            self.update_task()
            self.update_run_state()

    def step_image_link(self,url):
        if url.toString()=='step-images' and self.mode_picker.currentData()=='guided':
            self.call(self.show_step_images)

    def show_step_images(self):
        from .student_step_images import StepImages

        if not self.active_step or self.mode_picker.currentData()!='guided':
            return None
        if self.step_images_dialog:
            self.step_images_dialog.close()
        self.step_images_dialog=StepImages(self)
        self.step_images_dialog.finished.connect(self.clear_step_images)
        self.step_images_dialog.show()
        self.step_images_dialog.raise_()
        self.step_images_dialog.activateWindow()
        return self.step_images_dialog

    def clear_step_images(self,*_):
        self.step_images_dialog=None

    def show_question_hints(self,*_):
        hints=self.hub.material['hints'].get(self.lesson['id'],{}) if self.lesson else {}
        self.hints.set_entries(hints.get(self.hint_question.currentData(),()))

    def help_step(self):
        step = self.active_step
        if step and self.lesson_tabs.currentIndex() == self.hints_index:
            selected = self.hint_question.currentData()
            step = next((s for s in self.lesson['steps'] if s['id'] == selected), step)
        return step

    def ask_ai(self):
        if step:=self.help_step():
            return self.hub.ask_ai(self.lesson,step)

    def show_solution(self):
        if step:=self.help_step():
            return self.hub.show_solution(self.lesson,step)

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
        quiz=self.active_step['kind']=='quiz'
        if quiz:
            if self.answer.currentData() is None:
                raise ValueError('Choose an answer before checking this step.')
            if self.mode_picker.currentData()=='independent' and self.answer.currentData()!=self.active_step['answer']:
                raise ValueError('Try again. Open Hints for a clue.')
        evidence=evaluate(self.active_step,self.lesson,s.project,s.run_manager.rows,s.path,self.answer.currentData(),self.notes.toPlainText())
        if missing_prerequisites(self.hub.portfolio.state,self.lesson,self.hub.data):
            detail=' '+evidence['explanation'] if quiz else ''
            feedback(self.feedback,'Practice check passed. Complete the listed prerequisites to earn progression credit.'+detail,role='correct')
            self.practice_passed=True;self.update_next();return
        self.hub.portfolio.award(self.lesson,self.active_step,evidence,self.hub.data)
        index=self.steps.currentIndex();self.hub.fill()
        self.steps.setItemText(index,f'{index+1}. '+self.active_step['title']+' ✓')
        feedback(self.feedback,'Reflection recorded.' if self.active_step['kind']=='reflection' else 'Checkpoint passed. Evidence saved.')
        if quiz:
            feedback(self.feedback,'Checkpoint passed. '+evidence['explanation'],role='correct')
        elif 'logic_samples' in evidence:
            count=len(evidence['logic_samples'])
            message=f'{count} samples passed in both the schematic and layout-loaded cases.'
            if evidence.get('targets'):message+=' All design targets passed.'
            feedback(self.feedback,message,role='correct')
        elif 'continuous_rails' in evidence:
            feedback(self.feedback,'VPWR and VGND are continuous across the seam. The checked layers meet spacing.',role='correct')
        elif 'loop_measurements' in evidence:
            count = len(evidence['loop_measurements'])
            feedback(self.feedback,f'Saved unity crossings and phase margins for {count} comparison settings.',role='correct')
        elif 'bench_reading' in evidence:
            from .student_testbench import WORKFLOWS
            workflow=WORKFLOWS[evidence['bench_workflow']]
            feedback(self.feedback,f'{workflow} passed at {evidence["bench_reading"]:.5g} {evidence.get("bench_unit","V")}. Evidence saved.',role='correct')
        elif 'device_metrics' in evidence:
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
        elif 'interview_measurements' in evidence:
            feedback(self.feedback,'Comparison recorded. Open Results to review the measurements before answering the interview prompt.')
        elif 'analog_runs' in evidence:
            point=evidence['analog_runs'][0].get('gmid')
            if point:
                feedback(self.feedback,f'M2 measured {point["gm_S"]*1e6:.3g} µS gm, {point["current_A"]*1e6:.3g} µA ID and {point["gm_over_id"]:.3g} V⁻¹ gm/ID. Evidence saved.')
            else:
                feedback(self.feedback,f'All {len(evidence["analog_runs"])} testbenches meet the targets. Measurements saved to your learning record.')
        elif 'layout_study' in evidence:
            measurements=evidence['layout_study']
            feedback(self.feedback,'Checkpoint passed. '+' · '.join(f'{key}: {value}' for key,value in measurements.items())+'. Saved.')
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
        practice_next=self.practice_passed and self.steps.currentIndex()+1<self.steps.count()
        self.next_button.setVisible(bool(self.active_step and (self.active_step['id'] in done or practice_next)))
        if complete(self.hub.portfolio.state,self.lesson):
            self.next_button.setText('Continue path' if self.hub.next_path_lesson(self.lesson) else 'Continue learning')
        else:
            self.next_button.setText('Next step')

    def advance(self):
        if self.practice_passed:
            if self.steps.currentIndex()+1<self.steps.count():
                self.steps.setCurrentIndex(self.steps.currentIndex()+1);self.steps.setFocus()
            return
        if complete(self.hub.portfolio.state,self.lesson):
            next_lesson = self.hub.next_path_lesson(self.lesson)
            if next_lesson:
                self.show_hub()
                self.hub.select_lesson(next_lesson)
            else:
                self.hub.continue_learning()
            return
        done=earned(self.hub.portfolio.state,self.lesson)
        index=next((i for i,s in enumerate(self.lesson['steps']) if s['id'] not in done),None)
        if index is not None:self.steps.setCurrentIndex(index);self.steps.setFocus()

    def workspace(self):
        from .student_projects import lesson_workspace

        self.require_project();s=self.studio
        if not s.leave_digital_workspace():return
        s.cid,mode=lesson_workspace(s.project,self.lesson,self.active_step['id'])
        s.mode_combo.setCurrentIndex(1 if mode=='layout' else 0);s.refresh(True)
        self.show();self.raise_()

    def signal_study_action(self):
        from .student_signal_ui import open_form
        self.flush();self.require_idle()
        open_form(self,self.lesson['signal_lab'],self.active_step['id'])

    def layout_study_action(self):
        from .student_layout_labs import build_fold, focus, set_clock_spacing, set_input_ports
        from .student_layout_signoff_ui import ACTIONS, open_form
        self.flush();self.require_idle();s=self.studio
        lab=self.lesson['layout_lab'];step=self.active_step['id']
        cid=focus(s.project,lab,step)
        if (lab,step) in ACTIONS:
            open_form(self,lab,step,cid)
        elif (lab,step)==('access','access'):
            from .student_layout_signoff import current_placement, place_macro
            if current_placement(s.project)!=(16000,0):
                s.commit(lambda p:place_macro(p,16000,0,s.layout.locked_layers),'Use compact practice layout')
            self.workspace()
            feedback(self.feedback,'Compact macro ready. Check this step to measure the metal-1 detour.')
        elif lab=='fold' and step=='folded':
            s.commit(lambda p:build_fold(p,cid,4),'Generate device layout');self.workspace()
        elif lab=='lvs' and step=='swap':
            choice,ok=QInputDialog.getItem(self,'Edit input ports','Physical position of inp',
                                           ['Upper · Y = +4 µm','Lower · Y = −4 µm'],1,False)
            if ok:s.commit(lambda p:set_input_ports(p,cid,choice.startswith('Upper')),'Reassign input ports')
        elif lab=='noise' and step=='space':
            distance,ok=QInputDialog.getDouble(self,'Set clock spacing','Centerline separation (µm)',1.4,1.4,8,3)
            if ok:s.commit(lambda p:set_clock_spacing(p,cid,round(distance*200)*5),'Move clock route')
        elif lab=='eco' and step=='update':
            from .layout_eco import apply, propose
            cell=next(c for c in s.project['cells'] if c['id']==cid)
            candidate,report=propose(s.project,cid,[cell['devices'][0]['id']],s.layout.locked_layers)
            moves=len(report['adjusted_routes'])
            choice=QMessageBox.question(self,'Review layout update',
                  f'Regenerate the shared NMOS and adjust {moves} attached route(s). The two parent instances retain their placements. Apply the update?')
            if choice==QMessageBox.Yes:
                s.commit(lambda p:apply(p,candidate,report),'Update shared transistor layout');self.workspace()

    def analog_project_action(self):
        self.flush();self.require_idle();s=self.studio
        if self.lesson.get('standard_cell'):
            if self.active_step['id']=='route':
                from .student_cell_layout_ui import route_editor
                return route_editor(self)
            if self.lesson.get('goal'):
                from .student_cell_layout_ui import design_editor
                return design_editor(self)
            from .student_standard_cells import build_layout
            key=self.lesson['standard_cell']
            s.commit(lambda p:build_layout(p,key),'Place standard-cell rows')
            self.workspace()
            self.update_run_state()
            feedback(self.feedback,'Rows placed. Inspect the footprint, rails, and ports before checking this step.')
            return
        if self.lesson.get('bench_project'):
            from .student_testbench_ui import editor
            return editor(self)
        if self.lesson.get('analog_project')=='interview':
            from .student_interview import focus
            if not s.leave_digital_workspace():return
            s.cid=focus(s.project,self.active_step['id'],circuit=True)
            s.mode_combo.setCurrentIndex(0);s.refresh(True);self.show();self.raise_()
            return
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
            starter, project_id = self.lesson['starter'],s.project['id']
            dialog=MillerDialog if starter=='miller-study' else AhujaDialog
            from .student_loop_study import save
            def capture(values):
                self.require_idle()
                if s.project['id']!=project_id:
                    raise ValueError('Open the matching lesson project before saving the comparison.')
                s.commit(lambda project:save(project,starter,values),'Save loop comparison')
            self.frequency_dialog=dialog(s,capture if self.active_step['id']=='loop-evidence' else None)
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

    def open_vga(self):
        self.rtl()
        self.studio.digital_window().show_vga()

    def mixed_signal_setup(self):
        from .mixed_signal_ui import show
        self.require_project();dialog=show(self.studio)
        dialog.tabs.setCurrentIndex(0)
        return dialog

    def run(self):
        self.flush();self.require_idle();s=self.studio
        if self.lesson.get('standard_cell'):
            from .student_standard_cells import prepare
            job=prepare(s.project,self.lesson,self.hub.tools())
        elif self.lesson.get('bench_project'):
            from .student_testbench import prepare
            job=prepare(s.project,self.lesson,self.bench_workflow.currentData(),self.hub.tools(),self.active_step['id'])
        elif self.lesson.get('signal_lab'):
            from .student_signal_labs import prepare
            job=prepare(s.project,self.lesson,self.active_step['id'],self.hub.tools())
        elif self.lesson.get('layout_lab'):
            from .student_layout_labs import prepare
            job=prepare(s.project,self.lesson,self.active_step['id'],self.hub.tools())
        elif self.lesson['starter']=='layout-decisions':
            from .student_layout_decisions import prepare
            job=prepare(s.project,self.active_step['id'])
            job['student_layout_step']=self.active_step['id']
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

    def step_run_rows(self,rows):
        if not self.active_step or self.active_step['kind']=='quiz':return []
        return [r for r in rows if r['job'].get('student_lesson')==self.lesson['id'] and (
            self.active_step['kind']=='reflection' or lesson_run_step(r['job']) in (None,self.active_step['id']))]

    def require_idle(self):
        if any(r['state'] in ('Queued','Running','Stopping') for r in self.lesson_rows()):
            raise ValueError('This lesson project already has an active run. Wait for it to finish or cancel it first.')

    def update_run_state(self):
        if not self.lesson:return
        record=self.hub.portfolio.workspace(self.lesson)
        bound=bool(record and record['project_id']==self.studio.project['id'])
        rows=self.lesson_rows();active=[r for r in rows if r['state'] in ('Queued','Running','Stopping')]
        from .digital_design import config
        project=self.studio.project
        is_check=bool(self.active_step and self.active_step['kind']=='check')
        can_run=bound and not active
        bench_path=bool(self.lesson.get('bench_project'))
        show_workflow=bench_path and bool(self.active_step) and self.active_step['kind']!='quiz'
        self.bench_workflow_label.setVisible(show_workflow)
        self.bench_workflow.setVisible(show_workflow)
        self.bench_workflow.setEnabled(can_run)
        starter=self.lesson['starter']
        kind=self.lesson.get('analog_project')
        self.analog_action.hide()
        self.layout_action.hide()
        self.signal_action.hide()
        bandgap=self.lesson.get('bandgap')
        lab=self.lesson.get('layout_lab')
        signal=self.lesson.get('signal_lab')
        mixed=project.get('mixed_signal',{}) if bound else {}
        rtl=bool(bound and config(project,mixed.get('digital_cell',project['top'])))
        self.controls['Open RTL'].setVisible(rtl)
        self.controls['Open RTL'].setEnabled(rtl)
        self.controls['Open VGA Playground'].setVisible(bool(self.lesson.get('vga_lesson')))
        self.controls['Open VGA Playground'].setEnabled(rtl)
        self.controls['Open workspace'].setVisible(not rtl or bool(mixed))
        self.controls['Mixed-signal experiment…'].setVisible(bool(mixed))
        self.controls['Mixed-signal experiment…'].setEnabled(bool(mixed))
        stage=self.lesson.get('inverter_stage')
        if stage:
            check=self.active_step.get('rule',{}).get('check') if is_check else None
            buttons=('Open inverter', 'Build layout' if is_check and stage=='layout' else None,
                     'Add DRC fault' if check=='drc-failure' else None,
                     'Add LVS fault' if check=='lvs-failure' else None,
                     'Repair lesson fault' if check in ('drc','lvs') else None)
            for control in self.inverter_buttons:
                control.setVisible(control.text() in buttons)
                control.setEnabled(bound and (control.text()=='Open inverter' or not active))
        run_button=self.controls['Run lesson']
        self.controls['Run lesson'].setText('Run lesson')
        if self.lesson.get('standard_cell'):
            step=self.active_step['id'] if self.active_step else None
            if self.lesson['standard_cell']=='abutment':
                run_button.hide()
                if step=='place':
                    self.analog_action.setText('Align cell row…')
                    self.analog_action.setEnabled(can_run)
                    self.analog_action.show()
                return
            run_button.setVisible(step=='verify')
            if step=='verify' and self.lesson.get('goal'):
                self.analog_action.setText('Revise design…')
                self.analog_action.setEnabled(can_run)
                self.analog_action.show()
            if step in ('place','route'):
                cell=next((c for c in project['cells'] if c['id']==project.get('student_standard_cell',{}).get('cell')),None)
                if step=='place':
                    sized=bool(self.lesson.get('goal'))
                    self.analog_action.setText(('Revise design…' if cell and cell['shapes'] else 'Size and place…')
                                              if sized else 'Place cell rows')
                    self.analog_action.setEnabled(can_run and bool(cell) and (sized or not cell['shapes']))
                    self.analog_action.show()
                elif cell and cell.get('student_cell_layout'):
                    self.analog_action.setText('Add route…')
                    self.analog_action.setEnabled(can_run)
                    self.analog_action.show()
        elif bench_path:
            run_button.setVisible(is_check)
            from .student_testbench import checkpoint_key, course
            reuse = is_check and course()[checkpoint_key(self.lesson,self.active_step['id'])].get('reuse')
            if reuse:
                run_button.setText('Compare reference and variant')
            prefix = 'Edit reference ' if reuse else 'Edit '
            self.analog_action.setText(prefix+('SPICE program…' if self.bench_workflow.currentData()=='spice' else 'testbench…'))
            self.analog_action.setEnabled(can_run);self.analog_action.setVisible(is_check)
        elif kind and self.active_step:
            from .student_analog import run_names
            step=self.active_step['id'];names=run_names(kind,step)
            self.controls['Run lesson'].setVisible(bool(names))
            self.controls['Run lesson'].setText('Run post-layout checks' if step=='post-layout' else 'Run testbenches')
            if kind=='bias' and step=='corners':
                self.controls['Run lesson'].setText('Run nine PVT cases')
            from .process_adapters import capabilities
            needs_full_pdk=step=='post-layout' and not capabilities(self.studio.project['pdk'])['external_verification']
            if kind=='interview':
                self.controls['Run lesson'].setText('Compare interconnect' if step.startswith('route-') else 'Run experiment')
                self.analog_action.setText('Open circuit')
                self.analog_action.setEnabled(bound and not active);self.analog_action.setVisible(bool(names))
            elif kind=='bandgap':
                names={'accuracy':'Run temperature sweep','startup':'Run startup cases','post-layout':'Run extracted comparison'}
                if step in names:self.controls['Run lesson'].setText(names[step])
                if step=='layout':
                    from .student_bandgap_lab import core_cell
                    existing=bound and core_cell(self.studio.project)['shapes']
                    self.analog_action.setText('Regenerate layout…' if existing else 'Generate layout')
                elif step in ('accuracy','startup'):self.analog_action.setText('Open bandgap circuit')
                else:self.analog_action.setText('Open temperature model…')
                self.analog_action.setEnabled(bound and not active);self.analog_action.setVisible(is_check)
            elif step in ('fixture','bias','layout','bias-layout','schematic') or needs_full_pdk:
                self.analog_action.setText({'layout':'Generate core layout…','bias-layout':'Generate bias mirror layout…',
                                            'post-layout':'Migrate PDK revision…'}.get(step,'Edit testbench…'))
                self.analog_action.setEnabled(bound and not active);self.analog_action.show()
        elif signal and self.active_step:
            from .student_signal_labs import run_name
            from .student_signal_ui import ACTIONS
            step=self.active_step['id'];title=run_name(signal,step)
            self.controls['Run lesson'].setVisible(bool(title));self.controls['Run lesson'].setText(title)
            if (signal,step) in ACTIONS:
                self.signal_action.setText(ACTIONS[signal,step]+'…')
                self.signal_action.setEnabled(bound and not active);self.signal_action.show()
        elif lab and self.active_step:
            from .student_layout_labs import run_name
            from .student_layout_signoff_ui import ACTIONS
            step=self.active_step['id'];title=run_name(lab,step)
            self.controls['Run lesson'].setVisible(bool(title));self.controls['Run lesson'].setText(title)
            action={('fold','folded'):'Generate device layout',('lvs','swap'):'Edit input ports…',
                    ('eco','update'):'Review layout update…',('noise','space'):'Set clock spacing…'}.get((lab,step))
            if (lab,step) in ACTIONS:action=ACTIONS[lab,step]+'…'
            if bound and (lab,step)==('access','access') and missing_prerequisites(self.hub.portfolio.state,self.lesson,self.hub.data):
                action='Use compact practice layout'
            if action:
                self.layout_action.setText(action);self.layout_action.setEnabled(bound and not active);self.layout_action.show()
        elif starter=='layout-decisions' and self.active_step:
            from .student_layout_decisions import EXTRACTION_STEPS
            run_step=self.active_step['id'] in EXTRACTION_STEPS
            self.controls['Run lesson'].setVisible(run_step)
            self.controls['Run lesson'].setText('Compare route RC')
        elif starter in ('ahuja-study','miller-study') or bandgap:
            self.controls['Run lesson'].hide()
            self.analog_action.setText('Open temperature study…' if bandgap else 'Open loop comparison…')
            self.analog_action.setEnabled(bound)
            self.analog_action.show()
        else:
            run_types={'digital','sar','capstone','lc_bode','result','current','difference','device_metrics'}
            has_run=any(s.get('rule',{}).get('type') in run_types for s in self.lesson['steps'])
            if stage:
                has_run=stage in ('dc','transient','drc','lvs') or (stage=='handoff' and is_check and self.active_step['id']=='measure')
            run_button.setVisible(is_check and has_run)
            if starter=='lc-bode':
                self.controls['Run lesson'].setText('Run AC sweep')
        can_run=can_run and not run_button.isHidden()
        run_button.setEnabled(can_run)
        campaign=is_check and self.active_step.get('rule',{}).get('type')=='campaign'
        self.qualify.setVisible(campaign);self.qualify.setEnabled(campaign and bound and not active)
        self.controls['Cancel lesson runs'].setEnabled(bool(active));self.controls['Cancel lesson runs'].setVisible(bool(active))
        result_rows=[r for r in self.step_run_rows(rows) if r.get('result')]
        self.controls['Results'].setVisible(bool(result_rows) or not run_button.isHidden() or campaign)
        self.controls['Results'].setEnabled(bound and bool(result_rows) and (kind!='interview' or not active))
        for name in ('Open workspace','Save work'):self.controls[name].setEnabled(bound)
        self.check_button.setEnabled(bound)
        self.run_progress.setVisible(bool(active))
        if active:
            progress=round(sum(r.get('progress',0) for r in active)/len(active))
            self.run_progress.setRange(0,100);self.run_progress.setValue(progress)
            status=' · '.join(f'{sum(r["state"]==state for r in active)} {state.lower()}' for state in ('Running','Queued','Stopping') if any(r['state']==state for r in active))
            self.run_status.setText(status+(f' · {progress}%' if progress else ''))
        elif not bound:self.run_status.setText('Resume this lesson from Student Hub to use its workspace.')
        elif visible_rows:=self.step_run_rows(rows):self.run_status.setText('Latest run: '+visible_rows[-1]['state'])
        else:self.run_status.setText('Ready to run.' if can_run or campaign else '')
        self.run_status.setVisible(bool(self.run_status.text()))

    def finished(self,row,result):
        if self.active_step and self.active_step['kind']=='check' and row in self.step_run_rows(self.lesson_rows()):
            feedback(self.feedback,row['name']+' · '+row['state']+'. '+('Open Results or check this step.' if result else row.get('log','')[-350:]),row['state']=='Failed')
        self.update_run_state()

    def results(self):
        self.require_project();s=self.studio
        rows=[r for r in self.step_run_rows(self.lesson_rows()) if r.get('result')]
        if not rows:raise ValueError('There is no saved result for this checkpoint yet.')
        if self.active_step['kind']=='reflection':
            titles={step['id']:step['title'] for step in self.lesson['steps']}
            stages=list(dict.fromkeys(lesson_run_step(r['job']) for r in rows))
            if len(stages)>1:
                names=[titles.get(stage,'Lesson runs') for stage in stages]
                name,ok=QInputDialog.getItem(self,'Review saved results','Checkpoint',names,len(names)-1,False)
                if not ok:return
                selected=stages[names.index(name)]
                rows=[r for r in rows if lesson_run_step(r['job'])==selected]
        latest=rows[-1]
        if latest['result'].get('student_cell_layout'):
            from .student_cell_layout_ui import CellResults
            self.cell_results=CellResults(s,latest['result'])
            self.cell_results.show()
            return self.cell_results
        if self.lesson.get('bench_project'):
            from .student_testbench_ui import BenchResults
            self.bench_result=BenchResults(s,rows,self.bench_workflow.currentData())
            self.bench_result.show()
            return self.bench_result
        if self.lesson.get('signal_lab'):
            from .student_signal_ui import SignalResults
            self.signal_results=SignalResults(s,latest);self.signal_results.show()
            return
        if self.lesson.get('layout_lab') and latest['result'].get('student_stream'):
            from .student_layout_signoff_ui import show_report
            self.layout_results=show_report(s,latest)
            return
        if self.lesson.get('layout_lab') and latest['result'].get('rc_comparison'):
            from .analog_run_ui import RunInspector
            self.layout_results=RunInspector(s,latest);self.layout_results.show()
            return
        if self.lesson['starter']=='lc-bode':
            from .student_frequency_ui import FilterDialog
            self.frequency_dialog=FilterDialog(s,latest['job']['project'],latest['result'])
            self.frequency_dialog.show()
            return
        if self.lesson.get('analog_project'):
            from .analog_run_ui import RunInspector
            step=lesson_run_step(latest['job'])
            by_bench={r['job']['student_analog']['bench']:r for r in rows if 'student_analog' in r['job'] and lesson_run_step(r['job'])==step}
            if not by_bench:raise ValueError('Run this step’s testbenches first.')
            if self.lesson['analog_project']=='interview':
                from .student_interview_ui import InterviewResults
                saved=list(by_bench.values())[-1]['job']['project']
                self.bias_inspector=InterviewResults(s,saved,step,rows)
                self.bias_inspector.show();return
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
