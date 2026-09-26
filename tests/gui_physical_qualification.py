"""Exercise the same physical acceptance probe shipped in the frozen desktop."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from icstudio.physical_desktop_probe import main
if __name__=='__main__':raise SystemExit(main())
