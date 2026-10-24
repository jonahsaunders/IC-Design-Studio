"""Declarative equivalents of two checksum-reviewed public IHP tap symbols.

The Apache-2.0 source symbols/models remain unchanged. Only the exact reviewed
symbol text is adapted in memory; Tcl is never executed. The model delegates R
to schematic capture, so dimensions must keep driving the resistance formula.
"""
import hashlib
import re

# Formula: IHP PDK Authors, Apache-2.0, pinned source symbols. Their original
# copyright/license headers remain in each package's libs.tech/xschem files.
SOURCE_COMMIT = '5e6d592e4002946a4616f798c357f0f3c06cf3b6'
SOURCE_URL = 'https://github.com/IHP-GmbH/IHP-Open-PDK/tree/'+SOURCE_COMMIT+'/ihp-sg13g2'
SYMBOLS = {
    'ntap1':'4793bb1189cb3a44307745c35d7ff8b6fdae3c7b9a36fb62fc549041eb307281',
    'ptap1':'ca93ba7e1aefc330edfa3735186977289b77594f8f137b000e8f432634a8ecb9',
}
MODELS = {
    'resistors_mod.lib':'7c77da0c0419c8a332550da3f934f530262bd452734090db827b68ff88d09c43',
    'resistors_mod_mismatch.lib':'ce5ea8559df174fbdad8192e45e5d65772ae3af90af61ba295419b2cb5154b29',
}
FORMULA = '1.0/(1.0/(9.8e-10/(@w*@l))+1.0/(9.8e-4/(2.0*(@w+@l))))'
NOTE = 'Reviewed IHP tap formula evaluated as bounded arithmetic; original Tcl is not executed. W/L are metres and determine resistance.'


def declarative_symbol(source):
    text = source.decode('utf-8').replace('\r\n','\n').replace('\r','\n')
    if hashlib.sha256(source).hexdigest() not in SYMBOLS.values():
        return text, []
    # The starred alternative LVS attribute is retained in the original file,
    # not exposed as an invalid native attribute. Preserve the active LVS text.
    text, comments = re.subn(r'^\*lvs_format=.*\n', '', text, flags=re.M)
    text, formats = re.subn(r'^format=.*$',
        'format="@spiceprefix@name @pinlist @model r=\''+FORMULA+'\' w=@w l=@l"', text, flags=re.M)
    if comments != 1 or formats != 1:
        raise ValueError('Unexpected reviewed IHP tap symbol structure.')
    return text, [NOTE]


def constrain(model, parameters, source):
    if model not in SYMBOLS or hashlib.sha256(source).hexdigest() not in MODELS.values():
        raise ValueError('Review IHP tap model equations for this source revision.')
    if set(parameters) != {'w','l','emit_r'} or parameters['emit_r']['default'] != FORMULA.replace('@',''):
        raise ValueError('Unexpected IHP tap resistance formula.')
    parameters['emit_r'].update(computed=True, unit='ohm')
    for name in ('w','l'):
        parameters[name].update(positive=True, unit='m')
