"""Teaching material and a readable, honest portfolio, separate from grading."""
import html
import json

from .model import atomic_write, now


def study_guide(data):
    from .getting_started import resource_root
    content = json.loads((resource_root()/'examples/student-hub/study-guide.json').read_text(encoding='utf-8'))
    ids = {lesson['id'] for lesson in data['lessons']}
    if set(content['lessons']) != ids:
        raise ValueError('Every lesson needs teaching material in the study guide.')
    for note in content['lessons'].values():
        for field in ('concept','worked_example','try_next','interview','artifact'):
            if not isinstance(note.get(field),str) or not note[field].strip():
                raise ValueError('Incomplete lesson teaching material: '+field)
    return content


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
