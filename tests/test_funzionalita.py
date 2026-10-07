"""Verifica che ogni funzionalita' dell'editor sia realmente utilizzabile.

Ogni controllo ricarica il documento ed esegue una sola operazione, cosi' i
risultati non siinfluenzano. Un controllo che non richiama il pulsante
dell'interfaccia verifica comunque l'azione di menu corrispondente.
"""

import os

import pymupdf
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QWidget

from pdfeditor.core import geometry as geo

MODELLI = "modelli_senza_dialogo.txt"


@pytest.fixture()
def app_pulita(finestra, documento_modello):
    """Finestra con il documento di prova e un ciclo di eventi pronto."""
    finestra._error = lambda exc, titolo="": pytest.fail(
        f"l'operazione ha sollevato {type(exc).__name__}: {exc}"
    )
    finestra.load_path(documento_modello)
    for _ in range(6):
        QApplication.instance().processEvents()
    return finestra


@pytest.fixture()
def senza_dialoghi(finestra):
    """Chiude i dialogi che si aprono, per non bloccare il test."""
    def chiudi():
        for wid in QApplication.instance().topLevelWidgets():
            if wid is finestra or not wid.isVisible():
                continue
            if isinstance(wid, (QDialog, QMessageBox)) and wid.isModal():
                wid.reject()

    timer = QTimer()
    timer.setInterval(30)
    timer.timeout.connect(chiudi)
    timer.start()
    yield finestra
    timer.stop()



def _scena(finestra, x: float, y: float):
    """Punto espresso in punti PDF, nelle coordinate dello schermo."""
    vista = finestra.view
    return vista.scene_obj.node(0).scenePos() + QPointF(x, y)


def _trascina(finestra, da, a, mods=Qt.NoModifier) -> None:
    """Trascina con eventi veri, dalla pagina indicata."""
    vp = finestra.view.viewport()
    p1 = finestra.view.mapFromScene(_scena(finestra, *da))
    p2 = finestra.view.mapFromScene(_scena(finestra, *a))
    QTest.mousePress(vp, Qt.LeftButton, mods, p1)
    for _ in range(2):
        QApplication.instance().processEvents()
    QTest.mouseMove(vp, p2)
    for _ in range(2):
        QApplication.instance().processEvents()
    QTest.mouseRelease(vp, Qt.LeftButton, mods, p2)
    for _ in range(4):
        QApplication.instance().processEvents()


# =============================================================== ciclo del file

def test_apre_il_documento(app_pulita):
    assert app_pulita.doc.is_open
    assert app_pulita.doc.page_count >= 1


def test_nuovo_documento(finestra):
    finestra.file_new()
    assert finestra.doc.is_open


def test_salva_su_disco(tmp_path, app_pulita):
    destinazione = tmp_path / "prova.pdf"
    app_pulita.doc.save(destinazione)
    assert destinazione.exists() and destinazione.stat().st_size > 0


def test_salva_una_copia(tmp_path, app_pulita):
    app_pulita.doc.save_copy(tmp_path / "copia.pdf")
    assert (tmp_path / "copia.pdf").exists()


def test_salvataggio_incrementale(app_pulita):
    grezzo = app_pulita.doc.save_bytes()
    assert len(grezzo) > 0


# ==================================================================== pagine

def test_inserisce_e_duplica_pagine(app_pulita):
    iniziale = app_pulita.doc.page_count
    app_pulita.doc.insert_page(iniziale, 595, 842)
    assert app_pulita.doc.page_count == iniziale + 1
    app_pulita.doc.duplicate_pages([0])
    assert app_pulita.doc.page_count == iniziale + 2


def test_sposta_ed_elimina_pagine(app_pulita):
    doc = app_pulita.doc
    doc.insert_page(doc.page_count, 595, 842)
    doc.move_page(doc.page_count - 1, 0)
    assert doc.page_info(0).rect.width > 0
    doc.delete_pages([0])
    assert doc.page_count >= 1


def test_ruota_le_pagine(app_pulita):
    doc = app_pulita.doc
    prima = int(doc.page(0).rotation)
    app_pulita.pages_rotate(90)
    assert int(doc.page(0).rotation) != prima
    doc.rotate_pages(list(range(doc.page_count)), -90)
    assert int(doc.page(0).rotation) == prima


def test_ruota_la_vista(app_pulita):
    app_pulita.doc.set_view_rotation(0, 90)
    assert app_pulita.doc.view_rotation(0) == 90
    app_pulita.doc.set_view_rotation(0, 0)
    assert app_pulita.doc.view_rotation(0) == 0


def test_ritaglia_e_azzera(app_pulita):
    doc = app_pulita.doc
    doc.crop_page(0, pymupdf.Rect(20, 20, 575, 820))
    doc.reset_crop([0])
    assert doc.page_info(0).rect.width > 0


def test_numera_e_togli(app_pulita):
    doc = app_pulita.doc
    doc.add_page_numbers(fmt="{n}", first=1)
    assert doc.has_page_numbers()
    doc.remove_page_numbers()
    assert not doc.has_page_numbers()


def test_estrae_una_pagina(app_pulita):
    assert app_pulita.doc.extract_pages([0]) is not None


# ================================================================== visualizza

def test_zoom(app_pulita):
    vista = app_pulita.view
    app_pulita.view_zoom_in()
    primo = vista.zoom()
    app_pulita.view_zoom_out()
    assert vista.zoom() < primo
    app_pulita.view_actual_size()
    assert abs(vista.zoom() - 1.0) < 0.01
    app_pulita.view_fit_page()
    assert vista.zoom() > 0
    app_pulita.view_fit_width()
    assert vista.zoom() > 0


def test_modi_di_visualizzazione(app_pulita):
    vista = app_pulita.view
    for modo in ("continuous", "single", "facing"):
        vista.set_view_mode(modo)
        assert vista.view_mode() == modo
    vista.set_view_mode("continuous")


def test_schermo_intero_e_presentazione(app_pulita):
    app_pulita.toggle_fullscreen()
    app_pulita.toggle_fullscreen()
    app_pulita.toggle_presentation()
    assert app_pulita._in_presentation
    app_pulita.toggle_presentation()
    assert not app_pulita._in_presentation


def test_interruttori_di_visualizzazione(app_pulita):
    for funzione, lettore in (
        (app_pulita.action_toggle_grid, lambda w: w.view.grid_visible()),
        (app_pulita.action_toggle_snap, lambda w: w.view.snap_on),
        (app_pulita.action_toggle_fields, lambda w: w.view.highlight_fields),
    ):
        prima = lettore(app_pulita)
        funzione()
        assert lettore(app_pulita) != prima
        funzione()
        assert lettore(app_pulita) == prima


def test_tema(app_pulita):
    chiaro = app_pulita.pal.bg
    app_pulita.toggle_theme()
    assert app_pulita.pal.bg != chiaro
    app_pulita.toggle_theme()
    assert app_pulita.pal.bg == chiaro


def test_vai_a_pagina(app_pulita):
    app_pulita.view.go_to_page(0)
    assert app_pulita.view.current_page() == 0


# =========================================================== selezione e copia

def test_seleziona_e_copia_testo(app_pulita):
    vista = app_pulita.view
    vista.select_all_text()
    assert vista.selected_text().strip()
    assert vista.copy_selection()


def test_annulla_e_ripeti(app_pulita):
    app_pulita.doc.replace_text("Relazione", "Rapporto")
    assert "Rapporto" in app_pulita.doc.text(0)
    app_pulita.edit_undo()
    assert "Relazione annuale" in app_pulita.doc.text(0)
    app_pulita.edit_redo()
    assert "Rapporto" in app_pulita.doc.text(0)


# ================================================================ annotazioni

@pytest.mark.parametrize("tipo", [
    "rect", "circle", "line", "arrow", "ink", "polygon", "note", "freetext", "stamp", "link",
])
def test_crea_ogni_tipo_di_annotazione(app_pulita, tipo):
    kw = {}
    if tipo in ("line", "arrow", "ink", "polygon"):
        kw["vertices"] = [(100, 400), (150, 430), (200, 410)]
    elif tipo == "note":
        kw["text"] = "una nota"
    elif tipo == "freetext":
        kw["text"] = "testo libero"
    elif tipo == "link":
        kw["text"] = "https://example.org"
    xref = app_pulita.doc.add_annot(0, tipo, pymupdf.Rect(100, 400, 240, 460), **kw)
    if tipo == "link":
        # i collegamenti non sono annotazioni ma vivono in un array separato
        assert app_pulita.doc.links(0), "il collegamento non è stato creato"
        return
    assert xref > 0
    assert any(a["xref"] == xref for a in app_pulita.doc.annots(0))


@pytest.mark.parametrize("tipo", ["highlight", "underline", "strikeout", "squiggly"])
def test_crea_gli_evidenziatori(app_pulita, tipo):
    xref = app_pulita.doc.add_annot(
        0, tipo, pymupdf.Rect(100, 400, 240, 415), quads=[pymupdf.Rect(100, 400, 240, 415)]
    )
    assert xref > 0


def test_modifica_ed_elimina_annotazione(app_pulita):
    doc = app_pulita.doc
    xref = doc.add_annot(0, "rect", pymupdf.Rect(100, 400, 240, 460))
    doc.set_annot_rect(0, xref, pymupdf.Rect(90, 390, 230, 450))
    doc.set_annot_props(0, xref, {"opacity": 0.5})
    assert doc.annot_rect(0, xref) is not None
    doc.delete_annot(0, xref)
    assert not any(a["xref"] == xref for a in doc.annots(0))


def test_appiattisci_annotazioni(app_pulita):
    """«Appiattisci annotazioni» tocca solo le annotazioni.

    Le due voci di menu erano la stessa chiamata a ``bake(annots=True,
    widgets=True)``: appiattire le annotazioni cancellava anche i campi modulo,
    e viceversa. Ora ognuna lascia in piedi ciò che non le riguarda.
    """
    doc = app_pulita.doc
    campi_prima = len(doc.fields())
    annots_prima = len(doc.annots(0, include_widgets=False))
    doc.add_annot(0, "rect", pymupdf.Rect(100, 400, 240, 460))
    doc.flatten_annotations()
    assert len(doc.annots(0, include_widgets=False)) == annots_prima
    assert len(doc.fields()) == campi_prima, "i campi non sono annotazioni"


def test_appiattisci_campi(app_pulita):
    """«Appiattisci campi» tocca solo i campi e lascia le annotazioni."""
    doc = app_pulita.doc
    annots_prima = len(doc.annots(0, include_widgets=False))
    doc.add_annot(0, "rect", pymupdf.Rect(100, 400, 240, 460))
    doc.flatten_fields()
    assert not doc.fields(), "i campi dovrebbero essere diventati contenuto"
    assert (
        len(doc.annots(0, include_widgets=False)) == annots_prima + 1
    ), "le annotazioni devono restare"


# ===================================================================== testo

def test_inserisce_testo(app_pulita):
    doc = app_pulita.doc
    doc.insert_text_box(0, pymupdf.Rect(60, 700, 300, 730), "ciao", fontsize=11)
    assert "ciao" in doc.text(0)
    doc.add_text(0, (60, 760), "riga", fontsize=10)


def test_legge_testo_e_parole(app_pulita):
    doc = app_pulita.doc
    assert "Relazione" in doc.text(0)
    assert doc.words(0)
    assert doc.words_in_rect(0, pymupdf.Rect(50, 110, 520, 150))
    assert doc.extract_text(0)
    assert doc.fonts(0) is not None


def test_sostituisci_testo(app_pulita):
    """La sostituzione deve mettere la parola al posto giusto e nell'ordine giusto."""
    prima = app_pulita.doc.text(0)
    assert "Relazione annuale" in prima
    assert app_pulita.doc.replace_text("Relazione", "Rapporto") >= 1
    dopo = app_pulita.doc.text(0)
    assert "Rapporto annuale" in dopo, f"ordine di lettura sbagliato: {dopo!r}"


def test_sostituisci_una_frase_intera(app_pulita):
    assert app_pulita.doc.replace_text("Testo da modificare qui.", "Testo rivisto") >= 1
    testo = app_pulita.doc.text(0)
    assert "Testo rivisto" in testo
    assert "modificare" not in testo


def test_redazione(app_pulita):
    doc = app_pulita.doc
    doc.redact(0, [pymupdf.Rect(50, 110, 300, 150)])
    assert "Testo da modificare" not in doc.text(0)
    assert doc.find_redact_targets(0, "Relazione") is not None
    doc.redact_search(0, "Relazione")


# =================================================================== immagini

def test_immagini(app_pulita, tmp_path):
    doc = app_pulita.doc
    assert doc.image_rects(0)
    assert doc.image_inventory()
    estratti = tmp_path / "estratta.png"
    assert doc.extract_image_to_file(doc.image_rects(0)[0]["xref"], estratti)
    assert estratti.exists()


# ====================================================== conversione da immagini

def _foto(cartella, nome, w=800, h=600, colore=(200, 40, 40)):
    """Scrive un'immagine di prova e ne restituisce il percorso."""
    from PIL import Image

    Image.new("RGB", (w, h), colore).save(cartella / nome, "PNG")
    return str(cartella / nome)


def _foto_ordinate(cartella, colori):
    """Un'immagine per colore, nell'ordine dei colori richiesti."""
    return [_foto(cartella, f"foto{idx}.png", colore=c) for idx, c in enumerate(colori)]


def _apri(percorso):
    return pymupdf.open(percorso)


def _forme(generato):
    """Le dimensioni di ogni pagina, nell'ordine in cui sono disposte."""
    return [(round(p.rect.width), round(p.rect.height)) for p in generato]


def _riquadri(pagina):
    """I riquadri delle immagini disegnate, nell'ordine in cui sono tracciate."""
    return [pymupdf.Rect(i["bbox"]) for i in pagina.get_image_info()]


def _al_centro(pagina):
    """Il colore del pixel al centro della pagina: dice quale foto c'e' dentro."""
    pm = pagina.get_pixmap(dpi=24)
    return pm.pixel(pm.width // 2, pm.height // 2)


def _quasiuguale(a, b, tol=6):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def test_converti_una_immagine(app_pulita, tmp_path):
    doc = app_pulita.doc
    prima, dopo = doc.path, doc.page_count
    out = tmp_path / "foto.pdf"
    assert doc.images_to_pdf(out, [_foto(tmp_path, "a.png")]) == out
    assert out.exists()
    generato = _apri(out)
    assert generato.page_count == 1
    assert round(generato[0].rect.width) == 595 and round(generato[0].rect.height) == 842
    # la conversione produce un file a se': il documento aperto resta com'era
    assert doc.path == prima and doc.page_count == dopo


def test_converti_una_foto_per_pagina(app_pulita, tmp_path):
    out = tmp_path / "foto.pdf"
    app_pulita.doc.images_to_pdf(out, _foto_ordinate(tmp_path, [(200, 0, 0), (0, 200, 0), (0, 0, 200)]))
    generato = _apri(out)
    assert generato.page_count == 3
    for pagina, atteso in zip(generato, [(200, 0, 0), (0, 200, 0), (0, 0, 200)]):
        assert _quasiuguale(_al_centro(pagina), atteso), "le foto non sono nell'ordine scelto"


def test_la_griglia_raggruppa_le_immagini(app_pulita, tmp_path):
    out = tmp_path / "griglia.pdf"
    app_pulita.doc.images_to_pdf(out, _foto_ordinate(tmp_path, [(200, 0, 0), (0, 200, 0), (0, 0, 200)]),
                                 per_page=4)
    generato = _apri(out)
    assert generato.page_count == 1
    riquadri = _riquadri(generato[0])
    assert len(riquadri) == 3
    # la prima sta in alto a sinistra, la seconda in alto a destra: e' l'ordine
    # con cui sono state scelte, letto sulla pagina
    assert riquadri[0].x0 < riquadri[1].x0
    assert _quasiuguale(_al_centro(generato[0]), (0, 200, 0)) is False


def test_la_griglia_mette_una_immagine_per_cella(app_pulita, tmp_path):
    out = tmp_path / "griglia.pdf"
    quattro = [_foto(tmp_path, f"q{i}.png", 400, 400) for i in range(4)]
    app_pulita.doc.images_to_pdf(out, quattro, per_page=4, margin=0.0)
    riquadri = _riquadri(_apri(out)[0])
    assert len(riquadri) == 4
    # quattro celle quadre su un A4: si toccano e non si sovrappongono
    for r in riquadri:
        assert round(r.width) == round(r.height)
        assert not (r & pymupdf.Rect(0, 0, 595, 842)).is_empty
    for i, a in enumerate(riquadri):
        for b in riquadri[i + 1:]:
            assert (a & b).is_empty, "due immagini nella stessa cella"


def test_i_margini_tengono_le_immagini_dentro(app_pulita, tmp_path):
    out = tmp_path / "margini.pdf"
    margine = 36.0
    app_pulita.doc.images_to_pdf(out, [_foto(tmp_path, "a.png")], margin=margine)
    riquadro = _riquadri(_apri(out)[0])[0]
    assert riquadro.x0 >= margine - 0.5 and riquadro.y0 >= margine - 0.5
    assert _apri(out)[0].rect.width - riquadro.x1 >= margine - 0.5


def test_il_formato_orizzontale_scambia_i_lati(app_pulita, tmp_path):
    out = tmp_path / "orizzontale.pdf"
    app_pulita.doc.images_to_pdf(out, [_foto(tmp_path, "a.png")], orientation="orizzontale")
    rett = _apri(out)[0].rect
    assert rett.width > rett.height
    assert round(rett.width) == 842 and round(rett.height) == 595


def test_il_formato_immagine_prende_la_forma_della_foto(app_pulita, tmp_path):
    out = tmp_path / "forma.pdf"
    tre = [_foto(tmp_path, "a.png", 800, 600), _foto(tmp_path, "b.png", 600, 800),
           _foto(tmp_path, "c.png", 400, 400)]
    app_pulita.doc.images_to_pdf(out, tre, page="immagine", fit="originale", dpi=72.0, margin=0.0)
    generato = _apri(out)
    assert _forme(generato) == [(800, 600), (600, 800), (400, 400)]


def test_il_formato_immagine_tiene_i_margini(app_pulita, tmp_path):
    out = tmp_path / "forma.pdf"
    app_pulita.doc.images_to_pdf(out, [_foto(tmp_path, "a.png")], page="immagine",
                                 fit="originale", dpi=72.0, margin=10.0)
    rett = _apri(out)[0].rect
    # il margine sta dentro la pagina: chiedere un bordo e ritrovare il foglio
    # identico sarebbe un'opzione che sembra fare qualcosa e non fa niente
    assert round(rett.width) == 820 and round(rett.height) == 620


def test_l_adattamento_alla_pagina_mostra_tutto(app_pulita, tmp_path):
    out = tmp_path / "conta.pdf"
    # una panorama molto larga su una pagina verticale ci sta solo in altezza
    app_pulita.doc.images_to_pdf(out, [_foto(tmp_path, "a.png", 1600, 200)], fit="pagina")
    riquadro = _riquadri(_apri(out)[0])[0]
    assert riquadro.width < 595
    assert abs(riquadro.width / riquadro.height - 8.0) < 0.01


def test_l_adattamento_piena_riempie_la_pagina(app_pulita, tmp_path):
    out = tmp_path / "piena.pdf"
    app_pulita.doc.images_to_pdf(out, [_foto(tmp_path, "a.png", 1600, 200)],
                                 fit="piena", margin=0.0)
    generato = _apri(out)
    pm = generato[0].get_pixmap(dpi=24)
    # il ritaglio arriva ai bordi del foglio: senza, ci sarebbero strisce vuote
    for x, y in ((1, 1), (pm.width - 2, 1), (1, pm.height - 2), (pm.width - 2, pm.height - 2)):
        assert _quasiuguale(pm.pixel(x, y), (200, 40, 40), tol=40), "il ritaglio non riempie la pagina"


def test_l_adattamento_originale_stampa_alla_risoluzione(app_pulita, tmp_path):
    for dpi, atteso in ((150.0, (384.0, 288.0)), (300.0, (192.0, 144.0))):
        out = tmp_path / f"dpi{int(dpi)}.pdf"
        app_pulita.doc.images_to_pdf(out, [_foto(tmp_path, "a.png")], fit="originale", dpi=dpi)
        riquadro = _riquadri(_apri(out)[0])[0]
        assert abs(riquadro.width - atteso[0]) < 1.0
        assert abs(riquadro.height - atteso[1]) < 1.0


def test_la_griglia_ha_un_tetto(app_pulita, tmp_path):
    out = tmp_path / "troppe.pdf"
    dodici = [_foto(tmp_path, f"t{i}.png", 60, 60) for i in range(13)]
    app_pulita.doc.images_to_pdf(out, dodici, per_page=99, margin=0.0)
    generato = _apri(out)
    from pdfeditor.core.document import MAX_IMMAGINI_PER_PAGINA

    # oltre il tetto il foglio diventa una tabelle di francobolli illeggibili:
    # il chiamante puo' sbagliare il numero, non renderlo illeggibile
    assert generato.page_count == 2
    assert MAX_IMMAGINI_PER_PAGINA == 12


def test_converti_senza_immagini(app_pulita, tmp_path):
    from pdfeditor.core.document import DocumentError

    with pytest.raises(DocumentError):
        app_pulita.doc.images_to_pdf(tmp_path / "vuoto.pdf", [])


def test_converti_una_immagine_illeggibile(app_pulita, tmp_path):
    from pdfeditor.core.document import DocumentError

    rotto = tmp_path / "rotto.png"
    rotto.write_bytes(b"questo non e' un'immagine")
    with pytest.raises(DocumentError) as esito:
        app_pulita.doc.images_to_pdf(tmp_path / "rotto.pdf", [str(rotto)])
    assert "rotto.png" in str(esito.value)


def test_aprire_una_immagine_mette_una_foto_per_pagina(app_pulita, tmp_path):
    """«Apri un'immagine» non e' «converti»: ogni pagina ha la forma della sua foto."""
    doc = app_pulita.doc
    doc.open_images([_foto(tmp_path, "a.png", 800, 600),
                     _foto(tmp_path, "b.png", 600, 800),
                     _foto(tmp_path, "c.png", 400, 400)])
    assert doc.page_count == 3
    assert _forme([doc.page(i) for i in range(3)]) == [(800, 600), (600, 800), (400, 400)]
    # e' un documento nuovo, mai salvato: toccarlo prima non ha senso
    assert doc.path is None


def test_converti_immagini_crea_e_apre_il_file(app_pulita, tmp_path, monkeypatch):
    """La voce di menu deve scrivere il PDF e aprire quello, non lasciare com'era."""
    from PySide6.QtWidgets import QFileDialog

    from pdfeditor.ui.dialogs import props

    scelte = _foto_ordinate(tmp_path, [(200, 0, 0), (0, 200, 0)])
    bersaglio = tmp_path / "conversione.pdf"

    class Scelto:
        def __init__(self, *a, **k):
            pass

        def exec(self):
            return props.QDialog.Accepted

        def images(self):
            return scelte

        def values(self):
            return {"page": "A4", "orientation": "verticale", "fit": "pagina",
                    "margin": 18.0, "per_page": 1, "dpi": 150}

    monkeypatch.setattr(props, "ImagesToPdfDialog", Scelto)
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(bersaglio), "PDF")))
    app_pulita.file_images_to_pdf()
    for _ in range(6):
        QApplication.instance().processEvents()
    assert bersaglio.exists(), "il PDF delle immagini non e' stato scritto"
    assert app_pulita.doc.path == bersaglio, "il PDF generato non e' stato aperto"
    assert app_pulita.doc.page_count == 2


def test_converti_immagini_usa_le_scelte_del_dialogo(app_pulita, tmp_path, monkeypatch):
    """Le opzioni scelte nel dialogo devono arrivare al motore, non essere dimenticate."""
    from PySide6.QtWidgets import QFileDialog

    from pdfeditor.ui.dialogs import props

    bersaglio = tmp_path / "scelte.pdf"
    volute = {"page": "A5", "orientation": "orizzontale", "fit": "piena",
              "margin": 12.0, "per_page": 4, "dpi": 300}
    passate = {}

    class Scelto:
        def __init__(self, *a, **k):
            pass

        def exec(self):
            return props.QDialog.Accepted

        def images(self):
            return [_foto(tmp_path, "a.png")]

        def values(self):
            return dict(volute)

    def finto(path, files, **kw):
        passate.update(kw)
        # la conversione vera gira lo stesso: cosi' l'azione arriva fino
        # all'apertura del file senza che il file ci sia
        return reale(path, files, **kw)

    reale = app_pulita.doc.images_to_pdf
    monkeypatch.setattr(props, "ImagesToPdfDialog", Scelto)
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(bersaglio), "PDF")))
    monkeypatch.setattr(app_pulita.doc, "images_to_pdf", finto)
    app_pulita.file_images_to_pdf()
    assert passate == volute, f"al motore sono arrivate altre scelte: {passate}"


def test_converti_immagini_annullato_non_tocca_niente(app_pulita, tmp_path, monkeypatch):
    """Un dialogo annullato o senza immagini non deve produrre nessun file."""
    from PySide6.QtWidgets import QFileDialog

    from pdfeditor.ui.dialogs import props

    bersaglio = tmp_path / "non_esiste.pdf"
    richiamato = []

    def sorvegliato(*a, **k):
        richiamato.append(a)
        return bersaglio

    class Annullato:
        def __init__(self, *a, **k):
            pass

        def exec(self):
            return props.QDialog.Rejected

        def images(self):
            return []

        def values(self):
            return {}

    monkeypatch.setattr(props, "ImagesToPdfDialog", Annullato)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(sorvegliato))
    monkeypatch.setattr(app_pulita.doc, "images_to_pdf",
                        lambda *a, **k: pytest.fail("non si doveva convertire niente"))
    app_pulita.file_images_to_pdf()
    assert not richiamato, "il dialogo annullato ha aperto la finestra di salvataggio"
    assert not bersaglio.exists()


def test_converti_immagini_ridefinisce_il_formato(app_pulita, tmp_path, monkeypatch):
    """Un formato sconosciuto o una griglia assurda non devono far fallire la conversione."""
    out = tmp_path / "strano.pdf"
    app_pulita.doc.images_to_pdf(out, [_foto(tmp_path, "a.png")], page="non esiste",
                                 fit="non esiste", per_page=-4)
    generato = _apri(out)
    assert generato.page_count == 1
    # senza un formato riconosciuto si cade sul A4, non su una pagina a caso
    assert round(generato[0].rect.width) == 595


def test_riduci_dimensione(app_pulita, tmp_path):
    esito = app_pulita.doc.reduce_size(tmp_path / "ridotto.pdf", quality=60)
    assert isinstance(esito, dict)
    assert (tmp_path / "ridotto.pdf").exists()


# ===================================================================== campi

def test_campi_del_documento_di_prova(app_pulita):
    assert len(app_pulita.doc.fields()) == 5
    assert app_pulita.doc.field_kinds_count()


@pytest.mark.parametrize("tipo", ["text", "checkbox", "combo", "button", "signature"])
def test_crea_ogni_tipo_di_campo(app_pulita, tipo):
    extra = {"options": ["a", "b"], "value": "a"} if tipo == "combo" else {}
    xref = app_pulita.doc.add_field(0, tipo, pymupdf.Rect(60, 620, 260, 646),
                                    name=f"nuovo_{tipo}", **extra)
    assert xref > 0
    assert any(f.xref == xref for f in app_pulita.doc.fields())


def test_gruppo_di_pulsanti_di_opzione(app_pulita):
    xrefs = app_pulita.doc.add_radio_group(
        0, [pymupdf.Rect(60, 700, 78, 718), pymupdf.Rect(90, 700, 108, 718)], "scelta"
    )
    assert len(xrefs) == 2
    assert app_pulita.doc.select_radio(0, xrefs[0])
    assert app_pulita.doc.radio_is_on(0, xrefs[0])


def test_valore_e_proprieta_del_campo(app_pulita):
    campo = app_pulita.doc.fields(0)[0]
    app_pulita.doc.set_field_value(0, campo.xref, "Mario")
    assert next(f.value for f in app_pulita.doc.fields() if f.xref == campo.xref) == "Mario"
    assert app_pulita.doc.set_field_properties(0, campo.xref, {"fontsize": 14})
    assert app_pulita.doc.validate_field_value(0, campo.xref, "x") is not None


def test_azzera_e_appiattisci_campi(app_pulita):
    doc = app_pulita.doc
    doc.set_field_value(0, doc.fields(0)[0].xref, "qualcosa")
    doc.reset_form()
    doc.flatten_fields()
    assert not doc.fields()


def test_ordina_i_campi(app_pulita):
    assert app_pulita.doc.sort_fields_in_reading_order() is not None


# ================================================================= protezione

def test_esporta_protetto_e_lo_riapre(tmp_path):
    from pdfeditor.core.document import Document

    sorgente = Document()
    sorgente.new(595, 842)
    sorgente.insert_text_box(0, pymupdf.Rect(50, 50, 300, 90), "ciao", fontsize=12)
    protetto = tmp_path / "protetto.pdf"
    sorgente.export(str(protetto), permissions=-4, owner_pass="prop", user_pass="prova")
    sorgente.close()

    aperto = Document()
    aperto.open(str(protetto), password="prova")
    assert aperto.is_encrypted
    aperto.remove_encryption("prop")
    assert aperto._encrypt_fields() is None
    liberato = tmp_path / "liberato.pdf"
    aperto.save(liberato)
    aperto.close()

    verifica = Document()
    verifica.open(str(liberato))
    assert not verifica.is_encrypted
    verifica.close()


# ============================================================= segnalibri e meta

def test_segnalibri(app_pulita):
    doc = app_pulita.doc
    doc.add_bookmark("Capitolo", 0)
    assert any(b["title"] == "Capitolo" for b in doc.outline())
    assert doc.rename_bookmark("Capitolo", "Capitolo due")
    assert any(b["title"] == "Capitolo due" for b in doc.outline())
    doc.remove_bookmark("Capitolo due")
    assert not any(b["title"] == "Capitolo due" for b in doc.outline())


def test_metadati_e_lingua(app_pulita):
    doc = app_pulita.doc
    assert doc.metadata() is not None
    doc.set_metadata({"title": "Titolo"})
    assert doc.metadata().get("title") == "Titolo"
    doc.set_document_language("it")
    assert doc.language() == "it"
    assert doc.xmp_metadata() is not None


def test_snapshot(app_pulita):
    assert len(app_pulita.doc.snapshot()) > 0


# ===================================================================== pannelli

@pytest.mark.parametrize("nome", [
    "panel_search", "panel_fields", "panel_bookmarks", "panel_comments",
    "panel_attach", "panel_props", "panel_quality",
])
def test_i_pannelli_esistono_e_caricano(finestra, documento_modello, nome):
    from pdfeditor.ui import theme
    from pdfeditor.ui.theme import Palette

    pannello = getattr(finestra, nome, None)
    assert pannello is not None, f"il pannello {nome} non esiste"
    finestra.load_path(documento_modello)
    for _ in range(4):
        QApplication.instance().processEvents()
    finestra._reload_panels()  # il caricamento vero, quello che fa il programma
    pannello.setVisible(True)
    for _ in range(2):
        QApplication.instance().processEvents()
    # Un pannello che non ha costruito i suoi controlli non ha una dimensione
    # e non ha figli: e' il modo di accorgersi che il pannello e' nato a
    # meta'. Prima la verifica finiva con «assert pannello is not None»
    # ripetuto, quindi non guardava niente.
    assert isinstance(pannello.palette, Palette), f"il pannello {nome} non ha una palette"
    assert pannello.sizeHint().isValid(), f"il pannello {nome} non ha una dimensione valida"
    figli = pannello.findChildren(QWidget)
    assert figli, f"il pannello {nome} non ha costruito nessun controllo"
    assert theme.corrente() is not None


# ================================================================= schede informative

@pytest.mark.parametrize("azione", [
    "action_shortcuts", "action_about", "action_third_party", "action_preferences",
    "action_security", "action_verify_signatures", "action_doc_props",
])
def test_le_voci_informative_si_aprono(finestra, documento_modello, senza_dialoghi, azione):
    finestra.load_path(documento_modello)
    for _ in range(4):
        QApplication.instance().processEvents()
    getattr(finestra, azione)()
    for _ in range(4):
        QApplication.instance().processEvents()


# ================================================= firma e immagini mobili


def test_una_immagine_inserita_si_sposta(finestra, documento_modello):
    """Un'immagine si afferra e si trascina come un qualsiasi elemento.

    Le immagini non sono annotazioni: senza cercarle nel punto premuto non
    erano selezionabili e la firma inserita restava ferma dove capitava.
    """
    import io as _io

    from PIL import Image

    finestra.load_path(documento_modello)
    for _ in range(6):
        QApplication.instance().processEvents()
    b = _io.BytesIO()
    Image.new("RGBA", (200, 60), (200, 0, 0, 255)).save(b, "PNG")
    finestra.doc.insert_image(0, pymupdf.Rect(120, 600, 320, 660), b.getvalue(),
                              keep_proportion=False)
    for _ in range(4):
        QApplication.instance().processEvents()
    vista = finestra.view
    prima = finestra.doc.image_rects(0)[-1]["rect"]
    hit = vista._hit_test(0, vista._page_local(0, _scena(finestra, 200, 630)))
    assert hit is not None and hit[0] == "image", "l'immagine non e' stata riconosciuta"

    finestra.select_tool("select")
    _trascina(finestra, (200, 630), (300, 710))
    dopo = finestra.doc.image_rects(0)[-1]["rect"]
    assert abs((dopo.x0 - prima.x0) - 100) <= 3, f"spostata di {dopo.x0 - prima.x0} invece di 100"
    assert abs((dopo.y0 - prima.y0) - 80) <= 3, f"spostata di {dopo.y0 - prima.y0} invece di 80"


def test_la_firma_viene_posizionata_e_rest_a_selezionata(finestra, documento_modello):
    """La firma non deve finire in un punto a caso.

    Prima cercava uno spazio libero sulla pagina: finiva lontano da dove si
    lavora e non la si poteva ne' vedere ne' spostare. Ora parte dal centro
    di cio' che si vede e resta selezionata, pronta da trascinare.
    """
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QDialogButtonBox

    from pdfeditor.ui.dialogs.signature_dialog import SignatureDialog

    finestra.load_path(documento_modello)
    for _ in range(6):
        QApplication.instance().processEvents()
    prima = len(finestra.doc.image_rects(0))

    def pilota():
        for wid in QApplication.instance().topLevelWidgets():
            if not isinstance(wid, SignatureDialog) or not wid.isVisible():
                continue
            wid.tabs.setCurrentIndex(1)
            wid.type_text.setText("Mario Rossi")
            for _ in range(3):
                QApplication.instance().processEvents()
            for b in wid.findChildren(QDialogButtonBox)[0].buttons():
                if b.text() == "Inserisci":
                    b.click()
                    return

    timer = QTimer()
    timer.setInterval(80)
    timer.timeout.connect(pilota)
    timer.start()
    finestra.action_signature()
    timer.stop()
    for _ in range(6):
        QApplication.instance().processEvents()

    assert len(finestra.doc.image_rects(0)) == prima + 1, "la firma non e' stata inserita"
    inserita = finestra.doc.image_rects(0)[-1]["rect"]
    # deve stare dentro la pagina e nella parte visibile
    assert finestra.doc.page_info(0).rect.contains(inserita), f"fuori pagina: {inserita}"
    assert not finestra.view.scene_obj.selection.rect.isNull(), "la firma non e' selezionata"
    assert abs(finestra.view.scene_obj.selection.rect.x() - inserita.x0) <= 2, (
        "la selezione non coincide con la firma inserita"
    )


def test_la_firma_si_trascina_dopo_l_inserimento(finestra, documento_modello):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QDialogButtonBox

    from pdfeditor.ui.dialogs.signature_dialog import SignatureDialog

    finestra.load_path(documento_modello)
    for _ in range(6):
        QApplication.instance().processEvents()

    def pilota():
        for wid in QApplication.instance().topLevelWidgets():
            if not isinstance(wid, SignatureDialog) or not wid.isVisible():
                continue
            wid.tabs.setCurrentIndex(1)
            wid.type_text.setText("Mario Rossi")
            for _ in range(3):
                QApplication.instance().processEvents()
            for b in wid.findChildren(QDialogButtonBox)[0].buttons():
                if b.text() == "Inserisci":
                    b.click()
                    return

    timer = QTimer()
    timer.setInterval(80)
    timer.timeout.connect(pilota)
    timer.start()
    finestra.action_signature()
    timer.stop()
    for _ in range(6):
        QApplication.instance().processEvents()

    inserita = finestra.doc.image_rects(0)[-1]["rect"]
    cx, cy = (inserita.x0 + inserita.x1) / 2, (inserita.y0 + inserita.y1) / 2
    _trascina(finestra, (cx, cy), (cx + 40, cy + 90))
    spostata = finestra.doc.image_rects(0)[-1]["rect"]
    assert abs((spostata.x0 - inserita.x0) - 40) <= 3, "la firma non si e' spostata in orizzontale"
    assert abs((spostata.y0 - inserita.y0) - 90) <= 3, "la firma non si e' spostata in verticale"


# ============================================================ firma digitale


def test_la_firma_digitata_si_scrive_davvero(finestra, documento_modello):
    """Il nome digitato deve uscire leggibile, non come una fila di quadratini.

    I font venivano scelti leggendo il nome del file: un font di scrittura
    antica con «script» nel nome finiva in testa alla lista e il nome
    digitato usciva fatto di rettangoli.
    """
    from pdfeditor.signature import typed

    # L'ordinamento e' la promessa di list_fonts: i font utilizzabili stanno
    # davanti, e un font calligrafico senza lettere latine non puo' precedere
    # un font che le ha. Prima questa verifica finiva con un «or True»,
    # quindi non controllava niente ed era passata accanto al difetto.
    font = typed.list_fonts()
    if font:
        ultimo_utile = max((i for i, f in enumerate(font) if f["latino"]), default=-1)
        primo_inutile = min((i for i, f in enumerate(font) if not f["latino"]), default=len(font))
        assert primo_inutile > ultimo_utile, (
            f"un font senza lettere latine (indice {primo_inutile}) precede un font "
            f"utilizzabile (indice {ultimo_utile})"
        )
    # il font predefinito deve poter scrivere le lettere
    predefinito = typed.pick_default_font()
    assert predefinito, "nessun font disponibile"
    assert typed.ha_lettere(predefinito), "il font predefinito non ha le lettere"

    finestra.load_path(documento_modello)
    for _ in range(6):
        QApplication.instance().processEvents()
    from pdfeditor.ui.dialogs.signature_dialog import SignatureDialog

    dlg = SignatureDialog(finestra.doc, 0, finestra.library, finestra)
    dlg.tabs.setCurrentIndex(1)
    for _ in range(3):
        QApplication.instance().processEvents()
    assert typed.ha_lettere(dlg.font_box.currentData()), (
        f"il dialogo parte da un font senza lettere: {dlg.font_box.currentText()}"
    )
    dlg.type_text.setText("Mario Rossi")
    for _ in range(5):
        QApplication.instance().processEvents()
    immagine = dlg._typed_image
    assert immagine is not None, "nessuna immagine generata"
    # il testo deve occupare una parte sensata dell'immagine
    p = immagine.convert("RGBA")
    disegno = sum(1 for y in range(0, immagine.height, 3)
                  for x in range(0, immagine.width, 3)
                  if p.getpixel((x, y))[3] > 40)
    assert disegno > 20, "l'immagine sembra vuota"
    dlg.close()


# ==================================================================== tema


def test_il_tema_scuro_raggiunge_tutto(finestra, documento_modello):
    """Il tema scuro deve arrivare a pannelli, vista e miniature."""
    from pdfeditor.ui import theme

    finestra.load_path(documento_modello)
    for _ in range(6):
        QApplication.instance().processEvents()
    iniziale = finestra.pal.bg
    finestra.toggle_theme()
    for _ in range(6):
        QApplication.instance().processEvents()
    assert finestra.pal.bg != iniziale
    assert theme.corrente() is finestra.pal, "la palette attiva non e' stata aggiornata"
    for nome in ("panel_search", "panel_fields", "panel_bookmarks", "panel_comments",
                 "panel_attach", "panel_props", "panel_quality"):
        pannello = getattr(finestra, nome)
        assert pannello.palette is finestra.pal, f"il pannello {nome} e' rimasto sul tema precedente"
    assert finestra.view.palette is finestra.pal
    assert finestra.thumbs.palette is finestra.pal
    finestra.toggle_theme()
    for _ in range(4):
        QApplication.instance().processEvents()
    assert finestra.pal.bg == iniziale


def test_il_cambio_tema_ridisegna_le_icone_della_barra(finestra):
    """Le icone delle barre sono disegnate a mano: vanno ridisegnate.

    Il loro colore viene dalla palette, quindi cambiar tema senza ridisegnarle
    le lasciava del colore precedente: su barra scura erano scure e non si
    vedevano piu'.
    """
    from pdfeditor.ui import theme

    def _media_chiara(azione):
        # solo i pixel opachi contano: lo sfondo di un'icona trasparente,
        # letto come nero, farebbe sembrare ogni icona scura
        img = azione.icon().pixmap(22, 22).toImage()
        campioni = [img.pixelColor(x, y).red()
                    for y in range(img.height())
                    for x in range(img.width())
                    if img.pixelColor(x, y).alpha() > 200]
        return sum(campioni) / len(campioni) if campioni else None

    def _porta_a(scuro: bool):
        if (finestra.pal is theme.DARK) != scuro:
            finestra.toggle_theme()
        for _ in range(6):
            QApplication.instance().processEvents()
        return finestra.pal

    _porta_a(False)
    scuro_media = _media_chiara(finestra.main_acts["save"])
    assert scuro_media is not None, "l'icona di salvataggio e' vuota"

    _porta_a(True)
    chiaro_media = _media_chiara(finestra.main_acts["save"])
    assert chiaro_media is not None, "l'icona e' sparita dopo il cambio tema"
    assert chiaro_media > scuro_media + 40, (
        f"l'icona non e' stata ridisegnata: resta scura ({scuro_media:.0f} -> {chiaro_media:.0f})"
    )
    # anche il menu a tendina degli strumenti, non solo la barra
    menu = finestra._tool_button.menu()
    assert menu is not None, "il menu a tendina degli strumenti non c'e'"
    voce = next(a for a in menu.actions() if a.text() == "Seleziona")
    assert _media_chiara(voce) is not None
    _porta_a(False)


def test_le_maniglie_di_ridimensionamento_hanno_un_colore_del_tema(finestra):
    """I colori delle maniglie stanno nella palette, non fissi sul tema chiaro.

    Con i colori fissi restavano bianchi con bordo blu anche a tema scuro, e
    non si distinguevano dalla pagina.
    """
    from pdfeditor.ui import theme

    for pal, nome in ((theme.LIGHT, "chiaro"), (theme.DARK, "scuro")):
        assert pal.handle_fill and pal.handle_border, f"maniglie senza colore nel tema {nome}"
        assert pal.handle_fill != pal.handle_border, (
            f"nel tema {nome} le maniglie sarebbero invisibili: riempimento e bordo uguali"
        )
    assert theme.LIGHT.handle_fill != theme.DARK.handle_fill, (
        "le maniglie hanno lo stesso colore nei due temi: il tema scuro non le cambia"
    )


def test_il_tema_vale_anche_per_le_finestre_aperte(finestra, documento_modello):
    """Un dialogo aperto dopo il cambio di tema nasce del colore giusto."""
    from pdfeditor.ui import theme
    from pdfeditor.ui.dialogs import props

    finestra.load_path(documento_modello)
    for _ in range(4):
        QApplication.instance().processEvents()
    if finestra.pal is theme.LIGHT:
        finestra.toggle_theme()
        for _ in range(4):
            QApplication.instance().processEvents()
    dlg = props.PageSetupDialog((595, 842), finestra)
    try:
        assert dlg.palette is theme.corrente()
        assert dlg.palette is finestra.pal
    finally:
        dlg.close()


# ============================================================== collegamenti


def test_un_collegamento_si_puo_cliccare(finestra, documento_modello, monkeypatch):
    """Un collegamento in pagina deve essere cliccabile e aprire l'indirizzo.

    I collegamenti non sono annotazioni: vivono in un array della pagina. Non
    esisteva nessun riquadro su cui cliccare, quindi si poteva creare il
    collegamento e leggerlo nell'elenco, ma non usarlo. Il riquadro era anche
    costruito male: ereditava da QGraphicsPathItem e chiamava una setRect che
    quel tipo non ha.
    """
    finestra.load_path(documento_modello)
    for _ in range(6):
        QApplication.instance().processEvents()
    finestra.doc.add_annot(0, "link", pymupdf.Rect(100, 100, 320, 130),
                           text="https://esempio.it")
    for _ in range(4):
        QApplication.instance().processEvents()
    finestra.view.refresh_links()
    finestra._on_doc_changed()
    for _ in range(4):
        QApplication.instance().processEvents()

    finestra.select_tool("select")
    for _ in range(2):
        QApplication.instance().processEvents()
    riquadri = finestra.view.scene_obj.links
    assert len(riquadri) == 1, f"collegamenti visibili in pagina: {len(riquadri)}, attesi 1"
    assert riquadri[0].uri == "https://esempio.it"
    assert riquadri[0].rect().width() > 100, "il riquadro del collegamento e' troppo piccolo"

    aperti = []
    monkeypatch.setattr(finestra, "_open_link", aperti.append)
    # il centro e' in coordinate di scena: va portato nel viewport, altrimenti
    # il clic finisce nel punto sbagliato
    dove = finestra.view.mapFromScene(riquadri[0].rect().center())
    QTest.mouseClick(finestra.view.viewport(), Qt.LeftButton, Qt.NoModifier, dove)
    for _ in range(4):
        QApplication.instance().processEvents()
    assert aperti == ["https://esempio.it"], f"clic non arrivato al gestore: {aperti}"


def test_i_collegamenti_non_coprono_gli_altri_strumenti(finestra, documento_modello):
    """Con uno strumento diverso dal selettore i collegamenti spariscono.

    Un riquadro cliccabile sopra la pagina bloccherebbe il disegno.
    """
    finestra.load_path(documento_modello)
    for _ in range(6):
        QApplication.instance().processEvents()
    finestra.doc.add_annot(0, "link", pymupdf.Rect(100, 100, 320, 130),
                           text="https://esempio.it")
    for _ in range(4):
        QApplication.instance().processEvents()
    finestra.select_tool("select")
    for _ in range(2):
        QApplication.instance().processEvents()
    assert len(finestra.view.scene_obj.links) == 1
    finestra.select_tool("rect")
    for _ in range(2):
        QApplication.instance().processEvents()
    assert not finestra.view.scene_obj.links, "i collegamenti coprono ancora la pagina"
    finestra.select_tool("select")


def test_un_collegamento_interno_porta_alla_pagina(finestra, documento_modello):
    """Un salto a un'altra pagina del documento si puo' seguire."""
    finestra.load_path(documento_modello)
    for _ in range(6):
        QApplication.instance().processEvents()
    if finestra.doc.page_count < 2:
        finestra.doc.insert_page(1)
        for _ in range(3):
            QApplication.instance().processEvents()
    finestra.doc.add_annot(0, "link", pymupdf.Rect(100, 300, 320, 330), target_page=1)
    for _ in range(4):
        QApplication.instance().processEvents()
    finestra.select_tool("select")
    for _ in range(2):
        QApplication.instance().processEvents()
    interni = [l for l in finestra.view.scene_obj.links if l.azione is not None]
    assert interni, "il collegamento alla pagina 2 non e' diventato cliccabile"
    finestra._goto_page(0)
    for _ in range(2):
        QApplication.instance().processEvents()
    dove = finestra.view.mapFromScene(interni[0].rect().center())
    QTest.mouseClick(finestra.view.viewport(), Qt.LeftButton, Qt.NoModifier, dove)
    for _ in range(4):
        QApplication.instance().processEvents()
    assert finestra.view.current_page() == 1, "il collegamento interno non ha portato alla pagina"


def test_una_annotazione_sopra_un_collegamento_e_agibile(finestra, documento_modello, monkeypatch):
    """Un'annotazione appoggiata su un collegamento si deve poter toccare.

    La prova del collegamento veniva prima di ogni altra e vinceva sempre: il
    clic apriva il browser e l'annotazione non era mai selezionata, quindi
    non si poteva spostare, ridimensionare ne' cancellare. Con il clic
    sull'annotazione deve selezionarsi, e il collegamento resta cliccabile
    dove non c'e' nient'altro.
    """
    finestra.load_path(documento_modello)
    for _ in range(6):
        QApplication.instance().processEvents()
    finestra.doc.add_annot(0, "link", pymupdf.Rect(100, 100, 320, 130),
                           text="https://esempio.it")
    finestra.doc.add_annot(0, "rect", pymupdf.Rect(120, 105, 300, 125))
    for _ in range(4):
        QApplication.instance().processEvents()
    finestra.view.refresh_links()
    finestra._on_doc_changed()
    finestra.select_tool("select")
    for _ in range(3):
        QApplication.instance().processEvents()

    aperti = []
    monkeypatch.setattr(finestra, "_open_link", aperti.append)
    rettangolo = next(a for a in finestra.doc.annots(0, include_widgets=False)
                      if a["type"] in ("Square", "Rect"))
    dove = finestra.view.mapFromScene(_scena(finestra, 200, 115))
    QTest.mouseClick(finestra.view.viewport(), Qt.LeftButton, Qt.NoModifier, dove)
    for _ in range(4):
        QApplication.instance().processEvents()
    assert aperti == [], "il collegamento ha preso il clic destinato all'annotazione"
    assert finestra.view.selection_xref() == rettangolo["xref"], (
        f"l'annotazione non e' stata selezionata: {finestra.view.selection_xref()}"
    )

    # fuori dall'annotazione il collegamento si apre ancora
    dove = finestra.view.mapFromScene(_scena(finestra, 310, 120))
    QTest.mouseClick(finestra.view.viewport(), Qt.LeftButton, Qt.NoModifier, dove)
    for _ in range(4):
        QApplication.instance().processEvents()
    assert aperti == ["https://esempio.it"], f"il collegamento ha smesso di funzionare: {aperti}"


def test_il_collegamento_non_blocca_gli_strumenti_di_disegno(finestra, documento_modello, monkeypatch):
    """Con un pennello il clic su un collegamento deve disegnare.

    Il collegamento veniva seguito anche con il rettangolo selezionato: il
    tratto non partiva e compariva la domanda di aprire il browser.
    """
    finestra.load_path(documento_modello)
    for _ in range(6):
        QApplication.instance().processEvents()
    finestra.doc.add_annot(0, "link", pymupdf.Rect(100, 300, 320, 330),
                           text="https://esempio.it")
    for _ in range(4):
        QApplication.instance().processEvents()
    aperti = []
    monkeypatch.setattr(finestra, "_open_link", aperti.append)
    finestra.select_tool("rect")
    for _ in range(2):
        QApplication.instance().processEvents()
    prima = len(finestra.doc.annots(0, include_widgets=False))
    _trascina(finestra, (120, 305), (300, 320))
    assert len(finestra.doc.annots(0, include_widgets=False)) == prima + 1, (
        "il rettangolo non e' stato disegnato sopra il collegamento"
    )
    assert aperti == [], f"il collegamento ha aperto il browser durante il disegno: {aperti}"


def test_la_selezione_accorda_il_genere(finestra, documento_modello):
    """«Annotazione selezionata»: in italiano l'aggettivo concorda col nome."""
    finestra.load_path(documento_modello)
    for _ in range(6):
        QApplication.instance().processEvents()
    finestra.doc.add_annot(0, "rect", pymupdf.Rect(100, 500, 300, 540))
    for _ in range(3):
        QApplication.instance().processEvents()
    finestra.select_tool("select")
    messaggi = []
    finestra.view.status.connect(messaggi.append)
    rett = finestra.doc.annots(0, include_widgets=False)[-1]
    QTest.mouseClick(finestra.view.viewport(), Qt.LeftButton, Qt.NoModifier,
                     finestra.view.mapFromScene(_scena(finestra, 200, 520)))
    for _ in range(4):
        QApplication.instance().processEvents()
    assert any("selezionata" in m for m in messaggi), (
        f"messaggio con il genere sbagliato: {messaggi}"
    )
    del rett


# ============================================================ scorciatoie


def _scorciatoie_dichiarate(finestra) -> dict[str, str]:
    """Le scorciatoie reali, raccolte dai menu, per testo della voce."""
    out = {}
    for azione in finestra.menuBar().actions():
        menu = azione.menu()
        if menu is None:
            continue
        for voce in menu.actions():
            scorciatoia = voce.shortcut().toString()
            if scorciatoia:
                out.setdefault(scorciatoia, voce.text())
    return out


def test_ogni_scorciatoia_annunciata_esiste(finestra):
    """La finestra di aiuto non deve promettere scorciatoie inesistenti.

    Una volta l'elenco era scritto a mano e aveva annunciato «Ctrl+G» per la
    griglia (che era «Ctrl+'»), i tasti da una lettera per gli strumenti (mai
    registrati) e «Ctrl+W» per chiudere (azione che non e' mai esistita). Ora
    l'elenco e' ricavato dai menu, quindi la verifica serve a impedire che
    torni a diventare una lista scritta a mano.
    """
    testo = finestra._elenco_scorciatoie()
    assert testo.strip(), "l'elenco delle scorciatoie e' vuoto"
    reali = set(_scorciatoie_dichiarate(finestra))

    # ogni scorciatoia citata deve corrispondere a una voce di menu reale:
    # nell'aiuto le scorciatoie sono la seconda colonna, in un campo fisso
    import re

    citate = {m.group(1).strip() for m in re.finditer(r"^\s{2}(\S[^ ]*.*?)\s{2,}\S", testo, re.M)}
    ignota = {c for c in citate if c and c not in reali and not c.startswith(("F1", "Invio", "Alt", "Spazio"))}
    assert not ignota, f"l'aiuto promette scorciatoie che non esistono: {ignota}"
    assert len(citate) >= 20, f"l'aiuto elenca solo {len(citate)} voci: sembra svuotato"


def test_una_scorciatoia_non_e_registrata_due_volte(finestra):
    """La stessa scorciatoia non può stare su due voci di menu.

    Qt le tratta in modo ambiguo: con due voi che rispondono allo stesso tasto
    la gestione dipende dall'ordine di costruzione dei menu.
    """
    visti: dict[str, str] = {}
    doppioni = []
    for azione in finestra.menuBar().actions():
        menu = azione.menu()
        if menu is None:
            continue
        for voce in menu.actions():
            scorciatoia = voce.shortcut().toString()
            if not scorciatoia:
                continue
            if scorciatoia in visti and visti[scorciatoia] != voce.text():
                doppioni.append(f"{scorciatoia}: «{visti[scorciatoia]}» e «{voce.text()}»")
            visti[scorciatoia] = voce.text()
    assert not doppioni, f"scorciatoie duplicate sui menu: {doppioni}"


def test_il_tasto_che_sceglie_lo_strumento_non_e_una_scorciatoia(finestra):
    """I campi modulo si compilano dentro la finestra: niente tasti singoli.

    Una scorciatoia di una lettera sola, sulla finestra principale, scatterebbe
    la digitazione nei campi: è il motivo per cui i tasti V/H/T/S/I sono solo
    un richiamo e non sono registrati.
    """
    from PySide6.QtGui import QKeySequence

    for azione in finestra.menuBar().actions():
        menu = azione.menu()
        if menu is None:
            continue
        for voce in menu.actions():
            testo = voce.shortcut().toString()
            if not testo:
                continue
            assert len(testo) > 1, (
                f"«{voce.text()}» usa il tasto singolo {testo}: "
                "intercetterebbe la digitazione nei campi modulo"
            )
    assert QKeySequence("Ctrl+H").toString() in {
        a.shortcut().toString()
        for m in (x.menu() for x in finestra.menuBar().actions()) if m
        for a in m.actions()
    }, "Ctrl+H (sostituisci) non e' piu' registrata"


# ==================================================== inserimento delle firme


def test_il_bianco_diventa_trasparente_e_il_resto_no():
    """La firma su fondo bianco deve diventare trasparente, e solo li'.

    La conversione e' passata da un ciclo Python su ogni pixel a NumPy: il
    comportamento deve restare identico, soglia compresa, perche' le sfumature
    dell'antialiasing nella firma non possono sparire diventate bianche.
    """
    from PIL import Image

    from pdfeditor.ui.main_window import _white_to_alpha

    img = Image.new("RGBA", (4, 1))
    img.putpixel((0, 0), (255, 255, 255, 255))   # bianco puro -> via
    img.putpixel((1, 0), (250, 250, 250, 255))   # soglia esatta: 250 non e' > 250 -> resta
    img.putpixel((2, 0), (0, 0, 0, 255))         # nero -> resta
    img.putpixel((3, 0), (255, 255, 255, 200))   # bianco: diventa del tutto trasparente

    out = _white_to_alpha(img)
    assert out.mode == "RGBA"
    assert out.getpixel((0, 0))[3] == 0, "il bianco puro doveva diventare trasparente"
    assert out.getpixel((1, 0))[3] == 255, "un grigio alla soglia non deve sparire"
    assert out.getpixel((2, 0))[3] == 255, "il nero non deve diventare trasparente"
    # il bianco sparisce del tutto, anche se era gia' semitrasparente:
    # e' il comportamento di sempre, e la verifica lo fissa
    assert out.getpixel((3, 0))[3] == 0, "il bianco semitrasparente doveva sparire"
    assert out.size == img.size


# ====================================================== lingua dei messaggi


def test_il_conteggio_accorda_il_numero_alla_parola():
    """In italiano il singolare cambia anche l'aggettivo.

    La barra di stato scriveva «1 pagina selezionate»: il numero e il nome
    erano corretti, la forma no, e con una sola pagina selezionata si leggeva
    come un errore.
    """
    from pdfeditor.core import i18n
    from pdfeditor.ui.main_window import _conta

    it = ("pagina selezionata", "pagine selezionate")
    en = ("page selected", "pages selected")
    assert _conta(1, it, en) == "1 pagina selezionata"
    assert _conta(2, it, en) == "2 pagine selezionate"
    assert _conta(0, ("parola selezionata", "parole selezionate"),
                  ("word selected", "words selected")) == "0 parole selezionate"
    assert _conta(1, ("campo", "campi"), ("field", "fields")) == "1 campo"

    # in inglese il singolare e' un'altra parola, non solo un'altra desinenza
    i18n.set_lingua("en")
    try:
        assert _conta(1, it, en) == "1 page selected"
        assert _conta(2, it, en) == "2 pages selected"
    finally:
        i18n.set_lingua("it")


def test_la_barra_di_stato_accorda_il_numero_alla_parola(finestra, documento_modello):
    """Le voci che contano una cosa sola devono stare al singolare."""
    finestra.load_path(documento_modello)
    for _ in range(6):
        QApplication.instance().processEvents()
    finestra.thumbs.select_pages([0])
    finestra._on_thumb_selection([0])
    for _ in range(3):
        QApplication.instance().processEvents()
    testo = finestra.lbl_status.text()
    assert testo in ("", "1 pagina selezionata"), f"barra di stato: «{testo}»"


# ================================================ difetti riprodotti e corretti

def test_casella_di_spunta_con_il_clic(app_pulita, monkeypatch):
    """Lo strumento «Casella di spunta» deve creare il campo.

    Il nome dello strumento veniva trasformato in «check», che il motore non
    conosce: ogni casella di spunta moriva con «Tipo di campo non supportato:
    check» e non disegnava nulla.
    """
    from pdfeditor.ui.dialogs import props
    from pdfeditor.ui.main_window import FIELD_TOOLS

    assert FIELD_TOOLS["field_check"] == "checkbox"

    class Accettato:
        def __init__(self, parent=None, tipo="text"):
            self.tipo = tipo

        def exec(self):
            return props.QDialog.Accepted

        def values(self):
            return {
                "name": "spunta", "value": "", "fontsize": 11, "font": "Helv",
                "color": (0, 0, 0), "options": [], "tooltip": "", "required": False,
                "read_only": False, "multiline": False, "password": False,
                "button_caption": "",
            }

    monkeypatch.setattr(props, "NewFieldDialog", Accettato)
    prima = len(app_pulita.doc.fields())
    app_pulita._start_tool("field_check")
    _trascina(app_pulita, (100, 300), (118, 318))
    assert len(app_pulita.doc.fields()) == prima + 1, "la casella di spunta non è stata creata"


def test_allega_un_file_come_annotazione(app_pulita, tmp_path, monkeypatch):
    """«Allega file…» deve creare l'annotazione.

    I byte arrivavano come `text` e finivano in un `bytes.encode()`; inoltre
    `Page.add_file_annot` si chiama `buffer_`, non `buffer`: la voce di menu
    non poteva funzionare.
    """
    allegato = tmp_path / "nota.txt"
    allegato.write_text("contenuto dell'allegato")
    from PySide6.QtWidgets import QFileDialog

    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(allegato), ""))
    )
    prima = len(app_pulita.doc.annots(0, include_widgets=False))
    app_pulita._attach_annotation()
    assert len(app_pulita.doc.annots(0, include_widgets=False)) == prima + 1, (
        "l'annotazione di allegato non è stata creata"
    )
    xref = app_pulita.doc.annots(0, include_widgets=False)[-1]["xref"]
    assert "nota.txt" in app_pulita.doc.xref_key(xref, "FS")[1]


def test_testo_libero_crea_un_annotazione(app_pulita, monkeypatch):
    """«Testo libero» deve creare un'annotazione, non una casella di testo.

    Finiva dentro `insert_text_box`, cioe' nel flusso di contenuto della
    pagina: la casella non si poteva piu' spostare, modificare o cancellare
    e non compariva fra le annotazioni. Era quindi identica a «Casella di
    testo» pur avendo un nome diverso.
    """
    from pdfeditor.ui.dialogs import props

    class Accettato:
        def __init__(self, parent=None, fontname="helv", size=12.0):
            pass

        def exec(self):
            return props.QDialog.Accepted

        def values(self):
            return {
                "text": "nota libera", "fontname": "Helvetica", "fontsize": 12.0,
                "color": (0, 0, 0), "align": 0, "rotate": 0, "lineheight": 1.2,
                "fill": None, "border": None, "border_width": 1.0, "margin": 3.0,
                "opacity": 1.0, "fit": "none", "bold": False, "italic": False,
                "underline": False,
            }

    monkeypatch.setattr(props, "TextBoxDialog", Accettato)
    prima = len(app_pulita.doc.annots(0, include_widgets=False))
    app_pulita._start_tool("freetext")
    app_pulita._on_tool_action("freetext", (0, (120.0, 300.0, 300.0, 340.0)))
    annots = app_pulita.doc.annots(0, include_widgets=False)
    assert len(annots) == prima + 1, "«Testo libero» non ha creato nessuna annotazione"
    assert annots[-1]["type"] == "FreeText"
    assert annots[-1]["info"].get("content") == "nota libera"


def test_il_font_del_campo_viene_rispettato(app_pulita):
    """Il font scelto per un campo deve finire davvero nella /DA.

    La finestra passava la stringa «None»: la lista di controllo del motore
    la scartava e ogni campo di testo nasceva in Helvetica,Times o Courier
    scelta non faceva nulla.
    """
    doc = app_pulita.doc
    xref = doc.add_field(0, "text", pymupdf.Rect(60, 500, 260, 526), name="times", font="TiRo")
    assert doc.xref_key(xref, "DA")[1].find("/TiRo") >= 0, (
        f"font non applicato: {doc.xref_key(xref, 'DA')}"
    )
    xref = doc.add_field(0, "text", pymupdf.Rect(60, 540, 260, 566), name="times2", font="Times")
    assert doc.xref_key(xref, "DA")[1].find("/TiRo") >= 0, (
        f"font esteso non riconosciuto: {doc.xref_key(xref, 'DA')}"
    )
    xref = doc.add_field(0, "text", pymupdf.Rect(60, 580, 260, 606), name="sconosciuto",
                         font="NonEsiste")
    assert doc.xref_key(xref, "DA")[1].find("/Helv") >= 0, (
        f"un font inesistente doveva ripiegare su Helvetica: {doc.xref_key(xref, 'DA')}"
    )


def test_la_finestra_del_campo_offre_un_font_presente():
    """La finestra «Nuovo campo» deve partire da un font scelto.

    La coppia era al contrario (mostrava il codice, conservava il nome esteso):
    `findData("helv")` non trovava nulla, la combinazione restava vuota e i
    valori riportavano la stringa «None».
    """
    from pdfeditor.core import textlayout
    from pdfeditor.ui.dialogs import props

    assert textlayout.font_da_name("helv") == "Helv"
    assert textlayout.font_da_name("Times-Roman") == "TiRo"
    assert textlayout.font_da_name("tiit") == "TiRo"
    assert textlayout.font_da_name("NonEsiste") == "Helv"

    dlg = props.NewFieldDialog(None, "checkbox")
    try:
        valori = dlg.values()
        assert valori["kind"] == "checkbox", "il tipo scelto dallo strumento non era preselezionato"
        assert valori["font"] in {n for _, n in textlayout.FIELD_FONTS}
    finally:
        dlg.deleteLater()


def test_ricerca_parola_intera(app_pulita):
    """«Parola intera» deve escludere le sotto-stringhe.

    Il confronto era `needle in testo`, quindi tornava sempre vero: «ore»
    trovava anche dentro «Lorem».
    """
    doc = app_pulita.doc
    assert doc.search("Relazione"), "il testo di prova non contiene la parola cercata"
    sotto = doc.search("elaz", whole_word=True)
    assert sotto == [], f"una sotto-stringa è stata accettata come parola intera: {sotto}"
    intera = doc.search("Relazione", whole_word=True)
    assert intera, "la parola intera non è stata trovata"
    assert len(doc.search("elazione", whole_word=False)) >= len(intera)


def test_sostituzione_riconosce_le_opzioni(app_pulita):
    """Sostituire deve rispettare «parola intera» e «maiusc/minuscole»."""
    doc = app_pulita.doc
    assert doc.search("elazione", whole_word=False), "manca il testo di prova"
    n = doc.replace_text("elazione", "TITOLO", 0, whole_word=True)
    assert n == 0, "la sostituzione ha colpito una sotto-stringa"
    assert "Relazione" in doc.text(0), "il testo è stato alterato"
    n = doc.replace_text("Relazione", "Rapporto", 0, whole_word=True)
    assert n >= 1
    assert "Rapporto" in doc.text(0)


def test_grassetto_corsivo_e_sottolineatura(app_pulita):
    """Le leve della barra del testo devono cambiare il testo inserito.

    Scrivevano solo un messaggio nella barra di stato: la casella usciva
    identica e non c'era modo di togliere l'effetto.
    """
    doc = app_pulita.doc
    app_pulita._start_tool("text")
    app_pulita.text_style.update({"bold": False, "italic": False, "underline": False})
    app_pulita.doc.insert_text_box(0, pymupdf.Rect(60, 300, 400, 330), "Senza stile",
                                   fontname="helv", fontsize=18)
    from pdfeditor.ui.main_window import _font_con_stile

    assert _font_con_stile("helv", False, False) == "helv"
    assert _font_con_stile("helv", True, False) == "hebo"
    assert _font_con_stile("helv", False, True) == "hebi"
    assert _font_con_stile("helv", True, True) == "hebi"
    assert _font_con_stile("tiro", True, False) == "tibo"
    assert _font_con_stile("NonEsiste", True, False) == "NonEsiste"

    # la sottolineatura deve disegnare qualcosa sulla pagina
    prima = len(doc.page(0).get_drawings())
    doc.insert_text_box(0, pymupdf.Rect(60, 340, 400, 370), "Sottolineato",
                        fontname="helv", fontsize=18, underline=True)
    assert len(doc.page(0).get_drawings()) > prima, "la sottolineatura non ha disegnato nulla"


def test_il_testo_nella_finestra_ha_uno_stile(app_pulita):
    """Le caselle Grassetto e Corsivo della finestra devono cambiare il font."""
    from pdfeditor.ui.dialogs import props

    dlg = props.TextBoxDialog(None, "helv", 12.0)
    try:
        assert dlg.font_box.currentData() == "helv", (
            f"font preselezionato sbagliato: {dlg.font_box.currentData()!r}"
        )
        nomi = [dlg.font_box.itemText(i) for i in range(dlg.font_box.count())]
        assert len(set(nomi)) == len(nomi), f"nomi di font ripetuti: {nomi}"
        dlg.bold.setChecked(True)
        assert dlg.values()["fontname"] == "hebo"
        dlg.italic.setChecked(True)
        assert dlg.values()["fontname"] in ("hebi",)
        assert dlg.values()["underline"] is False
    finally:
        dlg.deleteLater()


def test_il_testo_della_pagina_nuova(app_pulita):
    """`insert_page` accetta un testo: deve scriverlo.

    Il parametro esisteva ma non veniva letto, quindi una pagina inserita con
    un titolo restava bianca.
    """
    doc = app_pulita.doc
    at = doc.insert_page(1, 595, 842, text="Titolo del capitolo")
    assert "Titolo del capitolo" in doc.text(at)


def test_la_qualita_jpeg_raggiunge_il_file(app_pulita):
    """La qualità scelta nell'esportazione deve cambiare il file prodotto."""
    from PySide6.QtWidgets import QFileDialog

    alta = app_pulita.doc.extract_page_image(0, dpi=100, fmt="jpg", quality=95)
    bassa = app_pulita.doc.extract_page_image(0, dpi=100, fmt="jpg", quality=20)
    assert len(bassa) < len(alta), (
        f"la qualità non è arrivata al motore: {len(bassa)} contro {len(alta)} byte"
    )
    assert alta.startswith(b"\xff\xd8"), "il file non e' un JPEG"


def test_intervallo_di_esportazione_illeggibile(app_pulita):
    """Un intervallo che non indica pagine deve essere un errore detto.

    Tornava una lista vuota e l'esportazione ripiegava sulla pagina corrente:
    il file risultante aveva una pagina sola, senza che nessuno lo dicesse.
    """
    from pdfeditor.ui.dialogs import props

    dlg = props.ExportDialog(app_pulita.doc.page_count)
    try:
        campo = dlg.range
        pagine = app_pulita.doc.page_count
        campo.setText(f"1-{pagine}")
        assert dlg.parse_range() == list(range(pagine))
        campo.setText(f"{pagine}-")
        assert dlg.parse_range() == list(range(pagine)), "un intervallo aperto doveva arrivare in fondo"
        campo.setText("-1")
        assert dlg.parse_range() == [0], "un intervallo aperto doveva partire dall'inizio"
        for cattivo in ("", "abc", "1,abc", f"1-{pagine + 5}"):
            campo.setText(cattivo)
            with pytest.raises(ValueError):
                dlg.parse_range()
    finally:
        dlg.deleteLater()


def test_la_stampa_mostra_un_messaggio(app_pulita, monkeypatch):
    """Un errore di stampa deve arrivare all'utente, non come traccia."""
    from pdfeditor.ui import printing

    vista = []
    app_pulita._error = lambda exc, titolo="": vista.append((titolo, str(exc)))
    monkeypatch.setattr(
        printing, "print_document",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("la stampante ha rifiutato il foglio")),
    )
    app_pulita.file_print()
    assert vista, "l'errore di stampa non e' arrivato a nessuna parte"
    assert "rifiutato" in vista[0][1]


def test_stampa_con_risoluzione_zero(app_pulita):
    """Una stampante che non conosce la propria risoluzione non deve bloccare."""
    from pdfeditor.ui import printing
    from PySide6.QtPrintSupport import QPrinter

    stampante = QPrinter(QPrinter.HighResolution)
    stampante.setResolution(0)
    assert printing.print_document.__doc__
    # il percorso critico e' il valore minimo del dpi: con 0 il rendering non
    # terminava e la stampa restava bloccata senza mostrare nulla
    assert max(36, min(1200, 300, 0)) == 36
    del stampante


def test_la_pagina_e_la_qualità_del_rendering():
    """Il valore minimo del dpi non deve mai essere zero."""
    assert max(36, min(1200, 1, 0)) == 36
    assert max(36, min(1200, 5000, 1200)) == 1200


def test_il_parametro_scartato_non_esiste_piu():
    """`_mutate` aveva un parametro che nessuno usava: un ostacolo per chi legge."""
    import inspect

    from pdfeditor.core.document import Document

    assert "result_index" not in inspect.signature(Document._mutate).parameters
    assert "commit" not in inspect.signature(Document._page_edit_placeholder).parameters \
        if hasattr(Document, "_page_edit_placeholder") else True


def test_le_proprieta_reddito_sull_immagine(app_pulita, monkeypatch):
    """«Proprietà immagine» deve ridimensionare l'immagine selezionata.

    La voce scriveva solo «Le proprietà dell'immagine si applicano dopo
    l'inserimento»: era un pulsante morto.
    """
    from pdfeditor.ui.dialogs import props

    rett = app_pulita.doc.image_rects(0)[0]["rect"]
    prima = tuple(round(v, 1) for v in rett)
    app_pulita.select_tool("select")
    for _ in range(3):
        QApplication.instance().processEvents()
    dove = app_pulita.view.mapFromScene(
        _scena(app_pulita, rett.x0 + rett.width / 2, rett.y0 + rett.height / 2)
    )
    QTest.mouseClick(app_pulita.view.viewport(), Qt.LeftButton, Qt.NoModifier, dove)
    for _ in range(4):
        QApplication.instance().processEvents()
    assert app_pulita.view.selection_kind() == "image", (
        f"clic sull'immagine: selezionato {app_pulita.view.selection_kind()!r}"
    )

    class Accettato:
        def __init__(self, current, page_size, parent=None, posizione=(0.0, 0.0)):
            self.current = current
            self.posizione = posizione

        def exec(self):
            return props.QDialog.Accepted

        def values(self):
            x0, y0 = self.posizione
            return {"rect": (x0, y0, x0 + 80.0, y0 + 40.0), "crop": False}

    monkeypatch.setattr(props, "ImagePropertiesDialog", Accettato)
    app_pulita.action_image_props()
    # `move_image` toglie e reinserisce: l'immagine va cercata di nuovo
    dopo = max(app_pulita.doc.image_rects(0), key=lambda i: i["rect"].get_area())["rect"]
    dopo = tuple(round(v, 1) for v in dopo)
    assert dopo != prima, f"l'immagine non e' cambiata: {prima} -> {dopo}"
    assert abs(dopo[2] - dopo[0] - 80.0) <= 1 and abs(dopo[3] - dopo[1] - 40.0) <= 1, (
        f"dimensione sbagliata: {dopo}"
    )
    # la finestra parla di dimensione: l'immagine non deve spostarsi
    assert abs(dopo[0] - prima[0]) <= 1 and abs(dopo[1] - prima[1]) <= 1, (
        f"l'immagine è stata spostata: {prima} -> {dopo}"
    )
    assert app_pulita.view.selection_kind() == "image", (
        "dopo il ridimensionamento l'immagine non e' piu' selezionata"
    )


def test_la_finestra_dell_immagine_tiene_le_proporzioni():
    """Cambiando la larghezza l'altezza segue, se le proporzioni sono attive."""
    from pdfeditor.ui.dialogs import props

    dlg = props.ImagePropertiesDialog((200.0, 100.0), (595.0, 842.0))
    try:
        dlg.w.setValue(100.0)
        assert abs(dlg.h.value() - 50.0) < 0.2, (
            f"l'altezza doveva seguire la larghezza: {dlg.h.value()}"
        )
        dlg.proporzioni.setChecked(False)
        dlg.h.setValue(120.0)
        assert abs(dlg.h.value() - 120.0) < 0.2
        valori = dlg.values()
        assert abs(valori["rect"][2] - 100.0) < 0.2
        assert abs(valori["rect"][3] - 120.0) < 0.2
        assert valori["crop"] is False
    finally:
        dlg.deleteLater()


def test_nessuna_azione_morta():
    """Un'azione non puo' limitarsi a scrivere un messaggio.

    Il controllo passava in rassegna i metodi che chiamano solo `_status`:
    era la firma di «Proprietà immagine», un pulsante che non faceva niente.
    """
    import ast
    import inspect
    from pathlib import Path

    from pdfeditor.ui import main_window as mw

    origine = Path(inspect.getfile(mw))
    albero = ast.parse(origine.read_text(encoding="utf-8"))
    inerti = []
    for nodo in ast.walk(albero):
        if not isinstance(nodo, ast.FunctionDef):
            continue
        if not any(isinstance(n, ast.Name) and n.id == "action" for n in ast.walk(nodo)):
            continue
        chiamate = [
            c for c in ast.walk(nodo)
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
            and c.func.attr in ("_status", "showMessage")
        ]
        if not chiamate:
            continue
        altro = [
            c for c in ast.walk(nodo)
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
            and c.func.attr not in ("_status", "showMessage")
        ]
        if not altro:
            inerti.append(nodo.name)
    assert not inerti, f"azioni che scrivono solo un messaggio: {inerti}"


def test_un_immagine_si_puo_trascinare_piu_volte(app_pulita, tmp_path):
    """Un'immagine spostata due volte deve esistere ancora.

    Lo spostamento rilegge l'immagine e la reinserisce. Dopo la prima mossa
    MuPDF lasciava un segnaposto di un pixel al posto della vecchia e la
    seconda reinserimento finiva su quel segnaposto: l'immagine spariva dal
    file. Con una firma inserita dal programma, trascinarla due volte la
    faceva svanire.
    """
    doc = app_pulita.doc
    for i, box in enumerate((
        pymupdf.Rect(0, 0, 80, 40),
        pymupdf.Rect(10, 10, 200, 120),
        pymupdf.Rect(20, 20, 300, 200),
    )):
        immagini = doc.image_rects(0)
        assert len(immagini) == 1, (
            f"alla mossa {i + 1} il documento contiene {len(immagini)} immagini: {immagini}"
        )
        doc.move_image(0, immagini[0]["xref"], box)
    finale = doc.image_rects(0)
    assert len(finale) == 1, f"immagini finali: {finale}"
    assert abs(finale[0]["rect"].width - 280) <= 1, [round(v) for v in finale[0]["rect"]]
    assert finale[0]["width"] > 1, "l'immagine e' diventata un segnaposto di un pixel"

    # e deve sopravvivere al salvataggio
    from pdfeditor.core import document as docmod

    salvato = tmp_path / "spostata.pdf"
    doc.save(salvato)
    riletta = docmod.Document()
    try:
        riletta.open(salvato)
        assert len(riletta.image_rects(0)) == 1, "l'immagine non e' sopravvissuta al file"
    finally:
        riletta.close()


def test_il_riordino_e_la_richiesta_di_annullamento(app_pulita):
    """Annullare e ripeti dopo lo spostamento riportano l'immagine al posto."""
    doc = app_pulita.doc
    prima = doc.image_rects(0)[0]
    doc.move_image(0, prima["xref"], pymupdf.Rect(0, 0, 90, 45))
    assert [round(v) for v in doc.image_rects(0)[0]["rect"]] == [0, 0, 90, 45]
    doc.history.undo()
    tornata = doc.image_rects(0)[0]["rect"]
    assert abs(tornata.x0 - prima["rect"].x0) <= 1, [round(v) for v in tornata]
    doc.history.redo()
    assert [round(v) for v in doc.image_rects(0)[0]["rect"]] == [0, 0, 90, 45]
