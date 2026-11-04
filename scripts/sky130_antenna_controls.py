"""Independent rectangular area/perimeter oracle for staged antenna arithmetic.

These isolate antenna calculations; they are not geometry-legal test chips.
Existing exact-cut via3/via4 controls separately exercise physical cut arrays.
"""
import argparse, hashlib, json
from fractions import Fraction as F
from pathlib import Path
import klayout.db as db

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,required=True)
OUT=parser.parse_args().output; OUT.mkdir(parents=True,exist_ok=False)
names=['poly','licon','li','mcon','met1','via','met2','via2','met3','via3','met4','via4','met5']
gds=[(66,20),(66,44),(67,20),(67,44),(68,20),(68,44),(69,20),(69,44),(70,20),(70,44),(71,20),(71,44),(72,20)]
limits=[50,3,75,3,400,6,400,6,400,6,400,6,400]
thickness=list(map(F,['.180','0','.100','0','.350','0','.350','0','.800','0','.800','0','1.200']))
factors=[0,0,450,18,400,36,400,36,400,36,400,36,400]
bonuses=[0,0,0,0,2200,0,2200,0,2200,0,2200,0,2200]
gate=F('0.252'); diode_area=F('.25')
ly=db.Layout(); ly.dbu=.001; top=ly.create_cell('CONTROLS'); rows=[]

def coupon(i, delta, protection='none', variant='ordinary'):
    idx=len(rows); xoff=idx*100000
    shape_boxes={}
    def rect(layer, coords):
        coords=tuple(int(v) for v in coords)
        shape_boxes.setdefault(str(layer),[]).append(coords)
        top.shapes(ly.layer(*layer)).insert(db.Box(coords[0]+xoff,coords[1],coords[2]+xoff,coords[3]))
    rect((65,20),(0,0,1500,1680))
    rect((93,44),(-130,-130,1630,1810))
    credit=(factors[i]*diode_area+bonuses[i]) if protection in ('diode','nwell-tap','two-diodes') and variant=='ordinary' else 0
    ratio=F(limits[i])+credit
    if i==0:
        length=(ratio*gate/thickness[i]/2-F('.15'))*1000
        assert length.denominator==1
        rect(gds[0],(650,-500,800,-500+length+delta*5))
        etched=(2*(F('.15')+(length+delta*5)/1000))*thickness[i]
    else:
        rect(gds[0],(650,-500,800,3000))
        for j in range(1,i+1):
            if j==i:
                if thickness[i]:
                    width=F(3); height=ratio*gate/thickness[i]/2-width
                    height_nm=height*1000
                    assert height_nm.denominator==1
                    rect(gds[j],(0,2000,3000,2000+height_nm+delta*5))
                    etched=2*(width+(height_nm+delta*5)/1000)*thickness[i]
                else:
                    height_nm=ratio*gate/F('.6')*1000
                    assert height_nm.denominator==1
                    rect(gds[j],(600,2100,1200,2100+height_nm+delta*5))
                    etched=F('.6')*(height_nm+delta*5)/1000
            elif thickness[j]:
                rect(gds[j],(0,2000,3000,6000))
            else:
                rect(gds[j],(650,2100,820,2270))
    if variant in ('future','disconnected'):
        assert i<12
        next_metal=next(j for j in (2,4,6,8,10,12) if j>i)
        px=10000
        rect((65,20) if protection=='diode' else (65,44),(px,2300,px+500,2800))
        for j in range(1,next_metal):
            if thickness[j]:rect(gds[j],(px,2000,px+2000,6000))
            else:rect(gds[j],(px+100,2450,px+270,2620))
        if variant=='future':
            if i==0 or thickness[i]:rect(gds[next_metal-1],(650,2100,820,2270))
            rect(gds[next_metal],(0,2100,px+2000,3000))
    elif protection!='none':
        # Separate diode/tap. For licon the target contact reaches it directly;
        # other checks connect it through local interconnect.
        px=900 if i==1 else 2000
        if protection=='two-diodes':
            rect((65,20),(2000,2300,2250,2800))
            rect((65,20),(2500,2300,2750,2800))
            rect((66,44),(2040,2450,2210,2620))
            rect((66,44),(2540,2450,2710,2620))
        else:
            rect((65,20) if protection=='diode' else (65,44),(px,2300,px+500,2800))
            offset=100 if i==1 else 150
            rect((66,44),(px+offset,2450,px+offset+170,2620))
            if protection=='nwell-tap':rect((64,20),(px-500,1800,px+1000,3300))
    actual_gate=gate
    if variant=='two-gates':
        actual_gate=2*gate
        if i==0:rect((65,20),(0,4000,1500,5680))
        else:
            rect((65,20),(0,-3000,1500,-1320))
            rect((66,20),(650,-3500,800,-500))
    if variant=='unconnected-metal':rect(gds[i],(10000,2000,11000,1002000))
    value=etched/actual_gate-credit
    # Poly cannot connect a diffusion region or substrate tap without contacts.
    exempt=protection=='short' and i>0 and variant=='ordinary'
    rows.append(dict(id=idx,stage=names[i],delta_grid_steps=delta,protection=protection,variant=variant,
                     gate_area_um2=str(actual_gate),etched_area_um2=str(etched),diode_credit=str(credit),
                     expected_egar=str(value),limit=limits[i],expected_violation=not exempt and value>limits[i],
                     gate_bbox_nm=[xoff+650,0,xoff+800,1680],shapes=shape_boxes))

for i in range(13):
    for delta in (-1,0,1): coupon(i,delta)
    if i>0:
        for delta in (-1,0,1): coupon(i,delta,'diode')
        coupon(i,1,'short')
        coupon(i,1,'nwell-tap')
    coupon(i,1,variant='two-gates')
    coupon(i,-1,variant='unconnected-metal')
    if i<12:
        for protection in ('diode','short'):
            coupon(i,1,protection,'future')
            coupon(i,1,protection,'disconnected')
    if bonuses[i]:coupon(i,1,'two-diodes')
options=db.SaveLayoutOptions();options.gds2_write_timestamps=False
ly.write(str(OUT/'input.gds'),options)
record=dict(schema=1,qualified=False,scope=__doc__,rows=rows,
            driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            gds_sha256=hashlib.sha256((OUT/'input.gds').read_bytes()).hexdigest())
(OUT/'expectations.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(dict(coupons=len(rows),expected_target_faults=sum(r['expected_violation'] for r in rows))))
