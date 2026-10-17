"""Independent inside/outside Manhattan bounds for native diagonal shielding."""
from pathlib import Path
from fractions import Fraction
import argparse, json, math, shlex, subprocess, sys
import klayout.db as k

repo = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo))
from icstudio.model import file_digest
from icstudio.engines import tcl_word
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline', required=True)
parser.add_argument('--candidate', required=True)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=False)
tech = repo / 'icstudio/assets/pdks/gf180mcuC/libs.tech/magic/gf180mcuC.tech'
baseline = str(Path(args.baseline).resolve())
candidate = str(Path(args.candidate).resolve())
report = dict(status='running', qualified=False, script_sha256=file_digest(Path(__file__)),
              technology_sha256=file_digest(tech), engines={p:file_digest(p) for p in (baseline,candidate)},
              scope='Positive straight-edge fringe shielding; exact-mask diagonal shapes bracketed by independent native Manhattan inside/outside geometries. Corner and direct-overlap models remain outside this gate.',
              limits=dict(native_relative=2e-5, native_absolute_af=1e-5,
                          final_relative_bracket_width=.005, steps_nm=[200,100,50,25,10,5],
                          reason='Frozen before execution; bounds use positive-kernel shielding monotonicity and six-significant-digit native serialization.'), cases=[])
def retain(): (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
retain()

def region(points): return k.Region(k.Polygon([k.Point(*p) for p in points]))
lower = [(8000,8000),(26000,8000),(8000,26000)]
upper = [(26000,8000),(26000,26000),(8000,26000)]
cross = [(14000,8000),(26000,8000),(26000,20000)]
cases = {
    'lower': [(36,lower)],
    'upper': [(36,upper)],
    'complementary_planes': [(36,lower),(34,upper)],
    'crossed_planes': [(36,lower),(34,cross)],
    'crossed_planes_reversed': [(34,lower),(36,cross)],
}

def heights(points, x):
    ys=[]
    for a,b in zip(points,points[1:]+points[:1]):
        if a[0]==x: ys.append(Fraction(a[1]))
        if min(a[0],b[0])<x<max(a[0],b[0]):
            ys.append(Fraction(a[1])+Fraction(x-a[0],b[0]-a[0])*(b[1]-a[1]))
    assert ys
    return min(ys),max(ys)

def staircase(points, step, inside):
    xs=sorted({p[0] for p in points}|set(range(min(p[0] for p in points),max(p[0] for p in points)+1,step)))
    result=k.Region()
    for a,b in zip(xs,xs[1:]):
        lo0,hi0=heights(points,a);lo1,hi1=heights(points,b)
        low=(max if inside else min)(lo0,lo1);high=(min if inside else max)(hi0,hi1)
        low=5*((math.ceil if inside else math.floor)(low/5))
        high=5*((math.floor if inside else math.ceil)(high/5))
        if high>low: result.insert(k.Box(a,low,b,high))
    exact=region(points)
    assert (result-exact).is_empty() if inside else (exact-result).is_empty()
    return result

def run(folder, shapes, rotation, engine):
    folder.mkdir(parents=True)
    ly=k.Layout();ly.dbu=.001;top=ly.create_cell('diagonal_control')
    for layer,box,label in [(42,k.Box(10000,10000,20000,20000),'A'),(30,k.Box(22000,11000,24000,19000),'B')]:
        top.shapes(ly.layer(layer,0)).insert(box)
        top.shapes(ly.layer(layer,10)).insert(k.Text(label,k.Trans(box.center())))
    for layer,rs in shapes: top.shapes(ly.layer(layer,0)).insert(rs)
    top.transform(k.Trans(rotation,False,0,0));ly.write(str(folder/'coupon.gds'))
    (folder/'startup.tcl').write_text('drc off\ntech load '+tcl_word(tech)+'\n')
    body='scalegrid 1 10\ngds read '+tcl_word(folder/'coupon.gds')+'\nload diagonal_control\nselect top cell\nextract do capacitance\nextract do coupling\nextract no resistance\nextract all\ngds write '+tcl_word(folder/'imported.gds')+'\nputs DIAGONAL_COMPLETE\n'
    (folder/'extract.tcl').write_text('if {[catch {\n'+body+'} err]} {puts "DIAGONAL_ERROR $err"}\nquit -noprompt\n')
    command=[engine,'-dnull','-noconsole','-rcfile',str(folder/'startup.tcl'),str(folder/'extract.tcl')]
    with (folder/'engine.log').open('w') as log: p=subprocess.run(command,cwd=folder,stdout=log,stderr=subprocess.STDOUT,timeout=120)
    text=(folder/'engine.log').read_text();assert p.returncode==0 and 'DIAGONAL_COMPLETE' in text and 'DIAGONAL_ERROR' not in text
    original=k.Layout();original.read(str(folder/'coupon.gds'));actual=k.Layout();actual.read(str(folder/'imported.gds'))
    def reg(layout,layer):
        idx=layout.find_layer(layer,0)
        return k.Region() if idx is None else k.Region(layout.top_cell().begin_shapes_rec(idx)).merged()
    assert actual.dbu==original.dbu==.001
    assert all((reg(actual,layer)^reg(original,layer)).is_empty() for layer in (30,34,36,42)), 'Native import changed physical masks'
    rows=[shlex.split(l) for l in (folder/'diagonal_control.ext').read_text().splitlines() if l.strip()]
    scale=next(float(t[2]) for t in rows if t[0]=='scale')
    ab=math.fsum(float(t[3])*scale for t in rows if t[0]=='cap' and sorted(t[1:3])==['A','B'])
    return dict(coupling_af=ab,command=command,exit_code=p.returncode,artifacts={n:file_digest(folder/n) for n in ('coupon.gds','imported.gds','diagonal_control.ext','engine.log')})

try:
    for name,definitions in cases.items():
        for rotation in range(4):
            folder=out/(name+'-'+str(rotation));folder.mkdir()
            exact=[(layer,region(points)) for layer,points in definitions]
            row=dict(case=name,rotation=rotation,bounds=[]);report['cases'].append(row);retain()
            row['baseline']=run(folder/'baseline',exact,rotation,baseline)
            row['candidate']=run(folder/'candidate',exact,rotation,candidate);retain()
            value=row['candidate']['coupling_af']
            previous=None
            for step in report['limits']['steps_nm']:
                inner=[(layer,staircase(points,step,True)) for layer,points in definitions]
                outer=[(layer,staircase(points,step,False)) for layer,points in definitions]
                less=run(folder/(str(step)+'-inside'),inner,rotation,baseline)
                more=run(folder/(str(step)+'-outside'),outer,rotation,baseline)
                lo,hi=more['coupling_af'],less['coupling_af'];tol=max(1e-5,2e-5*max(abs(lo),abs(hi),abs(value)))
                bound=dict(step_nm=step,inside=less,outside=more,lower_af=lo,upper_af=hi,
                           candidate_in_bounds=lo-tol<=value<=hi+tol,
                           nested=True if previous is None else lo>=previous[0]-tol and hi<=previous[1]+tol)
                row['bounds'].append(bound);retain();previous=(lo,hi)
            row['bracket_relative_width']=(hi-lo)/abs(value) if value else None
            row['bracket_absolute_width_af']=hi-lo
            row['baseline_fault_detected']=not lo-tol<=row['baseline']['coupling_af']<=hi+tol
            row['passed']=all(b['candidate_in_bounds'] and b['nested'] for b in row['bounds']) and (
                value==0 if name=='complementary_planes' else value>0 and row['bracket_relative_width']<=.005)
            retain();print(json.dumps({k:row[k] for k in ('case','rotation','passed','baseline_fault_detected','bracket_relative_width')}),flush=True)
    assert all(r['passed'] for r in report['cases'])
    assert any(r['baseline_fault_detected'] for r in report['cases'])
    report['status']='native-diagonal-shield-bounds-passed';retain()
except BaseException as exc:
    report.update(status='failed',error=str(exc));retain();raise
