# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — SmartStore Auto Buyer"""

import os
import customtkinter

ctk_path = os.path.dirname(customtkinter.__file__)

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[
        ('chromedriver.exe', '.'),
    ],
    datas=[
        (ctk_path, 'customtkinter/'),
        ('app_icon.ico', '.'),
        ('app_icon.png', '.'),
    ],
    hiddenimports=[
        'keyring.backends.Windows',
        'customtkinter',
        'PIL._tkinter_finder',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SmartStoreAutoBuyer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app_icon.ico',
)
