"""Saved numerical evidence for the two compensation lessons."""

from . import student_ahuja, student_miller


LESSONS = {
    'miller-study': (
        'Save Miller loop measurements',
        'At 20 pF load and 2 pF compensation, save the comparisons for 500 Ω, 1 kΩ and 2 kΩ.',
        ((20,2,500), (20,2,1000), (20,2,2000)),
    ),
    'ahuja-study': (
        'Save Ahuja loop measurements',
        'At 20 pF and 40 pF load, save the comparisons for both 10 MHz and 50 MHz buffer poles.',
        ((20,10), (20,50), (40,10), (40,50)),
    ),
}
STEP = 'loop-evidence'


def add_checkpoints(lessons):
    for lesson in lessons:
        starter = lesson['starter']
        if starter in LESSONS:
            title, instructions, _ = LESSONS[starter]
            step = dict(id=STEP,kind='check',title=title,instructions=instructions,rule={'type':'loop_study'})
            lesson['steps'].insert(-1,step)


def legacy_lesson(lesson):
    if lesson['starter'] in LESSONS:
        return {**lesson,'steps':[step for step in lesson['steps'] if step['id']!=STEP]}
    return None


def practice(starter):
    _, goal, _ = LESSONS[starter]
    return [goal,[
        'Choose Open loop comparison. Keep the fixture in unity feedback.',
        'Set each requested load and compensation condition. Read the first falling unity crossing and the phase margin from the same curve.',
        'Choose Save comparison for each condition. Open the remaining settings and repeat.',
        'Close the comparison and choose Check this step to record the measurements.',
    ], goal+' For Miller, compare the sign and location of the zero. For Ahuja, compare the finite-buffer row against the ideal buffer.']


def measure(starter, values):
    study = student_miller.study if starter=='miller-study' else student_ahuja.study
    _, series = study(*values)
    return {key:{name:list(value) if name=='zero' else value for name,value in row.items() if name not in ('gain','phase')}
            for key,row in series.items()}


def save(project, starter, values):
    values = tuple(values)
    _, _, cases = LESSONS[starter]
    if values not in cases:
        raise ValueError('Select one of the load and compensation conditions in the lesson.')
    records = project.setdefault('student_loop_study',{}).setdefault(starter,{})
    records[str(cases.index(values))] = measure(starter,values)


def check(project, starter):
    _, instructions, cases = LESSONS[starter]
    actual = project.get('student_loop_study',{}).get(starter,{})
    evidence = []
    for index, values in enumerate(cases):
        measured = measure(starter,values)
        if actual.get(str(index)) != measured:
            raise ValueError(instructions+' Save each comparison from the loop viewer.')
        evidence.append(dict(condition=list(values), readings=measured))
    return evidence
