if {[catch {
gds read "/var/tmp/icstudio-physical/54ba0fec4f7047329c9bc43c502f4822/output/physical-flow/layout.gds"
load "parallel_coupon"
select top cell
box values 0 0 0 0
if {![port "D" exists]} {error "Missing layout port D"}
port "D" index 1
if {![port "G" exists]} {error "Missing layout port G"}
port "G" index 2
if {![port "S" exists]} {error "Missing layout port S"}
port "S" index 3
if {![port "B" exists]} {error "Missing layout port B"}
port "B" index 4
extract all
ext2spice lvs
ext2spice subcircuit top on
ext2spice renumber off
ext2spice global off
ext2spice hierarchy on
ext2spice blackbox off
ext2spice scale off
ext2spice merge none
ext2spice cthresh infinite
ext2spice rthresh infinite
ext2spice extresist off
ext2spice -o extracted.spice
puts "STUDIO_MOS_CIF_SCALE [cif scale out]"

puts STUDIO_MAGIC_COMPLETE
} err]} {puts stderr "STUDIO_MAGIC_ERROR $err"}
quit -noprompt
