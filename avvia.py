#!/usr/bin/env python3
"""Punto d'ingresso per l'eseguibile pacchettizzato.

PyInstaller esegue questo file come script a se' stante, quindi l'import di
``pdfeditor`` deve essere assoluto: un import relativo (come in
``pdfeditor/__main__.py``) fallirebbe nell'eseguibile compilato.
"""

import os
import sys


def _prepara() -> None:
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    if sys.platform.startswith("linux") and not (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    ):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    root = os.path.dirname(os.path.abspath(__file__))
    if root not in sys.path:
        sys.path.insert(0, root)


if __name__ == "__main__":
    _prepara()
    from pdfeditor.app import run

    sys.exit(run())
