"""Require complete GF180 B RC, terminal equivalence, fill audit and post-RC PVT."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import load_project,file_digest,atomic_write
from icstudio.engines import execute
from icstudio.gf180_rc import technology,collapsed
from icstudio.magic_rc import normalize,finalize
from icstudio.rc_islands import prune
from scripts.verify_gf180_banba_physical import magic_script,check_extracted,simulate,OPEN_PDKS_COMMIT


def qualify(args):
    out=args.out.resolve()
    if out.exists() and any(out.iterdir()):raise ValueError('Use a new RC evidence directory.')
    out.mkdir(parents=True);report={'status':'failed','signoff':False}
    try:
        from icstudio.external_tools import executable_info
        report['engines']={key:executable_info(getattr(args,key)) for key in ('magic','ngspice')}
        # Magic's executable is a shell launcher. Bind the implementation it
        # loads as well as the launcher to the evidence for source-built runs.
        magic_prefix=Path(report['engines']['magic']['path']).parent.parent
        magic_library=magic_prefix/'lib/magic/tcl/tclmagic.so'
        if not magic_library.is_file():raise ValueError('Use the pinned source-built Magic prefix for RC qualification.')
        report['engines']['magic']['shared_library']=executable_info(magic_library)
        source_lock=magic_prefix.parent/'source-lock.json'
        expected=json.loads((ROOT/'examples/gf180-rc-engine-lock.json').read_text())
        if not source_lock.is_file() or json.loads(source_lock.read_text())!=expected:
            raise ValueError('Magic build source lock does not match the current extraction patch.')
        report['engines']['magic']['source_lock_sha256']=file_digest(source_lock)
        report['engine_lock_sha256']=file_digest(ROOT/'examples/gf180-rc-engine-lock.json')
        report['patch_sha256']=file_digest(ROOT/'packaging/physical/magic-gf180-rc.patch')
        report['implementation_sha256']=file_digest(__file__)
        source=args.open_pdks.resolve()
        commit=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
        if commit!=OPEN_PDKS_COMMIT:raise ValueError('Wrong open_pdks source revision.')
        tech=out/'gf180mcuB.tech'
        execute([sys.executable,source/'common/preproc.py',source/'gf180mcu/magic/gf180mcu.tech',tech,
                 '-DTECHNAME=gf180mcuB','-DREVISION='+commit,'-DMETALS4','-DMIM','-DTHICKMET1P1','-DHRPOLY1K','-DMAGIC_CURRENT=8.3'],out)
        original=tech.read_text();atomic_write(out/'upstream.tech',original);atomic_write(tech,technology(original))
        p=load_project(ROOT/'examples/gf180-banba/layout/banba-layout.icproj')
        gds=ROOT/'examples/gf180-banba/layout/banba-layout.gds'
        reference=(ROOT/'examples/gf180-banba/layout/density/schematic.spice').read_text()
        prefix=magic_script(p,tech,gds);atomic_write(out/'empty.magicrc','')
        def magic(name,commands):
            script=prefix+commands+'\nquit -noprompt\n';atomic_write(out/(name+'.tcl'),script)
            try:log=execute([args.magic,'-dnull','-noconsole','-rcfile',out/'empty.magicrc',out/(name+'.tcl')],out,timeout=600)
            except Exception as exc:
                atomic_write(out/(name+'.log'),str(exc));raise
            atomic_write(out/(name+'.log'),log)
            filtered=log.replace("Warning: Calma reading is not undoable!  I hope that's OK.",'')
            if re.search(r'Missing .*connection|smaller than extract|Bad device|Error:|STUDIO_.*ERROR',filtered,re.I):
                raise ValueError('Magic extraction diagnostic in '+name)
            return log
        magic('capacitance','extract do local\nextract all\next2spice lvs\next2spice merge none\next2spice cthresh 0\next2spice -o extracted-c.spice\nsave banba_layout')
        report['capacitance']=check_extracted(reference,(out/'extracted-c.spice').read_text())
        # Keep ext2sim and resistance extraction in separate processes.
        magic('prepare-rc','ext2sim labels on\next2sim')
        log=magic('resistance','extresist simplify off\nextresist all')
        counts=[re.findall(pattern,log) for pattern in (r'Total Nets: (\d+)',r'Nets extracted: (\d+)',r'Nets output: (\d+)')]
        if any(len(v)!=1 for v in counts) or len({int(v[0]) for v in counts})!=1:
            raise ValueError('Every original net must be extracted and output.')
        report['net_count']=int(counts[0][0]);norm=normalize(out,'banba_layout',max_capacitors=100000)
        magic('export-rc','ext2spice lvs\next2spice subcircuit top on\next2spice renumber off\next2spice global off\next2spice merge none\next2spice cthresh 0\next2spice extresist on\next2spice -o extracted.spice')
        norm=finalize(out,'banba_layout')
        contracted=collapsed((out/'extracted.spice').read_text(),norm);atomic_write(out/'collapsed.spice',contracted)
        report['terminal_equivalence']=check_extracted(reference,contracted)
        report['resistors']=norm['resistor_count'];report['conservation']=norm['conservation']
        report['islands']=prune(out/'extracted.spice',out/'electrical.spice')
        from scripts.qualify_gf180_fill_coupling import qualify as fill_check
        report['fill_coupling']=fill_check(gds,ROOT/'examples/gf180-banba/layout/density/banba-density.gds',tech,args.magic,out/'fill-coupling')
        report['electrical_sha256']=file_digest(out/'electrical.spice')
        if args.extraction_only:
            report.update(status='extracted',scope='Extraction and fill controls only; post-RC PVT/startup has not been qualified.')
            return report
        version=execute([args.ngspice,'--version'],out)
        if 'KLU' not in version:raise ValueError('This dense RC qualification requires an ngspice build with KLU.')
        atomic_write(out/'ngspice-version.log',version)
        cases=[(args.corner,t,v) for t in (-40,125) for v in (2.7,3.6)] if args.corner else None
        report['simulation']=simulate(p,out/'electrical.spice',args.ngspice,out/'simulation',['VDD','VREF','VSS'],solver='klu',timeout=3600,workers=args.workers,cases=cases)
        report['corner_selection']=args.corner or 'all five process corners'
        report['simulation']['scope']='Distributed R and conserved original C; isolated unobservable R-only components omitted with proof.'
        if not report['simulation']['passed']:raise ValueError('Post-RC PVT or startup requirements failed.')
        report.update(status='passed',technology_sha256=file_digest(tech),layout_sha256=file_digest(gds),
                      scope='Pinned reference and bounded open-PDK parasitic model; no foundry calibration or signoff.')
        return report
    except Exception as exc:report['error']=str(exc);raise
    finally:atomic_write(out/'qualification.json',json.dumps(report,indent=2))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for key in ('open-pdks','out'):ap.add_argument('--'+key,type=Path,required=True)
    for key in ('magic','ngspice'):ap.add_argument('--'+key,required=True)
    ap.add_argument('--workers',type=int,default=4)
    ap.add_argument('--corner',choices=('nominal','ff','ss','fs','sf'),help='One CI matrix shard; all five are required for full PVT qualification.')
    ap.add_argument('--extraction-only',action='store_true',help='Report extracted, never passed; does not qualify PVT/startup.')
    qualify(ap.parse_args())
