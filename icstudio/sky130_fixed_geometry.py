"""Reviewed fixed internal geometry of the public SKY130 20 V subcircuits.

The internal MOS and parasitic geometry is constant; W/L arguments do not
scale it. Out-of-bin arguments can also fail simulator model selection.
These guards describe the model interface, not legal
drawn-mask dimensions, a voltage rating, or a foundry operating envelope.
"""
import hashlib
from .model import scalar

CONTRACTS={
    'sky130_fd_pr__nfet_20v0':('64b63a8bd76ca1a5f7f14849d80399e99dd85ed39534c452ae65c4a3fa19e270','29.41','2.95'),
    'sky130_fd_pr__nfet_20v0_iso':('0ba6101d75c9ca9271c9e0254901804a33f2981d6a7b60e35d3a71e311e9fc56','30','1.5'),
    'sky130_fd_pr__nfet_20v0_nvt':('1b3c68a09794e92515d24ff596f92e087b527f68eb696df63dfadb3a78cb9c04','30','1.5'),
    'sky130_fd_pr__nfet_20v0_zvt':('a2173e3b3d601fc070e8c2babad25c01f6d0c61df8b3432d25245c800d51389d','30','5'),
    'sky130_fd_pr__pfet_20v0':('5ac0449e927e098e43b89b7ad84c506e59aca864fd8d1dae8e1f15b1dece9660','30','0.5'),
}
NOTE='Fixed internal model geometry: W/L inputs do not scale the public 20 V subcircuit and out-of-bin values can fail model selection. Only the recorded W/L values are accepted; use mult for parallel copies. These values do not establish drawn-mask dimensions or reliability limits.'


def constrain(model,parameters,source):
    expected,w,l=CONTRACTS[model]
    if hashlib.sha256(source).hexdigest()!=expected:
        raise ValueError('Unreviewed SKY130 fixed-geometry model; select an explicit adapter.')
    for key,value in (('w',w),('l',l)):
        if key not in parameters or scalar(parameters[key]['default'])!=scalar(value):
            raise ValueError('Unexpected SKY130 fixed-geometry symbol default: '+key)
        parameters[key].update(fixed=value,unit='um (fixed internal model geometry)')
