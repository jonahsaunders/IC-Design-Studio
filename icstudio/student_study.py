"""Student Hub planning, curriculum comparison, and setup discovery."""

import json
import math
import os
from pathlib import Path
import shutil

from .model import digest
from .student_hub import complete, earned, missing_prerequisites, tools_for_lesson


def resume_recap(state, lesson):
    done = earned(state, lesson)
    steps = lesson['steps']
    completed = [step for step in reversed(steps) if step['id'] in done]
    last = max(completed, key=lambda step: done[step['id']].get('earned', ''), default=None)
    recent_run = max(
        (step for step in completed if has_run(done[step['id']]['evidence'])),
        key=lambda step: done[step['id']].get('earned', ''), default=None)
    next_step = next((step for step in steps if step['id'] not in done), None)
    return last, recent_run, next_step


def has_run(evidence):
    return any(key in ('job_hash', 'result_hash', 'result_sha256', 'run_path', 'runs', 'case_runs', 'run')
               or key.endswith(('_runs', '_job_hash', '_result_hash'))
               for key in evidence)


def session_options(state, data, minutes, recent, readiness, eligible):
    options = []
    for lesson in data['lessons']:
        if not eligible(lesson) or complete(state, lesson):
            continue
        if missing_prerequisites(state, lesson, data) or readiness(lesson):
            continue
        done = earned(state, lesson)
        steps = [step for step in lesson['steps'] if step['id'] not in done]
        # Put more of the published time estimate toward editing and running.
        weights = {'quiz': 1, 'check': 3, 'reflection': 1}
        total = sum(weights[step['kind']] for step in lesson['steps'])
        work = 0
        planned = []
        for step in steps:
            work += weights[step['kind']]
            duration = math.ceil(lesson['minutes'] * work / total)
            if duration > minutes:
                break
            planned.append(step)
            estimate = duration
        if planned:
            options.append((lesson, planned, estimate, len(planned) == len(steps)))
    options.sort(key=lambda option: (
        option[0]['id'] != recent,
        not bool(earned(state, option[0])),
        not option[3],
        -option[2],
    ))
    return options


def catalog_snapshot(data, material, inverter_course, inverter_material):
    snapshot = {}
    for lesson in data['lessons']:
        key = lesson['id']
        snapshot[key] = dict(title=lesson['title'], stamp=digest([
            lesson, *[material[field][key] for field in ('lessons', 'hints', 'practice')],
            inverter_material.get(key),
        ]))
    for unit in inverter_course['lessons']:
        key = 'inverter-' + unit['lesson']['id']
        snapshot[key] = dict(title=unit['lesson']['title'], stamp=digest([unit, inverter_material[key]]))
    return snapshot


def catalog_changes(previous, current):
    changes = []
    for key, record in current.items():
        if key not in previous:
            changes.append(('Added', record['title']))
        elif record != previous[key]:
            changes.append(('Updated', record['title']))
    changes.extend(('Removed', record['title']) for key, record in previous.items() if key not in current)
    return changes


def executable(name, configured=''):
    candidate = configured or shutil.which(name)
    return bool(candidate and (shutil.which(candidate) or
                (Path(candidate).is_file() and os.access(candidate, os.X_OK))))


class MachineReadiness:
    """Discover installed prerequisites without starting simulators."""

    def __init__(self, tools, digital):
        from .digital_runtime import installed, manifest
        from .digital_vga import REVISION, assets
        from .physical_backend import TOOLS
        from .spice_program import find_ngspice

        ngspice = find_ngspice(tools.get('ngspice', ''))
        self.ngspice = bool(ngspice and executable('ngspice', ngspice))
        self.native_icarus = all(executable(name, tools.get(name, '')) for name in ('iverilog', 'vvp'))
        runtime = installed()
        if digital['toolchain'] == 'custom' or os.environ.get('ICSTUDIO_DIGITAL_NATIVE') == '1':
            self.digital_icarus = all(executable(name, digital['tools'].get(name, '')) for name in ('iverilog', 'vvp'))
        else:
            self.digital_icarus = bool(runtime)
        self.manifest = manifest() if runtime else None
        self.included_physical = bool(self.manifest and set(TOOLS) <= set(self.manifest.get('tools', ())))
        self.custom_physical = {name: executable(name, tools.get(name, '')) for name in ('magic', 'netgen')}
        self.physical = (all(self.custom_physical.values()) if tools.get('magic') or tools.get('netgen')
                         else self.included_physical)
        self.analog_physical = (all(self.custom_physical.values()) if any(self.custom_physical.values()) or
                                tools.get('magic') or tools.get('netgen') else self.included_physical)
        root = assets()
        try:
            self.vga = (root / 'index.html').is_file() and json.loads(
                (root / 'icstudio-build.json').read_text(encoding='utf-8')).get('revision') == REVISION
        except (OSError, ValueError, AttributeError):
            self.vga = False
        self._decks = {}

    def blockers(self, lesson, profile=None, analog_pdk=None):
        from .osdi import managed_models
        from .process_adapters import physical_adapter

        needed = tools_for_lesson(lesson)
        missing = []
        stage = lesson.get('inverter_stage')
        technology = profile['technology'] if profile else analog_pdk
        if stage and (not profile or not profile['ready']):
            missing.append(('pdk', 'Register a supported inverter PDK revision.'))
        if lesson.get('analog_project') not in (None, 'bandgap', 'interview') and not analog_pdk:
            missing.append(('pdk', 'Register the SKY130A process models.'))
        if 'ngspice' in needed:
            if stage and technology and technology.get('simulation', {}).get('requires_osdi'):
                if stage in ('dc', 'transient'):
                    try:
                        managed_models(technology, self.manifest)
                    except ValueError:
                        missing.append(('physical', 'Set up the included IHP simulator and compiled models.'))
            elif not self.ngspice:
                missing.append(('engines', 'Install or select native ngspice.'))
        if 'Icarus Verilog' in needed:
            if lesson['path'] == 'digital' and not self.digital_icarus:
                missing.append(('digital', 'Set up Icarus in Digital tools.'))
            elif lesson['path'] != 'digital' and not self.native_icarus:
                missing.append(('engines', 'Install or select native iverilog and vvp.'))
        if lesson.get('vga_lesson') and not self.vga:
            missing.append(('vga', 'Install the VGA Playground preview assets.'))
        if 'Matching process verification decks and physical tools' in needed:
            if technology is not None and (stage or lesson.get('analog_project') in ('opamp', 'tia')):
                key = id(technology)
                if key not in self._decks:
                    try:
                        physical_adapter(technology).engine_assets(technology)
                        self._decks[key] = True
                    except (OSError, ValueError, KeyError):
                        self._decks[key] = False
                if not self._decks[key]:
                    missing.append(('pdk', 'Install a matching PDK with physical verification decks.'))
            analog = lesson.get('analog_project')
            if analog == 'bandgap':
                ready = self.custom_physical['magic'] or self.included_physical
                if not ready:
                    missing.append(('physical', 'Set up Magic for capacitance extraction.'))
            elif not (self.analog_physical if analog in ('opamp', 'tia') else self.physical):
                missing.append(('physical', 'Set up Magic and Netgen for physical verification.'))
        return list(dict.fromkeys(missing))
