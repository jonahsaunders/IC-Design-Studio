"""Real menu regressions: zoom, digital switching, export drafts and IHP routing."""
import argparse
import json
import os
from pathlib import Path
import sys
import traceback
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=ROOT/'build/audit-regressions')
    out=parser.parse_args().out.resolve();out.mkdir(parents=True,exist_ok=True)
    os.environ['XDG_CONFIG_HOME']=str(out/'config');os.environ['XDG_DATA_HOME']=str(out/'data')
    from PySide6.QtWidgets import QApplication,QFileDialog,QPushButton,QPlainTextEdit,QLabel
    from PySide6.QtCore import QPointF
    from PySide6.QtTest import QTest
    from icstudio.gui import Studio
    from icstudio.model import example,digest,clone
    from icstudio.layout import rect
    from icstudio.interchange import import_layout
    from icstudio.student_inverter import profile,create
    from tests.test_student_physical import technology
    app=QApplication([]);w=Studio(recover=False);w.maybe_save=lambda:True;w.show()
    errors=[];w.error=errors.append
    sys.excepthook=lambda t,v,tb:(errors.append(str(v)),traceback.print_exception(t,v,tb))
    checks=[]

    for mode,canvas in [('schematic',w.schematic),('layout',w.layout)]:
        w.current_mode=mode;canvas.auto_fit=False;canvas.scale=.71;canvas.offset=QPointF(17.25,32.5)
        center=QPointF(canvas.rect().center());before=canvas.model(center)
        for name in ('Zoom in','Zoom out'):
            action=next(a for _,a in w._commands if a.text()==name)
            action.trigger()
            assert (canvas.model(center)-before).manhattanLength()<1e-8
        assert abs(canvas.scale-.71)<1e-10 and not errors,errors
    checks.append('Both zoom menu commands preserve the model point at the canvas center')

    for new in (w.new_digital_counter,w.new_digital_uart,w.new_digital_apb,w.new_digital_counter):
        w.set_project(example());new();QTest.qWait(40)
    w.set_project(example());QTest.qWait(40)
    assert w.centralWidget() is not None and w._digital_window is None
    checks.append('Repeated digital example switches restore circuit panels without deleted Qt objects')

    w.select([w.cell['devices'][1]['id']]);w.form_fields['Value'].setText('22k')
    spice=out/'pending.cir'
    with patch.object(QFileDialog,'getSaveFileName',return_value=(str(spice),'')):w.export_spice()
    assert '22000' in spice.read_text() and w.cell['devices'][1]['value']=='22k'
    w.add_shape(rect('metal1',0,0,1000,1000));w.mode_combo.setCurrentIndex(1)
    w.select([w.cell['shapes'][0]['id']],'layout');w.form_fields['Width'].setText('2.5')
    layout=out/'pending.gds'
    with patch.object(QFileDialog,'getSaveFileName',return_value=(str(layout),'')):w.export_gds()
    exported,_=import_layout(layout);assert exported['cells'][0]['shapes'][0]['points'][1][0]==2500
    w.select([w.cell['shapes'][0]['id']],'layout');w.form_fields['Width'].setText('invalid')
    with patch.object(QFileDialog,'getSaveFileName',side_effect=AssertionError('Invalid edits must stop export')):w.export_gds()
    assert w._inspector_dirty
    w.build_inspector();checks.append('SPICE/GDS exports include pending edits and reject invalid drafts')

    p=create(profile(technology('ihp-sg13g2')));w.set_project(p)
    def managed(job):job['settings'].update(managed_osdi='ihp-sg13g2',physical_runtime={'kind':'linux'})
    with patch('icstudio.physical_backend.prepare_simulation',side_effect=managed) as backend:
        job=w.prepare_simulation({**p['analysis'],'type':'op'},'ngspice')
        assert job['settings']['managed_osdi']=='ihp-sg13g2' and 'executable' not in job
        backend.assert_called_once()
    # A deliberately selected custom library must never silently use a different model.
    p['simulation_runtime']={'osdi':[{'path':'chosen.osdi'}]}
    with patch('icstudio.physical_backend.prepare_simulation',side_effect=AssertionError('Custom choice must be preserved')), \
            patch('icstudio.spice_program.find_ngspice',return_value=sys.executable):
        job=w.prepare_simulation({**p['analysis'],'type':'op'},'ngspice',p)
        assert 'managed_osdi' not in job['settings']
    checks.append('Normal IHP analysis selects the included runtime; explicit OSDI configuration is preserved')
    from tests.test_native_migration import divider
    from icstudio.native_migration import review_path
    from icstudio.xschem_compat import review_project
    source=divider(out/'imported-program')
    source.write_text(source.read_text().replace('op\n','let audit=1\nop\n'))
    for kind,reader in [('program',review_path),('xschem',review_project)]:
        p=reader(source)['candidate'];p['pdk']=technology('ihp-sg13g2');w.set_project(p)
        with patch('icstudio.physical_backend.prepare_simulation',side_effect=managed) as backend, \
                patch('icstudio.run_environment.stamp',return_value={'engine':'ngspice'}):
            job=w.prepare_simulation({'type':kind,'probes':'v(out)'},'ngspice')
            assert job['settings']['managed_osdi']=='ihp-sg13g2' and 'executable' not in job
            backend.assert_called_once()
    w.runtime_dialog();dialog=w._runtime_dialog
    assert 'Included IHP' in dialog.findChild(QPlainTextEdit).toPlainText()
    with patch('icstudio.physical_backend.prepare_simulation',side_effect=managed):
        next(b for b in dialog.findChildren(QPushButton) if b.text()=='Verify files').click()
    assert any('runtime is ready' in label.text() for label in dialog.findChildren(QLabel))
    assert any(b.text()=='Physical tools setup…' for b in dialog.findChildren(QPushButton))
    QTest.qWait(30);assert dialog.grab().save(str(out/'runtime-ihp.png'))
    dialog.close();checks.append('Imported and native IHP programs use the included runtime; runtime dialog verifies that choice')
    assert not errors,errors
    w.saved_hash=digest(w.project);w.close();app.processEvents()
    (out/'checks.json').write_text(json.dumps({'status':'passed','checks':checks},indent=2))
    print(json.dumps({'status':'passed','checks':checks}))


if __name__=='__main__':main()
