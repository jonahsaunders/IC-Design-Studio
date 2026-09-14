"""A durable, dependency-aware controller over the application's job queue."""
from __future__ import annotations

import json
from pathlib import Path

from .model import atomic_write, clone, now, uid
from .digital_identity import PHYSICAL, current

LABELS = {'lint': 'Lint', 'simulate': 'Simulation', 'elaborate': 'Elaboration', 'synth': 'Generic synthesis',
          'regression': 'Regression', 'mapped': 'Synthesis', 'equivalence': 'Equivalence',
          'floorplan': 'Floorplan', 'place': 'Placement', 'cts': 'Clock tree', 'route': 'Routing',
          'finish': 'GDS & extraction', 'timing': 'Timing'}


def sequence(target, config):
    if target == 'verify':
        return ['lint', 'regression' if config.get('tests') else 'simulate', 'mapped', 'equivalence', 'timing']
    if target in PHYSICAL:
        return ['mapped', *PHYSICAL[:PHYSICAL.index(target) + 1], 'timing']
    if target in ('timing', 'equivalence'):
        return ['mapped', target]
    if target not in LABELS:
        raise ValueError('Unknown digital flow target.')
    return [target]


def data_of(row):
    return (row.get('result') or {}).get('digital_result', {})


def usable(row, project, cid, stage=None):
    from .digital_design import config
    data = data_of(row)
    return (row['state'] == 'Complete' and row['job']['project']['id'] == project['id']
            and row['job']['cell'] == cid and bool(data)
            and (stage is None or data['stage'] == stage)
            and current(data, config(project, cid), row['job']['settings'].get('simulator', 'icarus'))
            and data.get('verdict') not in ('FAIL', 'UNKNOWN', 'ERROR', 'INCOMPLETE'))


def latest_upstream(rows, project, cid, stage):
    """Select compatible data by stage, never an unrelated last-selected row."""
    if stage not in (*PHYSICAL, 'timing', 'equivalence'):
        return None
    allowed = ['mapped']
    if stage in PHYSICAL:
        allowed += list(PHYSICAL[:PHYSICAL.index(stage)])
    else:
        allowed += list(PHYSICAL)
    candidates = [r for r in rows if data_of(r).get('stage') in allowed and usable(r, project, cid)]
    if not candidates:
        return None
    return max(enumerate(candidates), key=lambda pair: (allowed.index(data_of(pair[1])['stage']), pair[0]))[1]


def matching_result(rows, job):
    from .digital_design import config
    from .digital_identity import stage_key
    from .digital_flow import validate_result
    settings = job['settings']; stage = settings['stage']; upstream = settings.get('upstream', {})
    key = stage_key(config(job['project'], job['cell']), stage, settings.get('simulator', 'icarus'))
    for row in reversed(rows):
        data = data_of(row)
        if not usable(row, job['project'], job['cell'], stage) or data.get('input_key') != key:
            continue
        if data.get('environment') != job['environment']:
            continue
        if stage in (*PHYSICAL, 'timing', 'equivalence'):
            recorded = row['job']['settings'].get('upstream', {}).get('artifacts', {})
            expected = upstream.get('artifacts', {})
            if any(recorded.get(k, {}).get('sha256') != expected.get(k, {}).get('sha256') for k in ('netlist', 'spef')):
                continue
        try:
            validate_result(row['result'], row['path'])
        except (OSError, ValueError):
            continue
        return row
    return None


def controller_type():
    # The pure planning helpers stay usable by the CLI and non-Qt unit tests.
    from PySide6.QtCore import QObject, QTimer, Signal

    class FlowController(QObject):
        changed = Signal()

        def __init__(self, window):
            super().__init__(window)
            self.window = window; self.record = None; self.path = None; self.active_row = None
            window.studio.run_manager.completed.connect(self.completed)

        @property
        def active(self):
            return bool(self.record and self.record['state'] == 'Running')

        def save(self):
            if self.path:
                atomic_write(self.path, json.dumps(self.record, indent=2))
            self.changed.emit()

        def start(self, target):
            w = self.window
            if self.active:
                raise ValueError('Stop the current flow before starting another target.')
            if not w.apply():
                return
            config = clone(w.config)
            self.record = {'version': 1, 'id': uid(), 'created': now(), 'target': target,
                           'project': clone(w.studio.project), 'cell': w.cell_id,
                           'tools': w.workspace.tools(), 'orfs': w.studio.settings.value('digital/orfs', ''),
                           'simulator': w.simulator.currentData(), 'state': 'Running',
                           'steps': [{'stage': s, 'state': 'Pending'} for s in sequence(target, config)]}
            self.path = Path(w.studio.jobs_dir)/w.project_id/'plans'/(self.record['id']+'.json')
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.active_row = None; self.save(); QTimer.singleShot(0, self.advance)

        def advance(self):
            if not self.active or self.active_row is not None:
                return
            from .digital_flow import prepare
            r = self.record; w = self.window
            step = next((s for s in r['steps'] if s['state'] == 'Pending'), None)
            if step is None:
                r['state'] = 'Complete'; self.save(); return
            try:
                rows = w.studio.run_manager.rows
                upstream = latest_upstream(rows, r['project'], r['cell'], step['stage'])
                job = prepare(r['project'], step['stage'], r['simulator'], r['tools'], cell_id=r['cell'],
                              upstream=upstream['path'] if upstream else None, orfs=r['orfs'])
                cached = matching_result(rows, job)
                if cached:
                    step.update(state='Reused', run=cached['id']); self.save()
                    QTimer.singleShot(0, self.advance); return
                job['settings']['plan_id'] = r['id']
                row = w.studio.run_manager.enqueue(job, w.studio.jobs_dir, LABELS[step['stage']])
                self.active_row = row['id']; step.update(state='Running', run=row['id']); self.save()
                w.runs.setCurrentIndex(w.runs.findData(row['id']))
            except Exception as exc:
                step.update(state='Failed', error=str(exc)); r['state'] = 'Failed'; self.save()
                w.message.setText(str(exc))

        def completed(self, row, result):
            if not self.record or row['id'] != self.active_row:
                return
            self.active_row = None
            step = next(s for s in self.record['steps'] if s.get('run') == row['id'])
            verdict = (result or {}).get('digital_result', {}).get('verdict')
            passed = row['state'] == 'Complete' and verdict not in ('FAIL', 'UNKNOWN', 'ERROR', 'INCOMPLETE')
            step.update(state='Complete' if passed else 'Failed', verdict=verdict)
            if not passed:
                self.record['state'] = 'Failed' if self.active else 'Cancelled'
                step['error'] = verdict or row['log'][-2000:]
            self.save()
            if self.active:
                QTimer.singleShot(0, self.advance)

        def stop(self):
            if not self.active:
                return
            self.record['state'] = 'Cancelled'; self.save()
            rows = [r for r in self.window.studio.run_manager.rows if r['id'] == self.active_row]
            self.window.studio.run_manager.cancel(rows)
            if rows and rows[0]['state']=='Cancelled':
                step=next(s for s in self.record['steps'] if s.get('run')==self.active_row)
                step['state']='Cancelled';self.active_row=None;self.save()

        def restore(self):
            if self.active:
                return
            folder = Path(self.window.studio.jobs_dir)/self.window.project_id/'plans'
            for path in sorted(folder.glob('*.json'), key=lambda p:p.stat().st_mtime_ns, reverse=True):
                try:
                    record = json.loads(path.read_text())
                    if record.get('version') != 1 or record['cell'] != self.window.cell_id:
                        continue
                    if record['state'] == 'Running':
                        pending=next((s.get('run') for s in record['steps'] if s['state']=='Running'),None)
                        row=next((r for r in self.window.studio.run_manager.rows if r['id']==pending and r['state'] in ('Running','Queued')),None)
                        if row:self.active_row=row['id']
                        else:record['state'] = 'Interrupted'
                    self.record = record; self.path = path; self.changed.emit(); return
                except (OSError, ValueError, KeyError):
                    continue
            self.record = None; self.path = None; self.changed.emit()

        def resume(self):
            if self.active or not self.record:
                return
            if self.active_row is not None:
                raise ValueError('Wait for the stopping worker before resuming.')
            # Continue the captured project; new edits require a new target run.
            # Re-evaluate every dependency, including missing or changed artifacts.
            from .digital_design import config
            self.record['steps'] = [{'stage': s, 'state': 'Pending'} for s in sequence(self.record['target'], config(self.record['project'], self.record['cell']))]
            self.record['state'] = 'Running'; self.save(); QTimer.singleShot(0, self.advance)

    return FlowController
