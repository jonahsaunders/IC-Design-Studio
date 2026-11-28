"""Teaching material and a readable, honest portfolio, separate from grading."""
import html
import json
from functools import lru_cache

from .model import atomic_write, now


@lru_cache(maxsize=1)
def hint_source():
    from .getting_started import resource_root
    return json.loads((resource_root()/'examples/student-hub/study-hints.json').read_text(encoding='utf-8'))


def answer_choices(step, lesson=None):
    """Use stable presentation order while keeping authored answer IDs."""
    from .model import digest
    choices = list(step.get('options', ()))
    if choices and lesson and step['id']=='predict':
        distractors = review_course()[author_id(lesson)].get('distractors')
        if distractors:
            indices = [i for i in range(len(choices)) if i!=step['answer']]
            for index,value in zip(indices,distractors,strict=True):
                choices[index]=value
    return sorted(enumerate(choices), key=lambda item: digest([step['instructions'],item[1]]))


@lru_cache(maxsize=1)
def review_course():
    from .getting_started import resource_root
    from . import student_beacon, student_testbench

    authored = json.loads((resource_root()/'examples/student-hub/lesson-review.json').read_text(encoding='utf8'))
    embedded = {lesson['id']: student_beacon.teaching(lesson['vga_lesson']) for lesson in student_beacon.lessons()}
    embedded.update({lesson['id']: student_testbench.teaching(lesson['id']) for lesson in student_testbench.lessons()})
    for key, note in embedded.items():
        authored.setdefault(key, {'exercise': note['try_next'], 'evidence': note['artifact']})
    return authored


def author_id(lesson):
    stage = lesson.get('inverter_stage')
    return 'inverter-'+stage if stage else lesson['id']


def evidence_label(step):
    if step['kind']=='quiz':
        return 'Knowledge check'
    if step['kind']=='reflection':
        return 'Reflection for instructor review'
    rule = step['rule']
    kind = rule['type']
    if kind in {'structure','nets','value','hierarchy','layout','digital_sources','config','config_number','rtl_contains'}:
        return 'Workspace inspection'
    if kind=='saved':
        return 'Saved project'
    if kind=='standard_cell':
        return 'Simulation and design targets' if step['id']=='verify' else 'Teaching-layout checks'
    if kind=='inverter':
        return {'binding':'PDK inspection','schematic':'Workspace inspection'}.get(rule.get('check'),'Measurement or process verification')
    if kind in {'layout_exercise','layout_decisions','layout_study'}:
        return 'Physical geometry or model evidence'
    if kind=='loop_study':
        return 'Saved loop-response measurements'
    return 'Simulation or measured result'


def preparation_html(lesson):
    from .student_hub import tools_for_lesson
    tools = tools_for_lesson(lesson)
    background = {
        'analog-projects':'DC bias, small-signal gain and transient or frequency plots.',
        'standard-cells':'CMOS pull-up and pull-down paths, physical pins and power rails.',
        'layout':'Layer visibility, physical nets and dimensional units.',
        'digital':'Logic values, clock edges and basic RTL.',
        'mixed':'Analog waveforms, logic timing and sampling.',
        'capstone':'Analog waveforms, logic timing and sampling.',
        'testbenches':'Schematic ports and basic operating-point or transient plots.',
        'inverter':'Four-terminal MOS devices and the selected process rules.',
    }.get(lesson['path'])
    if lesson['id']=='a-switch-drive':
        background = 'Gate-to-source voltage and Ohm’s law. The gm/ID series is useful background.'
    if lesson['id']=='project-ahuja':
        background += ' The Miller compensation lesson is useful preparation.'
    elif lesson['id'] in ('project-opamp','project-tia'):
        background += ' Review the matching Testbenches sequence first.'
    elif lesson['id'].startswith('project-bandgap-'):
        background += ' A current-reference and cascode-mirror comparison is useful preparation.'
    elif lesson['id']=='l-access':
        background += ' The compact layout from Plan a block before routing is the shared starting point.'
    setup = ' · '.join(tools)
    if tools:
        setup += '. Open Engine setup in Student Hub before starting.'
    return (('<h3>Useful background</h3>'+_paragraph(background)) if background else '') + (
        '<h3>Tools to check before starting</h3>'+_paragraph(setup) if tools else '')


def review_html(lesson):
    item = review_course()[author_id(lesson)]
    return ('<h3>Try a new case</h3>'+_paragraph(item['exercise'])+
            '<h3>Evidence to discuss</h3>'+_paragraph(item['evidence'])+
            '<p>Use this exercise for practice or instructor review. Keep a link to the result or name the trace, net or rule you used.</p>')


def lesson_hints(lesson, author_id=None):
    if lesson.get('vga_lesson'):
        from .student_beacon import hints
        return hints(lesson['vga_lesson'])
    if lesson.get('standard_cell'):
        from .student_standard_cells import hints
        return hints(lesson['standard_cell'])
    if lesson.get('bench_project'):
        from .student_testbench import hints
        return hints(lesson['id'])
    source = hint_source()
    result = {}
    for step in lesson['steps']:
        if step['kind'] != 'quiz':
            continue
        key = f'{author_id or lesson["id"]}/{step["id"]}'
        entries = source.get(key, [])
        if not isinstance(entries, list) or len(entries) != 4 or any(
            not isinstance(pair, list) or len(pair) != 2
            or any(not isinstance(text, str) or not text.strip() for text in pair)
            or not pair[0].endswith('?') for pair in entries
        ) or len({pair[0].casefold() for pair in entries}) != 4:
            raise ValueError('Add four distinct student questions with answers for '+key)
        result[step['id']] = entries
    return result


@lru_cache(maxsize=1)
def mode_source():
    from .getting_started import resource_root
    return json.loads((resource_root()/'examples/student-hub/lesson-modes.json').read_text(encoding='utf-8'))


def lesson_practice(lesson, author_id=None):
    if lesson.get('vga_lesson'):
        from .student_beacon import practice
        return practice(lesson['vga_lesson'])
    if lesson.get('standard_cell'):
        from .student_standard_cells import practice
        return practice(lesson['standard_cell'])
    if lesson.get('bench_project'):
        from .student_testbench import practice
        return practice(lesson['id'])
    source = mode_source()
    tasks, questions = {}, {}
    for step in lesson['steps']:
        key = f'{author_id or lesson["id"]}/{step["id"]}'
        if step['kind'] == 'quiz' and key in source['challenge_questions']:
            prompt = source['challenge_questions'][key]
            if not isinstance(prompt, str) or not prompt.strip():
                raise ValueError('Add a question for ' + key)
            questions[step['id']] = prompt
        if step['kind'] != 'check':
            continue
        if step['rule']['type']=='loop_study':
            from .student_loop_study import practice
            tasks[step['id']] = practice(lesson['starter'])
            continue
        record = source['tasks'].get(key)
        if not isinstance(record, list) or len(record) != 3:
            raise ValueError('Add a challenge, walkthrough and solution for ' + key)
        goal, actions, solution = record
        if (not isinstance(actions, list) or len(actions) < 2
                or not all(isinstance(line, str) and line.strip() for line in [goal, *actions, solution])):
            raise ValueError('Incomplete practice material for ' + key)
        updated = {
            ('f-debug','build'): ('Choose a load resistance and preserve the 10 kΩ divider. The output must remain at least 0.89 V.',
                                  ['Open the loaded divider and identify the parallel lower leg.',
                                   'Choose a load resistance that leaves enough voltage at out and apply the edit.',
                                   'Run the lesson and use Results to test your design.']),
            ('a-gmid-size','build'): ('Choose a width for the target gm at the fixed bias. Keep VG, VD and L at their specified values.',
                                      ['Read the target operating point and identify which parameter is adjustable.',
                                       'Apply a candidate width. Use the measured gm, ID and gm/ID to check the sizing.']),
            ('a-gmid-tradeoff','build'): ('Choose bias and width to hit the same gm at a lower current.',
                                          ['Compare the desired gm/ID with the previous bias and choose a gate voltage.',
                                           'Enter a width and use the operating-point readout to test both targets.']),
        }.get((lesson['id'],step['id']))
        tasks[step['id']] = [*updated,solution] if updated else record
    return dict(tasks=tasks, questions=questions)


def study_guide(data):
    from .getting_started import resource_root
    from .student_layout_labs import course
    from .student_signal_labs import course as signal_course
    from . import student_beacon, student_standard_cells, student_testbench
    content = json.loads((resource_root()/'examples/student-hub/study-guide.json').read_text(encoding='utf-8'))
    ids = {lesson['id'] for lesson in data['lessons']}
    content['lessons'].update({'l-' + unit['id']: unit['teaching'] for unit in course() if 'l-' + unit['id'] in ids})
    content['lessons'].update({unit['id']: unit['teaching'] for unit in signal_course() if unit['id'] in ids})
    bench_ids = {lesson['id'] for lesson in data['lessons'] if lesson.get('bench_project')}
    content['lessons'].update({key: student_testbench.teaching(key) for key in bench_ids})
    content['lessons'].update({lesson['id']: student_beacon.teaching(lesson['vga_lesson'])
                               for lesson in data['lessons'] if lesson.get('vga_lesson')})
    content['lessons'].update({lesson['id']: student_standard_cells.teaching(lesson['standard_cell'])
                               for lesson in data['lessons'] if lesson.get('standard_cell')})
    if set(content['lessons']) != ids:
        raise ValueError('Every lesson needs teaching material in the study guide.')
    for note in content['lessons'].values():
        for field in ('concept','worked_example','try_next','interview','artifact'):
            if not isinstance(note.get(field),str) or not note[field].strip():
                raise ValueError('Incomplete lesson teaching material: '+field)
    content['hints'] = {lesson['id']: lesson_hints(lesson) for lesson in data['lessons']}
    content['practice'] = {lesson['id']: lesson_practice(lesson) for lesson in data['lessons']}
    return content


def question_text(step, practice, guided):
    return step['instructions'] if guided else practice['questions'].get(step['id'], step['instructions'])


def challenge_text(step, practice):
    if step['kind'] == 'check':
        return practice['tasks'][step['id']][0]
    return question_text(step, practice, False)

def _paragraph(text):
    return '<p>' + html.escape(text).replace('\n', '<br>') + '</p>'


def _numbered(actions):
    return '<ol>' + ''.join('<li>' + html.escape(action) + '</li>' for action in actions) + '</ol>'


def task_html(step, practice, guided, workflow='graphical'):
    if step['kind'] == 'quiz':
        question = _paragraph(question_text(step, practice, guided))
        return question + (_numbered([
            'Read the conditions in the question and make a prediction.',
            'Choose your answer from the list below.',
            'Choose Check this step and read the explanation.',
        ]) if guided else '')
    if step['kind'] == 'reflection':
        prompt = _paragraph(step['instructions'])
        return prompt + (_numbered([
            'If this lesson has a saved run, open Results to revisit it. For a geometry, source, or study exercise, reopen the workspace or study you used.',
            'Record the test conditions, your observation and an explanation. Include the run, trace, net or rule you used, with units where applicable.',
            'Enter at least 40 characters in Your reflection and choose Record reflection.',
        ]) if guided else '')
    goal, actions, _ = practice['tasks'][step['id']]
    if not guided:
        return _paragraph(goal)
    bench = practice.get('bench_workflows', {}).get(step['id'])
    if bench:
        return _paragraph(step['instructions']) + _bench_walkthrough(bench, workflow)
    checklist = list(actions)
    if not any('Check this step' in action for action in checklist):
        checklist.append('Choose Check this step and read the checkpoint result.')
    return _paragraph(goal) + _numbered(checklist)


def lesson_run_step(job):
    return (job.get('student_layout_step') or job.get('student_signal_step')
            or job.get('student_bench_step') or job.get('student_cell_step')
            or job.get('student_analog', {}).get('stage'))


def _bench_walkthrough(bench, workflow):
    steps = _numbered(bench[workflow])
    if workflow == 'spice':
        steps += '<pre>' + html.escape(bench['program']) + '</pre>'
    return steps


def solution_html(step, practice, note):
    title = '<h2>' + html.escape(step['title']) + '</h2>'
    if step['kind'] == 'quiz':
        answer = html.escape(step['options'][step['answer']])
        return title + '<p><b>' + answer + '</b></p>' + _paragraph(step['explanation'])
    if step['kind'] == 'reflection':
        return (title + '<h3>Example reasoning</h3>' + _paragraph(note['worked_example'])
                + _paragraph('Use your own observed values, test conditions and reasoning for this prompt.')
                + _paragraph(step['instructions']))
    _, actions, solution = practice['tasks'][step['id']]
    if code := practice.get('code',{}).get(step['id']):
        return title + _paragraph(solution) + _numbered(actions) + '<pre>'+html.escape(code)+'</pre>'
    bench = practice.get('bench_workflows', {}).get(step['id'])
    if bench:
        return (title + _paragraph(solution)
                + '<h3>Graphical testbench</h3>' + _bench_walkthrough(bench, 'graphical')
                + '<h3>SPICE program</h3>' + _bench_walkthrough(bench, 'spice'))
    return title + _paragraph(solution) + '<h3>In Studio</h3>' + _numbered(actions)


RELATED_EXAMPLES = {
    'foundations':'A 6 kΩ resistor and a 4 kΩ resistor divide a 5 V step to 2 V before any load is attached. Adding another 4 kΩ across the lower leg changes that leg to 2 kΩ and its output to 1.25 V.',
    'analog':'A 1 mS transconductor driven by 10 mV supplies 10 µA of incremental current. Across 20 kΩ this gives 0.2 V before output resistance or loading is included.',
    'digital':'In a two-clock pipeline, an input accepted on edge 4 can emerge on edge 6. The matching valid bit must go through the same two stages even when the following cycle is empty.',
    'mixed':'For a 4-bit converter with a 1.6 V span, one ideal code step is 0.1 V. A 30 mV hold error therefore consumes 0.3 LSB before comparator or DAC error is counted.',
    'layout':'For a uniform 18 µm by 0.6 µm route, length divided by width gives 30 squares. At 0.4 Ω per square, the uniform segment contributes about 12 Ω before contacts and vias.',
    'career':'A reproducible requirement specifies a value, a tolerance, a condition and a test. For example, a board-level regulator must supply 3.30 V ± 50 mV at 30 mA after 1 ms.',
    'analog-projects':'A pole at 2 MHz and a second pole at 20 MHz both affect phase. At 5 MHz the second pole adds about 14° of lag, even if its effect on magnitude is still small.',
    'testbenches':'A sensor fixture with 1.05 V at one input and 0.75 V at the other applies 0.30 V differential around 0.90 V common mode. Save both pin traces so either derived quantity can be checked.',
    'standard-cells':'A gate that slews through a 10 fF load with roughly 90 µA of current moves 0.9 V in about 100 ps. This charge estimate gives a comparison point for a measured propagation delay.',
    'inverter':'A transfer curve can cross at half the supply while its switching region is asymmetric. Mark the two slope-of-minus-one points separately before calculating either noise margin.',
    'capstone':'If a sampler settles to within 0.4 LSB and its reference drifts by 0.3 LSB in the same direction, a worst-case sum is 0.7 LSB. Testing each block alone does not establish a 0.5 LSB system limit.',
}


def notes_html(note, lesson=None):
    idea = '<h3>Understand the idea</h3>'+_paragraph(note['concept'])
    related = '<h3>Worked example with different conditions</h3>'+_paragraph(RELATED_EXAMPLES[lesson['path']]) if lesson else ''
    return idea+related+''.join('<h3>'+title+'</h3>'+_paragraph(note[key]) for key,title in (
        ('artifact','Keep for your portfolio'),('interview','Explain the result')))


def overview_html(note):
    return '<p><b>Portfolio outcome</b><br>'+html.escape(note['artifact'])+'</p>'


def portfolio_html(portfolio, data, guide):
    from .student_hub import earned, complete, missing_prerequisites
    esc = html.escape; state = portfolio.state; sections=[]
    for lesson in data['lessons']:
        done = earned(state,lesson)
        record = state['lessons'].get(lesson['id'],{})
        workspace = portfolio.workspace(lesson)
        status = 'Complete' if complete(state,lesson) else 'In progress' if done else 'Not yet earned'
        missing = missing_prerequisites(state,lesson,data)
        rows=[]
        for step in lesson['steps']:
            evidence=done.get(step['id'],{}).get('evidence',{})
            note=record.get('notes',{}).get(step['id'])
            if note is None: note=evidence.get('note','')
            detail=''
            if note: detail+='<p class="note">'+esc(note)+'</p>'
            if evidence:
                # Include captured measurements/hashes and original earned notes,
                # distinct from editable drafts. Escape all user-controlled text.
                detail+='<details><summary>Captured evidence</summary><pre>'+esc(json.dumps(evidence,indent=2,ensure_ascii=False))+'</pre></details>'
            if step['kind']=='reflection':
                detail += '<p>Review the test conditions, the cited observation and the circuit reasoning.</p>'
            rows.append('<li><b>'+esc(step['title'])+'</b> · '+esc(evidence_label(step))+' · '+('Earned' if evidence else 'Not earned')+detail+'</li>')
        sections.append('<section><h2>'+esc(lesson['title'])+'</h2><p>'+esc(lesson['path'].title())+' · '+status+
                        f' · {len(done)}/{len(lesson["steps"])} checkpoints</p>'+overview_html(guide['lessons'][lesson['id']])+
                        ('<p>Prerequisites still needed: '+esc(', '.join(missing))+'</p>' if missing else '')+
                        ('<p>Saved project: '+esc(workspace['path'])+'</p>' if workspace else '')+
                        '<ol>'+''.join(rows)+'</ol></section>')
    count=sum(complete(state,l) for l in data['lessons'])
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>IC design learning portfolio</title><style>
body{font:16px/1.6 system-ui,sans-serif;color:#18273b;background:#f3f6fa;margin:0 auto;max-width:960px;padding:36px}
section{background:white;border:1px solid #ccd6e0;border-radius:12px;padding:24px;margin:24px 0;break-inside:avoid}
h1,h2{line-height:1.2} .note,pre{white-space:pre-wrap;overflow-wrap:anywhere}pre{font-size:12px;background:#f3f6fa;padding:12px}
@media print{body{padding:0;background:white}details{display:block}section{border:0;border-top:1px solid #ccc}}
</style><h1>IC design learning portfolio</h1>'''+f'<p>{count} of {len(data["lessons"])} lessons complete · Exported {esc(now())}</p>'+\
        '<p>This is a learning record. Checkpoints preserve evidence from the design that passed at the time; subsequent edits can differ. '+\
        'Reflections and current drafts are student writing, not independently assessed engineering conclusions. '+\
        'Generic teaching results do not establish foundry signoff or job qualification. Use the JSON learning record for embedded saved projects.</p>'+''.join(sections)+'</html>'


def export_portfolio(portfolio, destination, data, guide):
    atomic_write(destination,portfolio_html(portfolio,data,guide))
