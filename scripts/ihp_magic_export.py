"""Export the bounded IHP electrical view in its actual native layout grid.

Reading a saved .ext in a fresh default-grid Magic process can change junction
areas and perimeters. The hierarchical exporter can also move MOS gate C.
Import, extract and export flat in one process; audit the complete C graph.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


def tcl_word(value):
    value=str(value).replace('\\','/')
    if any(c in value for c in '{}\r\n\x00'):
        raise ValueError('Unsupported native path or identifier.')
    return '{'+value+'}'


def export_script(top):
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',top):
        raise ValueError('Use a simple captured top-cell identifier.')
    return '''if {[catch {
gds read input.gds
load '''+tcl_word(top)+'''
select top cell
extract all
feedback save extraction.feedback
ext2spice lvs
ext2spice hierarchy off
ext2spice cthresh 0
ext2spice -o extracted.spice '''+tcl_word(top)+'''
puts IHP_LAYOUT_GRID_EXPORT_COMPLETE
} err]} {puts "IHP_LAYOUT_GRID_EXPORT_ERROR $err"}
quit -noprompt
'''


def export(gds, top, technology, executable, output):
    gds,technology,executable,output=[Path(p).resolve() for p in (gds,technology,executable,output)]
    if output.exists():raise ValueError('Use a new native export directory.')
    script=export_script(top)
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    lock=Path(__file__).resolve().parents[1]/'examples/ihp-active-fill-source-lock.json'
    sources=json.loads(lock.read_text())['sources']['magic']['files']
    tech_files={Path(row['path']).name:row['sha256'] for row in sources if row['path'].endswith('.tech')}
    if technology.name!='ihp-sg13g2.tech' or not tech_files:
        raise ValueError('The pinned IHP technology entry point is required.')
    for name,digest in tech_files.items():
        if sha(technology.parent/name)!=digest:raise ValueError('Pinned native technology changed: '+name)
    gds_digest=sha(gds);engine_digest=sha(executable)
    output.mkdir(parents=True,exist_ok=False)
    shutil.copyfile(gds,output/'input.gds')
    for name in tech_files:shutil.copyfile(technology.parent/name,output/name)
    (output/'startup.tcl').write_text('drc off\ntech load ihp-sg13g2.tech\n',encoding='ascii',newline='\n')
    (output/'export.tcl').write_text(script,encoding='ascii',newline='\n')
    with (output/'engine.log').open('w',encoding='utf-8') as log:
        result=subprocess.run([str(executable),'-dnull','-noconsole','-rcfile',str(output/'startup.tcl'),
                               str(output/'export.tcl')],cwd=output,stdout=log,stderr=subprocess.STDOUT,timeout=1800)
    log=(output/'engine.log').read_text()
    if (result.returncode or 'IHP_LAYOUT_GRID_EXPORT_COMPLETE' not in log or
            'IHP_LAYOUT_GRID_EXPORT_ERROR' in log or not (output/'extracted.spice').is_file()):
        raise ValueError('Native layout-grid export failed; retain its diagnostic log.')
    if sha(gds)!=gds_digest or sha(executable)!=engine_digest:
        raise ValueError('A native export input changed during execution.')
    try:
        from .check_ihp_flat_capacitance import audit,raw_capacitors,write_full_precision
    except ImportError:
        from check_ihp_flat_capacitance import audit,raw_capacitors,write_full_precision
    capacitance=audit(output/(top+'.ext'),output/'extracted.spice')
    precise=write_full_precision(raw_capacitors(output/(top+'.ext')),output/'capacitance-full-precision.spice')
    record=dict(schema=1,status='captured',qualified=False,top=top,source_gds_sha256=gds_digest,
                engine_sha256=engine_digest,technology_sha256=tech_files,script_sha256=sha(__file__),
                source_lock_sha256=sha(lock),grid_policy='Import GDS, extract and export in the same native process.',
                capacitance_audit=capacitance,
                full_precision_capacitance_sha256=precise,
                files={p.name:sha(p) for p in output.iterdir() if p.is_file()},
                scope='Native model capture only; warning, connectivity, capacitance and performance audits are required.')
    (output/'record.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8',newline='\n')
    return record


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('gds','technology','executable','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--top',required=True)
    a=p.parse_args();r=export(a.gds,a.top,a.technology,a.executable,a.output)
    print(json.dumps({k:r[k] for k in ('status','qualified','source_gds_sha256','grid_policy')}))


if __name__=='__main__':main()
