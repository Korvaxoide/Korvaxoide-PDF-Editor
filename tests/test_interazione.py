"""Test di interazione: eventi reali, non chiamate ai metodi.

I test precedenti chiamavano direttamente i metodi della vista, quindi
passavano anche quando il percorso degli eventi era rotto: e' cosi' che un
clic su un campo modulo non faceva nulla e la digitazione perdeva tutto
tranne il primo carattere. Qui ogni azione passa da ``QTest``, come quando
preme un utente, e le finestre modali vengono chiuse automaticamente.
"""

from __future__ import annotations

import pymupdf
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QToolBar,
)

import ambiente
from pdfeditor.core import geometry as geo
from pdfeditor.ui.main_window import MainWindow


# ----------------------------------------------------------------- strumenti


class Utente:
    """Simula un utente: clic, tastiera e attesa degli eventi."""

    def __init__(self, finestra: MainWindow) -> None:
        self.w = finestra
        self.app = QApplication.instance()
        self.modali_chiusi: list[str] = []
        # chiude i dialoghi che si aprono, così un test non si blocca e
        # l'esito resta quello che conta
        self.timer = QTimer()
        self.timer.setInterval(120)
        self.timer.timeout.connect(self._chiudi_modali)
        self.timer.start()

    def _chiudi_modali(self) -> None:
        for w in self.app.topLevelWidgets():
            if not w.isVisible():
                continue
            if isinstance(w, QMessageBox):
                self.modali_chiusi.append(w.text()[:60])
                w.reject()
            elif isinstance(w, QDialog) and w.isModal():
                self.modali_chiusi.append(w.windowTitle() or type(w).__name__)
                w.reject()

    def attendi(self, cicli: int = 6) -> None:
        for _ in range(cicli):
            self.app.processEvents()

    def barra(self) -> QToolBar:
        for b in self.w.findChildren(QToolBar):
            if b.objectName() == "mainToolbar":
                return b
        raise AssertionError("barra principale non trovata")

    def pulsante(self, testo: str):
        b = self.barra()
        for a in b.actions():
            if a.text() == testo:
                widget = b.widgetForAction(a)
                assert widget is not None, f"«{testo}» non ha un pulsante"
                return widget
        raise AssertionError(f"pulsante «{testo}» non trovato")

    def clic_pulsante(self, testo: str) -> None:
        QTest.mouseClick(self.pulsante(testo), Qt.LeftButton)
        self.attendi()

    def punto_pagina(self, pagina: int, x: float, y: float) -> QPoint:
        vista = self.w.view
        nodo = vista.scene_obj.node(pagina)
        return vista.mapFromScene(nodo.scenePos() + QPointF(x, y))

    def punto_scena(self, pagina: int, x: float, y: float) -> QPointF:
        """Punto di scena corrispondente a un punto espresso in punti PDF."""
        vista = self.w.view
        return vista.scene_obj.node(pagina).scenePos() + QPointF(x, y)

    def punti_sotto_pixel(self, pagina: int, px: QPoint) -> QPointF:
        """Punto in punti PDF che corrisponde a un pixel della vista.

        Serve a misurare dove il puntatore si trova davvero: il mouse viaggia
        in pixel interi, quindi un punto PDF richiesto e un punto PDF ottenuto
        non coincidono mai, e la differenza dipende da quanti pixel vale un
        punto su quella macchina.
        """
        vista = self.w.view
        return vista._page_pos(vista.mapToScene(px))[1]

    def margine_di_un_pixel(self) -> float:
        """Quanti punti PDF vale un pixel della vista, con un pelo di respiro."""
        return 2 / max(self.w.view.transform().m11(), 0.01)

    def clic_pagina(self, pagina: int, x: float, y: float) -> None:
        QTest.mouseClick(self.vista_viewport(), Qt.LeftButton, Qt.NoModifier,
                        self.punto_pagina(pagina, x, y))
        self.attendi()

    def trascina(self, pagina: int, da: tuple[float, float], a: tuple[float, float],
                 mods=Qt.NoModifier) -> None:
        vp = self.vista_viewport()
        p1 = self.punto_pagina(pagina, *da)
        p2 = self.punto_pagina(pagina, *a)
        QTest.mousePress(vp, Qt.LeftButton, mods, p1)
        self.attendi(2)
        QTest.mouseMove(vp, p2)
        self.attendi(2)
        QTest.mouseRelease(vp, Qt.LeftButton, mods, p2)
        self.attendi()

    def vista_viewport(self):
        return self.w.view.viewport()

    def campo(self, nome: str):
        for f in self.w.doc.fields():
            if f.name == nome:
                return f
        raise AssertionError(f"campo {nome!r} non trovato")


@pytest.fixture()
def utente(finestra) -> Utente:
    finestra.resize(1500, 950)
    finestra.show()
    finestra.load_path(str(_documento_modello()))
    for _ in range(10):
        QApplication.instance().processEvents()
    u = Utente(finestra)
    yield u
    # il timer che chiude i dialoghi modali vive con l'utente finché l'oggetto
    # esiste: lasciarlo acceso dopo il test lo faceva chiudere anche i dialoghi
    # dei test successivi, e una firma disegnata a mano spariva da sola
    u.timer.stop()


def _documento_modello() -> str:
    """PDF con testo, campi modulo e un'immagine.

    Ogni chiamata riceve un file proprio. Su Windows un PDF che una
    finestra precedente tiene aperto non può essere riscritto: un modello
    condiviso farebbe fallire una dopo l'altra tutte le prove che lo usano,
    e il primo errore racconterebbe la catena invece della causa.
    """
    import io
    import uuid

    from PIL import Image

    from pdfeditor.core.document import Document

    percorso = str(ambiente.cartella("modelli") / f"interazione-{uuid.uuid4().hex}.pdf")
    d = Document()
    d.new(595, 842)
    d.insert_text_box(0, pymupdf.Rect(50, 60, 520, 95), "Relazione annuale", fontsize=18)
    d.insert_text_box(0, pymupdf.Rect(50, 110, 520, 150), "Testo da modificare qui.", fontsize=11)
    for nome, y in (("nome", 170), ("cognome", 210), ("citta", 250)):
        d.add_field(0, "text", pymupdf.Rect(50, y, 320, y + 28), name=nome, value="")
    d.add_field(0, "checkbox", pymupdf.Rect(50, 300, 70, 320), name="accetto", value=False)
    d.add_field(0, "combo", pymupdf.Rect(50, 340, 250, 362), name="settore",
                options=["Vendite", "Produzione"], value="Vendite")
    b = io.BytesIO()
    Image.new("RGB", (300, 200), (60, 120, 200)).save(b, "PNG")
    d.insert_image(0, pymupdf.Rect(50, 390, 400, 590), b.getvalue())
    d.add_bookmark("Introduzione", 0)
    d.save(percorso)
    d.close()
    return percorso


# --------------------------------------------------------------------- zoom


def test_zoom_avanti_e_indietro(utente: Utente):
    """I pulsanti dello zoom devono cambiare la percentuale mostrata."""
    iniziale = utente.w.lbl_zoom.text()
    utente.clic_pulsante("Ingrandisci")
    dopo = utente.w.lbl_zoom.text()
    assert dopo != iniziale, f"la percentuale non è cambiata ({iniziale})"
    assert int(dopo.rstrip("%")) > int(iniziale.rstrip("%"))

    utente.clic_pulsante("Riduci")
    assert utente.w.lbl_zoom.text() == iniziale


def test_zoom_si_ferma_ai_limiti(utente: Utente):
    for _ in range(30):
        utente.clic_pulsante("Riduci")
    assert utente.w.lbl_zoom.text() != ""
    assert utente.w.view.zoom() >= 0.05


def test_zoom_con_rotella_e_control(utente: Utente):
    from PySide6.QtCore import QPointF as _PF
    from PySide6.QtGui import QWheelEvent

    iniziale = utente.w.view.zoom()
    vp = utente.vista_viewport()
    pos = utente.punto_pagina(0, 200, 300)
    ev = QWheelEvent(
        _PF(pos), _PF(pos), QPoint(0, 120), QPoint(0, 120),
        Qt.NoButton, Qt.ControlModifier, Qt.NoScrollPhase, False,
    )
    QApplication.sendEvent(vp, ev)
    utente.attendi()
    assert utente.w.view.zoom() != iniziale, "la rotella con Control non ha cambiato lo zoom"


def test_zoom_tastiera(utente: Utente):
    """Ctrl+0 adatta alla pagina, Ctrl+2 la dimensione reale."""
    iniziale = utente.w.lbl_zoom.text()
    QTest.keyClick(utente.w, Qt.Key_Plus, Qt.ControlModifier)
    utente.attendi()
    assert utente.w.lbl_zoom.text() != iniziale
    QTest.keyClick(utente.w, Qt.Key_2, Qt.ControlModifier)
    utente.attendi()
    assert utente.w.lbl_zoom.text() == "100%", utente.w.lbl_zoom.text()


# ------------------------------------------------------------ campi modulo


def test_clic_su_un_campo_lo_attiva(utente: Utente):
    """Il clic su un campo deve aprirne l'editor."""
    f = utente.campo("nome")
    utente.clic_pagina(f.page, f.rect.x0 + 30, (f.rect.y0 + f.rect.y1) / 2)
    assert utente.w.view.active_field == (f.page, f.xref), "il campo non si è attivato"
    assert utente.w.view._editor is not None
    assert utente.w.view._editor.isVisible()


def test_digitazione_completa_va_a_buon_fine(utente: Utente):
    """Tutto quello che si scrive deve finire nel campo, non solo il primo tasto."""
    f = utente.campo("nome")
    utente.clic_pagina(f.page, f.rect.x0 + 30, (f.rect.y0 + f.rect.y1) / 2)
    editor = utente.w.view._editor
    assert editor is not None
    QTest.keyClicks(editor, "Mario Rossi")
    utente.attendi()
    valore = next(c.value for c in utente.w.doc.fields() if c.xref == f.xref)
    assert valore == "Mario Rossi", f"nel documento c'è {valore!r}"


def test_digitazione_in_tutti_i_campi(utente: Utente):
    for nome, testo in (("nome", "Ada"), ("cognome", "Lovelace"), ("citta", "Londra")):
        f = utente.campo(nome)
        utente.clic_pagina(f.page, f.rect.x0 + 30, (f.rect.y0 + f.rect.y1) / 2)
        editor = utente.w.view._editor
        assert editor is not None, f"l'editor di {nome} non si è aperto"
        QTest.keyClicks(editor, testo)
        utente.attendi()
        valore = next(c.value for c in utente.w.doc.fields() if c.xref == f.xref)
        assert valore == testo, f"{nome}: nel documento c'è {valore!r}"


def test_editor_sparisce_cliccando_fuori(utente: Utente):
    f = utente.campo("nome")
    utente.clic_pagina(f.page, f.rect.x0 + 30, (f.rect.y0 + f.rect.y1) / 2)
    assert utente.w.view._editor is not None
    utente.clic_pagina(f.page, 480, 700)
    assert utente.w.view._editor is None, "l'editor è rimasto aperto"


def test_casella_di_spunta_si_compila_al_clic(utente: Utente):
    f = utente.campo("accetto")
    assert f.value in (False, "Off", "", None)
    utente.clic_pagina(f.page, (f.rect.x0 + f.rect.x1) / 2, (f.rect.y0 + f.rect.y1) / 2)
    valore = next(c.value for c in utente.w.doc.fields() if c.xref == f.xref)
    assert valore not in (False, "Off", "", None), "la casella non si è spuntata"


def test_editor_riapre_dopo_una_richiesta_di_pagine(utente: Utente):
    """Una ricostruzione della scena non deve far perdere la compilazione."""
    f = utente.campo("nome")
    utente.clic_pagina(f.page, f.rect.x0 + 30, (f.rect.y0 + f.rect.y1) / 2)
    QTest.keyClicks(utente.w.view._editor, "Prova")
    utente.attendi()
    utente.w._on_pages_changed()
    utente.attendi()
    assert utente.w.view._editor is not None, "l'editor è stato distrutto"
    QTest.keyClicks(utente.w.view._editor, " lunga")
    utente.attendi()
    valore = next(c.value for c in utente.w.doc.fields() if c.xref == f.xref)
    assert valore == "Prova lunga", f"nel documento c'è {valore!r}"


# ------------------------------------------------------------- strumenti


@pytest.mark.parametrize("strumento", [
    "select", "hand", "text", "image", "signature", "highlight", "note",
    "rect", "circle", "line", "arrow", "polygon", "ink", "stamp", "link", "redact",
])
def test_selezione_strumento(finestra, strumento: str):
    finestra.show()
    finestra.select_tool(strumento)
    assert finestra.tool == strumento
    assert finestra.view.tool == strumento


def test_il_menu_strumenti_esiste_e_ha_voci(finestra):
    """Il menu del pulsante strumento deve elencare gli strumenti disegnabili."""
    finestra.show()
    bottone = getattr(finestra, "_tool_button", None)
    assert bottone is not None, "manca il pulsante di scelta strumento"
    menu = bottone.menu()
    assert menu is not None
    voci = [a.text() for a in menu.actions() if a.text()]
    for atteso in ("Seleziona", "Mano", "Firma", "Rettangolo", "Freccia"):
        assert atteso in voci, f"«{atteso}» manca dal menu: {voci}"


def test_trascinamento_rettangolo_crea_annotazione(utente: Utente):
    utente.w.select_tool("rect")
    prima = len(utente.w.doc.annots(0, include_widgets=False))
    utente.trascina(0, (60, 620), (260, 700))
    assert len(utente.w.doc.annots(0, include_widgets=False)) == prima + 1
    tipo = utente.w.doc.annots(0, include_widgets=False)[-1]["type"]
    assert tipo == "Square", tipo


def test_trascinamento_freccia_crea_annotazione(utente: Utente):
    utente.w.select_tool("arrow")
    prima = len(utente.w.doc.annots(0, include_widgets=False))
    utente.trascina(0, (60, 620), (260, 700))
    assert len(utente.w.doc.annots(0, include_widgets=False)) == prima + 1


def test_evidenziatore_crea_annotazione(utente: Utente):
    utente.w.select_tool("highlight")
    prima = len(utente.w.doc.annots(0, include_widgets=False))
    utente.trascina(0, (50, 110), (300, 130))
    assert len(utente.w.doc.annots(0, include_widgets=False)) == prima + 1


def test_annullamento_e_ripetizione_dopo_annotazione(utente: Utente):
    utente.w.select_tool("rect")
    prima = len(utente.w.doc.annots(0, include_widgets=False))
    utente.trascina(0, (60, 620), (260, 700))
    utente.w.edit_undo()
    utente.attendi()
    assert len(utente.w.doc.annots(0, include_widgets=False)) == prima
    utente.w.edit_redo()
    utente.attendi()
    assert len(utente.w.doc.annots(0, include_widgets=False)) == prima + 1


# ------------------------------------------------------------ selezione testo


def test_selezione_e_copia_del_testo(utente: Utente):
    from PySide6.QtGui import QGuiApplication

    utente.w.select_tool("select")
    utente.trascina(0, (45, 55), (400, 100))
    testo = utente.w.view.selected_text()
    assert "Relazione" in testo, testo
    assert utente.w.view.copy_selection()
    assert "Relazione" in QGuiApplication.clipboard().text()


def test_seleziona_tutto_e_copia(utente: Utente):
    from PySide6.QtGui import QGuiApplication

    utente.w.view.select_all_text()
    assert utente.w.view.selected_text().strip()
    assert utente.w.view.copy_selection()
    QGuiApplication.clipboard().clear()
    QTest.keyClick(utente.vista_viewport(), Qt.Key_A, Qt.ControlModifier)
    utente.attendi()
    assert utente.w.view.selected_text().strip(), "Ctrl+A non ha selezionato il testo"
    QTest.keyClick(utente.vista_viewport(), Qt.Key_C, Qt.ControlModifier)
    utente.attendi()
    assert "Relazione" in QGuiApplication.clipboard().text()


# ---------------------------------------------------------------- pulsanti


@pytest.mark.parametrize("nome", [
    "Nuovo", "Apri", "Salva", "Salva come", "Stampa", "Cerca", "Firma",
    "Ingrandisci", "Riduci", "Adatta alla pagina", "Ruota a sinistra",
    "Ruota a destra",
])
def test_pulsante_reagisce(finestra, nome: str):
    """Nessun pulsante deve bloccare l'interfaccia.

    Le finestre modali aperte vengono chiuse subito: qui conta che il clic
    arrivi al codice senza errori.
    """
    finestra.show()
    finestra.load_path(str(_documento_modello()))
    for _ in range(6):
        QApplication.instance().processEvents()
    u = Utente(finestra)
    try:
        u.clic_pulsante(nome)
        # nessuna eccezione: il pulsante è semplicemente reattivo
        assert finestra.isEnabled()
    finally:
        u.timer.stop()


def test_ruota_pagina_dalla_barra(utente: Utente):
    prima = utente.w.doc.page_info(0).rotation
    utente.clic_pulsante("Ruota a destra")
    assert utente.w.doc.page_info(0).rotation != prima


def test_apri_e_salva(utente: Utente, tmp_path):
    """Salvare deve scrivere il file e segnarlo come non modificato."""
    import pathlib

    from PySide6.QtWidgets import QFileDialog

    bersaglio = tmp_path / "salvato.pdf"
    originale = QFileDialog.getSaveFileName
    QFileDialog.getSaveFileName = staticmethod(
        lambda *a, **k: (str(bersaglio), "PDF (*.pdf)")
    )
    try:
        utente.w.file_save_as()
        utente.attendi()
    finally:
        QFileDialog.getSaveFileName = originale
    assert bersaglio.exists(), "il file non è stato scritto"
    assert utente.w.doc.dirty is False


# ---------------------------------------------------------------- pannelli


def test_apre_il_pannello_ricerca(utente: Utente):
    utente.w.dock_side.setVisible(True)
    utente.w.edit_find()
    utente.attendi()
    assert utente.w.dock_side.isVisible()
    assert utente.w.tabs.currentWidget() is utente.w.panel_search


def test_ricerca_trova_il_testo(utente: Utente):
    utente.w.panel_search.find.setText("Relazione")
    risultati = utente.w.panel_search.search(utente.w.doc)
    assert len(risultati) >= 1, "la ricerca non ha trovato nulla"
    assert utente.w.panel_search.current_hit() is not None


def test_pannello_campi_elenca_i_campi(utente: Utente):
    utente.w.panel_fields.load(utente.w.doc)
    assert utente.w.panel_fields.table.rowCount() == len(utente.w.doc.fields())


# ------------------------------------------------ strumenti a clic singolo


def test_firma_con_il_clic(utente: Utente, monkeypatch):
    """Lo strumento firma deve inserire la firma dove si clicca.

    La vista manda il punto premuto: se il codice lo tratta come un riquadro
    il clic finiva in un errore e la firma non compariva.
    """
    from pdfeditor.ui.dialogs.signature_dialog import SignatureDialog

    def accetta(self):
        self.tabs.setCurrentIndex(1)
        self.type_text.setText("Mario Rossi")
        for _ in range(3):
            QApplication.processEvents()
        self._accept()
        return SignatureDialog.Accepted

    monkeypatch.setattr(SignatureDialog, "exec", accetta)
    prima = len(utente.w.doc.image_rects(0))
    utente.w.select_tool("signature")
    utente.clic_pagina(0, 60, 600)
    assert len(utente.w.doc.image_rects(0)) == prima + 1, "la firma non è stata inserita"


def test_casella_di_testo_con_il_clic(utente: Utente, monkeypatch):
    from pdfeditor.ui.dialogs import props

    def accetta(self):
        self.text.setPlainText("Nota di prova")
        return props.QDialog.Accepted

    monkeypatch.setattr(props.TextBoxDialog, "exec", accetta)
    prima = len(utente.w.doc.text(0))
    utente.w.select_tool("text")
    utente.clic_pagina(0, 60, 620)
    assert len(utente.w.doc.text(0)) > prima, "la casella di testo non è stata inserita"


def test_nota_con_il_clic(utente: Utente, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    monkeypatch.setattr(
        QInputDialog, "getMultiLineText",
        staticmethod(lambda *a, **k: ("Verificare i dati", True)),
    )
    prima = len(utente.w.doc.annots(0, include_widgets=False))
    utente.w.select_tool("note")
    utente.clic_pagina(0, 480, 700)
    annots = utente.w.doc.annots(0, include_widgets=False)
    assert len(annots) == prima + 1, "la nota non è stata inserita"
    assert annots[-1]["type"] == "Text"


def test_timbro_con_il_clic(utente: Utente, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **k: ("Approvato", True))
    )
    prima = len(utente.w.doc.annots(0, include_widgets=False))
    utente.w.select_tool("stamp")
    utente.clic_pagina(0, 60, 650)
    assert len(utente.w.doc.annots(0, include_widgets=False)) == prima + 1, "il timbro non è stato inserito"


def test_campo_di_testo_con_il_clic(utente: Utente, monkeypatch):
    """Con lo strumento «Campo di testo» un semplice clic deve creare il campo."""
    from pdfeditor.ui.dialogs import props

    class Accettato:
        def __init__(self, parent=None, tipo="text"):
            self._ok = True
            self.tipo = tipo

        def exec(self):
            return props.QDialog.Accepted

        def values(self):
            return {
                "name": "nuovo_campo", "value": "testo", "fontsize": 11,
                "font": "Helv", "color": (0, 0, 0), "options": [],
                "tooltip": "", "required": False, "read_only": False,
                "multiline": False, "password": False, "button_caption": "",
                "choice_editable": False,
            }

    monkeypatch.setattr(props, "NewFieldDialog", Accettato, raising=False)
    prima = len(utente.w.doc.fields())
    utente.w.select_tool("field_text")
    utente.clic_pagina(0, 60, 700)
    assert len(utente.w.doc.fields()) == prima + 1, "il campo non è stato creato"


# ------------------------------------------------------------- scorciatoie


def test_i_menu_contengono_tutte_le_voci(finestra):
    """Se le azioni dei menu vengono raccolte, i menu si svuotano.

    È successo davvero: File, Modifica e Visualizza risultavano senza
    quasi nessuna voce, e le scorciatoie non esistevano.
    """
    import gc

    finestra.show()
    gc.collect()
    attesi = {
        "&File": "Nuovo",
        "&Modifica": "Annulla",
        "&Visualizza": "Adatta alla larghezza",
        "&Annota": "Evidenzia",
        "&Moduli": "Campo di testo",
        "&Pagine": "Ruota a destra",
        "&Firma": "Inserisci firma…",
        "&Strumenti": "OCR (riconosci testo)…",
    }
    for titolo, voce in attesi.items():
        menu = next(
            (m.menu() for m in finestra.menuBar().actions() if m.text() == titolo and m.menu()),
            None,
        )
        assert menu is not None, f"menu {titolo} non trovato"
        voci = [a.text() for a in menu.actions() if not a.isSeparator()]
        assert voce in voci, f"«{voce}» manca da {titolo}: {voci}"


def test_le_scorciatoie_dello_zoom_funzionano(finestra):
    for _ in range(4):
        QApplication.instance().processEvents()
    assert finestra.view.zoom() > 0
    QTest.keyClick(finestra, Qt.Key_2, Qt.ControlModifier)
    for _ in range(4):
        QApplication.instance().processEvents()
    assert finestra.lbl_zoom.text() == "100%", finestra.lbl_zoom.text()
    QTest.keyClick(finestra, Qt.Key_0, Qt.ControlModifier)
    for _ in range(4):
        QApplication.instance().processEvents()
    assert finestra.view._zoom_mode == "fit_page"
    QTest.keyClick(finestra, Qt.Key_1, Qt.ControlModifier)
    for _ in range(4):
        QApplication.instance().processEvents()
    assert finestra.view._zoom_mode == "fit_width"


# --------------------------------------------- allineamento e coordinate


@pytest.mark.parametrize("zoom", [0.5, 1.0, 1.75, 3.0])
def test_l_editor_copre_il_riquadro_del_campo(utente: Utente, zoom):
    """L'editor deve cadere esattamente sul riquadro azzurro del campo.

    Le coordinate di scena sono gia' in punti: la scala la fa la
    trasformazione della vista. Se anche il codice moltiplica per lo zoom,
    l'editor finisce altrove e a 200% era finito a y=724 su un campo a y=381.
    """
    campo = utente.campo("nome")
    utente.w.view.set_zoom(zoom, mode="custom")
    utente.attendi()
    utente.w.view.begin_field_edit(0, campo.xref)
    utente.attendi()
    assert utente.w.view._editor is not None, "l'editor non si e' aperto"
    atteso = utente.w.view.field_rect_viewport(0, campo.xref)
    assert utente.w.view._editor.geometry() == atteso, (
        f"l'editor e' a {utente.w.view._editor.geometry()}, il campo e' a {atteso}"
    )


@pytest.mark.parametrize("zoom", [0.6, 1.0, 2.0])
def test_il_trascinamento_rispetta_le_coordinate_a_ogni_zoom(utente: Utente, zoom):
    """Un riquadro disegnato da (100,100) a (200,150) deve finire li'.

    Con lo zoom applicato due volte, a 200% il riquadro finiva a meta' del
    punto e della dimensione previsti.
    """
    utente.w.view.set_zoom(zoom, mode="custom")
    utente.attendi()
    utente.w.select_tool("rect")
    utente.trascina(0, (100, 100), (200, 150))
    quadrati = [a for a in utente.w.doc.annots(0, include_widgets=False) if a["type"] == "Square"]
    assert quadrati, "il riquadro non e' stato creato"
    r = quadrati[-1]["rect"]
    for ottenuto, voluto, nome in (
        (r.x0, 100, "x0"), (r.y0, 100, "y0"),
        (r.x1, 200, "x1"), (r.y1, 150, "y1"),
    ):
        assert abs(ottenuto - voluto) <= 2, f"{nome}: {ottenuto} invece di {voluto} (zoom {zoom})"


@pytest.mark.parametrize("zoom", [0.6, 1.0, 2.0])
def test_il_clic_su_un_campo_funziona_a_ogni_zoom(utente: Utente, zoom):
    utente.w.view.set_zoom(zoom, mode="custom")
    utente.attendi()
    utente.w.select_tool("select")
    dentro = utente.w.view.field_at(0, utente.punto_scena(0, 100, 184))
    fuori = utente.w.view.field_at(0, utente.punto_scena(0, 100, 400))
    assert dentro == (0, utente.campo("nome").xref), f"zoom {zoom}: il campo non e' stato trovato"
    assert fuori is None, f"zoom {zoom}: ha trovato un campo dove non c'e'"


def test_l_editor_segue_la_pagina_che_scorre(utente: Utente):
    """Scorrendo, l'editor deve seguire il campo."""
    campo = utente.campo("nome")
    utente.w.view.set_zoom(2.0, mode="custom")
    utente.attendi()
    utente.w.view.begin_field_edit(0, campo.xref)
    utente.attendi()
    barra = utente.w.view.verticalScrollBar()
    barra.setValue(barra.value() + 150)
    utente.attendi()
    assert utente.w.view._editor.geometry() == utente.w.view.field_rect_viewport(0, campo.xref), (
        "l'editor e' rimasto fermo mentre la pagina scorreva"
    )


def test_l_editor_segue_il_cambio_di_zoom(utente: Utente):
    campo = utente.campo("nome")
    utente.w.view.set_zoom(1.0, mode="custom")
    utente.attendi()
    utente.w.view.begin_field_edit(0, campo.xref)
    utente.attendi()
    utente.w.view.set_zoom(2.0, mode="custom")
    utente.attendi()
    assert utente.w.view._editor.geometry() == utente.w.view.field_rect_viewport(0, campo.xref), (
        "l'editor non si e' riadattato al nuovo zoom"
    )


def test_l_editor_si_chiude_se_il_campo_esce_dalla_vista(utente: Utente):
    campo = utente.campo("nome")
    for _ in range(4):
        utente.w.view.zoom_in()
    utente.attendi()
    utente.w.view.begin_field_edit(0, campo.xref)
    utente.attendi()
    barra = utente.w.view.verticalScrollBar()
    barra.setValue(barra.maximum())
    utente.attendi()
    assert utente.w.view._editor is None, "l'editor resterebbe appeso fuori dalla vista"
    assert utente.w.view.active_field is None


def test_la_selezione_del_testo_e_corretta_a_ogni_zoom(utente: Utente):
    for zoom in (0.6, 1.0, 2.0):
        utente.w.view.set_zoom(zoom, mode="custom")
        utente.attendi()
        utente.w.select_tool("select")
        utente.trascina(0, (50, 110), (520, 150))
        assert "Testo da modificare qui" in utente.w.view.selected_text(), (
            f"zoom {zoom}: selezione sbagliata ({utente.w.view.selected_text()!r})"
        )
        utente.w.view.clear_text_selection()


# --------------------------------------- spostare e ridimensionare elementi


def test_spostare_un_elemento_col_trascinamento(utente: Utente):
    """Clic su un'annotazione e trascinamento: prima crashava.

    Il rettangolo di partenza veniva passato a QRectF, che non accetta un
    Rect di PyMuPDF: PySide6 sollevava un TypeError e l'annotazione non era
    piu' spostabile.
    """
    import pymupdf

    utente.w.doc.add_annot(0, "rect", pymupdf.Rect(100, 600, 200, 650), color=(1, 0, 0))
    utente.attendi()
    prima = [a["rect"] for a in utente.w.doc.annots(0, include_widgets=False)
             if a["type"] == "Square"][-1]
    utente.w.select_tool("select")
    utente.trascina(0, (150, 625), (210, 665))
    dopo = [a["rect"] for a in utente.w.doc.annots(0, include_widgets=False)
            if a["type"] == "Square"][-1]
    # l'annotazione ha un bordo, quindi del rettangolo si verifica lo spostamento
    for adesso, prima_, voluto, nome in (
        (dopo.x0, prima.x0, 60, "x0"), (dopo.y0, prima.y0, 40, "y0"),
    ):
        assert abs((adesso - prima_) - voluto) <= 2, (
            f"{nome}: si e' spostata di {adesso - prima_} invece di {voluto}"
        )


def test_ridimensionare_un_elemento_dalle_maniglie(utente: Utente):
    """Le maniglie devono ridimensionare davvero.

    La selezione veniva cercata dentro lo stato del trascinamento, che viene
    azzerato al rilascio del mouse: la maniglia non trovava nulla e il
    ridimensionamento non partiva.
    """
    import pymupdf

    utente.w.doc.add_annot(0, "rect", pymupdf.Rect(100, 600, 200, 650), color=(1, 0, 0))
    utente.attendi()
    utente.w.select_tool("select")
    utente.clic_pagina(0, 150, 625)
    vista = utente.w.view
    zona = next((r, n) for r, n in vista.scene_obj.selection.zones if n == "se")
    cx, cy = zona[0].x() + 4, zona[0].y() + 4
    utente.trascina(0, (cx, cy), (cx + 60, cy + 40))
    rettangoli = [a["rect"] for a in utente.w.doc.annots(0, include_widgets=False)
                  if a["type"] == "Square"]
    r = rettangoli[-1]
    assert abs(r.x1 - 260) <= 3 and abs(r.y1 - 690) <= 3, f"ridimensionata in {r}"


def test_spostare_un_campo_modulo(utente: Utente):
    """I campi devono potersi spostare col mouse.

    Il clic normale apre l'editor, quindi si tiene premuto Alt: prima di
    questo ramo usciva subito e il campo non era mai spostabile.

    Il magnetismo resta spento qui: con la griglia agganciata il campo
    finirebbe addosso a un'altra annotazione e il test misurerebbe lo
    scarto, non lo spostamento. Lo aggancio ha una verifica sua.
    """
    utente.w.view.set_snap(False)
    campo = utente.campo("nome")
    prima = campo.rect
    utente.w.select_tool("select")
    # il puntatore viaggia in pixel interi e la vista li traduce in punti PDF: si
    # misura dove il puntatore arriva davvero e si chiede che il campo lo segua
    # esattamente li. Confrontare con 60 punti fissi voleva dire che la prova
    # dipendeva da quanti pixel vale un punto, che cambia da macchina a
    # macchina: su quella del CI un pixel valeva qualche punto e il campo era
    # stato spostato correttamente di 55,9.
    inizio = utente.punto_pagina(0, 100, 184)
    fine = utente.punto_pagina(0, 160, 224)
    atteso = utente.punti_sotto_pixel(0, fine) - utente.punti_sotto_pixel(0, inizio)
    assert atteso.x() > 40 and atteso.y() > 25, f"trascinamento troppo piccolo: {atteso}"
    utente.trascina(0, (100, 184), (160, 224), mods=Qt.AltModifier)
    nuovo = next(c.rect for c in utente.w.doc.fields() if c.xref == campo.xref)
    margine = utente.margine_di_un_pixel()
    zoom = utente.w.view.transform().m11()
    assert abs((nuovo.x0 - prima.x0) - atteso.x()) <= margine, (
        f"x: spostato di {nuovo.x0 - prima.x0}, attesi {atteso.x()} "
        f"(pixel {inizio.x()},{inizio.y()} -> {fine.x()},{fine.y()}, zoom {zoom:.4f})"
    )
    assert abs((nuovo.y0 - prima.y0) - atteso.y()) <= margine, (
        f"y: spostato di {nuovo.y0 - prima.y0}, attesi {atteso.y()} (zoom {zoom:.4f})"
    )


def _pagina_per_il_magnetismo(utente: Utente) -> int:
    """Una pagina vuota tutta per il test del magnetismo.

    Serve perche' il documento modello ha testo, campi e un'immagine: con
    quelli in mezzo il riquadro trascinato puo' agganciarsi a un campo
    qualsiasi e il test misurerebbe il caso fortuito, non quello voluto.
    """
    utente.w.doc.insert_page(0)
    utente.attendi()
    return 0


def _aggiungi_riquadro(utente: Utente, pagina: int, rect) -> int:
    """Un rettangolo sulla pagina, e il suo xref.

    L'xref serve perche' ``annots()`` non ha un ordine stabile: scegliere
    "l'ultimo" faceva misurare il rettangolo sbagliato, e il test passava o
    falliva a seconda dell'ordine in cui MuPDF li restituisce.
    """
    noti = {a["xref"] for a in utente.w.doc.annots(pagina)}
    utente.w.doc.add_annot(pagina, "rect", rect, color=(1, 0, 0))
    nuovi = [a["xref"] for a in utente.w.doc.annots(pagina) if a["xref"] not in noti]
    assert len(nuovi) == 1, f"aggiunti {len(nuovi)} rettangoli invece di uno"
    return nuovi[0]


def test_il_magnetismo_aggancia_il_bordo(utente: Utente):
    """Col magnetismo attivo l'elemento deve agganciarsi al bordo di un altro.

    Prima il magnetismo era calcolato e subito sovrascritto: nessuno snap
    visibile e nessuno salvato, quindi l'opzione non faceva nulla. Qui si
    trascina un elemento a due punti dal bordo di un altro e si verifica che
    atterri sul bordo esatto, non li' vicino.
    """
    import pymupdf

    pagina = _pagina_per_il_magnetismo(utente)
    vista = utente.w.view
    vista.set_snap(True, guides=True)
    # il fermo: bordo sinistro a x=350, lontano dal centro pagina perche' il
    # magnetismo aggancia anche ai bordi e al centro della pagina
    _aggiungi_riquadro(utente, pagina, pymupdf.Rect(350, 600, 450, 660))
    # quello che si trascina parte da x0=100 e si rilascia a x0=348
    xref = _aggiungi_riquadro(utente, pagina, pymupdf.Rect(100, 600, 200, 660))
    utente.attendi()
    utente.w.select_tool("select")
    utente.clic_pagina(pagina, 150, 630)
    assert vista.selection_kind() == "annot", "l'annotazione non e' stata selezionata"
    utente.trascina(pagina, (150, 630), (398, 630))
    r = utente.w.doc.annot_rect(pagina, xref)
    # il rettangolo chiesto era 100..200 ma PyMuPDF lo scrive con il bordo
    # dentro, quindi parte da 99 e il trascinamento di 248 punti lo porta a
    # 347: il magnetismo deve tirarlo al bordo del fermo, a 350
    assert abs(r.x0 - 350) <= 1.0, f"agganciato a x0={r.x0}, attesi 350"
    assert abs(r.width - 102) <= 0.5, f"larghezza cambiata: {r.width}, attesa 102"


def test_il_magnetismo_spento_segue_il_mouse(utente: Utente):
    """Senza magnetismo il riquadro deve restare dove lo lascia il mouse."""
    import pymupdf

    pagina = _pagina_per_il_magnetismo(utente)
    _aggiungi_riquadro(utente, pagina, pymupdf.Rect(350, 600, 450, 660))
    xref = _aggiungi_riquadro(utente, pagina, pymupdf.Rect(100, 600, 200, 660))
    utente.attendi()
    utente.w.view.set_snap(False)
    utente.w.select_tool("select")
    utente.clic_pagina(pagina, 150, 630)
    utente.trascina(pagina, (150, 630), (398, 630))
    r = utente.w.doc.annot_rect(pagina, xref)
    assert abs(r.x0 - 347) <= 1.0, f"x0={r.x0}, atteso 347: il magnetismo ha agganciato"


def test_ridimensionare_un_campo_modulo(utente: Utente):
    campo = utente.campo("nome")
    utente.w.select_tool("select")
    QTest.mouseClick(utente.vista_viewport(), Qt.LeftButton, Qt.AltModifier,
                     utente.punto_pagina(0, 100, 184))
    utente.attendi()
    vista = utente.w.view
    zona = next((r, n) for r, n in vista.scene_obj.selection.zones if n == "se")
    cx, cy = zona[0].x() + 4, zona[0].y() + 4
    utente.trascina(0, (cx, cy), (cx + 80, cy))
    nuovo = next(c.rect for c in utente.w.doc.fields() if c.xref == campo.xref)
    assert abs(nuovo.x1 - 400) <= 3, f"campo ridimensionato in {nuovo}"


def test_le_maniglie_della_selezione_si_disegnano(utente: Utente):
    """Le maniglie non devono fallire durante il disegno.

    I loro colori stanno in Metrics: letti dalla palette il disegno sollevava
    AttributeError a ogni passaggio e la selezione restava senza maniglie.
    """
    import pymupdf

    utente.w.doc.add_annot(0, "rect", pymupdf.Rect(100, 600, 200, 650), color=(1, 0, 0))
    utente.attendi()
    utente.w.select_tool("select")
    utente.clic_pagina(0, 150, 625)
    assert utente.w.view.scene_obj.selection.zones, "nessuna maniglia generata"
    # il disegno avviene davvero: senza errori e con un'immagine non vuota
    immagine = utente.w.view.grab().toImage()
    assert immagine.width() > 0


@pytest.mark.parametrize("zoom", [0.6, 1.0, 1.5])
def test_la_pagina_disegnata_occupa_esattamente_il_suo_riquadro(utente: Utente, zoom):
    """La pagina disegnata deve riempiere il riquadro che le spetta.

    Il pixmap della pagina veniva generato alla scala corrente, ma disegnato
    alla sua dimensione naturale dentro un nodo che misura la pagina in
    punti: finiva più grande del proprio riquadro, con uno scarto che
    cresceva con lo zoom. Immagine della pagina e sovrapposti (campi,
    annotazioni) finivano cosi' su due sistemi di coordinate diversi, e ogni
    campo sembrava sfalsato rispetto al riquadro azzurro.

    Il riferimento e' il bordo bianco della pagina: netto e uguale su ogni
    piattaforma, a differenza di un bordo grigio che si confonde con
    l'antialiasing.
    """
    vista = utente.w.view
    vista.set_zoom(zoom, mode="custom")
    utente.attendi()
    immagine = vista.grab().toImage()
    y = immagine.height() // 2

    def bianco(x: int) -> bool:
        c = immagine.pixelColor(x, y)
        return c.red() > 246 and c.green() > 246 and c.blue() > 246

    bianchi = [x for x in range(immagine.width()) if bianco(x)]
    assert bianchi, "la pagina non si vede"
    atteso = vista.mapFromScene(vista._scene_rect(0, utente.w.doc.page_info(0).rect)).boundingRect()
    margine = 3
    assert abs(min(bianchi) - atteso.x()) <= margine, (
        f"zoom {zoom}: la pagina parte da x={min(bianchi)}, atteso {atteso.x():.0f}"
    )
    assert abs(max(bianchi) - (atteso.x() + atteso.width())) <= margine, (
        f"zoom {zoom}: la pagina finisce a x={max(bianchi)}, "
        f"atteso {atteso.x() + atteso.width():.0f}"
    )


# ------------------------------------------------------------- firma disegnata


def test_firma_disegnata_col_mouse(finestra, monkeypatch):
    """Disegnare una firma a mano e inserirla deve funzionare davvero.

    Il riquadro di disegno accettava nessun tratto: al primo clic lo spacchettava
    male la posizione del puntatore e al primo movimento chiamava un metodo
    dell'evento che in Qt 6 non esiste. Il dialogo si apriva, ma restava vuoto.

    Il dialogo è modale e gira il proprio ciclo di eventi, quindi qui si entra
    dentro e si deve anche uscire: si aspetta che il riquadro sia collocato,
    si traccia tenendo premuto il tasto e, qualunque cosa accada, il dialogo
    viene chiuso. Senza questo la suite restava appesa: «Inserisci» su un
    riquadro vuoto apre un avviso modale, e un avviso che nessuno chiude tiene
    aperto il ciclo di eventi per sempre.
    """
    import time

    from PySide6.QtCore import QPoint, QTimer
    from PySide6.QtWidgets import QDialogButtonBox

    from pdfeditor.ui.dialogs.signature_dialog import SignatureDialog

    finestra.load_path(str(_documento_modello()))
    for _ in range(8):
        QApplication.instance().processEvents()
    prima = len(finestra.doc.image_rects(0))
    esito = {}
    scadenza = time.monotonic() + 20

    def chiudi_quello_che_resta():
        for wid in QApplication.instance().topLevelWidgets():
            if isinstance(wid, QMessageBox) and wid.isVisible():
                wid.close()
            elif isinstance(wid, SignatureDialog) and wid.isVisible():
                wid.reject()

    def pilota():
        if time.monotonic() > scadenza:
            esito["scaduto"] = True
            chiudi_quello_che_resta()
            return
        # un avviso del dialogo è modale a sua volta: chiuderlo o il ciclo di
        # eventi non si chiude
        for wid in QApplication.instance().topLevelWidgets():
            if isinstance(wid, QMessageBox) and wid.isVisible():
                wid.close()
                return
        if esito:  # il tratto è già stato tracciato: non rifarlo
            return
        for wid in QApplication.instance().topLevelWidgets():
            if not isinstance(wid, SignatureDialog) or not wid.isVisible():
                continue
            pad = wid.pad
            if pad.width() < 50 or pad.height() < 50:
                # non ancora collocato: i tratti cadrebbero fuori dal riquadro
                return
            QTest.mousePress(pad, Qt.LeftButton, Qt.NoModifier, QPoint(40, 110))
            for i in range(20):
                # il riquadro continua il tratto finche' il tasto e' premuto:
                # `mouseMove` non accetta i modificatori, ma il riquadro segue
                # la pressione registrata sopra
                QTest.mouseMove(pad, QPoint(40 + i * 24, 110 - 34 * ((i % 8) - 4) / 4))
            QTest.mouseRelease(pad, Qt.LeftButton, Qt.NoModifier, QPoint(500, 110))
            for _ in range(3):
                QApplication.instance().processEvents()
            esito["vuoto"] = pad.is_empty()
            esito["immagine"] = wid.current_image() is not None
            scatola = wid.findChildren(QDialogButtonBox)[0]
            for b in scatola.buttons():
                if b.text() == "Inserisci":
                    b.click()
                    return
            wid.reject()

    timer = QTimer()
    timer.setInterval(50)
    timer.timeout.connect(pilota)
    timer.start()
    try:
        finestra.action_signature()
    finally:
        timer.stop()
    for _ in range(6):
        QApplication.instance().processEvents()

    assert esito, "il riquadro di disegno non è mai diventato pronto"
    assert not esito.get("scaduto"), "il dialogo della firma non si è chiuso"
    assert esito["vuoto"] is False, "il riquadro di disegno non ha registrato il tratto"
    assert esito.get("immagine") is True, "la firma disegnata non ha prodotto un'immagine"
    assert len(finestra.doc.image_rects(0)) == prima + 1, "la firma non è finita nel documento"
    assert "firm" in finestra.lbl_status.text().lower(), finestra.lbl_status.text()


# ------------------------------------------------------------------- menu


def test_ogni_voce_di_menu_reagisce(finestra, monkeypatch):
    """Nessuna voce di menu deve sollevare un errore.

    È il controllo che ha scoperto «Appiattisci annotazioni», che chiamava un
    metodo inexistente e falliva ogni volta.

    «Terze parti» apre l'elenco delle licenze nel browser: qui il browser non
    parte, si registra solo l'indirizzo. Su Windows `os.startfile` su una macchina
    senza browser non ritorna mai, e la verifica restava appesa sei ore prima
    che la piattaforma la spegnesse.
    """
    import webbrowser

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QDialog, QMessageBox

    aperte: list[str] = []

    def annota(url, *_a, **_k):
        aperte.append(url)
        return True

    monkeypatch.setattr(webbrowser, "open", annota)

    # le voci che aprirebbero finestre di sistema o chiuderebbero il programma
    saltate = {
        "Esci", "Stampa", "Salva", "Salva come…", "Apri…", "Inserisci da file…",
        "Inserisci immagine…", "Apri immagine…", "Apri cartella", "Sfoglia…",
    }
    finestra.load_path(str(_documento_modello()))
    for _ in range(8):
        QApplication.instance().processEvents()
    errori: list[str] = []

    def chiudi_modali():
        for wid in QApplication.instance().topLevelWidgets():
            if wid is finestra or not wid.isVisible() or not wid.isModal():
                continue
            if isinstance(wid, (QDialog, QMessageBox)):
                wid.reject()

    timer = QTimer()
    timer.setInterval(40)
    timer.timeout.connect(chiudi_modali)
    timer.start()

    def voci():
        raccolte = []

        def dentro(menu, percorso):
            for a in menu.actions():
                if a.isSeparator():
                    continue
                testo = a.text()
                if a.menu() is not None:
                    dentro(a.menu(), percorso + (testo,))
                else:
                    raccolte.append((percorso, testo))

        for a in finestra.menuBar().actions():
            if a.menu() is not None:
                dentro(a.menu(), (a.text().replace("&", ""),))
        return raccolte

    def trova(percorso, testo):
        menu = finestra.menuBar()
        for nome in percorso:
            azione = next((a for a in menu.actions() if a.text().replace("&", "") == nome), None)
            if azione is None or azione.menu() is None:
                return None
            menu = azione.menu()
        return next((a for a in menu.actions() if a.text() == testo), None)

    for percorso, testo in voci():
        if testo in saltate:
            continue
        azione = trova(percorso, testo)
        if azione is None or not azione.isEnabled():
            continue
        try:
            azione.trigger()
            for _ in range(3):
                QApplication.instance().processEvents()
        except Exception as exc:  # noqa: BLE001
            errori.append(f"{' ▸ '.join(percorso + (testo,))}: {type(exc).__name__}: {exc}")
    timer.stop()
    assert not errori, "voci di menu che falliscono:\n  " + "\n  ".join(errori)
    # la voce delle terze parti deve aver chiesto l'apertura dell'elenco, e non
    # è stato un caso: il browser vero non è mai partito
    assert [u for u in aperte if u.endswith("THIRD-PARTY.md")], (
        f"la voce delle terze parti non ha aperto l'elenco delle licenze: {aperte}"
    )


def test_la_presentazione_si_puo_e_chiudere(finestra):
    """Presentazione entra ed esce, riportando pannelli e barre.

    Prima si entrava ma non si usciva: docks e barre restavano nascosti e la
    vista bloccata su una pagina.
    """
    finestra.load_path(str(_documento_modello()))
    for _ in range(6):
        QApplication.instance().processEvents()
    prima = {
        "pagine": finestra.dock_thumbs.isVisible(),
        "lati": finestra.dock_side.isVisible(),
        "vista": finestra.view.view_mode(),
    }
    finestra.toggle_presentation()
    for _ in range(8):
        QApplication.instance().processEvents()
    assert finestra.view.view_mode() == "single", "la presentazione non imposta una pagina per volta"
    assert not finestra.dock_thumbs.isVisible(), "il pannello pagine dovrebbe sparire"
    finestra.toggle_presentation()
    for _ in range(8):
        QApplication.instance().processEvents()
    assert finestra.view.view_mode() == prima["vista"], "la vista non è tornata come prima"
    assert finestra.dock_thumbs.isVisible() == prima["pagine"], "il pannello pagine non è tornato"
    assert finestra.dock_side.isVisible() == prima["lati"], "i pannelli laterali non sono tornati"


def test_appiattisci_annotazioni_non_fallisce(finestra, monkeypatch):
    """«Appiattisci annotazioni» deve funzionare e toccare solo le annotazioni.

    Chiamava Page.apply_annots, che in PyMuPDF 1.28 non esiste: la voce di menu
    si chiudeva con un AttributeError. E appiattiva anche i campi modulo, che
    sono un'altra voce di menu.
    """
    finestra.load_path(str(_documento_modello()))
    for _ in range(6):
        QApplication.instance().processEvents()

    def annots() -> int:
        return sum(
            len(finestra.doc.annots(i, include_widgets=False))
            for i in range(finestra.doc.page_count)
        )

    campi_prima = len(finestra.doc.fields())
    annots_prima = annots()
    finestra.doc.add_annot(0, "rect", pymupdf.Rect(100, 400, 240, 460))
    annots_prima += 1
    monkeypatch.setattr(finestra, "_confirm", lambda _msg: True)
    finestra.action_flatten_annots()
    for _ in range(6):
        QApplication.instance().processEvents()
    assert len(finestra.doc.fields()) == campi_prima, "i campi devono restare compilabili"
    assert annots() == annots_prima - 1, "le annotazioni vanno appiattite"
    assert "appiatt" in finestra.lbl_status.text().lower(), finestra.lbl_status.text()


def test_i_file_recenti_spariti_vengono_scartati(finestra, tmp_path):
    """Un file recente che non esiste più non deve restare nell'elenco."""
    esistente = tmp_path / "resta.pdf"
    esistente.write_bytes(b"%PDF-1.4\n")
    sparito = str(tmp_path / "non-esiste.pdf")
    finestra.settings.set("recent_files", [str(esistente), sparito])
    voci = finestra.settings.recent_files()
    assert sparito not in voci, "il file sparito è rimasto nell'elenco"
    assert str(esistente) in voci


def _pulsanti_standard(lingua: str) -> list[str]:
    """I pulsanti di Qt dopo aver installato il traduttore della lingua data."""
    from PySide6.QtWidgets import QDialogButtonBox

    from pdfeditor import app as appmod

    appmod._install_translator(QApplication.instance(), lingua)
    scatola = QDialogButtonBox(
        QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        | QDialogButtonBox.Close | QDialogButtonBox.Save
    )
    return [b.text() for b in scatola.buttons()]


def test_i_pulsanti_standard_seguono_la_lingua(finestra):
    """I pulsanti di Qt devono essere nella lingua dell'interfaccia.

    Senza traduttore i dialoghi mostravano pulsanti misti: «Inserisci» in
    italiano accanto a «Cancel». Il traduttore era pero' scritto fisso su
    l'italiano: con l'interfaccia in inglese i pulsanti sarebbero usciti in
    italiano, che e' il mezzo peggio di non tradurli affatto.
    """
    italiano = _pulsanti_standard("it")
    assert "Annulla" in italiano, f"pulsanti non tradotti in italiano: {italiano}"
    assert "Cancel" not in italiano, f"pulsanti in inglese con UI italiana: {italiano}"

    inglese = _pulsanti_standard("en")
    assert "Cancel" in inglese, f"pulsanti non tradotti in inglese: {inglese}"
    assert "Annulla" not in inglese, f"pulsanti in italiano con UI inglese: {inglese}"

    # il pulsante OK e' identico nelle due lingue: serve a verificare che il
    # traduttore non sia stato tolto ma solo cambiato
    assert _pulsanti_standard("it") == italiano
