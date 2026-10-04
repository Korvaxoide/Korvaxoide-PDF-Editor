# -*- mode: python ; coding: utf-8 -*-
"""Specifica PyInstaller per Korvaxoide PDF Editor.

Un unico file per Windows, Linux e macOS: il sistema viene rilevato da
PyInstaller. Dopo la raccolta viene eseguita una potatura dei moduli Qt non
necessari (WebEngine, Quick, Qml, Designer, Multimedia, Sql…), che da soli
pesano oltre 300 MB.

    python -m tools.make_icons
    pyinstaller KorvaxoidePDF.spec --noconfirm

Le icone non sono nel repository, sono disegnate: senza il primo comando
l'eseguibile esce senza icona, perche' qui sotto il file viene cercato e, se
manca, si prosegue senza. ``build_linux.sh`` e ``build_windows.ps1`` eseguono
i due passi nell'ordine giusto.
"""

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve()
IS_WINDOWS = sys.platform.startswith("win")
IS_MACOS = sys.platform == "darwin"

# La versione viene letta dal pacchetto con una regex, non importandolo:
# importare ``pdfeditor`` qui trascinerebbe dentro la specifica tutto quello
# che il pacchetto importa, e non serve a nulla per costruire l'eseguibile.
VERSION = ""
for _riga in (ROOT / "pdfeditor" / "__init__.py").read_text(encoding="utf-8").splitlines():
    _m = re.match(r'^__version__ = "(.*)"$', _riga)
    if _m:
        VERSION = _m.group(1)
        break
if not VERSION:
    raise SystemExit("versione non trovata in pdfeditor/__init__.py")

# --------------------------------------------------------------- dipendenze
hidden = [
    "pymupdf",
    "pymupdf.mupdf",
    "PIL.Image",
    "PIL.ImageFont",
    "PIL.ImageDraw",
    "PIL.ImageFilter",
    "cryptography",
    "asn1crypto",
]

# Moduli Qt che l'applicazione usa davvero. Elencarli evita che PyInstaller
# trascini l'intero Qt Addons (oltre 400 MB di librerie inutili).
QT_USED = [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtPrintSupport",
    "PySide6.QtNetwork",
    "PySide6.QtSvg",
    "PySide6.QtXml",
    "PySide6.QtOpenGL",
    "PySide6.QtDBus",
]

# Moduli Qt da escludere esplicitamente: grandi e non usati.
QT_EXCLUDED = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebChannel",
    "PySide6.QtWebSockets", "PySide6.QtWebView", "PySide6.QtQuick", "PySide6.QtQuick3D",
    "PySide6.QtQuickWidgets", "PySide6.QtQml", "PySide6.QtQuickControls2", "PySide6.QtDesigner",
    "PySide6.QtHelp", "PySide6.QtUiTools", "PySide6.QtSql", "PySide6.QtTest",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtSpatialAudio",
    "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning", "PySide6.QtSensors",
    "PySide6.QtSerialPort", "PySide6.QtSerialBus", "PySide6.QtRemoteObjects", "PySide6.QtScxml",
    "PySide6.QtStateMachine", "PySide6.QtTextToSpeech", "PySide6.QtVirtualKeyboard",
    "PySide6.QtHttpServer", "PySide6.QtNetworkAuth", "PySide6.Qt3DCore", "PySide6.Qt3DRender",
    "PySide6.Qt3DInput", "PySide6.Qt3DLogic", "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtConcurrent", "PySide6.QtLocation",
    "PySide6.QtWebChannel", "PySide6.QtIntl", "PySide6.QtQmlModels",
]

hidden += QT_USED

datas: list[tuple[str, str]] = []
binaries: list[tuple[str, str]] = []

for cartella, destinazione in (("resources/icons", "resources/icons"),
                               ("resources/fonts", "resources/fonts")):
    src = ROOT / cartella
    if src.is_dir():
        for f in src.iterdir():
            if f.is_file():
                datas.append((str(f), f"{destinazione}/{f.name}"))

# Le traduzioni Qt sono gia' incluse dall'hook di PyInstaller: qui vengono solo
# mantenute le italiane (potatura, in fondo).


def potatura_qt(percorso: Path) -> tuple[int, int]:
    """Rimuove librerie e plugin Qt non necessari. Ritorna (file, byte rimossi)."""
    rimossi = 0
    byte = 0

    def _elimina(sotto: Path, predicato) -> None:
        nonlocal rimossi, byte
        if not sotto.is_dir():
            return
        for f in sorted(sotto.rglob("*"), reverse=True):
            if f.is_file() and predicato(f):
                try:
                    byte += f.stat().st_size
                    f.unlink()
                    rimossi += 1
                except OSError:
                    pass

    def _non_usato(f: Path) -> bool:
        nome = f.name.lower()
        return any(k in nome for k in (
            "webengine", "quick", "qml", "designer", "multimedia", "charts",
            "datavisualization", "bluetooth", "nfc", "positioning", "sensors",
            "serialport", "scxml", "states", "texttospeech", "remoteobjects",
            "spatialaudio", "virtualkeyboard", "httpserver", "networkauth",
            "quick3d", "3dcore", "3drender", "3dinput", "3dlogic", "3danimation",
            "3dextras", "sqldrivers", "designer", "help", "qtquick", "shadertools",
        ))

    # Nella distribuzione su cartella Qt sta sotto _internal
    qt = percorso / "_internal" / "PySide6" / "Qt"
    if not qt.is_dir():
        qt = percorso / "PySide6" / "Qt"
    if not qt.is_dir():
        return 0, 0
    # librerie Qt non usate
    _elimina(qt / "lib", _non_usato)
    # plugin Qt non usati
    plugin_da_togliere = (
        "sceneparsers", "assetimporters", "sqldrivers", "qmltooling", "qmllint",
        "designer", "multimedia", "geoservices", "canbus", "sensors", "position",
        "texttospeech", "webview", "renderers", "tls", "networkinformation",
        "scxmldatamodel",
    )
    for nome in plugin_da_togliere:
        p = qt / "plugins" / nome
        if p.is_dir():
            byte += sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
            shutil.rmtree(p, ignore_errors=True)
            rimossi += 1
    # traduzioni superflue
    tr = qt / "translations"
    if tr.is_dir():
        for f in tr.iterdir():
            if f.is_file() and not f.stem.endswith("_it"):
                try:
                    byte += f.stat().st_size
                    f.unlink()
                    rimossi += 1
                except OSError:
                    pass
    # moduli QML
    qml = qt / "qml"
    if qml.is_dir():
        byte += sum(f.stat().st_size for f in qml.rglob("*") if f.is_file())
        shutil.rmtree(qml, ignore_errors=True)
        rimossi += 1
    # librerie di terze parti allegate da Qt ma inutili qui
    for f in (qt / "lib").glob("libav*.so*"):
        try:
            byte += f.stat().st_size
            f.unlink()
            rimossi += 1
        except OSError:
            pass
    return rimossi, byte


a_p = Analysis(
    [str(ROOT / "avvia.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=QT_EXCLUDED + [
        "tkinter", "matplotlib", "scipy", "numpy.f2py", "IPython",
        "pytest", "setuptools", "pip", "lxml", "test",
    ],
    noarchive=False,
)

pyz = PYZ(a_p.pure)

exe = EXE(
    pyz,
    a_p.scripts,
    [],
    exclude_binaries=True,
    name="KorvaxoidePDF",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=IS_MACOS,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "resources" / "icons" / "korvaxoide_pdf_editor.ico")
    if (ROOT / "resources" / "icons" / "korvaxoide_pdf_editor.ico").exists()
    else None,
)

coll = COLLECT(
    exe,
    a_p.binaries,
    a_p.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="KorvaxoidePDF",
)

# La potatura va eseguita dopo COLLECT, quando i file sono su disco.
_base = Path(DISTPATH)
if not _base.is_absolute():
    _base = Path(SPECPATH) / _base
print("[potatura] percorso:", _base / "KorvaxoidePDF", "esiste:", (_base / "KorvaxoidePDF").is_dir())
_rimossi, _byte = potatura_qt(_base / "KorvaxoidePDF")
print(f"[potatura Qt] rimossi {_rimossi} elementi ({_byte / (1024 * 1024):.0f} MB)")

if IS_MACOS:
    app = BUNDLE(
        coll,
        name="Korvaxoide PDF Editor.app",
        icon=str(ROOT / "resources" / "icons" / "korvaxoide_pdf_editor.icns")
        if (ROOT / "resources" / "icons" / "korvaxoide_pdf_editor.icns").exists()
        else None,
        bundle_identifier="it.korvaxoide.pdfeditor",
        info_plist={
            "CFBundleName": "Korvaxoide PDF Editor",
            "CFBundleDisplayName": "Korvaxoide PDF Editor",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            "CFBundleDocumentTypes": [
                {
                    "CFBundleTypeName": "Documento PDF",
                    "CFBundleTypeExtensions": ["pdf"],
                    "CFBundleTypeRole": "Editor",
                }
            ],
        },
    )
