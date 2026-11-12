"""Exact GF180 extensionless Xschem configuration declaration routes.

This reads three pinned configuration sources with the existing nonexecuting
Tcl grammar. It neither resolves dependencies nor runs Xschem, Tcl or a model.
Menus and the IHP configuration with unenumerated Tk callbacks remain excluded.
"""
import hashlib
from scripts.inventory_source_configs import tcl_views


def require(ok, message):
    if not ok:
        raise ValueError('Xschem configuration inventory: '+message)


REVIEWED = {('gf180-ecosystem', 'google/globalfoundries-pdk-libs-gf180mcu_fd_pr@9f992d5a9186d1f7820c58f039c484ad35b2edea', 'cells/xschem/xschemrc', 'libraries/gf180mcu_fd_pr/latest/cells/xschem/xschemrc', None, '100644'): ('a6952b491a3eb69ecb3c52a285ba15cef6165234c330ddf00da19a189c1a6665', 'eaa174ac04a4c972f392528e6759171d91690e48', 16864), ('gf180mcu', 'fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr@4d0b4cef59c7686fac5fd3f4c6fb41d251d1f90c', 'cells/xschem/user_xschemrc', 'cells/xschem/user_xschemrc', None, '100644'): ('75c713dedded94663b02abc2b83a06f7b637b6da077b3ac1cbb7d2a059597647', 'bae24d152ce765fc36bb7c82d2d339c3c4487554', 1089), ('gf180mcu', 'fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr@4d0b4cef59c7686fac5fd3f4c6fb41d251d1f90c', 'cells/xschem/xschemrc', 'cells/xschem/xschemrc', None, '100644'): ('3b3236fe5afc371f74c13de83c15c9cb266237729cc4db89f40923f837823cde', 'f7dbdc9dc48fb5540764be816b3be045dcab0054', 14460)}


def configuration_facts(text):
    # Do not confuse a successful lexical parse with complete callback coverage.
    # These three exact configurations have no Tk callback declarations.
    require('-command' not in text, 'Tk callback declarations require separate review')
    return tcl_views(text)


def xschem_configuration_views(row, raw):
    key = tuple(row.get(k) for k in ('family','repository','repository_path','path','archive','mode'))
    expected = REVIEWED.get(key)
    if expected is None:
        return None
    digest, blob, size = expected
    require(type(raw) is bytes and len(raw) == size and hashlib.sha256(raw).hexdigest() == digest,
            'source bytes changed')
    require(hashlib.sha1(b'blob '+str(size).encode()+b'\0'+raw).hexdigest() == blob,
            'Git source identity changed')
    require(row.get('bytes') == size and row.get('git_blob_sha1') == blob and
            row.get('sha256', digest) == digest, 'source ledger identity changed')
    return configuration_facts(raw.decode('utf-8'))
