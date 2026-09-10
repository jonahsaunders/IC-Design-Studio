"""Independent text-format fixtures, not output of Studio's exporter."""
from pathlib import Path

HEADER='v {xschem version=3.4.4 file_version=1.2}\nG {}\nK {}\nV {}\nS {}\nE {}\n'


def amplifier(root):
    root=Path(root);(root/'devices').mkdir(parents=True,exist_ok=True);(root/'blocks').mkdir(exist_ok=True);(root/'models').mkdir(exist_ok=True)
    def sym(name,kind,fmt,template,pins):
        text=HEADER.replace('K {}','K {type='+kind+' format="'+fmt+'" template="'+template+'" custom_note="preserve this attribute"}')
        text+='B 4 -20 -20 20 20 {}\nT {@name} 25 -15 0 0 0.2 0.2 {}\n'
        if kind in ('resistor','capacitor','vsource'):text+='T {@value} 25 5 0 0 0.2 0.2 {}\n'
        for i,(pin,x,y) in enumerate(pins):
            direction=('out' if pin=='out' else 'in') if kind=='subcircuit' else 'inout'
            text+=f'B 5 {x-2} {y-2} {x+2} {y+2} {{name={pin} dir={direction} sim_pinnumber={i+1}}}\n'
        if kind=='subcircuit':
            text=text.replace('B 4 -20 -20 20 20 {}','B 4 -40 -40 40 40 {}').replace('T {@name} 25 -15','T {@name} -25 5')
            for pin,x,y in pins:text+=f'L 4 {x} {y} {max(-40,min(40,x))} {max(-40,min(40,y))} {{}}\n'
        elif kind in ('resistor','capacitor','vsource'):
            text=text.replace('B 4 -20 -20 20 20 {}','L 4 0 -30 0 -20 {}\nL 4 0 20 0 30 {}')
            if kind=='resistor':
                points=[(0,-20),(6,-15),(-6,-10),(6,-5),(-6,0),(6,5),(-6,10),(6,15),(0,20)]
                text+=''.join(f'L 4 {x} {y} {xx} {yy} {{}}\n' for (x,y),(xx,yy) in zip(points,points[1:]))
            elif kind=='capacitor':text+='L 4 0 -20 0 -4 {}\nL 4 0 4 0 20 {}\nL 4 -12 -4 12 -4 {}\nL 4 -12 4 12 4 {}\n'
            else:text+='A 4 0 0 20 0 360 {}\nL 4 -5 -8 5 -8 {}\nL 4 0 -13 0 -3 {}\nL 4 -5 8 5 8 {}\n'
        (root/name).write_text(text)
    sym('devices/res.sym','resistor','@name @pinlist @value m=@m','name=R1 value=1k m=1',[('P',0,-30),('M',0,30)])
    sym('devices/cap.sym','capacitor','@name @pinlist @value','name=C1 value=1p',[('P',0,-30),('M',0,30)])
    sym('devices/voltage.sym','vsource','@name @pinlist @value','name=V1 value=0',[('P',0,-30),('M',0,30)])
    sym('devices/nmos.sym','nmos','@name @pinlist @model w=@w l=@l','name=M1 model=nch w=10u l=1u',[('D',20,-50),('G',-50,0),('S',20,50),('B',50,0)])
    for name,kind in [('label','label'),('ipin','ipin'),('opin','opin')]:sym('devices/'+name+'.sym',kind,'*.'+kind+' @lab','name=p lab=net',[('p',0,0)])
    sym('devices/code.sym','netlist_commands','@value','name=code value=none',[])
    sym('blocks/gain.sym','subcircuit','@name @pinlist @symname resistance=@resistance width=@width','name=X1 resistance=10k width=10u',[('in',-60,-20),('out',60,-20),('vdd',0,-60),('vss',0,60)])
    top=HEADER+'''C {devices/voltage.sym} 100 100 0 0 {name=VDD value=1.8}
C {devices/voltage.sym} 100 240 0 0 {name=VIN value="0.8 AC 1"}
C {blocks/gain.sym} 360 180 0 0 {name=XAMP resistance=8k width=12u designer_note="keep me"}
C {devices/cap.sym} 500 210 0 0 {name=CL value=1p}
C {devices/label.sym} 100 70 0 0 {name=l1 lab=vdd}
C {devices/label.sym} 100 130 0 0 {name=l2 lab=0}
C {devices/label.sym} 100 210 0 0 {name=l3 lab=vin}
C {devices/label.sym} 100 270 0 0 {name=l4 lab=0}
C {devices/label.sym} 300 160 0 0 {name=l5 lab=vin}
C {devices/label.sym} 360 120 0 0 {name=l6 lab=vdd}
C {devices/label.sym} 360 240 0 0 {name=l7 lab=0}
C {devices/label.sym} 420 160 0 0 {name=l8 lab=vout}
C {devices/label.sym} 500 240 0 0 {name=l9 lab=0}
N 420 160 500 160 {}
N 500 160 500 180 {}
C {devices/code.sym} 100 380 0 0 {name=setup value=".include models/nmos.spice
.ac dec 20 10 10meg"}
T {Common-source amplifier with hierarchical parameter overrides} 100 20 0 0 0.2 0.2 {}
L 4 90 35 600 35 {dash=3}
'''
    child=HEADER+'''C {devices/res.sym} 240 100 0 0 {name=RD value=resistance}
C {devices/nmos.sym} 220 220 0 0 {name=M1 model=nch w=width l=1u}
C {devices/ipin.sym} 240 70 0 0 {name=p1 lab=vdd sim_pinnumber=3}
C {devices/ipin.sym} 170 220 0 0 {name=p2 lab=in sim_pinnumber=1}
C {devices/opin.sym} 240 170 0 0 {name=p3 lab=out sim_pinnumber=2}
C {devices/ipin.sym} 240 270 0 0 {name=p4 lab=vss sim_pinnumber=4}
C {devices/label.sym} 270 220 0 0 {name=l1 lab=vss}
N 240 130 240 170 {}
T {Editable gain stage} 80 30 0 0 0.2 0.2 {}
'''
    (root/'amplifier.sch').write_text(top);(root/'blocks/gain.sch').write_text(child);(root/'models/nmos.spice').write_text('* Level-1 reference model, illustrative only\n.model nch nmos (level=1 vto=0.45 kp=100u lambda=0.02)\n')
    return root/'amplifier.sch'
