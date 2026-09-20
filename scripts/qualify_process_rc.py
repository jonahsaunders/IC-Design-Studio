"""Independent acceptance probes for actual pinned-process RC extraction.

The metal coupon is an extraction-tool reference, not measured-silicon
calibration. Its constants are transcribed from the locked nominal SKY130 deck.
"""
import json
import math
import re
import argparse
import sys
import shlex
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

from icstudio.model import clone, example, scalar, atomic_write, file_digest, save_project


COUPON = {'length_um':100., 'width_um':1., 'port_inset_um':.5,
          'sheet_ohm':.125, 'area_af_per_um2':25.78, 'edge_af_per_um':40.57,
          'load_ohm':100., 'resistance_relative_tolerance':.02,
          'capacitance_relative_tolerance':.05,
          'capacitance_conservation_relative_tolerance':1e-4}


def accept_short_result(report, directory):
    """An actual port merge is detected before Netgen can compare the decks."""
    from qualify_layout_process import accept_result
    from icstudio.sky130_flow import subcircuit
    directory=Path(directory)
    if accept_result(report,'lvs',directory):return True
    stages=report.get('stages',[])
    failed=next((i for i,s in enumerate(stages) if s['status']=='failed'),None)
    if failed is None or stages[failed]['name']!='lvs_extraction':return False
    if any(s['status']!='passed' for s in stages[:failed]) or any(s['status']!='not_run' for s in stages[failed+1:]):return False
    if report.get('drc_count')!=0 or not stages[failed].get('error','').startswith('Extracted port order differs from the schematic:'):return False
    try:
        log=(directory/'lvs-extraction/console.log').read_text()
        if 'STUDIO_MAGIC_COMPLETE' not in log:return False
        name=report['cell_name']
        expected,_,_=subcircuit((directory/'schematic.spice').read_text(),name)
        actual,_,_=subcircuit((directory/'lvs-extraction/extracted.spice').read_text(),name)
    except (OSError,ValueError,KeyError):return False
    # A two-net deliberate bridge must remove exactly one of its two ports,
    # retain every other port, and have a corroborating geometric short finding.
    missing=set(expected)-set(actual)
    if len(missing)!=1 or len(expected)!=len(actual)+1 or not set(actual)<set(expected):return False
    return any(f.get('code')=='LVS.SHORT' and len(set(f.get('nets',[])))==2 and
               missing<set(f['nets'])<=set(expected) for f in report.get('findings',[]))


def reevaluate(directory):
    """Retain original evidence and explicitly correct only short classification."""
    from datetime import datetime, timezone
    directory=Path(directory);original=directory/'qualification.json'
    report=json.loads(original.read_text())
    if report.get('status') not in ('passed','failed') or report.get('extraction')!='rc':
        raise ValueError('Only a completed process RC run can be re-evaluated.')
    expected={'metal1-independent-rc-coupon'}
    for kind in report.get('circuits',[]):
        for corner,temp in report.get('conditions',[]):
            for bench in (('op','ac') if kind=='amplifier' else ('op','dc')):
                expected.add(f'{kind}_{bench}-{corner}-{temp}')
                expected.add(f'{kind}_{bench}-physical-{corner}-{temp}')
        expected.add(kind+'-stale-extraction')
        expected.update(kind+'-'+fault for fault in ('narrow-metal','route-open','wrong-channel-length','route-short'))
    names=[item['name'] for item in report.get('cases',[])]
    if not report.get('circuits') or not report.get('conditions') or len(set(names))!=len(names) or set(names)!=expected:
        raise ValueError('The original run must contain every declared qualification case exactly once.')
    corrected=[];engine_reports={}
    for item in report['cases']:
        if item.get('type')=='independent_rc_reference':
            coupons=item.get('evidence',{}).get('coupons',[])
            if len(coupons)!=2 or any(not all(key in row for key in ('capacitance_reference_f','capacitance_f','ac_admittance_capacitance_f')) for row in coupons):
                raise ValueError('Re-run the independent coupon with absolute capacitance and AC-admittance checks; differential-only evidence is insufficient.')
            for row in coupons:
                check_capacitance_conservation(row['capacitance_reference_f'],row['capacitance_f'],row['ac_admittance_capacitance_f'])
        path=directory/item['engine_report'] if item.get('engine_report') else None
        if path:
            engine=json.loads(path.read_text());engine_reports[item['engine_report']]=file_digest(path)
            if item['type']=='physical':process_evidence(engine,path.parent)
        if item['status']=='passed':continue
        if item.get('type')!='deliberate_fault' or not item['name'].endswith('-route-short') or not path or not accept_short_result(engine,path.parent):
            raise ValueError('Re-evaluation cannot accept this failure: '+item['name'])
        item.update(status='passed',expected_failure_stage='lvs_extraction_or_lvs')
        corrected.append({'case':item['name'],'engine_report_sha256':file_digest(path),
                          'extracted_sha256':file_digest(path.parent/'lvs-extraction/extracted.spice'),
                          'magic_log_sha256':file_digest(path.parent/'lvs-extraction/console.log')})
    report['status']='passed'
    report['reevaluation']={'created':datetime.now(timezone.utc).isoformat(),
        'reason':'Original acceptance required Netgen failure. A deliberate two-port short is correctly rejected at the extracted-interface gate after real Magic merges the ports. Only this classification is corrected; original engine reports and qualification.json are unchanged.',
        'original_report':'qualification.json','original_sha256':file_digest(original),
        'harness_files':{str(Path('scripts')/name):file_digest(Path(__file__).parent/name)
                         for name in ('qualify_process_rc.py','qualify_analog_process.py')},
        'corrected_cases':corrected,'engine_reports':engine_reports}
    atomic_write(directory/'qualification-reevaluated.json',json.dumps(report,indent=2))
    return report


def passive_values(text):
    """Read emitted numeric R/C values; reject unresolved or nonphysical data."""
    out={'R':[], 'C':[]}
    for line in re.sub(r'\n\s*\+\s*',' ',text).splitlines():
        tokens=line.split()
        if not tokens or tokens[0][0].upper() not in out:continue
        if len(tokens)!=4:raise ValueError('Expected a numeric four-field parasitic: '+line)
        value=scalar(tokens[3])
        if not math.isfinite(value) or value<=0:raise ValueError('Parasitic values must be finite and positive.')
        out[tokens[0][0].upper()].append({'name':tokens[0],'nodes':tokens[1:3],'value':value})
    return out


def check_capacitance_conservation(reference, extracted, admittance):
    """Differencing lengths cannot detect a constant device/coupling scale error."""
    if any(not math.isfinite(v) or v<=0 for v in (reference,extracted,admittance)):
        raise ValueError('Capacitance conservation requires positive finite measurements.')
    if any(not math.isclose(reference,v,rel_tol=COUPON['capacitance_conservation_relative_tolerance'],abs_tol=1e-19)
           for v in (extracted,admittance)):
        raise ValueError('Distributed RC did not conserve independent capacitance: '+
                         str({'reference_f':reference,'extracted_f':extracted,'ac_admittance_f':admittance}))


def original_coupon_capacitances(path,ports):
    """Independent, bounded reader for this three-terminal coupon's .ext C."""
    rows=[shlex.split(line) for line in Path(path).read_text().splitlines()]
    scale=next(float(r[2]) or 1 for r in rows if r and r[0]=='scale')*1e-18
    substrate=next(r[1] for r in rows if r and r[0]=='substrate')
    caps=[]
    for row in rows:
        if not row:continue
        if row[0]=='node':nodes=[row[1],substrate];value=float(row[3])*scale
        elif row[0]=='cap':nodes=row[1:3];value=float(row[3])*scale
        else:continue
        if not set(nodes)<=set(ports):raise ValueError('Unexpected internal node in independent coupon capacitance reference.')
        if value>0:caps.append({'nodes':nodes,'value':value})
    return caps


def maxwell_matrix(capacitors,ports):
    matrix=[[0. for _ in ports] for _ in ports]
    for cap in capacitors:
        a,b=[ports.index(node) for node in cap['nodes']];c=cap['value']
        matrix[a][a]+=c;matrix[b][b]+=c;matrix[a][b]-=c;matrix[b][a]-=c
    return matrix


def maxwell_probe(project,cid,tools,network,reference,ports,directory):
    """Measure every terminal current for each independent AC excitation."""
    from icstudio.engines import run_deck
    directory=Path(directory);directory.mkdir()
    expected=maxwell_matrix(reference,ports);observed=[[0. for _ in ports] for _ in ports];hashes={}
    passive='\n'.join(v['name']+' '+' '.join(v['nodes'])+' '+repr(v['value'])
                      for kind in ('R','C') for v in network[kind])+'\n'
    for excitation in range(len(ports)):
        deck='* Independent full terminal capacitance matrix\n'+passive
        deck+='\n'.join('V'+str(i)+' '+port+' 0 AC '+str(int(i==excitation)) for i,port in enumerate(ports))+'\n'
        deck+='.ac lin 2 1000 1001\n.save '+' '.join('i(v'+str(i)+')' for i in range(len(ports)))+' v('+ports[excitation]+')\n.end\n'
        path=directory/(str(excitation)+'.cir');atomic_write(path,deck)
        result=run_deck(project,cid,{'type':'deck','deck':str(path)},tools['ngspice'],directory/str(excitation))
        atomic_write(directory/str(excitation)/'result.json',json.dumps(result,indent=2))
        for terminal in range(len(ports)):
            name='v'+str(terminal)
            current=result['currents'][name][0];phase=math.radians(result['current_phase'][name][0])
            observed[terminal][excitation]=-current*math.sin(phase)/(2*math.pi*result['x'][0])
        hashes[path.name]=file_digest(path)
    evidence={'terminals':ports,'frequency_hz':1000,'expected_f':expected,'ac_admittance_f':observed,
              'max_absolute_error_f':max(abs(a-b) for r,s in zip(expected,observed) for a,b in zip(r,s)),
              'deck_sha256':hashes,'scope':'Every terminal excited against all others at AC ground; includes signed mutual terms and substrate capacitance.'}
    atomic_write(directory/'comparison.json',json.dumps(evidence,indent=2))
    if any(not math.isclose(a,b,rel_tol=1e-5,abs_tol=1e-24) for r,s in zip(expected,observed) for a,b in zip(r,s)):
        raise ValueError('Distributed RC changed the original terminal capacitance matrix: '+str(evidence))
    return evidence


def process_evidence(report, directory):
    """A passing label alone cannot qualify RC, provenance, or actual engines."""
    directory=Path(directory)
    if report.get('status')!='passed' or report.get('physical_extraction')!={'mode':'rc'}:
        raise ValueError('The complete saved-bench process RC flow must pass.')
    stages={s['name']:s for s in report.get('stages',[])}
    required=('preflight','schematic_simulation','drc','lvs_extraction','lvs',
              'capacitance_extraction','post_layout_simulation','integrity')
    if any(stages.get(name,{}).get('status')!='passed' for name in required):
        raise ValueError('Missing or failed physical verification stage.')
    data=stages['capacitance_extraction']['evidence']
    if data.get('mode')!='rc' or not data.get('profile',{}).get('distributed_resistance'):
        raise ValueError('Capacitance-only evidence cannot qualify distributed RC.')
    from icstudio.magic_rc import ALGORITHM
    normalization=data.get('profile',{}).get('capacitance_normalization',{})
    if (normalization.get('algorithm')!=ALGORITHM or normalization.get('conservation',{}).get('status')!='passed' or
            normalization.get('export',{}).get('status')!='passed'):
        raise ValueError('Current process RC requires conserved capacitance and a verified final export.')
    from icstudio.hierarchical_flow import verify_integrity
    integrity=stages['integrity']['evidence']
    verify_integrity(directory,integrity['files'],integrity['assets'],integrity['tools'])
    extraction=(directory/data['deck']).parent;normalization_path=extraction/'rc-normalization.json'
    if json.loads(normalization_path.read_text())!=normalization:
        raise ValueError('The normalization profile differs from its retained report.')
    if normalization.get('implementation_sha256')!=file_digest(ROOT/'icstudio/magic_rc.py'):
        raise ValueError('Capacitance normalization source differs from current implementation.')
    required={normalization_path.relative_to(directory).as_posix():file_digest(normalization_path)}
    for name,expected in normalization.get('files',{}).items():
        path=(extraction/name).resolve()
        if not path.is_relative_to(extraction.resolve()) or file_digest(path)!=expected:
            raise ValueError('Changed normalization/extraction input: '+name)
        required[path.relative_to(directory.resolve()).as_posix()]=expected
    exported=normalization['export']
    if (exported.get('file')!=Path(data['deck']).name or exported.get('sha256')!=file_digest(directory/data['deck']) or
            exported.get('raw_file') not in normalization.get('files',{}) or
            exported.get('raw_sha256')!=normalization['files'][exported['raw_file']]):
        raise ValueError('Final export and raw exporter evidence are not bound to normalization.')
    if any(integrity['files'].get(name)!=sha for name,sha in required.items()):
        raise ValueError('Flow integrity must bind normalization and every raw/final extraction file.')
    network=passive_values((directory/data['deck']).read_text())
    if len(network['R'])<=stages['lvs_extraction']['evidence'].get('resistors',0) or not network['C']:
        raise ValueError('The extracted network must add positive distributed R and C.')
    comparisons=report.get('measurement_comparison',[])
    if not comparisons or any(r.get('before') is None or r.get('after') is None for r in comparisons):
        raise ValueError('The saved measurements must exist before and after extraction.')
    return {'resistors':len(network['R']),'capacitors':len(network['C']),
            'sum_resistance_ohm':sum(v['value'] for v in network['R']),
            'sum_capacitance_f':sum(v['value'] for v in network['C']),
            'deck_sha256':file_digest(directory/data['deck']),
            'measurements':comparisons,'integrity_verified':True}


def stale_evidence_probe(report, source, directory):
    """Corrupt a copy of real extraction; preserve the original accepted files."""
    from icstudio.hierarchical_flow import verify_integrity
    source=Path(source);directory=Path(directory);directory.mkdir(parents=True)
    extraction=next(s['evidence'] for s in report['stages'] if s['name']=='capacitance_extraction')
    original=source/extraction['deck'];copy=directory/'extracted.spice'
    text=original.read_text();atomic_write(copy,text)
    locked={'extracted.spice':file_digest(copy)}
    verify_integrity(directory,locked,{}, {})
    atomic_write(copy,text+'\n* Deliberately stale qualification evidence\n')
    try:verify_integrity(directory,locked,{}, {})
    except ValueError as error:
        return {'status':'passed','source_sha256':file_digest(original),
                'expected_sha256':locked['extracted.spice'],'changed_sha256':file_digest(copy),
                'observed_error':str(error)}
    raise ValueError('Changed extraction evidence was accepted.')


def coupon_project(technology, length_um):
    """A metal1 lead anchored to a real gate, avoiding shorted external ports."""
    from icstudio.layout import rect
    from icstudio.sky130_layout import layers, install_mos
    from icstudio.catalog import create_device
    from icstudio.physical_cells import assign_port
    p=example('empty');p['name']='Pinned SKY130 metal1 RC coupon';p['pdk']=clone(technology)
    c=p['cells'][0];c.update(name='rc_coupon',ports=['IN','DRAIN','VSS'])
    catalog=technology['simulation']['catalog']
    key=next(k for k,b in catalog.items() if b.get('model')=='sky130_fd_pr__nfet_01v8' and
             b.get('pin_order')==['d','g','s','b'] and b.get('emit_parameters',{}).get('w')=='w' and not b.get('unavailable'))
    d=create_device(p['pdk'],key,'MEND');d['params'].update(w='1u',l='.5u')
    d['nets']={'d':'DRAIN','g':'IN','s':'VSS','b':'VSS'};c['devices']=[d]
    install_mos(p,c['id'],d['id']);ls=layers(p['pdk'])
    pins={pin['pin']:pin['point'] for pin in c['layout_pins']};gx,gy=pins['g']
    start=gx-round(length_um*1000)
    c['shapes'].append(rect(ls['m1'],start,gy-500,gx-start+170,1000,net='IN'))
    bx,by=pins['b'];sx,sy=pins['s']
    c['shapes'].append(rect(ls['m1'],bx-170,by-170,sx-bx+340,340,net='VSS'))
    for name,point in [('IN',[start+500,gy]),('DRAIN',pins['d']),('VSS',pins['b'])]:
        assign_port(p,c['id'],name,ls['m1'],point)
    return p,c['id']


def coupon_probe(technology, tools, directory):
    """Differential coupons cancel identical device-contact/end corrections."""
    from icstudio.interchange import export_layout
    from icstudio.process_adapters import physical_adapter
    from icstudio.silicon_flow import magic_script
    from icstudio.external_tools import extraction_commands
    from icstudio.sky130_flow import subcircuit
    from icstudio.engines import run_deck
    directory=Path(directory);directory.mkdir(parents=True)
    technology_path=physical_adapter(technology).engine_assets(technology)['technology']
    measurements=[]
    for length in (100.,200.):
        work=directory/str(int(length));work.mkdir()
        p,cid=coupon_project(technology,length);cell=p['cells'][0]
        save_project(p,work/'input.icproj');export_layout(p,work/'coupon.gds')
        commands,profile=extraction_commands('rc')
        magic_script(tools['magic'],technology_path,work/'coupon.gds',cell['name'],cell['ports'],work/'extraction',
                     commands+'ext2spice -o extracted.spice')
        path=work/'extraction/extracted.spice';text=path.read_text();ports,body,_=subcircuit(text,'rc_coupon')
        if set(ports)!=set(cell['ports']):raise ValueError('Coupon port identity changed during extraction.')
        values=passive_values(body)
        devices=[line.split() for line in body.splitlines() if re.match(r'^X\S+\s',line,re.I)]
        if len(devices)!=1 or 'sky130_fd_pr__nfet_01v8' not in devices[0]:
            raise ValueError('The independent coupon must extract its one known gate anchor.')
        gate=devices[0][2];connected={'IN'};selected=[]
        for _ in range(len(values['R'])+1):
            more=[r for r in values['R'] if set(r['nodes'])&connected]
            expanded=connected|{node for r in more for node in r['nodes']}
            if expanded==connected:selected=more;break
            connected=expanded
        if gate not in connected or not selected:raise ValueError('Coupon gate is not connected through extracted resistance.')
        capacitance=sum(v['value'] for v in values['C'] if set(v['nodes'])&connected)
        base_commands,_=extraction_commands('capacitance')
        magic_script(tools['magic'],technology_path,work/'coupon.gds',cell['name'],cell['ports'],work/'capacitance-reference',
                     base_commands+'ext2spice -o extracted.spice')
        base_path=work/'capacitance-reference/extracted.spice'
        _,base_body,_=subcircuit(base_path.read_text(),'rc_coupon')
        reference_capacitance=sum(v['value'] for v in passive_values(base_body)['C'] if 'IN' in v['nodes'])
        # Run the actual extracted passive path with a known resistor load. The
        # transistor only anchors extraction, and is absent from this linear test.
        deck='* Independent extracted-resistor coupon transfer\n'
        deck+='\n'.join(r['name']+' '+' '.join(r['nodes'])+' '+repr(r['value']) for r in selected)+'\n'
        deck+='VDRIVE IN 0 1\nRLOAD '+gate+' 0 100\n.op\n.save v('+gate+')\n.end\n'
        atomic_write(work/'transfer.cir',deck)
        result=run_deck(p,cid,{'type':'deck','deck':str(work/'transfer.cir')},tools['ngspice'],work/'simulation')
        atomic_write(work/'simulation/result.json',json.dumps(result,indent=2))
        voltage=result['traces'][gate.lower()][0];resistance=COUPON['load_ohm']*(1/voltage-1)
        # With all other original nets grounded and no DC load, low-frequency
        # input susceptance is omega times the total physical IN capacitance.
        # This independent cap-only reference catches constant inflation that
        # cancels between long and short wire coupons.
        ac_deck='* Absolute distributed-capacitance conservation probe\n'
        ac_deck+='\n'.join(r['name']+' '+' '.join(r['nodes'])+' '+repr(r['value']) for r in selected)+'\n'
        for cap in values['C']:
            if not set(cap['nodes'])&connected:continue
            nodes=[node if node in connected else '0' for node in cap['nodes']]
            ac_deck+=cap['name']+' '+' '.join(nodes)+' '+repr(cap['value'])+'\n'
        ac_deck+='VDRIVE IN 0 AC 1\n.ac lin 2 1000 1001\n.save i(vdrive) v('+gate+')\n.end\n'
        atomic_write(work/'admittance.cir',ac_deck)
        ac=run_deck(p,cid,{'type':'deck','deck':str(work/'admittance.cir')},tools['ngspice'],work/'admittance')
        atomic_write(work/'admittance/result.json',json.dumps(ac,indent=2))
        current=ac['currents']['vdrive'][0];phase=math.radians(ac['current_phase']['vdrive'][0])
        admittance_capacitance=-current*math.sin(phase)/(2*math.pi*ac['x'][0])
        original_caps=original_coupon_capacitances(work/'capacitance-reference/rc_coupon.ext',cell['ports'])
        matrix=maxwell_probe(p,cid,tools,values,original_caps,cell['ports'],work/'maxwell')
        measurements.append({'length_um':length,'resistance_ohm':resistance,'capacitance_f':capacitance,
                             'terminal_capacitance_matrix':matrix,
                             'capacitance_reference_f':reference_capacitance,'ac_admittance_capacitance_f':admittance_capacitance,
                             'capacitance_reference_sha256':file_digest(base_path),
                             'admittance_probe_sha256':file_digest(work/'admittance.cir'),
                             'transfer_v':voltage,'extracted_sha256':file_digest(path),
                             'linear_probe_sha256':file_digest(work/'transfer.cir'),'gate_node':gate})
    length_delta=measurements[1]['length_um']-measurements[0]['length_um']
    resistance=measurements[1]['resistance_ohm']-measurements[0]['resistance_ohm']
    expected_resistance=COUPON['sheet_ohm']*length_delta/COUPON['width_um']
    capacitance=measurements[1]['capacitance_f']-measurements[0]['capacitance_f']
    expected_capacitance=(COUPON['area_af_per_um2']*COUPON['width_um']+2*COUPON['edge_af_per_um'])*length_delta*1e-18
    evidence={'reference':COUPON,'profile':profile,'coupons':measurements,
              'expected_delta_resistance_ohm':expected_resistance,'measured_delta_resistance_ohm':resistance,
              'expected_delta_capacitance_f':expected_capacitance,'extracted_delta_capacitance_f':capacitance,
              'technology_sha256':file_digest(technology_path),
              'scope':'100/200 µm straight metal1 leads with the same device contact; differencing cancels contact/end effects. Pinned deck model, not measured silicon or field-solver calibration.'}
    atomic_write(directory/'comparison.json',json.dumps(evidence,indent=2))
    for item in measurements:
        check_capacitance_conservation(item['capacitance_reference_f'],item['capacitance_f'],item['ac_admittance_capacitance_f'])
    if not math.isclose(resistance,expected_resistance,rel_tol=COUPON['resistance_relative_tolerance']):
        raise ValueError('Process coupon resistance disagrees with sheet-R × added length/width: '+str(evidence))
    if not math.isclose(capacitance,expected_capacitance,rel_tol=COUPON['capacitance_relative_tolerance']):
        raise ValueError('Process coupon capacitance disagrees with the locked area/perimeter reference: '+str(evidence))
    if measurements[1]['transfer_v']>=measurements[0]['transfer_v']:
        raise ValueError('Additional extracted route resistance did not reduce the independent loaded transfer.')
    return evidence


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--reevaluate',type=Path,required=True)
    print(json.dumps(reevaluate(ap.parse_args().reevaluate),indent=2))
