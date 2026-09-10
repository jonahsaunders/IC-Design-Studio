"""Qualify the six-case GF180 testbench with real Xschem and ngspice.

Compare independent Xschem netlisting of the supplied circuit with Studio's
capture, native catalog, exported Xschem and reimported native execution paths.
This is schematic/simulation compatibility, not layout or PVT qualification.
"""
import argparse,bisect,cmath,json,math,os,platform,re,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio import __version__
from icstudio.model import atomic_write,save_project,load_project,file_digest
from icstudio.spice_program import read_plot,runtime_environment
from icstudio.engines import execute

SOURCE=ROOT/'examples/gf180-bandgap/5vfullv2-compatibility.sch'
CASES=[('startup','tran',3000),('dc--40C','dc',17),('dc-25C','dc',17),
       ('dc-125C','dc',17),('psrr','ac',61),('zout','ac',61)]
PROBES='v(vref) v(avdd) v(v1) v(v2) i(vsense) i(vdd)'
DIAGNOSTICS=r'(^\s*error\b|\bfailed\b|no such vector|no such device|unknown parameter|unknown subckt|singular matrix|timestep too small)'
TOLERANCES={'relative':1e-4,'voltage_absolute':2e-6,'current_absolute':2e-11}


def portable_source(source,directory):
    """Relocate dependencies only; Xschem itself reads the original circuit."""
    from icstudio.xschem_libraries import library_root
    source=Path(source);directory.mkdir(parents=True)
    gf=library_root('gf180mcu')/'gf180mcu';standard=library_root('xschem')/'xschem'
    for name,origin in [('symbols',gf/'symbols'),('models',gf/'models'),('devices',standard/'devices')]:
        shutil.copytree(origin,directory/name)
    shutil.copy2(gf/'LICENSE',directory/'GF180-LICENSE.txt')
    shutil.copy2(standard/'COPYRIGHT',directory/'XSCHEM-COPYRIGHT.txt')
    text=source.read_text(encoding='utf-8')
    for name in ('design','sm141064'):
        text=text.replace('/foss/pdks/gf180mcuD/libs.tech/ngspice/'+name+'.ngspice','models/'+name+'.spice')
    atomic_write(directory/source.name,text)
    return directory/source.name


def case_plots(directory):
    result={}
    for name,kind,points in CASES:
        plot=read_plot(directory/('quick-'+name+'.raw'))
        if plot['plot_kind']!=kind:raise AssertionError(name+': wrong analysis type')
        if (len(plot['x'])<points if kind=='tran' else len(plot['x'])!=points):
            raise AssertionError(name+': incomplete waveform')
        if set(plot['traces'])!={'vref','avdd','v1','v2'} or set(plot['currents'])!={'i(vsense)','i(vdd)'}:
            raise AssertionError(name+': missing voltage or current probes: '+str(list(plot['currents'])))
        result[name]=plot
    return result


def validate_log(text):
    errors=[s for s in text.splitlines() if re.search(DIAGNOSTICS,s,re.I)]
    if errors:raise AssertionError('\n'.join(errors))
    if 'GF180_QUICK_COMPATIBILITY_SIX_ANALYSES_COMPLETE' not in text:
        raise AssertionError('The testbench did not finish its six analyses.')


def external(source,output,xschem,ngspice,libraries=()):
    from icstudio.external_tools import xschem_netlist
    record=xschem_netlist(source,output,xschem,libraries=libraries)
    if record['status']!='complete':raise AssertionError('Xschem netlisting failed')
    decks=list((output/'netlists').glob('*.spice'))
    if len(decks)!=1:raise AssertionError('Expected one top-level Xschem netlist')
    folder=output/'sources/0'
    started=time.monotonic()
    text=execute([ngspice,'-n','-D','ngbehavior=hsa','-b',decks[0].resolve()],folder,timeout=180,env=runtime_environment(ngspice))
    atomic_write(output/'simulation.log',text);validate_log(text)
    return case_plots(folder),time.monotonic()-started


def run_studio(project,directory,engine,capture=False):
    from icstudio.xschem_runtime import run as run_capture
    from icstudio.native_spice import run as run_native
    started=time.monotonic()
    result=(run_capture if capture else run_native)(project,project['top'],{'timeout':180,'probes':PROBES},engine,directory)
    atomic_write(directory/'result.json',json.dumps(result))
    cases=result['xschem_cases' if capture else 'analysis_cases']
    if result['program_status']!='Complete' or len(cases)!=6 or any(c['state']!='Complete' for c in cases):
        raise AssertionError(str(result['warnings']))
    if [c['analysis'] for c in cases]!=[c[1] for c in CASES]:raise AssertionError('Case order changed')
    validate_log(result['log'])
    return case_plots(directory),time.monotonic()-started


def interpolate(xs,ys,x):
    i=bisect.bisect_right(xs,x)
    if i==0:return ys[0]
    if i==len(xs):return ys[-1]
    a,b=xs[i-1],xs[i]
    return ys[i-1]+(ys[i]-ys[i-1])*((x-a)/(b-a))


def compare(reference,actual):
    """Compare voltages/currents, including AC phase, at both grids' points."""
    rows=[]
    for name,kind,_ in CASES:
        a,b=reference[name],actual[name];xa,xb=a['x'],b['x']
        if any(not math.isclose(x,y,rel_tol=1e-10,abs_tol=1e-12) for x,y in [(xa[0],xb[0]),(xa[-1],xb[-1])]):
            raise AssertionError(name+': simulation domains differ')
        if kind!='tran' and (len(xa)!=len(xb) or any(not math.isclose(x,y,rel_tol=1e-10) for x,y in zip(xa,xb))):
            raise AssertionError(name+': sweep grids differ')
        grid=sorted(set(xa+xb));measurements=[]
        for group,phase,absolute in [('traces','phase',TOLERANCES['voltage_absolute']),('currents','current_phase',TOLERANCES['current_absolute'])]:
            if set(a[group])!=set(b[group]):raise AssertionError(name+': trace names differ')
            for signal in a[group]:
                av,bv=a[group][signal],b[group][signal]
                if kind=='ac':
                    av=[cmath.rect(v,math.radians(p)) for v,p in zip(av,a[phase][signal])]
                    bv=[cmath.rect(v,math.radians(p)) for v,p in zip(bv,b[phase][signal])]
                scale=max(abs(v) for v in av);limit=absolute+TOLERANCES['relative']*scale
                error=max(abs(interpolate(xa,av,x)-interpolate(xb,bv,x)) for x in grid)
                measurements.append({'signal':signal,'maximum_absolute_error':error,'allowed_error':limit,'passed':error<=limit})
        rows.append({'case':name,'reference_points':len(xa),'actual_points':len(xb),'signals':measurements,
                     'passed':all(m['passed'] for m in measurements)})
    return {'passed':all(row['passed'] for row in rows),'cases':rows}


def summary(plots):
    startup=plots['startup'];psrr=plots['psrr'];zout=plots['zout']
    return {'startup_vref_v':startup['traces']['vref'][-1],
            'startup_vdd_v':startup['traces']['avdd'][-1],
            'startup_iref_na':abs(startup['currents']['i(vsense)'][-1])*1e9,
            'startup_idd_ua':-startup['currents']['i(vdd)'][-1]*1e6,
            'dc_vref_at_3v_and_5v':{name:[plots[name]['traces']['vref'][0],plots[name]['traces']['vref'][-1]] for name in ('dc--40C','dc-25C','dc-125C')},
            'psrr_1hz_db':-20*math.log10(psrr['traces']['vref'][0]),
            'zout_1hz_ohm':zout['traces']['vref'][0]}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=SOURCE);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--ngspice',default=os.environ.get('ICSTUDIO_TEST_NGSPICE') or shutil.which('ngspice'),required=False)
    parser.add_argument('--xschem',default=os.environ.get('ICSTUDIO_TEST_XSCHEM') or shutil.which('xschem'),required=False)
    args=parser.parse_args();out=args.output.resolve()
    if not args.ngspice or not args.xschem:parser.error('Supply real --ngspice and --xschem executables.')
    if out.exists() and any(out.iterdir()):parser.error('Choose a new, empty output directory.')
    out.mkdir(parents=True,exist_ok=True)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    report={'status':'failed','application_version':__version__,'application_commit':commit,
            'application_code_modified':bool(subprocess.check_output(['git','diff','--name-only','HEAD','--','icstudio'],cwd=ROOT,text=True).strip()),
            'compatibility_code_sha256':{name:file_digest(ROOT/name) for name in ('icstudio/catalog_migration.py','icstudio/native_exchange.py')},
            'platform':platform.platform(),'source_sha256':file_digest(args.source),'analyses_per_run':6,
            'scope':'Xschem/Studio GF180 schematic and simulation compatibility. No Magic/KLayout physical geometry, full PVT, noise, Monte Carlo, or sign-off claim.',
            'tolerances':TOLERANCES,'comparisons':{}}
    def checkpoint():atomic_write(out/'report.json',json.dumps(report,indent=2))
    try:
        from icstudio.runtime_setup import check_ngspice
        report['runtime']=check_ngspice(args.ngspice)
        print('Netlisting original circuit independently in Xschem…',flush=True)
        original=portable_source(args.source,out/'portable-source')
        baseline,elapsed=external(original,out/'xschem-reference',args.xschem,args.ngspice,[original.parent/'devices'])
        report['reference']={'status':'passed','seconds':elapsed,'measurements':summary(baseline)};checkpoint()
        from icstudio.xschem_compat import review_project
        record=review_project(args.source)
        if record['errors'] or record['candidate']['xschem_exchange']['unresolved']:raise AssertionError('Unresolved source dependencies')
        capture=record['candidate'];save_project(capture,out/'capture.icproj')
        print('Running Studio preserved import…',flush=True)
        actual,elapsed=run_studio(capture,out/'studio-capture',args.ngspice,True)
        report['comparisons']['studio_capture']={**compare(baseline,actual),'seconds':elapsed};checkpoint()
        from icstudio.native_migration import review as native_review
        from icstudio.catalog_migration import review as catalog_review
        from icstudio.pdks import PDKRegistry
        from icstudio.bundled_pdks import packages
        native=native_review(capture)
        if native['candidate'] is None:raise AssertionError(str(native['items']))
        registry=PDKRegistry(out/'registry');package=next(p for p in packages(verify=True) if p['name']=='gf180mcuD')
        technology=registry.technology(registry.install(Path(package['path'])/'package.json'))
        migrated=catalog_review(native['candidate'],technology)
        atomic_write(out/'migration-review.json',json.dumps({k:v for k,v in migrated.items() if k!='candidate'},indent=2))
        if migrated['candidate'] is None or migrated['converted']!=60 or migrated['unmatched']!=0:raise AssertionError(str(migrated['items']))
        project=migrated['candidate'];report['catalog']={'converted':60,'unmatched':0,'revision':package['revision']}
        project['name']='GF180 six-case compatibility';project['analysis'].update(type='program',engine='ngspice',probes=PROBES,timeout=180)
        save_project(project,out/'5vfullv2-native.icproj');project=load_project(out/'5vfullv2-native.icproj')
        print('Running native catalog conversion after save/reopen…',flush=True)
        actual,elapsed=run_studio(project,out/'studio-native',args.ngspice)
        report['comparisons']['native_catalog']={**compare(baseline,actual),'seconds':elapsed};checkpoint()
        from icstudio.native_exchange import export_project,review_project as review_exchange
        exported=export_project(project,out/'native-xschem');path=Path(exported['directory'])/exported['top']
        print('Netlisting native export independently in Xschem…',flush=True)
        actual,elapsed=external(path,out/'xschem-native-export',args.xschem,args.ngspice)
        report['comparisons']['xschem_native_export']={**compare(baseline,actual),'seconds':elapsed};checkpoint()
        returned=review_exchange(path)
        if returned['errors'] or returned['candidate'] is None:raise AssertionError(str(returned['errors']))
        q=returned['candidate'];old={d['id']:d for c in project['cells'] for d in c['devices']}
        new={d['id']:d for c in q['cells'] for d in c['devices']}
        def model_identity(device):
            return {key:device.get('model_ref',{}).get(key) for key in ('pdk','revision','device','instance_prefix')}
        if old.keys()!=new.keys() or any(model_identity(old[k])!=model_identity(new[k]) or old[k]['nets']!=new[k]['nets'] for k in old):
            raise AssertionError('Device identities, model references or connections changed during round trip')
        from icstudio.catalog import binding_for,parameter_values
        from icstudio.model import clone
        for key in old:
            if not old[key].get('model_ref') or old[key]['kind'] not in ('NMOS','PMOS'):continue
            a,b=clone(old[key]),clone(new[key]);binding=binding_for(project['pdk'],a)
            a['params']['w']=b['params']['w']=str(float(a['params']['w'])*1.1)
            av,bv=parameter_values(binding,a),parameter_values(binding,b)
            if any(not math.isclose(av[k],bv[k],rel_tol=1e-10,abs_tol=0) for k in av):
                raise AssertionError(a['name']+': round trip froze a live model parameter')
        save_project(q,out/'5vfullv2-roundtrip.icproj');q=load_project(out/'5vfullv2-roundtrip.icproj')
        print('Running reimported native project…',flush=True)
        actual,elapsed=run_studio(q,out/'studio-roundtrip',args.ngspice)
        report['comparisons']['native_roundtrip']={**compare(baseline,actual),'seconds':elapsed}
        report['roundtrip']={'device_identities_retained':len(old),'catalog_models_retained':60,'connections_retained':True}
        if not all(c['passed'] for c in report['comparisons'].values()):raise AssertionError('Numerical comparison failed; inspect report.json.')
        report['status']='passed';checkpoint();print(json.dumps({'status':'passed','analyses_per_run':6,'paths_compared':4,'measurements':report['reference']['measurements']},indent=2));return 0
    except Exception as exc:
        report['error']=str(exc);checkpoint();raise


if __name__=='__main__':raise SystemExit(main())
