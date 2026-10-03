"""Test della firma digitale e della protezione del documento."""

from __future__ import annotations

import re
from pathlib import Path

import pymupdf
import pytest

from pdfeditor.core.document import Document, DocumentError
from pdfeditor.features import digitalsign as ds


@pytest.fixture()
def sorgente(tmp_path: Path) -> Path:
    p = tmp_path / "sorgente.pdf"
    d = Document()
    d.new(595, 842)
    d.insert_text_box(0, pymupdf.Rect(60, 60, 500, 110), "Relazione da firmare", fontsize=16)
    d.save(p)
    d.close()
    return p


@pytest.fixture(scope="module")
def certificato(tmp_path_factory) -> ds.Certificate:
    return ds.make_self_signed(
        "Mario Rossi", "mario@rossi.it", "Rossi SRL", save_to=tmp_path_factory.mktemp("cert") / "cert.pem"
    )


# ------------------------------------------------------------------ certificati


def test_generazione_certificato_autofirmato(certificato: ds.Certificate):
    assert certificato.self_signed
    assert certificato.subject == "Mario Rossi"
    assert certificato.pem.startswith(b"-----BEGIN CERTIFICATE-----")
    assert certificato.key_pem
    assert certificato.not_before and certificato.not_after
    assert "autofirmato" in certificato.summary()


def test_caricamento_certificato_pem(tmp_path: Path, certificato: ds.Certificate):
    rigenerato = ds.make_self_signed("Luigi Verdi", save_to=tmp_path / "c.pem")
    letto = ds.load_certificate(tmp_path / "c.pem")
    assert "Luigi Verdi" in letto.subject
    assert letto.key_pem
    # il certificato riletto deve essere lo stesso, non uno qualsiasi: prima
    # c'era un «or True» che rendeva vera la verifica anche se il seriale
    # cambiava, e il caricamento del PEM non era controllato
    assert letto.serial == rigenerato.serial, (
        f"il seriale rilretto ({letto.serial}) non e' quello generato ({rigenerato.serial})"
    )
    assert letto.self_signed, "un certificato creato da noi deve risultare autofirmato"


def test_caricamento_certificato_inesistente(tmp_path: Path):
    with pytest.raises(Exception):
        ds.load_certificate(tmp_path / "non_esiste.pem")


# ------------------------------------------------------------------- firma


def test_firma_crea_pdf_valido(sorgente: Path, certificato: ds.Certificate, tmp_path: Path):
    out = tmp_path / "firmato.pdf"
    r = ds.sign_document(sorgente, out, certificato, page_index=0, rect=(60, 700, 320, 760))
    assert r.ok
    assert out.exists()
    d = pymupdf.open(str(out))
    assert d.page_count == 1
    assert not d.is_encrypted
    d.close()


def test_firma_verificata(sorgente: Path, certificato: ds.Certificate, tmp_path: Path):
    out = tmp_path / "firmato.pdf"
    ds.sign_document(sorgente, out, certificato, rect=(60, 700, 320, 760), reason="Accettazione")
    esito = ds.verify_file(out)
    assert len(esito) == 1
    s = esito[0]
    assert s["signed"] is True
    assert s["valid"] is True
    assert "non e' stato modificato" in s["integrity"]


def test_firma_contiene_i_dati_del_certificato(sorgente: Path, certificato: ds.Certificate, tmp_path: Path):
    out = tmp_path / "firmato.pdf"
    ds.sign_document(sorgente, out, certificato, reason="Accettazione", location="Milano",
                     name="Mario Rossi")
    s = ds.verify_file(out)[0]
    assert "Mario Rossi" in (s.get("subject") or "")
    assert s.get("reason") == "Accettazione"
    assert s.get("location") == "Milano"
    assert s.get("signer_name") == "Mario Rossi"
    assert s.get("digest") == "sha256"
    assert s.get("message_digest")


def test_manomissione_rilevata(sorgente: Path, certificato: ds.Certificate, tmp_path: Path):
    out = tmp_path / "firmato.pdf"
    ds.sign_document(sorgente, out, certificato, rect=(60, 700, 320, 760))
    grezzo = bytearray(out.read_bytes())
    # si altera un valore di /ByteRange, che sta dentro la zona firmata: la
    # struttura del file resta valida ma l'impronta non corrisponde piu'
    m = re.search(rb"/ByteRange\s*\[\s*\d+\s+\d+", grezzo)
    assert m
    inizio = m.end() - 1
    grezzo[inizio] = ord("9") if grezzo[inizio] != ord("9") else ord("8")
    manomesso = tmp_path / "manomesso.pdf"
    manomesso.write_bytes(bytes(grezzo))
    s = ds.verify_file(manomesso)[0]
    assert s["valid"] is False
    assert "modificato" in s["integrity"]


def test_byte_range_azzera_tutto_il_documento(sorgente: Path, certificato: ds.Certificate, tmp_path: Path):
    out = tmp_path / "firmato.pdf"
    ds.sign_document(sorgente, out, certificato, rect=(60, 700, 320, 760))
    grezzo = out.read_bytes()
    m = re.search(rb"/ByteRange\s*\[\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)", grezzo)
    assert m
    a, b, c, d = (int(x) for x in m.groups())
    assert a == 0
    assert b < c                      # l'intervallo escluso e' il segnaposto
    assert d == len(grezzo)           # copre tutto il resto
    # l'intervallo escluso e' esattamente <...> dello spazio riservato
    assert c - b == ds.PLACEHOLDER_LEN + 2
    # il segnaposto e' l'unica zona non coperta: tutto il resto e' firmato
    assert b == c - ds.PLACEHOLDER_LEN - 2


def test_firma_invisibile(sorgente: Path, certificato: ds.Certificate, tmp_path: Path):
    out = tmp_path / "invisibile.pdf"
    r = ds.sign_document(sorgente, out, certificato, rect=None, visible=False)
    assert r.ok
    s = ds.verify_file(out)[0]
    assert s["valid"] is True


def test_due_firme_indipendenti(sorgente: Path, certificato: ds.Certificate, tmp_path: Path):
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    ds.sign_document(sorgente, a, certificato, reason="Prima")
    ds.sign_document(sorgente, b, certificato, reason="Seconda")
    assert ds.verify_file(a)[0]["reason"] == "Prima"
    assert ds.verify_file(b)[0]["reason"] == "Seconda"


def test_firma_con_chiave_ec(sorgente: Path, tmp_path: Path):
    cert = ds.make_self_signed("Carla Verdi", key_type="ec", save_to=tmp_path / "ec.pem")
    out = tmp_path / "firmato_ec.pdf"
    r = ds.sign_document(sorgente, out, cert, rect=(60, 700, 320, 760))
    assert r.ok
    s = ds.verify_file(out)[0]
    assert s["valid"] is True


def test_firma_documento_protetto(sorgente: Path, certificato: ds.Certificate, tmp_path: Path):
    protetto = tmp_path / "protetto.pdf"
    d = Document()
    d.open(sorgente)
    d.export(str(protetto), permissions=-1, owner_pass="o", user_pass="u")
    d.close()
    out = tmp_path / "firmato_protetto.pdf"
    with pytest.raises(ds.SignatureError):
        ds.sign_document(protetto, out, certificato)


def test_dettagli_firma(sorgente: Path, certificato: ds.Certificate, tmp_path: Path):
    out = tmp_path / "firmato.pdf"
    ds.sign_document(sorgente, out, certificato, reason="Accettazione")
    dettagli = ds.verify_file(out)[0]
    for chiave in ("page", "name", "signed", "subject", "issuer", "date", "trust", "integrity"):
        assert chiave in dettagli


def test_nessuna_firma(sorgente: Path):
    assert ds.inspect_signatures(sorgente) == []


# ------------------------------------------------------------------ permessi


PERM = (
    ("Stampa", pymupdf.PDF_PERM_PRINT),
    ("Modifica", pymupdf.PDF_PERM_MODIFY),
    ("Copia", pymupdf.PDF_PERM_COPY),
)


@pytest.mark.parametrize("etichetta,bit", PERM)
def test_permessi_disattivati(sorgente: Path, tmp_path: Path, etichetta: str, bit: int):
    out = tmp_path / f"senza_{bit}.pdf"
    d = Document()
    d.open(sorgente)
    # PyMuPDF accetta un intero con segno: i bit sono i piu' bassi, quindi
    # ``~bit`` disattiva il permesso lasciando gli altri attivi.
    d.export(str(out), permissions=~bit, owner_pass="o", user_pass="u")
    d.close()
    opened = pymupdf.open(str(out))
    assert opened.authenticate("u")
    assert not (opened.permissions & bit)
    opened.close()


def test_rimozione_protezione(sorgente: Path, tmp_path: Path):
    protetto = tmp_path / "protetto.pdf"
    d = Document()
    d.open(sorgente)
    d.export(str(protetto), permissions=-1, owner_pass="proprietario", user_pass="utente")
    d.close()
    raw = pymupdf.open(str(protetto))
    assert raw.needs_pass
    raw.close()
    d2 = Document()
    d2.open(protetto, "utente")
    assert d2.remove_encryption("proprietario") is None
    assert not d2.is_encrypted
    d2.close()


def test_rimozione_protezione_non_scrive_file_sporco(sorgente: Path, tmp_path: Path, monkeypatch):
    """Rimuovere la cifratura non deve creare un file chiamato ':memory:'."""
    protetto = tmp_path / "protetto.pdf"
    d = Document()
    d.open(sorgente)
    d.export(str(protetto), permissions=-1, owner_pass="proprietario", user_pass="utente")
    d.close()

    lavoro = tmp_path / "lavoro"
    lavoro.mkdir()
    monkeypatch.chdir(lavoro)
    d2 = Document()
    d2.open(protetto, "utente")
    d2.remove_encryption("proprietario")
    d2.close()
    assert list(lavoro.iterdir()) == [], f"file inattesi: {[p.name for p in lavoro.iterdir()]}"


def test_algoritmi_cifratura(sorgente: Path, tmp_path: Path):
    d = Document()
    d.open(sorgente)
    for nome, alg in (("aes256", pymupdf.PDF_ENCRYPT_AES_256), ("aes128", pymupdf.PDF_ENCRYPT_AES_128)):
        out = tmp_path / f"{nome}.pdf"
        d.export(str(out), permissions=-1, owner_pass="o", user_pass="u", algorithm=alg)
        opened = pymupdf.open(str(out))
        assert opened.needs_pass
        assert opened.authenticate("u")
        assert opened.is_encrypted is False or opened.authenticate("u")
        opened.close()
    d.close()


# --------------------------------------------------- firma in campo esistente


@pytest.fixture()
def modulo_con_campo_firma(sorgente: Path, tmp_path: Path) -> Path:
    """Modulo con un campo firma vuoto, come in un documento ricevuto."""
    from pdfeditor.core.document import Document, DocumentError

    d = Document()
    d.new(595, 842)
    d.insert_text_box(0, pymupdf.Rect(50, 50, 545, 90), "Richiesta di rimborso", fontsize=18)
    d.add_field(0, "text", pymupdf.Rect(50, 100, 320, 125), name="nome", value="Mario Rossi")
    d.add_field(0, "signature", pymupdf.Rect(50, 140, 320, 190), name="firma_cliente")
    out = tmp_path / "modulo_firma.pdf"
    d.save(out)
    d.close()
    return out


def test_firma_in_campo_esistente(modulo_con_campo_firma: Path, certificato: ds.Certificate, tmp_path: Path):
    """La firma apposta in un campo esistente lo compila, senza creare campi nuovi."""
    out = tmp_path / "firmato_campo.pdf"
    r = ds.sign_document(
        modulo_con_campo_firma, out, certificato,
        field_name_search="firma_cliente", reason="Conferma richiesta", location="Milano",
    )
    assert r.ok
    assert r.details["field"] == "firma_cliente"
    assert r.details["existing_field"] is True

    firme = ds.verify_file(out)
    assert len(firme) == 1
    assert firme[0]["name"] == "firma_cliente"
    assert firme[0]["signed"] is True
    assert firme[0]["valid"] is True
    assert firme[0]["reason"] == "Conferma richiesta"
    assert firme[0]["location"] == "Milano"

    # nessun campo firma aggiuntivo e valore del campo di testo intatto
    from pdfeditor.core.document import Document, DocumentError

    d = Document()
    d.open(out)
    campi = d.fields()
    assert [c.name for c in campi] == ["nome", "firma_cliente"]
    assert next(c.value for c in campi if c.name == "nome") == "Mario Rossi"
    d.close()


def test_firma_in_campo_esistente_usa_il_riquadro_del_campo(
    modulo_con_campo_firma: Path, certificato: ds.Certificate, tmp_path: Path
):
    """La firma eredita posizione e dimensioni dal campo, non dal rettangolo dato."""
    out = tmp_path / "firmato_riquadro.pdf"
    r = ds.sign_document(
        modulo_con_campo_firma, out, certificato,
        field_name_search="firma_cliente", rect=None, visible=True,
    )
    assert r.ok
    # il campo non deve spostarsi: /Rect resta quello del modulo originale
    grezzo = pymupdf.open(str(out))
    xref = ds.find_signature_field(grezzo, name="firma_cliente")
    numeri = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", grezzo.xref_get_key(xref, "Rect")[1])]
    assert numeri[:4] == [50, 652, 320, 702], numeri
    # l'aspetto e' disegnato sulla pagina del campo
    testo = grezzo[0].get_text()
    assert "Firmato da" in testo
    grezzo.close()


def test_firma_twice_rifiutata(modulo_con_campo_firma: Path, certificato: ds.Certificate, tmp_path: Path):
    """Un campo gia' firmato non puo' essere firmato di nuovo."""
    primo = tmp_path / "primo.pdf"
    ds.sign_document(modulo_con_campo_firma, primo, certificato, field_name_search="firma_cliente")
    with pytest.raises(ds.SignatureError, match="già"):
        ds.sign_document(primo, tmp_path / "secondo.pdf", certificato,
                         field_name_search="firma_cliente")


def test_campo_firma_inesistente(modulo_con_campo_firma: Path, certificato: ds.Certificate, tmp_path: Path):
    with pytest.raises(ds.SignatureError, match="Nessun campo firma"):
        ds.sign_document(modulo_con_campo_firma, tmp_path / "x.pdf", certificato,
                         field_name_search="campo_che_non_esiste")


def test_ricerca_campo_firma_per_xref(modulo_con_campo_firma: Path, certificato: ds.Certificate, tmp_path: Path):
    grezzo = pymupdf.open(str(modulo_con_campo_firma))
    xref = ds.find_signature_field(grezzo, name="firma_cliente")
    assert xref is not None
    assert ds.find_signature_field(grezzo, xref=xref) == xref
    assert ds.find_signature_field(grezzo, name="inesistente") is None
    grezzo.close()

    out = tmp_path / "firmato_xref.pdf"
    r = ds.sign_document(modulo_con_campo_firma, out, certificato, field_xref=xref)
    assert r.ok
    assert ds.verify_file(out)[0]["valid"] is True


def test_due_firme_in_campi_diversi(sorgente: Path, certificato: ds.Certificate, tmp_path: Path):
    """Due campi distinti vengono firmati in modo indipendente."""
    from pdfeditor.core.document import Document, DocumentError

    d = Document()
    d.open(sorgente)
    d.add_field(0, "signature", pymupdf.Rect(50, 100, 300, 150), name="firma_a")
    d.add_field(0, "signature", pymupdf.Rect(50, 200, 300, 250), name="firma_b")
    primo = tmp_path / "due_campi.pdf"
    d.save(primo)
    d.close()

    secondo = tmp_path / "firmato_a.pdf"
    ds.sign_document(primo, secondo, certificato, field_name_search="firma_a")
    assert len(ds.verify_file(secondo)) == 2
    valide = [s for s in ds.verify_file(secondo) if s["signed"] and s["valid"]]
    assert len(valide) == 1 and valide[0]["name"] == "firma_a"


def test_campo_firma_nuovo_non_finisce_capovolto(sorgente: Path, certificato: ds.Certificate, tmp_path: Path):
    """/Rect usa l'origine in basso: il campo creato deve restare dove richiesto."""
    out = tmp_path / "firmato_alto.pdf"
    # rettangolo in coordinate schermo, in alto a sinistra della pagina
    ds.sign_document(sorgente, out, certificato, page_index=0, rect=(80, 100, 380, 160))
    grezzo = pymupdf.open(str(out))
    widget = list(grezzo[0].widgets())[0]
    schermo = widget.rect
    grezzo.close()
    assert abs(schermo.x0 - 80) < 1 and abs(schermo.y0 - 100) < 1
    assert abs(schermo.x1 - 380) < 1 and abs(schermo.y1 - 160) < 1


# ---------------------------------------- conservazione della protezione in memoria


@pytest.fixture()
def protetto(tmp_path: Path) -> Path:
    """PDF con password e permessi ridotti."""
    d = Document()
    d.new(595, 842)
    d.insert_text_box(0, pymupdf.Rect(50, 50, 500, 90), "Contenuto riservato", fontsize=12)
    out = tmp_path / "protetto.pdf"
    d.export(
        str(out),
        permissions=~(pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_COPY),
        owner_pass="o", user_pass="u",
    )
    d.close()
    return out


def test_has_encryption_resta_vero_dopo_le_modifiche(protetto: Path):
    """La cifratura del file di origine non deve sparire dalla descrizione."""
    d = Document()
    d.open(protetto, "u")
    assert d.has_encryption is True
    d.insert_text_box(0, pymupdf.Rect(50, 120, 500, 160), "Aggiunto", fontsize=12)
    assert d.has_encryption is True, "il file di partenza era protetto"
    d.close()


def test_salvare_un_documento_protetto_modificato_non_perde_la_password(protetto: Path, tmp_path: Path):
    """Salvare non deve mai produrre un PDF privo di protezione.

    MuPDF perde il /Encrypt quando serializza il documento per la cronologia:
    senza questo controllo il file salvato uscirebbe aperto a tutti.
    """
    d = Document()
    d.open(protetto, "u")
    d.insert_text_box(0, pymupdf.Rect(50, 120, 500, 160), "Aggiunto", fontsize=12)
    with pytest.raises(DocumentError, match="protezione"):
        d.save(tmp_path / "risalvato.pdf")
    assert not (tmp_path / "risalvato.pdf").exists()
    d.close()


def test_salvataggio_rifiutato_anche_senza_modifiche(protetto: Path, tmp_path: Path):
    """Basta la cronestra iniziale a far perdere la cifratura in memoria."""
    d = Document()
    d.open(protetto, "u")
    d.snapshot()  # quello che fa ogni modifica
    with pytest.raises(DocumentError, match="protezione"):
        d.save(tmp_path / "risalvato.pdf")
    d.close()


def test_il_file_originale_resta_protetto(protetto: Path, tmp_path: Path):
    d = Document()
    d.open(protetto, "u")
    d.insert_text_box(0, pymupdf.Rect(50, 120, 500, 160), "Aggiunto", fontsize=12)
    with pytest.raises(DocumentError):
        d.save(tmp_path / "risalvato.pdf")
    d.close()
    grezzo = pymupdf.open(str(protetto))
    assert grezzo.needs_pass
    assert grezzo.authenticate("u")
    assert not grezzo.permissions & pymupdf.PDF_PERM_PRINT
    grezzo.close()


def test_esportazione_con_password_resta_la_via_consigliata(protetto: Path, tmp_path: Path):
    d = Document()
    d.open(protetto, "u")
    d.insert_text_box(0, pymupdf.Rect(50, 120, 500, 160), "Aggiunto", fontsize=12)
    out = d.export(
        tmp_path / "esportato.pdf",
        permissions=~(pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_COPY),
        owner_pass="o", user_pass="u",
    )
    grezzo = pymupdf.open(str(out))
    assert grezzo.needs_pass and grezzo.authenticate("u")
    assert "Aggiunto" in grezzo[0].get_text()
    grezzo.close()
    d.close()


def test_documento_non_protetto_si_salva_normalmente(sorgente: Path, tmp_path: Path):
    d = Document()
    d.open(sorgente)
    d.insert_text_box(0, pymupdf.Rect(50, 120, 500, 160), "Aggiunto", fontsize=12)
    d.save(tmp_path / "normale.pdf")
    assert pymupdf.open(str(tmp_path / "normale.pdf")).page_count == 1
    d.close()
