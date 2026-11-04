"""Compare physical contacts with independently shorted residue-only C matrices."""
from pathlib import Path
from collections import defaultdict
import argparse,json,math,shlex,subprocess,sys
import klayout.db as k
repo=Path(__file__).resolve().parents[1];sys.path.insert(0,str(repo))
from icstudio.model import file_digest
from icstudio.engines import tcl_word
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--baseline',required=True);ap.add_argument('--candidate',required=True);ap.add_argument('--out',type=Path,required=True)
args=ap.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
tech=repo/'icstudio/assets/pdks/gf180mcuC/libs.tech/magic/gf180mcuC.tech'
engines={'reference':str(Path(args.baseline).resolve()),'old_contact':str(Path(args.baseline).resolve()),'new_contact':str(Path(args.candidate).resolve())}
report=dict(status='running',qualified=False,script_sha256=file_digest(Path(__file__)),technology_sha256=file_digest(tech),cases=[],limits=dict(relative=1e-5,absolute_af=1e-10),
    engine_sha256={name:file_digest(path) for name,path in engines.items()},
    scope='Native material primitive (not a manufacturing-rule fixture), with exact saved-Magic residue geometry checks. Contact helper consistency with an independently extracted residue-only geometry, after mathematically shorting the two source conductors. No foundry accuracy claim.')
def retain():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
def matrix(path):
    rows=[shlex.split(l) for l in path.read_text().splitlines() if l.strip()];scale=next(float(r[2]) for r in rows if r[0]=='scale');data=defaultdict(list)
    rename=lambda n:'A' if n in ('A0','A1') else n
    def edge(a,b,c):
        if a==b:return
        for key,sign in (((a,a),1),((b,b),1),((a,b),-1),((b,a),-1)):data[key].append(sign*c)
    for r in rows:
        if r[0] in ('node','substrate'):edge(rename(r[1]),'SUB',float(r[3])*scale)
        elif r[0]=='cap':edge(rename(r[1]),rename(r[2]),float(r[3])*scale)
    return {p:math.fsum(v) for p,v in data.items()}
try:
    for rotation in range(4):
        for case in ('absent','full_single','full_partition','half','gap_partition'):
            row=dict(case=case,rotation=rotation,variants={});report['cases'].append(row);retain();matrices={}
            for variant,engine in engines.items():
                folder=out/(case+'-'+str(rotation))/variant;folder.mkdir(parents=True)
                ly=k.Layout();ly.dbu=.001;top=ly.create_cell('contact_control')
                def shape(layer,rect,label=None):
                    top.shapes(ly.layer(layer,0)).insert(rect)
                    if label:top.shapes(ly.layer(layer,10)).insert(k.Text(label,k.Trans(rect.center())))
                source=k.Box(9995,9995,20005,20005) if variant=='reference' else k.Box(10000,10000,20000,20000);shape(34,source,'A1');shape(30,source,'A0');shape(46,k.Box(22000,11000,24000,19000),'B')
                if variant!='reference':shape(33,source)
                if case=='full_single':shape(42,k.Box(8000,8000,26000,22000))
                elif case in ('full_partition','gap_partition'):
                    shape(42,k.Box(8000,8000,26000,13235));shape(36,k.Box(8000,13235+(5 if case=='gap_partition' else 0),26000,22000))
                elif case=='half':shape(42,k.Box(8000,8000,26000,13235))
                top.transform(k.Trans(rotation,False,0,0));ly.write(str(folder/'coupon.gds'))
                (folder/'startup.tcl').write_text('drc off\ntech load '+tcl_word(tech)+'\n')
                body='scalegrid 1 10\ngds read '+tcl_word(folder/'coupon.gds')+'\nload contact_control\nselect top cell\nextract do capacitance\nextract do coupling\nextract no resistance\nextract all\nsave contact_control\ngds write '+tcl_word(folder/'imported.gds')+'\nputs CONTACT_CONTROL_COMPLETE\n'
                (folder/'extract.tcl').write_text('if {[catch {\n'+body+'} err]} {puts "CONTACT_CONTROL_ERROR $err"}\nquit -noprompt\n')
                command=[engine,'-dnull','-noconsole','-rcfile',str(folder/'startup.tcl'),str(folder/'extract.tcl')]
                with (folder/'engine.log').open('w') as log:p=subprocess.run(command,cwd=folder,stdout=log,stderr=subprocess.STDOUT,timeout=120)
                log=(folder/'engine.log').read_text();assert p.returncode==0 and 'CONTACT_CONTROL_COMPLETE' in log and 'CONTACT_CONTROL_ERROR' not in log
                def native_regions(path):
                    regions={};kind=None;factor=10
                    aliases={'polysilicon':'p','polycontact':'pc','metal1':'m1','metal2':'m2','metal3':'m3','metal4':'m4'}
                    for line in path.read_text().splitlines():
                        if line.startswith('magscale '):
                            num,den=map(int,line.split()[1:]);assert 10*num%den==0;factor=10*num//den
                        elif line.startswith('<< '):kind=aliases.get(line[3:-3],line[3:-3])
                        elif line.startswith('rect '):
                            if kind=='checkpaint':continue
                            assert kind in ('p','pc','m1','m2','m3','m4'),kind
                            for material in (('p','m1') if kind=='pc' else (kind,)):
                                regions.setdefault(material,k.Region()).insert(k.Box(*(int(v)*factor for v in line.split()[1:])))
                        elif line.startswith('tri '):raise AssertionError('Unexpected nonrectangular primitive.')
                    return {n:v.merged() for n,v in regions.items()}
                native=native_regions(folder/'contact_control.mag')
                if variant=='reference':reference_native=native
                else:
                    assert all((native.get(n,k.Region())^reference_native.get(n,k.Region())).is_empty() for n in native.keys()|reference_native.keys()),'Native residue geometry differs.'
                m=matrix(folder/'contact_control.ext');matrices[variant]=m
                row['variants'][variant]=dict(command=command,exit_code=p.returncode,native_residue_regions_match=True,native_mag_sha256=file_digest(folder/'contact_control.mag'),signal_coupling_af=-m.get(('A','B'),0.),ext_sha256=file_digest(folder/'contact_control.ext'),gds_sha256=file_digest(folder/'coupon.gds'),imported_gds_sha256=file_digest(folder/'imported.gds'))
            ref,new,old=(matrices[v] for v in ('reference','new_contact','old_contact'));keys=ref.keys()|new.keys()
            row['matrix_matches_reference']=all(math.isclose(ref.get(p,0.),new.get(p,0.),rel_tol=1e-5,abs_tol=1e-10) for p in keys)
            oldkeys=ref.keys()|old.keys()
            row['baseline_matches_reference']=all(math.isclose(ref.get(p,0.),old.get(p,0.),rel_tol=1e-5,abs_tol=1e-10) for p in oldkeys)
            row['expected_baseline_fault_detected']=row['baseline_matches_reference'] if case=='absent' else not row['baseline_matches_reference']
            row['maximum_difference_af']=max(abs(ref.get(p,0.)-new.get(p,0.)) for p in keys)
            row['differences']=[dict(a=p[0],b=p[1],reference=ref.get(p,0.),candidate=new.get(p,0.)) for p in sorted(keys) if not math.isclose(ref.get(p,0.),new.get(p,0.),rel_tol=1e-5,abs_tol=1e-10)]
            ab=-new.get(('A','B'),0.);row['passed']=row['matrix_matches_reference'] and row['expected_baseline_fault_detected'] and (abs(ab)<1e-10 if case.startswith('full') else ab>0)
            retain();print(json.dumps(dict(case=case,rotation=rotation,signals={k:v['signal_coupling_af'] for k,v in row['variants'].items()},passed=row['passed'],max_error=row['maximum_difference_af'])),flush=True)
    assert len(report['cases'])==20 and all(r['passed'] for r in report['cases']);report['baseline_faults_detected']=sum(not r['baseline_matches_reference'] for r in report['cases']);report['status']='native-contact-shield-controls-passed';retain()
except BaseException as exc:report.update(status='failed',error=str(exc));retain();raise
