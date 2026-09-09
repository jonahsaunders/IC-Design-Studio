v {xschem version=3.4.4 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
C {vsource.sym} 0 0 0 0 {name="V1" value="DC 1 AC 1"}
C {res.sym} 100 -30 1 0 {name="R1" value="1k" m="1"}
C {capa.sym} 160 0 0 0 {name="C1" value="1u" m="1"}
C {gnd.sym} 0 30 0 0 {name="g1" lab="GND"}
C {lab_wire.sym} 160 -30 0 0 {name="p1" lab="out"}
C {code_shown.sym} 300 50 0 0 {name="sim" value=".control
foreach T 1 2
reset
alter v1 dc=$T
save all
op
tran 10u 1m
ac dec 5 10 10k
echo level $T
destroy all
end
.endc"}
N 0 -30 70 -30 {}
N 130 -30 160 -30 {}
N 0 30 160 30 {}
