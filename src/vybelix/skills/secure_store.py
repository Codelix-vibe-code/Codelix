"""Small Windows DPAPI wrapper for local skill configuration secrets."""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


class SecretStoreError(RuntimeError):
    pass


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def protect(data: bytes) -> bytes:
    if os.name != "nt":
        raise SecretStoreError("Le stockage sécurisé des secrets de skills nécessite DPAPI Windows.")
    if not isinstance(data, bytes) or len(data) > 1_048_576:
        raise SecretStoreError("Données secrètes invalides ou trop volumineuses.")
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    source_buffer = ctypes.create_string_buffer(data)
    source = _DataBlob(len(data), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_byte)))
    target = _DataBlob()
    crypt32.CryptProtectData.argtypes = [ctypes.POINTER(_DataBlob), wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DataBlob)]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    if not crypt32.CryptProtectData(ctypes.byref(source), "Vybelix Skill Config", None, None, None, 0x1, ctypes.byref(target)):
        raise SecretStoreError("DPAPI n’a pas pu chiffrer la configuration du skill.")
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree(target.pbData)
