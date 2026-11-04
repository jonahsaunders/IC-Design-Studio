"""Measure required waffle-drop predicates on explicitly selected full windows.

This command always exits 2: numerical observations are not full acceptance.
No window lattice or cell exemption is inferred from layout bounds.
"""
import argparse
import json
from pathlib import Path
from icstudio.digital_sky130_waffle_windows import audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('gds', type=Path)
    parser.add_argument('--windows', type=Path, required=True, help='JSON list of full 700 um window bounds in integer nm')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.gds, json.loads(args.windows.read_bytes()))
    args.output.write_bytes((json.dumps(report, indent=2)+'\n').encode())
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
