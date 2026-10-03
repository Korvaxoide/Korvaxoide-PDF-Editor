"""Test dei controlli di qualità: accessibilità e pre-stampa."""

from __future__ import annotations

import io

import pymupdf
import pytest
from PIL import Image

from pdfeditor.core.document import Document, DocumentError
from pdfeditor.features import quality


def _immagine(w: int, h: int, colore=(200, 40, 40)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), colore).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture()
def doc() -> Document:
    d = Document()
    d.new(595, 842)
    yield d
    d.close()


@pytest.fixture()
def povero() -> Document:
    """Documento con i problemi più comuni: niente lingua, niente titolo, immagine piccola."""
    d = Document()
    d.new(595, 842)
    d.insert_text_box(0, pymupdf.Rect(50, 50, 520, 90), "Relazione", fontsize=16)
    d.insert_image(0, pymupdf.Rect(50, 120, 545, 400), _immagine(300, 200), keep_proportion=False)
    d.insert_page(1)
    yield d
    d.close()


def _codici(esito) -> list[str]:
    return [f.code for f in esito]


# ---------------------------------------------------------------- accessibilità


def test_segnala_lingua_e_titolo_mancanti(povero: Document):
    codici = _codici(quality.accessibility_report(povero))
    assert "lingua" in codici
    assert "titolo" in codici


def test_non_segnala_lingua_se_e_dichiarata(povero: Document):
    povero.set_document_language("it-IT")
    assert "lingua" not in _codici(quality.accessibility_report(povero))


def test_non_segnala_titolo_se_dichiarato(povero: Document):
    povero.set_metadata({"title": "Relazione annuale"})
    assert "titolo" not in _codici(quality.accessibility_report(povero))


def test_segnala_documento_non_strutturato(povero: Document):
    assert "struttura" in _codici(quality.accessibility_report(povero))


def test_segnala_immagine_senza_testo_alternativo_solo_se_davvero_mancante():
    """L'avviso sulle immagini deve basarsi su un controllo reale.

    ``/Alt`` sta sugli elementi strutturali (``/Figure``), non sull'oggetto
    immagine: chiedendolo all'xref dell'immagine la risposta è sempre «null» e
    ogni documento con una figura veniva segnalato, anche descritto. Qui si
    costruisce un documento strutturato con una figura senza descrizione e una
    con descrizione, e si verifica che venga segnalata solo la prima.
    """
    povero: Document
    d = Document()
    d.new(595, 842)
    d.insert_image(0, pymupdf.Rect(50, 120, 545, 400), _immagine(300, 200), keep_proportion=False)
    _albero_strutturato(d._require(), alt={})
    esito = quality.accessibility_report(d)
    voci = [f for f in esito if f.code == "immagini_alt"]
    assert voci, "una figura senza /Alt va segnalata"
    assert voci[0].count == 1, voci[0]
    d.close()

    d = Document()
    d.new(595, 842)
    d.insert_image(0, pymupdf.Rect(50, 120, 545, 400), _immagine(300, 200), keep_proportion=False)
    _albero_strutturato(d._require(), alt={0: "Diagramma dei flussi"})
    esito = quality.accessibility_report(d)
    assert not [f for f in esito if f.code == "immagini_alt"], "una figura descritta non va segnalata"
    d.close()


def _albero_strutturato(doc, alt: dict[int, str]) -> None:
    """Albero strutturale con una figura, con o senza testo alternativo.

    ``/StructTreeRoot`` si scrive come dizionario annidato: MuPDF crea da sé gli
    oggetti indiretti mancanti.
    """
    pagina = doc[0].xref
    alt_testo = alt.get(0)
    descrizione = f" /Alt ({alt_testo})" if alt_testo else ""
    albero = (
        f"<< /Type /StructTreeRoot /K [<< /Type /StructElem /S /Div /P {pagina} 0 R"
        f" /K [<< /Type /StructElem /S /Figure /P {pagina} 0 R{descrizione} >>] >>] >>"
    )
    doc.xref_set_key(doc.pdf_catalog(), "StructTreeRoot", albero)


def test_segnala_pagina_senza_testo(povero: Document):
    voce = next(f for f in quality.accessibility_report(povero) if f.code == "senza_testo")
    assert voce.pages == [1], voce.pages


def test_segnala_cifratura(tmp_path):
    src = tmp_path / "base.pdf"
    d = Document()
    d.new(595, 842)
    d.insert_text_box(0, pymupdf.Rect(50, 50, 500, 90), "Testo", fontsize=12)
    d.save(src)
    protetto = tmp_path / "protetto.pdf"
    d.export(str(protetto), permissions=-1, owner_pass="o", user_pass="u")
    d.close()
    d2 = Document()
    d2.open(protetto, "u")
    voce = next(f for f in quality.accessibility_report(d2) if f.code == "cifratura")
    assert voce.severity == "error"
    assert voce.action == "rimuovi_protezione"
    d2.close()


def test_segnala_campi_fuori_ordine_di_lettura(doc: Document):
    """I campi vanno in ordine di lettura, non in ordine di creazione."""
    doc.add_field(0, "text", pymupdf.Rect(50, 200, 300, 228), name="basso", value="")
    doc.add_field(0, "text", pymupdf.Rect(50, 100, 300, 128), name="alto", value="")
    assert "ordine_campi" in _codici(quality.accessibility_report(doc))


def test_non_segnala_ordine_campi_se_giusto(doc: Document):
    doc.add_field(0, "text", pymupdf.Rect(50, 100, 300, 128), name="alto", value="")
    doc.add_field(0, "text", pymupdf.Rect(50, 200, 300, 228), name="basso", value="")
    assert "ordine_campi" not in _codici(quality.accessibility_report(doc))


def test_correzione_riordina_i_campi(doc: Document):
    doc.add_field(0, "text", pymupdf.Rect(50, 200, 300, 228), name="basso", value="")
    doc.add_field(0, "text", pymupdf.Rect(50, 100, 300, 128), name="alto", value="")
    assert doc.sort_fields_in_reading_order() == 2
    assert [f.name for f in doc.fields()] == ["alto", "basso"]
    assert "ordine_campi" not in _codici(quality.accessibility_report(doc))


def test_riordino_annullabile(doc: Document):
    doc.add_field(0, "text", pymupdf.Rect(50, 200, 300, 228), name="basso", value="")
    doc.add_field(0, "text", pymupdf.Rect(50, 100, 300, 128), name="alto", value="")
    prima = [f.name for f in doc.fields()]
    doc.sort_fields_in_reading_order()
    doc.history.undo()
    assert [f.name for f in doc.fields()] == prima


def test_lingua_non_valida_rifiutata(doc: Document):
    for cattivo in ("", "   ", "1234", "ab@cd"):
        with pytest.raises(DocumentError):
            doc.set_document_language(cattivo)


def test_lingua_valida_accettata(doc: Document):
    for buono in ("it", "it-IT", "en_GB", "pt-BR"):
        doc.set_document_language(buono)
        assert doc.language()


def test_documento_senza_problemi_e_vuoto_dei_risultati():
    d = Document()
    d.new(595, 842)
    d.set_document_language("it-IT")
    d.set_metadata({"title": "Vuoto"})
    d.insert_text_box(0, pymupdf.Rect(50, 50, 500, 90), "Testo", fontsize=12)
    # resta solo l'avviso sul documento non strutturato, che il programma
    # non puo' correggere da solo
    assert _codici(quality.accessibility_report(d)) == ["struttura"]
    d.close()


# ------------------------------------------------------------------ pre-stampa


def test_preflight_segnala_immagine_a_risoluzione_bassa(povero: Document):
    voce = next(f for f in quality.preflight_report(povero) if f.code == "risoluzione")
    assert voce.count == 1
    assert voce.severity == "warning"
    # l'immagine e' 300px su 495pt: poco piu' di 43 dpi
    assert "43" in voce.detail or "44" in voce.detail, voce.detail


def test_preflight_rispetta_la_soglia_di_risoluzione(doc: Document):
    """La soglia e' quella che decide: 2000px su 495pt sono circa 290 dpi."""
    doc.insert_text_box(0, pymupdf.Rect(50, 50, 500, 90), "Testo", fontsize=12)
    doc.insert_image(0, pymupdf.Rect(50, 120, 545, 400), _immagine(2000, 1400), keep_proportion=False)
    assert "risoluzione" in _codici(quality.preflight_report(doc, min_dpi=300))
    assert "risoluzione" not in _codici(quality.preflight_report(doc, min_dpi=200))


def test_preflight_segnala_pagina_bianca(povero: Document):
    voce = next(f for f in quality.preflight_report(povero) if f.code == "pagine_bianche")
    assert voce.pages == [1]


def test_preflight_segnala_immagini_rgb(povero: Document):
    assert "spazio_colore" in _codici(quality.preflight_report(povero))


def test_preflight_opzione_disattiva_rgb(povero: Document):
    assert "spazio_colore" not in _codici(quality.preflight_report(povero, segnala_rgb=False))


def test_preflight_segnala_file_grande(povero: Document):
    voce = next(f for f in quality.preflight_report(povero, max_megabytes=0.0001) if f.code == "dimensione")
    assert voce.action == "riduci_file"


def test_preflight_non_segnala_file_grande_se_il_limite_e_alto(povero: Document):
    assert "dimensione" not in _codici(quality.preflight_report(povero, max_megabytes=1000))


def test_preflight_font_base14_non_segnalati(doc: Document):
    """Helvetica e Times sono presenti in ogni lettore: non sono un problema."""
    doc.insert_text_box(0, pymupdf.Rect(50, 50, 500, 90), "Testo", fontsize=12, fontname="helv")
    assert "font" not in _codici(quality.preflight_report(doc))


def test_preflight_segnala_documento_protetto(tmp_path):
    src = tmp_path / "base.pdf"
    d = Document()
    d.new(595, 842)
    d.save(src)
    protetto = tmp_path / "protetto.pdf"
    d.export(str(protetto), permissions=-1, owner_pass="o", user_pass="u")
    d.close()
    d2 = Document()
    d2.open(protetto, "u")
    voce = next(f for f in quality.preflight_report(d2) if f.code == "cifratura")
    assert voce.action == "rimuovi_protezione"
    d2.close()


# -------------------------------------------------------------------Finding


def test_finding_si_seria_in_un_dizionario():
    f = quality.Finding("x", "Titolo", "Dettaglio", "warning", pages=[1, 2], count=2, action="correggi")
    d = f.as_dict()
    assert d["code"] == "x" and d["title"] == "Titolo"
    assert d["pages"] == [1, 2] and d["count"] == 2 and d["action"] == "correggi"


def test_plurale_corretto():
    """La forma conta anche in inglese, dove il nome cambia con il numero."""
    it = ("immagine", "immagini")
    en = ("image", "images")
    assert quality._plurale(1, it, en) == "1 immagine"
    assert quality._plurale(3, it, en) == "3 immagini"

    from pdfeditor.core import i18n

    i18n.set_lingua("en")
    try:
        assert quality._plurale(1, it, en) == "1 image"
        assert quality._plurale(3, it, en) == "3 images"
    finally:
        i18n.set_lingua("it")


def test_normalizza_font():
    assert quality._normalize_font("ABCDEF+Helvetica") == "Helvetica"
    assert quality._normalize_font("Liberation Serif") == "LiberationSerif"
