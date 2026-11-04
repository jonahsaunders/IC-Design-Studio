"""Source-defined LVS selectors for public IHP RF MOS and MiM symbols.

These selectors retain physical class during Xschem exchange. They neither
supply RF geometry nor change the compact simulation model or saved package.
"""
import shlex
from .pdk_import import template_values

RF_VIEWS = {
    'sg13_lv_rf_nmos': ('sg13_lv_nmos', 'rfnmos'),
    'sg13_lv_rf_pmos': ('sg13_lv_pmos', 'rfpmos'),
    'sg13_hv_rf_nmos': ('sg13_hv_nmos', 'rfnmoshv'),
    'sg13_hv_rf_pmos': ('sg13_hv_pmos', 'rfpmoshv'),
    'cap_rfcmim': ('cap_rfcmim', 'rfcmim'),
}


def lvs_model(binding, symbol=None):
    source = binding.get('source', '')
    views = {'libs.tech/xschem/sg13g2_pr/'+name+'.sym': values
             for name, values in RF_VIEWS.items()}
    if source not in views:
        return None
    compact, selector = views[source]
    if binding.get('model') != compact or binding.get('prefix') != 'X':
        raise ValueError('IHP RF MOS compact-model binding changed; review its physical selector.')
    for candidate in (binding.get('symbol', {}), symbol) if symbol is not None else (binding.get('symbol', {}),):
        attrs = candidate.get('attributes', {})
        defaults = template_values(attrs.get('template', ''))
        expected = ('C@name @pinlist @lvs_model w=@w l=@l wfeed=@wfeed m=@m'
                    if compact == 'cap_rfcmim' else
                    'M@name @pinlist @lvs_model w=@w l=@l ng=@ng m=@m')
        if (defaults.get('lvs_model') != selector
                or ' '.join(attrs.get('lvs_format', '').split()) != expected):
            raise ValueError('IHP RF MOS source-defined LVS selector changed or is missing.')
    return selector


def validate_external_selector(binding, properties):
    """Keep old missing properties readable; reject changed or ambiguous ones."""
    selector = lvs_model(binding)
    if selector is None:
        return
    lexer = shlex.shlex(properties, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ''
    values = [token.split('=', 1)[1] for token in lexer
              if token.startswith('lvs_model=')]
    if values and values != [selector]:
        raise ValueError('IHP RF LVS selector changed externally or is ambiguous. Choose the physical catalog view in Studio.')
