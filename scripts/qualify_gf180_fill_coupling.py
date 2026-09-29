"""Bounded fill-coupling audit with real, near/far Magic control structures.

This is the pinned open-PDK model's interaction-range check, not a field solver.
Purpose-4 dummy metal is materialized only in disposable control GDS files.
"""
import argparse
import json
import math
from pathlib import Path
import re
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import atomic_write,file_digest,scalar
from icstudio.engines import execute,tcl_word
from icstudio.fill_capacitance import from_ext
from scripts.fill_gf180_banba import FILL_LAYERS,BORDER,source_regions


def range_um(text):
    section=re.search(r'(?ms)^extract\s*\n(.*?)^end\s*$',text)
    if not section:raise ValueError('No extraction section.')
    section=section[1]
    if re.findall(r'(?m)^\s*units\s+(\S+)',section)!=['microns']:
        raise ValueError('Expected micron extraction coefficients.')
    limits=[]
    for keyword in ('sidehalo','fringeshieldhalo'):
        values=re.findall(r'(?m)^\s*'+keyword+r'\s+([\d.]+)\s*$',section)
        if len(values)!=1:raise ValueError('Ambiguous '+keyword+' interaction range.')
        value=float(values[0])
        if not math.isfinite(value) or value<=0:raise ValueError('Invalid interaction range.')
        limits.append(value)
    return max(limits)


def geometry(core,filled,halo):
    import klayout.db as k
    before,after=k.Layout(),k.Layout();before.read(str(core));after.read(str(filled))
    if before.dbu!=.001 or after.dbu!=.001 or before.top_cell().name!=after.top_cell().name:
        raise ValueError('Unexpected fill top cell or database units.')
    original=source_regions(before,before.top_cell());current=source_regions(after,after.top_cell())
    occupied=k.Region()
    for pair,shapes in original.items():
        if pair in FILL_LAYERS.values() and not shapes.is_empty():raise ValueError('Core already contains fill.')
        occupied+=shapes
    for pair in original.keys()|current.keys():
        if pair not in (*FILL_LAYERS.values(),BORDER):
            if not (original.get(pair,k.Region())^current.get(pair,k.Region())).is_empty():
                raise ValueError('Circuit mask changed: '+str(pair))
    blocked=occupied.merged().sized(math.ceil(halo/before.dbu));result={}
    for name,pair in FILL_LAYERS.items():
        tiles=current.get(pair,k.Region())
        if tiles.is_empty():raise ValueError('Missing '+name+' fill.')
        if not tiles.interacting(blocked).is_empty():raise ValueError('Fill is within the extraction range: '+name)
        result[name]={'tiles':tiles.count(),'area_um2':tiles.area()*after.dbu**2}
    return {'core_masks_unchanged':True,'all_fill_outside_range_um':halo,'fill':result}


def coupon(pair,gap,tech,magic,out):
    import klayout.db as k
    out.mkdir(parents=True);ly=k.Layout();ly.dbu=.001;top=ly.create_cell('fill_control')
    top.shapes(ly.layer(pair[0],0)).insert(k.Box(0,0,2000,20000))
    top.shapes(ly.layer(pair[0],10)).insert(k.Text('SIGNAL',k.Trans(1000,10000)))
    if gap is not None:
        x=2000+round(gap/ly.dbu)
        top.shapes(ly.layer(*pair)).insert(k.Box(x,0,x+2000,20000))
        # Labels name the isolated conductor; neither is electrically grounded.
        top.shapes(ly.layer(pair[0],10)).insert(k.Text('FLOATING',k.Trans(x+1000,10000)))
    ly.write(str(out/'purpose4.gds'))
    dummy=ly.find_layer(*pair)
    if dummy is not None:
        for shape in top.shapes(dummy).each():top.shapes(ly.layer(pair[0],0)).insert(shape)
        top.shapes(dummy).clear()
    ly.write(str(out/'conductors.gds'))
    atomic_write(out/'startup.tcl','drc off\ntech load '+tcl_word(tech)+'\n')
    body='scalegrid 1 10\ngds read '+tcl_word(out/'conductors.gds')+'\nload fill_control\nselect top cell\n'
    if gap is not None:body+='port FLOATING remove\n'
    body+='extract all\next2spice lvs\next2spice cthresh 0\next2spice -o extracted.spice\nputs FILL_CONTROL_COMPLETE\n'
    script='if {[catch {\n'+body+'} err]} {puts "FILL_CONTROL_ERROR $err"}\nquit -noprompt\n'
    atomic_write(out/'extract.tcl',script)
    log=execute([magic,'-dnull','-noconsole','-rcfile',out/'startup.tcl',out/'extract.tcl'],out)
    atomic_write(out/'engine.log',log)
    if 'FILL_CONTROL_COMPLETE' not in log or 'FILL_CONTROL_ERROR' in log:raise ValueError('Fill control extraction failed.')
    # Read authoritative aF values directly. ext2spice rounds tiny mutual C to
    # zero, and floating metal must not be replaced by a grounded capacitor.
    reduction=from_ext(out/'fill_control.ext',[] if gap is None else ['FLOATING'])
    atomic_write(out/'floating-reduction.json',json.dumps(reduction,indent=2))
    coupling=sum(v['value_f'] for v in reduction['input_coupling_f']
                 if {v['a'].upper(),v['b'].upper()}=={'SIGNAL','FLOATING'})
    return {'gap_um':gap,'signal_to_fill_f':coupling,'purpose4_sha256':file_digest(out/'purpose4.gds'),
            'materialized_sha256':file_digest(out/'conductors.gds'),'extracted_sha256':file_digest(out/'extracted.spice'),
            'effective_signal_ground_f':reduction['ground_f']['SIGNAL'],
            'floating_reduction_sha256':file_digest(out/'floating-reduction.json'),
            'floating_reduction_algorithm':reduction['algorithm']}


def qualify(core,filled,tech,magic,out):
    from icstudio.external_tools import executable_info
    magic=executable_info(magic)['path']
    core,filled,tech,out=map(lambda p:Path(p).resolve(),(core,filled,tech,out))
    if out.exists() and any(out.iterdir()):raise ValueError('Use a fresh fill evidence directory.')
    out.mkdir(parents=True,exist_ok=True);halo=range_um(tech.read_text())
    result={'status':'failed','technology_sha256':file_digest(tech),'core_sha256':file_digest(core),
            'filled_sha256':file_digest(filled),'geometry':geometry(core,filled,halo),'controls':{},
            'scope':'No direct core/fill interaction within this finite-range open-PDK model. Does not quantify longer-range fields, fill-to-fill networks or foundry-calibrated parasitics.'}
    try:
        for name in ('m1','m2','m3','m4'):
            rows={label:coupon(FILL_LAYERS[name],gap,tech,magic,out/name/label)
                  for label,gap in (('absent',None),('near',1.),('far',halo+2.))}
            result['controls'][name]=rows
            if rows['near']['signal_to_fill_f']<=0 or any(rows[k]['signal_to_fill_f']!=0 for k in ('absent','far')):
                raise ValueError('Fill coupling positive/negative control failed: '+name)
        result['status']='passed';return result
    finally:atomic_write(out/'qualification.json',json.dumps(result,indent=2))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for key in ('core','filled','tech','out'):ap.add_argument('--'+key,type=Path,required=True)
    ap.add_argument('--magic',required=True);a=ap.parse_args()
    print(json.dumps(qualify(a.core,a.filled,a.tech,a.magic,a.out),indent=2))
