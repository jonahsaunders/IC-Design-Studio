"""Teaching material and a readable, honest portfolio, separate from grading."""
import html
import json
from functools import lru_cache

from .model import atomic_write, now


@lru_cache(maxsize=1)
def hint_source():
    from .getting_started import resource_root
    return json.loads((resource_root()/'examples/student-hub/study-hints.json').read_text(encoding='utf-8'))


def lesson_hints(lesson, author_id=None):
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
        record = source['tasks'].get(key)
        if not isinstance(record, list) or len(record) != 3:
            raise ValueError('Add a challenge, walkthrough and solution for ' + key)
        goal, actions, solution = record
        if (not isinstance(actions, list) or len(actions) < 2
                or not all(isinstance(line, str) and line.strip() for line in [goal, *actions, solution])):
            raise ValueError('Incomplete practice material for ' + key)
        tasks[step['id']] = record
    return dict(tasks=tasks, questions=questions)


def study_guide(data):
    from .getting_started import resource_root
    from .student_layout_labs import course
    from .student_signal_labs import course as signal_course
    content = json.loads((resource_root()/'examples/student-hub/study-guide.json').read_text(encoding='utf-8'))
    ids = {lesson['id'] for lesson in data['lessons']}
    content['lessons'].update({'l-' + unit['id']: unit['teaching'] for unit in course() if 'l-' + unit['id'] in ids})
    content['lessons'].update({unit['id']: unit['teaching'] for unit in signal_course() if unit['id'] in ids})
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


def task_html(step, practice, guided):
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
            'Open Results for the relevant saved run, or reopen the edited workspace for a geometry or source check.',
            'Write what you predicted, what you observed and how your evidence answers the question above. Include units and test conditions where relevant.',
            'Enter at least 40 characters in Your reflection and choose Record reflection.',
        ]) if guided else '')
    goal, actions, _ = practice['tasks'][step['id']]
    if not guided:
        return _paragraph(goal)
    checklist = list(actions)
    if not any('Check this step' in action for action in checklist):
        checklist.append('Choose Check this step and read the checkpoint result.')
    return _paragraph(goal) + _numbered(checklist)


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
    return title + _paragraph(solution) + '<h3>In Studio</h3>' + _numbered(actions)


def notes_html(note):
    esc = html.escape
    return ''.join(f'<h3>{title}</h3><p>{esc(note[key]).replace(chr(10),"<br>")}</p>' for key,title in (
        ('concept','Understand the idea'),('worked_example','Worked example'),
        ('try_next','Try another case'),('artifact','Keep for your portfolio'),('interview','Explain it in an interview')))


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
            rows.append('<li><b>'+esc(step['title'])+'</b> — '+('Earned' if evidence else 'Not earned')+detail+'</li>')
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
