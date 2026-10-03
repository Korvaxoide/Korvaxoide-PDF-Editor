"""Stampa, esportazione PDF/A e presentazione."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pymupdf
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtPrintSupport import QPrintDialog, QPrinter, QPrinterInfo
from PySide6.QtWidgets import QWidget

from ..core import document as docmod
from ..core.i18n import tr


def print_document(parent: QWidget, doc: docmod.Document, dpi: int = 300) -> None:
    """Apre la finestra di stampa e stampa le pagine selezionate."""
    printer = QPrinter(QPrinter.HighResolution)
    printer.setFromTo(1, doc.page_count)
    dialog = QPrintDialog(printer, parent)
    dialog.setWindowTitle(tr("Stampa documento"))
    if dialog.exec() != QPrintDialog.Accepted:
        return
    # L'intervallo va preso dalla finestra: senza questo la scelta «pagine 3-5»
    # veniva ignorata e si stampava tutto il documento
    da = max(1, int(printer.fromPage() or 1)) - 1
    a = int(printer.toPage() or doc.page_count) - 1
    render_to_printer(doc, printer, page_range=(da, a), dpi=dpi)


def render_to_printer(
    doc: docmod.Document,
    printer: QPrinter,
    page_range: tuple[int, int] | None = None,
    dpi: int = 300,
) -> None:
    """Disegna le pagine del documento sulla stampante.

    Solleva ``RuntimeError`` se la stampante non accetta il foglio o se
    ``newPage()`` fallisce a meta' stampa: chi chiama deve tradurlo in un
    messaggio per l'utente.
    """
    painter = QPainter()
    if not painter.begin(printer):
        raise RuntimeError(
            "La stampante non ha accettato il foglio. Verifica che sia collegata "
            "e che abbia carta, poi riprova."
        )
    try:
        first, last = page_range or (0, doc.page_count - 1)
        first = max(0, first)
        last = min(doc.page_count - 1, last)
        res = printer.resolution()
        # una stampante che non conosce la propria risoluzione restituisce 0:
        # con un dpi pari a zero il rendering non termina e la stampa resta
        # bloccata senza mai mostrare nulla
        res = int(res) if res and int(res) > 0 else 300
        # il rendering non puo' superare la risoluzione della stampante: chiederle
        # piu' punti significa solo tempo speso senza guadagno
        res_effettivo = max(36, min(1200, int(dpi) or 300, res))
        for i in range(first, last + 1):
            if i > first and not printer.newPage():
                # carta esaurita o formato non supportato: senza avviso la
                # stampa si fermava e sembrava completata
                raise RuntimeError(
                    f"La stampante non ha accettato una nuova pagina dopo la "
                    f"pagina {i}. La stampa si e' fermata a meta'."
                )
            info = doc.page_info(i)
            size_pt = (info.rect.width, info.rect.height)
            rect = printer.pageLayout().paintRectPixels(res)
            scale = min(rect.width() / size_pt[0], rect.height() / size_pt[1])
            w = max(1, int(size_pt[0] * scale))
            h = max(1, int(size_pt[1] * scale))
            # ``view_rotation=False``: si stampa la pagina come e' salvata nel
            # file, non come l'utente l'ha ruotata a schermo
            pix = doc.render(i, dpi=res_effettivo, view_rotation=False)
            img = _pixmap_to_qimage(pix)
            x = (rect.width() - w) // 2
            y = (rect.height() - h) // 2
            painter.drawImage(x, y, img.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
    finally:
        painter.end()


def _pixmap_to_qimage(pix) -> Any:
    from ..ui.page_items import pixmap_to_qimage

    return pixmap_to_qimage(pix)


# ------------------------------------------------------------------- PDF/A


def find_ghostscript() -> str:
    """Percorso dell'eseguibile Ghostscript, se disponibile."""
    for name in ("gswin64c", "gswin32c", "gs", "ghostscript"):
        path = shutil.which(name)
        if path:
            return path
    for cand in (
        r"C:\Program Files\gs\gs10.03.1\bin\gswin64c.exe",
        r"C:\Program Files\gs\gs10.02.1\bin\gswin64c.exe",
        "/usr/bin/gs",
        "/usr/local/bin/gs",
        "/opt/homebrew/bin/gs",
    ):
        if os.path.exists(cand):
            return cand
    return ""


PDFA_PROFILES = {
    "1b": "-dPDFA=1",
    "2b": "-dPDFA=2",
    "3b": "-dPDFA=3",
}


def _pdfa_part(level: str) -> str:
    """Parte numerica del livello PDF/A.

    I livelli sono indicati come «2b», ma a Ghostscript (``-dPDFA=``) e ai
    metadati XMP (``pdfaid:part``) serve solo la parte, cioe' «2». Prendere
    l'ultimo carattere restituirebbe «b»: la conversione fallirebbe e il
    file risulterebbe dichiarato come PDF/A-«b».
    """
    return {"1": "1", "1b": "1", "2": "2", "2b": "2", "3": "3", "3b": "3"}.get(
        str(level).strip().lower(), "2"
    )


def _pdfa_conformance(level: str) -> str:
    """Lettera di conformita' richiesta: «b» per tutti i livelli offerti."""
    testo = str(level).strip().lower()
    return testo[-1] if testo[-1:] in ("a", "b", "u") else "b"


def convert_pdfa(doc: docmod.Document, path: str, pages: list[int], level: str = "2b") -> tuple[bool, str]:
    """Converte in PDF/A tramite Ghostscript.

    Restituisce ``(ok, messaggio)``. Se Ghostscript non e' installato viene
    prodotto comunque un PDF valido con i metadati di identazione, segnalando
    pero' che la conversione completa non e' stata eseguita.
    """
    gs = find_ghostscript()
    tmp_dir = Path(tempfile.mkdtemp(prefix="korvaxoide_pdfa_"))
    try:
        src = tmp_dir / "in.pdf"
        doc.export(str(src), pages)
        if not gs:
            # Non si puo' salvare sul file appena aperto: PyMuPDF lo rifiuta
            # («save to original must be incremental») e la finestra mostrava
            # l'errore grezzo lasciando per terra un file non convertito.
            # Si scrive a parte e si sostituisce, come fa _stamp_pdfa_metadata.
            bersaglio = Path(path)
            provvisorio = bersaglio.with_name(bersaglio.name + "_noa.pdf")
            doc.export(str(provvisorio), pages)
            meta = doc.metadata()
            d = pymupdf.open(str(provvisorio))
            try:
                d.set_metadata(
                    {
                        **meta,
                        "producer": f"Korvaxoide: PDF Editor (PDF/A {level} non applicato)",
                    }
                )
                d.save(str(provvisorio) + ".tmp", garbage=3, deflate=True)
            finally:
                d.close()
            Path(str(provvisorio) + ".tmp").replace(provvisorio)
            provvisorio.replace(bersaglio)
            return (
                False,
                "Ghostscript non è installato: il PDF è stato esportato ma non convertito in PDF/A.\n"
                "Su Windows installa Ghostscript; su Linux il pacchetto «ghostscript».",
            )
        icc = Path(path).with_suffix(".icc")
        args = [
            gs,
            "-dPDFA=" + _pdfa_part(level),
            "-dBATCH", "-dNOPAUSE", "-dNOOUTERSAVE", "-dQUIET",
            "-sColorConversionStrategy=RGB",
            f"-sDEVICE=pdfwrite",
            # senza questo Ghostscript segnala ogni non conformita' ma produce
            # comunque il file: la conversione risultava «riuscita» anche se il
            # PDF non era valido
            f"-sOutputFile={path}",
            str(src),
        ]
        if level.startswith("1") and icc.exists():
            args.insert(-1, f"-sOutputICCProfile={icc}")
        res = subprocess.run(args, capture_output=True, text=True, timeout=600)
        if res.returncode != 0 or not Path(path).exists():
            # con -dQUIET Ghostscript non scrive quasi nulla: si mostra quello
            # che c'e', altrimenti l'utente vede «non riuscita:» e basta
            dettaglio = (res.stderr or res.stdout or "").strip()
            if not dettaglio:
                dettaglio = (
                    f"Ghostscript ha restituito il codice {res.returncode} senza "
                    f"messaggi. Livello richiesto: PDF/A-{level}."
                )
            return False, f"Conversione in PDF/A-{level} non riuscita:\n{dettaglio[-500:]}"
        if not _stamp_pdfa_metadata(path, level):
            return (
                False,
                f"Il file è stato convertito in PDF/A-{level} ma non è stato "
                f"possibile scrivere i metadati di identificazione: "
                f"{Path(path).name} potrebbe non essere conforme.",
            )
        return True, f"Convertito in PDF/A-{level}: {Path(path).name}"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _stamp_pdfa_metadata(path: str, level: str) -> bool:
    """Aggiunge XMP e identificazione richiesti da PDF/A.

    Restituisce ``False`` se l'operazione non riesce: un PDF/A senza i
    metadati di identificazione non e' conforme, quindi vale la pena
    saperlo. La scrittura non puo' essere incrementale: PyMuPDF non
    abbina mai una scrittura incrementale alla raccolta dei rifiuti.
    """
    bersaglio = Path(path)
    provvisorio = bersaglio.with_name(bersaglio.name + "_meta.pdf")
    d = pymupdf.open(path)
    try:
        meta = dict(d.metadata or {})
        meta["producer"] = f"Korvaxoide: PDF Editor (PDF/A {level})"
        d.set_metadata(meta)
        # ``set_xml_metadata`` sostituisce l'intero pacchetto: ricostruirlo da
        # zero cancellava autore, titolo e gli altri metadati XMP che il
        # documento aveva. Qui si aggiunge solo l'identificazione PDF/A a
        # quello che c'era gia'.
        d.set_xml_metadata(
            _xmp(level, esistente=d.get_xml_metadata() or "", meta=meta)
        )
        # non si puo' salvare sul file aperto: si scrive accanto e si
        # sostituisce, cosi' un errore non lascia il file a metà
        d.save(str(provvisorio), garbage=3, deflate=True)
        provvisorio.replace(bersaglio)
        return True
    except Exception as exc:
        print(f"metadati PDF/A non applicati: {exc}", file=sys.stderr)
        return False
    finally:
        try:
            d.close()
        except Exception:
            pass
        provvisorio.unlink(missing_ok=True)


def _xmp(
    level: str,
    esistente: str = "",
    meta: dict[str, Any] | None = None,
) -> str:
    """Pacchetto XMP con l'identificazione PDF/A, mantenendo il resto.

    PDF/A pretende anche i metadati ``xmp:CreateDate``, ``xmp:ModifyDate``,
    ``xmp:CreatorTool`` e ``pdf:Producer``: senza quelli un validatore
    rifiuta il file. Vengono presi dal documento e, se mancano, compilati con
    la data corrente.
    """
    part = _pdfa_part(level)
    conformance = _pdfa_conformance(level).upper()
    info = dict(meta or {})
    adesso = datetime.now().astimezone().isoformat(timespec="seconds")
    creazione = _xmp_date(info.get("creationDate")) or adesso
    modifica = _xmp_date(info.get("modDate")) or adesso
    titolo = _xml_escape(info.get("title") or "")
    autore = _xml_escape(info.get("author") or "")
    soggetto = _xml_escape(info.get("subject") or "")
    parole = _xml_escape(info.get("keywords") or "")
    produttore = _xml_escape(info.get("producer") or "Korvaxoide: PDF Editor")
    strumento = _xml_escape(info.get("creator") or "Korvaxoide: PDF Editor")

    # il pacchetto esistente viene conservato: aggiungere una seconda sezione
    # rdf:Description mantiene autore, titolo e campi personalizzati
    blocco_prima = ""
    if esistente and "pdfaid:part" not in esistente:
        interno = _solo_corpo_xmp(esistente)
        if interno:
            blocco_prima = interno

    return f"""<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="Korvaxoide PDF Editor">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
{blocco_prima}  <rdf:Description rdf:about="" xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/">
   <pdfaid:part>{part}</pdfaid:part>
   <pdfaid:conformance>{conformance}</pdfaid:conformance>
  </rdf:Description>
  <rdf:Description rdf:about="" xmlns:xmp="http://ns.adobe.com/xap/1.0/">
   <xmp:CreateDate>{creazione}</xmp:CreateDate>
   <xmp:ModifyDate>{modifica}</xmp:ModifyDate>
   <xmp:CreatorTool>{strumento}</xmp:CreatorTool>
  </rdf:Description>
  <rdf:Description rdf:about="" xmlns:pdf="http://ns.adobe.com/pdf/1.3/">
   <pdf:Producer>{produttore}</pdf:Producer>
  </rdf:Description>
  <rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/">
   <dc:title><rdf:Alt><rdf:li xml:lang="x-default">{titolo}</rdf:li></rdf:Alt></dc:title>
   <dc:creator><rdf:Seq><rdf:li>{autore}</rdf:li></rdf:Seq></dc:creator>
   <dc:description><rdf:Alt><rdf:li xml:lang="x-default">{soggetto}</rdf:li></rdf:Alt></dc:description>
  </rdf:Description>
  <rdf:Description rdf:about="" xmlns:pdf="http://ns.adobe.com/pdf/1.3/">
   <pdf:Keywords>{parole}</pdf:Keywords>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""


def _solo_corpo_xmp(testo: str) -> str:
    """Le sezioni ``rdf:Description`` del pacchetto XMP esistente.

    Si estrae il contenuto di ``rdf:RDF``, non l'elemento stesso: reinserirlo
    dentro il pacchetto nuovo produceva un ``rdf:RDF`` annidato, che non è
    XMP valido.
    """
    inizio = testo.find("<rdf:RDF")
    if inizio < 0:
        return ""
    apri = testo.find(">", inizio)
    fine = testo.rfind("</rdf:RDF>")
    if apri < 0 or fine < 0 or fine <= apri:
        return ""
    corpo = testo[apri + 1:fine].strip()
    if not corpo:
        return ""
    righe = [r for r in (riga.strip() for riga in corpo.splitlines()) if r]
    return "\n".join(f"  {r}" for r in righe) + "\n"


def _xmp_date(valore: Any) -> str:
    """Una data in formato XMP (ISO 8601) partendo da quella del documento."""
    testo = str(valore or "").strip()
    if not testo:
        return ""
    m = re.search(r"(\d{4})-?(\d{2})-?(\d{2})(?:[T ](\d{2}):?(\d{2})?:?(\d{2}))?", testo)
    if not m:
        return ""
    a, mo, g = m.group(1), m.group(2), m.group(3)
    if not m.group(4):
        return f"{a}-{mo}-{g}T00:00:00"
    return f"{a}-{mo}-{g}T{m.group(4)}:{m.group(5)}:{m.group(6)}"


def _xml_escape(valore: Any) -> str:
    testo = str(valore or "")
    return (
        testo.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def available_printers() -> list[str]:
    """Nomi delle stampanti configurate nel sistema."""
    try:
        return [p.printerName() for p in QPrinterInfo.availablePrinters()]
    except Exception:
        return []
