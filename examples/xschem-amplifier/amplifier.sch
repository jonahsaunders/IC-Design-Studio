v {xschem version=3.4.4 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
C {devices/voltage.sym} 100 100 0 0 {name=VDD value=1.8}
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
