"""Utility per i dialoghi."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QScrollArea, QVBoxLayout, QWidget


def adatta_a_schermo(dlg: QDialog, larghezza: int = 560, altezza: int = 620) -> QDialog:
    """Dimensiona il dialogo entro lo schermo e ne rende il contenuto scorrevole.

    Un dialogo che chiede piu' spazio dello schermo spinge fuori vista pulsanti e
    opzioni: su uno schermo piccolo il pulsante di conferma sparisce e la
    funzione sembra non funzionare. Qui la dimensione richiesta viene ridotta a
    quella disponibile e, se il contenuto non ci sta, l'intero corpo del dialogo
    viene infilato in un'area scorrevole: nulla resta irraggiungibile.

    Va chiamata all'inizio del costruttore: la parte che sposta il contenuto
    nell'area scorrevole aspetta il ciclo di eventi, quando il layout del
    dialogo e' ormai costruito.
    """
    schermo = QApplication.primaryScreen()
    disponibile = schermo.availableGeometry() if schermo is not None else None
    if disponibile is None:
        dlg.resize(larghezza, altezza)
        return dlg

    # un margine per i bordi della finestra e per la barra del titolo
    limite_w = max(360, int(disponibile.width() * 0.94))
    limite_h = max(300, int(disponibile.height() * 0.92))
    dlg.resize(min(larghezza, limite_w), min(altezza, limite_h))
    dlg.setMinimumSize(min(360, limite_w), min(280, limite_h))
    QTimer.singleShot(0, lambda: _rendi_scorrevole(dlg, limite_w, limite_h))
    return dlg


def _rendi_scorrevole(dlg: QDialog, limite_w: int, limite_h: int) -> None:
    """Mette il corpo del dialogo in un'area scorrevole se non ci sta."""
    if getattr(dlg, "_adattato", False) or dlg.property("scroll_adattato"):
        return
    minimo = dlg.minimumSizeHint()
    if minimo.height() <= limite_h and minimo.width() <= limite_w:
        return
    vecchio = dlg.layout()
    if vecchio is None or not vecchio.count():
        return
    contenitore = QWidget(dlg)
    nuovo = QVBoxLayout(contenitore)
    nuovo.setContentsMargins(0, 0, 0, 0)
    while vecchio.count():
        nuovo.addItem(vecchio.takeAt(0))
    area = QScrollArea(dlg)
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.NoFrame)
    area.setWidget(contenitore)
    # si riusa il layout gia' presente: aggiungerne un secondo su uno stesso
    # widget e' un errore per Qt
    vecchio.addWidget(area)
    dlg.setProperty("scroll_adattato", True)
    dlg._area_scorrevole = area  # va tenuto vivo

