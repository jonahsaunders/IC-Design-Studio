"""Measure the public Tiny Tapeout metal-density profiles; always unqualified."""
import argparse
import json
from pathlib import Path
from icstudio.digital_sky130_oxide_density import audit


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('gds', type=Path)
    p.add_argument('--bounds-nm', type=int, nargs=4, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.resolve() == args.gds.resolve():
        p.error('Output must not overwrite the input layout.')
    report = audit(args.gds, args.bounds_nm)
    args.output.write_bytes((json.dumps(report, indent=2)+'\n').encode())
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
