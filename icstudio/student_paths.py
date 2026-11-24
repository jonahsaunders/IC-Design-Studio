"""Cross-world routes with handoffs drawn from earned checkpoint evidence."""

from dataclasses import dataclass
import math

from .student_hub import earned

HANDOFF_PREFIX = 'Earlier checkpoint · '


@dataclass(frozen=True)
class Milestone:
    lesson: str
    checkpoint: str
    task: str


@dataclass(frozen=True)
class Route:
    title: str
    goal: str
    milestones: tuple[Milestone, ...]


ROUTES = {
    'feedback': Route('Feedback and compensation',
        'Follow poles and phase from a passive filter to a loaded feedback loop and into compensation.', (
            Milestone('a-lc-bode', 'tune', 'Measure the tuned low-pass frequency, Q, and phase.'),
            Milestone('tb-verify-loop-stability', 'loop-step',
                'Use the tuned filter phase and Q to explain why a load can cause ringing. Compare the loop phase margin with the follower step.'),
            Milestone('project-miller', 'loop-evidence',
                'Use your loaded loop crossing and step response as a reference point. Compare how the Miller capacitor and nulling resistor move the zero and change phase margin.'),
        )),
    'sensor': Route('Sensor signal to bits',
        'Trace a sensor step through an analog settling budget, a SAR decision, and a digital register frame.', (
            Milestone('tb-tia-step', 'measure', 'Measure the receiver’s settling time and undershoot after a photocurrent step.'),
            Milestone('m-settling', 'measure',
                'Carry the TIA settling time into a timing budget. Allow that time before starting the SAR’s comparison cycles, then explain what a shorter comparison period does to the code.'),
            Milestone('d-spi-register', 'measure',
                'Use the observed SAR code as an example register payload. Write the corresponding eight-bit value and explain when the SPI frame may commit it.'),
        )),
    'physical': Route('RTL to layout evidence',
        'Carry a mux truth table from RTL to layout-loaded simulation and into a design review.', (
            Milestone('d-logic', 'measure', 'Run the XOR and mux reference truth-table checks.'),
            Milestone('sc-mux2', 'verify',
                'Carry the verified mux truth table into the standard-cell fixture. Compare each schematic and layout-loaded output against the same Boolean expectation.'),
            Milestone('p-review', 'explain',
                'Use the layout-loaded mux evidence in your design review. Include the verified sample count and the largest observed voltage change, along with the conditions and limits.'),
        )),
}


def validate_routes(lessons):
    by_id = {lesson['id']:lesson for lesson in lessons}
    for route in ROUTES.values():
        worlds = set()
        for stage in route.milestones:
            lesson = by_id.get(stage.lesson)
            if not lesson or not any(s['id']==stage.checkpoint and s['kind']!='quiz' for s in lesson['steps']):
                raise ValueError(f'Update the {route.title} path checkpoint for {stage.lesson}.')
            worlds.add(lesson['path'])
        if len(worlds) < 2:
            raise ValueError(f'{route.title} must span multiple worlds.')


def _reading(values, key, units=''):
    value = values.get(key)
    return f'{value:.3g}{units}' if isinstance(value, (int,float)) and math.isfinite(value) else None


def summary(lesson, evidence, previous=None):
    if lesson=='a-lc-bode':
        reading = evidence.get('lesson_measurements',{})
        frequency = _reading(reading,'f0_Hz',' Hz')
        quality = _reading(reading,'q')
        phase = _reading(reading,'phase_deg','°')
        if all((frequency,quality,phase)):
            return f'Tuned low-pass response at {frequency}, Q {quality}, phase {phase}.'
    elif lesson=='tb-verify-loop-stability':
        loop = (previous or {}).get('bench_figures',{})
        step = evidence.get('bench_figures',{})
        unity = _reading(loop,'First unity crossing (Hz)',' Hz')
        phase = _reading(loop,'Phase margin (°)','°')
        settle = _reading(step,'Settling within 2% (µs)',' µs')
        if all((unity,phase,settle)):
            return f'At 47 pF, first unity crossing {unity}, phase margin {phase}, follower settling {settle}.'
    elif lesson=='project-miller' and evidence.get('loop_measurements'):
        return f'{len(evidence["loop_measurements"])} compensation and load comparisons saved.'
    elif lesson=='tb-tia-step':
        values = evidence.get('bench_figures',{})
        settle = _reading(values,'Settling within 20 mV (µs)',' µs')
        undershoot = _reading(values,'Undershoot (mV)',' mV')
        if settle and undershoot:
            return f'TIA settling within 20 mV took {settle}, with {undershoot} undershoot.'
    elif lesson=='m-settling' and evidence.get('codes') and evidence.get('edges'):
        return f'Recovered SAR code {evidence["codes"][0]} at comparison edge {evidence["edges"][0]}.'
    elif lesson=='d-spi-register' and evidence.get('result_sha256'):
        return 'Mode 0 register simulation passed the reference framing and commit checks.'
    elif lesson=='d-logic' and evidence.get('result_sha256'):
        return 'The XOR and mux passed every input combination in the reference RTL simulation.'
    elif lesson=='sc-mux2':
        layout, schematic = evidence.get('logic_samples',[]), evidence.get('schematic_samples',[])
        if layout and len(layout)==len(schematic) and all(a['inputs']==b['inputs'] for a,b in zip(layout,schematic)):
            delta = max(abs(a['output_V']-b['output_V']) for a,b in zip(layout,schematic))
            return f'{len(layout)} mux samples passed with layout loading. Largest schematic-to-layout change {delta*1e3:.3g} mV.'
    elif lesson=='p-review' and evidence.get('note'):
        return 'Design review reflection saved.'
    return None


def milestones(route, state, lessons):
    results = []
    for stage in route.milestones:
        records = earned(state, lessons[stage.lesson])
        record = records.get(stage.checkpoint,{})
        extra = records.get('loop-ac',{}).get('evidence') if stage.lesson=='tb-verify-loop-stability' else None
        results.append(summary(stage.lesson,record.get('evidence',{}),extra) if record else None)
    return results


def handoff(route, lesson, state, lessons):
    for index, stage in enumerate(route.milestones):
        if stage.lesson==lesson and index:
            previous = route.milestones[index-1]
            reading = milestones(route,state,lessons)[index-1]
            task = stage.task
            if reading and lesson in ('m-settling','d-spi-register'):
                evidence = earned(state,lessons[previous.lesson])[previous.checkpoint]['evidence']
                task += sensor_transfer(lessons[lesson],evidence)
            return dict(route=route.title, source=lessons[previous.lesson]['title'], reading=reading, task=task)
    return None


def sensor_transfer(lesson, evidence):
    if lesson['id']=='m-settling':
        period = next((step['rule']['value'] for step in lesson['steps']
                       if step.get('rule',{}).get('path')==['period']),None)
        measured = evidence['bench_figures']['Settling within 20 mV (µs)']
        if isinstance(period,(float,int)) and period>0:
            periods = math.ceil(measured*1e-6/period)
            return f' At the exercise’s {period*1e6:.3g} µs comparison period, reserve {periods} whole periods for this settling budget.'
    elif lesson['id']=='d-spi-register':
        code = evidence['codes'][0]
        if isinstance(code,int) and 0<=code<256:
            return f' Use payload 0x{code:02X}, or {code:08b} transmitted most significant bit first.'
    return ''


def handoff_note(item):
    return f'{HANDOFF_PREFIX}{item["source"]}. {item["reading"]}'


def reflection_body(note):
    return '\n'.join(line for line in note.splitlines() if not line.startswith(HANDOFF_PREFIX)).strip()
