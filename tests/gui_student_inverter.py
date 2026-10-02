"""Exercise revision selection, durable work, native ngspice and layout actions."""
import json, os, sys, tempfile, time
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    from PySide6.QtCore import QSettings,QStandardPaths
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from icstudio.gui import Studio
    from icstudio.student_hub_ui import show
    from icstudio.student_hub import evaluate
    from icstudio.model import clone
    app=QApplication([]);app.setStyle('Fusion')
    if sys.platform=='win32' and app.platformName()=='offscreen':
        fonts=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'
        for name in ('segoeui.ttf','segoeuib.ttf','arial.ttf'):QFontDatabase.addApplicationFont(str(fonts/name))
    out=ROOT/'build/student-inverter-gui';out.mkdir(parents=True,exist_ok=True)
    profile=Path(tempfile.mkdtemp(prefix='profile-',dir=out));settings=QSettings(str(profile/'settings.ini'),QSettings.IniFormat)
    settings.setFallbacksEnabled(False)
    with patch('icstudio.gui.QSettings',return_value=settings),patch.object(QStandardPaths,'writableLocation',return_value=str(profile/'data')):
        w=Studio(recover=False)
    errors=[];w.error=errors.append;w.maybe_save=lambda:True;w.jobs_dir=profile/'runs';w.resize(1520,1040);w.show()
    from icstudio.spice_program import find_ngspice
    engine=find_ngspice(os.environ.get('ICSTUDIO_TEST_NGSPICE',''));assert engine,'Install native ngspice for this GUI test'
    w.settings.setValue('student/tools/ngspice',engine)
    # A full process package is optional; the bundled simulation tests always run.
    manifest=os.environ.get('ICSTUDIO_TEST_INVERTER_MANIFEST')
    if manifest:
        path=Path(manifest);m=json.loads(path.read_text());m['source_root']=str(path.parent)
        dest=w.pdk_registry.root/(m['id']+'@'+m['revision']);dest.mkdir();(dest/'package.json').write_text(json.dumps(m))
    h=show(w);g=h.guide;h.choose_path('inverter');assert h.lessons.count()==8
    assert h.process_panel.isVisible() and 'DRC/LVS' in h.process_status.text()
    w.resize(1180,900);QTest.qWait(80);h.grab().save(str(out/'student-inverter-hub.png'))
    saved={}
    for token,item in h.inverter_profiles.items():
        h.process_picker.setCurrentIndex(h.process_picker.findData(token));assert h.lessons.count()==8
        if not item['ready']:
            assert not h.start.isEnabled();assert 'OSDI' in h.process_status.text()
            assert 'Worked example' in h.details.toPlainText();continue
        key='i-'+token+'-dc';h.select_lesson(key);h.start_selected();original=w.project['id'];saved[token]=original
        assert g.inverter_actions.isVisible() and 'Worked example' in g.design_notes.toPlainText()
        if item['technology'].get('simulation',{}).get('requires_osdi') and not os.environ.get('ICSTUDIO_TEST_MANAGED'):
            from icstudio.student_inverter import prepare
            from icstudio import digital_runtime
            with patch.object(digital_runtime,'manifest',return_value=None):
                try:prepare(w.project,g.lesson)
                except ValueError as exc:assert 'included physical tools' in str(exc)
                else:raise AssertionError('Missing runtime accepted')
            g.save_work();continue
        g.run();deadline=time.monotonic()+300
        while w.run_manager.busy and time.monotonic()<deadline:QTest.qWait(25)
        assert not w.run_manager.busy and w.run_manager.rows[-1]['state']=='Complete',w.run_manager.rows[-1]
        result=evaluate(g.lesson['steps'][2],g.lesson,w.project,w.run_manager.rows)
        assert result['inverter_measurements']['switching_threshold']>0
        g.results();g.save_work()
        h.select_lesson('i-'+token+'-transient');h.start_selected();assert w.project['id']==original
        from icstudio.process_adapters import capabilities
        if 'inverter' in capabilities(item['technology'])['native_layout'] and capabilities(item['technology'])['external_verification']:
            h.select_lesson('i-'+token+'-layout');h.start_selected();g.build_inverter()
            evaluate(g.lesson['steps'][2],g.lesson,w.project)
            before=clone(w.project['cells']);g.inverter_edit('drc');assert w.project['cells']!=before
            g.inverter_edit('repair');assert w.project['cells']==before
            h.select_lesson('i-'+token+'-drc');h.start_selected();g.open_inverter();g.lesson_tabs.setCurrentIndex(0)
            if os.environ.get('ICSTUDIO_TEST_MANAGED'):
                g.run();deadline=time.monotonic()+600
                while w.run_manager.busy and time.monotonic()<deadline:QTest.qWait(25)
                assert not w.run_manager.busy and w.run_manager.rows[-1]['state']=='Complete',w.run_manager.rows[-1]
                evaluate(g.lesson['steps'][2],g.lesson,w.project,w.run_manager.rows)
                assert w.run_manager.rows[-1]['result']['silicon_report']['status']=='passed'
            g.setFloating(True);g.resize(550,950);QTest.qWait(60)
            w.grab().save(str(out/'student-inverter-layout.png'));g.grab().save(str(out/'student-drc-guide.png'))
            g.save_work()
    assert len(set(saved.values()))==len(saved)
    h.reload_pdks()
    for token,project_id in saved.items():
        h.select_lesson('i-'+token+'-process');h.start_selected();assert w.project['id']==project_id
    show(w);w.resize(1180,900);QTest.qWait(60);h.grab().save(str(out/'student-inverter-hub.png'))
    w.resize(780,980);h.set_text_scale(200);QTest.qWait(50)
    assert h.scroll.horizontalScrollBar().maximum()==0
    assert not errors,errors
    report=dict(status='PASS',qt_platform=app.platformName(),processes=len(saved),checks=[
        'eight stages filtered by PDK revision','IHP runtime setup is explicit','real ngspice through GUI queue',
        'measurement and waveform results','distinct durable per-process projects','reload and resume','200 percent text reflow'])
    report['checks'].append('native GF180 C/D and IHP layout, DRC fault injection and repair through GUI')
    if os.environ.get('ICSTUDIO_TEST_MANAGED'):report['checks'].append('IHP managed simulation and GF180 C/D + IHP physical runs through the GUI queue')
    (out/'checks.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
    w.close();app.processEvents()


if __name__=='__main__':main()
