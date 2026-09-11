"""Immutable shared checkpoints, object discussions and reproducible run evidence."""
import json
import time
from .model import digest, design_digest
from .live_protocol import ID, LiveError, bounded_project


TABLES=('review_checkpoints','review_comments','review_decisions','review_reports','review_requests')


def install(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS review_checkpoints(id TEXT,workspace TEXT,actor TEXT,name TEXT,
            revision INTEGER,hash TEXT,project TEXT,created REAL,PRIMARY KEY(workspace,id));
        CREATE TABLE IF NOT EXISTS review_comments(id TEXT,workspace TEXT,checkpoint TEXT,actor TEXT,
            cell TEXT,object TEXT,text TEXT,status TEXT,version INTEGER,created REAL,PRIMARY KEY(workspace,id));
        CREATE TABLE IF NOT EXISTS review_decisions(workspace TEXT,checkpoint TEXT,actor TEXT,
            status TEXT,message TEXT,updated REAL,PRIMARY KEY(workspace,checkpoint,actor));
        CREATE TABLE IF NOT EXISTS review_reports(id TEXT,workspace TEXT,checkpoint TEXT,actor TEXT,
            name TEXT,job TEXT,result TEXT,created REAL,PRIMARY KEY(workspace,id));
        CREATE TABLE IF NOT EXISTS review_requests(id TEXT,workspace TEXT,actor TEXT,fingerprint TEXT,
            response TEXT,PRIMARY KEY(workspace,id));
    ''')


def text(value,name,limit,empty=False):
    if not isinstance(value,str) or len(value)>limit or (not empty and not value.strip()) or any(ord(c)<32 and c not in '\n\t' for c in value):
        raise LiveError(name+' must contain '+('0' if empty else '1')+'–'+str(limit)+' printable characters.',400)
    return value.strip()


def checkpoint(db,wid,key):
    row=db.execute('SELECT * FROM review_checkpoints WHERE workspace=? AND id=?',(wid,key)).fetchone()
    if row is None:raise LiveError('Checkpoint unavailable.',404)
    return row


def handle(store,wid,token,request):
    from .live_store import encode
    db=store.db;action=request.get('action');read_only=action in ('list','checkpoint','report')
    actor=store._actor(wid,token,edit=not read_only)
    if action=='list':
        def rows(query):return [dict(r) for r in db.execute(query,(wid,))]
        return dict(checkpoints=rows('SELECT c.id,c.name,c.revision,c.hash,c.created,a.name AS author FROM review_checkpoints c JOIN actors a ON a.id=c.actor WHERE c.workspace=? ORDER BY c.created DESC'),
            comments=rows('SELECT c.*,a.name AS author FROM review_comments c JOIN actors a ON a.id=c.actor WHERE c.workspace=? ORDER BY c.created'),
            decisions=rows('SELECT c.*,a.name AS author FROM review_decisions c JOIN actors a ON a.id=c.actor WHERE c.workspace=? ORDER BY c.updated'),
            reports=rows('SELECT c.id,c.checkpoint,c.name,c.created,a.name AS author FROM review_reports c JOIN actors a ON a.id=c.actor WHERE c.workspace=? ORDER BY c.created'),
            revision=store._workspace(wid)['revision'])
    if action=='checkpoint':
        c=checkpoint(db,wid,request.get('checkpoint'));return dict(project=json.loads(c['project']),revision=c['revision'],hash=c['hash'],name=c['name'])
    if action=='report':
        r=db.execute('SELECT * FROM review_reports WHERE workspace=? AND id=?',(wid,request.get('report'))).fetchone()
        if r is None:raise LiveError('Shared result unavailable.',404)
        return dict(job=json.loads(r['job']),result=json.loads(r['result']),name=r['name'],checkpoint=r['checkpoint'])
    ident=request.get('id')
    if not isinstance(ident,str) or not ID.fullmatch(ident):raise LiveError('A review action needs a stable request ID.',400)
    fingerprint=digest(request)
    prior=db.execute('SELECT * FROM review_requests WHERE workspace=? AND id=?',(wid,ident)).fetchone()
    if prior:
        if prior['actor']!=actor['id'] or prior['fingerprint']!=fingerprint:raise LiveError('Request identity was already used.')
        return json.loads(prior['response'])
    if db.execute('SELECT count(*) FROM review_requests WHERE workspace=?',(wid,)).fetchone()[0]>=5000:raise LiveError('Workspace review history is full. Start a new workspace.',429)
    if action=='create_checkpoint':
        w=store._workspace(wid)
        if type(request.get('revision')) is not int or request['revision']!=w['revision']:raise LiveError('The shared layout changed. Synchronize before making a checkpoint.')
        count,size=db.execute('SELECT count(*),coalesce(sum(length(project)),0) FROM review_checkpoints WHERE workspace=?',(wid,)).fetchone()
        if count>=25 or size+len(w['project'].encode())>64*1024*1024:raise LiveError('Workspace checkpoint storage is full. Export a copy and start a new workspace.',429)
        name=text(request.get('name'),'Checkpoint name',100)
        if db.execute('SELECT 1 FROM review_checkpoints WHERE workspace=? AND lower(name)=lower(?)',(wid,name)).fetchone():raise LiveError('Choose a different checkpoint name.')
        project=json.loads(w['project']);hash_=design_digest(project)
        db.execute('INSERT INTO review_checkpoints VALUES(?,?,?,?,?,?,?,?)',(ident,wid,actor['id'],name,w['revision'],hash_,w['project'],time.time()))
        response=dict(id=ident,revision=w['revision'],hash=hash_)
    elif action=='comment':
        c=checkpoint(db,wid,request.get('checkpoint'));project=json.loads(c['project'])
        cid=request.get('cell','');obj=request.get('object','')
        if cid:
            cell=next((cell for cell in project['cells'] if cell['id']==cid),None)
            if cell is None:raise LiveError('The selected cell is absent from this checkpoint.')
            ids={o['id'] for field in ('devices','shapes','wires','layout_instances','layout_pins') for o in cell.get(field,[]) if 'id' in o}
            if obj and obj not in ids:raise LiveError('The selected object is absent from this checkpoint.')
        elif obj:raise LiveError('An object comment also needs its cell.',400)
        if db.execute('SELECT count(*) FROM review_comments WHERE workspace=?',(wid,)).fetchone()[0]>=500:raise LiveError('Workspace comment limit reached.',429)
        message=text(request.get('text'),'Comment',4000)
        db.execute('INSERT INTO review_comments VALUES(?,?,?,?,?,?,?,?,?,?)',(ident,wid,c['id'],actor['id'],cid,obj,message,'open',1,time.time()))
        response=dict(id=ident,version=1)
    elif action=='resolve_comment':
        row=db.execute('SELECT * FROM review_comments WHERE workspace=? AND id=?',(wid,request.get('comment'))).fetchone()
        if row is None:raise LiveError('Comment unavailable.',404)
        if row['actor']!=actor['id'] and actor['role']!='owner':raise LiveError('Only the comment author or workspace owner can resolve it.',403)
        if request.get('version')!=row['version']:raise LiveError('The comment changed. Refresh before updating it.')
        status=request.get('status')
        if status not in ('open','resolved'):raise LiveError('Choose open or resolved.',400)
        db.execute('UPDATE review_comments SET status=?,version=version+1 WHERE workspace=? AND id=?',(status,wid,row['id']))
        response=dict(id=row['id'],version=row['version']+1)
    elif action=='decide':
        c=checkpoint(db,wid,request.get('checkpoint'));status=request.get('status')
        if status not in ('approved','changes_requested','review_requested'):raise LiveError('Choose a review decision.',400)
        message=text(request.get('text',''),'Review note',2000,True)
        db.execute('INSERT OR REPLACE INTO review_decisions VALUES(?,?,?,?,?,?)',(wid,c['id'],actor['id'],status,message,time.time()))
        response=dict(checkpoint=c['id'],status=status)
    elif action=='share_report':
        c=checkpoint(db,wid,request.get('checkpoint'));job=request.get('job');result=request.get('result')
        if not isinstance(job,dict) or not isinstance(result,dict):raise LiveError('Choose a completed run with its saved input.',400)
        if len(encode(dict(job=job,result=result)).encode())>4*1024*1024:raise LiveError('The shared run exceeds 4 MiB. Export its evidence separately.',413)
        p=bounded_project(job.get('project'));input_hash=design_digest(p);base_hash=job.get('case',{}).get('base_design_hash',input_hash)
        if (p['id']!=json.loads(c['project'])['id'] or base_hash!=c['hash'] or result.get('design_hash')!=input_hash or
            result.get('project_id')!=p['id'] or result.get('cell_id')!=job.get('cell')):raise LiveError('The result does not match this checkpoint and its saved input.')
        if job.get('engine') not in ('builtin','ngspice') or job.get('settings',{}).get('type') not in ('op','tran','dc','ac','noise','testbench','silicon'):
            raise LiveError('Share a simulation or saved-testbench physical verification with portable settings.')
        if db.execute('SELECT count(*) FROM review_reports WHERE workspace=?',(wid,)).fetchone()[0]>=16:raise LiveError('Workspace shared-result limit reached.',429)
        name=text(request.get('name'),'Result name',100)
        # Local executable and run paths never become instructions on a teammate's machine.
        safe_job={k:v for k,v in job.items() if k in ('project','cell','settings','engine','case')}
        safe_job['settings']={k:v for k,v in job['settings'].items() if k not in ('executable','tools','directory','deck')}
        db.execute('INSERT INTO review_reports VALUES(?,?,?,?,?,?,?,?)',(ident,wid,c['id'],actor['id'],name,encode(safe_job),encode(result),time.time()))
        response=dict(id=ident,input_hash=input_hash)
    else:raise LiveError('Unknown review action.',400)
    db.execute('INSERT INTO review_requests VALUES(?,?,?,?,?)',(ident,wid,actor['id'],fingerprint,encode(response)))
    return response
