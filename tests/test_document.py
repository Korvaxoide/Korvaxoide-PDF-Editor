"""Test del modello di documento: pagine, testo, annotazioni, campi, sicurezza."""

from __future__ import annotations

import io
import os
from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from pdfeditor.core import document, geometry as geo
from pdfeditor.core.document import Document, DocumentError


@pytest.fixture()
def doc() -> Document:
    d = Document()
    d.new(595, 842)
    yield d
    d.close()


@pytest.fixture()
def tmp_pdf(tmp_path: Path) -> Path:
    p = tmp_path / "prova.pdf"
    d = Document()
    d.new()
    d.insert_text_box(0, pymupdf.Rect(50, 50, 500, 120), "Documento di prova\nSeconda riga", fontsize=14)
    d.save(p)
    d.close()
    return p


# ------------------------------------------------------------------- ciclo di vita


def test_creazione_documento(tmp_path: Path):
    d = Document()
    d.new()
    assert d.page_count == 1
    assert d.is_open and d.dirty
    p = tmp_path / "nuovo.pdf"
    d.save(p)
    assert p.exists()
    d.close()


def test_apertura_riapertura(tmp_pdf: Path):
    d = Document()
    d.open(tmp_pdf)
    assert d.page_count == 1
    assert "Documento di prova" in d.text(0)
    d.close()


def test_apertura_file_inesistente():
    d = Document()
    with pytest.raises(DocumentError):
        d.open("/percorso/che/non/esiste.pdf")
    d.close()


def test_apertura_file_non_pdf(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("ciao", encoding="utf-8")
    d = Document()
    with pytest.raises(DocumentError):
        d.open(f)
    d.close()


# ---------------------------------------------------------------------- pagine


def test_inserimento_e_eliminazione_pagine(doc: Document):
    doc.insert_page(1)
    doc.insert_page(0)
    assert doc.page_count == 3
    doc.delete_pages([0])
    assert doc.page_count == 2


def test_non_si_eliminano_tutte_le_pagine(doc: Document):
    with pytest.raises(DocumentError):
        doc.delete_pages([0])


def test_duplicazione_pagina(doc: Document):
    doc.insert_text_box(0, pymupdf.Rect(50, 50, 400, 90), "Titolo unico", fontsize=18)
    doc.duplicate_pages([0])
    assert doc.page_count == 2
    assert "Titolo unico" in doc.text(1)


def test_riordino_pagine(doc: Document):
    for i in range(3):
        doc.insert_text_box(0, pymupdf.Rect(50, 100 + i * 30, 400, 125 + i * 30), f"Marcatore {i}", fontsize=11)
    doc.duplicate_pages([0])
    doc.duplicate_pages([0])
    assert doc.page_count == 3
    doc.move_page(2, 0)
    assert doc.page_count == 3
    with pytest.raises(DocumentError):
        doc.move_pages([0, 0, 1])


def test_rotazione_pagina(doc: Document):
    doc.rotate_pages([0], 90)
    assert doc.page_info(0).rotation == 90
    w, h = doc.page_points(0)
    assert w > h  # ruotata di 90 gradi


def test_estrazione_pagine(doc: Document):
    doc.insert_page(1)
    sub = doc.extract_pages([1])
    assert sub.page_count == 1
    sub.close()


def test_mappatura_rect_rispetta_il_rendering(doc: Document):
    """Il rettangolo visualizzato deve combaciare con il rendering ruotato."""
    import numpy as np

    for pdf_rot in (0, 90, 180, 270):
        for view_rot in (0, 90, 180, 270):
            d = Document()
            d.new(400, 600)
            d.doc[0].set_rotation(pdf_rot)
            d.add_annot(0, "rect", pymupdf.Rect(40, 60, 140, 160), color=(1, 0, 0))
            d._view_rot[0] = view_rot
            disp = d.to_display_rect(0, pymupdf.Rect(40, 60, 140, 160))
            back = d.to_page_rect(0, disp)
            assert (back.x0, back.y0, back.x1, back.y1) == pytest.approx((40, 60, 140, 160))
            pix = d.render(0, zoom=2.0)
            arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.stride)[:, : pix.width * 3]
            arr = arr.reshape(pix.height, pix.width, 3)
            rosso = (arr[:, :, 0] > 200) & (arr[:, :, 1] < 80) & (arr[:, :, 2] < 80)
            ys, xs = np.where(rosso)
            assert len(xs) > 0
            for got, exp in ((xs.min(), disp.x0 * 2), (xs.max(), disp.x1 * 2),
                             (ys.min(), disp.y0 * 2), (ys.max(), disp.y1 * 2)):
                assert abs(int(got) - exp) <= 3
            d.close()


def test_ricerca_spazio_libero_non_sovrappone(doc: Document):
    from PIL import Image

    rects = []
    for _ in range(3):
        r = doc.find_free_spot(0, 160, 50)
        rects.append(r)
        buf = io.BytesIO()
        Image.new("RGBA", (160, 50), (10, 10, 10, 255)).save(buf, "PNG")
        doc.insert_image(0, r, buf.getvalue(), keep_proportion=False)
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            a, b = rects[i], rects[j]
            assert not (a.intersects(b) and not (a & b).is_empty)


# ------------------------------------------------------------------------ testo


def test_inserimento_casella_di_testo(doc: Document):
    res = doc.insert_text_box(0, pymupdf.Rect(50, 50, 450, 140), "Testo di prova", fontsize=12)
    assert res["spare"] >= 0
    assert "Testo di prova" in doc.text(0)


def test_testo_troppo_grande_segnalato(doc: Document):
    res = doc.insert_text_box(0, pymupdf.Rect(50, 50, 200, 70), "parola " * 60, fontsize=14)
    assert res["spare"] < 0


def test_ridimensionamento_testo(doc: Document):
    # riquadro abbastanza grande: il testo deve entrare riducendo il corpo
    res = doc.insert_text_box(0, pymupdf.Rect(50, 50, 260, 110), "parola " * 14, fontsize=28, fit="shrink")
    assert res["fontsize"] < 28
    assert res["spare"] >= 0


def test_crescita_automatica(doc: Document):
    piccolo = doc.insert_text_box(0, pymupdf.Rect(50, 50, 450, 70), "riga\n" * 6, fontsize=12, fit="grow")
    assert piccolo["rect"].height > 20


def test_nessuna_doppia_scrittura(doc: Document):
    """La sonda di adattamento non deve lasciare testo nell'anteprima."""
    doc.insert_text_box(0, pymupdf.Rect(50, 50, 260, 110), "una sola volta", fontsize=28, fit="shrink")
    assert doc.text(0).count("una sola volta") == 1


def test_sostituzione_testo(doc: Document):
    doc.insert_text_box(0, pymupdf.Rect(50, 50, 450, 80), "Vecchio valore", fontsize=12)
    n = doc.replace_text("Vecchio", "Nuovo")
    assert n >= 1
    assert "Nuovo" in doc.text(0)


def test_ricerca_sensibile_al_caso(doc: Document):
    doc.insert_text_box(0, pymupdf.Rect(50, 50, 450, 80), "Parola", fontsize=12)
    assert len(doc.search("parola", case=False)) == 1
    # sensibile al caso: nel testo c'e' «Parola»
    assert len(doc.search("Parola", case=True)) == 1
    assert len(doc.search("parola", case=True)) == 0
    assert len(doc.search("PAROLA", case=True)) == 0


# ---------------------------------------------------------------- annotazioni


@pytest.mark.parametrize(
    "kind",
    ["highlight", "underline", "strikeout", "squiggly", "rect", "circle", "ink", "note", "stamp"],
)
def test_creazione_annotazioni(doc: Document, kind: str):
    kwargs: dict = {"color": (0.8, 0.1, 0.1), "width": 1.5}
    if kind in ("ink",):
        kwargs["vertices"] = [(10, 10), (40, 50), (80, 20)]
    if kind == "note":
        kwargs["text"] = "nota"
    xref = doc.add_annot(0, kind, pymupdf.Rect(50, 50, 200, 120), **kwargs)
    assert xref > 0
    assert len(doc.annots(0, include_widgets=False)) == 1


def test_annotazione_freccia_punta(doc: Document):
    xref = doc.add_annot(0, "arrow", pymupdf.Rect(0, 0, 1, 1), vertices=[(10, 10), (100, 80)],
                         color=(0, 0, 0.5))
    kind, value = doc.xref_key(xref, "LE")
    assert kind == "array"
    assert "/R" in value


def test_forma_non_supportata(doc: Document):
    with pytest.raises(DocumentError):
        doc.add_annot(0, "inesistente", pymupdf.Rect(0, 0, 10, 10))


def test_eliminazione_annotazione(doc: Document):
    xref = doc.add_annot(0, "rect", pymupdf.Rect(50, 50, 150, 120), color=(1, 0, 0))
    assert len(doc.annots(0, include_widgets=False)) == 1
    doc.delete_annot(0, xref)
    assert len(doc.annots(0, include_widgets=False)) == 0


def test_collegamento_non_e_annotazione(doc: Document):
    doc.add_annot(0, "link", pymupdf.Rect(50, 50, 200, 70), text="https://esempio.it")
    assert len(doc.annots(0, include_widgets=False)) == 0
    assert any(l["uri"] == "https://esempio.it" for l in doc.links(0))


def test_spostare_un_annotazione_non_la_ingrandisce(doc: Document):
    """Ogni spostamento deve spostare, non far crescere il riquadro.

    PyMuPDF scrive il ``/Rect`` di un'annotazione includendo il bordo, quindi
    riscrivere il valore letto lo gonfiava di due punti per lato a ogni mossa:
    un rettangolo da 100x60, spostato quattro volte, arrivava a 110x70 e
    continuava a crescere. Il riquadro va quindi deflatato del bordo prima di
    essere riscritto.
    """
    xref = doc.add_annot(0, "rect", pymupdf.Rect(100, 600, 200, 660), color=(1, 0, 0))
    iniziale = doc.annot_rect(0, xref)
    for passo in range(4):
        r = doc.annot_rect(0, xref)
        doc.set_annot_rect(0, xref, pymupdf.Rect(r.x0 + 40, r.y0 + 10, r.x1 + 40, r.y1 + 10))
        dopo = doc.annot_rect(0, xref)
        assert abs(dopo.width - iniziale.width) <= 0.01, (
            f"dopo {passo + 1} spostamenti la larghezza e' {dopo.width}, era {iniziale.width}"
        )
        assert abs(dopo.height - iniziale.height) <= 0.01, (
            f"dopo {passo + 1} spostamenti l'altezza e' {dopo.height}, era {iniziale.height}"
        )
    finale = doc.annot_rect(0, xref)
    assert abs((finale.x0 - iniziale.x0) - 160) <= 0.5, f"x spostato di {finale.x0 - iniziale.x0}"
    assert abs((finale.y0 - iniziale.y0) - 40) <= 0.5, f"y spostato di {finale.y0 - iniziale.y0}"


def test_spostare_un_annotazione_con_bordo_spesso(doc: Document):
    """La correzione deve valere per qualsiasi spessore del bordo."""
    xref = doc.add_annot(0, "rect", pymupdf.Rect(100, 600, 200, 660), color=(1, 0, 0))
    for w in doc.page(0).annots():
        if w.xref == xref:
            w.set_border(width=6)
            w.update()
    iniziale = doc.annot_rect(0, xref)
    for _ in range(3):
        r = doc.annot_rect(0, xref)
        doc.set_annot_rect(0, xref, pymupdf.Rect(r.x0 + 40, r.y0, r.x1 + 40, r.y1))
    dopo = doc.annot_rect(0, xref)
    assert abs(dopo.width - iniziale.width) <= 0.01, f"larghezza {dopo.width}, era {iniziale.width}"
    assert abs((dopo.x0 - iniziale.x0) - 120) <= 0.5, f"x spostato di {dopo.x0 - iniziale.x0}"


# ---------------------------------------------------------------------- campi


def test_campi_testo_e_valori(doc: Document):
    doc.add_field(0, "text", pymupdf.Rect(50, 50, 300, 78), name="nome", value="Mario")
    f = doc.fields()[0]
    assert f.name == "nome" and f.value == "Mario" and f.kind == "text"
    doc.set_field_value(0, f.xref, "Luigi")
    assert [x.value for x in doc.fields() if x.name == "nome"][0] == "Luigi"


def test_casella_di_spunta(doc: Document):
    xref = doc.add_field(0, "checkbox", pymupdf.Rect(50, 50, 70, 70), name="ok", value=True)
    assert [f.value for f in doc.fields() if f.name == "ok"][0] not in ("Off", False)
    doc.set_field_value(0, xref, False)
    assert [f.value for f in doc.fields() if f.name == "ok"][0] in ("Off", False)


def test_elenco_a_discesa(doc: Document):
    doc.add_field(0, "combo", pymupdf.Rect(50, 50, 250, 72), name="scelta",
                  options=["Uno", "Due", "Tre"], value="Due")
    f = [x for x in doc.fields() if x.name == "scelta"][0]
    assert f.value == "Due" and f.options == ["Uno", "Due", "Tre"]


def test_gruppo_pulsanti_opzione(doc: Document):
    xrefs = doc.add_radio_group(
        0, [pymupdf.Rect(50, 50, 68, 68), pymupdf.Rect(100, 50, 118, 68)], name="grp", selected=1
    )
    radios = [f for f in doc.fields() if f.type == "RadioButton"]
    assert len(radios) >= 2
    attivi = [f for f in radios if f.value not in ("Off", False)]
    assert len(attivi) == 1
    doc.select_radio(0, xrefs[0])
    attivi = [f for f in doc.fields() if f.type == "RadioButton" and f.value not in ("Off", False)]
    assert len(attivi) == 1


def test_flag_del_campo(doc: Document):
    doc.add_field(0, "text", pymupdf.Rect(50, 50, 300, 78), name="n", multiline=True,
                  required=True, password=False, read_only=True)
    f = doc.fields()[0]
    assert f.multiline and f.required and f.read_only and not f.password


def test_campo_firma(doc: Document):
    xref = doc.add_field(0, "signature", pymupdf.Rect(50, 50, 300, 100), name="firma")
    f = [x for x in doc.fields() if x.name == "firma"][0]
    assert f.type == "Signature" and f.kind == "signature"


def test_statistiche_campi(doc: Document):
    doc.add_field(0, "text", pymupdf.Rect(50, 50, 300, 78), name="a", value="x")
    doc.add_field(0, "text", pymupdf.Rect(50, 90, 300, 118), name="b", value="")
    st = doc.field_stats()
    assert st["total"] == 2 and st["filled"] == 1


def test_azzera_e_appiattisci_campi(doc: Document):
    # il campo nasce vuoto: dopo la compilazione l'azzeramento deve svuotarlo
    doc.add_field(0, "text", pymupdf.Rect(50, 50, 300, 78), name="a", value="")
    xref = doc.fields()[0].xref
    doc.set_field_value(0, xref, "compilato")
    assert [f.value for f in doc.fields() if f.name == "a"][0] == "compilato"
    doc.reset_form()
    assert [f.value for f in doc.fields() if f.name == "a"][0] in ("", None)
    doc.flatten_fields()
    assert doc.fields() == []


def test_tipo_campo_non_supportato(doc: Document):
    with pytest.raises(DocumentError):
        doc.add_field(0, "inesistente", pymupdf.Rect(0, 0, 10, 10))


# ------------------------------------------------------------------- sicurezza


def test_cifratura_e_apertura(tmp_path: Path, doc: Document):
    p = tmp_path / "protetto.pdf"
    doc.export(str(p), permissions=-1, owner_pass="proprietario", user_pass="utente",
               algorithm=pymupdf.PDF_ENCRYPT_AES_256)
    d2 = pymupdf.open(str(p))
    assert d2.needs_pass
    assert d2.authenticate("utente")
    assert not d2.authenticate("sbagliata")
    d2.close()


def test_algoritmo_cifratura(tmp_path: Path, doc: Document):
    p = tmp_path / "a128.pdf"
    doc.export(str(p), permissions=-1, owner_pass="o", user_pass="u",
               algorithm=pymupdf.PDF_ENCRYPT_AES_128)
    d2 = Document()
    d2.open(p, "u")
    assert d2.page_count == 1
    d2.close()


# ------------------------------------------------------------- metadati e extra


def test_metadati(doc: Document):
    doc.set_metadata({"title": "Titolo", "author": "Autore"})
    assert doc.metadata()["title"] == "Titolo"


def test_segnalibri(doc: Document):
    doc.add_bookmark("Capitolo 1", 0)
    doc.add_bookmark("Capitolo 2", 0)
    assert [e["title"] for e in doc.outline()] == ["Capitolo 1", "Capitolo 2"]
    doc.remove_bookmark("Capitolo 1")
    assert [e["title"] for e in doc.outline()] == ["Capitolo 2"]


def test_allegati(tmp_path: Path, doc: Document):
    f = tmp_path / "nota.txt"
    f.write_text("contenuto", encoding="utf-8")
    doc.add_attachment(f)
    att = doc.attachments()
    assert len(att) == 1 and att[0]["name"] == "nota.txt"
    assert doc.attachment_bytes("nota.txt") == b"contenuto"
    doc.remove_attachment("nota.txt")
    assert doc.attachments() == []


# ------------------------------------------------------------------ annullamento


def test_annulla_e_ripeti_operazioni(doc: Document):
    doc.insert_text_box(0, pymupdf.Rect(50, 50, 400, 90), "Da annullare", fontsize=12)
    assert "Da annullare" in doc.text(0)
    doc.history.undo()
    assert "Da annullare" not in doc.text(0)
    doc.history.redo()
    assert "Da annullare" in doc.text(0)


# ------------------------------------------------------------- segnalibri


@pytest.fixture()
def tre_pagine_con_segnalibri(doc: Document) -> Document:
    doc.add_bookmark("Prima parte", 0)
    doc.add_bookmark("Capitolo uno", 0)
    doc.add_bookmark("Capitolo uno", 1)
    return doc


def test_aggiungi_segnalibro(doc: Document):
    doc.add_bookmark("Introduzione", 0)
    assert [(e["title"], e["page"]) for e in doc.outline()] == [("Introduzione", 0)]


def test_rimuovi_segnalibro(tre_pagine_con_segnalibri: Document):
    tre_pagine_con_segnalibri.remove_bookmark("Capitolo uno")
    titoli = [e["title"] for e in tre_pagine_con_segnalibri.outline()]
    assert titoli == ["Prima parte"]


def test_rimuovi_segnalibro_inesistente(tre_pagine_con_segnalibri: Document):
    with pytest.raises(DocumentError, match="Nessun segnalibro"):
        tre_pagine_con_segnalibri.remove_bookmark("non esiste")


def test_rinomina_segnalibro_per_titolo(tre_pagine_con_segnalibri: Document):
    tre_pagine_con_segnalibri.rename_bookmark("Prima parte", "Prefazione")
    assert [e["title"] for e in tre_pagine_con_segnalibri.outline()][0] == "Prefazione"


def test_rinomina_sceglie_l_occorrenza(tre_pagine_con_segnalibri: Document):
    """Con due titoli uguali si rinomina solo quello indicato."""
    tre_pagine_con_segnalibri.rename_bookmark("Capitolo uno", "Capitolo 1", occurrence=1)
    titoli = [e["title"] for e in tre_pagine_con_segnalibri.outline()]
    assert titoli == ["Prima parte", "Capitolo 1", "Capitolo uno"]


def test_rinomina_per_indice(tre_pagine_con_segnalibri: Document):
    tre_pagine_con_segnalibri.rename_bookmark_at(1, "Indice")
    assert [e["title"] for e in tre_pagine_con_segnalibri.outline()][1] == "Indice"


def test_rinomina_titolo_vuoto_rifiutata(tre_pagine_con_segnalibri: Document):
    with pytest.raises(DocumentError, match="vuoto"):
        tre_pagine_con_segnalibri.rename_bookmark_at(0, "   ")


def test_rinomina_indice_fuori_intervallo(tre_pagine_con_segnalibri: Document):
    with pytest.raises(DocumentError, match="non esiste"):
        tre_pagine_con_segnalibri.rename_bookmark_at(99, "X")


def test_rinomina_occorrenza_impossibile(tre_pagine_con_segnalibri: Document):
    with pytest.raises(DocumentError, match="segnalibri chiamati"):
        tre_pagine_con_segnalibri.rename_bookmark("Capitolo uno", "X", occurrence=9)


def test_sposta_segnalibro(doc: Document):
    doc.add_bookmark("Prima parte", 0)
    doc.insert_page(1)
    doc.move_bookmark_at(0, 1)
    assert doc.outline()[0]["page"] == 1


def test_sposta_segnalibro_pagina_inesistente(doc: Document):
    doc.add_bookmark("Prima parte", 0)
    with pytest.raises(DocumentError, match="non esiste"):
        doc.move_bookmark_at(0, 9)


def test_segnalibro_annullabile(doc: Document):
    doc.add_bookmark("Prima parte", 0)
    doc.rename_bookmark_at(0, "Prefazione")
    assert doc.outline()[0]["title"] == "Prefazione"
    doc.history.undo()
    assert doc.outline()[0]["title"] == "Prima parte"


# ------------------------------------------------- validazione dei valori


def test_maxlen_tronca_il_valore(doc: Document):
    """Un campo con lunghezza massima non puo' contenere un valore piu' lungo."""
    doc.add_field(0, "text", pymupdf.Rect(50, 50, 300, 78), name="cognome", value="", maxlen=5)
    campo = doc.fields()[0]
    assert doc.set_field_value(0, campo.xref, "Nunzio")
    assert doc.fields()[0].value == "Nunzi"


def test_maxlen_accetta_il_valore_gusto(doc: Document):
    doc.add_field(0, "text", pymupdf.Rect(50, 50, 300, 78), name="cognome", value="", maxlen=5)
    campo = doc.fields()[0]
    doc.set_field_value(0, campo.xref, "Nunz")
    assert doc.fields()[0].value == "Nunz"


def test_campo_senza_maxlen_accetta_qualsiasi_valore(doc: Document):
    doc.add_field(0, "text", pymupdf.Rect(50, 50, 300, 78), name="libero", value="")
    campo = doc.fields()[0]
    doc.set_field_value(0, campo.xref, "Un testo arbitrariamente lungo")
    assert doc.fields()[0].value == "Un testo arbitrariamente lungo"


def test_validazione_maxlen(doc: Document):
    doc.add_field(0, "text", pymupdf.Rect(50, 50, 300, 78), name="cognome", value="", maxlen=5)
    campo = doc.fields()[0]
    valido, motivo = doc.validate_field_value(0, campo.xref, "Nunzio")
    assert valido is False and "5" in motivo
    assert doc.validate_field_value(0, campo.xref, "Nunz") == (True, "")


def test_validazione_opzioni_del_menu(doc: Document):
    doc.add_field(0, "combo", pymupdf.Rect(50, 50, 250, 72), name="settore",
                  options=["Vendite", "Produzione"], value="Vendite")
    campo = doc.fields()[0]
    assert doc.validate_field_value(0, campo.xref, "Vendite") == (True, "")
    valido, motivo = doc.validate_field_value(0, campo.xref, "Inesistente")
    assert valido is False and "opzioni" in motivo
    # un elenco vuoto e' ammesso
    assert doc.validate_field_value(0, campo.xref, "") == (True, "")


def test_validazione_campo_inesistente(doc: Document):
    valido, motivo = doc.validate_field_value(0, 99999, "x")
    assert valido is False and "non trovato" in motivo


def test_validazione_pagina_fuori_intervallo(doc: Document):
    assert doc.validate_field_value(99, 0, "x")[0] is False


def test_casella_di_spunta_rimane_booleana(doc: Document):
    doc.add_field(0, "checkbox", pymupdf.Rect(50, 50, 70, 70), name="ok", value=False)
    campo = doc.fields()[0]
    doc.set_field_value(0, campo.xref, 1)
    assert doc.fields()[0].value in (True, "Yes", "On")


# ------------------------------------------------------- numerazione pagine


@pytest.fixture()
def tre_pagine(doc: Document) -> Document:
    doc.insert_text_box(0, pymupdf.Rect(50, 50, 500, 100), "Relazione", fontsize=16)
    doc.insert_page(1)
    doc.insert_page(2)
    return doc


def test_numerazione_tutte_le_pagine(tre_pagine: Document):
    assert tre_pagine.add_page_numbers() == 3
    for i in range(3):
        assert tre_pagine.text(i).strip().endswith(str(i + 1))


def test_numerazione_parte_da(tre_pagine: Document):
    """«first» e' il numero della prima pagina selezionata, non della pagina 1."""
    tre_pagine.add_page_numbers(first=5)
    assert tre_pagine.text(0).strip().endswith("5")
    assert tre_pagine.text(1).strip() == "6"
    assert tre_pagine.text(2).strip() == "7"


def test_numerazione_con_totale(tre_pagine: Document):
    tre_pagine.add_page_numbers(first=5, fmt="{page} / {total}", total=True)
    # il totale e' l'ultimo numero stampato
    assert tre_pagine.text(0).strip().endswith("5 / 7")
    assert tre_pagine.text(2).strip() == "7 / 7"


def test_numerazione_salta_la_ricopertina(tre_pagine: Document):
    tre_pagine.add_page_numbers(skip_first=True, first=1)
    assert "1" not in tre_pagine.text(0).replace("Relazione", "")
    assert tre_pagine.text(1).strip() == "1"


def test_numerazione_di_poche_pagine(tre_pagine: Document):
    assert tre_pagine.add_page_numbers([1]) == 1
    assert tre_pagine.has_page_numbers() == [1]


def test_rimozione_numerazione_ripristina_il_testo(tre_pagine: Document):
    prima = tre_pagine.text(0)
    tre_pagine.add_page_numbers()
    assert tre_pagine.remove_page_numbers() == 3
    assert tre_pagine.text(0) == prima
    assert tre_pagine.has_page_numbers() == []


def _blocchi_numerazione(doc: Document, index: int) -> int:
    """Quanti numeri di pagina sono scritti nel contenuto della pagina."""
    grezzo = doc.page(index).read_contents()
    return grezzo.count(b"/ScrNum BMC")


def test_numerazione_applicata_due_volte(tre_pagine: Document):
    """Applicandola due volte i numeri si sovrappongono ma restano rimovibili."""
    tre_pagine.add_page_numbers()
    tre_pagine.add_page_numbers()
    assert _blocchi_numerazione(tre_pagine, 1) == 2
    assert tre_pagine.remove_page_numbers() == 6
    assert _blocchi_numerazione(tre_pagine, 1) == 0
    assert tre_pagine.text(1).strip() == ""


def test_rimozione_senza_numerazione_rifiutata(tre_pagine: Document):
    with pytest.raises(DocumentError, match="Nessuna numerazione"):
        tre_pagine.remove_page_numbers()


def test_numerazione_annullabile(tre_pagine: Document):
    tre_pagine.add_page_numbers()
    tre_pagine.history.undo()
    assert tre_pagine.has_page_numbers() == []


def test_numerazione_annullabile_anche_dopo(tre_pagine: Document):
    """Anche annullando un'altra operazione la numerazione resta rimovibile."""
    tre_pagine.add_page_numbers()
    tre_pagine.insert_text_box(0, pymupdf.Rect(50, 150, 500, 200), "Altro", fontsize=12)
    assert tre_pagine.remove_page_numbers() == 3


def test_numerazione_sopra_pagina_ruotata(doc: Document):
    d = Document()
    d.new(842, 595)          # orizzontale
    d.rotate_pages([0], 90)  # diventa verticale
    d.add_page_numbers()
    assert d.text(0).strip() == "1"
    d.close()


def test_numerazione_parametri_invalidi(tre_pagine: Document):
    with pytest.raises(DocumentError, match="dimensione"):
        tre_pagine.add_page_numbers(fontsize=200)
    with pytest.raises(DocumentError, match="margine"):
        tre_pagine.add_page_numbers(margin=-5)
    with pytest.raises(DocumentError, match="Posizione"):
        tre_pagine.add_page_numbers(position="in_cima")


def test_numerazione_senza_pagine(doc: Document):
    assert doc.add_page_numbers([]) == 0
    assert doc.remove_page_numbers([]) == 0


def test_numerazione_su_pagina_senza_contenuto(doc: Document):
    """Una pagina vuota non ha flusso di contenuto: va creato."""
    d = Document()
    d.new(595, 842)
    assert d.add_page_numbers() == 1
    assert d.text(0).strip() == "1"
    assert d.remove_page_numbers() == 1
    assert d.text(0).strip() == ""
    d.close()


# ------------------------------------------------------- riduzione del file


def _immagine_pesante(w: int = 1600, h: int = 1100, seed: int = 7) -> bytes:
    """Immagine non compressibile: il caso reale di una fotografia."""
    import random

    rnd = random.Random(seed)
    img = Image.new("RGB", (w, h))
    img.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)) for _ in range(w * h)])
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture()
def documento_con_foto(doc: Document) -> Document:
    doc.insert_image(0, pymupdf.Rect(50, 50, 545, 420), _immagine_pesante(), keep_proportion=False)
    doc.insert_text_box(0, pymupdf.Rect(50, 440, 545, 480), "Testo da conservare", fontsize=14)
    return doc


def test_inventario_immagini(documento_con_foto: Document):
    inv = documento_con_foto.image_inventory()
    assert len(inv) == 1
    assert inv[0]["width"] == 1600 and inv[0]["height"] == 1100
    assert 1.7 < inv[0]["megapixels"] < 1.8


def test_riduzione_sensibile_sulle_immagini(documento_con_foto: Document, tmp_path: Path):
    r = documento_con_foto.reduce_size(tmp_path / "ridotto.pdf", quality=50, max_dpi=150)
    assert r["images"] == 1
    assert r["after"] < r["before"] / 2, r
    assert r["saved"] > 0


def test_riduzione_conserva_testo_e_pagine(documento_con_foto: Document, tmp_path: Path):
    r = documento_con_foto.reduce_size(tmp_path / "ridotto.pdf", quality=60, max_dpi=150)
    chk = pymupdf.open(str(r["path"]))
    assert chk.page_count == 1
    assert "Testo da conservare" in chk[0].get_text()
    chk.close()


def test_riduzione_il_documento_aperto_non_cambia(documento_con_foto: Document, tmp_path: Path):
    """La riduzione scrive un file nuovo: l'originale resta come era."""
    src = tmp_path / "originale.pdf"
    documento_con_foto.save(src)
    prima = src.stat().st_size
    testo = documento_con_foto.text(0)
    documento_con_foto.reduce_size(tmp_path / "ridotto.pdf", quality=50, max_dpi=150)
    assert src.stat().st_size == prima
    assert documento_con_foto.text(0) == testo
    assert documento_con_foto.dirty is False


def test_riduzione_risultato_apribile_e_renderizzabile(documento_con_foto: Document, tmp_path: Path):
    r = documento_con_foto.reduce_size(tmp_path / "ridotto.pdf", quality=70, max_dpi=150)
    pm = pymupdf.open(str(r["path"]))[0].get_pixmap(dpi=72)
    assert pm.width > 0 and pm.height > 0


def test_qualita_invalida_rifiutata(documento_con_foto: Document, tmp_path: Path):
    for cattiva in (0, 101, -5):
        with pytest.raises(DocumentError, match="qualità"):
            documento_con_foto.reduce_size(tmp_path / "x.pdf", quality=cattiva)


def test_riduzione_qualita_alta_meno_compatta(documento_con_foto: Document, tmp_path: Path):
    bassa = documento_con_foto.reduce_size(tmp_path / "bassa.pdf", quality=30, max_dpi=150)
    alta = documento_con_foto.reduce_size(tmp_path / "alta.pdf", quality=95, max_dpi=150)
    assert bassa["after"] < alta["after"]


def test_riduzione_senza_immagini(documento_con_foto: Document, tmp_path: Path):
    d = Document()
    d.new(595, 842)
    d.insert_text_box(0, pymupdf.Rect(50, 50, 500, 100), "Solo testo", fontsize=14)
    r = d.reduce_size(tmp_path / "solo_testo.pdf", quality=70, max_dpi=150)
    assert r["images"] == 0
    assert d.image_inventory() == []
    d.close()


# ------------------------------------------------------------------ allegati


def test_allega_file(doc: Document, tmp_path: Path):
    f = tmp_path / "relazione.txt"
    f.write_text("contenuto", encoding="utf-8")
    doc.add_attachment(f, "relazione.txt")
    assert [a["name"] for a in doc.attachments()] == ["relazione.txt"]
    assert b"contenuto" in doc.attachment_bytes("relazione.txt")


def test_allega_usa_il_nome_scelto(doc: Document, tmp_path: Path):
    f = tmp_path / "relazione.txt"
    f.write_text("x", encoding="utf-8")
    doc.add_attachment(f, "documenti/relazione.txt")
    assert [a["name"] for a in doc.attachments()] == ["documenti/relazione.txt"]


def test_allega_file_inesistente(doc: Document, tmp_path: Path):
    with pytest.raises(DocumentError, match="non esiste"):
        doc.add_attachment(tmp_path / "manca.txt")


def test_allega_cartella_rifiutata(doc: Document, tmp_path: Path):
    with pytest.raises(DocumentError, match="cartella"):
        doc.add_attachment(tmp_path)


def test_rimuovi_allegato(doc: Document, tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("x", encoding="utf-8")
    doc.add_attachment(f, "a.txt")
    doc.remove_attachment("a.txt")
    assert doc.attachments() == []


def test_rimuovi_allegato_inesistente(doc: Document):
    with pytest.raises(DocumentError, match="Nessun allegato"):
        doc.remove_attachment("non_esiste.txt")


# ---------------------------------------------------------------- salvataggio


def test_salva_il_file_scelto(doc: Document, tmp_path: Path):
    p = tmp_path / "prova.pdf"
    assert doc.save(p) == p
    assert pymupdf.open(str(p)).page_count == 1
    assert doc.path == p and doc.dirty is False


def test_salvataggio_senza_percorso_rifiutato(doc: Document):
    with pytest.raises(DocumentError, match="Nessun percorso"):
        doc.save()


def test_salvataggio_su_percorso_impossibile(doc: Document, tmp_path: Path):
    """Un percorso che non puo' esistere deve essere un errore dichiarato.

    Il percorso era ``/proc/inesistente/cartella/file.pdf``, che su Windows
    diventa ``C:\\proc\\inesistente\\cartella\\file.pdf``: la CI lo creava
    senza problemi e il salvataggio riusciva, quindi la prova non verificava
    niente. Qui la cartella padre e' un file, e su ogni sistema non puo'
    diventare una cartella.
    """
    ostacolo = tmp_path / "non_una_cartella"
    ostacolo.write_bytes(b"questo e' un file")
    with pytest.raises(DocumentError, match="Salvataggio non riuscito"):
        doc.save(ostacolo / "cartella" / "file.pdf")


def test_salvataggio_su_file_aperto_scrive_dentro(tmp_path: Path, monkeypatch):
    """Salvare sul file aperto deve funzionare anche senza poterlo sostituire.

    Su Windows un file aperto non si puo' sostituire, e il file da cui il
    documento e' stato aperto e' aperto: MuPDF lo legge attraverso un handle
    suo e ``os.replace`` finiva con «Access is denied», quindi salvare non
    scriveva niente. Quando la sostituzione non e' possibile il contenuto
    viene scritto dentro il file. Qui la condizione viene riprodotta per
    costruzione, e la via di Windows viene provata anche su Linux: non
    basta che non dia errore, il file deve restare valido e contenere le
    modifiche, anche dopo un secondo salvataggio.
    """
    p = tmp_path / "aperto.pdf"
    d = pymupdf.open()
    d.new_page(width=400, height=600)
    d.save(str(p))
    d.close()

    doc = Document()
    doc.open(str(p))
    monkeypatch.setattr(document, "_SOSTITUZIONE_DISPONIBILE", False)

    doc.insert_text_box(0, pymupdf.Rect(50, 100, 350, 140), "Salvataggio", fontsize=18)
    assert doc.save() == p
    assert not doc.dirty
    assert "Salvataggio" in pymupdf.open(str(p))[0].get_text()
    assert list(tmp_path.glob("*.tmp")) == [], "resta un provvisorio sul disco"

    # e ancora: il documento continua a poter essere salvato e letto
    doc.rotate_pages([0], 90)
    assert doc.save() == p
    salvato = pymupdf.open(str(p))
    assert int(salvato[0].rotation) == 90
    assert "Salvataggio" in salvato[0].get_text()
    doc.close()


def test_salvataggio_riprova_se_il_file_e_temporaneamente_aperto(
    tmp_path: Path, monkeypatch
):
    """Una sostituzione respinta al primo tentativo non deve far fallire tutto.

    Un antivirus o un programma di sincronizzazione possono tenere il file
    aperto per qualche decimo di secondo: il file deve essere scritto lo
    stesso, e senza lasciare il provvisorio addosso.
    """
    p = tmp_path / "momentaneamente.pdf"
    d = pymupdf.open()
    d.new_page(width=400, height=600)
    d.save(str(p))
    d.close()

    doc = Document()
    doc.open(str(p))
    vero = os.replace
    tentativi = []

    def respinge_una_volta(a, b):
        tentativi.append((a, b))
        if len(tentativi) == 1:
            raise PermissionError(13, "file aperto")
        return vero(a, b)

    monkeypatch.setattr(os, "replace", respinge_una_volta)
    # su Windows la sostituzione non è tentata: qui si prova comunque, perché è
    # il tentativo che va ripetuto
    monkeypatch.setattr(document, "_SOSTITUZIONE_DISPONIBILE", True)
    assert doc.save() == p
    assert len(tentativi) == 2, "il salvataggio non ha riprovato"
    assert list(tmp_path.glob("*.tmp")) == [], "resta un provvisorio sul disco"
    doc.close()


def test_salvataggio_riprova_anche_scrivendo_dentro(tmp_path: Path, monkeypatch):
    """La via senza sostituzione deve riprovare prima di arrendersi.

    È quella che Windows usa sempre, perché lì sostituire un file aperto è
    vietato: senza ripetizione un antivirus che lo tiene aperto mezzo secondo
    farebbe perdere il lavoro.
    """
    p = tmp_path / "scrittura.pdf"
    d = pymupdf.open()
    d.new_page(width=400, height=600)
    d.save(str(p))
    d.close()

    doc = Document()
    doc.open(str(p))
    monkeypatch.setattr(document, "_SOSTITUZIONE_DISPONIBILE", False)
    vero = document._scrivi_su_file_aperto
    tentativi = []

    def respinge_una_volta(provvisorio, target):
        tentativi.append((provvisorio, target))
        if len(tentativi) == 1:
            raise PermissionError(13, "file aperto")
        vero(provvisorio, target)

    monkeypatch.setattr(document, "_scrivi_su_file_aperto", respinge_una_volta)
    assert doc.save() == p
    assert len(tentativi) == 2, "la scrittura dentro il file non ha riprovato"
    assert list(tmp_path.glob("*.tmp")) == [], "resta un provvisorio sul disco"
    doc.close()


def test_salvataggio_dichiara_un_file_bloccato(tmp_path: Path, monkeypatch):
    """Un file che non si puo' ne' sostituire ne' scrivere va detto.

    Tacere lascerebbe l'utente con un file che sembra salvato e che invece
    e' quello di prima: peggio di un salvataggio dichiarato fallito.
    """
    p = tmp_path / "bloccato.pdf"
    d = pymupdf.open()
    d.new_page(width=400, height=600)
    d.save(str(p))
    d.close()

    doc = Document()
    doc.open(str(p))
    monkeypatch.setattr(document, "_SOSTITUZIONE_DISPONIBILE", False)
    monkeypatch.setattr(
        document, "_scrivi_su_file_aperto",
        lambda _a, _b: (_ for _ in ()).throw(PermissionError(13, "bloccato")),
    )
    with pytest.raises(DocumentError, match="aperto da un altro programma"):
        doc.save()
    assert list(tmp_path.glob("*.tmp")) == [], "resta un provvisorio sul disco"
    doc.close()



def test_salva_una_copia_non_tocca_la_sessione(tmp_path: Path):
    """Salvare una copia non deve spostare il file corrente ne' azzerare l'undo."""
    d = Document()
    d.new(595, 842)
    originale = tmp_path / "originale.pdf"
    d.save(originale)
    d.insert_text_box(0, pymupdf.Rect(50, 100, 300, 140), "Seconda", fontsize=14)

    stato = (d.path, d.dirty, d.history.undo_text())
    copia = tmp_path / "copia.pdf"
    d.save_copy(copia)
    assert (d.path, d.dirty, d.history.undo_text()) == stato

    # la copia contiene le modifiche, l'originale no
    assert "Seconda" in pymupdf.open(str(copia))[0].get_text()
    assert "Seconda" not in pymupdf.open(str(originale))[0].get_text()
    d.close()


def test_salva_una_copia_su_percorso_impossibile(doc: Document, tmp_path: Path):
    ostacolo = tmp_path / "non_una_cartella"
    ostacolo.write_bytes(b"questo e' un file")
    with pytest.raises(DocumentError, match="copia non riuscito"):
        doc.save_copy(ostacolo / "cartella" / "copia.pdf")


# --------------------------------------------------------- inserimento pagine


@pytest.fixture()
def pdf_esterno(tmp_path: Path) -> Path:
    d = pymupdf.open()
    for _ in range(3):
        d.new_page(width=200, height=200)
    p = tmp_path / "esterno.pdf"
    d.save(str(p))
    d.close()
    return p


def test_inserisce_pagine_da_altro_file(doc: Document, pdf_esterno: Path):
    assert doc.insert_pdf_pages(str(pdf_esterno), 1) == 3
    assert doc.page_count == 4


def test_inserisce_una_sola_pagina(doc: Document, pdf_esterno: Path):
    assert doc.insert_pdf_pages(str(pdf_esterno), 0, pages=[1]) == 1
    assert doc.page_count == 2


def test_inserimento_annullabile(doc: Document, pdf_esterno: Path):
    doc.insert_pdf_pages(str(pdf_esterno), 1)
    doc.history.undo()
    assert doc.page_count == 1


def test_inserimento_file_inesistente(doc: Document, tmp_path: Path):
    with pytest.raises(DocumentError, match="Impossibile aprire"):
        doc.insert_pdf_pages(str(tmp_path / "manca.pdf"), 0)


def test_inserimento_file_non_pdf(doc: Document, tmp_path: Path):
    f = tmp_path / "testo.txt"
    f.write_text("non sono un PDF", encoding="utf-8")
    with pytest.raises(DocumentError, match="non è un PDF valido"):
        doc.insert_pdf_pages(str(f), 0)


def test_inserimento_pagine_fuori_intervallo(doc: Document, pdf_esterno: Path):
    with pytest.raises(DocumentError, match="non esistono nel file di origine"):
        doc.insert_pdf_pages(str(pdf_esterno), 0, pages=[0, 7])
    assert doc.page_count == 1, "il documento non deve essere cambiato"


# ------------------------------------------------------------------ export


def test_export_di_tutte_le_pagine(doc: Document, tmp_path: Path):
    doc.insert_page(1)
    out = doc.export(tmp_path / "tutte.pdf")
    assert pymupdf.open(str(out)).page_count == 2


def test_export_di_un_sottoinsieme(doc: Document, tmp_path: Path):
    for _ in range(3):
        doc.insert_page(1)
    out = doc.export(tmp_path / "poche.pdf", pages=[0, 2])
    assert pymupdf.open(str(out)).page_count == 2


def test_export_rifiuta_indici_fuori_intervallo(doc: Document, tmp_path: Path):
    """Prima un indice inesistente aggiungeva una pagina vuota al file esportato."""
    with pytest.raises(DocumentError, match="fuori intervallo"):
        doc.export(tmp_path / "male.pdf", pages=[0, 5, 99])


def test_export_non_produce_pagine_extra(doc: Document, tmp_path: Path):
    out = doc.export(tmp_path / "ok.pdf", pages=[0])
    assert pymupdf.open(str(out)).page_count == 1


def test_export_senza_pagine_rifiutato(doc: Document, tmp_path: Path):
    with pytest.raises(DocumentError, match="Nessuna pagina"):
        doc.export(tmp_path / "vuoto.pdf", pages=[])


# ----------------------------------------------------------------- ritaglio


@pytest.fixture()
def pagina_con_testo(doc: Document) -> Document:
    doc.insert_text_box(0, pymupdf.Rect(70, 70, 480, 110), "Relazione annuale", fontsize=18)
    doc.insert_text_box(0, pymupdf.Rect(70, 130, 480, 260), "Contenuto del documento.", fontsize=12)
    return doc


def test_ritaglio_riduce_l_area_visibile(pagina_con_testo: Document):
    info = pagina_con_testo.page_info(0)
    pagina_con_testo.crop_page(0, geo.Rect(50, 50, 300, 400))
    dopo = pagina_con_testo.page_info(0)
    assert dopo.rect.width < info.rect.width
    assert dopo.rect.height < info.rect.height


def test_ritaglio_non_tocca_il_foglio(pagina_con_testo: Document):
    """Il ritaglio riduce l'area visibile, non il contenuto della pagina."""
    prima = pagina_con_testo.page_info(0).mediabox
    pagina_con_testo.crop_page(0, geo.Rect(50, 50, 300, 400))
    assert pagina_con_testo.page_info(0).mediabox == prima


def test_ritaglio_annullabile(pagina_con_testo: Document):
    prima = pagina_con_testo.page_info(0).rect
    pagina_con_testo.crop_page(0, geo.Rect(50, 50, 300, 400))
    pagina_con_testo.history.undo()
    assert pagina_con_testo.page_info(0).rect == prima


def test_ripristina_ritaglio(pagina_con_testo: Document):
    pagina_con_testo.crop_page(0, geo.Rect(50, 50, 300, 400))
    assert pagina_con_testo.reset_crop([0]) == 1
    assert pagina_con_testo.page_info(0).rect == pagina_con_testo.page_info(0).mediabox


def test_ritaglio_troppo_piccolo_rifiutato(pagina_con_testo: Document):
    with pytest.raises(DocumentError):
        pagina_con_testo.crop_page(0, geo.Rect(10, 10, 14, 14))


def test_ritaglio_automatico_trova_il_contenuto(pagina_con_testo: Document):
    zona = pagina_con_testo.auto_crop_rect(0)
    assert zona is not None
    info = pagina_con_testo.page_info(0)
    # la zona deve stare dentro la pagina e contenere il testo
    assert zona.x0 >= info.rect.x0 - 1 and zona.y0 >= info.rect.y0 - 1
    assert zona.x1 <= info.rect.x1 + 1 and zona.y1 <= info.rect.y1 + 1
    assert zona.width < info.rect.width * 0.9, zona


def test_ritaglio_automatico_ignora_una_pagina_gia_ritagliata(pagina_con_testo: Document):
    pagina_con_testo.crop_page(0, geo.Rect(50, 50, 300, 400))
    assert pagina_con_testo.auto_crop_rect(0) is None


def test_ritaglio_automatico_ignora_una_pagina_vuota(doc: Document):
    assert doc.auto_crop_rect(0) is None


def test_ritaglio_di_piu_pagine_con_formati_diversi(doc: Document):
    doc.insert_text_box(0, pymupdf.Rect(60, 60, 400, 100), "Prima pagina", fontsize=16)
    doc.insert_page(1, width=300, height=400)
    doc.insert_text_box(1, pymupdf.Rect(40, 40, 250, 80), "Seconda pagina", fontsize=12)
    zona = doc.auto_crop_rect(0)
    assert doc.crop_pages([0, 1], zona) == 2
    # entrambe ridotte, ciascuna nel proprio formato
    assert doc.page_info(0).rect.width < 595
    assert doc.page_info(1).rect.width < 300


def test_ritaglio_di_nessuna_pagina(pagina_con_testo: Document):
    assert pagina_con_testo.crop_pages([], geo.Rect(50, 50, 300, 400)) == 0
    assert pagina_con_testo.reset_crop([]) == 0


def test_ritaglio_automatico_usa_il_testo_verificato(pagina_con_testo: Document):
    """La zona rilevata deve contenere davvero il testo, non il vuoto."""
    zona = pagina_con_testo.auto_crop_rect(0)
    testo = pagina_con_testo.selected_text(0, zona)
    assert "Relazione" in testo


# ------------------------------------------------------------ selezione del testo


@pytest.fixture()
def testo_su_pagina(doc: Document) -> Document:
    doc.insert_text_box(0, pymupdf.Rect(50, 50, 545, 90), "Relazione annuale", fontsize=18)
    doc.insert_text_box(0, pymupdf.Rect(50, 120, 545, 220), "Primo paragrafo.\nSecondo paragrafo.", fontsize=11)
    return doc


def test_parole_una_volta_per_pagina(testo_su_pagina: Document):
    parole = testo_su_pagina.words(0)
    assert len(parole) == 6, parole
    # la seconda chiamata usa la cache
    assert testo_su_pagina.words(0) is parole


def test_parole_in_rettangolo(testo_su_pagina: Document):
    dentro = testo_su_pagina.words_in_rect(0, pymupdf.Rect(45, 45, 550, 95))
    assert len(dentro) == 2, dentro          # solo "Relazione annuale"
    vuoto = testo_su_pagina.words_in_rect(0, pymupdf.Rect(45, 700, 550, 780))
    assert vuoto == []


def test_parola_parzialmente_toccata_e_presa(testo_su_pagina: Document):
    """Basta toccare una parola con il rettangolo per selezionarla."""
    parole = testo_su_pagina.words_in_rect(0, pymupdf.Rect(50, 55, 56, 88))
    assert len(parole) >= 1


def test_testo_selezionato(testo_su_pagina: Document):
    testo = testo_su_pagina.selected_text(0, pymupdf.Rect(45, 45, 550, 95))
    assert testo == "Relazione annuale"


def test_testo_selezionato_di_piu_righe(testo_su_pagina: Document):
    testo = testo_su_pagina.selected_text(0, pymupdf.Rect(45, 45, 550, 230))
    assert "Relazione annuale" in testo
    assert "Secondo paragrafo." in testo
    # nessuna riga vuota nel risultato copiato
    assert all(r.strip() for r in testo.splitlines())


def test_testo_selezionato_tutto(testo_su_pagina: Document):
    testo = testo_su_pagina.selected_text(0, testo_su_pagina.page_info(0).rect)
    assert "Relazione" in testo and "Secondo" in testo


def test_cache_parole_invalidata_dopo_modifica(testo_su_pagina: Document):
    """Dopo una modifica la selezione non deve piu' citare il testo vecchio."""
    zona = pymupdf.Rect(45, 45, 550, 95)
    assert "annuale" in testo_su_pagina.selected_text(0, zona)
    testo_su_pagina.replace_text("annuale", "semestrale", 0)
    assert "semestrale" in testo_su_pagina.selected_text(0, zona)
    # la cache delle parole deve riflettere subito il nuovo testo
    titolo = [t for _, t in testo_su_pagina.words(0) if t.isalpha() and t.lower().startswith(("relazione", "annuale", "semestrale"))]
    assert any(t.lower() == "semestrale" for t in titolo), titolo
    assert not any(t.lower() == "annuale" for t in titolo), titolo


def test_cache_parole_invalidata_dopo_redazione(testo_su_pagina: Document):
    """Il testo redatto sparisce anche dalla selezione."""
    zona = pymupdf.Rect(45, 45, 550, 95)
    testo_su_pagina.redact(0, [zona])
    assert testo_su_pagina.selected_text(0, zona) == ""
    # il resto della pagina e' rimasto intatto
    assert "Secondo paragrafo." in testo_su_pagina.selected_text(0, pymupdf.Rect(45, 45, 550, 230))


def test_cache_parole_invalidata_dopo_annullamento(testo_su_pagina: Document):
    testo_su_pagina.insert_text_box(0, pymupdf.Rect(50, 300, 545, 340), "Parola aggiunta", fontsize=12)
    assert any("aggiunta" in t for _, t in testo_su_pagina.words(0))
    testo_su_pagina.history.undo()
    assert not any("aggiunta" in t for _, t in testo_su_pagina.words(0))


def test_rettangolo_qt_accettato(testo_su_pagina: Document):
    """La vista passa un QRectF: la conversione deve funzionare senza Qt nel nucleo."""
    from PySide6.QtCore import QRectF

    q = QRectF(45, 45, 505, 50)
    assert len(testo_su_pagina.words_in_rect(0, q)) == 2
    assert testo_su_pagina.selected_text(0, q) == "Relazione annuale"


@pytest.mark.parametrize("kind", ["rect", "circle", "highlight", "ink", "note", "stamp"])
def test_annullamento_creazione_annotazione(doc: Document, kind: str):
    """La copia precedente all'annotazione deve essere scattata prima di crearla."""
    doc.insert_text_box(0, pymupdf.Rect(50, 50, 400, 90), "Testo di riferimento", fontsize=12)
    prima = len(doc.annots(0, include_widgets=False))
    extra = {"vertices": [(10, 10), (40, 60), (90, 30)]} if kind == "ink" else {}
    testo = {"text": "nota"} if kind == "note" else {}
    doc.add_annot(0, kind, pymupdf.Rect(100, 100, 160, 150), color=(0, 0, 0), **extra, **testo)
    assert len(doc.annots(0, include_widgets=False)) == prima + 1
    doc.history.undo()
    assert len(doc.annots(0, include_widgets=False)) == prima
    doc.history.redo()
    assert len(doc.annots(0, include_widgets=False)) == prima + 1
    doc.history.undo()
    assert len(doc.annots(0, include_widgets=False)) == prima


def test_annullamento_testo_inserito(doc: Document):
    assert "Riferimento" not in doc.text(0)
    doc.insert_text_box(0, pymupdf.Rect(50, 50, 400, 90), "Riferimento", fontsize=12)
    assert "Riferimento" in doc.text(0)
    doc.history.undo()
    assert "Riferimento" not in doc.text(0)


def test_annullamento_campo_creato(doc: Document):
    doc.add_field(0, "text", pymupdf.Rect(50, 50, 300, 78), name="a", value="x")
    assert len(doc.fields()) == 1
    doc.history.undo()
    assert len(doc.fields()) == 0


def test_annullamento_operazioni_pagina(doc: Document):
    for _ in range(3):
        doc.insert_page(doc.page_count)
    assert doc.page_count == 4
    for atteso in (3, 2, 1):
        doc.history.undo()
        assert doc.page_count == atteso
    # il documento torna allo stato iniziale e puo' essere riaperto
    out = tmp_path_pdf(doc)
    assert out.page_count == 1


def tmp_path_pdf(doc: Document):
    """Salva il documento in un file temporaneo e lo riapre."""
    import tempfile
    from pathlib import Path

    p = Path(tempfile.mkdtemp(prefix="korvaxoide_test_")) / "prova.pdf"
    doc.save(p)
    d = Document()
    d.open(p)
    return d


def test_operazione_fallita_non_altera_il_documento(doc: Document):
    before = doc.text(0)
    with pytest.raises(DocumentError):
        doc.delete_pages([0, 1, 2])
    assert doc.text(0) == before
    assert doc.page_count == 1


def test_redazione_permanente(doc: Document):
    doc.insert_text_box(0, pymupdf.Rect(50, 50, 450, 90), "Segreto da cancellare", fontsize=12)
    rects = doc.find_redact_targets(0, "Segreto")
    assert rects
    doc.redact(0, rects)
    assert "Segreto" not in doc.text(0)


# ------------------------------------------------------------- dimensione pagina


def test_cambiare_la_dimensione_della_pagina_e_annullabile(doc: Document):
    """Cambiare dimensione deve potersi disfare come ogni altra modifica.

    La finestra scriveva direttamente sulla pagina con set_mediabox e
    set_cropbox, fuori da _mutate: la modifica finiva nel documento ma non
    nell'annullamento, quindi Ctrl+Z non la toglieva.
    """
    prima = doc.page_info(0).rect
    assert abs(prima.width - 595) <= 1, f"il documento di prova non e' A4: {prima}"
    doc.set_page_size([0], 400, 700)
    dopo = doc.page_info(0).rect
    assert abs(dopo.width - 400) <= 1 and abs(dopo.height - 700) <= 1, f"pagina {dopo}"
    assert doc.dirty
    doc.history.undo()
    tornata = doc.page_info(0).rect
    assert abs(tornata.width - prima.width) <= 1 and abs(tornata.height - prima.height) <= 1, (
        f"l'annullamento non ha riportato la pagina a {prima}, e' {tornata}"
    )


def test_cambiare_la_dimensione_di_piu_pagine_insieme(doc: Document):
    doc.insert_page(1)
    doc.insert_page(2)
    for p in range(doc.page_count):
        assert abs(doc.page_info(p).rect.width - 595) <= 1
    doc.set_page_size([0, 2], 300, 500)
    for p, atteso in ((0, 300), (1, 595), (2, 300)):
        larghezza = doc.page_info(p).rect.width
        assert abs(larghezza - atteso) <= 1, f"pagina {p}: {larghezza}, attesa {atteso}"


def test_dimensione_pagina_non_valida_rifiutata(doc: Document):
    for cattivo in ((0, 400), (400, 0), (-10, 400)):
        with pytest.raises(Exception):
            doc.set_page_size([0], *cattivo)
    assert abs(doc.page_info(0).rect.width - 595) <= 1, "una dimensione invalida ha modificato la pagina"


# ---------------------------------------------------------- esito delle modifiche


def test_spostare_riporta_che_è_andata_a_buon_fine(doc: Document):
    """Il risultato di ``set_annot_rect`` deve dire la verità.

    La closure non restituiva nulla, e ``bool(None)`` è ``False``: ogni volta
    che il riquadro era stato spostato correttamente il metodo riportava
    «non riuscito».
    """
    xref = doc.add_annot(0, "rect", pymupdf.Rect(100, 600, 200, 660), color=(1, 0, 0))
    assert doc.set_annot_rect(0, xref, pymupdf.Rect(300, 600, 400, 660)) is True
    assert abs(doc.annot_rect(0, xref).x0 - 300) <= 0.5
    # un xref che non esiste va riferito come fallito, non come riuscito
    assert doc.set_annot_rect(0, 999999, pymupdf.Rect(0, 0, 10, 10)) is False


def test_modificare_le_proprieta_riporta_che_e_andata_a_buon_fine(doc: Document):
    xref = doc.add_annot(0, "rect", pymupdf.Rect(100, 600, 200, 660), color=(1, 0, 0))
    assert doc.set_annot_props(0, xref, {"opacity": 0.5}) is True
    assert doc.set_annot_props(0, 999999, {"opacity": 0.5}) is False


def test_evidenziare_accetta_il_colore_scelto(doc: Document):
    """Il colore dell'evidenziatura si puo' scegliere.

    Il parametro finiva dentro la ricerca, che non lo accetta, e il programma
    si fermava con un ``TypeError``: nessuno poteva cambiare il colore.
    """
    doc.insert_text_box(0, pymupdf.Rect(50, 60, 500, 95), "Relazione annuale", fontsize=18)
    n = doc.highlight_hits("annuale", 0, color=(0, 0.8, 0.2))
    assert n == 1, f"occorrenze evidenziate: {n}"
    evidenziate = [a for a in doc.annots(0, include_widgets=False) if a["type"] == "Highlight"]
    assert evidenziate, "nessuna evidenziazione creata"
    # anche il colore di default deve funzionare
    assert doc.highlight_hits("Relazione", 0) == 1
