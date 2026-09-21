"""Rebuild the editable GF180 Banba physical implementation and mask export.

Project-specific first layout: real GF180 layers, explicit segmented schematic,
contacted devices and routed terminals. Native checks are not foundry signoff.
The bundled upstream PNP cell is Apache-2.0; see layout/upstream/NOTICE.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.model import clone, load_project, save_project, flatten, validate, erc, file_digest
from icstudio.layout import rect, polygon, shape_from_polygon, kdb, drc
from icstudio.physical import connectivity
from icstudio.interchange import export_layout
from icstudio.physical_cells import assign_port

OUT = ROOT / 'examples/gf180-banba/layout'
SOURCE = ROOT / 'examples/gf180-banba/pass2/banba.icproj'
PNP = OUT / 'upstream/pnp_05p00x05p00.gds'
UPSTREAM = 'aacc04cc30ed119baaa616dff266cca7006dc3d6'
PNP_SHA256 = '59e36ad406b03027054754627051686ea5a605f045d1a8f164e877a4da3008a9'
MASKS = dict(nwell=(21,0), comp=(22,0), poly=(30,0), pplus=(31,0),
             nplus=(32,0), contact=(33,0), m1=(34,0), via1=(35,0),
             m2=(36,0), via2=(38,0), m3=(42,0), via3=(40,0), m4=(46,0),
             sab=(49,0), resistor=(62,0), fusetop=(75,0), res_mk=(110,5),
             cap_mk=(117,5), mim_l_mk=(117,10), lvs_bjt=(118,5), drc_bjt=(127,5))


def stable(name):
    return hashlib.sha256(('banba-layout-v1:' + name).encode()).hexdigest()[:16]


def nm(value):
    from icstudio.model import scalar
    return 5 * round(scalar(value) * 1e9 / 5)


class Builder:
    def __init__(self):
        if file_digest(PNP)!=PNP_SHA256:raise ValueError('Pinned upstream PNP geometry changed.')
        self.p = load_project(SOURCE)
        self.p['name'] = 'GF180MCU Banba bandgap — first routed layout'
        self.p['id'] = stable('project')
        core = next(c for c in self.p['cells'] if c['name'] == 'banba_core')
        self.original = {d['name'].replace('/', '_'):d for d in flatten(self.p, core['id'])}
        self.c = dict(id=stable('physical-cell'), name='banba_layout', ports=['VDD','VSS','VREF'],
                      devices=[], shapes=[], layout_pins=[], layout_ports=[], layout_texts=[],
                      layout_label_mode='explicit', annotations=[])
        self.p['cells'].append(self.c)
        # Existing testbenches now instantiate the explicit physical schematic.
        for c in self.p['cells']:
            for d in c['devices']:
                if d['kind'] == 'X' and d.get('cell') == core['id']:
                    d['cell'] = self.c['id']
        self.count = 0
        self.access = []
        self.groups = []
        self.changes = []
        self.ls = {}
        tech = self.p['pdk']
        for key, pair in MASKS.items():
            name = next((l['name'] for l in tech['layers'] if (l['gds'],l['datatype']) == pair), 'banba_'+key)
            self.ls[key] = name
            if not any(l['name'] == name for l in tech['layers']):
                tech['layers'].append(dict(name=name, gds=pair[0], datatype=pair[1], color='#bd98ef', width=0, space=0))
        # Explicit bounded screening rules. Full GF180 rule decks are separate.
        minima = dict(m1=(230,230),m2=(280,280),m3=(280,280),m4=(440,460),
                      via1=(260,260),via2=(260,260),via3=(260,260),contact=(220,250),
                      poly=(180,240),comp=(220,280),nwell=(860,600))
        for l in tech['layers']:
            key = next((k for k,v in self.ls.items() if v == l['name']), None)
            l['width'],l['space'] = minima.get(key, (0,0))
        colors=dict(comp='#60bb87',poly='#e27773',nwell='#ab884e',m1='#559de9',m2='#c787df',m3='#e8bc55',m4='#69cbd1')
        for k,col in colors.items():
            next(l for l in tech['layers'] if l['name']==self.ls[k])['color']=col
        tech['connectivity'] = dict(conductors=[self.ls[k] for k in ('m1','m2','m3','m4','fusetop')],
            vias=[[self.ls[a],self.ls[v],self.ls[b]] for a,v,b in
                  [('m1','via1','m2'),('m2','via2','m3'),('m3','via3','m4'),('fusetop','via3','m4')]],
            via_blockers=[dict(conductor=self.ls['m3'],cut=self.ls['via3'],mask=self.ls['fusetop'])])
        tech['routing_conductors'] = [self.ls[k] for k in ('m1','m2','m3','m4')]
        tech['banba_physical_stack'] = dict(metals=4,mim_option='B',mim_density_ff_um2=2,
            physical_variant='B',model_bundle='gf180mcuD',
            note='M3/M4 MIM needs the four-metal stack; the bundled D package supplies models, not a complete physical process installation.')
        tech.setdefault('interoperability', {}).setdefault('port_layers', {})
        for k in ('m1','m2','m3','m4'):
            pair=(MASKS[k][0],10)
            label=next((l['name'] for l in tech['layers'] if (l['gds'],l['datatype'])==pair), 'banba_'+k+'_label')
            if not any(l['name']==label for l in tech['layers']):
                tech['layers'].append(dict(name=label,gds=pair[0],datatype=10,color='#eeeeee',width=0,space=0))
            tech['interoperability']['port_layers'][self.ls[k]]=label

    def shape(self, s, owner=''):
        self.count += 1
        s.update(id=stable('shape:'+str(self.count)), device_id=owner)
        self.c['shapes'].append(s)
        return s

    def box(self, key, x, y, w, h, net='', owner=''):
        assert all(v%5 == 0 for v in (x,y,w,h)), (key,x,y,w,h)
        return self.shape(rect(self.ls[key],x,y,w,h,net=net),owner)

    def wire(self, key, pts, net, width=600):
        pts=[list(v) for i,v in enumerate(pts) if i==0 or list(v)!=list(pts[i-1])]
        if len(pts)<2:return
        return self.shape(dict(kind='path',layer=self.ls[key],points=pts,width=width,net=net,generated_route=True))

    def via(self, level, x, y, net, pad=600):
        group=stable('via:'+str(self.count))
        for key,size in ((f'via{level}',260),(f'm{level}',pad),(f'm{level+1}',pad)):
            self.box(key,x-size//2,y-size//2,size,size,net if key[0]=='m' else '')['via_group']=group

    def device(self, source, name=None, **params):
        d=clone(self.original[source]);d['name']=name or source;d['id']=stable('device:'+d['name'])
        d['nets']={k:v.replace('/','_') for k,v in d['nets'].items()}
        d.pop('net_labels',None)
        d.setdefault('model_params',{}).update(params)
        self.c['devices'].append(d)
        return d

    def pin(self,d,pin,key,x,y,access=True):
        self.c['layout_pins'].append(dict(id=stable(d['name']+':'+pin),device_id=d['id'],pin=pin,layer=self.ls[key],point=[x,y]))
        if access:self.access.append((key,x,y,d['nets'][pin]))

    def fanout(self, x,y,target,net):
        """A local M3 jog escapes to a distinct vertical M2 access column."""
        self.via(1,x,y,net)
        self.via(2,x,y,net)
        self.wire('m3',[[x,y],[target,y]],net)
        self.via(2,target,y,net)
        self.access.append(('m2',target,y,net))

    def mos(self,name,x,y):
        d=self.device(name);w,l=nm(d['params']['w']),nm(d['params']['l']);o=d['id']
        assert 500<=w<=24000 and 1000<=l<=8000
        self.box('comp',x-800,y,l+1600,w,owner=o)
        self.box('pplus' if d['kind']=='PMOS' else 'nplus',x-1100,y-300,l+2200,w+600,owner=o)
        self.box('poly',x,y-1100,l,w+1400,owner=o)
        cy=y+5*round(w/10);gx=x+5*round(l/10)
        self.box('comp',x-2850,cy-400,800,800,owner=o)
        self.box('nplus' if d['kind']=='PMOS' else 'pplus',x-3050,cy-600,1200,1200,owner=o)
        if d['kind']=='PMOS':self.box('nwell',x-3550,y-1600,l+5150,w+2700,owner=o)
        for pin,px,py in [('s',x-500,cy),('d',x+l+500,cy),('g',gx,y-800),('b',x-2450,cy)]:
            self.box('contact',px-110,py-110,220,220,owner=o)
            self.box('m1',px-200,py-200,400,400,d['nets'][pin],o)
            # Contacted source/drain straps distribute current across width.
            if pin in ('s','d'):
                self.box('m1',px-200,y,400,w,d['nets'][pin],o)
                for yy in range(y+250,y+w-249,500):
                    if abs(yy-py)>=470:self.box('contact',px-110,yy-110,220,220,owner=o)
            self.pin(d,pin,'m1',px,py)
        self.groups.append(dict(name=name,kind='MOS',box_nm=[x-3550,y-1600,x+l+1600,y+w+1100]))

    def resistor_bank(self,name,x,y):
        src=self.original[name];length=nm(src['model_params']['l']);w=nm(src['model_params']['w'])
        n=max(1,math.ceil(length/100000));unit=length//n
        assert unit*n==length and unit%5==0
        ds=[]
        for i in range(n):
            d=self.device(name, name if n==1 else f'{name}_{i+1:02}',l=f'{unit/1000:g}u')
            a=src['nets']['p'].replace('/','_') if i==0 else f'{name}_series_{i}'
            b=src['nets']['m'].replace('/','_') if i==n-1 else f'{name}_series_{i+1}'
            d['nets'].update(p=a,m=b)
            yy=y+i*4000;o=d['id']
            self.box('poly',x-640,yy,unit+1280,w,owner=o)
            self.box('res_mk',x,yy,unit,w,owner=o)
            self.box('resistor',x-1040,yy-400,unit+2080,w+800,owner=o)
            self.box('sab',x-100,yy-280,unit+200,w+560,owner=o)
            for xx in (x-820,x+unit):self.box('pplus',xx,yy-180,820,w+360,owner=o)
            self.box('comp',x-2850,yy,700,w,owner=o)
            self.box('pplus',x-3050,yy-200,1100,w+400,owner=o)
            cy=yy+w//2
            # Alternating pin orientation forms a contacted series snake.
            terminals=[('p' if i%2==0 else 'm',x-460),('m' if i%2==0 else 'p',x+unit+460),('b',x-2500)]
            for pin,px in terminals:
                self.box('contact',px-110,cy-110,220,220,owner=o)
                self.box('m1',px-200,cy-200,400,400,d['nets'][pin],o)
                self.pin(d,pin,'m1',px,cy,False)
            ds.append(d)
            if i:
                px=x+unit+460 if (i-1)%2==0 else x-460
                self.wire('m1',[[px,cy-4000],[px,cy]],a)
        self.wire('m1',[[x-2500,y+w//2],[x-2500,y+(n-1)*4000+w//2]],'VSS')
        self.access.extend([('m1',x-2500,y+w//2,'VSS'),('m1',x-460,y+w//2,ds[0]['nets']['p'])])
        lastx=x+unit+460 if (n-1)%2==0 else x-460
        lasty=y+(n-1)*4000+w//2
        if n%2==0:self.fanout(lastx,lasty,x-5000,ds[-1]['nets']['m'])
        else:self.access.append(('m1',lastx,lasty,ds[-1]['nets']['m']))
        self.groups.append(dict(name=name,kind='resistor bank',box_nm=[x-6000,y-1000,x+unit+1500,y+n*4000],units=n))
        if n>1:self.changes.append(dict(device=name,change='series resistor sections',count=n,unit_length_um=unit/1000,total_length_um=length/1000))

    def resistor_column(self,name,desired):
        """Keep compact rows while reserving distinct M2 terminal columns."""
        src=self.original[name];length=nm(src['model_params']['l'])
        n=max(1,math.ceil(length/100000));unit=length//n
        for delta in [0]+[sign*i*1000 for i in range(1,41) for sign in (1,-1)]:
            x=desired+delta
            if x<4000:continue
            pts=[(x-2500,'VSS'),(x-460,src['nets']['p'].replace('/','_')),
                 (x-5000 if n%2==0 else x+unit+460,src['nets']['m'].replace('/','_'))]
            if all(abs(a-b)>=900 or a==b and net==other for a,net in pts
                   for key,b,_,other in self.access if key!='m4'):
                return x
        raise ValueError('No isolated M2 access columns for '+name)

    def pnp_array(self,x,y):
        db=kdb();ly=db.Layout();ly.read(str(PNP));top=ly.top_cell()
        self.pnp_centers={'Q1':[],'Q2':[]}
        for row in range(3):
            for col in range(3):
                original='Q1' if (row,col)==(1,1) else 'Q2'
                d=self.device(original,original if original=='Q1' else f'Q2_{len(self.pnp_centers["Q2"])+1}',m='1')
                dx,dy=x+col*16000,y+row*16000
                self.pnp_centers[original].append([dx+4200,dy+4200])
                for idx in ly.layer_indexes():
                    info=ly.get_info(idx)
                    if info.datatype==10:continue
                    key=next(k for k,pair in MASKS.items() if pair==(info.layer,info.datatype))
                    for poly in db.Region(top.begin_shapes_rec(idx)).merged().each():
                        self.shape(shape_from_polygon(poly.transformed(db.Trans(dx,dy)),self.ls[key]),d['id'])
                for pin,px,py in [('c',420,420),('b',1150,1150),('e',4200,4200)]:
                    self.pin(d,pin,'m1',dx+px,dy+py,False)
                    if pin=='e':self.fanout(dx+px,dy+py,dx+6000+row*2000,d['nets'][pin])
                    else:self.via(1,dx+px,dy+py,d['nets'][pin],pad=400)
                # Base and collector both return to VSS. Share one access
                # column without expanding the narrow upstream M1 rings.
                self.wire('m2',[[dx+420,dy+420],[dx+420,dy+1150],[dx+1150,dy+1150]],'VSS')
                self.access.append(('m2',dx+420,dy+420,'VSS'))
        self.groups.append(dict(name='Q1 : Q2 = 1 : 8',kind='PNP common centroid',box_nm=[x,y,x+40400,y+40400]))
        self.changes.append(dict(device='Q2',change='eight explicit parallel 5 × 5 µm PNPs',count=8))

    def mim(self,name,x,y,rows,cols):
        src=self.original[name];w=5*round(nm(src['model_params']['w'])/cols/5);h=5*round(nm(src['model_params']['l'])/rows/5)
        assert w*h<=10000*1e6 and min(w,h)>=5000
        for row in range(rows):
            for col in range(cols):
                d=self.device(name,name if rows*cols==1 else f'{name}_{row+1}_{col+1}',w=f'{w/1000:g}u',l=f'{h/1000:g}u')
                xx=x+col*(w+12000);yy=y+row*(h+12000);a,b=d['nets']['g'],d['nets']['b'];o=d['id']
                self.box('m3',xx-600,yy-600,w+1200,h+1200,b,o)
                self.box('fusetop',xx,yy,w,h,a,o)
                self.box('m4',xx,yy,w,h,a,o)
                self.box('cap_mk',xx-600,yy-600,w+1200,h+1200,owner=o)
                self.box('mim_l_mk',xx,yy,w,100,owner=o)
                # Distributed 4 x 4 top contacts; MIM dielectric blocks M3.
                for ix in range(4):
                    for iy in range(4):
                        vx=xx+1000+5*round(ix*(w-2000)/15);vy=yy+1000+5*round(iy*(h-2000)/15)
                        self.box('via3',vx-130,vy-130,260,260,owner=o)
                # Bottom is reached only from above, outside FuseTop (MIMTM.10).
                bx=xx-2500;by=yy+2000
                self.box('m3',bx-600,by-600,3100,1200,b,o)
                self.via(3,bx,by,b,pad=1200)
                self.pin(d,'b','m4',bx,by)
                self.pin(d,'g','m4',xx+5*round(w/10),yy+5*round(h/10))
        self.groups.append(dict(name=name,kind='MIM array',box_nm=[x-4000,y-1000,x+cols*(w+12000)-11000,y+rows*(h+12000)-11000],units=rows*cols))
        self.changes.append(dict(device=name,change='parallel MIM tiles on 5 nm grid',count=rows*cols,
            tile_um=[w/1000,h/1000],plate_area_um2=rows*cols*w*h/1e6))

    def guard(self):
        x,y,w,h,t=-7000,-5000,315000,55000,1000
        for key,extra in [('comp',0),('pplus',200),('m1',0)]:
            for a,b,c,d in [(x-extra,y-extra,w+2*extra,t+2*extra),(x-extra,y+h-t-extra,w+2*extra,t+2*extra),
                            (x-extra,y+t, t+2*extra,h-2*t),(x+w-t-extra,y+t,t+2*extra,h-2*t)]:
                self.box(key,a,b,c,d,'VSS' if key=='m1' else '')
        for xx in range(x+500,x+w-499,2000):
            for yy in (y+500,y+h-500):self.box('contact',xx-110,yy-110,220,220)
        for yy in range(y+2500,y+h-2499,2000):
            for xx in (x+500,x+w-500):self.box('contact',xx-110,yy-110,220,220)
        self.access.append(('m1',x+500,y+500,'VSS'))

    def route(self):
        nets=sorted({v[3] for v in self.access})
        tracks={n:-12000-4000*i for i,n in enumerate(nets)}
        xs={n:[] for n in nets}
        for key,x,y,net in self.access:
            if key=='m1':self.via(1,x,y,net)
            level=4 if key=='m4' else 2
            self.wire('m'+str(level),[[x,y],[x,tracks[net]]],net,600)
            self.via(3 if level==4 else 2,x,tracks[net],net)
            xs[net].append(x)
        for net,y in tracks.items():
            width=1600 if net in ('VDD','VSS') else 800
            self.wire('m3',[[-16000,y],[max(xs[net])+2000,y]],net,width)
            if net in self.c['ports']:assign_port(self.p,self.c['id'],net,self.ls['m3'],[-16000,y])
        self.tracks=tracks

    def build(self):
        order=['MP1','MP2','MP3','XAMP_MPA','XAMP_MPB','XAMP_MNA','XAMP_MNB',
               'XAMP_MPBIAS','XAMP_MPTAIL','XAMP_MPLOAD','XAMP_MNOUT','XSTART_MSENSE','XSTART_MNSENSE','XSTART_MNKICK']
        for i,name in enumerate(order):self.mos(name,i*18000,0)
        self.pnp_array(255000,0)
        for name,x,y in [('RCA',6000,70000),('RCB',6000,76000),('RPTAT',24000,90000),
                         ('ROUT',60000,90000),('XAMP_RBIAS',6000,110000),
                         ('XSTART_RDET',130000,70000),('XSTART_RPULL',130000,150000)]:
            self.resistor_bank(name,self.resistor_column(name,x),y)
        self.mim('COUT',330000,0,5,5)
        self.mim('XSTART_CTRACK',0,280000,2,2)
        self.mim('XAMP_CMILLER',245000,280000,1,1)
        self.guard();self.route()
        from icstudio.analog_constraints import footprint
        self.c['analog_constraints']=[]
        byname={d['name']:d['id'] for d in self.c['devices']}
        for name,members in [('Core mirrors',['MP1','MP2','MP3']),('Input pair',['XAMP_MPA','XAMP_MPB']),
                             ('Active load',['XAMP_MNA','XAMP_MNB']),('CTAT resistors',['RCA','RCB'])]:
            ids=[byname[n] for n in members]
            self.c['analog_constraints'].append(dict(id=stable(name),name=name,kind='matching',members=ids))
            if name in ('Input pair','Active load'):
                axis=sum(footprint(self.p,self.c['id'],did)[2][0] for did in ids)/2
                self.c['analog_constraints'].append(dict(id=stable(name+'-axis'),name=name+' axis',kind='symmetry',members=ids,axis='x',coordinate=axis))
        a=[byname['Q1']];b=[byname['Q2_'+str(i)] for i in range(1,9)]
        self.c['analog_constraints'].append(dict(id=stable('PNP-centroid'),name='1:8 PNP centroid',kind='common_centroid',members=a+b,groups=[a,b]))
        # Physical implementation schematic uses explicit, editable pin labels.
        for i,d in enumerate(self.c['devices']):
            d.update(x=180+(i%8)*360,y=160+(i//8)*330,net_labels=clone(d['nets']))
        self.c.update(wires=[],labels=[],junctions=[])
        self.c['annotations']=[dict(id=stable('note'),x=50,y=-60,text='PHYSICAL IMPLEMENTATION · explicit resistor sections, MIM tiles and PNP units\nOriginal second-pass hierarchy remains in this project. Native terminal checks are not foundry LVS.')]
        self.c['banba_layout']=dict(version=1,source_sha256=file_digest(SOURCE),upstream=UPSTREAM,
            changes=self.changes,groups=self.groups,bus_tracks_nm=self.tracks,pnp_centers_nm=self.pnp_centers,
            qualification='First routed layout. Native terminal connectivity and bounded width/space/grid screening; no foundry DRC/LVS or parasitic extraction.')
        self.p['design_notes']=dict(stage='First routed Banba layout',physical_cell=self.c['id'],
            limitations='No foundry DRC/LVS, density/antenna signoff, mismatch or extracted parasitic qualification. Sparse bus routing prioritizes inspectability over area.')
        validate(self.p)
        return self.p


def verify(p):
    c=next(c for c in p['cells'] if c['name']=='banba_layout')
    result=connectivity(p,c['id']);geometry=drc(p,c['id']);electrical=erc(p)
    from icstudio.analog_constraints import findings
    matching=findings(p,c['id'])
    db=kdb();bounds=db.Box()
    for s in c['shapes']:bounds+=polygon(s).bbox()
    centers=c['banba_layout']['pnp_centers_nm']
    centroids={k:[sum(v[i] for v in values)/len(values) for i in (0,1)] for k,values in centers.items()}
    report=dict(schema=1,source_sha256=file_digest(SOURCE),physical_cell=c['id'],devices=len(c['devices']),
        shapes=len(c['shapes']),terminals=len(c['layout_pins']),nets=len(result['net_regions']),
        bbox_um=[bounds.left/1000,bounds.bottom/1000,bounds.right/1000,bounds.top/1000],
        area_mm2=bounds.area()/1e12,erc=electrical,connectivity=result['issues'],geometry=geometry,matching=matching,
        pnp_centroids_nm=centroids,changes=c['banba_layout']['changes'],
        qualification=result['qualification'],foundry_drc='not run',foundry_lvs='not run',pex='not run')
    assert centroids['Q1']==centroids['Q2']
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=OUT)
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    b=Builder();p=b.build();report=verify(p)
    # Relocatable relative to the saved project, resolved by the native loader.
    import os
    p['pdk']['package_root']=os.path.relpath(ROOT/'icstudio/assets/pdks/gf180mcuD',args.out)
    save_project(p,args.out/'banba-layout.icproj')
    report['project_sha256']=file_digest(args.out/'banba-layout.icproj')
    (args.out/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('devices','shapes','terminals','area_mm2','pnp_centroids_nm')},indent=2))
    print('Findings:',{k:len(report[k]) for k in ('erc','connectivity','geometry','matching')})
    if any(report[k] for k in ('erc','connectivity','geometry','matching')):
        raise SystemExit('Resolve the saved validation findings before exporting.')
    # Export only the actual physical cell; retain the full project separately.
    physical=clone(p);physical['cells']=[clone(b.c)];physical['top']=b.c['id'];physical['simulation_setups']=[];physical['test_plans']=[];physical['testbenches']=[]
    export_layout(physical,args.out/'banba-layout.gds')
    print('Created',args.out/'banba-layout.icproj')


if __name__=='__main__':main()
