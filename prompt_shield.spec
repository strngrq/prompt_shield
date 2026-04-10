# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for PromptShield — optimized for minimal bundle size."""

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# ── Paths ──
ROOT = Path(SPECPATH)
ENTRY = str(ROOT / "prompt_shield" / "app.py")
ICON_MAC = str(ROOT / "resources" / "icon.icns")
ICON_WIN = str(ROOT / "resources" / "icon.ico")
ICON = ICON_MAC if sys.platform == "darwin" else ICON_WIN

# ── Heavy PySide6 modules we do NOT use ──
EXCLUDE_QT = [
    "PySide6.Qt3DAnimation", "PySide6.Qt3DCore", "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput", "PySide6.Qt3DLogic", "PySide6.Qt3DRender",
    "PySide6.QtBluetooth",
    "PySide6.QtCanvasPainter",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtDesigner",
    "PySide6.QtGraphs", "PySide6.QtGraphsWidgets",
    "PySide6.QtHelp",
    "PySide6.QtHttpServer",
    "PySide6.QtLocation",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
    "PySide6.QtNetworkAuth",
    "PySide6.QtNfc",
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtPositioning",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D",
    "PySide6.QtQuickControls2", "PySide6.QtQuickTest", "PySide6.QtQuickWidgets",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtSensors",
    "PySide6.QtSerialBus", "PySide6.QtSerialPort",
    "PySide6.QtSpatialAudio",
    "PySide6.QtSql",
    "PySide6.QtStateMachine",
    "PySide6.QtSvg", "PySide6.QtSvgWidgets",
    "PySide6.QtTest",
    "PySide6.QtTextToSpeech",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineQuick", "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebSockets", "PySide6.QtWebView",
    "PySide6.QtXml",
]

# Other heavy modules not needed at runtime
EXCLUDE_OTHER = [
    "tkinter", "_tkinter",
    "matplotlib", "PIL", "cairosvg", "cairocffi",  # build-time only
    "pytest", "unittest",
    "setuptools", "pkg_resources", "distutils",
    "pyinstaller", "PyInstaller",
]

EXCLUDES = EXCLUDE_QT + EXCLUDE_OTHER

# ── Presidio needs its recognizer YAML data files ──
# include_py_files=True ensures subdirectory tree physically exists on disk.
# Presidio resolves config paths via Path(__file__).parent / "../conf" which
# requires intermediate directories (recognizer_registry/, nlp_engine/, etc.)
# to be present for OS-level ".." traversal.  Without this, PyInstaller packs
# .pyc into PYZ and the directories are missing → FileNotFoundError.
presidio_datas = collect_data_files("presidio_analyzer", include_py_files=True)

# ── spaCy needs language data (lookups, etc.) ──
spacy_datas = collect_data_files("spacy", include_py_files=False)

# ── Include installed spaCy model packages with their data ──
en_model_datas = collect_data_files("en_core_web_sm")
spacy_datas += en_model_datas

# ── pymorphy3 dictionaries (Russian) ──
# spaCy's Russian model (ru_core_news_*) is downloaded at runtime via the
# Settings → Language Models UI, but its RussianLemmatizer lazily imports
# pymorphy3 + pymorphy3_dicts_ru. Those are pure-Python libraries, not model
# data, so we ship them in the bundle once. ~15 MB for dicts; covers both
# ru_core_news_sm and ru_core_news_lg.
spacy_datas += collect_data_files("pymorphy3_dicts_ru")

a = Analysis(
    [ENTRY],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "resources"), "resources"),
        *presidio_datas,
        *spacy_datas,
    ],
    hiddenimports=[
        "presidio_analyzer",
        "presidio_anonymizer",
        "spacy",
        "en_core_web_sm",
        # spaCy hidden imports that PyInstaller misses
        "spacy.lang.en",
        "spacy.lang.ru",
        # pymorphy3 is imported lazily inside spacy.lang.ru.lemmatizer at
        # runtime, so PyInstaller's static scanner misses it. Force-include.
        "pymorphy3",
        "pymorphy3.analyzer",
        "pymorphy3.opencorpora_dict",
        "pymorphy3.opencorpora_dict.storage",
        "pymorphy3_dicts_ru",
        "dawg_python",
        "docopt",
        "thinc.backends.numpy_ops",
        "thinc.backends.ops",
        "srsly.msgpack.util",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=2,  # strip docstrings & asserts from .pyc
    cipher=block_cipher,
)

# ── Remove Qt frameworks & dylibs we excluded ──
# PyInstaller may still bundle the .framework dirs even if the Python
# binding module is excluded. Strip them from binaries/datas.
_qt_strip = {
    "QtWebEngine", "Qt3D", "QtBluetooth", "QtMultimedia", "QtSensors",
    "QtSerialPort", "QtSerialBus", "QtRemoteObjects", "QtNfc",
    "QtQuick", "QtQml", "QtDesigner", "QtHelp", "QtCharts",
    "QtDataVisualization", "QtPdf", "QtSvg", "QtOpenGL",
    "QtLocation", "QtPositioning", "QtSpatialAudio", "QtTextToSpeech",
    "QtHttpServer", "QtNetworkAuth", "QtWebChannel", "QtWebSockets",
    "QtWebView", "QtScxml", "QtStateMachine", "QtTest", "QtGraphs",
    "QtCanvasPainter", "QtSql",
}

def _should_keep(name):
    for qt_mod in _qt_strip:
        if qt_mod in name:
            return False
    return True

a.binaries = [b for b in a.binaries if _should_keep(b[0])]
a.datas = [d for d in a.datas if _should_keep(d[0])]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

_is_win = sys.platform == "win32"

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PromptShield",
    debug=False,
    bootloader_ignore_signals=False,
    strip=not _is_win,
    upx=not _is_win,
    console=False,
    icon=ICON,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=not _is_win,
    upx=not _is_win,
    upx_exclude=[],
    name="PromptShield",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="PromptShield.app",
        icon=ICON_MAC,
        bundle_identifier="com.promptshield.app",
        info_plist={
            "CFBundleDisplayName": "PromptShield",
            "CFBundleShortVersionString": "1.0.0",
            "NSHighResolutionCapable": True,
        },
    )
