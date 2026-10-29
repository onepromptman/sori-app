# -*- mode: python ; coding: utf-8 -*-
#
# Build:  py -m PyInstaller --noconfirm "Sori.spec"
# Output: dist/Sori/  (onedir — ship the whole folder)
#
# The collect_all() calls below are what make the transcription backends
# survive freezing: ctranslate2/onnxruntime/av ship native DLLs that
# PyInstaller's import analysis alone will not find.
from PyInstaller.utils.hooks import collect_all

# huggingface_hub and faster_whisper have optional integrations with the
# whole scientific-Python stack. None of it is reachable from this app, but
# a plain collect_all drags ~500MB of torch/opencv/pyarrow into the bundle.
#
# matplotlib is NOT excluded (unlike the rest of this list) — engine/deckgen.py
# (the vendored private deck renderer) imports it unconditionally at module
# load, even though Sori never uses its PNG-preview path.
EXCLUDES = [
    'torch', 'torchvision', 'torchaudio',
    'cv2', 'pyarrow', 'pandas', 'numpy.f2py',
    'scipy', 'IPython', 'notebook', 'jupyter',
    'tkinter', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6',
    'tensorflow', 'transformers', 'datasets', 'sklearn',
]

# engine/ is optional: the public checkout does not ship it, and Sori renders
# fine without it. Naming a missing path in `datas` is a hard build error, so
# it is added only when present -- otherwise a public clone could not build
# its own exe. engine/fonts carries the OFL faces and OFL.txt, and the licence
# has to travel with the binaries it covers, so it ships whenever they do.
import os
datas = [('ui', 'ui')]
hiddenimports = ['sori_log', 'transcribe', 'training', 'deck_render', 'themes',
                  'themes.studio']
if os.path.isdir('engine'):
    hiddenimports += ['engine', 'engine.deckgen', 'engine.install_fonts']
    if os.path.isdir(os.path.join('engine', 'fonts')):
        datas.append(('engine/fonts', 'engine/fonts'))
binaries = []
tmp_ret = collect_all('faster_whisper')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('ctranslate2')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('av')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('yt_dlp')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('webview')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('clr_loader')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pythonnet')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('onnxruntime')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('tokenizers')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('huggingface_hub')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
# python-pptx ships a default.pptx template + XML schema files it loads by
# relative path at runtime — plain import analysis won't find those.
tmp_ret = collect_all('pptx')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
# matplotlib's font/style data files (mpl-data) — deckgen.py imports
# matplotlib unconditionally even though Sori only uses pptx output.
tmp_ret = collect_all('matplotlib')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('anthropic')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Sori',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Sori',
)
