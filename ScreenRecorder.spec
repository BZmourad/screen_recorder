# ScreenRecorder.spec
# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_all

# ---------------------------------------------------------------------------
# sounddevice : c'est un FICHIER .py (pas un package), + un dossier de données
# _sounddevice_data qui contient la DLL PortAudio.
# ---------------------------------------------------------------------------
import sounddevice as _sd
import _sounddevice_data as _sdd

_sd_file = _sd.__file__                    # .../site-packages/sounddevice.py
_sdd_dir = os.path.dirname(_sdd.__file__)  # .../site-packages/_sounddevice_data

# On force l'inclusion du fichier .py comme "data" pythonesque + on copie le
# dossier de données à côté dans le bundle.
datas_sd = [
    (_sd_file, "."),                       # sounddevice.py → racine du bundle
    (_sdd_dir, "_sounddevice_data"),       # dossier complet → _sounddevice_data/
]
binaries_sd = []
hiddenimports_sd = ["sounddevice", "_sounddevice_data"]

# ---------------------------------------------------------------------------
# imageio_ffmpeg : même chose, c'est un module simple + un dossier binaries/
# ---------------------------------------------------------------------------
import imageio_ffmpeg as _iff
import imageio_ffmpeg.binaries as _iffb  # noqa: F401  (force l'import)

_iff_file = _iff.__file__
_iff_dir = os.path.dirname(_iff_file)      # .../site-packages/imageio_ffmpeg

datas_ff = [(_iff_dir, "imageio_ffmpeg")]  # tout le dossier
binaries_ff = []
hiddenimports_ff = ["imageio_ffmpeg"]

# ---------------------------------------------------------------------------
# cv2 : garder collect_all qui fonctionne bien ici
# ---------------------------------------------------------------------------
datas_cv, binaries_cv, hiddenimports_cv = collect_all("cv2")

# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
datas = (
    [("assets/icon.ico", "."), (".env", ".")]
    + datas_sd + datas_ff + datas_cv
)
binaries = binaries_sd + binaries_ff + binaries_cv
hiddenimports = (
    ["win32gui", "win32con", "numpy", "ctypes"]
    + hiddenimports_sd + hiddenimports_ff + hiddenimports_cv
)

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
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
    name="ScreenRecorder",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                 # ⚠️ UPX peut corrompre les DLL natives — laisser à False
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico",
)