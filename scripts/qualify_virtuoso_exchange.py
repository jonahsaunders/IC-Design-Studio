"""Prepare a portable handoff, or check a real site-configured Virtuoso round trip.

The site supplies installed-version-specific argv, its actual layer map, PDK
identity and Netgen setup. No OpenAccess or licensed-tool result is fabricated.
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import atomic_write,file_digest
from icstudio.stream_contract import compare
from icstudio.engines import execute,netgen_lvs,require_lvs_match


def prepare(gds,cdl,top,output):
    import klayout.db as db
    root=Path(output).resolve()
    if root.exists() and any(root.iterdir()):raise ValueError('Use a new handoff directory.')
    gds,cdl=Path(gds).resolve(),Path(cdl).resolve()
    layout=db.Layout();layout.read(str(gds))
    if layout.cell(top) is None:raise ValueError('The layout has no requested top cell.')
    matches=re.findall(r'(?im)^\.subckt\s+'+re.escape(top)+r'\s+([^\r\n]+)',cdl.read_text())
    if len(matches)!=1:raise ValueError('The reference needs one explicit top-cell interface.')
    ports=matches[0].split()
    if len(ports)!=len(set(ports)) or any('=' in p for p in ports):raise ValueError('Use a resolved reference interface.')
    root.mkdir(parents=True,exist_ok=True)
    shutil.copy2(gds,root/'source.gds');shutil.copy2(cdl,root/'reference.cdl')
    contract={'schema':1,'top':top,'ports':ports,'dbu_um':layout.dbu,
              'cells':sorted(c.name for c in layout.each_cell()),
              'layers':sorted([[layout.get_info(i).layer,layout.get_info(i).datatype] for i in layout.layer_indexes()]),
              'files':{n:file_digest(root/n) for n in ('source.gds','reference.cdl')},
              'status':'prepared-unverified',
              'required':['Matching licensed Virtuoso/PDK installation','Actual drawing, pin and label layer/purpose map',
                          'Import and export through the native database','Independent CDL export and strict LVS',
                          'Exact geometry, text presentation, hierarchy, arrays and database units']}
    atomic_write(root/'handoff.json',json.dumps(contract,indent=2))
    return contract


def checked_bundle(root):
    root=Path(root).resolve();data=json.loads((root/'handoff.json').read_text())
    if data.get('schema')!=1 or set(data.get('files',{}))!={'source.gds','reference.cdl'}:
        raise ValueError('Unsupported handoff contract.')
    for name,sha in data['files'].items():
        if file_digest(root/name)!=sha:raise ValueError('Handoff input changed: '+name)
    return data


def check_return(bundle,gds,cdl,netgen,setup,output):
    data=checked_bundle(bundle);root=Path(output).resolve();root.mkdir(parents=True,exist_ok=True)
    result={'status':'failed','scope':'Returned stream/CDL content checks; caller must separately establish tool provenance.'}
    try:
        result['layout']=compare(Path(bundle)/'source.gds',gds)
        log=netgen_lvs(netgen,Path(bundle)/'reference.cdl',data['top'],cdl,data['top'],setup,root/'lvs')
        require_lvs_match(log)
        checked_bundle(bundle)
        result.update(status='passed',lvs='unique match, equivalent connected pins, no property errors',
                      returned_gds_sha256=file_digest(gds),returned_cdl_sha256=file_digest(cdl),
                      setup_sha256=file_digest(setup))
        return result
    except Exception as exc:
        result['error']=str(exc);raise
    finally:atomic_write(root/'content-check.json',json.dumps(result,indent=2))


def run(bundle,adapter,output):
    bundle=Path(bundle).resolve();contract=checked_bundle(bundle)
    config=json.loads(Path(adapter).read_text());root=Path(output).resolve()
    if root.exists() and any(root.iterdir()):raise ValueError('Use a new licensed-run directory.')
    if config.get('schema')!=1 or not config.get('pdk_id') or not config.get('pdk_revision'):
        raise ValueError('The site adapter must identify the installed matching PDK.')
    for key in ('layer_map','lvs_setup'):
        if not Path(config.get(key,'')).is_file():raise ValueError('Missing actual site '+key)
    root.mkdir(parents=True)
    values={'bundle':str(bundle),'work':str(root),'top':contract['top'],
            'returned_gds':str(root/'returned.gds'),'returned_cdl':str(root/'returned.cdl'),
            'layer_map':str(Path(config['layer_map']).resolve())}
    report={'status':'failed','pdk_id':config['pdk_id'],'pdk_revision':config['pdk_revision'],
            'adapter_sha256':file_digest(adapter),'layer_map_sha256':file_digest(config['layer_map']),
            'lvs_setup_sha256':file_digest(config['lvs_setup']),
            'steps':[], 'scope':'One site/PDK/version and this exact reference. No foundry signoff or general OpenAccess compatibility claim.'}
    try:
        for phase in ('version','import','export_layout','export_netlist'):
            argv=config.get('commands',{}).get(phase)
            if not isinstance(argv,list) or not argv or not all(isinstance(v,str) for v in argv):
                raise ValueError('Provide explicit argv for site phase '+phase)
            args=[v.format_map(values) for v in argv]
            binary=Path(args[0])
            if not binary.is_absolute() or not binary.is_file():raise ValueError('Use an existing absolute executable path for '+phase)
            step={'phase':phase,'argv':args,'executable_sha256':file_digest(binary)};report['steps'].append(step)
            log=execute(args,root,timeout=900);atomic_write(root/(phase+'.log'),log)
            step['log_sha256']=file_digest(root/(phase+'.log'))
        report['content']=check_return(bundle,root/'returned.gds',root/'returned.cdl',config['netgen'],config['lvs_setup'],root/'comparison')
        if file_digest(config['layer_map'])!=report['layer_map_sha256']:raise ValueError('Layer map changed during exchange.')
        if file_digest(config['lvs_setup'])!=report['lvs_setup_sha256']:raise ValueError('LVS setup changed during exchange.')
        report['status']='passed'
        return report
    except Exception as exc:
        report['error']=str(exc);raise
    finally:atomic_write(root/'qualification.json',json.dumps(report,indent=2))


def main():
    ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='mode',required=True)
    p=sub.add_parser('prepare')
    for key in ('gds','cdl','top','out'):p.add_argument('--'+key,required=True)
    p=sub.add_parser('run')
    for key in ('bundle','adapter','out'):p.add_argument('--'+key,required=True)
    a=ap.parse_args()
    result=prepare(a.gds,a.cdl,a.top,a.out) if a.mode=='prepare' else run(a.bundle,a.adapter,a.out)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
