"""Netlist a Studio package with actual Xschem, edit a MOS, and import it back."""
import argparse,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import load_project,atomic_write,save_project,scalar
from icstudio.interchange import export_xschem
from icstudio.engines import execute,tcl_word,run_deck
from icstudio.pdks import model_lines
from icstudio.xschem_io import import_package
from icstudio.sky130_flow import logic_metrics,subcircuit


def parameterized_component(out,args,cwd):
    p=load_project(ROOT/'examples/reusable-divider.icproj');export_xschem(p,out);(out/'profile').mkdir()
    rc=out/'xschemrc';rc.write_text('set XSCHEM_LIBRARY_PATH '+tcl_word(out)+'\nset netlist_dir '+tcl_word(out)+'\nset USER_CONF_DIR '+tcl_word(out/'profile')+'\nset XSCHEM_TMP_DIR '+tcl_word(out)+'\nset undo_type disk\n')
    cases=[]
    for mode,expected in (('original',.6),('edited',.45)):
        if mode=='edited':
            file=out/'top.sch';file.write_text(file.read_text().replace('ratio="2"','ratio="3"'))
        q,notes=import_package(out);run=out/mode;run.mkdir();save_project(q,run/'reimported.icproj')
        log=execute([args.xschem,'-x','-q','-n','-s','--rcfile',rc,'-o',out,out/'top.sch'],cwd or out,timeout=30);atomic_write(run/'netlisting.log',log)
        if re.search(r'unable to open|FATAL|not found|error executing|SKIPPING',log,re.I):raise ValueError('Xschem reported parameterized netlisting errors.')
        native=(out/'top.spice').read_text();assert re.search(r'^\.subckt divider in out vss\s+resistance=10k ratio=2$',native,re.M)
        atomic_write(run/'xschem.spice',native);deck='* Parameterized Xschem divider\n'+re.sub(r'^\.end\s*$','',native,flags=re.M|re.I)+'\n.op\n.save v(out)\n.end\n';atomic_write(run/'testbench.cir',deck)
        result=run_deck(q,q['top'],{'type':'deck','deck':str(run/'testbench.cir')},args.ngspice,run);atomic_write(run/'result.json',json.dumps(result))
        actual=result['traces']['out'][0];assert abs(actual-expected)<1e-9;cases.append({'case':mode,'status':'passed','expected_voltage':expected,'measured_voltage':actual})
    atomic_write(out/'report.json',json.dumps(cases,indent=2));return cases


def main():
    a=argparse.ArgumentParser();a.add_argument('--project',required=True);a.add_argument('--output',required=True);a.add_argument('--xschem',required=True);a.add_argument('--ngspice',required=True);a.add_argument('--xschem-workdir');args=a.parse_args()
    p=load_project(args.project);out=Path(args.output).resolve()
    if out.exists() and any(out.iterdir()):raise ValueError('Choose an empty exchange output directory.')
    export_xschem(p,out);(out/'profile').mkdir();rc=out/'xschemrc';rc.write_text('set XSCHEM_LIBRARY_PATH '+tcl_word(out)+'\nset netlist_dir '+tcl_word(out)+'\nset USER_CONF_DIR '+tcl_word(out/'profile')+'\nset XSCHEM_TMP_DIR '+tcl_word(out)+'\nset undo_type disk\n')
    top=next(c for c in p['cells'] if c['id']==p['top']);c=next(c for c in p['cells'] if c['name']=='custom_inverter');cwd=Path(args.xschem_workdir).resolve() if args.xschem_workdir else out
    results=[]
    for mode in ('original','edited'):
        if mode=='edited':
            d=next(d for d in c['devices'] if d['kind']=='NMOS');file=out/(c['name']+'.sch');text=file.read_text();lines=text.splitlines()
            for i,line in enumerate(lines):
                if 'symbols/'+d['id']+'.sym' in line:lines[i]=re.sub(r'(?<!\w)w=\S+','w=1.5',line)
            file.write_text('\n'.join(lines)+'\n');q,notes=import_package(out);back=next(cc for cc in q['cells'] if cc['id']==c['id']);assert scalar(next(d for d in back['devices'] if d['kind']=='NMOS')['params']['w'])==1.5e-6
            assert [d['nets'] for d in back['devices']]==[d['nets'] for d in c['devices']];save_project(q,out/'reimported.icproj');atomic_write(out/'import-report.json',json.dumps(notes,indent=2))
        log=execute([args.xschem,'-x','-q','-n','-s','--rcfile',rc,'-o',out,out/(top['name']+'.sch')],cwd,timeout=30);atomic_write(out/(mode+'-netlisting.log'),log)
        if re.search(r'unable to open|FATAL|not found|error executing',log,re.I):raise ValueError('Xschem reported netlisting errors.')
        native=(out/(top['name']+'.spice')).read_text();ports,body,_=subcircuit(native,c['name']);assert ports==c['ports'];assert 'sky130_fd_pr__nfet_01v8' in body and 'sky130_fd_pr__pfet_01v8' in body
        run=out/mode;run.mkdir();atomic_write(run/'xschem.spice',native)
        deck='* Real Xschem netlist with locked model/analysis wrapper\n'+'\n'.join(model_lines(p['pdk']))+'\n'+re.sub(r'^\.end\s*$','',native,flags=re.M|re.I)+'\n.tran 20p 62n\n.save v(vin) v(vout)\n.end\n';atomic_write(run/'testbench.cir',deck)
        r=run_deck(p,p['top'],{'type':'deck','deck':str(run/'testbench.cir')},args.ngspice,run);atomic_write(run/'result.json',json.dumps(r));results.append({'case':mode,'status':'passed','metrics':logic_metrics(r)})
    parameters=parameterized_component(out/'parameterized-component',args,Path(args.xschem_workdir).resolve() if args.xschem_workdir else None)
    atomic_write(out/'report.json',json.dumps({'status':'passed','xschem_version':execute([args.xschem,'-x','-q','--version','--rcfile',rc],cwd,timeout=15),'cases':results,'parameterized_component':parameters},indent=2));print('PASS: actual hierarchical Xschem netlisting, ngspice simulation, external width edit, native reimport, and parameterized component edits.')

if __name__=='__main__':main()
