"""Reject incomplete Magic input even when Tcl and the process report success."""
import re


def require_readable_stream(log, log_path):
    # Magic continues after dropping unmapped GDS masks, and can still emit a
    # plausible circuit. Labels are also part of the connectivity contract.
    # Keep the complete engine output before raising; never waive a lost layer.
    if re.search(r'Unknown layer/datatype|Error while reading cell', log, re.I):
        raise ValueError('Magic could not read the complete layout. The selected technology '
                         'may not support a layer or datatype. See '+str(log_path))
