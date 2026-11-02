"""Independent, finite written-netlist checks for the cap_cmim boundary probe."""
from decimal import Decimal, InvalidOperation
import re


def scalar(value):
    match=re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)([up]?)',value,re.I)
    if not match:raise ValueError('Unexpected physical capacitor number.')
    try:return Decimal(match[1])*{'':Decimal(1),'u':Decimal('1e-6'),'p':Decimal('1e-12')}[match[2].lower()]
    except InvalidOperation as exc:raise ValueError('Invalid physical capacitor number.') from exc


def circuit(text,length_um,width_um=75,terminals=('C1','C2')):
    """Require one physical C, C1 top then C2 bottom, exact area/perimeter."""
    lines=[line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('*')]
    if len(lines)!=3:raise ValueError('Unexpected capacitor netlist closure.')
    header=lines[0].split()
    if len(header)!=4 or header[0].lower()!='.subckt' or header[1].lower()!='coupon' or set(header[2:])!={'C1','C2'}:
        raise ValueError('Unexpected capacitor interface.')
    if lines[-1].lower() not in ('.ends coupon','.ends'):raise ValueError('Unexpected netlist terminator.')
    row=lines[1].split()
    if terminals not in (('C1','C2'),('C2','C1')):raise ValueError('Unknown terminal control.')
    if len(row)!=9 or not row[0].startswith('C') or row[1:4]!=[*terminals,'cap_cmim']:
        raise ValueError('Expected exactly one ordered top/bottom cap_cmim device.')
    params={}
    for field in row[4:]:
        if field.count('=')!=1:raise ValueError('Malformed capacitor parameter.')
        key,value=field.split('=');key=key.lower()
        if key in params:raise ValueError('Duplicated capacitor parameter.')
        params[key]=scalar(value)
    if set(params)!={'w','l','a','p','m'}:raise ValueError('Capacitor parameter coverage differs.')
    w=Decimal(str(width_um));l=Decimal(str(length_um)); expected=(w*Decimal('1e-6'),l*Decimal('1e-6'))
    if sorted((params['w'],params['l']))!=sorted(expected):raise ValueError('Extracted dimensions differ.')
    if params['a']!=w*l*Decimal('1e-12') or params['p']!=2*(w+l)*Decimal('1e-6') or params['m']!=1:
        raise ValueError('Extracted area, perimeter or multiplicity differs.')
    return dict(model='cap_cmim',top=terminals[0],bottom=terminals[1],width_um=str(w),length_um=str(l),
                area_um2=str(w*l),perimeter_um=str(2*(w+l)),multiplicity=1)
