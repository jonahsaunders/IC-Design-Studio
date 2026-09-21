"""Measured end-to-end command/undo/save/recovery and optional canvas rendering.

The benchmark checks recovered content on each sample. It does not infer UI
latency from model timings; canvas rendering is an explicitly separate stage.
"""
import platform
import statistics
import tempfile
import time
from pathlib import Path

from . import recovery
from .model import History, clone, digest, load_project, save_project
from .design_automation import commit_batch


def benchmark(project, batch, iterations=5, *, render=False):
    if type(iterations) is not int or not 1 <= iterations <= 50:
        raise ValueError('Choose 1–50 benchmark iterations.')
    stages = {name: [] for name in ('edit', 'undo', 'redo', 'save', 'reopen', 'recovery_write', 'recovery_read', 'total')}
    application = canvases = None
    if render:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QImage, QPainter
        from .canvas import Canvas
        application = QApplication.instance() or QApplication([])
        canvases = [Canvas('schematic'), Canvas('layout')]
        for canvas in canvases:
            canvas.resize(1280, 800)
        stages['canvas_render'] = []
    def content(p):
        return digest({k: v for k, v in p.items() if k not in ('revision', 'modified')})
    with tempfile.TemporaryDirectory(prefix='icstudio-edit-benchmark-') as directory:
        root = Path(directory)
        for i in range(iterations):
            history = History(clone(project))
            before = content(history.project)
            timings = {}
            def measure(name, function):
                started = time.perf_counter()
                result = function()
                timings[name] = (time.perf_counter() - started) * 1000
                return result
            start = time.perf_counter()
            measure('edit', lambda: commit_batch(history, batch))
            edited = content(history.project)
            measure('undo', history.undo)
            if content(history.project) != before:
                raise ValueError('Benchmark undo did not restore the design.')
            measure('redo', history.redo)
            if content(history.project) != edited:
                raise ValueError('Benchmark redo did not restore the edited design.')
            if render:
                def paint():
                    cell = next(c for c in history.project['cells'] if c['id'] == batch['commands'][0]['cell_id'])
                    for canvas in canvases:
                        displayed = cell
                        if canvas.mode == 'layout' and cell.get('layout_instances'):
                            from .layout_scene import LayoutScene
                            displayed = {**cell, '_layout_scene': LayoutScene().update(history.project, cell['id'])}
                        canvas.set_data(displayed, history.project['pdk'], revision=history.project['revision'])
                        canvas.fit()
                        output = QImage(canvas.size(), QImage.Format_ARGB32)
                        output.fill(0)
                        painter = QPainter(output)
                        try:
                            from PySide6.QtCore import QPoint
                            canvas.render(painter, QPoint())
                        finally:
                            painter.end()
                measure('canvas_render', paint)
            path = root / 'design.icproj'
            measure('save', lambda: save_project(history.project, path))
            reopened = measure('reopen', lambda: load_project(path))
            if digest(reopened) != digest(history.project):
                raise ValueError('Benchmark save/reopen changed the project.')
            snapshot = measure('recovery_write', lambda: recovery.write(history.project, root / 'recovery', path))
            restored, fallback = measure('recovery_read', lambda: recovery.read(snapshot))
            if fallback or digest(restored) != digest(history.project):
                raise ValueError('Benchmark recovery did not restore the latest project.')
            timings['total'] = (time.perf_counter() - start) * 1000
            for key, elapsed in timings.items():
                stages[key].append(elapsed)
    for canvas in canvases or []:
        canvas.close()
    return {'schema': 1, 'project_id': project['id'], 'base_revision': project['revision'],
            'project_hash': digest(project), 'batch_hash': digest(batch), 'iterations': iterations,
            'environment': {'python': platform.python_version(), 'system': platform.platform()},
            'size': {'cells': len(project['cells']), 'devices': sum(len(c['devices']) for c in project['cells']),
                     'shapes': sum(len(c['shapes']) for c in project['cells']),
                     'wires': sum(len(c.get('wires', [])) for c in project['cells'])},
            'checks': {'undo_restores_design': True, 'redo_restores_edit': True,
                       'save_reopens_exactly': True, 'recovery_restores_exactly': True},
            'scope': 'command/edit/undo/redo/save/reopen/recovery' + (' and two offscreen canvases' if render else '; no UI rendering'),
            'rendered_cell_id': batch['commands'][0]['cell_id'] if render else None,
            'timings_ms': {key: {'samples': values, 'median': statistics.median(values),
                                'max': max(values)} for key, values in stages.items()}}
