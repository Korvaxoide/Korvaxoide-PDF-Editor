"""Test dell'interfaccia: pannelli, vista, finestra principale (headless)."""

from __future__ import annotations

import os
from pathlib import Path

import pymupdf
import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from pdfeditor.core import geometry as geo
from pdfeditor.core import settings as sm
from pdfeditor.core.document import Document
from pdfeditor.ui import panels, theme, thumbnails
from pdfeditor.ui.page_view import PdfView

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture()
def documento() -> Document:
    d = Document()
    d.new(595, 842)
    d.insert_text_box(0, pymupdf.Rect(60, 80, 500, 120), "Relazione di prova", fontsize=16)
    d.add_field(0, "text", pymupdf.Rect(60, 200, 400, 228), name="nome", value="Mario Rossi")
    d.add_field(0, "checkbox", pymupdf.Rect(60, 250, 80, 270), name="ok", value=True)
    d.add_field(0, "combo", pymupdf.Rect(60, 290, 250, 312), name="scelta",
                options=["Uno", "Due", "Tre"], value="Due")
    d.add_radio_group(0, [pymupdf.Rect(60, 340, 80, 360), pymupdf.Rect(120, 340, 140, 360)],
                      name="grp", selected=0)
    yield d
    d.close()


def pump(n: int = 3) -> None:
    for _ in range(n):
        QApplication.processEvents()


# ------------------------------------------------------------------- vista


def test_vista_creata(app):
    v = PdfView()
    v.resize(900, 700)
    assert v.page_count() == 0
    assert v.tool == "select"


def test_vista_con_documento(app, documento: Document):
    v = PdfView()
    v.resize(900, 700)
    v.set_document(documento)
    pump()
    assert v.page_count() == 1
    assert v.zoom() > 0


def test_apertura_mostra_la_pagina_intera(app, documento: Document):
    """All'apertura si deve vedere la pagina intera, come in Acrobat.

    Con «adatta alla larghezza» una pagina A4 in verticale dentro una
    finestra larga ne mostrerebbe solo il terzo superiore.
    """
    vista = PdfView()
    vista.set_document(documento)
    vista.resize(1200, 800)
    vista.show()
    for _ in range(4):
        app.processEvents()
    assert vista._zoom_mode == "fit_page"
    info = documento.page_info(0)
    altezza = info.rect.height * vista.zoom()
    assert altezza <= vista.viewport().rect().height() + 1, altezza


def test_zoom(app, documento: Document):
    v = PdfView()
    v.resize(900, 700)
    v.set_document(documento)
    iniziale = v.zoom()
    v.zoom_in()
    assert v.zoom() > iniziale
    v.zoom_out()
    assert v.zoom() < iniziale * 1.3
    v.set_zoom(1.5)
    assert v.zoom() == pytest.approx(1.5)
    v.set_zoom(99.0)
    assert v.zoom() <= 16.0


def test_modalita_visualizzazione(app, documento: Document):
    v = PdfView()
    v.resize(900, 700)
    v.set_document(documento)
    for modo in ("continuous", "single", "continuous"):
        v.set_view_mode(modo)
        pump()
        assert v.view_mode() == modo


def test_griglia_e_campi(app, documento: Document):
    v = PdfView()
    v.resize(900, 700)
    v.set_document(documento)
    assert not v.grid_visible()
    v.set_grid(True, 24.0)
    assert v.grid_visible() and v.grid_size() == 24.0
    assert v.highlight_fields is True
    v.set_highlight_fields(False)
    assert v.highlight_fields is False


def test_strumenti(app, documento: Document):
    v = PdfView()
    v.resize(900, 700)
    v.set_document(documento)
    for t in ("select", "hand", "text", "rect", "ink", "field_text", "redact", "signature"):
        v.set_tool(t)
        assert v.tool == t


def test_stati_campi(app, documento: Document):
    v = PdfView()
    v.resize(900, 700)
    v.set_document(documento)
    assert len(v.field_states) == 6
    nomi = {st["info"].name for st in v.field_states.values()}
    assert {"nome", "ok", "scelta", "grp"} <= nomi


def test_compilazione_campo_testo(app, documento: Document):
    v = PdfView()
    v.resize(900, 700)
    v.set_document(documento)
    ricevuti: list[tuple] = []
    v.field_committed.connect(lambda p, x, val: ricevuti.append((p, x, val)))
    xref = next(x for (p, x), st in v.field_states.items() if st["info"].name == "nome")
    v.begin_field_edit(0, xref)
    pump()
    assert v._editor is not None
    v._editor_commit("Luigi Verdi")
    assert ricevuti and ricevuti[0][2] == "Luigi Verdi"
    v.hide_field_editor()
    assert v._editor is None


def test_casella_di_spunta_al_clic(app, documento: Document):
    v = PdfView()
    v.resize(900, 700)
    v.set_document(documento)
    prima = [f.value for f in documento.fields() if f.name == "ok"][0]
    xref = next(x for (p, x), st in v.field_states.items() if st["info"].name == "ok")
    v.begin_field_edit(0, xref)
    pump()
    dopo = [f.value for f in documento.fields() if f.name == "ok"][0]
    assert dopo != prima


def test_campo_sola_lettura(app):
    d = Document()
    d.new()
    d.add_field(0, "text", pymupdf.Rect(50, 50, 300, 78), name="ro", value="x", read_only=True)
    v = PdfView()
    v.resize(600, 600)
    v.set_document(d)
    xref = next(x for (p, x), st in v.field_states.items() if st["info"].name == "ro")
    v.begin_field_edit(0, xref)
    assert v._editor is None
    d.close()


def test_rendering_headless(app, documento: Document):
    v = PdfView()
    v.resize(800, 900)
    v.set_document(documento)
    v.set_zoom(1.0, "custom")
    pump()
    img = QImage(800, 900, QImage.Format_ARGB32)
    img.fill(0xFFFFFFFF)
    p = QPainter(img)
    v.render(p)
    p.end()
    # la pagina deve occupare una parte significativa del riquadro
    assert img.size().width() == 800
    arr = bytes(img.constBits())[: img.sizeInBytes()]
    assert len(set(arr)) > 5


def test_tema_scuro(app, documento: Document):
    v = PdfView()
    v.resize(600, 600)
    v.set_document(documento)
    v.set_theme(theme.DARK)
    pump()
    v.set_theme(theme.LIGHT)


# -------------------------------------------------------------------- icone


def test_ogni_icona_disegna_qualcosa(app):
    """Nessuna icona puo' risultare vuota.

    Le icone sono disegnate a runtime e l'errore veniva inghiotito: un refuso
    in un enum di Qt faceva sparire del tutto l'icona e in barra c'era un
    quadrato vuoto senza diagnosi. Il caso reale era ``Qt.RashCap``, che non
    esiste, nell'icona dello strumento predefinito.
    """
    from pdfeditor.ui import icons

    vuote = []
    for nome in sorted(icons.DRAWERS):
        img = icons.icon(nome, "#000000", 22).pixmap(22, 22).toImage()
        opachi = [img.pixelColor(x, y).alpha()
                  for y in range(22) for x in range(22)
                  if img.pixelColor(x, y).alpha() > 0]
        if not opachi:
            vuote.append(nome)
    assert not vuote, f"icone disegnate ma vuote: {vuote}"


def test_ogni_icona_prende_il_colore_richiesto(app):
    """L'icona deve essere del colore del tema, altrimenti in barra sparisce."""
    from pdfeditor.ui import icons

    sbagliate = []
    for nome in sorted(icons.DRAWERS):
        scuro = icons.icon(nome, "#101010", 22).pixmap(22, 22).toImage()
        chiaro = icons.icon(nome, "#f0f0f0", 22).pixmap(22, 22).toImage()

        def _media(img):
            px = [img.pixelColor(x, y).red()
                  for y in range(22) for x in range(22)
                  if img.pixelColor(x, y).alpha() > 200]
            return sum(px) / len(px) if px else None

        a, b = _media(scuro), _media(chiaro)
        if a is None or b is None or b < a + 60:
            sbagliate.append(f"{nome} ({a} -> {b})")
    assert not sbagliate, f"icone che non cambiano colore: {sbagliate}"


def test_ogni_azione_della_finestra_ha_un_icona_disegnata(finestra):
    """Le icone realmente usate nei menu e nelle barre non sono vuote."""
    from PySide6.QtGui import QAction

    vuote = []
    for a in finestra.findChildren(QAction):
        if a.icon().isNull():
            continue
        img = a.icon().pixmap(22, 22).toImage()
        if not any(img.pixelColor(x, y).alpha() > 0
                   for y in range(img.height()) for x in range(img.width())):
            vuote.append(a.text() or a.objectName() or "<senza testo>")
    assert not vuote, f"azioni con icona disegnata ma vuota: {vuote}"


# --------------------------------------------------------------- miniature


def test_miniature(app, documento: Document):
    p = thumbnails.ThumbnailsPanel()
    p.resize(300, 700)
    p.set_document(documento)
    pump()
    assert p.list.count() == 1
    item = p.list.item(0)
    assert isinstance(item, thumbnails.PageThumb)
    pm = item.pixmap()
    assert pm is not None and not pm.isNull()
    p.select_pages([0])
    assert p.selected_pages() == [0]


def test_miniature_sincronizzate(app, documento: Document):
    p = thumbnails.ThumbnailsPanel()
    p.set_document(documento)
    documento.insert_page(1)
    p.rebuild()
    assert p.list.count() == 2
    documento.delete_pages([1])
    p.rebuild()
    assert p.list.count() == 1


# ---------------------------------------------------------------- pannelli


def test_pannello_ricerca(app, documento: Document):
    p = panels.SearchPanel()
    p.find.setText("Relazione")
    hits = p.search(documento)
    assert len(hits) == 1
    assert p.results.count() == 1
    p.step(1)
    assert p.current_hit() is not None
    p.find.setText("inesistente")
    assert p.search(documento) == []


def test_pannello_campi(app, documento: Document):
    p = panels.FieldsPanel()
    p.load(documento)
    assert p.table.rowCount() == 6
    p.filter.setCurrentIndex(5)  # campi firma
    assert p.table.rowCount() == 0
    p.filter.setCurrentIndex(1)  # campi di testo
    assert p.table.rowCount() == 1


def test_pannello_segnalibri(app, documento: Document):
    documento.add_bookmark("Uno", 0)
    documento.add_bookmark("Due", 0)
    p = panels.BookmarksPanel()
    p.load(documento)
    assert p.tree.topLevelItemCount() == 2


def test_pannello_allegati(app, documento: Document, tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("dati", encoding="utf-8")
    documento.add_attachment(f)
    p = panels.AttachmentsPanel()
    p.load(documento)
    assert p.list.count() == 1
    assert documento.attachment_bytes("a.txt") == b"dati"


def test_pannello_commenti(app, documento: Document):
    documento.add_annot(0, "note", pymupdf.Rect(50, 400, 72, 422), text="Nota")
    p = panels.CommentsPanel()
    p.load(documento)
    assert len(p.rows) == 1
    assert p.rows[0]["text"] == "Nota"


def test_pannello_proprieta(app, documento: Document):
    documento.set_metadata({"title": "Relazione", "author": "Mario Rossi"})
    p = panels.PropertiesPanel()
    p.load(documento)
    assert p.edits["title"].text() == "Relazione"
    valori: dict = {}
    p.changed.connect(lambda v: valori.update(v))
    p.edits["author"].setText("Luigi")
    p.edits["author"].editingFinished.emit()
    assert valori["author"] == "Luigi"


# ------------------------------------------------------------ finestra principale


# il fixture «finestra» e' in conftest.py, condiviso con test_interazione.py


def test_finestra_avvia(finestra):
    assert finestra.isVisible()
    assert finestra.view is not None
    assert finestra.thumbs is not None
    assert finestra.tabs.count() == 7  # Ricerca, Campi, Segnalibri, Commenti, Allegati, Proprieta, Qualita


def test_finestra_nuovo_documento(finestra):
    finestra.doc.new()
    finestra.view.set_document(finestra.doc)
    finestra._on_pages_changed()
    pump()
    assert finestra.doc.page_count == 1
    assert "Pronto" in finestra.lbl_status.text() or finestra.lbl_status.text()


def test_finestra_apre_file(finestra, tmp_path: Path):
    p = tmp_path / "aperto.pdf"
    finestra.doc.new()
    finestra.doc.insert_text_box(0, pymupdf.Rect(60, 60, 400, 100), "Contenuto", fontsize=12)
    finestra.doc.save(p)
    assert finestra.load_path(str(p))
    pump()
    assert finestra.doc.page_count == 1
    assert "Contenuto" in finestra.doc.text(0)


def test_finestra_strumenti(finestra):
    for t in ("rect", "text", "signature", "field_text", "select"):
        finestra.select_tool(t)
        assert finestra.tool == t and finestra.view.tool == t


def test_finestra_pannelli(finestra):
    finestra._on_pages_changed()
    finestra.dock_side.setVisible(True)
    pump()
    finestra.panel_search.find.setText("Relazione")
    assert finestra.panel_search.search(finestra.doc) == []
    finestra._reload_panels()
    pump()


def test_finestra_tema(finestra):
    iniziale = finestra.pal
    finestra.toggle_theme()
    assert finestra.pal is not iniziale
    finestra.toggle_theme()
    assert finestra.pal is iniziale


def _prepara(finestra):
    """Finestra con una pagina di prova, gia' adattata alla pagina."""
    w = finestra
    w.doc.new(width=595, height=842)
    w.doc.insert_text_box(0, pymupdf.Rect(60, 80, 500, 120), "Relazione di prova", fontsize=16)
    w.doc.add_field(0, "text", pymupdf.Rect(60, 200, 400, 228), name="nome", value="Mario Rossi")
    w.view.set_document(w.doc)
    w._on_pages_changed()
    w.view._zoom_mode = "fit_page"
    w.view.apply_zoom_mode()
    pump()
    return w


def test_salto_alla_ricerca_conserva_lo_zoom(finestra):
    """Andare a un risultato di ricerca centra il riquadro senza cambiare scala."""
    w = _prepara(finestra)
    iniziale = w.view.zoom()

    w.panel_search.find.setText("Relazione")
    assert len(w.panel_search.search(w.doc)) == 1
    w._goto_hit(0, pymupdf.Rect(60, 80, 180, 100))
    pump()
    assert w.view.zoom() == pytest.approx(iniziale)
    assert w.view.zoom() < 2.0, "il salto a un risultato non deve ingrandire la pagina"


def test_salto_al_campo_conserva_lo_zoom(finestra):
    w = _prepara(finestra)
    iniziale = w.view.zoom()

    campo = w.doc.fields()[0]
    w._goto_field(campo.page, campo.xref)
    pump()
    assert w.view.zoom() == pytest.approx(iniziale)


def test_pannello_segnalibri_rinomina(finestra, documento: Document):
    """La rinomina inline deve arrivare al documento, non andare persa."""
    w = finestra
    w.doc.new(width=595, height=842)
    w.doc.add_bookmark("Prima parte", 0)
    w.doc.add_bookmark("Capitolo uno", 0)
    w.view.set_document(w.doc)
    w._on_pages_changed()
    w.panel_bookmarks.load(w.doc)
    pump()
    p = w.panel_bookmarks
    assert p.tree.topLevelItemCount() == 2

    p.tree.topLevelItem(1).setText(0, "Capitolo 1")
    pump()
    titoli = [e["title"] for e in w.doc.outline()]
    assert "Capitolo 1" in titoli, titoli
    # il pannello si ricarica con il titolo nuovo
    assert p.tree.topLevelItem(1).text(0) == "Capitolo 1"


def test_pannello_segnalibri_sposta(finestra, documento: Document):
    w = finestra
    w.doc.new(width=595, height=842)
    w.doc.insert_page(1)
    w.doc.add_bookmark("Prima parte", 0)
    w.view.set_document(w.doc)
    w._on_pages_changed()
    w.panel_bookmarks.load(w.doc)
    pump()
    w.view.go_to_page(1)
    pump()
    w.panel_bookmarks.tree.setCurrentItem(w.panel_bookmarks.tree.topLevelItem(0))
    w.panel_bookmarks._move()
    pump()
    assert w.doc.outline()[0]["page"] == 1


# ------------------------------------------------------- requisiti di licenza


def test_licenza_dichiarata_come_agpl():
    """La licenza segue PyMuPDF: AGPL-3.0, non una permissiva."""
    import pdfeditor

    assert pdfeditor.__license__ == "AGPL-3.0-or-later"
    assert pdfeditor.__repo_url__.startswith("https://")


def test_la_versione_e_un_numero_di_versione():
    """La versione deve essere leggibile come versione, non come testo libero.

    Da ``__version__`` dipendono il nome dell'AppImage, il nome dell'eseguibile
    Windows, la versione nel pacchetto macOS e quella delle informazioni sul
    programma: una virgola o uno spazio qui finiscono in un nome di file che
    nessuno riesce piu' a ordinare.
    """
    import re

    import pdfeditor

    assert re.fullmatch(r"\d+\.\d+\.\d+", pdfeditor.__version__), (
        f"versione malformata: {pdfeditor.__version__!r}"
    )


def test_la_versione_e_unica_e_lettura_da_un_solo_posto():
    """Gli script di compilazione prendono la versione dal pacchetto.

    Se il numero compare anche in ``build_linux.sh`` o in ``KorvaxoidePDF.spec``, le
    due copie vanno tenute d'accordo a mano e prima o poi divergono.
    """
    from pathlib import Path

    import pdfeditor

    radice = Path(pdfeditor.__file__).resolve().parents[1]
    numero = pdfeditor.__version__
    for nome in ("build_linux.sh", "KorvaxoidePDF.spec", "build_windows.ps1"):
        testo = (radice / nome).read_text(encoding="utf-8")
        assert numero not in testo, (
            f"{nome} contiene il numero di versione: deve leggerlo dal pacchetto"
        )


def test_finestra_informazioni_mostra_le_avvertenze_legali(finestra, monkeypatch):
    """La finestra dice sotto quale licenza il programma e' distribuito.

    Non si mette un avviso di copyright: l'autore non ha registrato il nome e
    non intende rivendicarlo. L'AGPL non obbliga a mostrarne uno, e non
    rinuncia con questo a nessun diritto: la licenza dichiarata qui e nel
    file LICENSE resta valida per chi riceve il programma.
    """
    from PySide6.QtWidgets import QMessageBox

    catturato: dict[str, str] = {}
    monkeypatch.setattr(
        QMessageBox, "about",
        staticmethod(lambda parent, title, text: catturato.update(titolo=title, corpo=text)),
    )
    finestra.action_about()
    testo = catturato["corpo"]
    # toglie i tag HTML per confrontare il testo
    import re

    piano = re.sub(r"<[^>]+>", "", testo)
    assert "Affero" in piano, "la licenza va detta in questa finestra"
    assert "Nessuna garanzia" in piano
    assert "gnu.org/licenses" in testo, "serve il collegamento al testo della licenza"
    assert "Copyright" not in piano, "l'avviso di copyright è stato tolto"


def test_la_licenza_agpl_e_sempre_quello_del_programma():
    """Togliere l'avviso di copyright non deve cambiare la licenza.

    Il nome non e' registrato, ma il programma resta AGPL-3.0: e' la condizione
    con cui viene distribuito e con cui puo' essere usato, modificato e
    ridistribuito. Se un domani la licenza cambiasse, il file LICENSE e questa
    finestra dovrebbero dirlo insieme.
    """
    import pdfeditor
    from pathlib import Path

    assert pdfeditor.__license__ == "AGPL-3.0-or-later"
    root = Path(__file__).resolve().parents[1]
    testo_licenza = (root / "LICENSE").read_text(encoding="utf-8")
    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in testo_licenza


def test_esiste_il_file_di_licenza():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    testo = (root / "LICENSE").read_text(encoding="utf-8")
    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in testo
    assert "Version 3, 19 November 2007" in testo
    # il testo non deve essere stato abbreviato: le sezioni devono esserci tutte
    assert "END OF TERMS AND CONDITIONS" in testo
    for sezione in range(14):
        assert f"\n  {sezione}. " in testo, f"manca la sezione {sezione}"


def test_esiste_l_elenco_delle_licenze_di_terze_parti():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    testo = (root / "THIRD-PARTY.md").read_text(encoding="utf-8")
    # ogni dipendenza di requirements.txt deve comparire con la sua licenza
    for pacchetto in ("PyMuPDF", "PySide6", "Pillow", "NumPy", "cryptography",
                      "asn1crypto"):
        assert pacchetto in testo, f"{pacchetto} non compare in THIRD-PARTY.md"
    assert "AGPL-3.0" in testo
    assert "PyInstaller" in testo


# ------------------------------------------------------------------ PDF/A


def test_livello_pdfa_estratto_correttamente():
    """«2b» deve diventare «2»: per Ghostscript e per i metadati XMP."""
    from pdfeditor.ui.printing import _pdfa_conformance, _pdfa_part

    assert _pdfa_part("1b") == "1"
    assert _pdfa_part("2b") == "2"
    assert _pdfa_part("3b") == "3"
    assert _pdfa_part("2") == "2"
    # un livello sconosciuto non deve produrre «b» nel flag di Ghostscript
    assert _pdfa_part("2b").isdigit()
    assert _pdfa_conformance("2b").upper() == "B"


def test_xmp_dichiara_il_livello_corretto():
    from pdfeditor.ui.printing import _xmp

    xmp = _xmp("2b")
    assert "<pdfaid:part>2</pdfaid:part>" in xmp
    assert "<pdfaid:conformance>B</pdfaid:conformance>" in xmp
    # il vecchio difetto scriveva «b» come parte
    assert "<pdfaid:part>b<" not in xmp


def test_conversione_pdfa(app, documento: Document, tmp_path: Path):
    from pdfeditor.ui import printing

    if printing.find_ghostscript() is None:
        pytest.skip("Ghostscript non è installato")
    out = tmp_path / "archiviazione.pdf"
    ok, msg = printing.convert_pdfa(documento, str(out), None, "2b")
    assert ok, msg
    assert out.exists()
    import re

    xmp = pymupdf.open(str(out)).get_xml_metadata() or ""
    assert re.search(r"pdfaid:part>2<", xmp), xmp[:200]
    assert "Relazione di prova" in pymupdf.open(str(out))[0].get_text()
    # nessun file temporaneo lasciato accanto
    assert not list(tmp_path.glob("*_meta.pdf"))


def test_conversione_pdfa_tutti_i_livelli(app, documento: Document, tmp_path: Path):
    from pdfeditor.ui import printing

    if printing.find_ghostscript() is None:
        pytest.skip("Ghostscript non è installato")
    for livello, parte in (("1b", "1"), ("2b", "2"), ("3b", "3")):
        out = tmp_path / f"a_{livello}.pdf"
        ok, msg = printing.convert_pdfa(documento, str(out), None, livello)
        assert ok, f"{livello}: {msg}"
        import re

        xmp = pymupdf.open(str(out)).get_xml_metadata() or ""
        assert re.search(rf"pdfaid:part>{parte}<", xmp), f"{livello}: XMP {xmp[:200]}"


def test_ocr_disponibile_su_questo_sistema():
    """Tesseract è opzionale: se c'è, l'OCR deve risultare utilizzabile."""
    from pdfeditor.ui import ocr

    if ocr.find_tesseract() is None:
        pytest.skip("Tesseract non è installato")
    assert ocr.is_available()
    assert ocr.version()


# ------------------------------------------------------------ divisione


def test_la_divisione_per_segnalibri_non_perde_le_pagine_iniziali():
    """Il primo segnalibro non e' l'inizio del documento.

    La divisione partiva dal primo segnalibro, quindi con un segnalibro a
    pagina 5 le pagine da 0 a 4 non finivano in nessun file: la perdita era
    silenziosa, il programma diceva solo «documento diviso».
    """
    from pdfeditor.ui.main_window import confini_di_divisione

    for segnalibri, atteso in (
        ([5], [0, 5]),
        ([5, 9], [0, 5, 9]),
        ([0, 5], [0, 5]),          # un segnalibro sulla prima pagina
        ([5, 5, 9], [0, 5, 9]),    # duplicati: un pezzo solo
        ([9, 5], [0, 5, 9]),       # segnalibri disordinati
        ([], [0]),                      # nessun segnalibro: un pezzo solo
    ):
        assert confini_di_divisione(10, segnalibri) == atteso, f"segnalibri {segnalibri}"


def test_la_divisione_per_blocchi_ricopre_ogni_pagina_una_volta():
    """Ogni pagina deve finire in esattamente un pezzo."""
    from pdfeditor.ui.main_window import confini_di_divisione

    for pagine, ogni in ((10, 3), (10, 1), (10, 25), (1, 1), (7, 2)):
        confini = confini_di_divisione(pagine, ogni=ogni)
        coperte = []
        for n, inizio in enumerate(confini):
            fine = confini[n + 1] if n + 1 < len(confini) else pagine
            coperte.extend(range(inizio, fine))
        assert coperte == list(range(pagine)), (
            f"{pagine} pagine ogni {ogni}: coperte {coperte}, perdute "
            f"{sorted(set(range(pagine)) - set(coperte))}, doppioni "
            f"{sorted({p for p in coperte if coperte.count(p) > 1})}"
        )


def test_la_divisione_per_segnalibri_ricopre_ogni_pagina_una_volta():
    """Come sopra, ma con i segnalibri come confini."""
    from pdfeditor.ui.main_window import confini_di_divisione

    for pagine, segnalibri in ((10, [5]), (10, [3, 7]), (10, [1, 2, 3, 4]), (4, [3])):
        confini = confini_di_divisione(pagine, segnalibri)
        coperte = []
        for n, inizio in enumerate(confini):
            fine = confini[n + 1] if n + 1 < len(confini) else pagine
            coperte.extend(range(inizio, fine))
        assert coperte == list(range(pagine)), (
            f"{pagine} pagine, segnalibri {segnalibri}: coperte {coperte}"
        )
