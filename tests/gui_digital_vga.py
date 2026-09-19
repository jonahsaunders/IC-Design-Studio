"""Run the same VGA qualification used by packaged desktop applications."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.vga_probe import main

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'build/digital-vga-ui')
    raise SystemExit(main(parser.parse_args().out))
