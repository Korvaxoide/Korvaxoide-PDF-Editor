"""Cronologia e scritture dei campi: un tasto non deve serializzare il PDF."""

from __future__ import annotations

import pymupdf
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

from pdfeditor.core.document import Document
from pdfeditor.ui.main_window import MainWindow


def _pdf_con_campi(percorso) -> None:
    """Un PDF con due campi di testo, già salvato su disco."""
    doc = Document()
    doc.new(400, 600)
    doc.add_field(0, "text", pymupdf.Rect(40, 80, 300, 110), name="nome")
    doc.add_field(0, "text", pymupdf.Rect(40, 130, 300, 160), name="cognome")
    doc.save(percorso)
    doc.close()


def _valore(doc: Document, nome: str):
    return next(f.value for f in doc.fields(0) if f.name == nome)


def _xref(doc: Document, nome: str) -> int:
    return next(f.xref for f in doc.fields(0) if f.name == nome)


@pytest.fixture()
def modulo(finestra, tmp_path) -> MainWindow:
    percorso = tmp_path / "modulo.pdf"
    _pdf_con_campi(percorso)
    finestra.load_path(str(percorso))
    for _ in range(6):
        QApplication.instance().processEvents()
    finestra.doc.history.clear()
    return finestra


def _apri_editor(finestra: MainWindow, nome: str) -> QLineEdit:
    xref = _xref(finestra.doc, nome)
    finestra.view.begin_field_edit(0, xref)
    for _ in range(4):
        QApplication.instance().processEvents()
    editor = finestra.view._editor
    assert isinstance(editor, QLineEdit)
    return editor


def test_venti_caratteri_fanno_una_sola_modifica(modulo, monkeypatch):
    """Venti tasti devono produrre due snapshot e un solo passo di undo."""
    doc = modulo.doc
    originale = doc.snapshot
    chiamate: list[int] = []

    def conta() -> bytes:
        chiamate.append(1)
        return originale()

    monkeypatch.setattr(doc, "snapshot", conta)
    editor = _apri_editor(modulo, "nome")

    QTest.keyClicks(editor, "abcdefghijklmnopqrst")
    # durante la digitazione il documento non viene toccato
    assert chiamate == []
    QTest.qWait(400)

    assert len(chiamate) == 2, chiamate
    assert _valore(doc, "nome") == "abcdefghijklmnopqrst"

    # un solo comando: il primo undo riporta al valore precedente, il secondo
    # non ha nulla da annullare
    assert doc.history.undo() is not None
    assert _valore(doc, "nome") == ""
    assert doc.history.undo() is None


def test_il_cambio_di_campo_non_perde_il_valore(modulo):
    """Passando a un altro campo il valore in sospeso viene scritto subito."""
    vista = modulo.view
    editor = _apri_editor(modulo, "nome")
    QTest.keyClicks(editor, "Anna")

    vista.begin_field_edit(0, _xref(modulo.doc, "cognome"))
    for _ in range(4):
        QApplication.instance().processEvents()

    assert _valore(modulo.doc, "nome") == "Anna"


def test_invio_flusha_il_valore(modulo):
    """Invio chiude l'editor e non deve perdere l'ultimo carattere."""
    editor = _apri_editor(modulo, "nome")
    QTest.keyClicks(editor, "X")

    QTest.keyClick(editor, Qt.Key_Return)
    for _ in range(4):
        QApplication.instance().processEvents()

    assert modulo.view._editor is None
    assert _valore(modulo.doc, "nome") == "X"


def test_il_salvataggio_include_il_commit_pendente(modulo):
    """Salvare entro i 300 ms del timer deve includere l'ultimo carattere."""
    editor = _apri_editor(modulo, "nome")
    QTest.keyClicks(editor, "M")

    # nessuna attesa: il timer non è ancora scattato
    modulo.file_save()

    with pymupdf.open(str(modulo.doc.path)) as letto:
        valori = {w.field_name: w.field_value for w in letto[0].widgets()}
    assert valori["nome"] == "M"
