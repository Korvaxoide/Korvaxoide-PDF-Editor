"""Verifica di accessibilità del documento.

I controlli rispecchiano quelli di Acrobat: lingua, titolo, struttura del
documento, testo alternativo alle immagini, link vuoti, ordine di tabulazione
dei campi e cifratura. Ogni problema ha un'azione correttiva quando questa puo'
essere svolta dal programma.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import pymupdf

from ..core import i18n
from ..core.i18n import tr

#: font base 14: non vanno incorporati, sono presenti in ogni lettore
STANDARD_FONTS = {
    "Helvetica",
    "Helvetica-Bold",
    "Helvetica-Oblique",
    "Helvetica-BoldOblique",
    "Times-Roman",
    "Times-Bold",
    "Times-Italic",
    "Times-BoldItalic",
    "Courier",
    "Courier-Bold",
    "Courier-Oblique",
    "Courier-BoldOblique",
    "Symbol",
    "ZapfDingbats",
    "Arial",
    "Arial,Bold",
    "Arial,Italic",
    "Arial,BoldItalic",
    "ArialMT",
    "Arial-BoldMT",
    "TimesNewRomanPSMT",
    "TimesNewRomanPS-BoldMT",
}


@dataclass
class Finding:
    """Un problema rilevato, con la correzione quando è disponibile."""

    code: str
    title: str
    detail: str = ""
    severity: str = "warning"  # "error" | "warning" | "info"
    pages: list[int] = field(default_factory=list)
    count: int = 0
    #: chiave dell'azione correttiva, "" se il programma non può risolverla
    action: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "title": self.title,
            "detail": self.detail,
            "severity": self.severity,
            "pages": list(self.pages),
            "count": self.count,
            "action": self.action,
        }


def _plurale(n: int, italiano: tuple[str, str], inglese: tuple[str, str]) -> str:
    """«1 immagine non ha», «3 immagini non hanno»: la forma sbagliata si ricorda.

    Le due coppie servono perché l'italiano e l'inglese non si possono tradurre
    a pezzi: in italiano l'azione sta dentro la frase («3 immagini non hanno»),
    in inglese il numero va davanti al nome e il verbo cambia con il plurale
    («3 images have no»). Con una sola coppia, in una delle due lingue la frase
    sarebbe grammaticale solo a metà.
    """
    singolare, plurale = inglese if i18n.lingua() == "en" else italiano
    return f"{n} {singolare if n == 1 else plurale}"


def _normalize_font(name: str) -> str:
    """Rimuove il prefisso di sottoinsieme (ABCDEF+) e gli spazi iniziali."""
    n = str(name or "").strip()
    if "+" in n[:8] and len(n) > 7:
        n = n.split("+", 1)[1]
    return n.replace(" ", "")


def _corpo_struttura(doc: Any) -> list[tuple[str, int]]:
    """Il testo dei dizionari che compongono l'albero strutturale.

    Ogni voce è il corpo di un dizionario con l'indice della pagina logica da
    cui arriva. L'albero può essere un oggetto indiretto — e si segue passando
    dagli xref dei figli — o essere incorporato direttamente nel catalogo, e in
    quel caso si legge il testo. Coprire le due forme è necessario perché i due
    casi si presentano con la stessa frequenza.
    """
    catalogo = doc.pdf_catalog()
    valore = doc.xref_get_key(catalogo, "StructTreeRoot")
    if valore[0] == "dict":
        return [(valore[1], -1)]
    if valore[0] != "xref":
        return []
    visti: set[int] = set()
    uscita: list[tuple[str, int]] = []

    def visita(xref: int, pagina: int) -> None:
        if xref in visti:
            return
        visti.add(xref)
        try:
            corpo = doc.xref_object(xref, compressed=True)
        except Exception:
            return
        uscita.append((corpo, pagina))
        m = re.search(r"/Pg\s+(\d+)\s+0\s+R", corpo)
        if m:
            pagina = int(m.group(1))
        for figlio in re.findall(r"(\d+)\s+0\s+R", _valore_corrente(corpo, "/K")):
            visita(int(figlio), pagina)

    visita(int(valore[1]), -1)
    return uscita


def _valore_corrente(corpo: str, chiave: str) -> str:
    """Il valore grezzo associato a una chiave in un dizionario PDF."""
    m = re.search(re.escape(chiave) + r"\s*(\[[^\]]*\]|<<.*?>>|[^\s/][^\s]*)", corpo, re.S)
    return m.group(1) if m else ""


def _figure_senza_alt(parts: list[tuple[str, int]]) -> list[int]:
    """Le pagine con figure prive di ``/Alt``.

    ``/Alt`` sta sull'elemento strutturale e non sull'oggetto immagine: è l'unico
    posto dove il testo alternativo è scritto, ed è quello che va cercato.
    """
    esito: list[int] = []
    for corpo, pagina in parts:
        for m in re.finditer(r"/S\s*/Figure", corpo):
            fine = corpo.find("/S /", m.end())
            segmento = corpo[m.end(): fine if fine > 0 else len(corpo)]
            if re.search(r"/Alt\s*\(\s*[^)\s]", segmento):
                continue
            esito.append(pagina)
    return esito


# --------------------------------------------------------------------- accessibilità


def accessibility_report(docmod: Any) -> list[Finding]:
    """Esamina il documento e restituisce i problemi di accessibilità.

    Si segnano solo problemi verificabili: nulla viene dichiarato mancante
    senza un controllo reale sul file, così l'utente non perde tempo a
    correggere segnalazioni false.
    """
    esito: list[Finding] = []
    doc = docmod._require()
    meta = {k.lower(): (v or "") for k, v in (docmod.metadata() or {}).items()}

    # lingua del documento
    lingua = (getattr(doc, "language", None) or "").strip()
    if not lingua:
        esito.append(
            Finding(
                "lingua",
                "Lingua del documento non dichiarata",
                "Senza /Lang i lettori di screen reader scelgono una lingua a caso.",
                "warning",
                action="imposta_lingua",
            )
        )

    # titolo
    if not meta.get("title", "").strip():
        esito.append(
            Finding(
                "titolo",
                "Titolo del documento mancante",
                "Il titolo compare nella finestra del lettore e nei motori di ricerca.",
                "warning",
                action="imposta_titolo",
            )
        )

    # struttura: un PDF senza struttura non e' navigabile dagli screen reader
    try:
        catalog = doc.pdf_catalog()
        ha_struttura = "/StructTreeRoot" in doc.xref_object(catalog)
    except Exception:
        ha_struttura = False
    if not ha_struttura:
        esito.append(
            Finding(
                "struttura",
                "Documento non strutturato",
                "Manca l'albero strutturale: gli screen reader non possono distinguere "
                "titoli, tabelle e figure. La correzione automatica non e' affidabile, "
                "perche' richiede di riconoscere il ruolo di ogni elemento.",
                "info",
            )
        )

    # immagini senza testo alternativo
    #
    # ``/Alt`` e' una proprieta' degli elementi strutturali (``/Figure`` dentro
    # ``/StructTreeRoot``), non una chiave dell'oggetto immagine: chiedendola
    # all'xref dell'immagine la risposta e' sempre «null» e il documento
    # risultava pieno di immagini non descritte, anche quando lo erano. Qui si
    # guardano gli elementi strutturali e, se il documento non è strutturato,
    # l'elenco delle figure resta semplicemente fuori dal controllo.
    senza_alt: list[int] = []
    if ha_struttura:
        try:
            senza_alt = _figure_senza_alt(_corpo_struttura(doc))
        except Exception:
            senza_alt = []
    if senza_alt:
        esito.append(
            Finding(
                "immagini_alt",
                "Immagini senza testo alternativo",
                _plurale(
                    len(senza_alt),
                    ("immagine non ha", "immagini non hanno"),
                    ("image has no", "images have no"),
                )
                + tr(" una descrizione. Le immagini con significato vanno "
                      "descritte per chi non le vede."),
                "warning",
                pages=sorted(p for p in set(senza_alt) if p >= 0),
                count=len(senza_alt),
            )
        )

    # link vuoti o malformati
    link_vuoti: list[int] = []
    for i in range(docmod.page_count):
        for l in doc[i].get_links() or ():
            # una destinazione interna vale solo se la pagina esiste davvero:
            # un indice fuori intervallo non porta da nessuna parte
            interno = l.get("page")
            valido_interno = isinstance(legittimo := interno, int) and 0 <= legittimo < docmod.page_count
            if not l.get("uri") and not valido_interno and not l.get("to"):
                link_vuoti.append(i)
    if link_vuoti:
        esito.append(
            Finding(
                "link_vuoti",
                "Link senza destinazione",
                _plurale(
                    len(link_vuoti),
                    ("collegamento non porta", "collegamenti non portano"),
                    ("link points", "links point"),
                )
                + tr(" da nessuna parte."),
                "warning",
                pages=sorted(set(link_vuoti)),
                count=len(link_vuoti),
            )
        )

    # ordine di tabulazione: confronta l'ordine del documento con quello in cui
    # i campi si leggono davvero sulla pagina
    campi = docmod.fields()
    if campi:
        ordine_documento = [(f.page, f.rect.y0, f.rect.x0) for f in campi]
        ordine_lettura = sorted(ordine_documento, key=lambda t: (t[0], round(t[1], 1), t[2]))
        if ordine_documento != ordine_lettura:
            esito.append(
                Finding(
                    "ordine_campi",
                    "Campi fuori ordine di lettura",
                    _plurale(
                        len(campi),
                        ("campo modulo non segue", "campi modulo non seguono"),
                        ("form field does not follow", "form fields do not follow"),
                    )
                    + tr(" l'ordine in cui si leggono sulla pagina: passando da "
                          "un campo all'altro con il tabulatore si saltano avanti "
                          "e indietro."),
                    "warning",
                    count=len(campi),
                    action="ordina_campi",
                )
            )

    # cifratura: blocca i lettori di screen reader
    if docmod.has_encryption:
        esito.append(
            Finding(
                "cifratura",
                "Documento protetto",
                "La cifratura impedisce a molti lettori di screen reader e ai "
                "strumenti automatici di leggere il testo.",
                "error",
                action="rimuovi_protezione",
            )
        )

    # pagine senza testo: tipicamente scansioni da riconoscere
    senza_testo = [i for i in range(docmod.page_count) if not doc[i].get_text().strip()]
    if senza_testo:
        esito.append(
            Finding(
                "senza_testo",
                "Pagine senza testo ricercabile",
                _plurale(
                    len(senza_testo),
                    ("pagina non contiene testo", "pagine non contengono testo"),
                    ("page contains no text", "pages contain no text"),
                )
                + tr(": se sono scansioni il riconoscimento OCR le rende "
                      "ricercabili e accessibili."),
                "info",
                pages=senza_testo,
                count=len(senza_testo),
                action="ocr",
            )
        )
    return esito


# ------------------------------------------------------------------ pre-stampa


def preflight_report(
    docmod: Any,
    min_dpi: int = 300,
    max_megabytes: float = 50.0,
    segnala_rgb: bool = True,
) -> list[Finding]:
    """Controlla il documento prima della stampa o della pubblicazione.

    Rileva quello che in stampa dà problemi: immagini a risoluzione troppo
    bassa, colori non adatti alla stampa, font non incorporati, file troppo
    grandi, pagine bianche e pagine scansionate senza testo.
    """
    esito: list[Finding] = []
    doc = docmod._require()

    # analisi delle immagini: risoluzione reale e spazio colore.
    # La mappaxref -> pagina e larghezza si costruisce una volta sola: rifarla
    # per ogni immagine costerebbe un giro su tutte le pagine.
    larghezze: dict[int, tuple[int, float]] = {}
    for i in range(docmod.page_count):
        for xref in (info[0] for info in doc[i].get_images(full=True)):
            if xref in larghezze:
                continue
            rects = doc[i].get_image_rects(xref)
            if rects:
                larghezze[xref] = (i, max(r.width for r in rects))

    deboli: list[int] = []
    dettaglio: set[str] = set()
    rgb: list[int] = []
    for voce in docmod.image_inventory():
        xref = voce["xref"]
        dove = larghezze.get(xref)
        if dove is None:
            continue
        pagina, larghezza_pt = dove
        # lo spazio colore si legge dal pixmap: nel file può essere un
        # riferimento indiretto, e la chiave va risolta
        try:
            canali = pymupdf.Pixmap(doc, xref).n
        except Exception:
            canali = voce.get("colors", 0)
        if canali == 3 and segnala_rgb:
            rgb.append(pagina)
        if larghezza_pt > 0:
            dpi = voce["width"] * 72.0 / larghezza_pt
            if dpi < min_dpi:
                deboli.append(pagina)
                dettaglio.add(f"{dpi:.0f} dpi")
    del larghezze

    if deboli:
        elenco = ", ".join(sorted(dettaglio)[:4]) + ("…" if len(dettaglio) > 4 else "")
        esito.append(
            Finding(
                "risoluzione",
                "Immagini a risoluzione bassa",
                _plurale(
                    len(deboli),
                    ("immagine è", "immagini sono"),
                    ("image is", "images are"),
                )
                + tr(" sotto i {dpi} dpi: in stampa usciranno sfocate. Valori "
                      "rilevati: {valori}.").format(dpi=min_dpi, valori=elenco),
                "warning",
                pages=sorted(set(deboli)),
                count=len(deboli),
                action="riduci_risoluzione",
            )
        )
    if rgb:
        esito.append(
            Finding(
                "spazio_colore",
                "Immagini in RGB",
                _plurale(
                    len(rgb),
                    ("immagine è", "immagini sono"),
                    ("image is", "images are"),
                )
                + tr(" in RGB. Per la stampa in quadricromia vanno convertite in "
                      "CMYK: gli stampatori le richiedono e la conversione tardi "
                      "può farle sbiecare."),
                "info",
                pages=sorted(set(rgb)),
                count=len(rgb),
            )
        )

    # font non incorporati
    mancanti: set[str] = set()
    for i in range(docmod.page_count):
        for voce in doc[i].get_fonts(full=True):
            xref, estensione, tipo, basefont = voce[0], voce[1], voce[2], voce[3]
            del xref, tipo
            if estensione and estensione != "n/a":
                continue  # incorporato
            nome = _normalize_font(basefont)
            if nome in STANDARD_FONTS or nome in {
                _normalize_font(n) for n in STANDARD_FONTS
            }:
                continue  # font standard, presenti in ogni lettore
            mancanti.add(str(basefont))
    if mancanti:
        # L'elenco porta con se' i puntini di sospensione: «incorporato» e
        # «incorporati» concordano col numero, quindi la frase intera si
        # traduce e non si affianca a pezzi.
        elenco = ", ".join(sorted(mancanti)[:6]) + ("…" if len(mancanti) > 6 else "")
        esito.append(
            Finding(
                "font",
                tr("Font non incorporati"),
                tr("{font} nel file ({elenco}). Su un altro computer il testo puo' "
                   "apparire diverso.")
                .format(
                    font=_plurale(
                        len(mancanti),
                        ("font usato non è incorporato", "font usati non sono incorporati"),
                        ("used font is not embedded", "used fonts are not embedded"),
                    ),
                    elenco=elenco,
                ),
                "warning",
                count=len(mancanti),
            )
        )

    # dimensione del file
    peso = len(doc.tobytes())
    if peso > max_megabytes * 1_048_576:
        esito.append(
            Finding(
                "dimensione",
                "File molto grande",
                tr("Il documento pesa {mb} MB. La riduzione delle immagini lo "
                   "rende molto piu' leggero.").format(mb=peso / 1_048_576),
                "info",
                action="riduci_file",
            )
        )

    # pagine bianche
    bianche: list[int] = []
    for i in range(docmod.page_count):
        campioni = docmod.render(i, dpi=18, annots=False, view_rotation=False).samples
        # si campiona una riga su quattro: una pagina interamente bianca si
        # riconosce senza rasterizzarla per intero
        if campioni and not any(c < 245 for c in campioni[::37]):
            bianche.append(i)
    if bianche:
        esito.append(
            Finding(
                "pagine_bianche",
                "Pagine bianche",
                _plurale(
                    len(bianche),
                    ("pagina è", "pagine sono"),
                    ("page is", "pages are"),
                )
                + tr(" completamente bianca. In un PDF inviato per stampa fanno "
                      "sprecare carta."),
                "info",
                pages=bianche,
                count=len(bianche),
            )
        )

    # pagine senza testo: scansioni da riconoscere
    senza_testo = [i for i in range(docmod.page_count) if not doc[i].get_text().strip()]
    if senza_testo:
        esito.append(
            Finding(
                "senza_testo",
                "Pagine senza testo ricercabile",
                _plurale(
                    len(senza_testo),
                    ("pagina non contiene testo", "pagine non contengono testo"),
                    ("page contains no text", "pages contain no text"),
                )
                + tr(". Se sono scansioni, l'OCR le rende ricercabili."),
                "info",
                pages=senza_testo,
                count=len(senza_testo),
                action="ocr",
            )
        )

    # cifratura
    if docmod.has_encryption:
        esito.append(
            Finding(
                "cifratura",
                "Documento protetto",
                "Molte stampanti e servizi di stampa non sanno stampare un PDF "
                "protetto: la stampa puo' risultare vuota.",
                "warning",
                action="rimuovi_protezione",
            )
        )

    return esito
