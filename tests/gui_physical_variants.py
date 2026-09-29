"""Exercise reviewed specialization, placement, locks, history and persistence."""
import argparse
import json
import os
from pathlib import Path
import sys


def fixture():
    from icstudio.model import example, device, uid, validate
    from icstudio.parametric import install
    p = example('empty')
    leaf = {'id': uid(), 'name': 'resistor_leaf', 'ports': ['a', 'b'],
            'parameters': {'r': '1k'}, 'devices': [device('R', 'R1', value='1k', nets={'p': 'a', 'n': 'b'})],
            'shapes': []}
    p['cells'].append(leaf)
    install(p, leaf['id'], leaf['devices'][0]['id'], {'kind': 'resistor', 'width': 1000})
    leaf['layout_ports'] = [{'name': leaf['devices'][0]['nets'][pin['pin']],
                             'layer': pin['layer'], 'point': list(pin['point'])}
                            for pin in leaf['layout_pins']]
    leaf['devices'][0]['value'] = '{r}'
    p['cells'][0]['devices'] = [device('X', 'X1', cell=leaf['id'], nets={'a': 'IN', 'b': 'OUT'}, parameters={'r': '2k'})]
    return validate(p)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    out = parser.parse_args().out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ['XDG_CONFIG_HOME'] = str(out / 'profile/config')
    os.environ['XDG_DATA_HOME'] = str(out / 'profile/data')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtWidgets import QApplication, QDialogButtonBox, QLabel
    from icstudio.gui import Studio
    from icstudio.model import clone, digest, save_project, load_project, uid, validate
    from icstudio.physical_variants import electrical_signature
    from icstudio.layout import polygon
    app = QApplication([])
    app.setStyle('Fusion')
    studio = Studio(recover=False)
    studio.maybe_save = lambda: True
    studio.live_check.setChecked(False)
    errors = []
    studio.error = lambda text: errors.append(str(text))
    studio.show()
    p = fixture()
    studio.set_project(p)
    original = clone(studio.project)
    studio.materialize_physical_dialog()
    preview = studio._review_dialog
    button = preview.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply)
    assert button.isEnabled(), [label.text() for label in preview.findChildren(QLabel)]
    assert studio.project == original
    # A layer lock added after preview must still prevent applying generated geometry.
    studio.layout.locked_layers.add('poly')
    button.click()
    app.processEvents()
    assert preview.isVisible() and studio.project == original
    studio.layout.locked_layers.clear()
    button.click()
    app.processEvents()
    assert not preview.isVisible()
    assert len(studio.history.undo_stack) == 1
    target = next(cell for cell in studio.project['cells'] if cell['id'] == studio.cell['devices'][0]['cell'])
    assert target['parameters']['r'] == '2000.0'
    body = next(shape for shape in target['shapes'] if shape.get('pcell_role') == 'body')
    assert polygon(body).bbox().width() == 20000
    assert electrical_signature(studio.project, studio.cid) == electrical_signature(original, original['top'])
    # The exported physical port must follow the regenerated resistor terminal.
    pin = next(pin for pin in target['layout_pins'] if pin['pin'] == 'n')
    assert next(port for port in target['layout_ports'] if port['name'] == 'b')['point'] == pin['point']
    modified = clone(studio.project['cells'])
    studio.undo()
    assert studio.project['cells'] == original['cells']
    studio.redo()
    assert studio.project['cells'] == modified
    save_project(studio.project, out / 'variants.icproj')
    assert load_project(out / 'variants.icproj')['cells'] == modified
    studio.set_project(original)
    studio.materialize_physical_dialog()
    preview = studio._review_dialog
    studio.commit(lambda project: project.update(name='Concurrent edit'), 'Rename project')
    changed = digest(studio.project)
    preview.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply).click()
    assert digest(studio.project) == changed and preview.isVisible()
    preview.reject()
    # Placing an unchanged shared master also affects all of its mask layers;
    # no regenerated shape dictionary is available to trigger the lock check.
    plain = clone(original)
    plain['cells'][0]['devices'][0]['parameters'] = {}
    studio.set_project(plain)
    before_plain = clone(studio.project)
    form = studio.place_linked_dialog()
    form.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()
    app.processEvents()
    preview = studio._review_dialog
    button = preview.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply)
    assert button.isEnabled()
    studio.layout.locked_layers.add('poly')
    button.click()
    app.processEvents()
    assert preview.isVisible() and studio.project == before_plain
    assert not studio.history.undo_stack
    studio.layout.locked_layers.clear()
    button.click()
    app.processEvents()
    assert not preview.isVisible() and len(studio.cell['layout_instances']) == 1
    assert studio.project['cells'][1]['shapes'] == before_plain['cells'][1]['shapes']
    studio.undo()
    assert studio.project['cells'] == before_plain['cells']
    # Placement performs the same specialization within its reviewed transaction.
    studio.set_project(original)
    form = studio.place_linked_dialog()
    form.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()
    app.processEvents()
    assert studio.project['cells'] == original['cells']
    preview = studio._review_dialog
    assert preview.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply).isEnabled()
    preview.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply).click()
    app.processEvents()
    assert len(studio.cell['layout_instances']) == 1
    assert studio.cell['layout_instances'][0]['cell'] == studio.cell['devices'][0]['cell']
    assert len(studio.history.undo_stack) == 1
    studio.undo()
    assert studio.project['cells'] == original['cells']
    studio.redo()
    studio.mode_combo.setCurrentIndex(1)
    studio.refresh(True)
    app.processEvents()
    studio.grab().save(str(out / 'physical-variants.png'))
    array_project = fixture()
    cell = array_project['cells'][0]
    instance = cell['devices'][0]
    instance.update(array={'start': 1, 'end': 0}, nets={'a': 'IN[1:0]', 'b': 'OUT[1:0]'})
    cell['layout_instances'] = [{'id': uid(), 'name': instance['name'], 'device_id': instance['id'],
                                'cell': instance['cell'], 'x': 0, 'y': 0, 'nx': 2, 'ny': 1,
                                'a': [40000, 0], 'b': [0, 0], 'rotation': 0, 'mirror': False}]
    validate(array_project)
    studio.set_project(array_project)
    studio.selection = [instance['id']]
    before_array = clone(studio.project['cells'])
    form = studio.materialize_array_dialog()
    form.fields['pitch_x'].setText('40')
    form.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()
    app.processEvents()
    assert studio.project['cells'] == before_array
    preview = studio._review_dialog
    assert preview.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply).isEnabled(), [label.text() for label in preview.findChildren(QLabel)]
    studio.layout.locked_layers.add('poly')
    preview.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply).click()
    app.processEvents()
    assert preview.isVisible() and studio.project['cells'] == before_array
    studio.layout.locked_layers.clear()
    preview.findChild(QDialogButtonBox).button(QDialogButtonBox.Apply).click()
    app.processEvents()
    assert [member['nets']['a'] for member in studio.cell['devices']] == ['IN[1]', 'IN[0]'], (studio.cell['devices'], errors, [label.text() for label in preview.findChildren(QLabel)])
    assert [placement['x'] for placement in studio.cell['layout_instances']] == [0, 40000]
    assert len({placement['device_id'] for placement in studio.cell['layout_instances']}) == 2
    expanded = clone(studio.project['cells'])
    studio.undo()
    assert studio.project['cells'] == before_array
    studio.redo()
    assert studio.project['cells'] == expanded
    save_project(studio.project, out / 'array.icproj')
    assert load_project(out / 'array.icproj')['cells'] == expanded
    assert not errors, errors
    studio.saved_hash = digest(studio.project)
    studio.close()
    report = {'status': 'passed', 'checks': ['preview without mutation', 'apply-time layer locks',
              'unchanged shared-master placement locks and undo', 'array expansion layer locks',
              'parameter-correct geometry and ports', 'electrical equivalence', 'one-step undo/redo',
              'save/reopen', 'stale preview rejection', 'reviewed automatic placement',
              'linked electrical array review, ordered nets, pitch, undo and reopen'],
              'scope': 'Offscreen Qt and illustrative resistor geometry; no process qualification.'}
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
