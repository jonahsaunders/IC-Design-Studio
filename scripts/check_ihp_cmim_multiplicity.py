"""Independent finite readback of two-unit CMIM physical multiplicity."""
import argparse
from decimal import Decimal, InvalidOperation
import json
import re
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.check_ihp_cmim_enclosures import (check_decks, data, expected_masks, extraction_command,
                                                require, safe_path, sha, stream, text)

CASES=('m2-0','pair-0','m2-90','pair-90','m1-0','m3-0','wrong-wire-0','missing-contact-0','wrong-width-0','physical-width-0')
SOURCE_HASHES={
    'icstudio/assets/physical/ihp_klayout_lvs/rule_decks/custom_combiner.lvs':'2e9f341023b96ab64ef83110d0a57d5f8be8a6906e67db60edbb62cfadeed56d',
    'icstudio/assets/physical/ihp_klayout_lvs/rule_decks/custom_reader.lvs':'c71b6713d8a62055d3d8e9e75a7f5f78140001bf76e3fa573b9883fab5e49f06',
    'docs/qualification/ihp-cmim-applicability-v1/04_06_cap.rst':'aebaa8a397b6409798e8f3ed189c0811d78c80be36979852220790828ce79006'}
PRIVATE_LVS={
 'rule_decks/cap_connections.lvs':'d1da00a7b550d3e9c8cfb61253c627d8cb5f18b2a406a3b508f8cfe29800942c',
 'rule_decks/custom_bjt_extractor.lvs':'2644f6f93eed681a52ee7f6da212c1794503e5421d9136788e6eda7c8fe3bcbc',
 'rule_decks/custom_extractor.lvs':'f7ea671a553e10216a3e107fb0884d2f5dbf717a3b77e8ba539f55f0866f4737',
 'rule_decks/diode_connections.lvs':'3aa44889da99d27ec665566e0647e302b255689e6662d952a16d22c5ddc0f0a1',
 'rule_decks/ind_connections.lvs':'743fa126000c7bc95cdae2bc16482750851736133db8e1704e9249183e76b28f',
 'rule_decks/ind_extraction.lvs':'733b7082d5c9a7390e171d2e51659b55cbb5e41c68f33f68d8ca8f84690d07fd'}

def copied_sources(flow):
    locks=(('drc','drc/rules','31601ee4ca33750dd2f580f6a8fc519bb5dbe99d504e72759fd97d538f4f3863'),
           ('lvs','lvs-extraction/deck','7b23e1228bc8e10e0772bec55aa3de1443042e6a9a6e5cffd7a8548a3f4c28bf'))
    for kind,subdir,lockhash in locks:
        lock=ROOT/('icstudio/assets/physical/ihp_klayout_'+kind)/'SOURCE.json'
        require(sha(lock)==lockhash,'Public source lock differs.')
        for name,entry in data(lock)['files'].items():
            part=Path(name);require(not part.is_absolute() and '..' not in part.parts and 'tmpuxoell2b' not in part.parts and '\\' not in name and ':' not in name,'Unsafe source member.')
            want=PRIVATE_LVS.get(name,entry['sha256']) if kind=='lvs' else entry['sha256']
            require(sha(flow/subdir/part)==want,'Copied native deck source differs: '+name)

def comparison_command(folder,flow,report):
    records=data(folder/'netgen-command.json');require(len(records)==1,'Netgen command count differs.')
    row=records[0];args=row['argv'];cwd=row['cwd'].replace('\\','/')
    require(cwd.endswith('/job/physical-flow/lvs') and '/../' not in cwd,'Netgen output path differs.')
    root=cwd[:-len('/lvs')];tool=report['stages'][0]['evidence']['tools']['netgen']['path']
    expected=[tool,'-batch','lvs','"'+root+'/schematic-lvs.spice" "coupon"',
              '"'+root+'/lvs-extraction/extracted.spice" "coupon"',root+'/ihp-strict-lvs.tcl',root+'/lvs/lvs.log','-json']
    require(args==expected and row['schematic_sha256']==sha(flow/'schematic-lvs.spice') and
        row['extracted_sha256']==sha(flow/'lvs-extraction/extracted.spice') and
        row['setup_sha256']==sha(flow/'ihp-strict-lvs.tcl')=='c68f3e6e5b5ed8634e91d36bb25f5cfed1694154f75075e4fd94944c2ff7eeb5' and
        report['comparison_setup']['source_sha256']=='9981101e0bbe9d8f6af656f03475d0d00fb7507559645e85e4d9d5f704b3878e',
        'Netgen invocation, setup or inputs differ.')

def masks(path,angle,extract=False,mode=''):
    import klayout.db as k
    original=expected_masks('MIM.c',600,0)
    second={key:region.dup() for key,region in original.items()};shift=7600
    if mode=='physical-width':
        shift=7700
        second[(36,0)]=k.Region(k.Box(-3600,-3500,3600,3500))
        second[(67,0)]=k.Region(k.Box(-4200,-4100,4200,4100))
        second[(189,4)]=k.Region(k.Box(-4200,-4100,4200,4100))
        second[(126,0)]=k.Region(k.Box(-3400,-3300,3400,3300))
    if mode=='missing-contact':second.pop((129,0))
    wanted={key:(region+second.get(key,k.Region()).transformed(k.Trans(shift,0))).merged() for key,region in original.items()}
    wanted[(126,0)]=(wanted[(126,0)]+k.Region(k.Box(3000,-3300,shift-3000,3300))).merged()
    if angle==90:wanted={key:r.transformed(k.Trans(k.Trans.R90,0,0)).merged() for key,r in wanted.items()}
    actual,labels=stream(path)
    require(set(actual)==set(wanted) and all((actual[k]^wanted[k]).is_empty() for k in wanted),'Pair mask differs.')
    require(len(list(actual[(36,0)].each()))==2 and len(list(actual[(129,0)].each()))==(25 if mode=='missing-contact' else 50),'Physical unit/contact count differs.')
    expected=[((126,2),'C1',0,0),((67,2),'C2',3600,0)]
    if angle==90:expected=[(layer,name,-y,x) for layer,name,x,y in expected]
    if extract:expected += [((layer[0],25),name,x,y) for layer,name,x,y in expected]
    require(labels==sorted(expected),'Pair electrode labels differ.')

def netlist(raw,mode,physical=False):
    rows=[line.split() for line in raw.splitlines() if line.strip() and not line.lstrip().startswith('*')]
    require(len(rows)>=3 and [x.lower() for x in rows[0][:2]]==['.subckt','coupon'] and rows[0][2:]==['C1','C2'] and
            [x.lower() for x in rows[-1]]==['.ends','coupon'],'Reference structure differs.')
    number=2 if mode in ('pair','wrong-wire','wrong-width') else 1;require(len(rows)==number+2,'Reference device count differs.')
    for i,row in enumerate(rows[1:-1]):
        pins=['C2','C1'] if mode=='wrong-wire' and i==1 else ['C1','C2']
        require(row[:4]==[('CX_C' if physical else 'X_C')+str(i+1),*pins,'cap_cmim'],'Reference device/pins differ.')
        values={}
        for item in row[4:]:
            require(item.count('=')==1,'Bad reference parameter.');key,value=item.lower().split('=')
            require(key not in values,'Duplicate parameter.')
            try:values[key]=Decimal(value)
            except InvalidOperation as exc:raise ValueError('Bad numeric parameter.') from exc
            require(values[key].is_finite(),'Nonfinite parameter.')
        m=Decimal(int(mode[1:])) if mode in ('m1','m2','m3') else Decimal(2 if mode in ('missing-contact','physical-width') else 1)
        width=Decimal('7.2e-6') if mode=='wrong-width' and i==1 else Decimal('7e-6')
        expected={'w':width,'l':Decimal('7e-6'),'m':m}
        expected.update({'a':width*Decimal('7e-6'),'p':2*(width+Decimal('7e-6'))} if physical else {'mm_ok':Decimal(1)})
        require(values==expected,'Reference geometry/multiplicity differs.')

def native(raw,mode=''):
    rows=[line.split() for line in raw.splitlines() if line.strip() and not line.lstrip().startswith('*')]
    require(len(rows)==4 and rows[0][:2]==['.SUBCKT','coupon'] and len(rows[0][2:])==2 and set(rows[0][2:])=={'C1','C2'} and
            rows[-1]==['.ENDS','coupon'],'Raw native interface differs.')
    for i,row in enumerate(rows[1:3]):
        top=row[1];require(len(row)==9 and row[0].startswith('C') and row[2:4]==['C2','cap_cmim'],'Raw physical unit differs.')
        require(bool(re.fullmatch(r'\\?\$\d+',top)) if mode=='missing-contact' and i==1 else top=='C1','Raw physical top differs.')
        values=['w=7.2u','l=7u','A=50.4p','P=28.4u','m=1'] if mode=='physical-width' and i==1 else ['w=7u','l=7u','A=49p','P=28u','m=1']
        require(row[4:]==values,'Raw physical geometry differs.')
    require(rows[1][0]!=rows[2][0],'Duplicate extracted device.')

def extracted_conversion(raw,converted,evidence):
    before=evidence['top_port_order']['before'];after=evidence['top_port_order']['after']
    require(len(before)==2 and set(before)=={'C1','C2'} and after==['C1','C2'] and evidence['interface_conversion']==[],
            'Unexpected extraction conversion.')
    old='.SUBCKT coupon '+' '.join(before);new='.SUBCKT coupon '+' '.join(after)
    require(raw.count(old)==1 and converted==raw.replace(old,new,1),'Comparison circuit differs from raw native devices.')

def verify_case(folder,name):
    mode,angle=name.rsplit('-',1);angle=int(angle);flow=folder/'job/physical-flow'
    for path in (folder/'selected.oas',flow/'original.gds',flow/'layout.gds'):masks(path,angle,mode=mode)
    masks(flow/'lvs-extraction/labels.gds',angle,True,mode)
    report=data(flow/'report.json');rows=report['stages']
    require([r['name'] for r in rows]==['preflight','layout_export','drc','lvs_extraction','lvs','integrity'],'Stage order differs.')
    positive=mode in ('m2','pair');expected={'preflight':'passed','layout_export':'passed','drc':'failed' if mode=='missing-contact' else 'passed','lvs_extraction':'passed','lvs':'passed' if positive else 'failed','integrity':'passed'}
    require({r['name']:r['status'] for r in rows}==expected,'Native stage outcomes differ.')
    check_decks(flow,report,[[],['MIM.h'] if mode=='missing-contact' else [],[]])
    copied_sources(flow);comparison_command(folder,flow,report)
    extraction=rows[3]['evidence'];mapping=extraction['label_mapping']
    require(mapping['source_sha256']==sha(flow/'original.gds') and mapping['sha256']==sha(flow/'lvs-extraction/labels.gds') and extraction['native_sha256']==sha(flow/'lvs-extraction/native.cir'),'Extraction identity differs.')
    extraction_command(data(flow/'lvs-extraction/command.json'),extraction['settings'],rows[0]['evidence']['tools']['klayout']['path'])
    console=text(flow/'lvs-extraction/console.log')
    for term in ('NET_ONLY enabled','LVS Total Run time','[layout_netlist] simplify: SKIPPED','[layout_netlist] combine_devices: SKIPPED','[layout_netlist] purge: SKIPPED','[layout_netlist] purge_nets: SKIPPED','[layout_netlist] purge_devices: SKIPPED'):
        require(term in console,'Unfiltered extraction incomplete.')
    raw_native=text(flow/'lvs-extraction/native.cir');native(raw_native,mode)
    extracted=text(flow/'lvs-extraction/extracted.spice')
    require(extraction['sha256']==sha(flow/'lvs-extraction/extracted.spice'),'Comparison extraction hash differs.')
    extracted_conversion(raw_native,extracted,extraction)
    original=text(folder/'captured-reference.spice');require(text(flow/'schematic.spice')==original,'Original X reference substituted.')
    sim=text(folder/'simulation-before.spice')
    require([line.strip() for line in sim.splitlines() if line.strip().startswith('X_C')]==
            [line.strip() for line in original.splitlines() if line.strip().startswith('X_C')], 'Exported simulation statements differ.')
    netlist(original,mode);netlist(text(flow/'schematic-lvs.spice'),mode,True)
    project=data(folder/'catalog.icproj');require(len(project['cells'])==1 and
        project['pdk']['package_lock']['id']=='ihp-sg13g2' and project['pdk']['package_lock']['revision']=='cfb96b74cf33877e','Project package differs.')
    package=ROOT/'icstudio/assets/pdks/ihp-sg13g2/package.json'
    require(sha(package)=='da58ba2de122d67d232ab20ca4fb353b70bdc68c00ef4279f9be7da640a68ae0' and
            project['pdk']['package_lock']['files']==data(package)['files'],'Full package lock differs.')
    devices=project['cells'][0]['devices'];count=2 if mode in ('pair','wrong-wire','wrong-width') else 1
    require(len(devices)==count,'Saved catalog count differs.')
    proof=report['reference_defaults'];require(len(proof)==count,'Projection receipt count differs.')
    for i,(device,row) in enumerate(zip(devices,proof),1):
        pins={'c0':'C2','c1':'C1'} if mode=='wrong-wire' and i==2 else {'c0':'C1','c1':'C2'}
        mult=int(mode[1:]) if mode in ('m1','m2','m3') else 2 if mode in ('missing-contact','physical-width') else 1
        params=device['model_params']
        require(device['kind']=='PDK' and device['name']=='C'+str(i) and device['nets']==pins and
            device['model_ref']=={'pdk':'ihp-sg13g2','revision':'cfb96b74cf33877e','device':'sg13g2_pr/cap_cmim.sym'} and
            'native_spice' not in device and set(params)=={'w','l','m','mm_ok'} and
            Decimal(str(params['w']))==Decimal('7.2e-6' if mode=='wrong-width' and i==2 else '7e-6') and Decimal(str(params['l']))==Decimal('7e-6') and
            type(params['m']) is int and params['m']==mult and type(params['mm_ok']) is int and params['mm_ok']==1,
            'Saved catalog device differs.')
        source=row['proof'];require(row['instance']=='X_C'+str(i) and row['physical_instance']=='CX_C'+str(i) and row['changed'] is True and
            source['source']=='libs.tech/xschem/sg13g2_pr/cap_cmim.sym' and source['sha256']=='b11c811ee178d260c4b7afcaa8c123f8a6c8c108dde1a119c91aa4386d24e20b' and
            source['model_sha256']=='ff9eb4cc9fdccc0645d9db0bd37e25e9fee2a633765910a7f55ac2084c49695f' and
            source['geometry_reader_sha256']==SOURCE_HASHES['icstudio/assets/physical/ihp_klayout_lvs/rule_decks/custom_reader.lvs'] and
            source['geometry_formula']=='A=w*l; P=2*(w+l), per unit; m retained separately','Source-bound physical projection differs.')
    log=text(flow/'lvs/lvs.log')
    if positive:
        require('Final result: Circuits match uniquely.' in log and 'Cell pin lists are equivalent.' in log and 'Property errors' not in log and
                log.count('cap_cmim (2->1)')==2,'Strict LVS or parallel reduction differs.')
        records=data(flow/'lvs/lvs.json')
        require(len(records)==1 and records[0]['name']==['coupon','coupon'] and records[0]['devices']==[[['cap_cmim',1]],[['cap_cmim',1]]] and
                records[0]['nets']==[2,2] and records[0]['badnets']==[] and records[0]['badelements']==[] and records[0]['pins']==[['C1','C2'],['C1','C2']],
                'Comparison summary differs.')
    elif mode in ('m1','m3'):
        value='4.9e-11' if mode=='m1' else '1.47e-10'
        require('Property errors were found.' in log and value in log and '9.8e-11' in log and 'area circuit1:' in log,'Multiplicity area mismatch differs.')
    elif mode=='wrong-wire':
        require('Final result: Netlists do not match.' in log and 'NET mismatches:' in log and 'DEVICE mismatches:' in log,
                'Wrong-wire net/device mismatch differs.')
    elif mode=='missing-contact':
        require('Final result: Top level cell failed pin matching.' in log and 'NET mismatches:' in log and 'DEVICE mismatches:' in log,'Missing-contact topology mismatch differs.')
    else:
        require('Property errors were found.' in log and 'parallel/series network does not match' in log and '5.04e-11' in log and '2.84e-05' in log,'Unit geometry mismatch differs.')
    return dict(name=name,raw_units=2,strict_lvs='passed' if positive else 'failed',schematic_sha256=sha(flow/'schematic.spice'),native_sha256=sha(flow/'lvs-extraction/native.cir'))

def source_inventory(required,actual):
    require(required==set(actual),'Source inventory differs.')

def verify_evidence(root):
    root=safe_path(root).resolve();require('tmpuxoell2b' not in root.parts,'Forbidden evidence path.')
    report=data(root/'report.json');require(report['status']=='OBSERVED' and [r['name'] for r in report['cases']]==list(CASES),'Selection differs.')
    contract=ROOT/'docs/qualification/ihp-cmim-enclosures-v1.json'
    require(sha(contract)=='8f82d1ba570a7e831a55e751700b04d9f3e35a0bc007acdf7639c223dfda501b','Enclosure source contract differs.')
    required=set(data(contract)['source_sha256']) | set(SOURCE_HASHES)
    required.update(p.relative_to(ROOT).as_posix() for p in (ROOT/'icstudio').glob('*.py'))
    required.update('scripts/'+n for n in ('qualify_ihp_cmim_enclosures.py','check_ihp_cmim_enclosures.py','qualify_ihp_cmim_reference.py',
                    'qualify_ihp_mim_layout.py','qualify_standard_mos.py','ihp_cmim_boundary_audit.py',
                    'check_ihp_cmim_multiplicity.py','qualify_ihp_cmim_multiplicity.py'))
    source_inventory(required,report['source_files'])
    for path,want in report['source_files'].items():
        part=Path(path);require(not part.is_absolute() and '..' not in part.parts and 'tmpuxoell2b' not in part.parts and '\\' not in path and ':' not in path,'Unsafe source identity.')
        require(sha(ROOT/part)==want,'Source changed: '+path)
    for path,want in SOURCE_HASHES.items():require(report['source_files'].get(path)==want,'Multiplicity source identity differs: '+path)
    for path in ('scripts/check_ihp_cmim_multiplicity.py','scripts/qualify_ihp_cmim_multiplicity.py'):
        require(sha(ROOT/path)==report['source_files'].get(path),'Runner or reader identity differs.')
    return dict(status='PASS_FINITE_MULTIPLICITY_READBACK',cases=[verify_case(root/name,name) for name in CASES],qualified=False,installed_acceptance=False)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args()
    print(json.dumps(verify_evidence(a.output),indent=2))

if __name__=='__main__':main()
