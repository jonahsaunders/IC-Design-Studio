"""Reviewed public GF180 asymmetric 10 V model interface.

Original Apache-2.0 models and symbols are distributed unchanged. Recommended
model geometry ranges are not a substitute for physical design-rule limits.
"""
import hashlib

MODELS=('nfet_10v0_asym','pfet_10v0_asym')
MODEL_SHA256='8a8d44d5f13d4a097e86fab598e97e82bb726af1cc01eb6d500739766dfd9363'
MODEL_PATH='libs.tech/ngspice/smbb000149.spice'
CORNERS=dict(nominal='typical',typical='typical',ff='ff',ss='ss',fs='fs',sf='sf')
DOCUMENTATION='https://gf180mcu-pdk.readthedocs.io/en/latest/analog/model_parameters/HV/'
NOTE='Public asymmetric 10 V model: independent drain/source terminals, single finger only. W/L bounds are the published recommended model ranges; physical geometry and reliability require separate checks.'


def constrain(model,parameters,source):
    if model not in MODELS or hashlib.sha256(source).hexdigest()!=MODEL_SHA256:
        raise ValueError('Review GF180 high-voltage model interface for this source revision.')
    if not {'w','l','nf','m','ad','as','pd','ps'}<=set(parameters):
        raise ValueError('Incomplete GF180 high-voltage parameter interface.')
    parameters['w'].update(minimum='4u',maximum='50u',unit='m')
    parameters['l'].update(minimum='.6u',maximum='20u',unit='m')
    parameters['nf'].update(fixed=1,integer=True)
    parameters['m'].update(minimum=1,maximum=100)
