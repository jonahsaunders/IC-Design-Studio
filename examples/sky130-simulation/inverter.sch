v {xschem version=3.4.4 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
C {vsource.sym} 0 0 0 0 {name="VDD" value="1.8" savecurrent="false"}
C {vsource.sym} 120 0 0 0 {name="VIN" value="PULSE(0 1.8 1n 50p 50p 4n 8n)" savecurrent="false"}
C {sky130_fd_pr/pfet_01v8.sym} 300 -90 0 0 {name="MP" W="2" L="0.15"}
C {sky130_fd_pr/nfet_01v8.sym} 300 90 0 0 {name="MN" W="1" L="0.15"}
C {capa.sym} 450 30 0 0 {name="CL" value="20f" m="1"}
C {lab_wire.sym} 0 -30 0 0 {name="p0" lab="vdd"}
C {lab_wire.sym} 0 30 0 0 {name="p1" lab="0"}
C {lab_wire.sym} 120 -30 0 0 {name="p2" lab="in"}
C {lab_wire.sym} 120 30 0 0 {name="p3" lab="0"}
C {lab_wire.sym} 280 -90 0 0 {name="p4" lab="in"}
C {lab_wire.sym} 280 90 0 0 {name="p5" lab="in"}
C {lab_wire.sym} 320 -120 0 0 {name="p6" lab="vdd"}
C {lab_wire.sym} 380 -90 0 0 {name="p7" lab="vdd"}
C {lab_wire.sym} 320 120 0 0 {name="p8" lab="0"}
C {lab_wire.sym} 380 90 0 0 {name="p9" lab="0"}
C {lab_wire.sym} 450 60 0 0 {name="p10" lab="0"}
C {lab_wire.sym} 400 0 0 0 {name="p11" lab="out"}
N 320 -60 320 60 {lab=out}
N 320 0 450 0 {lab=out}
N 320 -90 380 -90 {lab=vdd}
N 320 90 380 90 {lab=0}
C {code_shown.sym} 550 -120 0 0 {name="SIM" value=".lib /foss/pdks/sky130A/libs.tech/ngspice/sky130.lib.spice tt
.control
save all
tran 10p 12n
.endc"}
