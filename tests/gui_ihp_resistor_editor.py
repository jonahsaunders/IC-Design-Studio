"""Run the same IHP resistor lifecycle producer used by packaged desktop applications."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from icstudio.ihp_resistor_desktop_probe import main

if __name__=='__main__':
    raise SystemExit(main(sys.argv[1:]))
