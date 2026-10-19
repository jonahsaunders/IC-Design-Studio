"""Reject incomplete Magic input even when Tcl and the process report success."""
import re


def require_readable_stream(log, log_path):
    # Magic continues after dropping unmapped GDS masks, and can still emit a
    # plausible circuit. Labels are also part of the connectivity contract.
    # Keep the complete engine output before raising; never waive a lost layer.
    # cifMakeBoundaryFunc emits this exact warning when multiple recognized
    # boundary rectangles set FIXED_BBOX. It does not discard physical paint.
    # Do not generalize this exception to other reader errors or warnings.
    boundary = (r'Error while reading cell "([^"\r\n]+)" '
                r'\(byte position [0-9]+\): Warning: +Cell \1 boundary was redefined\.')
    unreadable = any(re.search(r'Unknown layer/datatype|Error while reading cell', line, re.I)
                     and not re.fullmatch(boundary, line.strip()) for line in log.splitlines())
    if unreadable:
        raise ValueError('Magic could not read the complete layout. The selected technology '
                         'may not support a layer or datatype. See '+str(log_path))
