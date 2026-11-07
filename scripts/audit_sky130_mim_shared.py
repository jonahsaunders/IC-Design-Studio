"""Independent native-file readback of the finite shared-bottom MiM class."""
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shlex

ROOT=Path(__file__).resolve().parents[1]


def require(ok,message):
    if not ok:raise ValueError('Shared MiM evidence: '+message)


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def source_files():
    return {p.relative_to(ROOT).as_posix():sha(p) for folder in ('icstudio','scripts')
            for p in sorted((ROOT/folder).rglob('*.py'))}


def inventory(root):
    root=Path(root).absolute()
    require(root.is_dir() and 'tmpuxoell2b' not in root.parts,'missing/forbidden root')
    for p in (*root.parents,root):require(not p.is_symlink() and not p.is_junction(),'linked root')
    files={}
    for folder,dirs,names in os.walk(root,followlinks=False):
        require('tmpuxoell2b' not in (*dirs,*names),'forbidden member')
        for name in (*dirs,*names):
            path=Path(folder)/name;require(not path.is_symlink() and not path.is_junction(),'linked member')
            if name in names:
                relative=path.relative_to(root).as_posix()
                if relative not in ('report.json','verification.json'):
                    require(path.is_file(),'nonregular member');files[relative]=sha(path)
    return files


def geometry(path,plate,angle):
    import klayout.db as db
    layout=db.Layout();layout.read(str(path));top=layout.cell('device_coupon')
    require(top is not None and abs(layout.dbu-.001)<1e-15,'layout top/grid')
    def region(pair):return db.Region(top.begin_shapes_rec(layout.layer(*pair))).merged()
    caps=region((89,44) if plate==1 else (97,44));bottom=region((70,20) if plate==1 else (71,20))
    polygons=list(caps.each());require(len(polygons)==2 and len(list(bottom.each()))==1,'not two caps on one continuous bottom')
    expected=(2000,10000) if angle==0 else (10000,2000)
    boxes=[]
    for cap in polygons:
        box=cap.bbox();require(cap.is_box() and (box.width(),box.height())==expected and
                              (db.Region(cap)-bottom).is_empty(),'written electrode dimensions/containment')
        boxes.append([box.left,box.bottom,box.right,box.top])
    cuts=region((70,44) if plate==1 else (71,44));external=cuts-caps
    require((external-bottom).is_empty(),'bottom cuts leave shared metal')
    groups=[[] for _ in boxes]
    for cut in external.each():
        via=cut.bbox();owners=[]
        for index,box in enumerate(boxes):
            along=(via.bottom>=box[1] and via.top<=box[3]) if angle==0 else (via.left>=box[0] and via.right<=box[2])
            outside=(via.left>box[2] or via.right<box[0]) if angle==0 else (via.bottom>box[3] or via.top<box[1])
            if along and outside:owners.append(index)
        require(len(owners)==1,'written contact must have exactly one owner')
        groups[owners[0]].append([via.left,via.bottom,via.right,via.top])
    for contacts in groups:
        require(len(contacts)==(9 if plate==1 else 1),'written independent bottom-contact group')
    return sorted((box,sorted(contacts)) for box,contacts in zip(boxes,groups))


def raw_graph(text,model,plate):
    """Check the finite coupon's complete native graph, without an RC claim."""
    rows=[shlex.split(line) for line in text.splitlines() if line.strip()]
    kinds={'timestamp':1,'version':1,'tech':1,'style':1,'scale':1,'resistclasses':1,
           'parameters':1,'port':2,'node':2,'substrate':1,'cap':1,'device':2}
    require({kind:sum(row[0]==kind for row in rows) for kind in kinds}==kinds and
            all(row[0] in kinds for row in rows),'incomplete/unknown native graph records')
    def selected(kind):return [row for row in rows if row[0]==kind]
    require(selected('tech')==[['tech','sky130A']] and selected('style')==[['style','ngspice()']] and
            selected('scale')==[['scale','1000','1','1e+06']] and
            selected('parameters')==[['parameters',model,'w=w','l=l']],'native technology/parameter convention')
    require(sorted((row[1],row[2]) for row in selected('port'))==[('N','2'),('P','1')] and
            all(len(row)==8 and row[7]==f'm{plate+3}' for row in selected('port')),'native ordered ports')
    require(sorted(row[1] for row in selected('node'))==['N','P'] and
            all(math.isfinite(float(row[3])) and float(row[3])>=0 for row in selected('node')),'native node set/values')
    sub=selected('substrate')[0];cap=selected('cap')[0]
    require(sub[1:4]==['SUB','0','0'] and sub[6]=='space','native substrate')
    require(len(cap)==4 and set(cap[1:3])=={'P','N'} and math.isfinite(float(cap[3])) and
            float(cap[3])>0,'native coupling topology/value')


def native(folder,plate,angle):
    directory=folder/'job/lvs-extraction';model=f'sky130_fd_pr__cap_mim_m3_{plate}'
    observed=geometry(folder/'job/layout.gds',plate,angle)
    original=(directory/'native-original.ext').read_text(encoding='utf-8')
    corrected=(directory/'device_coupon.ext').read_text(encoding='utf-8')
    raw_graph(original,model,plate)
    old=original.splitlines(keepends=True);new=corrected.splitlines(keepends=True)
    require(len(old)==len(new),'changed raw record count')
    count=0;locations=set();matched=set()
    for before,after in zip(old,new):
        if before.startswith('device '):
            a,b=shlex.split(before),shlex.split(after)
            require(len(a)==len(b)==16 and a[1:3]==b[1:3]==['csubckt',model] and
                    a[10]==b[10]=='P' and a[13]==b[13]=='N','native intrinsic identity/polarity')
            loc=tuple(int(v) for v in a[3:7]);require(loc not in locations,'duplicate native device');locations.add(loc)
            owners=[i for i,(box,_) in enumerate(observed) if all(
                box[0]<=10*loc[n]<=box[2] and box[1]<=10*loc[n+1]<=box[3] for n in (0,2))]
            require(len(owners)==1 and owners[0] not in matched,'native site does not identify one unused written electrode')
            matched.add(owners[0])
            require(a[:7]==b[:7] and a[9:]==b[9:],'changed native topology/non-dimension fields')
            require(a[7:9]==(['w=200','l=1000'] if angle==0 else ['w=1000','l=200']) and
                    b[7:9]==['w=200','l=1000'],'native/corrected dimension convention')
            expected=re.sub(r'\bw=1000(\s+)l=200\b',r'w=200\1l=1000',before) if angle else before
            require(after==expected,'changed native device bytes outside W/L');count+=1
        else:require(after==before,'changed native non-device record')
    require(count==2,'native intrinsic count')
    rows=[r.split() for r in (directory/'extracted.spice').read_text(encoding='utf-8').splitlines()
          if r.strip() and not r.lstrip().startswith('*')]
    require(rows[0]==['.subckt','device_coupon','P','N'] and rows[-1] in (['.ends'],['.ends','device_coupon']),'native exported interface')
    names=set();units=0
    for row in rows[1:-1]:
        require(row[0].startswith('X') and row[0].casefold() not in names and row[1:4]==['P','N',model],'native exported topology')
        names.add(row[0].casefold());values=dict(v.split('=') for v in row[4:])
        require(len(values)==len(row)-4 and set(values)<={'w','l','m'} and
                float(values['w'])==2 and float(values['l'])==10,'native exported dimensions')
        multiplier=float(values.get('m','1'))
        require(math.isfinite(multiplier) and multiplier>0 and multiplier.is_integer(),'native exported multiplicity')
        units+=multiplier
    require(units==2,'native exported count')
    proof=json.loads((directory/'mim-orientation.json').read_text(encoding='utf-8'))
    require(proof['native_sha256']==sha(directory/'native-original.ext') and proof['corrected_sha256']==sha(directory/'device_coupon.ext'), 'normalization provenance')
    require(proof['schema']==1 and proof['model']==model and proof['models']==[model] and
            proof['native_coordinate_nm']==10 and proof['gds_dbu_um']==.001 and
            proof['gds_sha256']==sha(folder/'job/layout.gds') and
            proof['technology_sha256']=='5ee53b96094fe144145bf1216627672747366ec9bef9f2f848304a9a0c77427e' and
            proof['pcell_sha256']=='48d2111c3246cbbed88bca5cf479dd8edc4ce4629d5241cca4102368765da69a','pinned native inputs/grid')
    require([(r['before'],r['after']) for r in proof['changes']]==[(a.rstrip(),b.rstrip()) for a,b in zip(old,new) if a!=b], 'normalization change evidence')
    actual=sorted((row['box'],sorted(row['bottom_contacts'])) for row in proof['electrodes'])
    require(actual==observed and all(row['model']==model and row['axis']==('x' if angle==0 else 'y') and row['shared_bottom_electrodes']==2
                                   for row in proof['electrodes']),'orientation contact ownership evidence')
    require('Property errors were found.' not in (folder/'job/lvs/lvs.log').read_text(encoding='utf-8') and
            'Final result: Circuits match uniquely.' in (folder/'job/lvs/lvs.log').read_text(encoding='utf-8'),'strict native LVS')
    return {'plate':plate,'angle':angle,'intrinsic_units':2,'written_shared_bottom_components':1,
            'normalization_changes':sum(a!=b for a,b in zip(old,new)),
            'native_sha256':sha(directory/'native-original.ext'),'corrected_sha256':sha(directory/'device_coupon.ext')}


def public_drc(folder,public,tool):
    from icstudio.digital_sky130_native import (CATEGORIES_SHA256,DECK_SHA256,FLAGS,
                                               LICENSE_SHA256,REVISION,measured)
    directory=folder/'public-drc'
    for name,digest in (('sky130A_mr.drc',DECK_SHA256),('categories.json',CATEGORIES_SHA256),('GPL-3.0.txt',LICENSE_SHA256)):
        require(sha(directory/name)==digest,'public DRC source identity/notice')
    require(public['source_commit']==REVISION and public['deck_sha256']==DECK_SHA256,'public DRC source claim')
    actual=measured(directory/'report.lyrdb','device_coupon')
    require(actual=={'markers':0,'categories':255,'violations':{}} and public['violations']==0 and
            public['categories']==255 and public['rules']=={},'public DRC result')
    source=PurePosixPath(public['settings']['input']);base=source.parent.parent
    require(source.is_absolute() and '..' not in source.parts and base.name==folder.name and
            source==base/'job/layout.gds','public DRC selected layout')
    expected=dict(input=str(source),top_cell='device_coupon',report=str(base/'public-drc/report.lyrdb'),thr='1',**FLAGS)
    require(public['settings']==expected,'public DRC settings')
    command=[tool,'-b','-r',str(base/'public-drc/sky130A_mr.drc')]
    for key,value in expected.items():command+=['-rd',key+'='+value]
    require(json.loads((directory/'command.json').read_text(encoding='utf-8'))==command,'public DRC command')
    log=(directory/'console.log').read_text(encoding='utf-8')
    require(log.splitlines().count('release 2026.03.30_01.00')==1 and not re.search(r'(?m)^ERROR:',log),'public DRC completion')


def verify(root):
    root=Path(root).absolute();report=json.loads((root/'report.json').read_text(encoding='utf-8'))
    require(report['status']=='OBSERVED' and report['qualified'] is False and report['installed_acceptance'] is False,'outcome/scope')
    require(report['source_files']==source_files(),'changed/incomplete source guard')
    files=inventory(root);require(files and report['files']==files,'changed/incomplete file inventory')
    require(sha(root/'adapter-package.json')=='531c0a4263b839b693d171ad223d01f1484130113f0fcb9010bf99b4c2da9417','unrelated physical adapter')
    package=json.loads((root/'adapter-package.json').read_text(encoding='utf-8'))
    require(report['package']['target']=='sky130A' and report['package']['revision']==package['revision'] and
            report['package']['manifest_sha256']==sha(root/'adapter-package.json'),'physical source claim')
    for name in ('LICENSE-PDK.txt','NOTICE-QUALIFICATION.txt'):
        require(sha(root/('adapter-'+name))==package['files'][name],'changed retained physical notice')
    expected=[(f'p{p}-{mode}-{a}',p,mode,a) for p in (1,2) for mode,a in
              (('positive',0),('positive',90),('missing-contact-group',0),('wrong-width',0),('wrong-count',0))]
    require([(r['name'],r['plate'],r['mode'],r['angle']) for r in report['cases']]==expected,'finite case selection')
    results=[]
    for row in report['cases']:
        folder=root/row['name'];actual=json.loads((folder/'job/report.json').read_text(encoding='utf-8'))
        stages={r['name']:r['status'] for r in actual['stages']}
        require(stages==row['stages'] and actual['status']==row['status'],'actual stage outcome differs')
        require((folder/'reference.spice').read_bytes()==(folder/'job/schematic.spice').read_bytes(),'selected/actual reference differs')
        width=3 if row['mode']=='wrong-width' else 2;count=1 if row['mode']=='wrong-count' else 2
        require((folder/'reference.spice').read_text(encoding='utf-8').split()==
                f'.subckt device_coupon P N X1 P N sky130_fd_pr__cap_mim_m3_{row["plate"]} w={width} l=10 m={count} .ends device_coupon'.split(),
                'reference does not describe the declared finite case')
        project=json.loads((folder/'input.icproj').read_text(encoding='utf-8'));technology=project['pdk']
        require(technology['package_lock']=={k:package[k] for k in ('id','revision','files')} and
                {k:v for k,v in technology.items() if k not in ('package_lock','package_root')}==package['technology'],'unrelated saved physical PDK')
        # The existing imported-layout job binds every retained native input;
        # re-read its declared generated files instead of trusting only status.
        for stage in actual['stages']:
            if stage['name']=='integrity' and stage['status']=='passed':
                for name,value in stage['evidence']['files'].items():
                    require(files.get(row['name']+'/job/'+name)==value,'changed native integrity input')
        if row['mode']=='positive':
            require(actual['status']=='passed' and stages==dict.fromkeys(('preflight','layout_export','drc','lvs_extraction','lvs','integrity'),'passed'),'positive native stages')
            public_drc(folder,row['public_drc'],report['tools']['klayout']['path'])
            results.append(native(folder,row['plate'],row['angle']))
        elif row['mode']=='missing-contact-group':
            require(stages['drc']=='passed' and stages['lvs_extraction']=='failed' and stages['lvs']=='not_run' and
                    'nonempty collinear' in actual['error'],'missing contact accepted or failed for unrelated cause')
        else:
            require(stages['lvs_extraction']=='passed' and stages['lvs']=='failed' and
                    'Property errors were found.' in (folder/'job/lvs/lvs.log').read_text(encoding='utf-8'),'reference fault escaped native LVS')
    return {'status':'PASS','qualified':False,'installed_acceptance':False,'files_verified':len(files),
            'positive_cases':len(results),'missing_contact_controls':2,'native_reference_faults':4,'cases':results}
