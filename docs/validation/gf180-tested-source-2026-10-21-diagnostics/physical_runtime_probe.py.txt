"""Real positive and negative tool checks before marking a runtime ready."""
import json
from pathlib import Path
import re
from .model import atomic_write, design_digest, file_digest, example, digest


def qualify(runtime, directory, progress):
    from .physical_backend import dispatch
    p=example('empty');source=Path(runtime['root'])/'usr/lib/x86_64-linux-gnu/magic/sys'
    technology=source/'scmos.tech'
    p['pdk']['package_root']=str(source)
    p['pdk']['package_lock']={'id':'runtime-scmos-probe','revision':'1','files':{'scmos.tech':file_digest(technology)}}
    job={'project':p,'cell':p['top'],'engine':'builtin','settings':{'type':'physical_probe','physical_runtime':runtime}}
    from . import digital_runtime
    atomic_write(digital_runtime.state_root()/'active-check.json',json.dumps({'directory':str(directory)}))
    result=dispatch(job,directory,lambda fraction,message:progress(message))
    if result['silicon_report']['status']!='passed':raise ValueError('Physical tools installation probe failed.')
    atomic_write(Path(directory)/'result.json',json.dumps(result,indent=2))


def run(job, directory, progress):
    from .engines import execute, tcl_word, netgen_lvs, require_lvs_match
    from .runtime_setup import check_ngspice
    import klayout.db as db
    root=Path(directory)/'physical-flow';root.mkdir()
    tools=job['settings']['tools'];checks=[]
    technology=Path(job['project']['pdk']['package_root'])/'scmos.tech'
    atomic_write(root/'startup.tcl','tech load '+tcl_word(technology)+'\n')
    for name,width in [('legal',20),('narrow',1)]:
        progress(.2,'Checking Magic '+name+' geometry')
        script=f'load {name}\nbox values 0 0 {width} 20\npaint metal1\ndrc check\ndrc catchup\nputs "PROBE_DRC [drc list count total]"\nquit -noprompt\n'
        atomic_write(root/(name+'.tcl'),script)
        log=execute([tools['magic'],'-dnull','-noconsole','-rcfile',root/'startup.tcl'],root,input_text=script)
        atomic_write(root/(name+'.log'),log);counts=re.findall(r'^PROBE_DRC (\d+)$',log,re.M)
        if len(counts)!=1 or ((int(counts[0])==0)!=(name=='legal')):raise ValueError('Magic installation DRC control failed: '+name)
        checks.append({'name':'drc-'+name,'status':'passed','count':int(counts[0])})
    atomic_write(root/'setup.tcl','permute default\nproperty default\n')
    atomic_write(root/'reference.spice','.subckt probe A B\nR1 A B 1000\n.ends probe\n')
    for name,value in [('equal',1000),('wrong',2000)]:
        progress(.6,'Checking Netgen '+name+' circuit')
        atomic_write(root/(name+'.spice'),f'.subckt probe A B\nR1 A B {value}\n.ends probe\n')
        log=netgen_lvs(tools['netgen'],root/'reference.spice','probe',root/(name+'.spice'),'probe',root/'setup.tcl',root/name)
        if name=='equal':require_lvs_match(log)
        elif not re.search(r'Property errors|Netlists do not match|Circuits do not match',log,re.I):
            raise ValueError('Netgen installation negative control did not reject the changed resistor.')
        checks.append({'name':'lvs-'+name,'status':'passed'})
    checks.append({'name':'ngspice','status':check_ngspice(tools['ngspice'])['status']})
    from .klayout_runtime_probe import qualify as qualify_klayout
    progress(.8,'Checking KLayout rule execution and invalid geometry')
    checks.extend(qualify_klayout(tools['klayout'],root/'klayout'))
    report={'status':'passed','design_hash':design_digest(job['project']),
            'qualification':'Runtime tool smoke tests only; no process or design qualification.',
            'stages':checks,'klayout':db.__version__}
    atomic_write(root/'report.json',json.dumps(report,indent=2))
    return {'silicon_report':report,'settings':job['settings'],'design_hash':report['design_hash'],
            'pdk_hash':digest(job['project']['pdk']),'evidence_directory':str(root)}
