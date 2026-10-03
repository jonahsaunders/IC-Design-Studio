"""Explicit desktop toolchain selection; saved paths never select a backend."""
from .digital_runtime import TOOLS


def normalize_executable(value):
    """Accept paths pasted with shell/Windows Copy as path quotes.

    A tool setting is one executable, never a shell command. Preserve internal
    whitespace and quotes, removing only a matching pair around the whole path.
    """
    value = str(value or '').strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        value = value[1:-1]
    return value


def selection(settings):
    mode = settings.value('digital/toolchain', 'included')
    if mode != 'custom':
        return {'toolchain': 'included', 'tools': {}, 'orfs': ''}
    return {'toolchain': 'custom',
            'tools': {name: normalize_executable(settings.value('engine/'+name, '')) for name in TOOLS},
            'orfs': settings.value('digital/orfs', '')}
