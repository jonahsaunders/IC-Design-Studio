"""Selected IHP coil physical interfaces, not electrical or EM qualification.

Uses two pinned public LVS fixtures. Retains their coil masks except an explicit
10 nm correction of a non-45-degree bridge edge in the center-tapped fixture.
Adds actual terminal leads and a contacted substrate. No simulation model is
invented or enabled. Exact source dimensions and every native report are kept.
"""
import argparse
import json
import re
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from icstudio.model import file_digest, load_project, save_project
from icstudio.layout_verification import reference, run
from icstudio.layout_import import read_layout
from icstudio.catalog import link_technology
from icstudio.interchange import export_layout
from icstudio.stream_contract import compare
from scripts.qualify_standard_mos import load_technology, write

SOURCE_SHA = {'inductor': '16bc1f047713f3cfe4cc2122938996ceac6ec9668b1b44f60acdec8928c20d86',
              'inductor3': 'fe1fef03609a1c2318abaf9e0bdb1e2c92d9bc505f090274c3683bf8ae479516'}
PARAMETERS = {'inductor': dict(w=2e-6, s=2.1e-6, d=25.35e-6, nr_r=1),
              'inductor3': dict(w=2e-6, s=2.1e-6, d=25.85e-6, nr_r=2)}
FAULTS = ('winding-open', 'lead-open', 'missing-recognition', 'missing-marker', 'missing-role', 'duplicate-role',
          'reference-width', 'reference-spacing', 'reference-diameter', 'reference-turns',
          'reference-multiplicity', 'reference-substrate', 'reference-terminal')


def stream(source, target, model, rotation=0, fault=None):
    import klayout.db as k
    if model not in SOURCE_SHA or file_digest(source) != SOURCE_SHA[model]:
        raise ValueError('Changed public IHP inductor fixture.')
    if rotation not in (0, 90, 180, 270):
        raise ValueError('Use an orthogonal coupon rotation.')
    old = k.Layout(); old.read(str(source)); top = old.top_cell()
    markers = k.Region(top.begin_shapes_rec(old.find_layer(27, 0))).merged()
    marker = min(markers.each(), key=lambda p: p.bbox().center().x**2+p.bbox().center().y**2)
    bounds = marker.bbox().enlarged(5000)
    ly = k.Layout(); ly.dbu = old.dbu; cell = ly.create_cell('coil_coupon'); labels = []
    for i in old.layer_indexes():
        info = old.get_info(i); dest = ly.layer(info)
        for s in top.shapes(i).each():
            if s.is_text():
                t = s.text
                if not bounds.contains(k.Point(t.x, t.y)): continue
                # Printed dimension captions are not device recognition. Keep
                # the original in the source archive; omit them in this coupon.
                if (info.layer, info.datatype) == (63, 0) and not t.string.startswith('inductor'): continue
                cell.shapes(dest).insert(t)
                if (info.layer, info.datatype) == (27, 25): labels.append(t)
            elif not (k.Region(s.polygon) & k.Region(bounds)).is_empty():
                if not (k.Region(s.polygon)-k.Region(bounds)).is_empty():
                    raise ValueError('Source crop would cut a mask polygon.')
                cell.shapes(dest).insert(s)
    correction = []
    if model == 'inductor3':
        for s in list(cell.shapes(ly.layer(134, 0)).each()):
            if s.is_text(): continue
            if str(s.polygon) == '(-3340,61940;-3340,63940;-2470,63940;1630,68050;3340,68050;3340,66050;2470,66050;-1630,61940)':
                before = str(s.polygon)
                points = [k.Point(p.x+10 if (p.x,p.y) in ((1630,68050),(2470,66050)) else p.x, p.y) for p in s.polygon.each_point_hull()]
                s.polygon = k.Polygon(points)
                correction.append(dict(layer=[134, 0], before=before, after=str(s.polygon), maximum_displacement_nm=10,
                                       reason='Make both diagonal bridge edges exactly 45 degrees; bridge width remains 2 um.'))
        if len(correction) != 1: raise ValueError('Unexpected source bridge geometry.')
    for t in labels:
        layer = 134 if model == 'inductor' or t.string == 'LC' else 126
        cell.shapes(ly.layer(layer, 0)).insert(k.Box(t.x-1000, -5000, t.x+1000, t.y+1000))
        cell.shapes(ly.layer(layer, 2)).insert(k.Text({'LA': 'A', 'LB': 'B', 'LC': 'C'}[t.string], k.Trans(t.x, -3000)))
    for layer, box in [(1, (-20000,-20000,-18000,-18000)), (14, (-20180,-20180,-17820,-17820)), (8, (-20000,-20000,-18000,-18000))]:
        cell.shapes(ly.layer(layer, 0)).insert(k.Box(*box))
    for x in range(-19800, -18300, 400):
        for y in range(-19800, -18300, 400): cell.shapes(ly.layer(6, 0)).insert(k.Box(x, y, x+160, y+160))
    cell.shapes(ly.layer(8, 2)).insert(k.Text('S', k.Trans(-19000, -19000)))
    if fault == 'missing-cross-vias': cell.shapes(ly.layer(133, 0)).clear()
    elif fault == 'missing-marker': cell.shapes(ly.layer(27,0)).clear()
    elif fault == 'turn-short':
        shapes=k.Region(cell.shapes(ly.layer(134,0))).merged();b=shapes.bbox()
        edge=next(e for p in shapes.each() for e in p.each_edge() if e.x1==b.left and e.x2==b.left)
        y=(edge.y1+edge.y2)//2
        cell.shapes(ly.layer(134,0)).insert(k.Box(b.left+1000,y-1000,b.left+6100,y+1000))
    elif fault in ('missing-recognition', 'missing-role', 'duplicate-role'):
        pair = (63, 0) if fault == 'missing-recognition' else (27, 25)
        for s in list(cell.shapes(ly.layer(*pair)).each()):
            if s.is_text() and (s.text.string.startswith('inductor') if fault == 'missing-recognition' else s.text.string == 'LA'):
                if fault == 'duplicate-role':
                    t=s.text; cell.shapes(ly.layer(*pair)).insert(k.Text(t.string,k.Trans(t.x+5,t.y)))
                else: s.delete()
    elif fault in ('winding-open', 'lead-open'):
        if fault == 'winding-open':
            shapes = k.Region(cell.shapes(ly.layer(134, 0))).merged(); b = shapes.bbox()
            edge=next(e for p in shapes.each() for e in p.each_edge() if e.x1==b.left and e.x2==b.left)
            y=(edge.y1+edge.y2)//2
            cut = k.Box(b.left-100, y-100, b.left+2100, y+100); layer = 134
        else:
            t = next(t for t in labels if t.string == 'LA'); layer = 134 if model == 'inductor' else 126
            cut = k.Box(t.x-1100, -2000, t.x+1100, -1000)
        shapes = k.Region(cell.shapes(ly.layer(layer, 0)))-k.Region(cut)
        cell.shapes(ly.layer(layer, 0)).clear(); cell.shapes(ly.layer(layer, 0)).insert(shapes)
    elif fault is not None: raise ValueError('Unknown coil physical fault.')
    if rotation: cell.transform(k.Trans(rotation//90, False, 0, 0))
    ly.write(str(target))
    return dict(source_sha256=SOURCE_SHA[model], crop=str(bounds), local_geometry_correction=correction,
                omitted_annotations='Multiline dimension captions only; IND device and terminal recognition labels preserved.',
                added_geometry='2 um terminal leads outside IND; separate 2x2 um p+ substrate contact with 16 contacts and explicit conductor labels.')


def selected(model, fault=None):
    ports = ['A', 'B', 'S'] if model == 'inductor' else ['A', 'C', 'B', 'S']; nodes = list(ports)
    values = dict(PARAMETERS[model], m=1)
    key = {'reference-width':'w', 'reference-spacing':'s', 'reference-diameter':'d',
           'reference-turns':'nr_r', 'reference-multiplicity':'m'}.get(fault)
    if key: values[key] *= 2
    elif fault == 'reference-substrate': nodes[-1] = nodes[0]
    elif fault == 'reference-terminal': nodes[0], nodes[1] = nodes[1], nodes[0]
    elif fault is not None: raise ValueError('Unknown coil reference fault.')
    line = 'L1 '+' '.join(nodes)+' '+model+' '+' '.join(k+'='+str(v) for k,v in values.items())
    return reference('.subckt coil_coupon '+' '.join(ports)+'\n'+line+'\n.ends coil_coupon\n', 'coil_coupon')


def fault_detected(result, folder, fault, ports):
    """A failed process is not evidence that a deliberate design fault was found."""
    stages={s['name']:s for s in result['stages']}
    if result['status']!='failed' or type(result.get('drc_count')) is not int or any(stages.get(s,{}).get('status')!='passed' for s in ('preflight','layout_export')):
        return False
    folder=Path(folder)
    if fault.startswith('reference-'):
        stage=stages.get('lvs',{});log=folder/'lvs/lvs.log'
        return (stage.get('status')=='failed'
                and stage.get('error')=='Netgen did not establish a unique match with equivalent connected pins and no property errors. See lvs/lvs.log.'
                and all(stages.get(s,{}).get('status')=='passed' for s in ('drc','lvs_extraction','integrity'))
                and log.is_file() and re.search(r'Circuits do not match|Property errors|Netlists do not match|disconnected node:|\(no matching pin\)|Final result: Top level cell failed pin matching\.',log.read_text(),re.I) is not None)
    stage=stages.get('lvs_extraction',{})
    if stage.get('status')!='failed':return False
    if fault=='lead-open':
        path=folder/'lvs-extraction/native.cir'
        if stage.get('error')!='IHP extracted port names differ from the schematic.' or not path.is_file():return False
        declarations=re.findall(r'(?im)^\.subckt\s+coil_coupon\s+([^\r\n]*)',path.read_text())
        return len(declarations)==1 and set(declarations[0].split())!=set(ports)
    path=folder/'lvs-extraction/inductor-wiring.json'
    if stage.get('error')!='IHP inductor recognition/wiring audit failed; see inductor-wiring.json.' or not path.is_file():return False
    expected={'winding-open':'disconnected-winding-metal','missing-cross-vias':'disconnected-winding-metal',
              'turn-short':'shorted-or-ambiguous-winding-loop','missing-marker':'orphan-inductor-recognition',
              'missing-recognition':'missing-or-ambiguous-inductor-recognition',
              'missing-role':'missing-or-ambiguous-winding-terminal','duplicate-role':'missing-or-ambiguous-winding-terminal'}
    proof=json.loads(path.read_text())
    return proof['passed'] is False and expected[fault] in {r['kind'] for r in proof['failures']}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--sources', type=Path, required=True); ap.add_argument('--output', type=Path, required=True)
    for name in ('magic','netgen','klayout'): ap.add_argument('--'+name, required=True)
    ap.add_argument('--pilot', action='store_true'); a = ap.parse_args()
    out = a.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    tools = {n: str(Path(getattr(a,n)).resolve(strict=True)) for n in ('magic','netgen','klayout')}
    tech, identity = load_technology('ihp-sg13g2'); rows = []
    files = [Path(__file__), *sorted((ROOT/'icstudio').glob('*.py'))]
    before = {p.relative_to(ROOT).as_posix():file_digest(p) for p in files}; write(out/'source-files.json', before)
    for model in SOURCE_SHA:
        for angle in ((0,) if a.pilot else (0,90,180,270)):
            faults = [None, *FAULTS, *(['missing-cross-vias','turn-short'] if model == 'inductor3' else [])] if angle == 0 else [None]
            for fault in faults:
                folder = out/(model+'-'+str(angle)+'-'+str(fault)); folder.mkdir()
                row = dict(model=model,rotation=angle,fault=fault)
                try:
                    provenance = stream(a.sources/(model+'.gds'), folder/'source.gds', model, angle,
                                        fault if fault and not fault.startswith('reference-') else None)
                    write(folder/'source.json', provenance)
                    ref = selected(model, fault if fault and fault.startswith('reference-') else None)
                    p,_ = read_layout(folder/'source.gds'); link_technology(p,tech); p['cells'][0]['ports']=ref['ports']
                    save_project(p,folder/'saved.icproj'); p=load_project(folder/'saved.icproj')
                    export_layout(p,folder/'export.oas'); export_layout(p,folder/'export.gds')
                    row['exchange'] = compare(folder/'export.oas',folder/'export.gds',text_presentation=False)
                    r=run(p,p['top'],folder/'verification',tools,ref,lvs_extractor='ihp-klayout')
                    row.update(native_status=r['status'],error=r.get('error'),report_sha256=file_digest(folder/'verification/report.json'))
                    # Never count an unrelated preflight or tool failure as a detected fault.
                    detected = fault_detected(r,folder/'verification',fault,ref['ports']) if fault else r['status']=='passed'
                    row['status']='PASS' if detected else 'FAIL'
                except Exception as exc: row.update(status='FAIL',error=repr(exc),traceback=traceback.format_exc())
                rows.append(row); write(folder/'record.json',row); write(out/'progress.json',rows)
                print(model,angle,fault,row['status'],row.get('error',''),flush=True)
    unchanged = before == {p.relative_to(ROOT).as_posix():file_digest(p) for p in files}
    report=dict(schema=1,chunk=7,chunk_complete=False,qualified=False,default_promoted=False,
                scope=__doc__,process=identity,cases=rows,implementation_unchanged=unchanged,
                status='PASS' if unchanged and all(r['status']=='PASS' for r in rows) else 'FAIL')
    write(out/'qualification.json',report)
    return 0 if report['status']=='PASS' else 1


if __name__=='__main__': raise SystemExit(main())
