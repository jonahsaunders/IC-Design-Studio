"""Finite rectangular SKY130 MiM orientation, connectivity and admittance checks.

This checks public-model equivalence, not measured high-frequency accuracy or
full device qualification. References never supply extraction dimensions.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import math
from pathlib import Path
import re
import sys
import traceback
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from icstudio.model import file_digest, save_project, load_project, atomic_write
from icstudio.catalog import link_technology
from icstudio.interchange import export_layout
from icstudio.layout_import import read_layout
from icstudio.layout_verification import run, reference
from icstudio.stream_contract import compare
from icstudio.sky130_rf_verification import drc
from scripts.qualify_sky130_mim2 import fixture, independent, altered, audit_native, FAULTS
from scripts.qualify_sky130_threshold_layouts import rejected
from scripts.qualify_standard_mos_layout import technology

SIZES = ((2,10,1),(10,2,1),(3.005,5.005,1),(2,30,1),(30,2,1),
         (2,10,3),(2,10,16),(2,2,1))
FIRST_SIZES = ((2,10,1),(10,2,1),(3.005,5.005,1),(6,30,1),(30,6,1),
               (2,10,3),(2,10,16),(2,2,1))


def admittance(project, subcircuits, corner, temp, tools, directory):
    from icstudio.engines import execute, ngspice_command, parse_raw
    from icstudio.pdks import model_lines, stage_model_deck
    directory.mkdir()
    text = '* Independent complex terminal probes, public-model equivalence only\n'
    text += '\n'.join(model_lines(project['pdk'],corner))+'\n'
    for phase, circuit in subcircuits.items():
        name = 'device_coupon_'+phase
        text += re.sub(r'(?im)^(\.subckt|\.ends)\s+device_coupon\b',
                       lambda m:m[1]+' '+name,circuit)
        text += f'\nVP_{phase} P_{phase} 0 DC 0 AC 1\nXDUT_{phase} P_{phase} 0 {name}\n'
    text += f'\n.temp {temp}\n.ac dec 1 1k 10G\n.save '
    text += ' '.join('i(VP_'+phase+')' for phase in subcircuits)+'\n.end\n'
    deck=directory/'probe.cir'; raw=directory/'probe.raw'
    atomic_write(deck,stage_model_deck(project['pdk'],text,directory))
    log=execute(ngspice_command(project,tools['ngspice'],raw,deck),directory,timeout=90)
    atomic_write(directory/'console.log',log)
    names,rows,is_complex=parse_raw(raw)
    if not is_complex or len(rows)!=8:raise ValueError('Expected eight complex AC samples.')
    result=[]
    for row in rows:
        frequency=row[names.index('frequency')].real
        values={phase:-row[names.index('i(vp_'+phase+')')] for phase in subcircuits}
        if not all(math.isfinite(v.real) and math.isfinite(v.imag) and v.imag>0 for v in values.values()):
            raise ValueError('Nonfinite or noncapacitive terminal response.')
        errors={k:abs(v/values['independent']-1) for k,v in values.items()}
        resistance={k:(1/v).real for k,v in values.items()}
        rerrors={k:abs(v/resistance['independent']-1) for k,v in resistance.items()}
        if any(errors[k]>1e-6 for k in ('schematic','extracted')):
            raise ValueError('Complex reference response differs: '+str(errors))
        if any(rerrors[k]>1e-6 for k in ('schematic','extracted')):
            raise ValueError('Series resistance differs: '+str(rerrors))
        result.append(dict(frequency_Hz=frequency,admittance_S={k:[v.real,v.imag] for k,v in values.items()},relative_error=errors,
                           series_resistance_ohm=resistance,resistance_relative_error=rerrors))
    if 'swapped' in subcircuits and result[-1]['resistance_relative_error']['swapped']<0.05:
        raise ValueError('Series resistance did not distinguish swapped width and length.')
    return dict(corner=corner,temperature_C=temp,samples=result,raw_sha256=file_digest(raw))


def bottom_open_rejected(report, directory, plate=2):
    """Require the exact mask fault and completed native extraction, not any error."""
    import klayout.db as db
    from icstudio.sky130_mim2_extract import masks
    stages={s['name']:s['status'] for s in report['stages']}
    if not (report['status']=='failed' and
            all(stages.get(k)=='passed' for k in ('preflight','layout_export')) and
            stages.get('lvs_extraction')=='failed' and
            report.get('error')=='MiM orientation needs bottom contacts on exactly one axis.'):
        return False
    model=f'sky130_fd_pr__cap_mim_m3_{plate}'
    layout,regions=masks(directory/'layout.gds','device_coupon',model)
    if regions['cap'].is_empty() or not (regions['cut']-regions['cap']).is_empty():return False
    extraction=directory/'lvs-extraction'
    native=extraction/'device_coupon.ext'; log=extraction/'native-extraction.log'
    return (native.is_file() and log.is_file() and
            'STUDIO_MAGIC_COMPLETE' in log.read_text() and
            'device csubckt '+model+' ' in native.read_text() and
            not (extraction/'extracted.spice').exists() and not (extraction/'native-original.ext').exists())


def execute_case(tech, size, index, output, tools, pilot=False, plate=2):
    import klayout.db as db
    from icstudio.testbenches import native_subcircuit
    folder=Path(output)/str(index); folder.mkdir()
    row=dict(size=size,plate=plate,status='RUNNING',layouts=[],faults=[],measurements=[])
    try:
        original=fixture(tech,size,plate); save_project(original,folder/'input.icproj')
        original=load_project(folder/'input.icproj'); export_layout(original,folder/'original.gds')
        for mirror,angle in ((False,0),(False,90)) if pilot else [(m,a) for m in (False,True) for a in (0,90,180,270)]:
            name=f'{angle}-'+('mirror' if mirror else 'plain')
            ly=db.Layout(); ly.read(str(folder/'original.gds'))
            # Off-origin transforms expose incorrect coordinate matching.
            ly.top_cell().transform(db.Trans(angle//90,mirror,125000,-235000))
            ly.write(str(folder/f'input-{name}.gds'))
            p,_=read_layout(folder/f'input-{name}.gds'); link_technology(p,tech); p['cells'][0]['ports']=['P','N']
            export_layout(p,folder/f'roundtrip-{name}.oas')
            p,_=read_layout(folder/f'roundtrip-{name}.oas'); link_technology(p,tech); p['cells'][0]['ports']=['P','N']
            export_layout(p,folder/f'roundtrip-{name}.gds')
            exchange=compare(folder/f'input-{name}.gds',folder/f'roundtrip-{name}.gds',text_presentation=False)
            dest=folder/f'valid-{name}'
            report=run(p,p['top'],dest,tools,reference(independent(size,plate=plate),'device_coupon'))
            if report['status']!='passed':raise ValueError(report.get('error','Native verification failed.'))
            native=audit_native(dest/'lvs-extraction/extracted.spice',size,plate)
            public=drc(tools['klayout'],dest/'layout.gds','device_coupon',tech,dest/'public-drc')
            if public['violations']:raise ValueError('Public DRC failed: '+str(public['rules']))
            row['layouts'].append(dict(name=name,native=native,exchange=exchange,public_drc=public,
                                       report_sha256=file_digest(dest/'report.json')))
        decks=dict(schematic=native_subcircuit(original,original['top']),
                   extracted=(folder/'valid-90-plain/lvs-extraction/extracted.spice').read_text(),
                   independent=independent(size,plate=plate))
        w,l,count=size
        if w!=l:decks['swapped']=independent((l,w,count),plate=plate)
        for corner,temp in (('nominal',27),) if pilot else (('nominal',27),('ss',0),('ff',85)):
            row['measurements'].append(admittance(original,decks,corner,temp,tools,folder/f'electrical-{corner}-{temp}'))
        for fault in FAULTS+(('reference-swapped',) if w!=l else ()):
            dest=folder/fault
            circuit=independent((l,w,count),plate=plate) if fault=='reference-swapped' else independent(size,fault,plate)
            faulty=original if fault=='reference-swapped' else altered(original,fault,plate)
            report=run(faulty,original['top'],dest,tools,reference(circuit,'device_coupon'))
            detected=rejected(report,dest)
            method='native circuit comparison'
            if not detected and fault=='bottom-open' and w!=l:
                detected=bottom_open_rejected(report,dest,plate); method='written-mask orientation guard after native extraction'
            if not detected:raise ValueError('Intended fault was not detected: '+fault+' '+str(report.get('error')))
            row['faults'].append(dict(name=fault,detected=True,method=method,error=report.get('error'),
                                      report_sha256=file_digest(dest/'report.json')))
        row['status']='PASS'
    except Exception as e:row.update(status='FAIL',error=str(e),traceback=traceback.format_exc())
    (folder/'record.json').write_bytes((json.dumps(row,indent=2)+'\n').encode()); return row


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('output','sky130','magic','netgen','klayout','ngspice'):ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--workers',type=int,default=2); ap.add_argument('--pilot',action='store_true')
    ap.add_argument('--plate',type=int,choices=(1,2),default=2)
    a=ap.parse_args(); out=a.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    tech,identity=technology('sky130A',a.sky130)
    files=[*sorted((ROOT/'icstudio').glob('*.py')),Path(__file__),*[ROOT/'scripts'/n for n in
        ('qualify_sky130_mim2.py','qualify_standard_mos_layout.py','qualify_sky130_threshold_layouts.py')]]
    hashes={p.relative_to(ROOT).as_posix():file_digest(p) for p in files}
    (out/'source-files.json').write_bytes((json.dumps(hashes,indent=2)+'\n').encode())
    tools={n:str(getattr(a,n).resolve(strict=True)) for n in ('magic','netgen','klayout','ngspice')}
    record=dict(schema=1,chunk=7,chunk_complete=False,qualified=False,status='RUNNING',scope=__doc__,plate=a.plate,
                package=identity,engine_sha256={k:file_digest(p) for k,p in tools.items()},cases=[])
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        sizes=FIRST_SIZES if a.plate==1 else SIZES
        for job in as_completed([pool.submit(execute_case,tech,s,i,out,tools,a.pilot,a.plate)
                                 for i,s in enumerate(sizes[:1] if a.pilot else sizes)]):
            row=job.result(); record['cases'].append(row); print(row['size'],row['status'],row.get('error',''),flush=True)
            (out/'record.json').write_bytes((json.dumps(record,indent=2)+'\n').encode())
    record['source_unchanged']=hashes=={p.relative_to(ROOT).as_posix():file_digest(p) for p in files}
    record['status']='PASS' if record['source_unchanged'] and all(c['status']=='PASS' for c in record['cases']) else 'FAIL'
    (out/'record.json').write_bytes((json.dumps(record,indent=2)+'\n').encode()); return int(record['status']!='PASS')


if __name__=='__main__':raise SystemExit(main())
