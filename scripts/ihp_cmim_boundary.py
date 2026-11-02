"""Exploratory imported public-source cap_cmim geometry near MIM.g.

Directly calls the pinned Magic draw procedure beyond its 30 um UI check;
this does not qualify that PCell's default or parameter-check behavior.
Native failures and all findings are retained; no operating rating is inferred.
"""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import sys
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from icstudio.interchange import export_layout
from icstudio.model import clone,file_digest,load_project,save_project
from icstudio.layout import rect
from icstudio.stream_contract import compare
from icstudio.layout_verification import reference,run
from icstudio.ihp_klayout_drc import read_report
from scripts.qualify_ihp_mim_layout import generate,rotate,altered,regions
from scripts.ihp_cmim_boundary_audit import circuit
from scripts.qualify_standard_mos import load_technology,write

# The direct draw centers rectangles on the origin.  A separate native probe
# measured the resulting written masks at these 20 nm dimension steps.
CASES=(('below',74.980,5623500000),('at',75.0,5625000000),('above',75.020,5626500000))


def geometry(project, expected_area):
    """Read actual imported masks and physical terminals independent of PCell metadata."""
    import klayout.db as k
    masks=regions(project); cap=masks.get((36,0),k.Region()); cuts=masks.get((129,0),k.Region())
    metal5=masks.get((67,0),k.Region()); top=masks.get((126,0),k.Region())
    polygons=list(cap.each())
    if len(polygons)!=1 or cap.area()!=expected_area or not polygons[0].is_box():
        raise ValueError('Imported MIM must be one rectangular mask of the exact requested area.')
    box=polygons[0].bbox()
    expected_dimensions={5623500000:[74980,75000],5625000000:[75000,75000],5626500000:[75000,75020]}
    if sorted((box.width(),box.height())) != expected_dimensions[expected_area]:
        raise ValueError('Imported MIM dimensions are outside the selected cases.')
    if (cuts & cap).is_empty() or (metal5 & cap).is_empty() or (top & cap).is_empty():
        raise ValueError('Missing physical capacitor, contact, or plate masks.')
    cell=project['cells'][0]; layers={r['name']:(r['gds'],r['datatype']) for r in project['pdk']['layers']}
    pins=cell.get('layout_ports',[])
    if len(pins)!=2 or {p['name'] for p in pins}!={'C1','C2'}:
        raise ValueError('Imported capacitor must retain exactly two named ports.')
    details=[]
    for pin in pins:
        pair=layers[pin['layer']]; region=masks.get(pair,k.Region()); point=k.Point(*pin['point'])
        if pair != {'C1':(126,0),'C2':(67,0)}[pin['name']]:
            raise ValueError('Port layer differs from the pinned draw procedure electrode mapping.')
        if not any(poly.inside(point) for poly in region.each()):raise ValueError('Port is not inside its conductor.')
        details.append(dict(name=pin['name'],layer=list(pair),point=pin['point']))
    return dict(area_nm2=cap.area(),width_nm=box.width(),height_nm=box.height(),
                bounds_nm=[box.left,box.bottom,box.right,box.top],pins=details,
                masks={f'{a}/{b}':dict(area_nm2=r.area(),components=len(list(r.each()))) for (a,b),r in sorted(masks.items())})


def fault_layout(project, fault):
    """Construct explicit 75 um coupon controls; native reports determine detection."""
    if fault=='missing-contacts':return altered(project,fault)
    q=clone(project);cell=q['cells'][0];layers={(v['gds'],v['datatype']):v['name'] for v in q['pdk']['layers']}
    caps=[s for s in cell['shapes'] if s['layer']==layers[36,0]]
    if len(caps)!=1:raise ValueError('Expected one capacitor for physical fault.')
    edge=max(x for x,y in caps[0]['points'])
    if fault=='plate-short':
        # Via outside MIM but inside the original 600 nm Metal5 surround;
        # the TopMetal1 tab overlaps the top plate and encloses this via.
        cell['shapes'] += [rect(layers[126,0],edge-400,-820,910,1640),
                           rect(layers[125,0],edge+90,-210,420,420)]
    else:raise ValueError('Unknown boundary physical fault.')
    return q


def category_counts(folder):
    decks={}
    for name in ('main','maximal'):
        path=folder/'drc'/name/'findings.lyrdb'
        if not path.is_file():raise ValueError('Missing native public '+name+' report.')
        data=read_report(path);counts={}
        for finding in data['findings']:
            rule=finding['rule'];counts[rule]=counts.get(rule,0)+1
        decks[name]=dict(count=data['count'],categories=counts,sha256=file_digest(path))
    return decks


def selected(length,physical_reference=False,swapped=False):
    if physical_reference:
        # cap_cmim.sym declares a C-prefixed LVS form. This is an explicit
        # physical reference, not a rewrite or proof of the simulation X form.
        w=Decimal('75');l=Decimal(str(length));area=w*l;perimeter=2*(w+l)
        terminals='C2 C1' if swapped else 'C1 C2'
        line=f'C1 {terminals} cap_cmim w={w}u l={l}u A={area}p P={perimeter}u m=1'
    else:
        line=f'X1 C1 C2 cap_cmim w=75u l={length:g}u m=1'
    return reference(f'.subckt coupon C1 C2\n{line}\n.ends coupon\n','coupon')


def physical(project,folder,tools,length,physical_reference=False,swapped=False):
    result=run(project,project['top'],folder,tools,selected(length,physical_reference,swapped),lvs_extractor='ihp-klayout',drc_engine='ihp-public')
    stages={s['name']:s['status'] for s in result['stages']}
    row=dict(status=result['status'],stages=stages,drc_count=result.get('drc_count'),error=result.get('error'),
             report_sha256=file_digest(folder/'report.json'))
    row['decks']=category_counts(folder)
    for name,path in (('native','lvs-extraction/native.cir'),('extracted','lvs-extraction/extracted.spice'),('lvs_log','lvs/lvs.log')):
        if (folder/path).is_file():row[name+'_sha256']=file_digest(folder/path)
    return row


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--pilot',action='store_true',help='Only the below-limit unrotated case; not a complete boundary run.')
    ap.add_argument('--physical-reference',action='store_true',help='Use the pinned symbol C-form physical LVS reference, not the simulation X form.')
    for name in ('magic','netgen','klayout'):ap.add_argument('--'+name,required=True)
    a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    tools={n:str(Path(getattr(a,n)).resolve(strict=True)) for n in ('magic','netgen','klayout')}
    report=dict(schema=1,status='RUNNING',qualified=False,chunk_complete=False,scope=__doc__,pilot=a.pilot,
        reference_form='physical-C' if a.physical_reference else 'simulation-X',
        geometry_recipe='Pinned cap_cmim_draw, centered rectangles at independently probed 20 nm dimension/10 nm edge steps; bypasses UI check and is not default PCell qualification.',
        cases=[],faults=[])
    write(out/'report.json',report)
    try:
        tech,identity=load_technology('ihp-sg13g2');report['package']=identity
        for name,length,area in (CASES[:1] if a.pilot else CASES):
            p=generate(tech,75,length,out/('generator-'+name),tools['magic'])
            save_project(p,out/(name+'.icproj'));q=load_project(out/(name+'.icproj'))
            before=geometry(p,area);after=geometry(q,area)
            if before!=after:raise ValueError('Save/reopen changed capacitor mask or pin geometry.')
            for angle in ((0,) if a.pilot else (0,90)):
                current=q if angle==0 else rotate(q);row=dict(case=name,length_um=length,rotation=angle,status='RUNNING')
                try:
                    row['geometry']=geometry(current,area);export_layout(current,out/f'{name}-{angle}.oas')
                    dest=out/f'{name}-{angle}';row['physical']=physical(current,dest,tools,length,a.physical_reference)
                    row['exchange']=compare(dest/'original.gds',out/f'{name}-{angle}.oas',text_presentation=False)
                    if a.physical_reference:
                        row['independent_netlists']={kind:circuit((dest/path).read_text(),length) for kind,path in
                            (('native','lvs-extraction/native.cir'),('extracted','lvs-extraction/extracted.spice'),('reference','schematic-lvs.spice'))}
                    row['status']='OBSERVED'
                except Exception as exc:row.update(status='ERROR',error=repr(exc),traceback=traceback.format_exc())
                report['cases'].append(row);write(out/'report.json',report)
            if name=='below' and not a.pilot:
                for fault in ('wrong-width','missing-contacts','plate-short'):
                    row=dict(fault=fault,status='RUNNING')
                    try:
                        # Complete 73 um drawn device against unchanged 75 um
                        # physical reference tests native area/perimeter LVS.
                        altered_project=generate(tech,73,length,out/'generator-fault-wrong-width',tools['magic']) if fault=='wrong-width' else fault_layout(q,fault)
                        row.update(status='OBSERVED',physical=physical(altered_project,out/('fault-'+fault),tools,length,a.physical_reference))
                    except Exception as exc:row.update(status='ERROR',error=repr(exc),traceback=traceback.format_exc())
                    report['faults'].append(row);write(out/'report.json',report)
                if a.physical_reference:
                    row=dict(fault='swapped-reference',status='RUNNING')
                    try:
                        dest=out/'fault-swapped-reference';row['physical']=physical(q,dest,tools,length,True,True)
                        try:circuit((dest/'schematic-lvs.spice').read_text(),length)
                        except ValueError as exc:row['independent_order_rejection']=str(exc)
                        else:raise ValueError('Independent ordered-pin control escaped.')
                        row['status']='OBSERVED'
                    except Exception as exc:row.update(status='ERROR',error=repr(exc),traceback=traceback.format_exc())
                    report['faults'].append(row);write(out/'report.json',report)
        report['status']='OBSERVED' if all(r['status']=='OBSERVED' for r in report['cases']+report['faults']) else 'ERROR'
    except Exception as exc:report.update(status='ERROR',error=repr(exc),traceback=traceback.format_exc())
    write(out/'report.json',report);print(json.dumps(report,indent=2));return int(report['status']!='OBSERVED')


if __name__=='__main__':raise SystemExit(main())
