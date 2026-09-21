"""Full Studio foreground editing/recovery measurements, with truthful display scope.

Run on the desired backend; this script never selects offscreen implicitly::

    QT_QPA_PLATFORM=offscreen python tests/gui_analog_scale.py --out build/scale
    xvfb-run python tests/gui_analog_scale.py --out build/scale --display-class virtual

Correctness is always gated. Latency and RSS are measured, not advertised as a
hardware guarantee. Optional explicit budgets turn those measurements into gates.
"""
import argparse
import ctypes
import json
import math
import os
from pathlib import Path
import platform
import statistics
import sys
import threading
import time
import traceback


ROOT = Path(__file__).resolve().parents[1]
EDIT_STAGES = (
    'layout_edit_and_full_refresh', 'layout_undo_and_full_refresh',
    'layout_redo_and_full_refresh', 'layout_restore_and_full_refresh',
    'edit_and_full_refresh', 'undo_and_full_refresh',
    'redo_and_full_refresh', 'unsaved_edit_and_refresh',
)


def memory_reader():
    """Current process RSS, including native Qt/KLayout allocations, without extras."""
    if sys.platform.startswith('linux'):
        page = os.sysconf('SC_PAGE_SIZE')
        return lambda: int(Path('/proc/self/statm').read_text().split()[1]) * page, 'Linux /proc/self/statm RSS'
    if os.name == 'nt':
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in ('PeakWorkingSetSize', 'WorkingSetSize',
                'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
                'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]
        current = ctypes.windll.kernel32.GetCurrentProcess
        current.restype = wintypes.HANDLE
        get = ctypes.windll.psapi.GetProcessMemoryInfo
        get.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        get.restype = wintypes.BOOL
        def read():
            counters = Counters(); counters.cb = ctypes.sizeof(counters)
            if not get(current(), ctypes.byref(counters), counters.cb):
                raise OSError('GetProcessMemoryInfo failed')
            return counters.WorkingSetSize
        return read, 'Windows process working set'
    # Unsupported hosts still get correctness/latency evidence without pretending
    # Python allocation counts describe Qt or the whole desktop process.
    return lambda: None, 'RSS unavailable on this host'


class MemorySamples:
    def __init__(self):
        self.read, self.method = memory_reader()
        self.stop = threading.Event(); self.peak = None; self.count = 0; self.error = None
        self.thread = threading.Thread(target=self.sample, daemon=True)

    def current(self):
        try:
            value = self.read()
            if value is not None:
                self.peak = max(self.peak or 0, value); self.count += 1
            return value
        except (OSError, ValueError, IndexError) as exc:
            self.error = str(exc); return None

    def sample(self):
        while not self.stop.wait(.02): self.current()

    def __enter__(self):
        self.before = self.current(); self.thread.start(); return self

    def __exit__(self, *_):
        self.stop.set(); self.thread.join(2); self.after = self.current()

    def report(self):
        return {'method': self.method, 'sample_interval_ms': 20, 'samples': self.count,
                'rss_before_bytes': self.before, 'rss_after_bytes': self.after,
                'sampled_peak_rss_bytes': self.peak, 'error': self.error,
                'scope': 'Whole current process; sampled peak may miss shorter allocation spikes.'}


def workloads():
    from icstudio.model import clone, device, file_digest, load_project, uid, validate, example
    from icstudio.parametric import install
    from icstudio.physical_cells import place
    from icstudio.layout import rect

    source = ROOT / 'examples/amplifier-testbench.icproj'
    p = load_project(source); p['name'] = 'Repeated analog fixture desktop workload'
    fixture = next(c for c in p['cells'] if c['id'] == p['top'])
    amplifier = next(c for c in p['cells'] if c['id'] != p['top'])
    for i, d in enumerate(amplifier['devices']):
        install(p, amplifier['id'], d['id'], {'x': i * 40000, 'y': 0})
    # Generic teaching geometry exercises linked display and footprint selection;
    # this workload does not claim electrically routed or process-qualified layout.
    amplifier['layout_ports'] = []
    for net in amplifier['ports']:
        pin = next(pin for pin in amplifier['layout_pins']
                   if next(d for d in amplifier['devices'] if d['id'] == pin['device_id'])['nets'][pin['pin']] == net)
        amplifier['layout_ports'].append({'name': net, 'layer': pin['layer'], 'point': clone(pin['point'])})
    instance = next(d for d in fixture['devices'] if d['kind'] == 'X')
    place(p, fixture['id'], instance['id'], 0, 0)
    load = next(d for d in fixture['devices'] if d['kind'] == 'C')
    install(p, fixture['id'], load['id'], {'x': 90000, 'y': 0})
    bank = {'id': uid(), 'name': 'amplifier_bank', 'ports': [], 'devices': [], 'shapes': []}
    p['cells'].append(bank); p['top'] = bank['id']
    for i in range(16):
        d = device('X', 'XAMP' + str(i + 1), (i % 4) * 240, (i // 4) * 180,
                   cell=fixture['id'], nets={})
        bank['devices'].append(d)
        place(p, bank['id'], d['id'], (i % 4) * 160000, (i // 4) * 70000)
    yield ('hierarchical-analog', validate(p), amplifier['id'], {
        'origin': 'examples/amplifier-testbench.icproj', 'source_sha256': file_digest(source),
        'description': '16 reused amplifier fixtures; three electrical/physical hierarchy levels; generic display geometry.',
        'qualification': 'Analog project editing and hierarchical display; excludes circuit simulation and physical qualification.'})

    p = example('empty'); p['name'] = '500 devices and 10000 shapes desktop workload'; c = p['cells'][0]
    c['devices'] = [device('R', 'R' + str(i + 1), (i % 25) * 250, (i // 25) * 200,
                           nets={'p': 'n' + str(i + 1), 'n': '0'}) for i in range(500)]
    c['shapes'] = [rect('metal1', (i % 100) * 1000, (i // 100) * 1000, 400, 400)
                   for i in range(10000)]
    yield ('synthetic-large', validate(p), c['id'], {
        'origin': 'Generated by tests/gui_analog_scale.py',
        'description': '500 distinct schematic devices and 10000 distinct local layout shapes.',
        'qualification': 'Synthetic scale workload; does not represent a routed production design.'})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--iterations', type=int, default=3)
    parser.add_argument('--display-class', choices=('auto', 'offscreen', 'virtual', 'native'), default='auto')
    parser.add_argument('--max-stage-ms', type=float, help='Optional maximum for any measured foreground stage.')
    parser.add_argument('--max-edit-ms', type=float, help='Maximum for every edit/undo/redo sample, including immediate refresh/repaint; excludes loading and saving.')
    parser.add_argument('--max-rss-mib', type=float, help='Optional sampled process RSS maximum.')
    args = parser.parse_args(argv)
    if not 1 <= args.iterations <= 20: parser.error('Use 1–20 iterations.')
    for value in (args.max_stage_ms, args.max_edit_ms, args.max_rss_mib):
        if value is not None and (not math.isfinite(value) or value <= 0): parser.error('Budgets must be finite and positive.')
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    os.environ['XDG_CONFIG_HOME'] = str(out / 'profile/config')
    os.environ['XDG_DATA_HOME'] = str(out / 'profile/data')
    sys.path.insert(0, str(ROOT))
    import PySide6
    from PySide6.QtCore import QEvent, QEventLoop, QObject, QPoint, QPointF, QSettings, QStandardPaths, Qt, qVersion
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from icstudio.gui import Studio
    from icstudio.model import clone, digest, file_digest, load_project, save_project
    from icstudio import __version__, recovery
    from icstudio.capture_ops import transform
    from icstudio.electrical_identity import partition
    from icstudio.design_ops import flatten_layout
    from icstudio.verification_campaigns import source_identity

    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(out / 'profile/settings'))
    # Native Windows QStandardPaths ignores XDG variables. This changes only the
    # harness process's profile routing, keeping settings/jobs/recovery isolated.
    QStandardPaths.writableLocation = staticmethod(lambda kind: str(out / 'profile' / str(kind.value)))
    app = QApplication.instance() or QApplication([]); app.setStyle('Fusion')
    backend = app.platformName()
    display = ('offscreen' if backend in ('offscreen', 'minimal') else 'unspecified') if args.display_class == 'auto' else args.display_class
    if display == 'native' and backend in ('offscreen', 'minimal'):
        parser.error('A native display run cannot use the offscreen/minimal Qt platform.')
    errors = []; studio = None; report = {'schema': 1, 'status': 'running', 'workloads': []}
    old_hook = sys.excepthook
    sys.excepthook = lambda typ, value, tb: (errors.append(str(value)), traceback.print_exception(typ, value, tb))
    started = source_identity()

    class Paints(QObject):
        def __init__(self): super().__init__(); self.total = self.schematic = self.layout = 0
        def eventFilter(self, obj, event):
            if event.type() == QEvent.Paint:
                self.total += 1
                if studio is not None:
                    self.schematic += obj is studio.schematic; self.layout += obj is studio.layout
            return False
        def counts(self): return {'all_widgets': self.total, 'schematic': self.schematic, 'layout': self.layout}
    paints = Paints(); app.installEventFilter(paints)

    def drain():
        app.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents(QEventLoop.AllEvents)
        if studio is not None: studio.repaint()
        app.processEvents(QEventLoop.AllEvents)

    def content(project):
        return digest({k: v for k, v in project.items() if k not in ('revision', 'modified')})

    try:
        tick = time.perf_counter(); studio = Studio(recover=False)
        studio.maybe_save = lambda: True; studio.error = lambda text: errors.append(str(text))
        studio.resize(1440, 960); studio.live_check.setChecked(False); studio.show()
        # Startup workspace restoration is a real deferred operation. Drain it
        # before per-operation timing instead of folding a fixed sleep into latency.
        QTest.qWait(200); drain()
        report['startup_ms'] = (time.perf_counter() - tick) * 1000
        screen = studio.screen(); geometry = screen.geometry()
        pixmap = studio.grab(); engine = pixmap.paintEngine()
        report.update(app_version=__version__, source=started, harness_sha256=file_digest(__file__),
            environment={'python': platform.python_version(), 'system': platform.platform(),
                'machine': platform.machine(), 'qt': qVersion(), 'pyside': PySide6.__version__,
                'qt_platform': backend, 'display_class': display, 'display_class_source': 'declared' if args.display_class != 'auto' else 'backend inference',
                'screen': {'name': screen.name(), 'width': geometry.width(), 'height': geometry.height(),
                    'logical_dpi': screen.logicalDotsPerInch(), 'physical_dpi_reported': screen.physicalDotsPerInch(),
                    'refresh_hz_reported': screen.refreshRate(), 'device_pixel_ratio': screen.devicePixelRatio()},
                'window_size': [studio.width(), studio.height()], 'style': app.style().objectName(),
                'renderer': {'pipeline': 'Qt QWidget backing store; QPainter in Canvas.paintEvent',
                    'screenshot_paint_engine': engine.type().name, 'screenshot_format': pixmap.toImage().format().name},
                'live_layout_checks': studio.live_check.isChecked()},
            timing_scope='Foreground Studio operation, queued immediate Qt work and synchronous QWidget repaint. Recovery completion measured separately. Startup includes a 200 ms deferred-restoration drain.',
            qualification='Recorded source/workloads/backend only. No external simulation, live DRC, GPU/display presentation latency, assistive technology or consumer-hardware qualification.',
            budgets={'max_stage_ms': args.max_stage_ms, 'max_edit_ms': args.max_edit_ms,
                     'edit_stages': list(EDIT_STAGES), 'max_rss_mib': args.max_rss_mib,
                     'status': 'not_configured' if all(v is None for v in (args.max_stage_ms,args.max_edit_ms,args.max_rss_mib)) else 'pending'})
        for name, project, edit_cid, description in workloads():
            work = out / name; work.mkdir(exist_ok=True)
            save_project(project, work / 'input.icproj')
            row = {'name': name, **description, 'input_sha256': file_digest(work / 'input.icproj'),
                   'iterations': args.iterations, 'samples': [], 'checks': []}
            report['workloads'].append(row)
            row['size'] = {'masters': len(project['cells']),
                'local_devices': sum(len(c['devices']) for c in project['cells']),
                'local_shapes': sum(len(c['shapes']) for c in project['cells']),
                'physical_instances': sum(len(c.get('layout_instances', [])) for c in project['cells']),
                'expanded_top_shapes': len(flatten_layout(project, project['top']))}
            with MemorySamples() as memory:
                for iteration in range(args.iterations):
                    samples = {}; paint_samples = {}
                    def measure(stage, fn):
                        prior = paints.counts(); tick = time.perf_counter(); result = fn(); drain()
                        samples[stage] = (time.perf_counter() - tick) * 1000
                        paint_samples[stage] = {k: v - prior[k] for k, v in paints.counts().items()}
                        if errors: raise AssertionError('Qt callback errors: ' + '; '.join(errors))
                        return result
                    measure('load_full_studio', lambda: studio.set_project(clone(project)))
                    QTest.qWait(30); drain()  # scheduled fit is outside operation samples
                    measure('full_refresh', lambda: studio.refresh(False))
                    root = project['top']
                    def view(cid, mode):
                        studio.cid = cid; studio.selection = []; studio.mode_combo.setCurrentIndex(mode)
                        studio.refresh(False); studio.fit_active()
                    measure('open_hierarchy_layout', lambda: view(root, 1))
                    QTest.qWait(30); drain()
                    before_selection = content(studio.project)
                    target = studio.cell.get('layout_instances', [None])[0] if studio.cell.get('layout_instances') else studio.cell['shapes'][0]
                    measure('layout_selection', lambda: studio.select([target['id']], 'layout'))
                    assert target['id'] in studio.selection and content(studio.project) == before_selection
                    canvas = studio.layout; offset = QPointF(canvas.offset); start = canvas.rect().center(); delta = QPoint(31, 19)
                    def pan():
                        QTest.mousePress(canvas, Qt.MiddleButton, Qt.NoModifier, start)
                        # QTest.mouseMove does not retain button state on every QPA
                        # plugin. Send the same held-button move a real drag emits.
                        event = QMouseEvent(QEvent.MouseMove, QPointF(start + delta), QPointF(canvas.mapToGlobal(start + delta)),
                                            Qt.NoButton, Qt.MiddleButton, Qt.NoModifier)
                        app.sendEvent(canvas, event)
                        QTest.mouseRelease(canvas, Qt.MiddleButton, Qt.NoModifier, start + delta)
                    measure('layout_mouse_pan', pan)
                    assert canvas.offset == offset + QPointF(delta) and not canvas.pan
                    assert content(studio.project) == before_selection
                    if iteration == 0:
                        assert studio.grab().save(str(work / 'layout.png'))
                    physical_before = content(studio.project); physical_topology = partition(studio.cell)
                    measure('layout_edit_and_full_refresh',
                            lambda: studio.editor_execute('move_ref', {'dx': 5000, 'dy': 0}))
                    physical_edited = content(studio.project)
                    assert physical_edited != physical_before and partition(studio.cell) == physical_topology
                    measure('layout_undo_and_full_refresh', studio.undo)
                    assert content(studio.project) == physical_before
                    measure('layout_redo_and_full_refresh', studio.redo)
                    assert content(studio.project) == physical_edited
                    measure('layout_restore_and_full_refresh', studio.undo)
                    assert content(studio.project) == physical_before
                    measure('open_hierarchy_schematic', lambda: view(edit_cid, 0))
                    QTest.qWait(30); drain()
                    device_id = studio.cell['devices'][0]['id']
                    measure('schematic_selection', lambda: studio.select([device_id], 'schematic'))
                    assert device_id in studio.selection
                    original = content(studio.project); topology = partition(studio.cell)
                    def edit():
                        assert studio.capture_commit(lambda p: transform(p, edit_cid, [device_id], dx=20), 'Scale qualification move')
                    measure('edit_and_full_refresh', edit)
                    edited = content(studio.project); assert edited != original
                    assert partition(studio.cell) == topology
                    measure('undo_and_full_refresh', studio.undo); assert content(studio.project) == original
                    measure('redo_and_full_refresh', studio.redo); assert content(studio.project) == edited
                    if iteration == 0: assert studio.grab().save(str(work / 'schematic.png'))
                    target_file = work / 'saved.icproj'; studio.path = target_file; studio._disk_hash = None
                    assert measure('save_and_full_refresh', studio.save)
                    saved = digest(studio.project); saved_bytes = target_file.read_bytes()
                    assert digest(load_project(target_file)) == saved
                    # Queue a real unsaved edit; restoring it must not overwrite
                    # the independently saved file or silently use an older snapshot.
                    measure('unsaved_edit_and_refresh', edit); unsaved = digest(studio.project)
                    assert measure('queued_recovery_completion', studio.finish_recovery)
                    assert not studio._recovery_error and studio._recovery_hash == unsaved
                    recovery_file = studio.recovery_dir / (studio.project['id'] + '.icproj')
                    captured = measure('recovery_read', lambda: recovery.read(recovery_file))
                    restored, fallback = captured; assert not fallback and digest(restored) == unsaved
                    measure('reopen_saved_full_studio', lambda: studio.set_project(load_project(target_file), target_file))
                    assert digest(studio.project) == saved
                    measure('restore_recovery_full_studio', lambda: studio.set_project(restored))
                    assert digest(studio.project) == unsaved and target_file.read_bytes() == saved_bytes
                    row['samples'].append({'iteration': iteration + 1, 'timings_ms': samples, 'paint_events': paint_samples,
                                           'rss_after_bytes': memory.current()})
                    print(json.dumps({'workload': name, 'iteration': iteration + 1, 'status': 'passed'}), flush=True)
            row['memory'] = memory.report()
            names = row['samples'][0]['timings_ms']
            row['timings_ms'] = {key: {'median': statistics.median(s['timings_ms'][key] for s in row['samples']),
                'max': max(s['timings_ms'][key] for s in row['samples'])} for key in names}
            row['checks'] = ['Full Studio refresh and visible schematic/layout paints completed.',
                'Selection and real mouse pan changed only view state.',
                'Physical move preserved schematic topology; layout undo/redo restored exact content.',
                'Schematic edit preserved electrical partition; undo/redo restored exact content.',
                'Studio save/reopen preserved the exact saved project.',
                'Queued durable recovery restored the latest unsaved edit without overwriting the saved file.']
            assert sum(s['paint_events']['layout_mouse_pan']['layout'] for s in row['samples']) > 0
            assert sum(s['paint_events']['layout_edit_and_full_refresh']['layout'] for s in row['samples']) > 0
            assert sum(s['paint_events']['edit_and_full_refresh']['schematic'] for s in row['samples']) > 0
        exceeded = []
        if args.max_stage_ms is not None and report['startup_ms'] > args.max_stage_ms:
            exceeded.append('startup')
        for row in report['workloads']:
            if args.max_edit_ms is not None:
                exceeded += [row['name'] + '/' + key for key in EDIT_STAGES
                             if row['timings_ms'][key]['max'] > args.max_edit_ms]
            if args.max_stage_ms is not None:
                exceeded += [row['name'] + '/' + key for key, value in row['timings_ms'].items() if value['max'] > args.max_stage_ms]
            if args.max_rss_mib is not None:
                peak = row['memory']['sampled_peak_rss_bytes']
                if peak is None or peak > args.max_rss_mib * 1024 * 1024: exceeded.append(row['name'] + '/RSS')
        report['budgets']['exceeded'] = exceeded
        if report['budgets']['status'] == 'pending': report['budgets']['status'] = 'failed' if exceeded else 'passed'
        assert not exceeded, 'Explicit budgets exceeded: ' + ', '.join(exceeded)
        report['status'] = 'passed'
    except Exception:
        report.update(status='failed', exception=traceback.format_exc())
    finally:
        if studio is not None:
            try:
                studio.finish_recovery(); studio.saved_hash = digest(studio.project); studio.close(); app.processEvents()
            except Exception: report.update(status='failed', cleanup_error=traceback.format_exc())
        app.removeEventFilter(paints); sys.excepthook = old_hook
        report['errors'] = errors; report['source_after'] = source_identity()
        if errors: report.update(status='failed')
        report['source_unchanged'] = started == report['source_after']
        if not report['source_unchanged']:
            report.update(status='failed', source_error='Product source changed during measurement; rerun against a stable source tree.')
        (out / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'status': report['status'], 'report': str(out / 'report.json'),
                      'exception': report.get('exception'), 'source_unchanged': report['source_unchanged']}), flush=True)
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__': raise SystemExit(main())
