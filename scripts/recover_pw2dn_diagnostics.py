"""Temporary, pinned, read-only Actions artifact recovery. Never executes artifact data."""
from __future__ import annotations
import argparse, hashlib, json, os, re, stat, tempfile, time, urllib.request, urllib.error, urllib.parse, zipfile
from pathlib import Path, PurePosixPath

REPO='jonahsaunders/IC-Design-Studio'
RUN=42850869471
ARTIFACT=13810605104
HEAD='eb0018c9c024588358b3f4f12f0af6a0581da937'
SIZE=1552333914
DIGEST='fc5a688b8aa85b6770b1164238399da0e89dc35d603f8b7ec1259c29dc18a6af'
PREFIXES=('windows-evidence/', 'build/windows-evidence/')
MEMBERS=('pw2dn/reference-launcher.log','pw2dn/reference-invocation.json','pw2dn/native-references/failure.json')
MAX_MEMBER=8*1024*1024
TAIL=64*1024
MAX_ENTRIES=100000
MAX_OUTPUT=256*1024
FIELDS={'status','returncode','exit_code','timed_out','error','message','exception','reason','stage','schema','candidate_commit','commit','execution_id'}
SENSITIVE=re.compile(r'(?i)(password|passwd|secret|token|authorization|credential|cookie|private.?key|api.?key)')

def require(value,message):
    if not value:raise ValueError(message)

def digest(data):return hashlib.sha256(data).hexdigest()
def write(path,value):
    data=(json.dumps(value,indent=2,allow_nan=False)+'\n').encode('utf-8')
    if len(data)>TAIL:data=b'{"status":"sanitized_projection_exceeds_cap","details_omitted":true}\n'
    path.write_bytes(data)

def redact(value):
    text=str(value)[:TAIL]
    lines=[]
    for line in text.splitlines():
        if SENSITIVE.search(line):lines.append('[redacted sensitive-key line]');continue
        line=re.sub(r'https?://\S+', '[redacted URL]', line)
        line=re.sub(r'\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)\b','[redacted credential]',line)
        lines.append(line[:2048])
    return '\n'.join(lines)

def project_json(data):
    value=json.loads(data)
    require(isinstance(value,dict),'Expected JSON object')
    # Reject nested values rather than stringifying secrets hidden in structures.
    return {key:redact(v) if isinstance(v,str) else v for key,v in value.items()
            if key in FIELDS and (v is None or type(v) in (str,int,bool))}

def project_log(data):
    text=data[-TAIL:].decode('utf-8',errors='replace')
    lines=[]
    for line in text.splitlines():
        # Only diagnostic structure and exception text. Never echo commands/env dumps.
        if re.match(r'^\s*(Traceback \(|File ["\']|[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception):)',line):
            lines.append(redact(line))
    return {'tail_bytes':min(len(data),TAIL),'tail_truncated':len(data)>TAIL,
            'projection':'traceback/file/exception lines only; other lines omitted',
            'lines':lines}

def metadata(run,artifact):
    require(run.get('id')==RUN and run.get('head_sha')==HEAD,'Run identity mismatch')
    require(run.get('repository',{}).get('full_name')==REPO and run.get('head_repository',{}).get('full_name')==REPO,'Run repository mismatch')
    require(run.get('status')=='completed' and run.get('conclusion')=='failure','Run not expected completed failure')
    require(artifact.get('id')==ARTIFACT and artifact.get('size_in_bytes')==SIZE and artifact.get('digest')=='sha256:'+DIGEST and artifact.get('expired') is False,'Artifact identity mismatch')
    wr=artifact.get('workflow_run',{})
    require(wr.get('id')==RUN and wr.get('head_sha')==HEAD,'Artifact run mismatch')
    require(wr.get('repository_id')==run['repository'].get('id') and wr.get('head_repository_id')==run['head_repository'].get('id'),'Artifact repository ID mismatch')

def inspect_archive(archive,output):
    reports=[]
    with zipfile.ZipFile(archive) as z:
        infos=z.infolist();require(len(infos)<=MAX_ENTRIES,'Too many archive entries')
        names=set();selected={}
        for info in infos:
            name=info.filename;parts=PurePosixPath(name).parts
            require(name and not name.startswith('/') and '\\' not in name and ':' not in name and all(p not in ('','..','.') for p in name.rstrip('/').split('/')),'Unsafe archive path')
            key=name.rstrip('/').casefold();require(key not in names,'Duplicate/case-colliding archive member');names.add(key)
            mode=info.external_attr>>16
            require(not stat.S_ISLNK(mode),'Linked archive member')
            require(not (info.flag_bits&1),'Encrypted archive member')
            for member in MEMBERS:
                if name in tuple(prefix+member for prefix in PREFIXES):
                    require(member not in selected,'Ambiguous allowlisted member')
                    require(not info.is_dir() and info.file_size<=MAX_MEMBER,'Oversized/nonfile diagnostic')
                    require(stat.S_IFMT(mode) in (0,stat.S_IFREG),'Unsupported diagnostic member type')
                    selected[member]=info
        for member in MEMBERS:
            info=selected.get(member)
            if info is None:reports.append({'member':member,'status':'missing','searched_exact_names':[p+member for p in PREFIXES]});continue
            with z.open(info) as f:data=f.read(MAX_MEMBER+1)
            require(len(data)==info.file_size and len(data)<=MAX_MEMBER,'Member size mismatch')
            try:projected=project_log(data) if member.endswith('.log') else project_json(data)
            except (ValueError,UnicodeError):projected={'status':'invalid_json','details_omitted':True}
            name=member.replace('/','__')+'.sanitized.json';write(output/name,projected)
            reports.append({'member':member,'archive_member':info.filename,'status':'recovered','original_bytes':len(data),'original_sha256':digest(data),'output':name,'output_sha256':digest((output/name).read_bytes())})
    return reports

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def api(path,token,redirect=False):
    require(path.startswith('/repos/'+REPO+'/actions/'),'Unapproved API path')
    request=urllib.request.Request('https://api.github.com'+path,headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'})
    try:response=urllib.request.build_opener(NoRedirect).open(request,timeout=60)
    except urllib.error.HTTPError as exc:
        if redirect and exc.code in (301,302,303,307,308):
            return artifact_url(exc.headers.get('Location',''))
        raise ValueError('GitHub API request failed with HTTP '+str(exc.code)) from None
    with response:
        data=response.read(2*1024*1024+1);require(len(data)<=2*1024*1024,'Oversized API metadata');return json.loads(data)

def artifact_url(url):
    parsed=urllib.parse.urlsplit(url)
    host=parsed.hostname or ''
    require(parsed.scheme=='https' and parsed.username is None and parsed.password is None and parsed.port in (None,443) and not parsed.fragment, 'Invalid signed artifact URL')
    require(bool(re.fullmatch(r'[a-z0-9-]+\.blob\.core\.windows\.net|[a-z0-9.-]+\.actions\.githubusercontent\.com',host)), 'Unrecognized artifact download host')
    return url

def download(url,path):
    # Signed artifact URL uses NO Authorization header; never retain/print URL.
    total=0;sha=hashlib.sha256();deadline=time.monotonic()+1200
    with urllib.request.build_opener(NoRedirect).open(artifact_url(url),timeout=60) as response,path.open('xb') as target:
        require(response.geturl().startswith('https://'),'Non-HTTPS archive response')
        while True:
            require(time.monotonic()<deadline,'Archive download deadline exceeded')
            block=response.read(1024*1024)
            if not block:break
            total+=len(block);require(total<=SIZE,'Archive exceeds pinned size');sha.update(block);target.write(block)
    require(total==SIZE and sha.hexdigest()==DIGEST,'Archive size/digest mismatch')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();out=args.output
    require(not out.exists(),'Output must be fresh');out.mkdir(parents=True)
    receipt={'schema':1,'scope':'TEMPORARY_READ_ONLY_PINNED_PW2DN_DIAGNOSTICS','repository':REPO,'run_id':RUN,'artifact_id':ARTIFACT,'candidate_sha':HEAD,'archive_sha256':DIGEST,'archive_bytes':SIZE,'status':'failed','source_script_sha256':digest(Path(__file__).read_bytes()),'limitations':'Sanitized narrow projection, not complete original logs. Missing files reported without substituting another run/artifact.'}
    try:
        token=os.environ.get('GH_TOKEN','');require(bool(token),'Missing ephemeral Actions token')
        receipt['stage']='metadata'
        run=api(f'/repos/{REPO}/actions/runs/{RUN}',token);artifact=api(f'/repos/{REPO}/actions/artifacts/{ARTIFACT}',token);metadata(run,artifact)
        with tempfile.TemporaryDirectory(prefix='pw2dn-recovery-') as tmp:
            receipt['stage']='archive_download'
            archive=Path(tmp)/'artifact.zip';download(api(f'/repos/{REPO}/actions/artifacts/{ARTIFACT}/zip',token,True),archive)
            receipt['archive_verified']=True;receipt['stage']='allowlisted_projection';receipt['members']=inspect_archive(archive,out)
        receipt['status']='complete'
    except Exception as exc:
        receipt['error_type']=type(exc).__name__;receipt['error']='Recovery failed at retained stage; exception text intentionally omitted to protect signed URLs and headers';raise RuntimeError('Pinned recovery failed; inspect sanitized manifest') from None
    finally:
        write(out/'manifest.json',receipt)
        require(sum(p.stat().st_size for p in out.iterdir() if p.is_file())<=MAX_OUTPUT,'Compact output exceeds cap')
if __name__=='__main__':main()
