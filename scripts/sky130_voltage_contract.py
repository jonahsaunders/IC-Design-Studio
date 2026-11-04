"""Check declared nominal voltage intent against exact HD reference evidence.

This is a single-domain design contract, not an analog voltage simulation or an
electrical-reliability qualification. An unspecified or unsupported range fails.
"""
from collections import Counter
from decimal import Decimal, InvalidOperation
import hashlib
import re

from scripts.ihp_lvs_reference import logical_lines
from scripts.sky130_lvs_reference import MASTERS_SHA256

PG = {'VGND': ('VSS','0'), 'VNB': ('VSS','0'), 'VPB': ('VDD','1.8'), 'VPWR': ('VDD','1.8')}
PHYSICAL = {'sky130_fd_sc_hd__'+name for name in ('fill_1','fill_2','fill_4','fill_8','tapvpwrvgnd_1')}
NFET='sky130_fd_pr__nfet_01v8'
PFET='sky130_fd_pr__pfet_01v8_hvt'


def require(value,message):
    if not value:raise ValueError(message)


def decimal(value):
    require(isinstance(value,str),'Voltage values must be explicit decimal strings.')
    try:result=Decimal(value)
    except InvalidOperation as exc:raise ValueError('Invalid voltage.') from exc
    require(result.is_finite(),'Non-finite voltage.')
    return result


def attribute(body,name):
    values=re.findall(r'^\s+'+re.escape(name)+r'\s*:\s*("[^"\n]*"|[^;\n]+);',body,re.M)
    require(len(values)==1,'Missing or duplicate Liberty attribute: '+name)
    return values[0].strip().strip('"')


def liberty(text):
    """Read the captured library's explicit formatting; reject unknown structure.

    Cell/pin endings have distinct indentation in this pinned source. This is
    not a general Liberty parser and must not accept another format by guessing.
    """
    require(attribute(text[:text.index('    cell (')],'nom_voltage')=='1.8000000000',
            'Expected the captured nominal 1.8 V library.')
    require(attribute(text[:text.index('    cell (')],'voltage_unit')=='1V','Unsupported voltage units.')
    maps=re.findall(r'^    voltage_map\("([^"]+)", ([0-9.]+)\);$',text,re.M)
    require(len(maps)==len(dict(maps)) and maps,'Duplicate/missing voltage maps.')
    maps={name:decimal(value) for name,value in maps}
    cells={}
    blocks=list(re.finditer(r'^    cell \("([A-Za-z0-9_]+)"\) \{\n(.*?)^    \}',text,re.M|re.S))
    require(len(blocks)==len(re.findall(r'^\s*cell\s*\(',text,re.M)),'Unsupported cell formatting.')
    for match in blocks:
        name,body=match.groups();require(name not in cells,'Repeated Liberty cell.')
        power={};pins={}
        pgs=list(re.finditer(r'^        pg_pin \("([A-Za-z0-9_]+)"\) \{\n(.*?)^        \}',body,re.M|re.S))
        require(len(pgs)==len(re.findall(r'^\s*pg_pin\s*\(',body,re.M)),'Unsupported power-pin formatting.')
        for pg in pgs:
            pin,content=pg.groups();require(pin not in power,'Repeated power pin.')
            voltage=attribute(content,'voltage_name');require(voltage in maps,'Missing power voltage map.')
            power[pin]=dict(voltage=str(maps[voltage]),kind=attribute(content,'pg_type'))
        signals=list(re.finditer(r'^        pin \("([A-Za-z0-9_]+)"\) \{\n(.*?)^        \}',body,re.M|re.S))
        # Nested test_cell pin groups describe scan/test behavior, not another
        # physical terminal list. Read only direct children of this cell.
        require(len(signals)==len(re.findall(r'^ {8}pin\s*\(',body,re.M)),'Unsupported signal-pin formatting: '+name)
        for signal in signals:
            pin,content=signal.groups();require(pin not in pins,'Repeated signal pin.')
            pins[pin]=dict(direction=attribute(content,'direction').upper(),
                power=attribute(content,'related_power_pin'),ground=attribute(content,'related_ground_pin'))
        cells[name]=dict(power=power,pins=pins)
    require(cells,'Empty library.')
    return cells


def empty_physical_cells(cdl):
    normalized=cdl.replace('\r\n','\n')
    require(hashlib.sha256(normalized.encode()).hexdigest()==MASTERS_SHA256,'Changed HD CDL source.')
    selected={};current=None;ports=[];body=[]
    for line in logical_lines(normalized):
        words=line.split();keyword=words[0].lower()
        if keyword=='.subckt':
            require(current is None,'Nested CDL subcircuit.')
            current=words[1];ports=words[2:];body=[]
        elif keyword=='.ends':
            require(current is not None,'Unexpected CDL end.')
            if current in PHYSICAL:
                required={'VGND','VPWR'} if current=='sky130_fd_sc_hd__tapvpwrvgnd_1' else set(PG)
                require(not body and len(ports)==len(required) and set(ports)==required,
                        'Physical-only cell contains electrical elements or unexpected ports.')
                selected[current]=dict(power={p:dict(voltage=PG[p][1],kind='physical_supply') for p in ports},pins={})
            current=None
        elif current is not None:body.append(line)
    require(current is None and set(selected)==PHYSICAL,'Incomplete physical-only master inventory.')
    return selected


def top_ports(inventory):
    ports={};nets={}
    require(inventory.get('schema')==1 and inventory['nets'],'Unsupported checkpoint inventory.')
    for net in inventory['nets']:
        require(net['net'] not in nets and net['sig_type'] in ('POWER','GROUND','SIGNAL','CLOCK'),'Duplicate or unsupported checkpoint net.')
        nets[net['net']]=net
        for pin in net['pins']:
            if '/' in pin['terminal']:continue
            entry=dict(net=net['net'],direction=pin['direction'],sig_type=net['sig_type'])
            require(pin['terminal'] not in ports or ports[pin['terminal']]==entry,'Conflicting top-port mapping.')
            ports[pin['terminal']]=entry
    require(ports and len({n['alias'] for n in nets.values()})==len(nets),'Missing ports or duplicate native aliases.')
    return ports,nets


def validate(contract,inventory,database,cells,native):
    ports,nets=top_ports(inventory)
    require(contract.get('schema')==1 and contract.get('mode')=='nominal-single-domain-hd'
            and contract.get('power_net_hv')==[],'Explicit supported voltage mode and HV-net declaration are required.')
    require(contract['top']==inventory['top'] and contract['checkpoint_sha256']==inventory['checkpoint_sha256'],
            'Voltage contract belongs to a different checkpoint.')
    require(contract['supplies']=={'VDD':'1.8','VSS':'0'},'Unsupported reference supply contract.')
    require(set(contract['ports'])==set(ports),'Every physical top port needs an explicit voltage range.')
    for name,actual in ports.items():
        defined=contract['ports'][name]
        require({k:defined[k] for k in actual}==actual,'Port identity/direction differs from voltage contract.')
        bounds=defined['range_v'];require(isinstance(bounds,list) and len(bounds)==2,'Missing port voltage limits.')
        low,high=map(decimal,bounds)
        require(Decimal(0)<=low<=high<=Decimal('1.8'),'Port voltage lies outside the supported nominal domain.')
        if actual['sig_type'] in ('POWER','GROUND'):
            required=Decimal('1.8') if actual['sig_type']=='POWER' else Decimal(0)
            require(low==high==required,'Incorrect physical supply voltage.')
    power={n['net'] for n in nets.values() if n['sig_type']=='POWER'}
    ground={n['net'] for n in nets.values() if n['sig_type']=='GROUND'}
    require(power=={'VDD'} and ground=={'VSS'},'Additional or renamed voltage domain requires review.')
    require(database.get('version')==1 and database.get('dbu_per_micron')==1000,'Unsupported database snapshot.')
    instances=database['instances'];expected={i['name']:i['master'] for i in inventory['instances']}
    require(len(expected)==len(inventory['instances']) and len(instances)==len(expected)
            and {i['name']:i['master'] for i in instances}==expected,'Instance inventory differs from extraction checkpoint.')
    signal_pins=power_pins=unconnected_outputs=0
    for inst in instances:
        require(inst['master'] in cells,'Unknown or uncharacterized master: '+inst['master'])
        master=cells[inst['master']];pins={p['name']:p for p in inst['pins']}
        require(len(pins)==len(inst['pins']) and set(pins)==set(master['power'])|set(master['pins']),
                'Missing, extra or duplicate master terminal: '+inst['name'])
        required_pg={'VGND','VPWR'} if inst['master']=='sky130_fd_sc_hd__tapvpwrvgnd_1' else set(PG)
        require(set(master['power'])==required_pg,'Unsupported cell supply/bias pins.')
        for name in sorted(required_pg):
            rail,voltage=PG[name]
            require(decimal(master['power'][name]['voltage'])==Decimal(voltage)
                    and pins[name]['net']==rail and pins[name]['direction']=='INOUT',
                    'Cell supply/bias pin has an incompatible voltage or connection: '+inst['name']+'/'+name)
            power_pins+=1
        for name,definition in master['pins'].items():
            actual=pins[name]
            require(definition['direction'] in ('INPUT','OUTPUT') and actual['direction']==definition['direction']
                    and definition['power']=='VPWR' and definition['ground']=='VGND','Unsupported signal voltage domain.')
            if actual['net'] is None or actual['net']=='':
                require(actual['direction']=='OUTPUT','Unconnected input has unspecified voltage intent.')
                unconnected_outputs+=1
            else:require(actual['net'] in nets,'Signal terminal references an unaccounted net.')
            signal_pins+=1
    vdd=nets['VDD']['alias'];vss=nets['VSS']['alias']
    require(native['ground']==vss,'Extracted substrate differs from declared ground.')
    require({n['alias'] for n in nets.values()}<=native['nodes'].keys(),'A declared checkpoint net is absent from native extraction.')
    devices=Counter();bodies=Counter();terminals=set()
    formats={NFET:(19,(9,10,13,16)),PFET:(19,(9,10,13,16)),
        'sky130_fd_pr__diode_pw2nd_05v5':(16,(9,10,13)),
        'sky130_fd_pr__res_generic_po':(18,(9,12,15))}
    for element in native['devices']:
        model=element[2];require(model in formats and len(element)==formats[model][0],'Unsupported extracted device.')
        kind='msubckt' if model in (NFET,PFET) else 'ndiode' if model.endswith('diode_pw2nd_05v5') else 'devres'
        require(element[0]=='device' and element[1]==kind,'Unsupported native element kind.')
        for position in formats[model][1]:
            require(element[position] in native['nodes'],'Extracted device has an unknown terminal.')
            terminals.add(element[position])
        if model in (NFET,PFET):
            require(element[9]==(vss if model==NFET else vdd),'Extracted MOS body is not tied to its declared rail.')
            bodies[element[9]]+=1
        devices[model]+=1
    require(devices[NFET]>0 and devices[PFET]>0,'Empty MOS circuit cannot establish a reference voltage contract.')
    return dict(status='nominal-voltage-contract-consistent',qualified=False,
        ports=len(ports),checkpoint_nets=len(nets),instances=len(instances),signal_pins=signal_pins,
        supply_and_bias_pins=power_pins,unconnected_outputs=unconnected_outputs,
        native_models=dict(sorted(devices.items())),mos_bodies=dict(sorted(bodies.items())),
        native_device_terminal_nodes=len(terminals),power_net_hv=[],
        scope='Explicit 0–1.8 V reference port contract, authenticated HD library domains, complete cell power/bias wiring and native MOS body checks. This does not calculate transient voltages, prove rail integrity, classify arbitrary circuits or establish foundry ERC/latch-up acceptance.')
