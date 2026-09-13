"""Require real installation checks before a platform's desktop is packaged."""
import json
import os
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from icstudio.digital_runtime import setup, manifest, payload_root
from icstudio.model import atomic_write

record=setup(lambda message:print(message,flush=True))
atomic_write(payload_root()/('qualified-'+('Windows' if os.name=='nt' else 'Linux')+'.json'),
             json.dumps({'sha256':manifest()['sha256'],'acceptance':record},indent=2))
