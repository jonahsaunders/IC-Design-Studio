"""Explicit parallel-factor propagation for seven pinned public SKY130 models.

The original resistor equations and mismatch parameter remain unchanged. Native
ngspice 42 and 47 did not propagate a caller's M through these nested X calls.
The correction declares M and explicitly forwards it to each immediate device.
"""
import hashlib

BASE_SHA256={
 'res_high_po':'5d5f46fc322ff3aa83222a588c712b758a3863b8aed3eea6ca637b120ddf411f',
 'res_xhigh_po':'de3ce358904404dc3aa11f8dc84500638557dd5fe4b5988e07c9e280fc9d6e78',
 'res_xhigh_po_0p35':'940ed59e4935e9f8bda6fe493bf0e5a33f7d7a6961f73fdb15e666637fa50f83',
 'res_xhigh_po_0p69':'d35a4b6371a9bd678f7fa1dabfbcfdbd3f29059ab5073516b4e55b6f92cb6b32',
 'res_xhigh_po_1p41':'c5993a674226d7878ac8a7400db00a26bfd25db3bd35c7b9a9da29db8ca11c14',
 'res_xhigh_po_2p85':'ecce036dde19fe4f0404652375a0ef549df115f393696f4c55639fde33cd9a47',
 'res_xhigh_po_5p73':'d4e13ad468f778656baf3438a3a2e7c5a6f64644678995f6ab6ec7e2e1636e3b'}
NOTICE='* IC Design Studio modification: explicitly propagate the parallel M factor.\n'


def relative(name):
    if name not in BASE_SHA256:raise ValueError('Unreviewed SKY130 resistor model.')
    return 'libs.ref/sky130_fd_pr/spice/sky130_fd_pr__'+name+'.model.spice'


def corrected(name,source):
    if name not in BASE_SHA256 or hashlib.sha256(source).hexdigest()!=BASE_SHA256[name]:
        raise ValueError('Use the exact reviewed SKY130 resistor source.')
    result=[];count=0
    for line in source.decode().splitlines(keepends=True):
        if line.startswith('.subckt'):
            result.append(NOTICE);line=line.rstrip('\n')+' m=1\n';count+=1
        if line.lower().startswith(('r','x')) and not (name=='res_xhigh_po' and line.startswith('rbody')):
            line=line.rstrip('\n')+' m={m}\n';count+=1
        # The behavioral R parser expects instance options after its complete
        # expression. Putting M before R= silently changes temperature behavior.
        if name=='res_xhigh_po' and line.startswith('+ (sub1'):
            line=line.rstrip('\n')+' m={m}\n';count+=1
        result.append(line)
    expected=4 if name=='res_high_po' else 5 if name=='res_xhigh_po' else 2
    if count!=expected:raise ValueError('Unexpected resistor statement structure.')
    return ''.join(result).encode()
