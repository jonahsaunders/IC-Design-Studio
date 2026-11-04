"""Native rectangular fringe controls; diagonal bounds have a separate runner."""
import argparse,json,math
from pathlib import Path
import shlex,subprocess,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import file_digest
from icstudio.engines import tcl_word
import klayout.db as k
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--baseline',required=True);ap.add_argument('--candidate',required=True);ap.add_argument('--out',type=Path,required=True)
args=ap.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
tech=ROOT/'icstudio/assets/pdks/gf180mcuC/libs.tech/magic/gf180mcuC.tech'
report=dict(status='running',qualified=False,scope='GF180 C rectangular fringe-shield representation controls, not calibrated field accuracy or complete extraction qualification.',
    required_additional_controls=['qualify_magic_diagonal_shielding.py'],
    script_sha256=file_digest(Path(__file__)),technology_sha256=file_digest(tech),cases=[],
    limits=dict(matrix_relative=1e-5,matrix_absolute_af=1e-12,reason='Bounded comparison of six-significant-digit native records; exact complete shields must have zero A/B coupling, and one-grid gaps must remain positive.'))
def retain():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
retain()
def shapes(case,rotation,folder):
    ly=k.Layout();ly.dbu=.001;top=ly.create_cell('shield_control');foot=k.Box(8000,8000,26000,22000)
    def box(layer,rect,label=None):
        top.shapes(ly.layer(layer,0)).insert(rect)
        if label:top.shapes(ly.layer(layer,10)).insert(k.Text(label,k.Trans(rect.center())))
    box(42,k.Box(10000,10000,20000,20000),'A');box(30,k.Box(22000,11000,24000,19000),'B')
    shield=k.Region();cut=13235
    if case=='full_single':box(36,foot);shield.insert(foot)
    elif case in ('full_partition','gap_partition'):
        lower=k.Box(8000,8000,26000,cut);upper=k.Box(8000,cut+(5 if case=='gap_partition' else 0),26000,22000)
        box(36,lower);box(34,upper);shield.insert(lower);shield.insert(upper)
    elif case=='half':
        rect=k.Box(8000,8000,26000,cut);box(36,rect);shield.insert(rect)
    elif case=='split':
        poly=k.Polygon([k.Point(8000,8000),k.Point(26000,8000),k.Point(8000,26000)])
        top.shapes(ly.layer(36,0)).insert(poly);shield.insert(poly)
    else:assert case=='absent'
    missing=k.Region(foot)-shield
    assert missing.is_empty()==case.startswith('full_')
    top.transform(k.Trans(rotation,False,0,0));ly.write(str(folder/'coupon.gds'))
    return dict(missing_shield_area_dbu2=missing.area(),gds_grid_um=ly.dbu,native_grid_um=.005,gds_sha256=file_digest(folder/'coupon.gds'))
def coupling(path):
    result={};rows=[shlex.split(l) for l in path.read_text().splitlines() if l.strip()]
    scale=next(float(t[2]) for t in rows if t[0]=='scale')
    for t in rows:
        if t[0]=='cap':result.setdefault(tuple(sorted(t[1:3])),[]).append(float(t[3])*scale)
    return {p:math.fsum(v) for p,v in result.items()}
try:
    for rotation in range(4):
        for name in ('absent','full_single','full_partition','gap_partition','half'):
            folder=out/(name+'-'+str(rotation));folder.mkdir();row=dict(case=name,rotation=rotation,geometry=shapes(name,rotation,folder),variants={});report['cases'].append(row);retain()
            matrices={}
            for variant in ('baseline','candidate'):
                target=folder/variant;target.mkdir();(target/'startup.tcl').write_text('drc off\ntech load '+tcl_word(tech)+'\n')
                body='scalegrid 1 10\ngds read '+tcl_word(folder/'coupon.gds')+'\nload shield_control\nselect top cell\nextract do capacitance\nextract do coupling\nextract no resistance\nextract all\ngds write '+tcl_word(target/'imported.gds')+'\nputs SHIELD_CONTROL_COMPLETE\n'
                (target/'extract.tcl').write_text('if {[catch {\n'+body+'} err]} {puts "SHIELD_CONTROL_ERROR $err"}\nquit -noprompt\n')
                cmd=[str(Path(getattr(args,variant)).resolve()),'-dnull','-noconsole','-rcfile',str(target/'startup.tcl'),str(target/'extract.tcl')]
                with (target/'engine.log').open('w') as log:proc=subprocess.run(cmd,cwd=target,stdout=log,stderr=subprocess.STDOUT,timeout=120)
                log=(target/'engine.log').read_text();assert proc.returncode==0 and 'SHIELD_CONTROL_COMPLETE' in log and 'SHIELD_CONTROL_ERROR' not in log
                actual=k.Layout();actual.read(str(target/'imported.gds'))
                original=k.Layout();original.read(str(folder/'coupon.gds'))
                def region(layout,layer):
                    idx=layout.find_layer(layer,0)
                    return k.Region() if idx is None else k.Region(layout.top_cell().begin_shapes_rec(idx)).merged()
                assert actual.dbu==original.dbu==.001
                assert all((region(actual,layer)^region(original,layer)).is_empty() for layer in (30,34,36,42)), 'Native import changed physical masks.'
                matrices[variant]=coupling(target/'shield_control.ext');ab=matrices[variant].get(('A','B'),0.)
                row['variants'][variant]=dict(command=cmd,exit_code=proc.returncode,imported_physical_masks_unchanged=True,imported_gds_sha256=file_digest(target/"imported.gds"),signal_coupling_af=ab,ext_sha256=file_digest(target/'shield_control.ext'),log_sha256=file_digest(target/'engine.log'))
                retain()
            old,new=matrices['baseline'],matrices['candidate'];keys=old.keys()|new.keys()
            row['matrix_matches']=all(math.isclose(old.get(p,0.),new.get(p,0.),rel_tol=1e-5,abs_tol=1e-12) for p in keys)
            row['maximum_change_af']=max((abs(old.get(p,0.)-new.get(p,0.)) for p in keys),default=0.)
            value=row['variants']['candidate']['signal_coupling_af']
            row['expected_signal_response']='zero' if name.startswith('full_') else 'positive'
            row['passed']=row['matrix_matches'] and all(v>=0 for v in new.values()) and (value==0 if name.startswith('full_') else value>0)
            retain();print(json.dumps(dict(case=name,rotation=rotation,af=value,passed=row['passed'])),flush=True)
    assert all(r['passed'] for r in report['cases'])
    report['status']='native-rectangular-shield-controls-passed';retain()
except BaseException as exc:
    report.update(status='failed',error=str(exc));retain();raise
