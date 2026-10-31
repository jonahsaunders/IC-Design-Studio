"""Necessary model geometry guards from the exact public isolbox equations.

These are mathematical domain checks, not foundry minimum design dimensions.
The inner diode uses (w - 2.1 um) * (l - 2.1 um); both lengths must be positive.
"""
import hashlib

MODEL_SHA256='66fa37819fa8a5c8af4dbb85f11208c3e38faa49c117de55c35a1538786715e8'


def constrain(parameters,model_bytes):
    if hashlib.sha256(model_bytes).hexdigest()!=MODEL_SHA256:
        raise ValueError('Review isolation-box geometry for this model revision.')
    if not {'w','l'}<=parameters.keys():raise ValueError('Missing isolation-box dimensions.')
    for name in ('w','l'):
        parameters[name]['exclusive_minimum']='2.1u'
    return parameters
