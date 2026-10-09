"""Independently captured interconnect corners for one final routed geometry."""
import json
import math
from pathlib import Path
import re

from .model import atomic_write, digest


def validate(platform):
    definition=platform.get('extraction')
    if definition is None:return
    if not isinstance(definition,dict) or set(definition)!={'cell_lefs','corners','coupling_threshold_ff'}:
        raise ValueError('Extraction needs cell LEFs, named corners and an explicit coupling threshold.')
    files={f['path']:f for f in platform.get('files',[])}
    def captured(path):
        if not isinstance(path,str) or path not in files or not files[path]['bytes']:
            raise ValueError('Extraction references a missing or empty captured platform file.')
    lefs=definition['cell_lefs']
    if not isinstance(lefs,list) or not lefs or any(not isinstance(p,str) for p in lefs) or len(set(lefs))!=len(lefs):
        raise ValueError('Extraction needs unique captured cell LEFs.')
    for path in lefs:captured(path)
    corners=definition['corners']
    if not isinstance(corners,dict) or not 1<=len(corners)<=20:
        raise ValueError('Define 1–20 interconnect extraction corners.')
    names=set()
    for name,fileset in corners.items():
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',name) or name.casefold() in names:
            raise ValueError('Extraction corner names must be distinct portable identifiers.')
        names.add(name.casefold())
        if not isinstance(fileset,dict) or set(fileset)!={'rules','technology_lef'}:
            raise ValueError('Every extraction corner needs rules and a matching technology LEF.')
        for path in fileset.values():captured(path)
    threshold=definition['coupling_threshold_ff']
    if type(threshold) not in (int,float) or not math.isfinite(threshold) or threshold<0:
        raise ValueError('The coupling threshold must be finite, nonnegative femtofarads.')


def selected(config):
    definition=config.get('platform',{}).get('extraction',{})
    available=definition.get('corners',{})
    corners=config.get('rc_corners',list(available))
    if not isinstance(corners,list) or any(not isinstance(c,str) for c in corners) or len(set(corners))!=len(corners) or any(c not in available for c in corners) or available and not corners:
        raise ValueError('Select unique interconnect corners from the locked platform.')
    if 'rc_corners' in config and not available:
        raise ValueError('This platform has no captured interconnect corner definitions.')
    return corners


def spef_metrics(path,top):
    """Reject empty/nonfinite extraction without claiming electrical acceptance."""
    text=Path(path).read_text();nets=0;section=None;resistors=0;capacitors=0;resistance=0.;capacitance=0.
    design=re.findall(r'^\*DESIGN\s+"?([^"\r\n]+)"?\s*$',text,re.M)
    if design!=[top]:raise ValueError('Extracted SPEF names a different design.')
    units={}
    for name in ('R','C'):
        matches=re.findall(r'^\*'+name+r'_UNIT\s+(\S+)\s+(\S+)\s*$',text,re.M)
        if len(matches)!=1:raise ValueError('Extracted SPEF lacks unambiguous units.')
        scale=float(matches[0][0])
        if not math.isfinite(scale) or scale<=0:raise ValueError('Invalid extracted SPEF units.')
        units[name]=' '.join(matches[0])
    for line in text.splitlines():
        fields=line.split()
        if not fields:continue
        if fields[0]=='*D_NET':
            if len(fields)!=3:raise ValueError('Malformed extracted net capacitance.')
            value=float(fields[2]);nets+=1
            if not math.isfinite(value) or value<0:raise ValueError('Invalid extracted net capacitance.')
        if fields[0] in ('*CAP','*RES','*END','*CONN'):section=fields[0];continue
        if section not in ('*CAP','*RES') or not fields[0].isdigit():continue
        if len(fields) not in ((3,4) if section=='*CAP' else (4,)):
            raise ValueError('Malformed extracted RC element.')
        value=float(fields[-1])
        if not math.isfinite(value) or value<0:raise ValueError('Invalid extracted RC element.')
        if section=='*RES':resistors+=1;resistance+=value
        else:capacitors+=1;capacitance+=value
    if not nets or not resistors or not capacitors or not math.isfinite(resistance+capacitance) or resistance<=0 or capacitance<=0:
        raise ValueError('Extraction produced no positive routed resistance or capacitance.')
    return {'nets':nets,'resistors':resistors,'capacitors':capacitors,'units':units,
            'sum_resistance_values':resistance,'sum_capacitance_values':capacitance,
            'scope':'Raw SPEF element sums in reported units; not path delay or signoff acceptance.'}


def extract(r):
    from .digital_implementation import tcl_word
    corners=selected(r.config)
    if not corners:return
    definition=r.platform['extraction'];locks={f['path']:f for f in r.platform['files']}
    root=r.root/'platform'
    report={'schema':1,'status':'complete','platform_fingerprint':r.platform['fingerprint'],
        'definition_sha256':digest(definition),'def':r.artifacts['def'],'netlist':r.artifacts['netlist'],
        'coupling_threshold_ff':definition['coupling_threshold_ff'],'corners':{},
        'scope':'Independent OpenRCX runs on the same final DEF, using each corner technology LEF and extraction deck.'}
    for corner in corners:
        files=definition['corners'][corner];folder=r.root/'extraction'/corner;folder.mkdir(parents=True)
        # Rebuild the database from the final DEF so via/layer properties come
        # from this corner's technology LEF, not the nominal implementation DB.
        lines=['read_lef '+tcl_word(root/files['technology_lef'])]
        lines += ['read_lef '+tcl_word(root/path) for path in definition['cell_lefs']]
        lines += ['read_liberty '+tcl_word(path) for path in r.libraries()]
        lines += ['read_def '+tcl_word(r.root/r.artifacts['def']['path']),
            'define_process_corner -ext_model_index 0 icstudio_rc',
            'extract_parasitics -ext_model_file '+tcl_word(root/files['rules'])+
                ' -coupling_threshold '+str(definition['coupling_threshold_ff']),
            'write_spef '+tcl_word(folder/'parasitics.spef')]
        script=folder/'extract.tcl';atomic_write(script,'if {[catch {\n'+'\n'.join(lines)+'\n} message]} {puts stderr $message; exit 1}\nexit 0\n')
        r.command([r.tools['openroad'],'-no_init','-exit',str(script)],'Extracting interconnect · '+corner,fraction=.96)
        metrics=spef_metrics(folder/'parasitics.spef',r.config['top'])
        key='spef_'+corner;r.add_artifact(key,folder/'parasitics.spef');r.add_artifact('extraction_script_'+corner,script)
        report['corners'][corner]={'spef_key':key,'spef':r.artifacts[key],
            'inputs':{path:locks[path] for path in [*files.values(),*definition['cell_lefs']]},'metrics':metrics}
    r.save_json('extraction',report,'extraction.json')


def timing_sources(r):
    """Resolve only hash-verified upstream parasitics for the selected RC set."""
    from .digital_implementation import verify_upstream
    upstream=r.settings.get('upstream',{});artifacts=upstream.get('artifacts',{})
    if r.config.get('physical',{}).get('gf180_fill') and 'fill' not in artifacts:
        raise ValueError('Run physical finish with GF180 fill before extracted timing.')
    if not any(k=='spef' or k.startswith('spef_') for k in artifacts):return [(None,None)]
    verify_upstream(upstream);corners=selected(r.config)
    from .digital_gf180_fill import verify as verify_fill
    verify_fill(upstream,r.config)
    if not corners:return [(None,'spef')]
    if 'extraction' not in artifacts:
        raise ValueError('Run physical finish with the selected interconnect corners before extracted timing.')
    report=json.loads((Path(upstream['root'])/artifacts['extraction']['path']).read_text())
    if (report.get('schema')!=1 or report.get('status')!='complete' or
        report.get('platform_fingerprint')!=r.platform['fingerprint'] or
        report.get('definition_sha256')!=digest(r.platform['extraction']) or
        report.get('def')!=artifacts.get('def') or report.get('netlist')!=artifacts.get('netlist')):
        raise ValueError('Extraction evidence does not match the captured platform and final geometry/netlist.')
    for corner in corners:
        item=report.get('corners',{}).get(corner,{})
        if item.get('spef_key')!='spef_'+corner or item.get('spef')!=artifacts.get('spef_'+corner):
            raise ValueError('Missing captured extraction for interconnect corner: '+corner)
    return [(corner,'spef_'+corner) for corner in corners]
