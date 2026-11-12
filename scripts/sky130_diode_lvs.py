"""Add the HD antenna diode omitted from the supplied transistor-only CDL.

The independent maintained library supplies its terminals and dimensions. Its
layout must match the installed cell on every polygon layer. This adapter is
specific to diode_2 and does not qualify other diode families or simulation.
"""
from decimal import Decimal
import hashlib
from pathlib import Path
import re
import klayout.db as k
from scripts.ihp_lvs_reference import require, logical_lines
from scripts.sky130_lvs_reference import strict_deck as transistor_deck


CELL='sky130_fd_sc_hd__diode_2'
MODEL='sky130_fd_pr__diode_pw2nd_05v5'
SPICE_SHA256='67b980af74314791f0ea796118c740730958e5cb7083d58acab20c17781bee45'
GDS_SHA256='7198f35a0a4bde6ba7155242c567b21644b04696c39734b604490c09e6709c90'


def reference_dimensions(source):
    require(hashlib.sha256(source).hexdigest()==SPICE_SHA256,'Unreviewed diode model source.')
    lines=logical_lines(source.decode('ascii'))
    require(len(lines)==3 and lines[0]=='.subckt '+CELL+' DIODE VGND VNB VPB VPWR'
            and lines[2]=='.ends','Unexpected diode reference interface.')
    m=re.fullmatch(r'XD0 VNB DIODE '+MODEL+r' perim=([\d.e+]+) area=([\d.e+]+)',lines[1])
    require(m is not None,'Unexpected diode topology or parameters.')
    # This library view uses area/perimeter factors referenced to 1e12/1e6.
    # Require agreement with the independently supplied source GDS below;
    # never infer these reference dimensions from a design being tested.
    return Decimal(m[2])/Decimal('1e12'),Decimal(m[1])/Decimal('1e6')


def verify_library(source_spice,source_gds,installed_gds):
    source_gds,installed_gds=Path(source_gds),Path(installed_gds)
    require(hashlib.sha256(source_gds.read_bytes()).hexdigest()==GDS_SHA256,'Unreviewed diode source layout.')
    area,perimeter=reference_dimensions(source_spice)
    source=k.Layout();source.read(str(source_gds));installed=k.Layout();installed.read(str(installed_gds))
    require(len(source.top_cells())==1 and source.top_cell().name==CELL and installed.cell(CELL) is not None,
            'Missing diode source or installed cell.')
    require(abs(source.dbu-.001)<1e-12 and abs(installed.dbu-.001)<1e-12,'Unexpected diode layout units.')
    def masks(layout,cell):
        result={}
        for index in layout.layer_indexes():
            info=layout.get_info(index);r=k.Region(cell.begin_shapes_rec(index)).merged()
            if not r.is_empty():result[(info.layer,info.datatype)]=r
        return result
    left=masks(source,source.top_cell());right=masks(installed,installed.cell(CELL))
    require(all((left.get(pair,k.Region())^right.get(pair,k.Region())).is_empty() for pair in left.keys()|right.keys()),
            'Installed diode masks differ from the independent reference.')
    diode=(left[(65,20)]&left[(93,44)]-left[(64,20)])&left[(81,23)]
    require(diode.count()==1 and Decimal(diode.area())/1000000==area and Decimal(diode.perimeter())/1000==perimeter,
            'Independent diode SPICE and source GDS dimensions disagree.')
    return dict(cell=CELL,model=MODEL,area_um2=str(area),perimeter_um=str(perimeter),
                source_spice_sha256=SPICE_SHA256,source_gds_sha256=GDS_SHA256,
                installed_gds_sha256=hashlib.sha256(installed_gds.read_bytes()).hexdigest(),
                polygon_layers_equal=True,reference_units_checked_against_source_layout=True)


def enrich_reference(reference,source_spice):
    area,perimeter=reference_dimensions(source_spice)
    empty='.SUBCKT '+CELL+' DIODE VGND VNB VPB VPWR\n.ENDS '+CELL
    require(reference.count(empty)==1,'Expected exactly one empty diode master in the pinned CDL.')
    return reference.replace(empty,empty.split('\n')[0]+f'\nD0 VNB DIODE {MODEL} A={area} P={perimeter}\n.ENDS '+CELL)


def strict_deck(upstream,top):
    code=transistor_deck(upstream,top)
    marker='# Define connectivity for netlist extraction'
    require(code.count(marker)==1,'Changed native connectivity section.')
    extra='''# Independently referenced low-voltage antenna diode; both dimensions compare.
NDIODE = (DIFF & NSDM - NWELL) & DIODE
diode_class = extract_devices(diode("'''+MODEL+'''"), { "P" => SUB, "N" => NDIODE, "tA" => SUB, "tC" => NSD })
diode_class.enable_parameter("P", true)
diode_class.enable_parameter("A", true)
'''
    code=code.replace(marker,extra+'\n'+marker)
    # Both diode properties are secondary in the native comparer unless
    # explicitly selected. Native area/perimeter fault controls enforce this.
    # These tolerances absorb floating arithmetic only, far below a DBU step.
    require(code.count('if ! compare')==1,'Changed native comparison section.')
    code=code.replace('if ! compare',f'tolerance("{MODEL}", "A", :absolute => 1e-12)\n'
                      f'tolerance("{MODEL}", "P", :absolute => 1e-12)\nif ! compare')
    return code
