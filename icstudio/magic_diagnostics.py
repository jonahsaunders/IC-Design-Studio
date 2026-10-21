"""Reject incomplete Magic input and rules despite successful Tcl/process exits."""
import re


def require_valid_technology(log, log_path):
    # Native TechError/TechPrintLine diagnostics identify the source, line and
    # section. Magic can skip an invalid rule and still report zero violations
    # and our Tcl completion marker. Missing includes and truncated definitions
    # use this same formatter, even when the body calls them a warning.
    if re.search(r'^.+: line [0-9]+: section [^\r\n]+:\s*$', log, re.M):
        raise ValueError('Magic could not load the complete technology rules. '
                         'Inspect the retained native diagnostic in '+str(log_path))


def require_readable_stream(log, log_path):
    require_valid_technology(log, log_path)
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
