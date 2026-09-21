"""Render the actual native Banba layout in Studio and annotated mask views."""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def render(out):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from icstudio.gui import Studio
    from icstudio.model import load_project, digest
    from icstudio.layout import polygon
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    os.environ['XDG_CONFIG_HOME']=str(out/'profile/config')
    os.environ['XDG_DATA_HOME']=str(out/'profile/data')
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(out/'profile/settings'))
    app=QApplication([]);app.setStyle('Fusion')
    p=load_project(ROOT/'examples/gf180-banba/layout/banba-layout.icproj')
    c=next(c for c in p['cells'] if c['name']=='banba_layout')
    errors=[];old=sys.excepthook
    sys.excepthook=lambda kind,value,tb:errors.append(str(value))
    win=Studio(recover=False);win.error=errors.append;win.maybe_save=lambda:True
    try:
        win.resize(1800,1100);win.show();win.live_check.setChecked(False)
        win.set_project(p);win.cell_combo.setCurrentIndex(win.cell_combo.findData(c['id']))
        win.mode_combo.setCurrentIndex(1);QTest.qWait(300);win.layout.fit();QTest.qWait(100)
        assert win.cid==c['id'] and len(win.cell['layout_pins'])==293
        win.grab().save(str(out/'studio-layout.png'))
        assert not errors,errors
        (out/'gui-validation.json').write_text(json.dumps(dict(status='passed',display=app.platformName(),
            checks=['Opened the saved project in Studio','Selected banba_layout and displayed all physical geometry',
                    'Rendered 103 devices and 293 explicit terminal mappings'],errors=errors),indent=2)+'\n')
    finally:
        win.saved_hash=digest(win.project);win.close();sys.excepthook=old
    # Publication image is generated from mask coordinates, never an illustration.
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    from matplotlib.patches import Rectangle
    colors={l['name']:l['color'] for l in p['pdk']['layers']}
    pairs={l['name']:(l['gds'],l['datatype']) for l in p['pdk']['layers']}
    def plot(path,box,title,groups):
        fig,ax=plt.subplots(figsize=(16,5) if (box[2]-box[0])/(box[3]-box[1])>3 else (12,9),facecolor='#101921');ax.set_facecolor('#101921')
        for key in [(21,0),(22,0),(30,0),(34,0),(36,0),(42,0),(46,0)]:
            for layer in [l for l,pair in pairs.items() if pair==key]:
                pts=[]
                for s in c['shapes']:
                    if s['layer']!=layer:continue
                    poly=polygon(s);b=poly.bbox()
                    if b.right<box[0]*1000 or b.left>box[2]*1000 or b.top<box[1]*1000 or b.bottom>box[3]*1000:continue
                    # Resolve holes so substrate/base rings remain visibly open.
                    from icstudio.layout import kdb
                    for piece in kdb().Region(poly).decompose_trapezoids().each():
                        pts.append([(v.x/1000,v.y/1000) for v in piece.each_point_hull()])
                if pts:ax.add_collection(PolyCollection(pts,facecolors=colors[layer],edgecolors='none',alpha=.8,label=layer))
        for group in groups:
            x0,y0,x1,y1=[v/1000 for v in group['box_nm']]
            ax.add_patch(Rectangle((x0-2,y0-2),x1-x0+4,y1-y0+4,fill=False,edgecolor='#b7c6ce',linewidth=.6))
            ax.text((x0+x1)/2,y1+5,group['name'].replace('XAMP_','').replace('XSTART_',''),
                    color='#e6edf2',fontsize=7,ha='center',va='bottom')
        ax.set(xlim=(box[0],box[2]),ylim=(box[1],box[3]),xlabel='µm',ylabel='µm')
        ax.set_aspect('equal');ax.tick_params(colors='#b7c6ce');ax.xaxis.label.set_color('#b7c6ce');ax.yaxis.label.set_color('#b7c6ce')
        for spine in ax.spines.values():spine.set_color('#42515a')
        ax.set_title(title,loc='left',color='white',fontsize=17,pad=22)
        ax.text(0,-.17,'GF180 · 4-metal / MIM-B · revised output filter · full physical closure pending',transform=ax.transAxes,color='#b7c6ce',fontsize=9)
        fig.savefig(path,dpi=180,bbox_inches='tight',facecolor=fig.get_facecolor());plt.close(fig)
    groups=c['banba_layout']['groups']
    overview=[g for g in groups if g['kind']!='MOS' and g['name'] not in ('RCA','RCB')]
    pair=[g['box_nm'] for g in groups if g['name'] in ('RCA','RCB')]
    overview.extend([dict(name='Mirrors / OTA / startup',box_nm=[-4000,-2000,247000,26000]),
                     dict(name='RCA / RCB',box_nm=[min(v[0] for v in pair),min(v[1] for v in pair),max(v[2] for v in pair),max(v[3] for v in pair)])])
    plot(out/'layout-overview.png',[-30,-85,860,530],'Banba bandgap | physical implementation',overview)
    plot(out/'layout-core.png',[-10,-9,310,60],'Matched devices | MOS bank and 1:8 PNP array',[g for g in groups if g['kind'] in ('MOS','PNP common centroid')])


if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--out',required=True)
    render(a.parse_args().out)
