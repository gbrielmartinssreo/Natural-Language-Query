# -*- mode: python ; coding: utf-8 -*-
"""Spec do PyInstaller para o NLQ (distribuição em pasta / onedir).

Uso:

    uv run --with pyinstaller pyinstaller --noconfirm --clean nlq.spec

O resultado fica em ``dist/NLQ/``. Os recursos internos (frontend,
prompts e skills) vão para dentro do pacote; ``.env`` e ``sheets/``
ficam externos, ao lado do executável.
"""

from PyInstaller.utils.hooks import collect_all

datas = [
    ("frontend", "frontend"),
    ("src/nlq/agent/prompts", "nlq/agent/prompts"),
    ("src/nlq/agent/skills", "nlq/agent/skills"),
]
binaries = []
hiddenimports = []

# Pacotes usados de forma dinâmica/indireta e que podem não ter hook.
for pacote in (
    "deepagents",
    "xldetect",
    "langchain_groq",
    "langchain_openrouter",
    "langchain_openai",
    "tiktoken",
):
    try:
        _datas, _binaries, _hidden = collect_all(pacote)
    except Exception:
        continue

    datas += _datas
    binaries += _binaries
    hiddenimports += _hidden


a = Analysis(
    ["src/nlq/desktop.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NLQ",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
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
    upx=False,
    upx_exclude=[],
    name="NLQ",
)
