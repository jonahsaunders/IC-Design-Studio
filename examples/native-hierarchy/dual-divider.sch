v {xschem version=3.4.4 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
C {vsource.sym} 0 0 0 0 {name=V1 value="DC 1 AC 1"}
C {lab_wire.sym} 0 -30 0 0 {name=p1 lab=supply}
C {gnd.sym} 0 30 0 0 {name=g1 lab=GND}
C {stage.sym} 240 0 0 0 {name=X0 rtop=1k rbottom=1k cload=10n}
C {stage.sym} 240 240 0 0 {name=X1 rtop=3k rbottom=1k cload=10n}
C {lab_wire.sym} 180 0 0 0 {name=p2 lab=supply}
C {lab_wire.sym} 300 0 0 0 {name=p3 lab=data[0]}
C {gnd.sym} 240 60 0 0 {name=g2 lab=GND}
C {lab_wire.sym} 180 240 0 0 {name=p4 lab=supply}
C {lab_wire.sym} 300 240 0 0 {name=p5 lab=data[1]}
C {gnd.sym} 240 300 0 0 {name=g3 lab=GND}
C {code_shown.sym} 480 0 0 0 {name="sim" only_toplevel="true" value=".control
set filetype=ascii
save all
op
write hierarchy-op.raw v(\"data[0]\") v(\"data[1]\")
tran 1u 100u
write hierarchy-tran.raw v(\"data[0]\") v(\"data[1]\")
ac dec 8 10 100k
write hierarchy-ac.raw v(\"data[0]\") v(\"data[1]\")
.endc"}
