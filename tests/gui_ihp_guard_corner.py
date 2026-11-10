"""Run the additive guard-corner Qt producer from the source checkout only."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from icstudio.ihp_guard_corner_desktop_probe import main

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
