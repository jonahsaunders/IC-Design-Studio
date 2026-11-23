"""Student Hub second-pass acceptance, including recoverable storage failures.

No external engines required: runs the real teaching solver through RunManager.
Retains screenshots and checks on each OS used by desktop CI.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=ROOT/'build/student-usability')
    args = parser.parse_args()
    out = args.out.resolve();out.mkdir(parents=True, exist_ok=True)
    # Every invocation gets a fresh profile; repeated acceptance cannot borrow credit.
    import tempfile
    profile = Path(tempfile.mkdtemp(prefix='profile-', dir=out))
    from PySide6.QtCore import QSettings, QStandardPaths, Qt
    from PySide6.QtGui import QCloseEvent, QFontDatabase, QFontMetrics
    from PySide6.QtWidgets import QApplication, QPushButton, QFileDialog, QStyle, QStyleOptionFrame
    from PySide6.QtTest import QTest
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(profile))
    QStandardPaths.writableLocation = staticmethod(lambda kind: str(profile/str(kind.value)))
    from icstudio.gui import Studio
    from icstudio.student_hub_ui import show
    from icstudio.student_hub import Portfolio, complete
    from icstudio.student_projects import create
    from icstudio.model import digest, save_project
    from icstudio.ui_style import palette
    app = QApplication([]);app.setStyle('Fusion')
    # Qt's Windows offscreen plugin does not enumerate the system font directory.
    # Without loading real fonts, screenshots consist of square missing glyphs
    # and layout measurements are invalid (see the other desktop GUI probes).
    if sys.platform=='win32' and app.platformName()=='offscreen':
        fonts=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'
        for name in ('segoeui.ttf','segoeuib.ttf','arial.ttf'):
            assert QFontDatabase.addApplicationFont(str(fonts/name))>=0, f'Could not load {name}'
    errors = []
    old_hook=sys.excepthook
    def exception(kind,value,tb):errors.append(str(value));old_hook(kind,value,tb)
    sys.excepthook=exception
    settings=QSettings(str(profile/'settings.ini'),QSettings.IniFormat)
    settings.setFallbacksEnabled(False)
    with patch('icstudio.gui.QSettings',return_value=settings):
        w = Studio(recover=False)
    w.resize(1440, 1000);w.maybe_save = lambda: True
    w.error = errors.append;w.jobs_dir = out/'runs';w.show()
    h = show(w);g = h.guide
    assert QFontMetrics(h.font()).inFontUcs4(ord('A')), 'The GUI must render real glyphs'
    checks = []

    def checked(name):
        assert not errors, errors
        checks.append(name)

    for key in [p['id'] for p in h.data['paths']]+['capstone']:
        h.choose_path(key)
        assert h.lessons.count() == sum(l['path']==key and (key!='inverter' or l['inverter_profile']==h.process_picker.currentData()) for l in h.data['lessons'])
        assert h.path_picker.currentData() == key
        assert h.path_list.currentItem().data(Qt.UserRole) == key
    h.select_lesson('f-first')
    # Return searches; only explicit lesson activation starts a project.
    before = digest(w.project)
    h.search.setFocus();QTest.keyClick(h.search, Qt.Key_Return);app.processEvents()
    assert digest(w.project) == before and g.lesson is None
    assert h.trail.rows['f-first'].hasFocus()
    h.mode_buttons['list'].click()
    h.search.setFocus();QTest.keyClick(h.search, Qt.Key_Return);app.processEvents()
    assert h.lessons.hasFocus()
    assert not any(b.autoDefault() or b.isDefault() for b in h.findChildren(QPushButton))
    h.search.setText('no-such-lesson');assert not h.start.isEnabled()
    assert not h.progress_text.text()
    h.search.clear();assert h.start.isEnabled()
    checked('Keyboard search cannot open a project; empty search disables the action')

    h.search.setText('  Advanced   project  ')
    assert h.lessons.count() and h.path_id=='foundations'
    assert all(h.by_id[h.lessons.item(i).data(Qt.UserRole)]['path']=='capstone' for i in range(h.lessons.count()))
    assert 'Advanced project' in h.lessons.currentItem().text()
    assert 'matching' in h.heading.text()
    h.search.clear()
    assert all(h.by_id[h.lessons.item(i).data(Qt.UserRole)]['path']=='foundations' for i in range(h.lessons.count()))
    checked('Search finds lessons across paths and clearing it restores the active path')

    # Both palettes and all scales fit the minimum window, with vertical scrolling.
    h.select_lesson('f-connect')
    contrast = {}
    def luminance(color):
        values=[int(color[i:i+2],16)/255 for i in (1,3,5)]
        values=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in values]
        return sum(a*b for a,b in zip(values,(.2126,.7152,.0722)))
    for dark in (False,True):
        w.dark=dark;w.apply_theme();p=palette(dark)
        assert p['accent'] in h.details.toHtml().lower()
        for fg,bg in [('text','panel'),('muted','panel'),('accent','panel'),('accent','tint')]:
            a,b=sorted((luminance(p[fg]),luminance(p[bg])))
            ratio=(b+.05)/(a+.05);assert ratio>=4.5,(dark,fg,bg,ratio)
            contrast[f'{"dark" if dark else "light"}-{fg}-{bg}']=round(ratio,2)
        for scale in (100,125,150,200):
            h.set_text_scale(scale);w.resize(720,680);QTest.qWait(40)
            assert h.width()<=720 and h.height()<=680,(w.size(),h.size(),w.minimumSizeHint())
            assert h.scroll.horizontalScrollBar().maximum()==0
            assert h.path_picker.isVisible() and h.split.orientation()==Qt.Vertical
            frame=QStyleOptionFrame();frame.initFrom(h.search)
            contents=h.search.style().subElementRect(QStyle.SE_LineEditContents,frame,h.search)
            assert contents.height()>=QFontMetrics(h.search.font()).height(),(dark,scale,contents)
            h.scroll.ensureWidgetVisible(h.start);app.processEvents()
            assert h.start.isVisible()
            h.scroll.verticalScrollBar().setValue(0)
            if scale in (100,200):h.grab().save(str(out/f'{"dark" if dark else "light"}-{scale}.png'))
    h.set_text_scale(100);w.resize(1180,860);QTest.qWait(50)
    assert h.path_list.isVisible() and not h.path_picker.isVisible()
    h.grab().save(str(out/'hub-wide.png'))
    checked('Light/dark contrast and live appearance; compact layout at 100–200% text')

    h.select_lesson('f-first');h.start_selected();assert g.lesson['id']=='f-first'
    g.answer.setCurrentIndex(2);g.check()
    assert g.steps.currentIndex()==0 and g.next_button.isVisible()
    assert 'passed' in g.feedback.text();g.advance();assert g.steps.currentIndex()==1
    checked('Checkpoint result remains visible until explicit Next step')

    g.run();rows=len(w.run_manager.rows)
    assert not g.controls['Run lesson'].isEnabled()
    g.call(g.run);assert len(w.run_manager.rows)==rows and 'active run' in g.feedback.text()
    deadline=time.monotonic()+45
    while w.run_manager.busy and time.monotonic()<deadline:QTest.qWait(20)
    assert not w.run_manager.busy and w.run_manager.rows[-1]['state']=='Complete'
    assert g.controls['Run lesson'].isEnabled() and g.controls['Results'].isEnabled()
    assert not g.controls['Cancel lesson runs'].isEnabled()
    checked('Real solver lifecycle, duplicate submission guard and results availability')

    g.steps.setCurrentIndex(3);draft='My reflection must survive an immediate close and a failed autosave.'
    g.notes.setPlainText(draft)
    with patch.object(Portfolio,'save_note',side_effect=OSError('Disk full')):
        g.steps.setCurrentIndex(1)
        assert g.steps.currentIndex()==3 and g.active_step['id']=='explain'
        assert g.notes.toPlainText()==draft and g.note_dirty
        show(w);h.reject();assert h.isVisible()
        event=QCloseEvent();w.closeEvent(event);assert not event.isAccepted()
        assert len(errors)==1 and 'reflection' in errors.pop()
    g.save_note();assert not g.note_dirty
    assert Portfolio(h.portfolio.root).state['lessons']['f-first']['notes']['explain']==draft
    checked('Disk-full preserves selected step and draft; Escape and app close remain recoverable')

    # Concurrent unrelated edits may be reloaded without discarding the local draft.
    other=Portfolio(h.portfolio.root)
    other.save_note(h.by_id['f-connect'],h.by_id['f-connect']['steps'][-1],'Other window draft')
    g.notes.setPlainText(draft+' More detail.')
    h.reload_progress();assert not g.note_dirty
    state=Portfolio(h.portfolio.root).state
    assert state['lessons']['f-connect']['notes']
    assert state['lessons']['f-first']['notes']['explain'].endswith('More detail.')
    checked('Reload resolves unrelated progress conflict without dropping either draft')

    other=Portfolio(h.portfolio.root);other.save_note(g.lesson,g.active_step,'Saved elsewhere')
    g.notes.setPlainText('My concurrent draft')
    with patch.object(h,'resolve_reflection',return_value=None):assert h.reload_progress() is False
    assert g.note_dirty and g.notes.toPlainText()=='My concurrent draft'
    with patch.object(h,'resolve_reflection',return_value='local'):h.reload_progress()
    assert Portfolio(h.portfolio.root).state['lessons']['f-first']['notes']['explain']=='My concurrent draft'
    other=Portfolio(h.portfolio.root);other.save_note(g.lesson,g.active_step,'Saved version chosen')
    g.notes.setPlainText('Another draft')
    with patch.object(h,'resolve_reflection',return_value='saved'):h.reload_progress()
    assert not g.note_dirty and g.notes.toPlainText()=='Saved version chosen'
    checked('Conflicting reflection has explicit keep, load and cancel recovery paths')

    # A moved project can be relinked, but never to another identity.
    lesson=g.lesson;original=h.portfolio.workspace(lesson)['path']
    moved=out/'moved-lesson.icproj';save_project(w.project,moved)
    wrong=out/'different.icproj';save_project(create('divider'),wrong)
    try:h.relink(lesson,wrong)
    except ValueError:pass
    else:raise AssertionError('Unrelated project was linked')
    assert h.portfolio.workspace(lesson)['path']==original
    h.relink(lesson,moved);assert h.portfolio.workspace(lesson)['path']==str(moved)
    checked('Moved project recovery preserves identity and existing progress')

    # Export must include pending current-project edits and stop on save cancellation.
    w.commit(lambda p:p.update(name='Current edited lesson'),'Rename lesson')
    exported=out/'portfolio.json'
    with patch.object(QFileDialog,'getSaveFileName',return_value=(str(exported),'')):
        h.export()
    data=json.loads(exported.read_text())
    assert 'Current edited lesson' in json.dumps(data)
    with patch.object(w,'save',return_value=False),patch.object(QFileDialog,'getSaveFileName') as choose:
        h.export();choose.assert_not_called()
    checked('Export saves current work and respects cancellation')

    # Start both projects from search and visit the stage-specific controls.
    for query, key in (('photodiode TIA', 'project-tia'), ('two-stage op amp', 'project-opamp')):
        h.search.setText(query);assert h.selected()['id']==key
        h.start_selected();assert g.lesson['id']==key
        assert g.steps.count()==9 and not g.controls['Run lesson'].isVisible()
        g.steps.setCurrentIndex(1)
        assert g.analog_action.isVisible() and 'Edit testbench' in g.analog_action.text()
        g.workspace();assert w.cell['name'] in ('tia_ac_fixture','opamp_ac_fixture')
        g.steps.setCurrentIndex(3);g.workspace()
        assert w.cell['name']=='reference_compliance_fixture'
        assert g.controls['Run lesson'].text()=='Run testbenches'
        g.steps.setCurrentIndex(5)
        assert g.analog_action.text()=='Generate core layout…'
        g.steps.setCurrentIndex(6);g.workspace()
        assert w.cell['name']=='resistor_current_reference' and g.analog_action.text()=='Generate bias mirror layout…'
        g.steps.setCurrentIndex(7);g.workspace()
        assert w.cell['name']=='two_stage_opamp' and w.mode_combo.currentIndex()==1
        assert g.controls['Run lesson'].text()=='Run post-layout checks'
    checked('Search opens both analog projects and their stage actions target the correct fixture and core')

    h.search.setText('LC filters');assert h.selected()['id']=='a-lc-bode'
    h.start_selected();g.steps.setCurrentIndex(2);g.run()
    deadline=time.monotonic()+30
    while w.run_manager.busy and time.monotonic()<deadline:QTest.qWait(20)
    assert not w.run_manager.busy and g.controls['Results'].isEnabled()
    g.results();plot=g.frequency_dialog
    assert plot.gain.result['plot_unit']=='dB' and plot.phase.result['plot_unit']=='°'
    plot.output.setCurrentIndex(plot.output.findData('bs'));QTest.qWait(30)
    assert plot.values.item(2,3).text()=='Undefined'
    ticks=plot.phase.result['frequency_ticks']
    assert len(ticks)==5 and plot.phase.result['trace_gaps']
    QTest.mouseClick(plot.phase,Qt.LeftButton,pos=plot.phase.screen(ticks[2],0).toPoint())
    assert 'undefined' in plot.cursor.text()
    plot.grab().save(str(out/'lc-bode-notch.png'));plot.close()
    checked('Real AC lesson runs open magnitude, phase and hand-sketch comparison; the notch phase is undefined')

    h.search.setText('Why layout choices');assert h.selected()['id']=='l-layout-decisions'
    h.start_selected();g.steps.setCurrentIndex(1);g.workspace()
    assert w.cell['name']=='via_coupon'
    g.steps.setCurrentIndex(4);g.workspace();assert w.cell['name']=='routing_bandwidth'
    g.run()
    deadline=time.monotonic()+30
    while w.run_manager.busy and time.monotonic()<deadline:QTest.qWait(20)
    assert not w.run_manager.busy and g.controls['Results'].isEnabled()
    g.results()
    assert w.results_tabs.currentIndex()==w.rc_tab and 'resistors' in w.rc_note.text()
    checked('Layout lesson selects the stage coupon and opens a measured RC comparison')

    h.search.setText('Ahuja compensation');assert h.selected()['id']=='project-ahuja'
    h.start_selected();assert w.cell['name']=='two_stage_opamp'
    g.analog_action.click();study=g.frequency_dialog
    assert study.values.item(1,3).text()=='Meets target'
    assert study.gain.result['y_reference']==0 and study.phase.result['y_reference']==-120
    study.buffer.setValue(10);assert study.values.item(2,3).text()=='Below target'
    QTest.qWait(30);study.grab().save(str(out/'ahuja-loop-study.png'));study.close()
    checked('Ahuja lesson changes the modeled loop and phase margin through keyboard-accessible controls')

    h.search.setText('nulling resistor');assert h.selected()['id']=='project-miller'
    h.start_selected();assert w.cell['name']=='two_stage_opamp' and g.steps.count()==6
    g.analog_action.click();study=g.frequency_dialog
    assert study.values.item(2,3).text()=='At infinity' and '202 pF' in study.legend.text()
    study.resistor.setValue(500);assert study.values.item(2,3).text().startswith('Right half plane')
    study.resistor.setValue(2000);assert study.values.item(2,3).text().startswith('Left half plane')
    study.capacitor.setValue(4);assert float(study.values.item(2,2).text())>60
    QTest.qWait(30);study.grab().save(str(out/'miller-loop-study.png'));study.close()
    checked('Miller lesson shows the zero crossing infinity and recomputes margin as Cc changes')

    h.select_lesson('project-bias-reference');h.start_selected()
    assert w.cell['name']=='simple_bias_fixture'
    bias_project=w.project['id']
    g.steps.setCurrentIndex(2)
    assert g.controls['Run lesson'].text()=='Run testbenches'
    h.select_lesson('project-cascode');h.start_selected()
    assert w.project['id']==bias_project and w.cell['name']=='cascode_mirror'
    g.steps.setCurrentIndex(2);g.workspace()
    assert w.cell['name']=='cascode_bias_fixture' and g.controls['Run lesson'].text()=='Run nine PVT cases'
    checked('Bias and cascode lessons share the trimmed project and open the correct fixtures and corner study')

    for topology in ('widlar','brokaw','kuijk','banba'):
        h.select_lesson('project-bandgap-'+topology);h.start_selected()
        assert w.cell['name']==('banba_layout' if topology=='banba' else topology+'_core')
        assert g.analog_action.text()=='Open temperature model…'
        g.analog_action.click();study=g.frequency_dialog
        assert study.kind==topology and study.volts.result['plot_unit']=='V' and study.drift.result['plot_unit']=='mV'
        assert study.values.rowCount()==4
        QTest.qWait(30)
        assert study.values.verticalScrollBar().maximum()==0 and study.values.horizontalScrollBar().maximum()==0
        previous=float(study.values.item(1,3).text())
        if topology=='banba':
            study.extra.setValue(.4)
            assert float(study.values.item(1,3).text())<previous
        elif topology=='kuijk':
            study.extra.setValue(2)
            assert float(study.values.item(1,3).text())>previous
        else:
            study.ratio.setValue(16)
            assert float(study.values.item(1,3).text())>previous
        QTest.qWait(30);study.grab().save(str(out/f'bandgap-{topology}.png'));study.close()
        for stage,action in (('accuracy','Run temperature sweep'), ('startup','Run startup cases'),
                             ('post-layout','Run extracted comparison')):
            index=next(i for i,step in enumerate(g.lesson['steps']) if step['id']==stage)
            g.steps.setCurrentIndex(index);g.workspace()
            assert g.controls['Run lesson'].text()==action
            if stage=='accuracy':
                assert g.analog_action.text()=='Open bandgap circuit'
                g.analog_action.click()
                assert w.cell['name']==('banba_layout' if topology=='banba' else topology+'_core')
        index=next(i for i,step in enumerate(g.lesson['steps']) if step['id']=='layout')
        g.steps.setCurrentIndex(index);g.workspace()
        assert w.mode_combo.currentIndex()==1
        if topology!='banba':
            assert g.analog_action.text()=='Generate layout'
            g.analog_action.click()
        assert w.cell['layout_pins'] and g.analog_action.text()=='Regenerate layout…'
    checked('Four transistor-level bandgap projects open independent predictions and run, layout, and extracted controls')

    for lesson in (item for item in h.data['lessons'] if item.get('analog_project')=='interview'):
        h.select_lesson(lesson['id']);h.start_selected()
        assert w.project['student_interview']==lesson['id'].removeprefix('interview-')
        g.steps.setCurrentIndex(1)
        assert g.controls['Run lesson'].isEnabled()
        g.analog_action.click()
        assert w.mode_combo.currentIndex()==0
    assert g.lesson['id']=='interview-post-layout-debug'
    g.steps.setCurrentIndex(0)
    g.answer.setCurrentIndex(g.answer.findData(g.active_step['answer']));g.check()
    g.steps.setCurrentIndex(1)
    g.workspace()
    assert w.mode_combo.currentIndex()==1 and g.controls['Run lesson'].text()=='Compare interconnect'
    g.run();deadline=time.monotonic()+30
    while w.run_manager.busy and time.monotonic()<deadline:QTest.qWait(20)
    assert not w.run_manager.busy and g.controls['Results'].isEnabled()
    g.results();study=g.bias_inspector
    assert study.readings.rowCount()==4 and study.plot.compare is not None
    assert 'Dashed line is schematic' in study.detail.text()
    study.grab().save(str(out/'interview-extracted-settling.png'));study.close()
    g.check()
    assert 'Comparison recorded' in g.feedback.text()
    checked('All interview labs open editable circuits and the settling lesson runs and compares actual extracted waveforms')

    # Second pass: project switches disable actions immediately and cannot misroute
    # cancellation or completed-run feedback to another project.
    w.set_project(create('divider'));assert not g.check_button.isEnabled()
    assert not g.controls['Run lesson'].isEnabled()
    h.select_lesson('f-first');h.start_selected();assert g.check_button.isEnabled()
    g.steps.setCurrentIndex(3);g.notes.setPlainText(draft+' Closing now.')
    g.setFloating(True);g.resize(420,850);QTest.qWait(40)
    g.grab().save(str(out/'guide-reflection.png'))
    # A wider font must reflow even when the saved text-size preference is 100%.
    g.setStyleSheet(g.styleSheet()+'\nQPushButton {font-size:24px;}')
    g.resize(360,700);QTest.qWait(40)
    assert g.scroll.horizontalScrollBar().maximum()==0
    assert g.controls['Engine setup'].y()>g.controls['Save work'].y()
    h.apply_theme()
    for scale in (100,200):
        h.set_text_scale(scale);g.resize(420,700);QTest.qWait(40)
        g.grab().save(str(out/f'guide-{scale}.png'))
        assert g.scroll.horizontalScrollBar().maximum()==0, (scale,g.scroll.widget().minimumSizeHint().width(),g.scroll.viewport().width())
        g.scroll.ensureWidgetVisible(g.check_button);app.processEvents()
        g.grab().save(str(out/f'guide-{scale}.png'))
    event=QCloseEvent();w.closeEvent(event);assert event.isAccepted()
    assert Portfolio(h.portfolio.root).state['lessons']['f-first']['notes']['explain'].endswith('Closing now.')
    checked('Project switching, metric-based action reflow and immediate app close preserve usability and the last keystroke')
    h.close();g.close();w.close();app.processEvents()
    report={'status':'PASS','platform':sys.platform,'qt_platform':app.platformName(),
            'checks':checks,'contrast_ratios':contrast,'native_macos_voiceover_tested':False}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
