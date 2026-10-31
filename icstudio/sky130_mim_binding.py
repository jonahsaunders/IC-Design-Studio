"""Exact-source correction for the second MiM symbol's unused VM parameter."""
import hashlib

SYMBOL_SHA256 = 'b20c6884dcacecd897b81276a7dc220beb0c760815f0fde2da241456557fec2e'
MODEL_SHA256 = 'a2e9ed5568b23debce5ac002f15df8c675010bac34d05b0c4e8a8dcca916260f'


def reviewed_parameters(symbol, model, emitted):
    if (hashlib.sha256(symbol).hexdigest() != SYMBOL_SHA256
            or hashlib.sha256(model).hexdigest() != MODEL_SHA256
            or emitted != {'w':'w', 'l':'l', 'vm':'mf', 'm':'mf'}):
        raise ValueError('Unreviewed SKY130 second MiM parameter source; select an explicit model adapter.')
    return {'w':'w', 'l':'l', 'mf':'mf', 'm':'mf'}
