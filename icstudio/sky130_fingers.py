"""Shared-diffusion SKY130 fingers, using total W and W/nf per channel."""
from .model import uid
from .layout import rect


def generate(tech,d,x,y,spec):
    from .sky130_layout import layers
    ls=layers(tech);nf=int(spec['values'].get('nf',1));w=spec['dimensions_nm']['w']//nf;l=spec['dimensions_nm']['l'];pitch=l+1000;last=(nf-1)*pitch;cy=5*round(w/10);shapes=[];pins=[]
    def box(key,a,b,c,e,net=''):
        s=rect(ls[key],x+a,y+b,c-a,e-b,d['id'],net);s['generated_device']=d['id'];shapes.append(s)
    def wire(key,points,net):
        shapes.append({'id':uid(),'kind':'path','layer':ls[key],'points':[[x+a,y+b] for a,b in points],'width':340,'net':net,'device_id':d['id'],'generated_device':d['id']})
    def contact(px,py,net):
        for key,half in [('licon',85),('li',170),('mcon',85),('m1',170)]:box(key,px-half,py-half,px+half,py+half,net if key in ('li','m1') else '')
    box('diff',-800,0,last+l+800,w);implant='psdm' if d['kind']=='PMOS' else 'nsdm';box(implant,-930,-130,last+l+930,w+130)
    box('tap',-2450,cy-250,-1950,cy+250);box('nsdm' if d['kind']=='PMOS' else 'psdm',-2580,cy-380,-1820,cy+380);contact(-2200,cy,d['nets']['b'])
    if d['kind']=='PMOS':box('nwell',-2820,-1200,last+l+1180,max(w+400,cy+620))
    gates=[]
    for i in range(nf):
        at=i*pitch;gate=at+5*round(l/10);gates.append([gate,-600]);box('poly',at,-800,at+l,w+300);box('poly',gate-220,-820,gate+220,-380);box('npc',gate-320,-920,gate+320,-280);contact(gate,-600,d['nets']['g'])
        box('via',gate-75,-675,gate+75,-525);box('m2',gate-170,-770,gate+170,-430,d['nets']['g'])
    wire('m2',[gates[0],gates[-1]],d['nets']['g'])
    columns=[-500]+[i*pitch+l+500 for i in range(nf)];source_y=w+700;drain_y=-1800;drain_x=last+l+2200
    sources=[];drains=[]
    for i,px in enumerate(columns):
        pin='s' if i%2==0 else 'd';net=d['nets'][pin];contact(px,cy,net);yy=source_y if pin=='s' else drain_y;wire('m1',[[px,cy],[px,yy]],net);(sources if pin=='s' else drains).append(px)
    if len(sources)>1:wire('m1',[[sources[0],source_y],[sources[-1],source_y]],d['nets']['s'])
    wire('m1',[[drains[0],drain_y],[drain_x,drain_y],[drain_x,cy]],d['nets']['d'])
    for pin,pt in [('s',[columns[0],cy]),('d',[drain_x,cy]),('g',gates[0]),('b',[-2200,cy])]:pins.append({'id':uid(),'device_id':d['id'],'pin':pin,'layer':ls['m1'],'point':[x+pt[0],y+pt[1]]})
    from .layout_eco import roles
    return roles({'shapes':shapes,'pins':pins,'record':{'device_id':d['id'],'spec':spec,'origin':[x,y]}})
