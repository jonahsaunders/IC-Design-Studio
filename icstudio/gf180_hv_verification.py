"""Local GF180 C/D asymmetric 10 V DRC and unfiltered device extraction.

The bundled Apache-2.0 sources stay unchanged. Private copies remove implicit
label joins and comparison filtering. A separate written-metal guard audit is
required before attaching extracted bulk terminals to the physical substrate.
This route does not qualify other devices, antenna, density or fabrication.
"""
import json
import math
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

from .model import atomic_write, file_digest, scalar

SOURCE = Path(__file__).parent/'assets/physical/gf180_hv'
COMMIT = '9f992d5a9186d1f7820c58f039c484ad35b2edea'
HASHES = {
    'LICENSE':'cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30',
    'AUTHORS':'c61dc34be0b6186601f8809e9d2f76ade4e15c94948bf3cc1aa33470965cb6b6',
    'gf180mcu.drc':'1da08a5cefb3bb42caecf72397a23be67d7b03318501453ebc322297811fe14f',
    'gf180mcu.lvs':'e63cf0e288c5d0c10c7528f12d28871eb29c8334f63e1581de2b0719caae5ded',
}
MODELS = {'nmos_10p0_asym':'nfet_10v0_asym','pmos_10p0_asym':'pfet_10v0_asym'}


def assets(root=None):
    root=Path(root or SOURCE).resolve()
    lock=json.loads((root/'SOURCE.json').read_text(encoding='utf-8'))
    if (lock.get('commit')!=COMMIT or lock.get('modified_upstream_files') is not False
            or {n:r['sha256'] for n,r in lock.get('files',{}).items()}!=HASHES):
        raise ValueError('Unknown public GF180 high-voltage rule bundle.')
    result={'SOURCE.json':root/'SOURCE.json'}
    for name,sha in HASHES.items():
        path=root/name
        if path.is_symlink() or not path.is_file() or file_digest(path)!=sha:
            raise ValueError('Missing or changed GF180 rule dependency: '+name)
        result[name]=path
    return result


def copy_assets(destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    for name,path in assets().items():shutil.copyfile(path,destination/name)
    assets(destination)


def guard_connections(source,top):
    """Require physical metal ties for every substrate/deep-well tap contact.

    No text, implant, diffusion, well or common substrate joins metal nets.
    Each tap component must be contacted. Taps of one body domain must reach
    the same metal net. The published outer P guard must surround every DNW.
    """
    import klayout.db as k
    source=Path(source);sha=file_digest(source)
    ly=k.Layout();ly.read(str(source));cell=ly.cell(top)
    if cell is None or any(cell.each_inst()) or abs(ly.dbu-.001)>1e-12:
        raise ValueError('GF180 HV checks need a flat verification stream on the 1 nm grid.')
    def region(layer,datatype=0):
        index=ly.find_layer(layer,datatype)
        return k.Region() if index is None else k.Region([
            s.polygon for s in cell.shapes(index).each() if not s.is_text()]).merged()
    # This adapter is deliberately limited to the reviewed C/D HV stack.
    # Additional well/resistor/MIM derivations need separate body-domain rules.
    if any(not region(n).is_empty() for n in (21,204,110,75)):
        raise ValueError('GF180 HV guard audit does not support other well, resistor or MIM devices.')
    if region(226).is_empty():raise ValueError('Missing GF180 high-voltage recognition mask.')
    metal=(34,36,42,46,81);via=(35,38,40,41)
    netter=k.LayoutToNetlist(cell.name,ly.dbu);layers={}
    for number in metal+via:
        r=region(number)
        if number in metal:r+=region(number,4)
        r.merge();layers[number]=r;netter.register(r,'mask_'+str(number));netter.connect(r)
    for lower,cut,upper in zip(metal,via,metal[1:]):
        netter.connect(layers[lower],layers[cut]);netter.connect(layers[cut],layers[upper])
    netter.extract_netlist();netter.check_extraction_errors()
    comp,contacts,dnw=region(22),region(33),region(12)
    ptap=(comp&region(31)).outside(dnw).merged()
    wells=list(dnw.each())
    groups=[('substrate',ptap)]+[('deep-well-'+str(i),(comp&region(32)).inside(k.Region(p)).merged()) for i,p in enumerate(wells)]
    failures=[];rows=[]
    hulls=k.Region([k.Polygon(list(p.each_point_hull())) for p in ptap.each() if p.holes()])
    for i,p in enumerate(wells):
        if not (k.Region(p)-hulls).is_empty():failures.append(dict(kind='missing-outer-substrate-guard',domain=i))
    for name,guards in groups:
        nets=[];count=0
        if guards.is_empty():failures.append(dict(kind='missing-body-tap',domain=name))
        for guard in guards.each():
            cuts=contacts.inside(k.Region(guard))
            if cuts.is_empty():failures.append(dict(kind='uncontacted-body-tap',domain=name,bbox=str(guard.bbox())))
            for cut in cuts.each():
                count+=1
                if not (k.Region(cut)-layers[34]).is_empty():
                    failures.append(dict(kind='body-contact-without-metal',domain=name))
                net=netter.probe_net(layers[34],cut.bbox().center())
                nets.append(None if net is None else net.cluster_id)
        if not nets or None in nets or len(set(nets))!=1:
            failures.append(dict(kind='disconnected-body-metal',domain=name,nets=nets))
        rows.append(dict(domain=name,tap_components=guards.count(),contacts=count,metal_nets=nets))
    # Shared substrate must not stand in for distinct equal-name port metal.
    labels={}
    for number in metal:
        index=ly.find_layer(number,10)
        if index is None:continue
        for shape in cell.shapes(index).each():
            if not shape.is_text():continue
            text=shape.text;net=netter.probe_net(layers[number],k.Point(text.x,text.y))
            labels.setdefault(text.string,[]).append(None if net is None else net.cluster_id)
    for name,nets in labels.items():
        if None in nets or len(set(nets))!=1:failures.append(dict(kind='disconnected-port-metal',port=name,nets=nets))
    logs=[str(e) for e in netter.each_log_entry()]
    if logs:failures.append(dict(kind='metal-extraction-diagnostics',messages=logs))
    if file_digest(source)!=sha:raise ValueError('GF180 layout changed during guard checking.')
    return dict(schema=1,passed=not failures,qualified=False,gds_sha256=sha,domains=rows,
                port_metal=labels,failures=failures,engine_version=k.__version__,
                scope='Contacted GF180 HV body domains and written-metal continuity; native DRC and strict device LVS are separately required.')


def extraction_recipe(text):
    boundary='logger.info("Starting GF180 LVS comparison section")'
    if text.count(boundary)!=1:raise ValueError('GF180 public comparison boundary changed.')
    text=text.split(boundary)[0]
    replacements={
        'connect_implicit("*")':'top_level(true) # IC Design Studio: require physical wiring.',
        'sub = polygon_layer':'sub = polygon_layer\nicstudio_psub = extent.sized(1.um).not(dnwell).not(nwell)',
        'connect(sub         ,          ptap)':
            '# IC Design Studio: guard metal was checked independently before extraction.\n'
            'connect(sub, icstudio_psub)\nconnect(ptap, icstudio_psub)',
        'connect_global(sub  ,         substrate_name)':
            '# IC Design Studio: connect through physical substrate, without an invented global port.',
    }
    for before,after in replacements.items():
        if text.count(before)!=1:raise ValueError('GF180 public extraction declaration changed.')
        text=text.replace(before,after)
    for model,sd,marker in (('nmos_10p0_asym','nsd_ldmos','mvsd'),('pmos_10p0_asym','psd_ldmos','mvpsd')):
        before=f'extract_devices(mos4("{model}"), {{ "SD" => {sd},'
        after=f'extract_devices(dmos4("{model}"), {{ "S" => {sd}.not({marker}), "D" => {sd}.and({marker}),'
        if text.count(before)!=1:raise ValueError('GF180 asymmetric extraction declaration changed.')
        # Public device identification assigns the drain to MVSD/MVPSD. The
        # symmetric MOS extractor arbitrarily exchanges terminals on rotation.
        # Split the same derived diffusion by that physical marker and use the
        # native asymmetric extractor. Keep W/L, junctions and terminal masks.
        text=text.replace(before,'# IC Design Studio: preserve physical asymmetric drain/source identity.\n'+after)
    return text+'''
# IC Design Studio: keep every device, parameter and measured terminal.
# Do not align with a reference, simplify, combine, purge or filter devices.
netlist
l2n_data.check_extraction_errors
netlist.make_top_level_pins
writer = RBA::NetlistSpiceWriter.new
writer.use_net_names = true
writer.with_comments = true
netlist.write($icstudio_netlist, writer, "Unfiltered GF180 HV extraction")
l2n_data.write_l2n($icstudio_netlist + ".l2n")
puts "ICSTUDIO_GF180_HV_EXTRACTION_COMPLETE"
'''


def convert(text):
    """Change only the two public HV model aliases and M/X element interface."""
    lines=re.sub(r'\n[ \t]*\+[ \t]*',' ',text).splitlines();changes=[];names=set()
    for i,line in enumerate(lines):
        tokens=line.split()
        if not tokens or tokens[0].startswith(('*','.')):continue
        if len(tokens)<8 or tokens[0][0].upper()!='M' or tokens[5] not in MODELS:
            raise ValueError('Unreviewed device in GF180 HV extraction.')
        if any('=' not in p for p in tokens[6:]):raise ValueError('Malformed GF180 extracted parameters.')
        params=[p.split('=',1)[0].upper() for p in tokens[6:]]
        if len(set(params))!=len(params) or set(params)!={'W','L','AS','AD','PS','PD'}:
            raise ValueError('Unexpected GF180 HV extraction parameters.')
        values={p.split('=',1)[0].upper():scalar(p.split('=',1)[1]) for p in tokens[6:]}
        if not all(math.isfinite(v) and v>0 for v in values.values()):
            raise ValueError('Invalid GF180 HV extracted geometry.')
        if not (4e-6-1e-15<=values['W']<=50e-6+1e-15 and .6e-6-1e-15<=values['L']<=20e-6+1e-15):
            raise ValueError('GF180 HV extracted width/length is outside the public model range.')
        name='X'+tokens[0][1:]
        if name.casefold() in names:raise ValueError('Duplicate GF180 extracted instance.')
        names.add(name);model=MODELS[tokens[5]]
        changes.append(dict(instance=tokens[0],replacement=name,source_model=tokens[5],model=model))
        tokens[0]=name;tokens[5]=model;lines[i]=' '.join(tokens)
    if not changes:raise ValueError('GF180 HV extraction has no devices.')
    return '\n'.join(lines)+'\n',changes


def _settings(source,folder,technology):
    target=technology.get('package_lock',{}).get('id')
    if target not in ('gf180mcuC','gf180mcuD'):raise ValueError('GF180 HV verification needs a C or D package.')
    return dict(input=Path(source).resolve(),thr=1,run_mode='flat',metal_top='9K' if target.endswith('C') else '11K',metal_level='5LM',mim_option='B')


def _execute(executable,entry,settings,folder):
    from .engines import execute
    args=[str(executable),'-b','-r',str(entry)]
    for key,value in settings.items():args+=['-rd',key+'='+str(value)]
    atomic_write(folder/'command.json',json.dumps(args,indent=2))
    try:log=execute(args,folder,timeout=300)
    except Exception as exc:atomic_write(folder/'console.log',str(exc));raise
    atomic_write(folder/'console.log',log)
    if re.search(r'(?m)^ERROR:',log):raise ValueError('GF180 native engine reported an error; see console.log.')
    return log


def drc(executable,source,top,technology,folder):
    folder=Path(folder);folder.mkdir();bundle=assets()
    # MDN.10d is a scalar 0.16 um min/max field gap. The public operand grows
    # only in X and misclassifies the same masks after a 90-degree rotation.
    # Grow both axes, still clipped to actual Poly2; retain every rule/limit.
    original='mdn_10d_field   = ncomp.and(poly2).sized(1.um, 0).and(poly2)'
    content=bundle['gf180mcu.drc'].read_text(encoding='utf-8')
    if content.count(original)!=1:raise ValueError('GF180 MDN.10d source declaration changed.')
    recipe=folder/'private.drc'
    atomic_write(recipe,content.replace(original,'# IC Design Studio: orientation-independent field operand.\n'+original.replace('sized(1.um, 0)','sized(1.um)')))
    recipe_sha=file_digest(recipe)
    settings=_settings(source,folder,technology);settings.update(report=folder/'findings.lyrdb',conn_drc='true')
    log=_execute(executable,recipe,settings,folder)
    if file_digest(recipe)!=recipe_sha:raise ValueError('GF180 private DRC recipe changed during execution.')
    if log.count('DRC Total Run time ')!=1:raise ValueError('GF180 full public DRC did not complete.')
    root=ET.parse(folder/'findings.lyrdb').getroot()
    if root.tag!='report-database' or root.findtext('top-cell')!=top or root.find('items') is None or root.find('categories') is None:
        raise ValueError('Malformed GF180 DRC report.')
    counts={}
    for item in root.findall('./items/item'):
        name=item.findtext('category')
        if not name:raise ValueError('Unnamed GF180 DRC finding.')
        counts[name]=counts.get(name,0)+1
    return dict(violations=sum(counts.values()),rules=counts,engine='klayout',source_commit=COMMIT,
                deck_sha256=file_digest(bundle['gf180mcu.drc']),recipe_sha256=recipe_sha,
                correction='MDN.10d field operand expanded on both axes; original 0.16 um minimum/maximum and all other rules retained.',
                settings={k:str(v) for k,v in settings.items()})


def extract(executable,source,top,ports,technology,folder):
    from .external_tools import check_extracted_interface
    from .ihp_klayout_lvs import order_top_ports
    folder=Path(folder);folder.mkdir();bundle=assets()
    guards=guard_connections(source,top)
    atomic_write(folder/'guard-connections.json',json.dumps(guards,indent=2))
    if not guards['passed']:raise ValueError('GF180 HV body/port wiring failed; see guard-connections.json.')
    copy_assets(folder/'source')
    recipe=folder/'private.lvs'
    atomic_write(recipe,extraction_recipe(bundle['gf180mcu.lvs'].read_text(encoding='utf-8')))
    settings=_settings(source,folder,technology)
    settings.update(report=folder/'extraction.lvsdb',target_netlist=folder/'automatic.cir',icstudio_netlist=folder/'native.cir')
    hashes={p:file_digest(p) for p in [recipe,*bundle.values(),*list((folder/'source').iterdir())]}
    log=_execute(executable,recipe,settings,folder)
    if log.count('ICSTUDIO_GF180_HV_EXTRACTION_COMPLETE')!=1:raise ValueError('GF180 unfiltered extraction did not complete.')
    native=folder/'native.cir';text,changes=convert(native.read_text(encoding='utf-8'))
    text,order=order_top_ports(text,top,ports)
    output=folder/'extracted.spice';atomic_write(output,text)
    check_extracted_interface(output,top,ports,technology)
    if any(file_digest(p)!=h for p,h in hashes.items()):raise ValueError('GF180 source or extraction recipe changed during execution.')
    return dict(deck='lvs-extraction/extracted.spice',sha256=file_digest(output),native_sha256=file_digest(native),
                source_commit=COMMIT,recipe_sha256=file_digest(recipe),interface_conversion=changes,
                top_port_order=order,guard_connections=guards,settings={k:str(v) for k,v in settings.items()})
