"""Explicit desktop toolchain selection; saved paths never select a backend."""
from .digital_runtime import TOOLS


def selection(settings):
    mode = settings.value('digital/toolchain', 'included')
    if mode != 'custom':
        return {'toolchain': 'included', 'tools': {}, 'orfs': ''}
    return {'toolchain': 'custom',
            'tools': {name: settings.value('engine/'+name, '') for name in TOOLS},
            'orfs': settings.value('digital/orfs', '')}
