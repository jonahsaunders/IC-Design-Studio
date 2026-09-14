"""Reconnect inherited worker pipes in the windowed Windows executable.

Pythonw and PyInstaller's windowed bootloader leave sys.stdout/stderr at None,
even when QProcess supplies valid redirected handles. Duplicate those handles
so closing a Python stream cannot close the parent's inherited handle itself.
"""
import os
import sys


def connect():
    if os.name!='nt': return
    import ctypes
    from ctypes import wintypes
    import msvcrt
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetStdHandle.argtypes=[wintypes.DWORD]; kernel.GetStdHandle.restype=wintypes.HANDLE
    kernel.GetCurrentProcess.restype=wintypes.HANDLE
    kernel.DuplicateHandle.argtypes=[wintypes.HANDLE,wintypes.HANDLE,wintypes.HANDLE,
                                    ctypes.POINTER(wintypes.HANDLE),wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.DuplicateHandle.restype=wintypes.BOOL
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    process=kernel.GetCurrentProcess()
    for name,number,mode,flag in [('stdin',-10,'r',os.O_RDONLY),('stdout',-11,'w',os.O_WRONLY),('stderr',-12,'w',os.O_WRONLY)]:
        if getattr(sys,name) is not None: continue
        handle=kernel.GetStdHandle(number & 0xffffffff)
        duplicate=wintypes.HANDLE()
        if handle not in (None,0,ctypes.c_void_p(-1).value) and kernel.DuplicateHandle(process,handle,process,ctypes.byref(duplicate),0,False,2):
            try:
                descriptor=msvcrt.open_osfhandle(duplicate.value,flag|os.O_BINARY)
            except OSError:
                kernel.CloseHandle(duplicate)
            else:
                setattr(sys,name,os.fdopen(descriptor,mode,encoding='utf-8',errors='replace',buffering=1))
                continue
        setattr(sys,name,open(os.devnull,mode,encoding='utf-8'))
