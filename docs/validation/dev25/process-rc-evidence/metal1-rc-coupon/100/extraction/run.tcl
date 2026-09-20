if {[catch {
gds read "/workspace/scratch/f4bfc77609d9/IC-Design-Studio/build/analog-rc-qualified/metal1-rc-coupon/100/coupon.gds"
load "rc_coupon"
select top cell
box values 0 0 0 0
if {![port "IN" exists]} {error "Missing layout port IN"}
port "IN" index 1
if {![port "DRAIN" exists]} {error "Missing layout port DRAIN"}
port "DRAIN" index 2
if {![port "VSS" exists]} {error "Missing layout port VSS"}
port "VSS" index 3
extract all
ext2spice lvs
ext2spice subcircuit top on
ext2spice renumber off
ext2spice global off
ext2spice hierarchy on
ext2spice blackbox off
ext2spice scale off
ext2spice merge none
ext2spice cthresh 0.0
ext2spice rthresh 0
ext2sim labels on
ext2sim
extresist all
ext2spice extresist on
ext2spice -o extracted.spice
puts STUDIO_MAGIC_COMPLETE
} err]} {puts stderr "STUDIO_MAGIC_ERROR $err"}
quit -noprompt
