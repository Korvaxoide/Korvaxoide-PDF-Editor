"""Test di regressione sui difetti trovati esaminando l'editor voce per voce.

Ogni test descrive il guasto e perché il correttivo è necessario: senza la
spiegazione il test diventa un NUMBER casuale che nessuno sa più perché esiste.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path

import numpy as np
import pymupdf
import pytest
from PIL import Image, ImageDraw

from pdfeditor.core import geometry as geo
from pdfeditor.core.document import Document, DocumentError


# ------------------------------------------------------------------ utilità


def _doc(pagine: int = 1, rot: int = 0, w: float = 400, h: float = 600) -> Document:
    d = pymupdf.open()
    for i in range(pagine):
        p = d.new_page(width=w, height=h)
        p.insert_text((40, 80), f"PAGINA {i}", fontsize=18)
        if rot:
            p.set_rotation(rot)
    doc = Document()
    doc._adopt(d)
    return doc


def _firma(alpha: bool = True, size=(400, 160)) -> bytes:
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.line((20, size[1] - 40, size[0] - 20, 40), fill=(16, 24, 40, 255), width=8)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _pixel_di_sfondo(doc: Document, pagina: int, punto: tuple[float, float]) -> tuple[int, ...]:
    """Colore del rendering in un punto della pagina (per verificare la trasparenza)."""
    pix = doc.render(pagina, zoom=2)
    return pix.pixel(int(punto[0] * 2), int(punto[1] * 2))


# ------------------------------------------------- la firma non diventa nera


def test_spostare_una_firma_conserva_il_canale_alpha():
    """Trascinare una firma non deve renderne nero lo sfondo.

    MuPDF salva un'immagine con alpha come RGB più una maschera ``/SMask``
    separata. ``extract_image`` restituisce solo i campi RGB, quindi la firma
    veniva reinserita senza la maschera e tornava con lo sfondo nero: ed è
    esattamente ciò che accadeva al primo trascinamento.
    """
    doc = _doc()
    doc.insert_image(0, geo.Rect(60, 100, 340, 200), _firma(), keep_proportion=False)
    assert _pixel_di_sfondo(doc, 0, (70, 190)) == (255, 255, 255)
    for passo in range(3):
        xref = doc.image_rects(0)[0]["xref"]
        doc.move_image(0, xref, geo.Rect(60 + 10 * passo, 300, 340 + 10 * passo, 400))
        assert _pixel_di_sfondo(doc, 0, (70 + 10 * passo, 390)) == (255, 255, 255), (
            f"sfondo nero dopo lo spostamento {passo + 1}"
        )


def test_estrarre_una_firma_conserva_la_trasparenza():
    doc = _doc()
    doc.insert_image(0, geo.Rect(60, 100, 340, 200), _firma(), keep_proportion=False)
    xref = doc.image_rects(0)[0]["xref"]
    dati = doc.extract_image(xref)
    assert Image.open(io.BytesIO(dati)).mode == "RGBA", "l'estrazione deve portare l'alpha"


def test_immagine_senza_alpha_restare_come_prima():
    """Il percorso senza ``/SMask`` non deve cambiare nulla."""
    buf = io.BytesIO()
    Image.new("RGB", (120, 60), (10, 120, 200)).save(buf, format="PNG")
    doc = _doc()
    doc.insert_image(0, geo.Rect(50, 100, 200, 160), buf.getvalue(), keep_proportion=False)
    xref = doc.image_rects(0)[0]["xref"]
    doc.move_image(0, xref, geo.Rect(80, 300, 230, 360))
    assert len(doc.image_rects(0)) == 1
    assert doc.image_rects(0)[0]["width"] == 120


# --------------------------------------------------- proprietà del campo modulo


def test_proprieta_del_campo_applicano_il_bordo():
    """«Proprietà del campo…» deve applicare tutto quello che chiede.

    ``Widget.border_style`` vuole una lettera; la finestra invia l'indice della
    tendina. L'assegnazione riusciva e il ``w.update()`` successivo sollevava
    ``AttributeError``, quindi nessuna proprietà veniva mai applicata.
    """
    doc = _doc()
    xref = doc.add_field(0, "text", geo.Rect(50, 100, 250, 130), "nome", "Mario")
    assert doc.set_field_properties(0, xref, {"field_name": "cognome", "border_style": 2})
    w = list(doc.page(0).widgets())[0]
    assert w.field_name == "cognome"
    assert doc.fields(0)[0].border_style in ("D", "Dashed")


def test_proprieta_del_campo_scrivono_la_descrizione():
    doc = _doc()
    xref = doc.add_field(0, "text", geo.Rect(50, 100, 250, 130), "nome", "")
    assert doc.set_field_tooltip(0, xref, "Scrivere in stampatello")
    assert doc.fields(0)[0].tooltip == "Scrivere in stampatello"


def test_proprieta_del_campo_che_non_esiste_non_sollevano():
    doc = _doc()
    assert doc.set_field_properties(0, 999999, {"field_name": "x"}) is False
    assert doc.set_field_tooltip(0, 999999, "x") is False


# ------------------------------------------------------------- duplicare pagine


def test_duplicare_piu_pagine_sceglie_quelle_giuste():
    """Con più pagine selezionate vanno duplicate proprio quelle.

    Ogni inserimento sposta in avanti gli indici successivi: procedendo
    dall'alto verso il basso la stessa pagina veniva duplicata due volte e una
    delle scelte non veniva duplicata affatto.
    """
    doc = _doc(pagine=5)
    prodotte = doc.duplicate_pages([0, 1])
    assert [doc.page(i).get_text().strip() for i in range(doc.page_count)] == [
        "PAGINA 0", "PAGINA 0", "PAGINA 1", "PAGINA 1", "PAGINA 2", "PAGINA 3", "PAGINA 4",
    ]
    assert prodotte == [1, 3], prodotte


def test_duplicare_tutte_le_pagine():
    doc = _doc(pagine=3)
    doc.duplicate_pages([0, 1, 2])
    assert doc.page_count == 6
    assert [doc.page(i).get_text().strip() for i in range(6)] == [
        "PAGINA 0", "PAGINA 0", "PAGINA 1", "PAGINA 1", "PAGINA 2", "PAGINA 2",
    ]
    assert doc.duplicate_pages([]) == []


def test_eliminare_una_pagna_inesistente_e_un_errore_chiaro():
    doc = _doc(pagine=3)
    with pytest.raises(DocumentError, match="non esiste"):
        doc.delete_pages([1, 99])
    assert doc.page_count == 3


# ----------------------------------------------------------------- protezione


def test_rimuovere_la_protezione_consente_di_salvare(tmp_path: Path):
    """Dopo «Rimuovi protezione» il documento deve restare salvevole.

    La rimozione non azzerava lo stato di cifratura: la modifica successiva
    veniva scambiata per una perdita di cifratura e da quel momento ogni
    salvataggio falliva, con un messaggio che invitava a rimuovere una
    protezione già rimossa.
    """
    sorgente = tmp_path / "protetto.pdf"
    d = pymupdf.open()
    d.new_page()
    d.save(
        str(sorgente),
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        owner_pw="proprietario",
        user_pw="utente",
    )
    d.close()
    doc = Document()
    doc.open(str(sorgente), "utente")
    assert doc.has_encryption
    doc.remove_encryption("proprietario")
    assert not doc.has_encryption
    doc.add_annot(0, "rect", geo.Rect(20, 20, 80, 80))
    assert doc._encryption_lost is False
    uscita = tmp_path / "sciolto.pdf"
    doc.save(uscita)
    assert uscita.exists()


# --------------------------------------------------------------- appiattimento


def test_appiattire_i_campi_non_tocca_le_annotazioni():
    doc = _doc()
    doc.add_field(0, "text", geo.Rect(50, 100, 250, 130), "campo", "valore")
    doc.add_annot(0, "rect", geo.Rect(100, 400, 200, 460))
    doc.flatten_fields()
    assert not doc.fields()
    assert len(doc.annots(0, include_widgets=False)) == 1


def test_appiattire_le_annotazioni_non_tocca_i_campi():
    doc = _doc()
    doc.add_field(0, "text", geo.Rect(50, 100, 250, 130), "campo", "valore")
    doc.add_annot(0, "rect", geo.Rect(100, 400, 200, 460))
    doc.flatten_annotations()
    assert len(doc.fields()) == 1
    assert not doc.annots(0, include_widgets=False)


# ---------------------------------------------------------------- pulsanti radio


def test_il_gruppo_di_pulsanti_di_opzione_ha_scelta_unica():
    doc = _doc()
    figli = doc.add_radio_group(
        0, [geo.Rect(40, 100, 58, 118), geo.Rect(66, 100, 84, 118), geo.Rect(92, 100, 110, 118)],
        "grp",
    )
    assert len(figli) == 3

    def accesi() -> list[str]:
        return [
            w.field_name for w in doc.page(0).widgets()
            if w.field_name != "grp" and w.field_value not in (False, "Off", "", None)
        ]

    doc.set_field_value(0, figli[0], True)
    assert accesi() == ["grp.grp#0"]
    doc.set_field_value(0, figli[2], True)
    assert accesi() == ["grp.grp#2"], "la scelta precedente deve spegnersi"
    doc.set_field_value(0, figli[2], True)
    assert accesi() == [], "ricliccare l'opzione attiva la deseleziona"


def test_ogni_opzione_ha_un_valore_uso():
    """Le opzioni devono esportare valori diversi.

    Con il solo ``/Yes`` di PyMuPDF due scelte diverse risultavano identiche
    per chi legge il file, e il campo padre non poteva dire quale fosse stata
    scelta.
    """
    doc = _doc()
    figli = doc.add_radio_group(
        0, [geo.Rect(40, 100, 58, 118), geo.Rect(66, 100, 84, 118)], "grp"
    )
    valori = set()
    for x in figli:
        doc.set_field_value(0, x, True)
        attivo = next(w for w in doc.page(0).widgets() if w.xref == x)
        valori.add(str(attivo.field_value or ""))
        assert doc.radio_is_on(0, x)
    assert len(valori) == 2 and "" not in valori, valori


def test_il_valore_del_campo_padre_segue_la_scelta():
    doc = _doc()
    figli = doc.add_radio_group(
        0, [geo.Rect(40, 100, 58, 118), geo.Rect(66, 100, 84, 118)], "grp", selected=1
    )
    grezzo = doc._require().tobytes()
    assert b"/V" in grezzo
    assert doc.radio_is_on(0, figli[1])
    assert not doc.radio_is_on(0, figli[0])


# ---------------------------------------------------- sostituzione del testo


def test_sostituire_una_parola_terne_corpo_colore_e_cornice():
    """La sostituzione deve mantenere stile e disegno di fondo.

    Prima lo stile veniva letto dopo la redazione, quindi il testo era
    sparito e la sostituzione usava sempre 11 pt neri; mancava inoltre
    ``overlay``, per cui il testo finiva sotto il resto della pagina, e il
    default cancellava le righe che toccavano la parola.
    """
    d = pymupdf.open()
    p = d.new_page(width=500, height=300)
    p.draw_line((60, 150), (300, 150), color=(0, 0, 0), width=1)
    p.insert_text((70, 140), "SEGRETO", fontsize=28, fontname="tibo", color=(0, 0, 1))
    doc = Document()
    doc._adopt(d)
    prima = [tuple(dr["rect"]) for dr in doc.page(0).get_drawings()]
    assert doc.replace_text("SEGRETO", "PUBBLICO") == 1
    assert "PUBBLICO" in doc.page(0).get_text()
    assert [tuple(dr["rect"]) for dr in doc.page(0).get_drawings()] == prima, (
        "la regola di fondo non deve sparire"
    )
    # il testo nuovo deve essere realmente visibile: la sostituzione non può
    # finire sotto il contenuto della pagina
    pix = doc.render(0, zoom=2)
    import numpy as np
    from PIL import Image as _I

    img = _I.frombytes("RGB", (pix.width, pix.height), pix.samples)
    fascia = np.asarray(img.convert("L").crop((int(60 * 2), int(105 * 2), int(300 * 2), int(150 * 2))))
    assert int((fascia < 150).sum()) > 200, "la sostituzione non si vede"


def test_l_intervallo_di_pagine_illeggibile_dice_perche():
    """Un intervallo scritto male va detto, non lasciato a Python.

    ``int()`` senza controllo lasciava emergere «invalid literal for int() with
    base 10: 'abc'» dalla finestra di esportazione.
    """
    from PySide6.QtWidgets import QApplication

    from pdfeditor.ui.dialogs.props import ExportDialog

    app = QApplication.instance() or QApplication([])
    dlg = ExportDialog(10)
    dlg.range.setText("abc-3")
    with pytest.raises(ValueError) as exc:
        dlg.parse_range()
    assert "non e' un numero" in str(exc.value)
    dlg.range.setText("1,1")
    assert dlg.parse_range() == [0], "la stessa pagina due volte va esportata una"
    dlg.range.setText("2-3")
    assert dlg.parse_range() == [1, 2]
    del app


# ------------------------------------------------------------ spazio pagine


def test_estrarre_una_pagna_inesistente_e_un_errore():
    """Chiedere la pagina 99 non deve produrre una pagina bianca in più."""
    doc = _doc(pagine=3)
    with pytest.raises(DocumentError, match="non esiste"):
        doc.extract_pages([0, 99])


def test_riordinare_le_pagine_accetta_un_iteratore():
    doc = _doc(pagine=3)
    doc.move_pages(iter([2, 1, 0]))
    assert [doc.page(i).get_text().strip() for i in range(3)] == [
        "PAGINA 2", "PAGINA 1", "PAGINA 0",
    ]


def test_spostare_una_pagna_inesistente_dice_perche():
    doc = _doc(pagine=2)
    with pytest.raises(DocumentError, match="non esiste"):
        doc.move_page(9, 0)


# ------------------------------------------------------------ numeri di pagina


@pytest.mark.parametrize("rotazione", [0, 90, 180, 270])
def test_il_numero_di_pagna_resta_sul_foglio_anche_ruotato(rotazione: int):
    """Il numero deve finire sul foglio, non fuori.

    La posizione era calcolata sul riquadro *mostrato*: su una pagina ruotata le
    misure hanno gli assi scambiati e il numero finiva fuori dal foglio, senza
    essere né visibile né estraibile.
    """
    doc = _doc(rot=rotazione)
    assert doc.add_page_numbers([0], position="bottom_right", fontsize=12, margin=20) == 1
    testo = doc.page(0).get_text()
    assert "1" in testo, f"rotazione {rotazione}: numero non nel testo ({testo!r})"


# --------------------------------------------------------------- copia del testo


@pytest.mark.parametrize("rotazione", [0, 90, 180, 270])
def test_copiare_il_testo_funziona_anche_su_pagina_ruotata(rotazione: int):
    d = pymupdf.open()
    p = d.new_page(width=400, height=600)
    p.insert_text((40, 300), "TEXTO DA COPIARE", fontsize=14)
    p.set_rotation(rotazione)
    doc = Document()
    doc._adopt(d)
    parole = doc.words_in_rect(0, doc.page_info(0).rect)
    assert parole, f"rotazione {rotazione}: nessuna parola trovata"
    unione = parole[0]
    for r in parole[1:]:
        unione = unione | r
    assert "TEXTO DA COPIARE" in doc.selected_text(0, geo.Rect(unione)), (
        f"rotazione {rotazione}: copia vuota"
    )


def test_estrarre_il_testo_di_una_pagina_ruotata():
    d = pymupdf.open()
    p = d.new_page(width=400, height=600)
    p.insert_text((40, 300), "RIGA UNICA", fontsize=14)
    p.set_rotation(90)
    doc = Document()
    doc._adopt(d)
    assert "RIGA UNICA" in doc.extract_text(0)


# ---------------------------------------------------------- posto libero pagine


def test_il_posto_libero_non_cede_sopra_al_testo():
    """Lo spazio libero va cercato dove il testo si vede.

    Blocchi di testo e immagini erano registrati nello spazio pagina mentre la
    ricerca avveniva in quello mostrato: su una pagina ruotata l'ostacolo finiva
    fuori dal foglio di lavoro e l'elemento finiva sopra il testo.
    """
    d = pymupdf.open()
    p = d.new_page(width=400, height=600)
    p.insert_text((40, 300), "TESTO CENTRALE", fontsize=14)
    p.set_rotation(90)
    doc = Document()
    doc._adopt(d)
    libero = doc.find_free_spot(0, 120, 40)
    mostrare = doc.to_display_rect(0, libero)
    parole = [r for r, _ in doc.words(0)]
    for r in parole:
        sovrapposizione = mostrare & r
        assert sovrapposizione.get_area() <= 0.01, (
            f"il posto libero {mostrare} copre il testo {r}"
        )


# ------------------------------------------------------------------ magnetismo


def test_il_magnetismo_aggancia_anche_in_verticale():
    """Agganci in orizzontale e in verticale insieme.

    Il flag di agganciamento veniva riusato fra i due assi: quello orizzontale
    spegneva il ciclo verticale dopo il primo candidato senza aver agganciato
    nulla, quindi allineare il bordo inferiore era impossibile.
    """
    from pdfeditor.core import geometry

    r = geometry.Rect(98, 112, 150, 142)
    target = geometry.Rect(100, 140, 140, 180)
    pagina = geometry.Rect(0, 0, 600, 800)
    res = geometry.compute_snap(r, [target], pagina, tol=4.0)
    assert res.snapped
    assert abs(res.x - r.x0 - 2) <= 0.5, "l'aggancio orizzontale non c'è"
    assert abs((res.y + r.height) - 140) <= 0.5, (
        f"il bordo inferiore non si è agganciato: fondo a {res.y + r.height}"
    )
    assert len(res.guides) >= 2, "manca la guida verticale"


# ----------------------------------------------------------------- libreria firme


def test_una_chiave_in_piu_nell_indice_non_fa_perdere_la_firma(tmp_path: Path):
    from pdfeditor.signature.manager import SignatureLibrary

    lib = SignatureLibrary(folder=tmp_path)
    lib.add_png(Image.new("RGBA", (10, 10), (255, 0, 0, 255)), name="prova")
    indice = tmp_path / "index.json"
    dati = json.loads(indice.read_text())
    dati[0]["note"] = "campo aggiunto da una versione futura"
    indice.write_text(json.dumps(dati))
    assert len(SignatureLibrary(folder=tmp_path).entries) == 1


def test_la_cartella_delle_firme_illeggibile_dice_perche(tmp_path: Path, monkeypatch):
    from pdfeditor.signature import manager

    sola_lettura = tmp_path / "ro"
    sola_lettura.mkdir()
    os.chmod(sola_lettura, 0o555)
    monkeypatch.setenv("XDG_DATA_HOME", str(sola_lettura))
    try:
        manager.library_dir()
    except manager.SignatureLibraryError as exc:
        assert "firm" in str(exc).lower()
    else:  # pragma: no cover - solo su sistemi che ignorano i permessi
        pytest.skip("il sistema consente la scrittura anche senza permessi")


def test_il_giro_tratti_conserva_penna_e_opacita():
    """Salvare e riaprire una firma non deve cambiarne l'aspetto."""
    from pdfeditor.signature import strokes as sk

    tela = sk.SignatureCanvas(width=300.0, height=120.0)
    tela.default_style.color = (200, 30, 30)
    tela.default_style.width = 4.2
    tela.default_style.opacity = 0.5
    tratto = tela.new_stroke(20, 60, 4.2)
    for x in range(21, 200):
        tratto.add(float(x), 60.0, 4.2)
    tratto.style.opacity = 0.5
    copia = sk.SignatureCanvas.from_dict(tela.to_dict())
    assert copia.default_style.color == (200, 30, 30)
    assert copia.default_style.width == 4.2
    assert copia.default_style.opacity == 0.5
    assert copia.strokes[0].style.opacity == 0.5
    assert copia.strokes[0].points == tratto.points


def test_il_ricampionamento_conserva_l_ultimo_punto():
    from pdfeditor.signature import strokes as sk

    assert sk.resample([(0.0, 0.0), (10.0, 0.0)], 0.35)[-1] == (10.0, 0.0)
    assert sk.resample([(0.0, 0.0), (3.0, 0.0)], 0.35)[-1] == (3.0, 0.0)


# --------------------------------------------------------- resa dei tratti firma


@pytest.mark.parametrize("scala", [1.0, 2.0, 4.0])
def test_lo_spessore_del_tratto_cresce_come_la_penna(scala: float):
    """La penna da 2,6 pt deve restare 2,6 pt moltiplicato per la scala.

    La scala entrava due volte nel raggio e il tratto veniva quattro volte
    più spesso del dovuto: a scala 4 una penna normale diventava una macchia.
    """
    import numpy as np
    from pdfeditor.signature import render, strokes as sk

    tela = sk.SignatureCanvas(width=200.0, height=60.0)
    tratto = tela.new_stroke(10, 30, 2.6)
    tratto.style.pressure = False
    for x in range(11, 190):
        tratto.add(float(x), 30.0, 2.6)
    img = render.render_strokes(tela, scale=scala, padding=0)
    alpha = np.asarray(img)[:, :, 3]
    colonna = alpha[:, alpha.shape[1] // 2]
    spessore = int((colonna > 128).sum())
    assert abs(spessore - 2.6 * scala) <= 1.5, (
        f"scala {scala}: spessore {spessore} invece di {2.6 * scala:.1f}"
    )


def test_la_firma_opaca_viene_ritagliata_lo_stesso():
    from pdfeditor.signature import render, strokes as sk

    tela = sk.SignatureCanvas(width=600.0, height=220.0)
    tratto = tela.new_stroke(20, 60, 3)
    for x in range(21, 200):
        tratto.add(float(x), 60.0, 3)
    trasparente = render.render_strokes(tela, scale=2.0, transparent=True)
    opaca = render.render_strokes(tela, scale=2.0, transparent=False)
    assert opaca.size == trasparente.size, "senza alpha il ritaglio non poteva funzionare"


def test_l_inchiostro_oltre_la_tela_non_viene_perso():
    from pdfeditor.signature import render, strokes as sk

    tela = sk.SignatureCanvas(width=200.0, height=100.0)
    tratto = tela.new_stroke(-60, 50, 3)
    for x in range(-59, 150):
        tratto.add(float(x), 50.0, 3)
    img = render.render_strokes(tela, scale=2.0, padding=0)
    import numpy as np

    colonne = int((np.asarray(img)[:, :, 3] > 128).any(axis=0).sum())
    assert colonne >= 210 * 2, f"inchiostro tagliato: {colonne} colonne su 420"


def test_una_firma_a_paletta_non_diventa_nera():
    from pdfeditor.signature import render

    img = Image.new("P", (20, 20), 0)
    img.putpalette([255, 255, 255] + [0, 0, 0] * 255)
    img.info["transparency"] = 0
    ImageDraw.Draw(img).line((0, 0, 19, 19), fill=1, width=3)
    assert render.to_jpeg_on_white(img)[:2] == b"\xff\xd8"
    assert render.flatten_for_pdf(img).mode == "RGB"
    assert render.flatten_for_pdf(img).getpixel((0, 0)) == (255, 255, 255), (
        "l'indice trasparente è diventato nero"
    )


# ------------------------------------------------------------- rimozione sfondo


def test_invertire_non_inverte_la_trasparenza():
    from pdfeditor.signature import bgremove

    img = Image.new("RGBA", (100, 40), (255, 255, 255, 255))
    ImageDraw.Draw(img).line((5, 30, 95, 10), fill=(0, 0, 0, 255), width=4)
    senza = np.asarray(bgremove.remove_background(img, bgremove.RemovalSettings(method="white", feather=0)))
    con = np.asarray(bgremove.remove_background(img, bgremove.RemovalSettings(method="white", invert=True, feather=0)))
    assert senza[2, 2, 3] == 0, "la carta deve restare trasparente"
    assert con[2, 2, 3] == 255, "invertendo la polarità la carta diventa contenuto"
    assert con[20, 50, 3] == 0, "il testo deve diventare trasparente"


def test_la_spazzola_da_raggio_negativo_non_solleva():
    from pdfeditor.signature import bgremove

    img = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
    ImageDraw.Draw(img).line((5, 20, 34, 20), fill=(0, 0, 0, 255), width=4)
    st = bgremove.RemovalSettings(method="none", erase_strokes=[(20, 20, -6)])
    out = bgremove.remove_background(img, st)  # non deve sollevare ValueError
    assert out is not None


def test_il_despeckle_toglie_il_grano_e_non_il_tratto():
    from pdfeditor.signature import bgremove

    img = Image.new("RGB", (60, 60), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.line((5, 5, 45, 45), fill=(0, 0, 0), width=1)   # tratto sottile
    d.point((55, 5), fill=(0, 0, 0))                   # macchiolina
    d.point((30, 55), fill=(0, 0, 0))
    st = bgremove.RemovalSettings(method="none", despeckle=3, feather=0, auto_crop=False)
    # «nessuna» restituisce l'immagine così com'è: qui si chiede la rimozione
    # dello sfondo, che è il caso in cui il grano si vede davvero
    st.method = "white"
    alpha = np.asarray(bgremove.remove_background(img, st))[:, :, 3]
    assert alpha[:50, :50].sum() > 0, "il tratto di penna è stato cancellato"
    assert alpha[5, 55] == 0 and alpha[55, 30] == 0, "le macchioline sono rimaste"


# --------------------------------------------------------------- firma digitata


def test_il_controllo_delle_lettere_applica_la_soglia():
    """La percentuale di copertura deve contare davvero.

    Il confronto usava ``min`` invece di ``max`` e valeva sempre vero: il
    controllo si riduceva a «almeno metà» e un font con poche lettere passava.
    """
    import pathlib
    from pdfeditor.signature import typed

    font = str(sorted(pathlib.Path("/usr/share/fonts").rglob("*.ttf"))[0])
    richieste = typed.LETTERE_FIRMA
    assert typed.ha_lettere(font, richieste, minimo=40)
    # un font che non ha nulla di quanto richiesto deve essere rifiutato
    assert not typed.ha_lettere(font, "中文字体沒有這些", minimo=40)


def test_la_firma_digitata_mette_maiuscole_e_minuscole_sulla_stessa_base():
    """Nel nome la maiuscola non deve galleggiare sopra le minuscole.

    Il glifo era centrato in verticale dentro la cella e poi sollevato di un
    pezzo fisso: con il valore predefinito la M di «Mario» restava sospesa
    qualche punto sopra il resto del nome.
    """
    from pdfeditor.signature import typed

    img = typed.render_typed(
        "Oo",
        typed.TypedStyle(
            size=88, ascender_height=1.0, rotate=0.0, slant=0.0,
            size_variation=0.0, spacing=0.2,
        ),
    )
    alpha = np.asarray(img)[:, :, 3] > 40
    colonne = np.where(alpha.any(axis=0))[0]
    assert colonne.size, "nessun glifo reso"
    # la lacuna fra i due glifi è la più lunga sequenza di colonne vuote interne
    vuote = [c for c in range(int(colonne[0]) + 1, int(colonne[-1])) if not alpha[:, c].any()]
    lacuna = []
    corrente: list[int] = []
    for c in vuote:
        if corrente and c != corrente[-1] + 1:
            lacuna = corrente
            corrente = []
        corrente.append(c)
    lacuna = corrente or lacuna
    assert lacuna, "i due glifi si toccano: la prova non distingue le basi"
    split = lacuna[len(lacuna) // 2]
    su = np.where(alpha[:, :split].any(axis=1))[0]
    gi = np.where(alpha[:, split:].any(axis=1))[0]
    assert len(su) and len(gi)
    fondo_maiuscola = int(su[-1])
    fondo_minuscola = int(gi[-1])
    assert abs(fondo_minuscola - fondo_maiuscola) <= 0.05 * 88, (
        f"la maiuscola galleggia {fondo_maiuscola - fondo_minuscola} px sopra la minuscola"
    )


def test_l_inclinazione_non_taglia_le_lettere_larghe():
    import numpy as np
    from pdfeditor.signature import typed

    diritto = typed.render_typed(
        "MW@lA", typed.TypedStyle(size=88, slant=0.0, rotate=0.0, size_variation=0.0, spacing=0.05)
    )
    inclinato = typed.render_typed(
        "MW@lA", typed.TypedStyle(size=88, slant=0.6, rotate=0.0, size_variation=0.0, spacing=0.05)
    )
    a = int((np.asarray(diritto)[:, :, 3] > 40).any(axis=0).sum())
    b = int((np.asarray(inclinato)[:, :, 3] > 40).any(axis=0).sum())
    assert b > 0, "l'inclinazione massima ha cancellato il testo"
    assert b >= a * 0.8, f"l'inclinazione ha perso inchiostro: {a} -> {b} colonne"


# ------------------------------------------------------------- qualità e OCR


def test_il_documento_senza_testo_alternativo_non_e_finora_segnalato_sempre():
    """``/Alt`` sta sugli elementi strutturali, non sull'oggetto immagine.

    Chiedendolo all'immagine la risposta è sempre «null» e ogni documento con
    una figura risultava segnalato, anche descritto, con un avviso che non si
    poteva correggere.
    """
    from pdfeditor.features import quality

    buf = io.BytesIO()
    Image.new("RGB", (300, 200), (200, 40, 40)).save(buf, "PNG")
    doc = _doc(w=595, h=842)
    doc.insert_image(0, pymupdf.Rect(50, 120, 545, 400), buf.getvalue(), keep_proportion=False)
    codici = [f.code for f in quality.accessibility_report(doc)]
    assert "struttura" in codici, "il documento non è strutturato: va segnalato quello"
    assert "immagini_alt" not in codici, "avviso non verificabile su un documento senza struttura"


def test_ocr_non_modifica_il_documento_se_non_riconosce_nulla(monkeypatch):
    from pdfeditor.ui import ocr

    doc = _doc()
    monkeypatch.setattr(ocr, "find_tesseract", lambda: "/bin/true")
    monkeypatch.setattr(ocr, "languages", lambda: ["ita"])
    monkeypatch.setattr(ocr, "extract_page_image", lambda *a, **k: b"", raising=False)
    monkeypatch.setattr(doc, "extract_page_image", lambda *a, **k: b"")
    ok, _msg = ocr.run_ocr(doc, "ita", 150, [0])
    assert ok is False
    assert not doc.dirty, "un OCR senza risultati non deve sporcare il documento"


import numpy as np  # noqa: E402  (usato dai test sopra)