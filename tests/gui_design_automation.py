"""Native dialog preview/apply/staleness, undo and screenshot acceptance."""
import argparse
import json
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ['XDG_CONFIG_HOME'] = str(out / 'profile/config')
    os.environ['XDG_DATA_HOME'] = str(out / 'profile/data')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtWidgets import QApplication
    from icstudio.gui import Studio
    from icstudio.automation_ui import AutomationDialog
    from icstudio.design_automation import envelope
    from icstudio.model import clone, digest
    app = QApplication.instance() or QApplication([])
    app.setStyle('Fusion')
    studio = Studio(recover=False)
    studio.show()
    app.processEvents()
    before = clone(studio.project)
    cell = studio.project['cells'][0]
    resistor = cell['devices'][1]
    command = {'type': 'set_parameter', 'cell_id': cell['id'], 'device_id': resistor['id'], 'name': 'value', 'value': '22k'}
    batch = envelope(studio.project, [command], 'Resize RC resistance')
    dialog = AutomationDialog(studio)
    dialog.show()
    dialog.tabs.setCurrentIndex(1)
    dialog.editor.setPlainText(json.dumps(batch, indent=2))
    dialog.preview_changes()
    assert dialog.proposal and dialog.apply_button.isEnabled(), dialog.error.text()
    assert studio.project == before
    app.processEvents()
    dialog.grab().save(str(out / 'automation-preview.png'))
    dialog.apply_changes()
    assert studio.project['cells'][0]['devices'][1]['value'] == '22k', dialog.error.text()
    assert len(studio.history.undo_stack) == 1
    studio.undo()
    assert studio.project['cells'] == before['cells']
    studio.redo()
    assert studio.project['cells'][0]['devices'][1]['value'] == '22k'
    stale = AutomationDialog(studio)
    stale.editor.setPlainText(json.dumps(envelope(studio.project, [{**command, 'value': '33k'}])))
    stale.preview_changes()
    assert stale.proposal
    studio.capture_commit(lambda p: p.update(name='Concurrent edit'), 'Rename project')
    current = digest(studio.project)
    stale.apply_changes()
    assert digest(studio.project) == current
    assert 'revision changed' in stale.error.text()
    assert not stale.apply_button.isEnabled()
    stale.reject()
    # Preserve a local recovery snapshot and avoid a close-save prompt in this test.
    studio.saved_hash = digest(studio.project)
    studio.close()
    report = {'status': 'passed', 'checks': ['preview does not mutate', 'one undo step',
        'undo and redo restore cells', 'stale preview preserves newer edit'],
        'screenshot': 'automation-preview.png', 'scope': 'offscreen Qt; no native desktop latency qualification'}
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
