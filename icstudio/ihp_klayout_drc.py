"""Run both unmodified public IHP geometry decks with their complete sources.

This is a selectable geometry check, independent of Magic. It supplies no
antenna, density, electrical reliability or complete-chip signoff claim.
"""
import json
from pathlib import Path
import re
import shutil

from .model import atomic_write, file_digest

SOURCE=Path(__file__).parent/'assets/physical/ihp_klayout_drc'
LOCK_SHA256='31601ee4ca33750dd2f580f6a8fc519bb5dbe99d504e72759fd97d538f4f3863'
COMMIT='5e6d592e4002946a4616f798c357f0f3c06cf3b6'
ENTRIES={'main':'ihp-sg13g2.drc','maximal':'rule_decks/sg13g2_maximal.drc'}


def assets(root=None):
    root=Path(root or SOURCE).resolve();lock=root/'SOURCE.json'
    if not lock.is_file() or lock.is_symlink() or file_digest(lock)!=LOCK_SHA256:
        raise ValueError('Missing or changed public IHP DRC source lock.')
    data=json.loads(lock.read_bytes());result={'SOURCE.json':lock}
    for name,record in data['files'].items():
        path=root/name
        if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file() or file_digest(path)!=record['sha256']:
            raise ValueError('Missing or changed IHP DRC dependency: '+name)
        result[name]=path
    return result


def copy_assets(destination):
    destination=Path(destination)
    for name,path in assets().items():
        target=destination/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    assets(destination)


def read_report(path):
    # A fresh Windows receipt reader has not opened a layout. Register the
    # native geometry types before asking RDB for edge pairs and polygons.
    import klayout.db
    from .klayout_verification import read_report as read
    return read(path)


def drc(executable,source,top,output):
    from .engines import execute
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=False)
    source=Path(source).resolve();before=file_digest(source)
    version=execute([str(executable),'-v'],out,timeout=20).strip()
    match=re.search(r'KLayout (\d+)\.(\d+)\.(\d+)',version)
    if not match or tuple(map(int,match.groups()))<(0,30,5):
        raise ValueError('The public IHP geometry decks require KLayout 0.30.5 or newer.')
    bundle=out/'rules';copy_assets(bundle);rows=[]
    for name,entry in ENTRIES.items():
        folder=out/name;folder.mkdir();report=folder/'findings.lyrdb'
        command=[str(executable),'-b','-r',str(bundle/entry)]
        settings=dict(input=str(source),topcell=top,report=str(report),log=str(folder/'native.log'),
                      run_mode='flat',threads=1,drc_json=str(bundle/'sg13g2_tech_mod.json'),
                      drc_json_default=str(bundle/'rule_decks/sg13g2_tech_default.json'))
        for key,value in settings.items():command+=['-rd',str(key)+'='+str(value)]
        atomic_write(folder/'command.json',json.dumps(command,indent=2))
        try:log=execute(command,folder,timeout=600)
        except Exception as error:atomic_write(folder/'console.log',str(error));raise
        atomic_write(folder/'console.log',log)
        marker="KLayout DRC run for tables 'main' completed in" if name=='main' else 'KLayout DRC run for maximum ruleSet completed in'
        if marker not in log or not report.is_file():
            raise ValueError('The public IHP '+name+' DRC deck did not finish.')
        if name=='main' and any(f'{switch} enabled: true' not in log for switch in ('FEOL','BEOL','OFFGRID','ANGLE','PIN','FORBIDDEN','RECOMMENDED')):
            raise ValueError('The public IHP main geometry switches were not all enabled.')
        parsed=read_report(report)
        if parsed['top']!=top:raise ValueError('The public IHP DRC report belongs to another top cell.')
        rows.append(dict(name=name,entry=entry,violations=parsed['count'],report=name+'/findings.lyrdb',
                         report_sha256=parsed['report_sha256'],categories=sorted({f['rule'] for f in parsed['findings']})))
    assets(bundle)
    if file_digest(source)!=before:raise ValueError('Layout changed during public IHP geometry checks.')
    result=dict(schema=1,engine=version,source_commit=COMMIT,source_lock_sha256=LOCK_SHA256,
                input_sha256=before,top=top,violations=sum(r['violations'] for r in rows),decks=rows,
                scope='Complete unmodified public main and maximal geometry decks, default rule switches. Antenna, density and fabrication qualification are separate.')
    atomic_write(out/'result.json',json.dumps(result,indent=2));return result
