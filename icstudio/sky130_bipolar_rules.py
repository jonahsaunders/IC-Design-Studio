"""Explicit versioned PNP extraction update for the old locked SKY130 deck.

The replacement rules are copied from RTimothyEdwards/open_pdks at
aa3fc215a80d32437b8cca1cb3fdee819d18c4c9, sky130/magic/sky130.tech.
Only PNP model selection changes: actual emitter area replaces Magic-only
identifier markers that do not survive GDS exchange. No model renaming or
extracted-netlist substitution is performed.
"""
import hashlib
import re

SOURCE_COMMIT='aa3fc215a80d32437b8cca1cb3fdee819d18c4c9'
SOURCE_URL=f'https://github.com/RTimothyEdwards/open_pdks/blob/{SOURCE_COMMIT}/sky130/magic/sky130.tech'
BASE_TECH_SHA256='5ee53b96094fe144145bf1216627672747366ec9bef9f2f848304a9a0c77427e'
TECH_SHA256='e3a5d4ec10e4f347548c79dafac20ac1bb8ceebb7cb8cbc716bbdc18b581837a'


def corrected_technology(content):
    if hashlib.sha256(content).hexdigest()!=BASE_TECH_SHA256:
        raise ValueError('PNP extraction correction requires the exact locked base SKY130 technology.')
    text=content.decode('utf-8')
    for kind,small_max in (('msubcircuit','0.47'),('bjt','0.48')):
        pattern=r' device '+kind+r' sky130_fd_pr__pnp_05v5_W0p68L0p68[^\n]*(?:\\\n[^\n]*)?\n'+r' device '+kind+r' sky130_fd_pr__pnp_05v5_W3p40L3p40[^\n]*(?:\\\n[^\n]*)?\n'+r' device '+kind+r' sky130_fd_pr__pnp_05v5 [^\n]*\n'
        replacement=(f' device {kind} sky130_fd_pr__pnp_05v5 pnp *pdiff pwell,space/w a1=area\n'
            f' device {kind} sky130_fd_pr__pnp_05v5_W0p68L0p68 pnp *pdiff \\\n\tpwell,space/w a1>0.45 a1<{small_max}\n'
            f' device {kind} sky130_fd_pr__pnp_05v5_W3p40L3p40 pnp *pdiff \\\n\tpwell,space/w a1>11.55 a1<11.57\n')
        # bjt's upstream formatting puts pwell on the first line; whitespace
        # has no extraction meaning, but record one deterministic byte stream.
        if kind=='bjt':replacement=replacement.replace('pnp *pdiff \\\n\tpwell,space/w ','pnp *pdiff pwell,space/w \\\n\t')
        text,count=re.subn(pattern,lambda _:replacement,text)
        if count!=1:raise ValueError('Unexpected locked SKY130 PNP extraction block: '+kind)
    return text.encode('utf-8')
