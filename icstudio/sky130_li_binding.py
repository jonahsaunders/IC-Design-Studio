"""Source-checked spelling correction for SKY130's local-interconnect resistor.

The symbol's `li` refers to the documented local-interconnect `l1` model.
No model equations or dimensions are substituted or modified.
"""
import hashlib

SYMBOL_SHA256 = '0074841d358fc35f443b6ed79181e6ccd424365836b6130c7f35cbf283ce354e'
MODEL_SHA256 = '277930447149f1b40ffda6959a990e473bbda7bdf97ce6180f5e563fe5957eea'
MODEL = 'sky130_fd_pr__res_generic_l1'
DOCUMENTATION = 'https://skywater-pdk.readthedocs.io/en/main/rules/device-details.html#generic-resistors'


def reviewed_model(symbol, model):
    if hashlib.sha256(symbol).hexdigest()!=SYMBOL_SHA256 or hashlib.sha256(model).hexdigest()!=MODEL_SHA256:
        raise ValueError('Unreviewed SKY130 local-interconnect resistor source; select an explicit model adapter.')
    return MODEL
