"""Narrow push/manual identity guard for build-only private WSL preparation."""
from pathlib import Path
import hashlib,json,os,re,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
BRANCH='refs/heads/codex/chunk7-blockers-20261108'
def validate(event,ref,expected,actual,request,policy):
 if not re.fullmatch('[0-9a-f]{40}',expected or '') or actual!=expected:raise ValueError('Immutable candidate mismatch')
 if event not in ('push','workflow_dispatch') or ref!=BRANCH:raise ValueError('Only selected research branch push/manual preparation')
 if set(request)!={'schema','purpose','policy_sha256','native_execution','request_id'} or request['schema']!=1 or request['purpose']!='BUILD_PREPARATION_ONLY' or request['native_execution'] is not False:raise ValueError('Request exceeds build-only scope')
 if not isinstance(request['request_id'],str) or not re.fullmatch('[A-Za-z0-9_-]{1,64}',request['request_id']):raise ValueError('Invalid preparation request ID')
 if hashlib.sha256(policy).hexdigest()!=request['policy_sha256']:raise ValueError('Request policy digest mismatch')
 if json.loads(policy)['review_state']!='APPROVED_FOR_BUILD_ONLY':raise ValueError('Policy not approved')
 return {'commit':actual,'scope':'BUILD_PREPARATION_ONLY','policy_sha256':request['policy_sha256'],'native_execution':False}
def main():
 base=ROOT/'docs/research/ihp-wsl-experimental';actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
 result=validate(os.environ['GITHUB_EVENT_NAME'],os.environ['GITHUB_REF'],os.environ['GITHUB_SHA'],actual,json.loads((base/'prepare-request.json').read_text()),(base/'build-policy.json').read_bytes())
 print(json.dumps(result))
 if os.environ.get('GITHUB_OUTPUT'):
  with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('policy_sha256='+result['policy_sha256']+'\n')
if __name__=='__main__':main()
