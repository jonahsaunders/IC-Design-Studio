"""Load the optional numerical core only from a compatible platform binary.

Source releases are platform-neutral and use the Python solver until a local
native core is built. Never ask Windows to load a Linux .so or macOS .dylib.
"""
from __future__ import annotations
import ctypes
from pathlib import Path
import platform
import struct
import sys


def native_library_name(target=None):
    target = sys.platform if target is None else target
    if target == 'win32':
        return 'iccore.dll'
    if target == 'darwin':
        return 'libiccore.dylib'
    if target.startswith('linux'):
        return 'libiccore.so'
    return None


def _windows_binary_matches(path):
    """Reject foreign or wrong-architecture files before LoadLibrary can show UI."""
    expected = {'amd64': 0x8664, 'x86_64': 0x8664, 'arm64': 0xaa64,
                'aarch64': 0xaa64, 'x86': 0x14c, 'i386': 0x14c,
                'i686': 0x14c}.get(platform.machine().lower())
    if ctypes.sizeof(ctypes.c_void_p) == 4:
        expected = 0x14c
    if expected is None:
        return False
    try:
        with path.open('rb') as f:
            header = f.read(64)
            if len(header) < 64 or header[:2] != b'MZ':
                return False
            offset = struct.unpack_from('<I', header, 60)[0]
            if not 64 <= offset <= 1024 * 1024:
                return False
            f.seek(offset)
            pe = f.read(6)
            return len(pe) == 6 and pe[:4] == b'PE\0\0' and struct.unpack_from('<H', pe, 4)[0] == expected
    except OSError:
        return False


def load_native_core(roots=None, target=None, loader=None):
    target = sys.platform if target is None else target
    name = native_library_name(target)
    if name is None:
        return None
    if roots is None:
        # __file__ is an absolute module path in both source and frozen builds.
        roots = [Path(__file__).resolve().parent]
    if loader is None:
        loader = ctypes.CDLL
    for root in roots:
        path = (Path(root) / name).resolve()
        if not path.is_file():
            continue
        if target == 'win32' and not _windows_binary_matches(path):
            continue
        try:
            lib = loader(str(path))
            solve = lib.ic_solve
            solve.argtypes = [ctypes.c_int] + [ctypes.POINTER(ctypes.c_double)] * 3
            solve.restype = ctypes.c_int
            return lib
        except (OSError, AttributeError):
            # The optional accelerator may be absent or incompatible. The
            # validated Python numerical path remains available in both cases.
            continue
    return None
