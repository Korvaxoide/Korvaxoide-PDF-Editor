"""Firma digitale dei PDF (PKCS#7 / CMS, RSA ed ECDSA).

PyMuPDF 1.28 non espone un'API di firma, quindi la costruzione del documento
firmato è fatta qui:

1. si aggiunge al PDF un campo firma non firmato con un segnaposto in ``/Contents``
2. si calcola ``/ByteRange`` sull'intervallo che esclude il segnaposto
3. si firma l'hash di quei byte con il certificato (CMS ``SignedData`` distaccato)
4. si sostituisce il segnaposto con il DER e si aggiornano ``/ByteRange`` e ``/M``

Il risultato è un PDF che i lettori riconoscono come firmato.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import os
import re
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pymupdf

from ..core.i18n import tr

SIGNATURE_BYTE = 0x20  # spazio:byte innocuo che può restare nel segnaposto
PLACEHOLDER_LEN = 16384  # spazio riservato in /Contents (esadecimale)


class SignatureError(Exception):
    """Errore durante la creazione o la verifica di una firma."""


@dataclass
class Certificate:
    """Materiale crittografico per firmare."""

    subject: str = ""
    issuer: str = ""
    email: str = ""
    serial: str = ""
    not_before: str = ""
    not_after: str = ""
    pem: bytes = b""
    key_pem: bytes = b""
    path: str = ""
    self_signed: bool = True
    trusted: bool = False

    def summary(self) -> str:
        bits = "autofirmato" if self.self_signed else "rilasciato da CA"
        return f"{self.subject} — {bits}, valido fino al {self.not_after}"


@dataclass
class SignatureResult:
    """Esito della firma."""

    ok: bool
    path: Path
    message: str = ""
    signature_bytes: int = 0
    placeholder_left: int = 0
    details: dict[str, Any] = field(default_factory=dict)


# ------------------------------------------------------------------ certificati


def make_self_signed(
    name: str = "",
    email: str = "",
    org: str = "",
    days: int = 1095,
    key_type: str = "rsa",
    save_to: Path | None = None,
) -> Certificate:
    """Genera un certificato personale autofirmato (PEM in memoria o su file)."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, rsa
    from cryptography.x509.oid import NameOID

    if key_type == "ec":
        key = ec.generate_private_key(ec.SECP256R1())
    else:
        key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    attrs = [x509.NameAttribute(NameOID.COMMON_NAME, name or "Utente")]
    if org:
        attrs.append(x509.NameAttribute(NameOID.ORGANIZATION_NAME, org))
    if email:
        attrs.append(x509.NameAttribute(NameOID.EMAIL_ADDRESS, email))
    subject = x509.Name(attrs)
    now = _dt.datetime.now(_dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - _dt.timedelta(minutes=5))
        .not_valid_after(now + _dt.timedelta(days=days))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=True,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    path = ""
    if save_to:
        save_to.parent.mkdir(parents=True, exist_ok=True)
        save_to.write_bytes(pem)
        try:
            (save_to.with_suffix(".key")).write_bytes(key_pem)
            path = str(save_to)
        except OSError:
            path = str(save_to)
    return Certificate(
        subject=name or "Utente",
        issuer=name or "Utente",
        email=email,
        serial=f"{cert.serial_number:X}",
        not_before=cert.not_valid_before_utc.strftime("%d/%m/%Y"),
        not_after=cert.not_valid_after_utc.strftime("%d/%m/%Y"),
        pem=pem,
        key_pem=key_pem,
        path=path,
        self_signed=True,
    )


def load_certificate(path: str | os.PathLike[str], password: str = "") -> Certificate:
    """Carica un certificato da file PFX/P12 o PEM."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.serialization import pkcs12

    p = Path(path)
    data = p.read_bytes()
    key = None
    cert = None
    if data[:4] == b"0\x82" or p.suffix.lower() in (".p12", ".pfx"):
        pw = password.encode() if password else None
        loaded = pkcs12.load_key_and_certificates(data, pw)
        if loaded is None or loaded[1] is None:
            raise SignatureError("Impossibile leggere il certificato: chiave o certificato assenti.")
        key, cert, _chain = loaded
    else:
        cert = x509.load_pem_x509_certificate(data)
        try:
            key = serialization.load_pem_private_key(_read_key(data, p), password=password.encode() if password else None)
        except Exception:
            for cand in (p.with_suffix(".key"), p.with_name(p.stem + ".key"), p.with_suffix(".pem")):
                if cand.exists() and cand != p:
                    try:
                        key = serialization.load_pem_private_key(
                            cand.read_bytes(), password=password.encode() if password else None
                        )
                        break
                    except Exception:
                        continue
    if cert is None:
        raise SignatureError("Certificato non valido.")
    if key is None:
        raise SignatureError("Chiave privata non trovata: serve un file .key o un PFX con chiave integrata.")
    return Certificate(
        subject=cert.subject.rfc4514_string(),
        issuer=cert.issuer.rfc4514_string(),
        email=_first_email(cert),
        serial=f"{cert.serial_number:X}",
        not_before=cert.not_valid_before_utc.strftime("%d/%m/%Y"),
        not_after=cert.not_valid_after_utc.strftime("%d/%m/%Y"),
        pem=cert.public_bytes(serialization.Encoding.PEM),
        key_pem=key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
        path=str(p),
        self_signed=cert.subject == cert.issuer,
    )


def _read_key(data: bytes, p: Path) -> bytes:
    """Estrae il primo blocco PEM ``PRIVATE KEY`` dal file."""
    marker = b"-----BEGIN"
    idx = 0
    while True:
        i = data.find(marker, idx)
        if i < 0:
            return data
        j = data.find(b"-----END", i)
        if j < 0:
            return data
        end = data.find(b"-----", j + 8)
        if end < 0:
            return data
        block = data[i : end + 5]
        if b"PRIVATE KEY" in block[:60]:
            return block
        idx = end + 5


def _first_email(cert: Any) -> str:
    from cryptography import x509

    try:
        vals = cert.subject.get_attributes_for_oid(x509.oid.NameOID.EMAIL_ADDRESS)
        return vals[0].value if vals else ""
    except Exception:
        return ""


# ------------------------------------------------------------------ firma


def add_signature_field(
    doc: pymupdf.Document,
    page_index: int,
    rect: tuple[float, float, float, float] | None,
    name: str = "Firma",
    reason: str = "",
    location: str = "",
    contact: str = "",
) -> int:
    """Aggiunge un campo firma vuoto con segnaposto per il CMS.

    Restituisce l'xref del campo. ``rect=None`` crea una firma invisibile.
    """
    page = doc[page_index]
    widget = pymupdf.Widget()
    widget.field_type = pymupdf.PDF_WIDGET_TYPE_SIGNATURE
    widget.field_name = name
    # PyMuPDF rifiuta i rettangolidegeneri: una firma invisibile usa quindi un
    # riquadro di 1x1 pt nell'angolo, senza aspetto visibile.
    widget.rect = pymupdf.Rect(*rect) if rect else pymupdf.Rect(0, 0, 1, 1)
    annot = page.add_widget(widget)
    if annot is None:
        raise SignatureError("Impossibile creare il campo firma.")
    xref = annot.xref
    doc.xref_set_key(xref, "FT", "/Sig")
    doc.xref_set_key(xref, "T", f"({_esc(name)})")
    doc.xref_set_key(xref, "V", "/Sig")
    doc.xref_set_key(xref, "F", "132")
    doc.xref_set_key(xref, "Ff", "0")
    # Il segnaposto dei contenuti viene rimpiazzato dalla DER del CMS.
    doc.xref_set_key(xref, "Contents", f"<{'00' * PLACEHOLDER_LEN}>")
    # MuPDF emette /ByteRange solo se la chiave esiste, e la normalizza a
    # [0 0 0 0]: verra' allargata a misura fissa dopo la serializzazione.
    doc.xref_set_key(xref, "ByteRange", "[0 0 0 0]")

    if reason:
        doc.xref_set_key(xref, "Reason", f"({_esc(reason)})")
    if location:
        doc.xref_set_key(xref, "Location", f"({_esc(location)})")
    if contact:
        doc.xref_set_key(xref, "ContactInfo", f"({_esc(contact)})")
    doc.xref_set_key(xref, "M", f"(D:{_dt.datetime.now(_dt.timezone.utc).strftime('%Y%m%d%H%M%S')}Z)")
    return xref


def sign_document(
    src: str | os.PathLike[str],
    dst: str | os.PathLike[str],
    cert: Certificate,
    page_index: int = 0,
    rect: tuple[float, float, float, float] | None = (80, 700, 280, 760),
    field_name: str = "Firma",
    reason: str = "",
    location: str = "",
    name: str = "",
    visible: bool = True,
    field_xref: int | None = None,
    field_name_search: str | None = None,
) -> SignatureResult:
    """Firma il PDF e scrive il risultato in ``dst``.

    Il file di destinazione non deve esistere: la firma e' un'operazione che
    modifica la struttura del PDF e va scritta in un file nuovo.

    Con ``field_xref`` (o ``field_name_search``) la firma viene apposta dentro
    un campo firma gia' presente nel documento, come fa Acrobat sui moduli:
    il campo conserva posizione, dimensioni e aspetto. Senza questi parametri
    viene creato un campo firma nuovo.
    """
    src_p, dst_p = Path(src), Path(dst)
    doc = pymupdf.open(str(src_p))
    try:
        if doc.is_encrypted and not doc.authenticate(""):
            raise SignatureError("Il documento è protetto: rimuovi la protezione prima di firmare.")
        if page_index >= doc.page_count:
            page_index = 0
        box = rect if (visible and rect) else None

        esistente = field_xref is not None or field_name_search is not None
        pagina = page_index
        if esistente:
            xref = find_signature_field(doc, name=field_name_search, xref=field_xref)
            if xref is None:
                dove = field_name_search or f"xref {field_xref}"
                raise SignatureError(
                    tr("Nessun campo firma trovato per {dove}.").format(dove=dove)
                )
            if field_is_signed(doc, xref):
                raise SignatureError("Il campo firma contiene già una firma.")
            # il campo puo' trovarsi su una pagina diversa: l'aspetto va
            # disegnato li' dove sta il campo, non dove richiede l'interfaccia
            pagina = _field_page(doc, xref)
            if box is None:
                r = _field_rect(doc, xref, pagina)
                if r:
                    box = r
            campo_nome = field_name_search or _field_name(doc, xref) or field_name
        else:
            xref = add_signature_field(
                doc, page_index, box, field_name, reason, location, name or cert.subject
            )
            campo_nome = field_name

        nonce = _make_nonce(PLACEHOLDER_LEN)
        _prepare_field(doc, xref, nonce, reason, location, name or cert.subject)
        if visible and box:
            _draw_signature_appearance(
                doc, xref, box, cert, reason, location, name, pagina, allinea=not esistente
            )
        # Prima passata: si scrive con il segnaposto per ottenere i byte finali.
        raw = doc.tobytes(garbage=3, deflate=True, clean=False)
        doc.close()

        # MuPDF riscrive sempre /ByteRange come [0 0 0 0]: va allargata a misura
        # fissa *prima* di calcolare l'hash, cosi' i numeri reali potranno essere
        # inseriti senza spostare i byte coperti dalla firma.
        raw = _widen_byte_range(raw)
        pos = _find_nonce(raw, nonce)
        # Secondo la specifica PDF le parentesi angolari fanno parte
        # dell'intervallo non firmato: si esclude quindi [<...>] per intero.
        lo = pos - 1
        hi = pos + len(nonce) + 1
        if raw[lo : lo + 1] != b"<" or raw[hi - 1 : hi] != b">":
            raise SignatureError("Segnaposto dei contenuti non ben formato.")
        capacity = len(nonce) // 2
        # Ordine corretto: i valori finali di /ByteRange stanno dentro la zona
        # firmata, quindi vanno scritti *prima* di calcolare l'hash. La
        # sostituzione e' a lunghezza costante, quindi gli scarti restano validi.
        raw = _patch_byte_range(raw, 0, lo, hi, len(raw))
        digest = _digest_range(raw, lo, hi)
        der = _build_cms(digest, cert, reason, location, name or cert.subject)
        if len(der) > capacity:
            raise SignatureError(
                tr("La firma ({firmato} byte) supera lo spazio riservato "
                   "({spazio} byte).")
                .format(firmato=len(der), spazio=capacity)
            )
        # Il DER e' codificato in esadecimale dentro <...>: il padding '00'
        # corrisponde a byte nulli, inerti per il lettore.
        hexed = (der + b"\x00" * (capacity - len(der))).hex().encode("ascii")
        signed = raw[:lo] + b"<" + hexed + b">" + raw[hi:]
        if len(signed) != len(raw):
            raise SignatureError("La sostituzione della firma ha alterato la lunghezza del file.")
        dst_p.parent.mkdir(parents=True, exist_ok=True)
        dst_p.write_bytes(signed)
        return SignatureResult(
            ok=True,
            path=dst_p,
            message=f"Documento firmato correttamente ({len(der)} byte di firma).",
            signature_bytes=len(der),
            placeholder_left=capacity - len(der),
            details={
                "byte_range": _format_byte_range(0, lo, hi, len(signed)).decode(),
                "field": campo_nome,
                "existing_field": esistente,
                "subject": cert.subject,
            },
        )
    finally:
        try:
            doc.close()
        except Exception:
            pass


def _draw_signature_appearance(
    doc: pymupdf.Document,
    sig_xref: int,
    box: tuple[float, float, float, float],
    cert: Certificate,
    reason: str,
    location: str,
    name: str,
    page_index: int = 0,
    allinea: bool = True,
) -> None:
    """Disegna l'aspetto visibile della firma.

    Il blocco viene scritto direttamente nel contenuto della pagina invece che
    nello stream di aspetto del widget: evita di attraversare la catena di
    annotazioni, che in PyMuPDF dipende da riferimenti deboli e si invalida
    appena la pagina viene rilasciata.

    ``box`` e' in coordinate schermo (origine in alto a sinistra), come le API
    di PyMuPDF. ``allinea`` riporta il riquadro del campo su quella zona: va
    disattivato quando il campo esiste gia', per non spostarlo.
    """
    page = doc[page_index]
    x0, y0, x1, y1 = box
    w = max(40.0, x1 - x0)
    h = max(16.0, y1 - y0)
    size = max(5.0, min(9.0, h * 0.18))
    navy = (0.10, 0.10, 0.40)
    grey = (0.35, 0.35, 0.35)
    try:
        page.insert_text(
            pymupdf.Point(x0 + 3, y0 + h - 5),
            f"Firmato da: {name or cert.subject}"[:90],
            fontsize=size,
            fontname="helv",
            color=navy,
        )
        y = y0 + h - 5 - size - 2
        stamp = _dt.datetime.now().strftime("%d/%m/%Y alle %H:%M")
        if cert.not_after:
            page.insert_text(
                pymupdf.Point(x0 + 3, y),
                f"Data: {stamp}"[:60],
                fontsize=max(4.5, size - 0.5),
                fontname="helv",
                color=grey,
            )
            y -= size
        extra = " · ".join(x for x in (reason, location) if x)
        if extra:
            page.insert_text(
                pymupdf.Point(x0 + 3, y),
                f"Motivo: {extra}"[:100],
                fontsize=max(4.5, size - 0.5),
                fontname="helv",
                color=grey,
            )
    except Exception:
        pass
    # Il riquadro del campo viene allineato alla zona disegnata. /Rect usa
    # l'origine in basso a sinistra, quindi le coordinate schermo vanno
    # ribaltate: senza questa conversione il campo finisce capovolto.
    if not allinea:
        return
    try:
        altezza = page.rect.height
        doc.xref_set_key(
            sig_xref, "Rect", f"[{x0:g} {altezza - y1:g} {x1:g} {altezza - y0:g}]"
        )
    except Exception:
        pass


def _digest_range(raw: bytes, start: int, end: int) -> bytes:
    h = hashlib.sha256()
    h.update(raw[:start])
    h.update(raw[end:])
    return h.digest()


def _build_cms(
    digest: bytes,
    cert: Certificate,
    reason: str = "",
    location: str = "",
    name: str = "",
) -> bytes:
    """Costruisce il CMS SignedData distaccato con gli attributi firmati.

    Un lettore PDF si aspetta che ``messageDigest`` corrisponda all'hash dei byte
    del file e che siano presenti ``contentType`` e ``signingTime``; la firma
    copre tutti gli attributi, quindi aggiungereli dopo invalida l'hash.
    """
    from asn1crypto import algos, cms, core, x509 as a_x509
    from asn1crypto.algos import DigestAlgorithm
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography import x509

    cert_obj = x509.load_pem_x509_certificate(cert.pem)
    key = serialization.load_pem_private_key(cert.key_pem, password=None)

    # 1) set di attributi firmati, conforme a quanto richiede il PDF
    now = _dt.datetime.now(_dt.timezone.utc)
    attrs = [
        cms.CMSAttribute({"type": cms.CMSAttributeType("content_type"), "values": ("data",)}),
        cms.CMSAttribute({"type": cms.CMSAttributeType("signing_time"), "values": (cms.Time({"utc_time": core.UTCTime(now)}),)}),
        cms.CMSAttribute({"type": cms.CMSAttributeType("message_digest"), "values": (core.OctetString(digest),)}),
    ]
    _register_pdf_attribute_oids()
    if reason:
        attrs.append(_text_attribute("signature_reason", reason))
    if location:
        attrs.append(_text_attribute("signature_location", location))
    if name:
        attrs.append(_text_attribute("signer_name", name))
    signed_attrs = cms.CMSAttributes(attrs)

    # 2) gli attributi firmati vengono firmati a loro volta.
    # In DER i SignedAttributes sono codificati come [0] IMPLICIT dentro il
    # SignerInfo, ma la firma copre la forma esplicita SET OF: serve untag().
    der_attrs = signed_attrs.untag().dump()
    signature_over_attrs = _raw_sign(key, der_attrs)

    sig_algo = _algorithm_identifier(key, cert_obj)

    from cryptography.hazmat.primitives import serialization as _ser

    cert_der = a_x509.Certificate.load(cert_obj.public_bytes(_ser.Encoding.DER))
    issuer_der = cert_der["tbs_certificate"]["issuer"].chosen
    signer_info = cms.SignerInfo(
        {
            "version": "v1",
            "sid": cms.SignerIdentifier({"issuer_and_serial_number": cms.IssuerAndSerialNumber(
                {"issuer": issuer_der, "serial_number": cert_obj.serial_number}
            )}),
            "digest_algorithm": DigestAlgorithm({"algorithm": "sha256"}),
            "signed_attrs": signed_attrs,
            "signature_algorithm": sig_algo,
            "signature": signature_over_attrs,
        }
    )
    signed_data = cms.SignedData(
        {
            "version": "v1",
            "digest_algorithms": cms.DigestAlgorithms((DigestAlgorithm({"algorithm": "sha256"}),)),
            "encap_content_info": cms.ContentInfo({"content_type": "data"}),
            "certificates": cms.CertificateSet((cert_der,)),
            "signer_infos": cms.SignerInfos((signer_info,)),
        }
    )
    return cms.ContentInfo({"content_type": "signed_data", "content": signed_data}).dump()


OID_SIGNATURE_REASON = "1.2.840.113583.1.1.8"
OID_SIGNATURE_LOCATION = "1.2.840.113583.1.1.9"
OID_SIGNER_NAME = "1.2.840.113583.1.1.10"


def _register_pdf_attribute_oids() -> None:
    """Registra gli OID attributi usati da Adobe nelle mappe di asn1crypto.

    ``CMSAttributeType`` accetta solo gli OID che conosce: senza questa
    registrazione non si possono aggiungere motivo, localita' e nome del
    firmatario come attributi firmati.
    """
    from asn1crypto import cms, core

    cls = cms.CMSAttributeType
    # Le mappe dell'oggetto vengono costruite alla prima istanziazione: senza
    # questo passaggio _reverse_map non esiste ancora.
    cls("content_type")
    for oid, label in (
        (OID_SIGNATURE_REASON, "signature_reason"),
        (OID_SIGNATURE_LOCATION, "signature_location"),
        (OID_SIGNER_NAME, "signer_name"),
    ):
        cls._map[oid] = label
        if getattr(cls, "_reverse_map", None) is not None:
            cls._reverse_map[label] = oid
        setattr(cls, label, oid)


def _text_attribute(label: str, text: str):
    """Attributo firmato con valore testuale UTF-8.

    Gli OID proprietari di Adobe non sono nel catalogo di asn1crypto, quindi il
    valore viene passato già codificato in DER e interpretato come ``Any``.
    """
    from asn1crypto import cms, core

    return cms.CMSAttribute(
        {
            "type": cms.CMSAttributeType(label),
            "values": (core.Any(core.UTF8String(text)),),
        }
    )


def _sha256(data: bytes) -> bytes:
    import hashlib

    return hashlib.sha256(data).digest()


def _raw_sign(key: Any, data: bytes) -> bytes:
    """Firma i dati con l'hash previsto da CMS (SHA-256).

    Si passano i dati, non il loro hash: ``sign()`` applica internamente
    l'algoritmo di hashing indicato, quindi pre-hashare produrrebbe una doppia
    impronta e la verifica fallirebbe.
    """
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

    if isinstance(key, rsa.RSAPrivateKey):
        return key.sign(data, padding.PKCS1v15(), hashes.SHA256())
    if isinstance(key, ec.EllipticCurvePrivateKey):
        der = key.sign(data, ec.ECDSA(hashes.SHA256()))
        # Nel CMS la firma ECDSA e' la concatenazione grezza r||s, mentre
        # ``cryptography`` produce e attende la forma DER.
        r, s = decode_dss_signature(der)
        size = (key.curve.key_size + 7) // 8
        return r.to_bytes(size, "big") + s.to_bytes(size, "big")
    raise SignatureError("Tipo di chiave non supportato.")


def _algorithm_identifier(key: Any, cert: Any):
    from asn1crypto import algos
    from cryptography.hazmat.primitives.asymmetric import ec, rsa

    if isinstance(key, rsa.RSAPrivateKey):
        return algos.SignedDigestAlgorithm({"algorithm": "sha256_rsa"})
    if isinstance(key, ec.EllipticCurvePrivateKey):
        return algos.SignedDigestAlgorithm({"algorithm": "sha256_ecdsa"})
    return algos.SignedDigestAlgorithm({"algorithm": "sha256_rsa"})


BYTE_RANGE_PLACEHOLDER = b"[0000000000 0000000000 0000000000 0000000000]"


def _format_byte_range(a: int, b: int, c: int, d: int) -> bytes:
    """Matrice /ByteRange con numeri a 10 cifre (stessa lunghezza del segnaposto)."""
    return (f"[{a:010d} {b:010d} {c:010d} {d:010d}]").encode("ascii")


def _widen_byte_range(raw: bytes) -> bytes:
    """Allarga ``/ByteRange`` a quattro numeri da 10 cifre.

    ``xref_set_key`` verrebbe sovrascritto da MuPDF, quindi l'allargamento
    avviene sui byte serializzati. Inserisce byte *prima* del calcolo
    dell'hash, quindi non invalida nulla.
    """
    narrow = b"/ByteRange[0 0 0 0]"
    wide = b"/ByteRange" + BYTE_RANGE_PLACEHOLDER
    idx = raw.rfind(narrow)
    if idx < 0:
        if BYTE_RANGE_PLACEHOLDER in raw:
            return raw
        raise SignatureError("Impossibile preparare /ByteRange nel file serializzato.")
    return raw[:idx] + wide + raw[idx + len(narrow) :]


def _patch_byte_range(raw: bytes, a: int, b: int, c: int, d: int) -> bytes:
    """Sostituisce il segnaposto /ByteRange con i valori reali.

    La sostituzione e' a lunghezza costante: i byte coperti dalla firma non
    cambiano, quindi l'hash calcolato prima resta valido.
    """
    value = _format_byte_range(a, b, c, d)
    if len(value) != len(BYTE_RANGE_PLACEHOLDER):
        raise SignatureError("Lunghezza inattesa di /ByteRange.")
    idx = raw.rfind(BYTE_RANGE_PLACEHOLDER)
    if idx < 0:
        raise SignatureError("Segnaposto /ByteRange non trovato nel file serializzato.")
    return raw[:idx] + value + raw[idx + len(BYTE_RANGE_PLACEHOLDER) :]


def _field_page(doc: pymupdf.Document, xref: int) -> int:
    """Indice della pagina che contiene un campo (0 se non determinabile)."""
    for index in range(doc.page_count):
        try:
            for widget in doc[index].widgets() or ():
                if widget.xref == xref:
                    return index
        except Exception:
            continue
    return 0


def _field_rect(
    doc: pymupdf.Document, xref: int, page_index: int | None = None
) -> tuple[float, float, float, float] | None:
    """Riquadro di un campo firma, in coordinate schermo.

    PyMuPDF 1.28 non espone un accesso al /Rect per xref: il valore si legge
    dalla chiave dell'oggetto. Le coordinate sono quelle del PDF (origine in
    basso), quindi vanno riportate con l'altezza della pagina che ospita il
    campo: usare quella della prima pagina mandava il blocco «Firmato da»
    fuori dal foglio con documenti di formati misti.
    """
    try:
        tipo, valore = doc.xref_get_key(xref, "Rect")
    except Exception:
        return None
    if tipo != "array":
        return None
    numeri = re.findall(r"-?\d+(?:\.\d+)?", valore)
    if len(numeri) < 4:
        return None
    x0, y0, x1, y1 = (float(n) for n in numeri[:4])
    if page_index is None:
        page_index = _field_page(doc, xref)
    try:
        altezza = doc[page_index].rect.height if 0 <= page_index < doc.page_count else 0.0
    except Exception:
        altezza = 0.0
    # da coordinate PDF (basso-alto) a coordinate schermo (alto-basso)
    return (min(x0, x1), altezza - max(y0, y1), max(x0, x1), altezza - min(y0, y1))


def _field_name(doc: pymupdf.Document, xref: int) -> str | None:
    """Legge il nome (/T) di un campo, se presente.

    PyMuPDF restituisce le stringhe gia' decodificate, ma un PDF puo'
    codificarle anche come oggetto nome: vengono accettate entrambe le forme.
    """
    try:
        grezzo = doc.xref_get_key(xref, "T")[1]
    except Exception:
        return None
    if not grezzo or grezzo == "null":
        return None
    if grezzo.startswith("(") and grezzo.endswith(")"):
        return grezzo[1:-1]
    if grezzo.startswith("/"):
        return grezzo[1:]
    return grezzo


def _prepare_field(
    doc: pymupdf.Document,
    xref: int,
    nonce: str,
    reason: str,
    location: str,
    contact: str,
) -> None:
    """Prepara un campo firma (nuovo o esistente) alla firma.

    Scrive il segnaposto casuale in /Contents e lascia /ByteRange a [0 0 0 0]:
    i valori reali vengono inseriti dopo, a lunghezza costante.
    """
    doc.xref_set_key(xref, "FT", "/Sig")
    doc.xref_set_key(xref, "F", "132")
    doc.xref_set_key(xref, "V", "/Sig")
    doc.xref_set_key(xref, "Ff", "0")
    doc.xref_set_key(xref, "Contents", f"<{nonce}>")
    doc.xref_set_key(xref, "ByteRange", "[0 0 0 0]")
    if reason:
        doc.xref_set_key(xref, "Reason", f"({_esc(reason)})")
    if location:
        doc.xref_set_key(xref, "Location", f"({_esc(location)})")
    if contact:
        doc.xref_set_key(xref, "ContactInfo", f"({_esc(contact)})")
    doc.xref_set_key(
        xref, "M", f"(D:{_dt.datetime.now(_dt.timezone.utc).strftime('%Y%m%d%H%M%S')}Z)"
    )


def _esc(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _make_nonce(length_hex: int) -> str:
    """Genera il contenuto segnaposto di un campo firma.

    Il segnaposto deve essere riconoscibile con certezza nel file serializzato.
    Una sequenza di zeri non basta: un PDF reale puo' contenere altri tratti di
    zeri esadecimali (immagini, maschere) e piu' firme da riempire. Qui si usa
    un valore casuale, che rende l'abbinamento non ambiguo.
    """
    return secrets.token_hex(length_hex // 2)


def _find_nonce(raw: bytes, nonce: str) -> int:
    """Indica dove inizia il segnaposto nel file serializzato.

    MuPDF riscrive la stringa esadecimale con le lettere maiuscole: si cerca
    quindi in entrambe le forme.
    """
    for forma in (nonce, nonce.upper(), nonce.lower()):
        pos = raw.find(forma.encode("ascii"))
        if pos >= 0:
            return pos
    raise SignatureError("Non è stato possibile individuare il segnaposto della firma.")


def find_signature_field(
    doc: pymupdf.Document, name: str | None = None, xref: int | None = None
) -> int | None:
    """Trova il widget di un campo firma, per xref o per nome.

    Restituisce l'xref del widget, oppure ``None`` se non esiste.
    """
    if xref is not None:
        try:
            if doc.xref_get_key(xref, "FT")[1] == "/Sig":
                return xref
        except Exception:
            return None
        return None
    # I campi modulo non sono sempre esposti come annotazioni della pagina: si
    # scandisce il documento e si affida a /FT, che e' l'autorita' sul tipo.
    for x in range(1, doc.xref_length()):
        try:
            if doc.xref_get_key(x, "FT")[1] != "/Sig":
                continue
        except Exception:
            continue
        if name is None or _field_name(doc, x) == name:
            return x
    return None


def field_is_signed(doc: pymupdf.Document, xref: int) -> bool:
    """Indica se il campo firma contiene gia' una firma valida.

    In un campo firma il widget e il dizionario firma sono lo stesso oggetto,
    quindi ``/Contents`` va letto direttamente sul campo; se ``/V`` punta invece
    a un riferimento indiretto si controlla anche li'.
    """
    candidati = [xref]
    try:
        tipo, valore = doc.xref_get_key(xref, "V")
        # ('name', '/Sig') e' un segnaposto, non un riferimento indiretto
        if tipo == "int" or (str(valore).isdigit() and tipo == "xref"):
            candidati.append(int(valore))
        elif str(valore).isdigit() and str(tipo).isdigit():
            candidati.append(int(valore))
    except Exception:
        pass
    for candidate in candidati:
        try:
            grezzo = doc.xref_get_key(candidate, "Contents")[1]
        except Exception:
            continue
        if not grezzo or grezzo == "null":
            continue
        # xref_get_key decodifica la stringa: si prova come testo esadecimale
        # e, se fallisce, come byte grezzi
        dati = b""
        testo = grezzo.strip("<>").strip()
        if testo and all(c in "0123456789abcdefABCDEF" for c in testo):
            try:
                dati = bytes.fromhex(testo)
            except ValueError:
                dati = b""
        if not dati:
            dati = grezzo.encode("latin-1", "replace")
        # un segnaposto (tutto nulli) non conta come firma
        if dati.strip(b"\x00"):
            return True
    return False


# ------------------------------------------------------------------ verifica


def inspect_signatures(path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    """Elenca le firme presenti in un PDF con i dati del certificato."""
    out: list[dict[str, Any]] = []
    doc = pymupdf.open(str(path))
    try:
        raw: bytes | None = Path(path).read_bytes()
        for i in range(doc.page_count):
            for w in doc[i].widgets() or ():
                if w.field_type_string != "Signature":
                    continue
                out.append(_describe_signature(doc, w, i, raw))
    finally:
        doc.close()
    return out


def _read_pdf_string(raw: bytes, objnum: int) -> bytes:
    """Legge un oggetto stringa PDF direttamente dai byte del file.

    ``xref_get_key`` non e' utilizzabile: il contenuto di ``/Contents`` e'
    binario e la sua decodifica come testo perde i byte non ASCII. Le stringhe
    non possono stare dentro un object stream, quindi si troveranno sempre a
    livello superiore del file.
    """
    # Lo stesso numero di oggetto puo' comparire in piu' generazioni del file:
    # vale l'ultima, cioe' quella a cui punta la tabella xref corrente.
    for sep in (b"\n", b"\r"):
        marker = sep + str(objnum).encode() + b" 0 obj"
        idx = raw.rfind(marker)
        if idx >= 0:
            break
    else:
        return b""
    i = idx + len(marker)
    n = len(raw)
    while i < n and raw[i] in b" \t\r\n":
        i += 1
    if i >= n:
        return b""
    ch = raw[i : i + 1]
    if ch == b"<":
        end = raw.find(b">", i + 1)
        if end < 0:
            return b""
        hexed = re.sub(rb"[^0-9A-Fa-f]", b"", raw[i + 1 : end])
        if len(hexed) % 2:
            hexed = hexed[:-1]
        try:
            return bytes.fromhex(hexed.decode("ascii"))
        except ValueError:
            return b""
    if ch == b"(":
        depth = 0
        j = i
        out = bytearray()
        while j < n:
            c = raw[j : j + 1]
            if c == b"\\":
                nxt = raw[j + 1 : j + 2]
                if nxt in b"01234567":
                    oct_digits = b""
                    k = j + 1
                    while k < n and len(oct_digits) < 3 and raw[k : k + 1] in b"01234567":
                        oct_digits += raw[k : k + 1]
                        k += 1
                    out.append(int(oct_digits, 8) & 0xFF)
                    j = k
                    continue
                mapping = {b"n": 10, b"r": 13, b"t": 9, b"b": 8, b"f": 12}
                if nxt in mapping:
                    out.append(mapping[nxt])
                elif nxt in (b"\n", b"\r"):
                    pass
                elif nxt:
                    out += nxt
                j += 2
                continue
            if c == b"(":
                depth += 1
                if depth > 1:
                    out += c
            elif c == b")":
                depth -= 1
                if depth == 0:
                    return bytes(out)
                out += c
            else:
                out += c
            j += 1
    return b""


CONTENTS_RE = re.compile(
    r"/Contents\s*(<[0-9A-Fa-f\s]*>|\((?:[^()\\]|\\.)*\)|(\d+)\s+0\s+R)",
    re.S,
)


def _decode_literal_string(text: str) -> bytes:
    """Decodifica una stringa letterale PDF ``(...)`` in byte."""
    out = bytearray()
    i = 1  # salta la parentesi aperta
    n = len(text)
    while i < n - 1:
        c = text[i]
        if c == "\\":
            i += 1
            if i >= n - 1:
                break
            nxt = text[i]
            if nxt in "01234567":
                digits = ""
                while i < n - 1 and len(digits) < 3 and text[i] in "01234567":
                    digits += text[i]
                    i += 1
                out.append(int(digits, 8) & 0xFF)
                continue
            out.append({"n": 10, "r": 13, "t": 9, "b": 8, "f": 12}.get(nxt, ord(nxt)) & 0xFF)
            i += 1
            continue
        code = ord(c)
        if code < 256:
            out.append(code)
        else:
            out += str(c).encode("utf-8", "replace")
        i += 1
    return bytes(out)


def _extract_contents(doc: pymupdf.Document, xref: int, raw: bytes | None) -> bytes:
    """Contenuto di ``/Contents`` come byte.

    Il valore e' binario: ``xref_get_key`` lo converte in testo e perde i byte
    non ASCII, quindi si legge il sorgente del dizionario e si decodifica il
    token esadecimale, letterale o indiretto che contiene.
    """
    try:
        obj = doc.xref_object(xref, compressed=False)
    except Exception:
        return b""
    m = CONTENTS_RE.search(obj or "")
    if not m:
        return b""
    token = m.group(1)
    if token.startswith("<"):
        hexed = re.sub(r"[^0-9A-Fa-f]", "", token[1:-1])
        if len(hexed) % 2:
            hexed = hexed[:-1]
        try:
            return bytes.fromhex(hexed)
        except ValueError:
            return b""
    if m.group(2) and raw is not None:
        return _read_pdf_string(raw, int(m.group(2)))
    if token and token.startswith("("):
        return _decode_literal_string(token)
    # ``/Contents`` puo' essere un oggetto indiretto: senza questo caso si
    # finiva col chiamare ``startswith`` su ``None``
    return b""


def _describe_signature(doc: pymupdf.Document, widget: Any, page: int, raw: bytes | None = None) -> dict[str, Any]:
    info: dict[str, Any] = {
        "page": page,
        "name": widget.field_name or "",
        "signed": bool(getattr(widget, "is_signed", False)),
        "subject": "",
        "issuer": "",
        "date": "",
        "trust": "sconosciuto",
        "valid": False,
    }
    try:
        info["date"] = doc.xref_get_key(widget.xref, "M")[1].strip("()")
    except Exception:
        pass
    der = _extract_contents(doc, widget.xref, raw)
    info["signed"] = bool(der)
    info["signature_bytes"] = len(der)
    if not der:
        return info
    try:
        parsed = _parse_cms(der)
        info.update(parsed)
    except Exception:
        info["trust"] = "non leggibile"
    return info


def _parse_cms(der: bytes) -> dict[str, Any]:
    """Estrae soggetto, emittente, data e integrita' da un CMS SignedData."""
    import base64
    from asn1crypto import cms, core

    info = cms.ContentInfo.load(der)
    if info["content_type"].native != "signed_data":
        return {"trust": "formato non riconosciuto", "valid": False}
    signed = info["content"]
    signer_infos = signed["signer_infos"]
    certs = signed["certificates"]
    if not signer_infos:
        return {"trust": "nessun firmatario", "valid": False}
    si = signer_infos[0]
    sid = si["sid"]
    cert = _certificato_del_firmatario(sid, certs)
    out: dict[str, Any] = {
        "valid": True,
        "trust": "firmatario non identificato",
        "digest": si["digest_algorithm"]["algorithm"].native,
    }
    if cert is not None:
        out["subject"] = _flatten_name(cert.subject)
        out["issuer"] = _flatten_name(cert.issuer)
        out["serial"] = f"{cert.serial_number:X}"
        out["not_before"] = str(cert["tbs_certificate"]["validity"]["not_before"].native)
        out["not_after"] = str(cert["tbs_certificate"]["validity"]["not_after"].native)
        out["self_signed"] = cert.subject.dump() == cert.issuer.dump()
    attrs = si["signed_attrs"]
    if attrs:
        for a in attrs:
            # Gli OID non standard arrivano come stringa puntata, non come label.
            t = ATTRIBUTE_LABELS.get(a["type"].dotted, a["type"].native)
            if t == "signing_time":
                try:
                    out["date"] = a["values"][0].native.isoformat()
                except Exception:
                    out["date"] = str(a["values"][0].native)
            elif t == "message_digest":
                out["message_digest"] = a["values"][0].native.hex()
            elif t == "signature_reason":
                out["reason"] = str(a["values"][0].native)
            elif t == "signature_location":
                out["location"] = str(a["values"][0].native)
            elif t == "signer_name":
                out["signer_name"] = str(a["values"][0].native)
    if out.get("self_signed"):
        out["trust"] = "autofirmato (attendibilità non verificata)"
    elif out.get("subject"):
        out["trust"] = "rilasciato da un'autorità"
    return out


def _certificato_del_firmatario(sid, certs) -> Any:
    """Il certificato che identifica il firmatario, se c'è.

    RFC 5652 ammette due forme per ``sid``: ``issuerAndSerialNumber`` e
    ``subjectKeyIdentifier``. Leggere sempre il numero di serie sollevava un
    errore sulle firme che usano la seconda, e la verifica si fermava su una
    firma perfettamente valida.
    """
    if sid is None:
        return None
    scelta = getattr(sid, "chosen", None)
    nome = getattr(sid, "name", "")
    if nome == "issuer_and_serial_number" and scelta is not None:
        wanted = scelta["serial_number"].native
        for c in certs or ():
            candidato = c.chosen
            if getattr(candidato, "serial_number", None) == wanted:
                return candidato
        return None
    if nome == "subject_key_identifier" and scelta is not None:
        wanted = bytes(scelta.native or b"")
        if not wanted:
            return None
        for c in certs or ():
            candidato = c.chosen
            try:
                estensioni = candidato["tbs_certificate"]["extensions"]
            except Exception:
                continue
            for e in estensioni or ():
                try:
                    if e["extn_id"].native != "subject_key_identifier":
                        continue
                    if bytes(e["extn_value"].parsed.native or b"") == wanted:
                        return candidato
                except Exception:
                    continue
    return None


ATTRIBUTE_LABELS = {
    OID_SIGNATURE_REASON: "signature_reason",
    OID_SIGNATURE_LOCATION: "signature_location",
    OID_SIGNER_NAME: "signer_name",
}


def _flatten_name(name: Any) -> str:
    parts = []
    try:
        for rdn in name.chosen:
            for atv in rdn:
                parts.append(f"{atv['type'].native}={atv['value'].native}")
    except Exception:
        try:
            return name.human_friendly
        except Exception:
            return ""
    return ", ".join(parts)


def verify_file(path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    """Firme presenti con verifica di integrita' e attendibilita'."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, padding
    from cryptography import x509

    p = Path(path)
    raw = p.read_bytes()
    out: list[dict[str, Any]] = []
    doc = pymupdf.open(str(p))
    try:
        for i in range(doc.page_count):
            for w in doc[i].widgets() or ():
                if w.field_type_string != "Signature":
                    continue
                info = _describe_signature(doc, w, i, raw)
                info["integrity"] = "non verificata"
                der = _extract_contents(doc, w.xref, raw)
                if not der:
                    info["integrity"] = "documento non firmato"
                    out.append(info)
                    continue
                try:
                    br = _byte_range(doc, w.xref)
                    if br is None:
                        info["integrity"] = "/ByteRange assente"
                        out.append(info)
                        continue
                    a, b, c, d = br
                    covered = raw[a:b] + raw[c:d]
                    info["covered_bytes"] = len(covered)
                    ok_hash, ok_sig = _verify_cms(der, covered, info)
                    if ok_hash and ok_sig:
                        info["integrity"] = "il contenuto non e' stato modificato"
                        info["valid"] = True
                    elif not ok_hash:
                        info["integrity"] = "ATTENZIONE: il contenuto e' stato modificato dopo la firma"
                        info["valid"] = False
                    else:
                        info["integrity"] = "firma non valida"
                        info["valid"] = False
                except Exception as exc:
                    info["integrity"] = f"verifica impossibile ({type(exc).__name__})"
                    # senza questo la voce restava con ``valid`` a True
                    # impostato da ``_parse_cms``: il pannello diceva «firma
                    # valida» mentre l'integrità non era stata nemmeno
                    # controllata
                    info["valid"] = False
                out.append(info)
    finally:
        doc.close()
    return out


def _byte_range(doc: pymupdf.Document, xref: int) -> tuple[int, int, int, int] | None:
    try:
        obj = doc.xref_object(xref, compressed=False)
    except Exception:
        return None
    m = re.search(r"/ByteRange\s*\[([^\]]*)\]", obj or "")
    if not m:
        return None
    try:
        nums = [int(x) for x in m.group(1).split()]
    except ValueError:
        return None
    if len(nums) != 4:
        return None
    return nums[0], nums[1], nums[2], nums[3]


def _verify_cms(der: bytes, covered: bytes, info: dict[str, Any]) -> tuple[bool, bool]:
    """Verifica hash del documento e firma degli attributi.

    Restituisce ``(hash_valido, firma_valida)``.
    """
    from asn1crypto import cms
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

    signed = cms.ContentInfo.load(der)["content"]
    si = signed["signer_infos"][0]
    attrs = si["signed_attrs"]
    if attrs is None:
        return False, False
    stored = None
    for a in attrs:
        if a["type"].dotted == "1.2.840.113549.1.9.4":
            stored = a["values"][0].native
    if stored is None:
        return False, False
    ok_hash = hashlib.sha256(covered).digest() == stored
    info["message_digest"] = stored.hex()

    cert = _certificato_del_firmatario(si["sid"], signed["certificates"])
    if cert is None:
        return ok_hash, False
    pub = x509.load_der_x509_certificate(cert.dump()).public_key()
    sig = si["signature"].native
    try:
        signed_bytes = attrs.untag().dump()
        if isinstance(pub, rsa.RSAPublicKey):
            pub.verify(sig, signed_bytes, padding.PKCS1v15(), hashes.SHA256())
        else:
            from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

            # Nel CMS la firma ECDSA e' grezza r||s, mentre ``cryptography``
            # attende la forma DER.
            size = (pub.curve.key_size + 7) // 8
            if len(sig) == 2 * size:
                sig = encode_dss_signature(
                    int.from_bytes(sig[:size], "big"), int.from_bytes(sig[size:], "big")
                )
            pub.verify(sig, signed_bytes, ec.ECDSA(hashes.SHA256()))
        ok_sig = True
    except Exception:
        ok_sig = False
    return ok_hash, ok_sig
