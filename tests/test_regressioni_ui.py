"""Test di interazione sui difetti trovati esaminando l'editor voce per voce.

Ogni test passa dagli eventi reali (``QTest``), come quando preme un utente:
chiamare i metodi della vista direttamente nasconderebbe proprio i guasti
che si cercano qui — riquadri scritti nello spazio sbagliato, selezioni che
non partono, pannelli che non rispondono.
"""

from __future__ import annotations

import io
from pathlib import Path

import pymupdf
import pytest
from PIL import Image
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from pdfeditor.core import geometry as geo
from pdfeditor.core.document import Document
from pdfeditor.ui.main_window import MainWindow

ROTAZIONI = (0, 90, 180, 270)


# ----------------------------------------------------------------- utilità


def _pdf(pagine: int = 1, rot: int = 0, w: float = 400, h: float = 600) -> str:
    """Scrive un PDF di prova e ne restituisce il percorso."""
    import tempfile

    d = pymupdf.open()
    for i in range(pagine):
        p = d.new_page(width=w, height=h)
        p.insert_text((40, 80), f"PAGINA {i}", fontsize=18)
        if rot:
            p.set_rotation(rot)
    percorso = str(Path(tempfile.mkdtemp(prefix="korvaxoide-reg-")) / "prova.pdf")
    d.save(percorso)
    d.close()
    return percorso


@pytest.fixture()
def finestra_pagina(finestra, tmp_path):
    """Finestra con un documento di una pagina già caricato."""

    def _carica(rot: int = 0, pagine: int = 1) -> MainWindow:
        p = tmp_path / f"doc{rot}_{pagine}.pdf"
        d = pymupdf.open()
        for i in range(pagine):
            pg = d.new_page(width=400, height=600)
            pg.insert_text((40, 80), f"PAGINA {i}", fontsize=18)
            if rot:
                pg.set_rotation(rot)
        d.save(str(p))
        d.close()
        finestra.load_path(str(p))
        for _ in range(6):
            QApplication.instance().processEvents()
        return finestra

    return _carica


def _trascina(finestra: MainWindow, da: QPointF, a: QPointF, mods=Qt.NoModifier) -> None:
    vista = finestra.view
    vp = vista.viewport()
    p1 = vista.mapFromScene(da)
    p2 = vista.mapFromScene(a)
    QTest.mousePress(vp, Qt.LeftButton, mods, p1)
    QApplication.instance().processEvents()
    QTest.mouseMove(vp, p2)
    QApplication.instance().processEvents()
    QTest.mouseRelease(vp, Qt.LeftButton, mods, p2)
    for _ in range(4):
        QApplication.instance().processEvents()


def _scena(finestra: MainWindow, pagina: int, x: float, y: float) -> QPointF:
    nodo = finestra.view.scene_obj.node(pagina)
    return nodo.scenePos() + QPointF(x, y)


def _mostrato(finestra: MainWindow, pagina: int, r: geo.Rect) -> geo.Rect:
    return geo.Rect(finestra.doc.to_display_rect(pagina, r))


# ----------------------------------------------- disegno su pagina ruotata


@pytest.mark.parametrize("rot", ROTAZIONI)
def test_il_rettangolo_cade_dove_e_stato_disegnato(finestra_pagina, rot):
    """Lo strumento deve scrivere dove l'utente ha trascinato.

    Il riquadro arrivava dalla vista nello spazio mostrato e veniva consegnato
    al motore come se fosse già quello della pagina: su una pagina ruotata ogni
    forma finiva nell'angolo opposto, con gli assi scambiati.
    """
    finestra = finestra_pagina(rot)
    finestra.select_tool("rect")
    _trascina(finestra, _scena(finestra, 0, 100, 100), _scena(finestra, 0, 220, 190))
    annots = finestra.doc.annots(0, include_widgets=False)
    assert annots, "nessuna annotazione creata"
    mostrato = _mostrato(finestra, 0, annots[0]["rect"])
    for ottenuto, atteso in zip(
        (mostrato.x0, mostrato.y0, mostrato.x1, mostrato.y1), (100, 100, 220, 190)
    ):
        assert abs(ottenuto - atteso) <= 2.0, (
            f"rot={rot}: riquadro {mostrato} invece di (100, 100, 220, 190)"
        )


@pytest.mark.parametrize("rot", ROTAZIONI)
def test_la_linea_collega_i_due_punti_disegnati(finestra_pagina, rot):
    finestra = finestra_pagina(rot)
    finestra.select_tool("line")
    _trascina(finestra, _scena(finestra, 0, 80, 80), _scena(finestra, 0, 300, 260))
    annots = [a for a in finestra.doc.annots(0, include_widgets=False) if a["type"] == "Line"]
    assert annots, f"rot={rot}: nessuna linea creata"
    vertici = annots[0]["vertices"]
    assert len(vertici) >= 2
    for punto, (atteso_x, atteso_y) in zip(vertici[:2], ((80, 80), (300, 260))):
        mostrato = finestra.doc.to_display_rect(0, geo.Rect(*punto, *punto))
        assert abs(mostrato.x0 - atteso_x) <= 2 and abs(mostrato.y0 - atteso_y) <= 2, (
            f"rot={rot}: vertice {punto} cade in {mostrato}"
        )


@pytest.mark.parametrize("rot", ROTAZIONI)
def test_spostare_un_elemento_lo_segue_sul_cursore(finestra_pagina, rot):
    """Lo spostamento deve seguire il puntatore anche se la pagina è ruotata.

    Il delta veniva applicato al riquadro della pagina misurato in punti di
    schermo: su una pagina ruotata l'elemento scivolava nella direzione
    sbagliata e la cornice di selezione si staccava da lui.
    """
    finestra = finestra_pagina(rot)
    finestra.doc.add_annot(0, "rect", geo.Rect(100, 100, 200, 180))
    xref = finestra.doc.annots(0, include_widgets=False)[0]["xref"]
    prima = _mostrato(finestra, 0, geo.Rect(100, 100, 200, 180))
    finestra.select_tool("select")
    centro = ((prima.x0 + prima.x1) / 2, (prima.y0 + prima.y1) / 2)
    _trascina(
        finestra,
        _scena(finestra, 0, *centro),
        _scena(finestra, 0, centro[0] + 60, centro[1] + 40),
    )
    dopo = _mostrato(finestra, 0, finestra.doc.annot_rect(0, xref))
    assert abs(dopo.x0 - (prima.x0 + 60)) <= 3, f"rot={rot}: x {prima.x0} -> {dopo.x0}"
    assert abs(dopo.y0 - (prima.y0 + 40)) <= 3, f"rot={rot}: y {prima.y0} -> {dopo.y0}"


@pytest.mark.parametrize("rot", ROTAZIONI)
def test_ridimensionare_dalle_maniglie(finestra_pagina, rot):
    finestra = finestra_pagina(rot)
    finestra.doc.add_annot(0, "rect", geo.Rect(100, 100, 200, 180))
    xref = finestra.doc.annots(0, "rect")[0]["xref"]
    prima = _mostrato(finestra, 0, geo.Rect(100, 100, 200, 180))
    finestra.select_tool("select")
    finestra.view._select_hit(0, xref, geo.Rect(100, 100, 200, 180), "annot")
    QApplication.instance().processEvents()
    _trascina(
        finestra,
        _scena(finestra, 0, prima.x1, prima.y1),
        _scena(finestra, 0, prima.x1 + 50, prima.y1 + 30),
    )
    dopo = _mostrato(finestra, 0, finestra.doc.annot_rect(0, xref))
    assert abs(dopo.x1 - (prima.x1 + 50)) <= 3, f"rot={rot}: {prima} -> {dopo}"
    assert abs(dopo.y1 - (prima.y1 + 30)) <= 3, f"rot={rot}: {prima} -> {dopo}"
    assert abs(dopo.width - (prima.width + 50)) <= 4, "la larghezza è esplosa"


@pytest.mark.parametrize(
    "zona, punto, atteso",
    (
        ("se", (300, 230), (0.0, 50.0, 300.0, 230.0)),
        ("nw", (50, 75), (50.0, 75.0, 250.0, 205.0)),
        ("e", (300, 230), (0.0, 100.0, 300.0, 180.0)),
        ("n", (50, 75), (100.0, 75.0, 200.0, 205.0)),
        ("sw", (50, 230), (50.0, 50.0, 250.0, 230.0)),
    ),
)
def test_ridimensionare_dal_centro_con_alt(zona, punto, atteso):
    """Con Alt il riquadro cresce dal centro e la maniglia segue il puntatore.

    La formula mescolava due ternarye identiche e produceva un riquadro senza
    senso: con la maniglia nord-ovest il riquadro collassava a un punto.
    """
    from pdfeditor.ui.page_view import _resize_rect

    ottenuto = _resize_rect(geo.Rect(100, 100, 200, 180), zona, QPointF(*punto), Qt.AltModifier)
    for ottenuto_v, atteso_v in zip(
        (ottenuto.x0, ottenuto.y0, ottenuto.x1, ottenuto.y1), atteso
    ):
        assert abs(ottenuto_v - atteso_v) <= 1.0, f"{zona}: {ottenuto} invece di {atteso}"


def test_senza_alt_il_lato_opposto_resta_fermo():
    from pdfeditor.ui.page_view import _resize_rect

    ottenuto = _resize_rect(geo.Rect(100, 100, 200, 180), "se", QPointF(300, 230), Qt.NoModifier)
    assert abs(ottenuto.x0 - 100) <= 1 and abs(ottenuto.y0 - 100) <= 1


# ------------------------------------------------ trascinamento e corridoio


def test_un_elemento_non_cambia_pagina_durante_il_trascinamento(finestra_pagina):
    """Rilasciare fuori pagina non deve spostare l'elemento altrove.

    L'indice della pagina veniva ricalcolato sul punto di rilascio: un
    elemento trascinato verso la pagina successiva finiva su quella e la
    modifica non veniva applicata, quindi tornava indietro senza avviso.
    """
    finestra = finestra_pagina(0, pagine=2)
    finestra.doc.add_annot(0, "rect", geo.Rect(100, 100, 200, 180))
    xref = finestra.doc.annots(0, include_widgets=False)[0]["xref"]
    finestra.select_tool("select")
    nodo1 = finestra.view.scene_obj.node(1)
    _trascina(
        finestra,
        _scena(finestra, 0, 150, 140),
        nodo1.scenePos() + QPointF(150, 140),
    )
    assert finestra.doc.annot_rect(0, xref) is not None
    assert not finestra.doc.annots(1, include_widgets=False), (
        "l'elemento è comparso sulla pagina sbagliata"
    )


def test_il_clic_nel_corridoio_non_seleziona(finestra_pagina):
    """Fra due pagine non c'è pagina: niente deve essere selezionato.

    L'indicizzatore ricadeva sempre sull'ultima pagina, quindi un clic nel
    corridoio afferrava un elemento che non era sotto il cursore.
    """
    finestra = finestra_pagina(0, pagine=3)
    finestra.doc.add_annot(2, "rect", geo.Rect(100, 100, 200, 180))
    finestra.select_tool("select")
    nodo = finestra.view.scene_obj.node(2)
    punto = finestra.view.mapFromScene(
        nodo.scenePos() + QPointF(150, -6)
    )
    QTest.mouseClick(finestra.view.viewport(), Qt.LeftButton, Qt.NoModifier, punto)
    for _ in range(4):
        QApplication.instance().processEvents()
    assert finestra.view.selected_page() is None
    assert finestra.view.selection_xref() is None


def test_aprire_un_altro_file_non_lascia_una__selezione_fantasma(finestra_pagina):
    """Dopo aver aperto un altro file la selezione va azzerata.

    Restava l'indice della pagina precedente: copiare, tagliare o eliminare
    finivavano con «Indice pagina non valido».
    """
    finestra = finestra_pagina(0, pagine=3)
    finestra.doc.add_annot(2, "rect", geo.Rect(100, 100, 200, 180))
    finestra.select_tool("select")
    finestra.view._select_hit(2, finestra.doc.annots(2, include_widgets=False)[0]["xref"],
                              geo.Rect(100, 100, 200, 180), "annot")
    QApplication.instance().processEvents()
    finestra_pagina(0, pagine=1)
    assert finestra.view.selected_page() is None
    assert finestra.view.copy_selection() is False


# ------------------------------------------------------------ campi modulo


def test_il_campo_eliminato_non_apre_piu_l_editor(finestra_pagina):
    """Cancellato il campo, quel punto deve restare muto.

    Le informazioni del campo sopravvivevano alla cancellazione: cliccando nel
    punto si apriva una casella e quello che si digitava finiva nel nulla.
    """
    finestra = finestra_pagina(0)
    xref = finestra.doc.add_field(0, "text", geo.Rect(50, 100, 250, 130), "nome", "")
    finestra.view.load_field_states()
    assert (0, xref) in finestra.view.field_states
    finestra.doc.delete_annot(0, xref)
    finestra._on_doc_changed()
    assert (0, xref) not in finestra.view.field_states
    assert finestra.view.field_at(0, _scena(finestra, 0, 150, 115)) is None


def test_la_casella_di_spunta_resta_evidenziata(finestra_pagina):
    """Dopo averla spuntata deve continuare a sembrare un campo.

    Il campo attivo restava impostato sulla casella: il bordo spariva e al suo
    posto veniva dipinto un riquadro pieno.
    """
    finestra = finestra_pagina(0)
    finestra.doc.add_field(0, "checkbox", geo.Rect(50, 100, 70, 120), "accetto", False)
    finestra.view.load_field_states()
    QTest.mouseClick(
        finestra.view.viewport(), Qt.LeftButton, Qt.NoModifier,
        finestra.view.mapFromScene(_scena(finestra, 0, 60, 110)),
    )
    for _ in range(4):
        QApplication.instance().processEvents()
    assert finestra.view.active_field is None, "il campo è rimasto «in compilazione»"
    assert finestra.doc.fields(0)[0].value in ("Yes", True, "On")


def test_esc_chiude_l_editor_del_campo(finestra_pagina):
    finestra = finestra_pagina(0)
    xref = finestra.doc.add_field(0, "text", geo.Rect(50, 100, 250, 130), "nome", "")
    finestra.view.load_field_states()
    finestra.view.begin_field_edit(0, xref)
    QApplication.instance().processEvents()
    assert finestra.view._editor is not None
    QTest.keyClick(finestra.view._editor, Qt.Key_Escape)
    for _ in range(4):
        QApplication.instance().processEvents()
    assert finestra.view._editor is None
    assert finestra.view.active_field is None


def test_tab_passa_al_campo_successivo(finestra_pagina):
    """Tab va al campo dopo: la guida del programma lo prometteva.

    Prima Tab toglieva il focus e lasciava la casella disegnata sulla pagina,
    con la digitazione che andava a perdere.
    """
    finestra = finestra_pagina(0)
    primo = finestra.doc.add_field(0, "text", geo.Rect(50, 100, 250, 130), "nome", "")
    secondo = finestra.doc.add_field(0, "text", geo.Rect(50, 160, 250, 190), "cognome", "")
    finestra.view.load_field_states()
    finestra.view.begin_field_edit(0, primo)
    QApplication.instance().processEvents()
    QTest.keyClick(finestra.view._editor, Qt.Key_Tab)
    for _ in range(4):
        QApplication.instance().processEvents()
    assert finestra.view.active_field == (0, secondo)


def test_invio_chiude_l_editor_del_campo(finestra_pagina):
    finestra = finestra_pagina(0)
    xref = finestra.doc.add_field(0, "text", geo.Rect(50, 100, 250, 130), "nome", "")
    finestra.view.load_field_states()
    finestra.view.begin_field_edit(0, xref)
    QApplication.instance().processEvents()
    QTest.keyClick(finestra.view._editor, Qt.Key_Return)
    for _ in range(4):
        QApplication.instance().processEvents()
    assert finestra.view._editor is None


def test_il_pulsante_di_opzione_sceglie_una_sola_opzione(finestra_pagina):
    finestra = finestra_pagina(0)
    figli = finestra.doc.add_radio_group(
        0, [geo.Rect(40, 100, 58, 118), geo.Rect(66, 100, 84, 118)], "grp"
    )
    finestra.view.load_field_states()
    for punto in (49, 75):
        bersaglio = finestra.view.mapFromScene(
            finestra.view.scene_obj.node(0).scenePos() + QPointF(punto, 109)
        )
        QTest.mouseClick(finestra.view.viewport(), Qt.LeftButton, Qt.NoModifier, bersaglio)
        for _ in range(4):
            QApplication.instance().processEvents()
    accesi = [w.field_name for w in finestra.doc.page(0).widgets()
              if w.field_name != "grp" and w.field_value not in (False, "Off", "", None)]
    assert accesi == ["grp.grp#1"], accesi


# ------------------------------------------------------------- disegno a mano


def test_la_linea_mostra_un_anteprima_durante_il_trascinamento(finestra_pagina):
    """Durante il trascinamento deve esserci qualcosa sotto il cursore.

    La gomma elastica veniva disegnata solo nell'evento che concludeva il
    tracciato, quindi l'utente rilasciava «alla cieca».
    """
    finestra = finestra_pagina(0)
    finestra.select_tool("line")
    vp = finestra.view.viewport()
    p1 = finestra.view.mapFromScene(_scena(finestra, 0, 80, 80))
    p2 = finestra.view.mapFromScene(_scena(finestra, 0, 300, 260))
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, p1)
    QTest.mouseMove(vp, p2)
    for _ in range(3):
        QApplication.instance().processEvents()
    assert len(finestra.view.scene_obj.overlay.points) >= 2, (
        "nessuna anteprima durante il trascinamento"
    )
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, p2)
    for _ in range(3):
        QApplication.instance().processEvents()


def test_cambiare_strumento_a_meta_trascinamento_non_rompe_il_rilascio(finestra_pagina):
    finestra = finestra_pagina(0)
    finestra.select_tool("rect")
    vp = finestra.view.viewport()
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier,
                     finestra.view.mapFromScene(_scena(finestra, 0, 80, 80)))
    finestra.select_tool("ink")
    QTest.mouseMove(vp, finestra.view.mapFromScene(_scena(finestra, 0, 200, 200)))
    for _ in range(3):
        QApplication.instance().processEvents()
    assert finestra.view._moving == {}, "il trascinamento del vecchio strumento è rimasto vivo"
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier,
                       finestra.view.mapFromScene(_scena(finestra, 0, 200, 200)))
    for _ in range(3):
        QApplication.instance().processEvents()


# ------------------------------------------------------------- firma e firme


def test_la_firma_trascinata_non_diventa_nera(finestra_pagina):
    """La firma spostata deve restare trasparente fuori dal tracciato."""
    buf = io.BytesIO()
    img = Image.new("RGBA", (400, 160), (0, 0, 0, 0))
    from PIL import ImageDraw

    ImageDraw.Draw(img).line((20, 120, 380, 40), fill=(16, 24, 40, 255), width=8)
    img.save(buf, format="PNG")
    finestra = finestra_pagina(0)
    finestra.doc.insert_image(0, geo.Rect(60, 100, 340, 200), buf.getvalue(), keep_proportion=False)
    finestra._on_doc_changed()
    for passo in range(2):
        immagini = finestra.doc.image_rects(0)
        assert immagini, f"l'immagine è sparita dopo {passo} spostamenti"
        xref = immagini[0]["xref"]
        finestra.select_tool("select")
        centro = (200 + 10 * passo, 150)
        _trascina(
            finestra,
            _scena(finestra, 0, *centro),
            _scena(finestra, 0, centro[0] + 40, centro[1] + 60),
        )
        # un punto dentro il riquadro della firma ma lontano dal tracciato:
        # lì deve esserci la pagina, non un rettangolo nero
        riquadro = finestra.doc.image_rects(0)[0]["rect"]
        pix = finestra.doc.render(0, zoom=2)
        x = int((riquadro.x0 + 8) * 2)
        y = int((riquadro.y1 - 6) * 2)
        assert tuple(pix.pixel(x, y)) == (255, 255, 255), (
            f"lo sfondo della firma è diventato {tuple(pix.pixel(x, y))}"
        )


# ------------------------------------------------------------------ pannelli


def test_i_segnalibri_conservano_la_gerarchia(finestra_pagina):
    """L'elenco deve mostrare l'outline com'è nel documento.

    Il registro dei padri veniva ripulito includendo la voce appena inserita,
    quindi ogni segnalibro finiva al primo livello e la struttura si perdeva.
    """
    finestra = finestra_pagina(0, pagine=3)
    finestra.doc.set_outline([
        {"title": "Capitolo 1", "level": 1, "page": 0},
        {"title": "Paragrafo 1.1", "level": 2, "page": 1},
        {"title": "Sottoparagrafo", "level": 3, "page": 1},
        {"title": "Paragrafo 1.2", "level": 2, "page": 2},
        {"title": "Capitolo 2", "level": 1, "page": 2},
    ])
    pannello = finestra.panel_bookmarks
    pannello.load(finestra.doc)
    albero = pannello.tree
    assert albero.topLevelItemCount() == 2, (
        "il documento ha due capitoli di primo livello"
    )
    primo = albero.topLevelItem(0)
    assert primo.text(0) == "Capitolo 1"
    assert primo.childCount() == 2, primo.childCount()
    assert primo.child(0).childCount() == 1, "il sottoparagrafo ha perso il padre"


def test_rimuovere_un_segnalibro_annidato(finestra_pagina):
    finestra = finestra_pagina(0, pagine=3)
    finestra.doc.set_outline([
        {"title": "Padre", "level": 1, "page": 0},
        {"title": "Figlio", "level": 2, "page": 1},
    ])
    pannello = finestra.panel_bookmarks
    pannello.load(finestra.doc)
    pannello.tree.setCurrentItem(pannello.tree.topLevelItem(0).child(0))
    pannello._remove()
    rimasti = [e["title"] for e in finestra.doc.outline()]
    assert rimasti == ["Padre"], rimasti


def test_i_commenti_rispondono(finestra_pagina):
    """Vai, rispondi ed elimina devono arrivare al commento giusto.

    Ogni voce portava l'indice del totale invece della propria posizione, e i
    tre comandi uscivano subito perché quell'indice non esisteva.
    """
    finestra = finestra_pagina(0, pagine=2)
    for i, titolo in enumerate(("Primo", "Secondo", "Terzo")):
        xref = finestra.doc.add_annot(0, "note", geo.Rect(40 + 30 * i, 300, 55 + 30 * i, 315), text=titolo)
        assert xref
    pannello = finestra.panel_comments
    navigati: list[tuple[int, object]] = []
    pannello.navigate.connect(lambda page, rect: navigati.append((page, rect)))
    pannello.load(finestra.doc)
    assert pannello.list.count() == 3
    for riga, atteso in enumerate(("Primo", "Secondo", "Terzo")):
        pannello.list.setCurrentRow(riga)
        pannello._go(pannello.list.item(riga))
    assert len(navigati) == 3, navigati
    assert all(p == 0 for p, _ in navigati)


def test_il_commento_giusto_viene_eliminato(finestra_pagina):
    finestra = finestra_pagina(0)
    xref = finestra.doc.add_annot(0, "note", geo.Rect(40, 300, 55, 315), text="da eliminare")
    pannello = finestra.panel_comments
    eliminati: list[int] = []
    pannello.delete_requested.connect(lambda page, x: eliminati.append(x))
    pannello.load(finestra.doc)
    pannello.list.setCurrentRow(0)
    pannello._delete()
    assert eliminati == [xref], eliminati


def test_correggi_selezionato_funziona_nella_scheda_di_pretampa(finestra_pagina):
    """Il pulsante deve abilitarsi anche nell'elenco di pre-stampa.

    Solo la selezione nell'elenco di accessibilità lo abilitava, quindi le
    correzioni di pre-stampa (OCR, protezione, peso del file) erano irraggiungibili.
    """
    finestra = finestra_pagina(0)
    pannello = finestra.panel_quality
    pannello.load(finestra.doc)
    pannello.tabs.setCurrentIndex(1)   # Pre-stampa
    QApplication.instance().processEvents()
    if pannello.print_list.topLevelItemCount() == 0:
        pytest.skip("nessun problema di pre-stampa su questo documento")
    pannello.print_list.setCurrentItem(pannello.print_list.topLevelItem(0))
    QApplication.instance().processEvents()
    assert pannello._selected_action() != "" or not pannello.fix_button.isEnabled() is False
    if pannello._selected_action():
        assert pannello.fix_button.isEnabled(), (
            "la correzione esiste ma il pulsante resta disabilitato"
        )


def test_la_cifratura_e_dichiarata_giusta(finestra_pagina):
    """Un PDF senza protezione non deve dichiararsi cifrato.

    La tabella delle costanti era sfalsata di una posizione: ogni algoritmo
    veniva letto come il precedente e AES-256 risultava sconosciuto.
    """
    finestra = finestra_pagina(0)
    finestra.panel_props.load(finestra.doc)
    testo = finestra.panel_props.info.text()
    assert "Cifratura: nessuna" in testo, testo


# ------------------------------------------------------------------ stampa


def test_la_stampa_riceve_l_intervallo_e_la_risoluzione(finestra_pagina, monkeypatch):
    """«Stampa…» deve passare i dati giunti alla funzione di stampa.

    La funzione non accettava il parametro ``dpi`` e non leggeva l'intervallo
    scelto: la stampa non partiva e, anche se fosse partita, avrebbe stampato
    tutto il documento.
    """
    import inspect

    from pdfeditor.ui import printing

    firma = inspect.signature(printing.render_to_printer)
    assert "dpi" in firma.parameters, "manca il parametro dpi"
    assert "page_range" in firma.parameters

    finestra = finestra_pagina(0, pagine=3)
    chiamate: list[tuple] = []

    class DialogoAccettato:
        Accepted = 1

        def __init__(self, *_a, **_k):
            pass

        def setWindowTitle(self, *_a):
            pass

        def exec(self):
            return 1  # Accepted

    class Stampante:
        HighResolution = 1

        def __init__(self, *_a):
            self._da, self._a = 2, 3

        def setFromTo(self, da, a):
            pass

        def fromPage(self):
            # ciò che l'utente ha scelto nella finestra
            return 2

        def toPage(self):
            return 3

    monkeypatch.setattr(printing, "QPrintDialog", DialogoAccettato)
    monkeypatch.setattr(printing, "QPrinter", Stampante)
    monkeypatch.setattr(
        printing, "render_to_printer",
        lambda doc, printer, page_range=None, dpi=300: chiamate.append((page_range, dpi)),
    )
    printing.print_document(finestra, finestra.doc, dpi=200)
    assert chiamate, "la stampa non è stata avviata"
    (intervallo, dpi) = chiamate[0]
    assert intervallo == (1, 2), f"l'intervallo scelto non è stato letto: {intervallo}"
    assert dpi == 200


def test_l_esportazione_pdf_a_senza_ghostscript_produce_il_file(finestra_pagina, tmp_path, monkeypatch):
    """Senza Ghostscript il file deve comunque essere scritto.

    Il ramo riscriveva il file appena aperto: PyMuPDF lo rifiuta e l'utente
    riceveva «save to original must be incremental».
    """
    from pdfeditor.ui import printing

    finestra = finestra_pagina(0)
    uscita = tmp_path / "archiviato.pdf"
    monkeypatch.setattr(printing, "find_ghostscript", lambda: "")
    ok, messaggio = printing.convert_pdfa(finestra.doc, str(uscita), [0], "2b")
    assert uscita.exists() and uscita.stat().st_size > 0
    assert ok is False
    assert "Ghostscript" in messaggio


def test_i_metadati_del_documento_sono_su_nella_libreria(tmp_path):
    """L'esportazione non deve perdere titolo e autore.

    ``insert_pdf`` porta il contenuto ma non il dizionario delle informazioni:
    ogni file esportato risultava senza titolo né autore.
    """
    doc = Document()
    doc.new(595, 842)
    doc.insert_text_box(0, pymupdf.Rect(50, 50, 500, 120), "Relazione", fontsize=14)
    doc.set_metadata({"title": "Il mio documento", "author": "Mario Rossi"})
    uscita = tmp_path / "esportato.pdf"
    doc.export(str(uscita))
    meta = pymupdf.open(str(uscita)).metadata
    assert meta.get("title") == "Il mio documento"
    assert meta.get("author") == "Mario Rossi"

def test_il_campo_padre_del_gruppo_non_ruba_il_clic(finestra_pagina):
    """Il padre del gruppo non è un pulsante.

    Copre l'intera area delle opzioni: trattandolo come un pulsante, il clic
    su una qualunque opzione cadeva sul padre e le spegneva tutte.
    """
    finestra = finestra_pagina(0)
    figli = finestra.doc.add_radio_group(
        0, [geo.Rect(40, 100, 58, 118), geo.Rect(66, 100, 84, 118)], "grp"
    )
    campi = {f.name: f for f in finestra.doc.fields()}
    assert campi["grp"].is_group, "il padre non è riconosciuto come tale"
    assert not campi["grp.grp#0"].is_group
    finestra.view.load_field_states()
    nodo = finestra.view.scene_obj.node(0)
    bersaglio = finestra.view.mapFromScene(nodo.scenePos() + QPointF(75, 109))
    hit = finestra.view.field_at(0, nodo.scenePos() + QPointF(75, 109))
    assert hit == (0, figli[1]), hit
    QTest.mouseClick(finestra.view.viewport(), Qt.LeftButton, Qt.NoModifier, bersaglio)
    for _ in range(4):
        QApplication.instance().processEvents()
    assert finestra.doc.radio_is_on(0, figli[1])
    assert not finestra.doc.radio_is_on(0, figli[0])


def test_il_documento_non_riapre_l_editor_di_una_casella_di_spunta(finestra_pagina):
    """Spuntare una casella non deve riaprire il proprio editor.

    La ricostruzione della scena riapriva l'editor del campo attivo, che
    rispuntava la casella, che ricostruiva di nuovo: un ciclo che faceva
    sparire la pagina dalla vista.
    """
    finestra = finestra_pagina(0)
    xref = finestra.doc.add_field(0, "checkbox", geo.Rect(50, 100, 70, 120), "accetto", False)
    finestra.view.load_field_states()
    bersaglio = finestra.view.mapFromScene(_scena(finestra, 0, 60, 110))
    QTest.mouseClick(finestra.view.viewport(), Qt.LeftButton, Qt.NoModifier, bersaglio)
    for _ in range(4):
        QApplication.instance().processEvents()
    assert len(finestra.view.scene_obj.nodes) == finestra.doc.page_count, (
        "la pagina è sparita dalla vista dopo aver spuntato la casella"
    )
    assert finestra.view.active_field is None
    assert xref


# --------------------------------------------------- deselezione del testo


def _finestra_con_testo(finestra, tmp_path):
    """Finestra con una pagina che ha testo nella parte alta e bianco sotto."""
    p = tmp_path / "testo.pdf"
    d = pymupdf.open()
    pg = d.new_page(width=400, height=600)
    pg.insert_text((40, 80), "Relazione annuale", fontsize=14)
    d.save(str(p))
    d.close()
    finestra.load_path(str(p))
    for _ in range(6):
        QApplication.instance().processEvents()
    return finestra


def test_un_clic_deseleziona_il_testo(finestra, tmp_path):
    """Cliccando nel vuoto l'evidenziazione del testo deve sparire.

    Il clic puliva la selezione degli elementi ma non quella del testo, e la
    parola restava evidenziata finche' non si sceglieva altro testo: non c'era
    modo di toglierla con un clic.
    """
    finestra = _finestra_con_testo(finestra, tmp_path)
    vista = finestra.view
    _trascina(finestra, _scena(finestra, 0, 30, 70), _scena(finestra, 0, 230, 90))
    assert vista.selected_text().strip(), "la selezione del testo non è partita"
    assert vista.scene_obj.text_selection.rects, "nessuna parola evidenziata"

    bersaglio = vista.mapFromScene(_scena(finestra, 0, 200, 500))
    QTest.mouseClick(vista.viewport(), Qt.LeftButton, Qt.NoModifier, bersaglio)
    for _ in range(4):
        QApplication.instance().processEvents()
    assert not vista.scene_obj.text_selection.rects, (
        "il testo è rimasto evidenziato dopo il clic"
    )
    assert vista.selected_text() == ""
    assert vista._text_selection is None


def test_il_clic_deseleziona_anche_fuori_dalla_pagina(finestra, tmp_path):
    """Anche il clic nel corridoio fra le pagine toglie l'evidenziazione."""
    finestra = _finestra_con_testo(finestra, tmp_path)
    vista = finestra.view
    vista.select_all_text()
    assert vista.scene_obj.text_selection.rects
    bersaglio = vista.mapFromScene(_scena(finestra, 0, 200, -60))
    QTest.mouseClick(vista.viewport(), Qt.LeftButton, Qt.NoModifier, bersaglio)
    for _ in range(4):
        QApplication.instance().processEvents()
    assert not vista.scene_obj.text_selection.rects
    assert vista.selected_text() == ""


def test_dopo_un_clic_si_puo_riselezionare(finestra, tmp_path):
    """Il clic che deseleziona non deve rompere il rettangolo di selezione."""
    finestra = _finestra_con_testo(finestra, tmp_path)
    vista = finestra.view
    vista.select_all_text()
    bersaglio = vista.mapFromScene(_scena(finestra, 0, 200, 500))
    QTest.mouseClick(vista.viewport(), Qt.LeftButton, Qt.NoModifier, bersaglio)
    for _ in range(4):
        QApplication.instance().processEvents()
    _trascina(finestra, _scena(finestra, 0, 30, 70), _scena(finestra, 0, 230, 90))
    assert vista.selected_text().strip(), (
        "dopo aver deselezionato il testo non si può più selezionare"
    )


# ------------------------------------------------------- salvataggio sul file


def test_salvare_senza_modifiche_sovrascrive_il_file(finestra, tmp_path):
    """Salvare un documento appena aperto deve riscrivere il file.

    MuPDF rifiuta la riscrittura completa sul file da cui il documento è stato
    aperto e chiede un salvataggio incrementale: ``Document.save`` non se ne
    accorgeva e il salvataggio falliva sempre con «save to original must be
    incremental», con o senza modifiche.
    """
    finestra._error = lambda exc, titolo="": pytest.fail(
        f"il salvataggio ha sollevato {type(exc).__name__}: {exc}"
    )
    p = tmp_path / "prova.pdf"
    d = pymupdf.open()
    d.new_page(width=400, height=600)
    d.save(str(p))
    d.close()
    finestra.load_path(str(p))
    for _ in range(6):
        QApplication.instance().processEvents()
    assert not finestra.doc.dirty

    finestra.file_save()
    for _ in range(4):
        QApplication.instance().processEvents()
    assert finestra.doc.path == p
    assert pymupdf.open(str(p)).page_count == 1
    assert list(tmp_path.glob("*.tmp")) == [], "resta un provvisorio sul disco"


def test_salvare_dopo_una_modifica_sovrascrive_il_file(finestra, tmp_path):
    """Lo stesso deve valere quando il documento è stato modificato."""
    finestra._error = lambda exc, titolo="": pytest.fail(
        f"il salvataggio ha sollevato {type(exc).__name__}: {exc}"
    )
    p = tmp_path / "prova2.pdf"
    d = pymupdf.open()
    d.new_page(width=400, height=600)
    d.save(str(p))
    d.close()
    finestra.load_path(str(p))
    for _ in range(6):
        QApplication.instance().processEvents()
    finestra.pages_rotate(90)
    for _ in range(4):
        QApplication.instance().processEvents()
    assert finestra.doc.dirty

    finestra.file_save()
    for _ in range(4):
        QApplication.instance().processEvents()
    assert not finestra.doc.dirty
    assert int(pymupdf.open(str(p))[0].rotation) == 90


# ------------------------------------------------------------------- icone


def _disegno_icona(nome: str, lato: int = 32):
    """Rendering dell'icona come immagine, per confrontarla pixel a pixel."""
    from PySide6.QtGui import QImage, QPainter

    from pdfeditor.ui import icons

    img = QImage(lato, lato, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    icons.DRAWERS[nome](lato, "#000000")(p)
    p.end()
    return img


def _forma(img):
    """Firma del disegno: la fila dei pixel coperti, riga per riga."""
    return tuple(
        "".join(
            "#" if img.pixelColor(x, y).alpha() > 128 else "." for x in range(img.width())
        )
        for y in range(img.height())
    )


@pytest.mark.parametrize(
    "annulla, ruota",
    [("undo", "rotate-left"), ("redo", "rotate-right")],
)
def test_annulla_e_ripeti_non_sono_le_icone_di_rotazione(annulla, ruota):
    """Le icone di annulla e ripeti devono essere frecce dritte, non archi.

    Erano le stesse frecce circolari della rotazione: nella barra i quattro
    pulsanti di annulla, ripeti, ruota a sinistra e ruota a destra sembravano
    due coppie identiche.
    """
    freccia = _forma(_disegno_icona(annulla))
    arco = _forma(_disegno_icona(ruota))
    assert freccia != arco, f"{annulla} e {ruota} hanno la stessa forma"


@pytest.mark.parametrize("nome", ["undo", "redo"])
def test_le_frecce_di_annulla_e_ripeti_sono_orizzontali(nome):
    """La freccia deve essere piu' larga che alta: e' una freccia, non un arco."""
    img = _disegno_icona(nome)
    scuri = [
        (x, y)
        for y in range(img.height())
        for x in range(img.width())
        if img.pixelColor(x, y).alpha() > 128
    ]
    xs = [x for x, _ in scuri]
    ys = [y for _, y in scuri]
    assert scuri, "l'icona e' vuota"
    assert max(xs) - min(xs) > max(ys) - min(ys), (
        f"{nome}: il disegno e' piu' alto che largo, sembra un arco"
    )


def test_annulla_e_ripeti_sono_mirrati():
    """Annulla e ripeti devono guardare in versi opposti."""
    sinistra = _forma(_disegno_icona("undo"))
    destra = _forma(_disegno_icona("redo"))
    assert destra == tuple(r[::-1] for r in sinistra), (
        "annulla e ripeti non sono uno la specular dell'altro"
    )
