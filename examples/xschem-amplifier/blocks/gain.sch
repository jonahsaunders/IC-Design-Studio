v {xschem version=3.4.4 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
C {devices/res.sym} 240 100 0 0 {name=RD value=resistance}
C {devices/nmos.sym} 220 220 0 0 {name=M1 model=nch w=width l=1u}
C {devices/ipin.sym} 240 70 0 0 {name=p1 lab=vdd sim_pinnumber=3}
C {devices/ipin.sym} 170 220 0 0 {name=p2 lab=in sim_pinnumber=1}
C {devices/opin.sym} 240 170 0 0 {name=p3 lab=out sim_pinnumber=2}
C {devices/ipin.sym} 240 270 0 0 {name=p4 lab=vss sim_pinnumber=4}
C {devices/label.sym} 270 220 0 0 {name=l1 lab=vss}
N 240 130 240 170 {}
T {Editable gain stage} 80 30 0 0 0.2 0.2 {}
