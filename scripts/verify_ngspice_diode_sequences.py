"""Check repeated diode analyses with the same oracle used by the application."""
import argparse
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.diode_runtime import (deck, validate, verify, normalized_error,
                                   THERMAL_VOLTAGE, RELATIVE_TOLERANCE,
                                   ABSOLUTE_TOLERANCE, INITIAL, AC_CASES)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.ngspice, args.output)
    print(json.dumps(result, indent=2))
    raise SystemExit(result['status'] != 'PASS')
