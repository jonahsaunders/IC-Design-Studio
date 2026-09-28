"""Execute real SKY130 width/spacing boundaries with the full Magic deck."""
import argparse
from pathlib import Path
import shutil
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.qualification_evidence import Report, magic_verify
from icstudio.model import file_digest


def qualify(args):
    import klayout.db as db
    report=Report(args.out,'sky130-drc-boundaries')
    state={}
    def preflight():
        state['magic']=report.tool('magic',args.magic,['--version'])
        # Explicit rule numbers and 5 nm steps around the pinned 140 nm rules.
        text=args.technology.read_text()
        for line in ('width *m1,rm1 140', 'spacing allm1,m1fill allm1,*obsm1,m1fill 140'):
            if line not in text:raise ValueError('The declared SKY130 rule boundary changed.')
        return dict(technology_sha256=file_digest(args.technology),width_nm=140,spacing_nm=140)
    report.case('prerequisites',preflight)
    for kind,rule in [('width','met1.1'),('spacing','met1.2')]:
        for value in (135,140,145):
            name=f'{kind}-{value}nm'
            def action(kind=kind,rule=rule,value=value,name=name):
                from scripts.qualification_evidence import Blocked
                if 'magic' not in state:raise Blocked('Magic is unavailable.')
                ly=db.Layout();ly.dbu=.001;top=ly.create_cell('BOUNDARY');idx=ly.layer(68,20)
                if kind=='width':top.shapes(idx).insert(db.Box(0,0,value,2000))
                else:
                    top.shapes(idx).insert(db.Box(0,0,500,2000))
                    top.shapes(idx).insert(db.Box(500+value,0,1000+value,2000))
                source=report.output/(name+'.gds');ly.write(str(source))
                result=magic_verify(source,'BOUNDARY',args.technology,report.output/name,state['magic'],extract=False)
                rules=result['drc']['rules']
                if value<140:
                    if not any(rule in r for r in rules):raise ValueError('Expected boundary rule was not reported.')
                    # Magic boxes can sit one internal grid step beyond the
                    # violating edge. Require coordinates within that tolerance.
                    scale=result['drc']['coordinate_unit_um']*1000
                    bounds=top.bbox()
                    nearby=[row for row in result['drc']['findings'] if rule in row['rule']
                            and row['box'][0]*scale <= bounds.right+scale
                            and row['box'][2]*scale >= bounds.left-scale
                            and row['box'][1]*scale <= bounds.top+scale
                            and row['box'][3]*scale >= bounds.bottom-scale]
                    if not nearby:raise ValueError('Missing defect coordinates near the submitted geometry.')
                elif result['drc']['count']:raise ValueError('Legal boundary rejected: '+repr(rules))
                return dict(expected_design_drc='failed' if value<140 else 'passed',**result)
            report.case(name,action)
    return report.finish()


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--technology',type=lambda p:Path(p).resolve(),required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--magic',default=shutil.which('magic'))
    raise SystemExit(qualify(ap.parse_args()))
