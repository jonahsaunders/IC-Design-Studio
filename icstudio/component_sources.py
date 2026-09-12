"""Library provenance helpers independent of the desktop runtime."""
from pathlib import PurePosixPath


def library_name(reference):
    """Use the saved relative library path, never require the original file."""
    parent = str(PurePosixPath(str(reference).replace('\\', '/')).parent)
    return parent if parent not in ('', '.') else 'Project definitions'



def imported_library(reference, symbol_path=''):
    source = library_name(reference)
    if source != 'Project definitions': return source
    path = PurePosixPath(str(symbol_path).replace('\\', '/'))
    parent = path.parent
    if parent.name == 'symbols': parent = parent.parent
    return parent.name or source
