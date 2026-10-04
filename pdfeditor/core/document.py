"""Modello del documento PDF.

Incapsula ``pymupdf.Document`` e mette a disposizione tutte le operazioni di
modifica (pagine, annotazioni, testo, immagini, moduli, sicurezza) con supporto
all'annullamento. Il modulo non importa Qt: restituisce ``Pixmap`` e dati grezzi,
lasciando la conversione in immagini alla UI.

Strategia di annullamento
-------------------------
``PyMuPDF`` 1.28 non permette di ricreare un oggetto cancellato partendo dal suo
xref (non esistono ``add_object``/``insert_annot``), quindi ogni modifica viene
annullata ripristinando una copia completa del documento. Ogni operazione è
registrata come coppia (prima, dopo) e lo stack viene potato quando il consumo
di memoria supera il budget impostato.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence

import pymupdf

from . import geometry as geo
from . import textlayout
from . import units
from .i18n import tr
from .history import Command, HistoryStack

MIB = 1024 * 1024
UNDO_BUDGET = 220 * MIB


class DocumentError(Exception):
    """Errore operativo sul documento (formato, permessi, struttura)."""


# --------------------------------------------------------------------------- eventi


class EventBus:
    """Semplice bus di eventi sincroni con gestione delle eccezioni."""

    def __init__(self) -> None:
        self._subs: dict[str, list[Callable[..., None]]] = {}
        self._any: list[Callable[[str, tuple], None]] = []

    def on(self, name: str, fn: Callable[..., None]) -> Callable[..., None]:
        self._subs.setdefault(name, []).append(fn)
        return fn

    def on_any(self, fn: Callable[[str, tuple], None]) -> Callable[[str, tuple], None]:
        self._any.append(fn)
        return fn

    def off(self, name: str, fn: Callable[..., None]) -> None:
        if fn in self._subs.get(name, ()):
            self._subs[name].remove(fn)

    def emit(self, name: str, *args: Any) -> None:
        for fn in list(self._subs.get(name, ())):
            try:
                fn(*args)
            except Exception:
                pass
        for fn in list(self._any):
            try:
                fn(name, args)
            except Exception:
                pass


# --------------------------------------------------------------------------- dati


@dataclass
class PageInfo:
    """Geometria di una pagina, con rectangolo nel sistema mostrato a schermo."""

    index: int
    rect: geo.Rect
    mediabox: geo.Rect
    cropbox: geo.Rect
    rotation: int = 0
    label: str = ""

    @property
    def is_landscape(self) -> bool:
        return self.rect.width > self.rect.height

    @property
    def size_pt(self) -> tuple[float, float]:
        return self.rect.width, self.rect.height


# ``Widget.border_style`` accetta una lettera, non un intero.
BORDER_STYLES = {0: "", 1: "S", 2: "D", 3: "B", 4: "I", 5: "U"}
def border_style_names() -> dict[int, str]:
    """Il nome leggibile di ogni stile di bordo, nella lingua in uso.

    I nomi arrivano alla finestra di dialogo, quindi sono chiavi di
    traduzione. Sta in una funzione e non in un dizionario di modulo perche'
    un dizionario fisserebbe la lingua al primo import, che non e'
    necessariamente quella scelta poi dall'utente.
    """
    return {
        0: tr("Nessuno"),
        1: tr("Continuo"),
        2: tr("Tratteggio"),
        3: tr("Rialzato"),
        4: tr("Incassato"),
        5: tr("Sottolineato"),
    }


def border_style_code(value: Any) -> str:
    """Normalizza il tipo di bordo in un valore accettato da PyMuPDF."""
    if isinstance(value, str):
        return value.strip()[:1].upper() or "S"
    try:
        return BORDER_STYLES.get(int(value), "S")
    except (TypeError, ValueError):
        return "S"


def _radio_group_of(field_name: str) -> str:
    """Nome del gruppo a cui appartiene un pulsante di opzione.

    I pulsanti figli si chiamano ``{gruppo}#{i}`` oppure ``{gruppo}.{i}`` a
    seconda di chi li ha creati; il padre porta il nome del gruppo.
    """
    nome = field_name or ""
    for sep in ("#", "."):
        if sep in nome:
            return nome.rsplit(sep, 1)[0]
    return nome


def _radio_state_name(group: str, field_name: str) -> str:
    """Nome dello stato acceso di un pulsante, senza il ``/`` iniziale."""
    nome = field_name or ""
    for sep in ("#", "."):
        if sep in nome:
            return nome.rsplit(sep, 1)[1] or "Yes"
    return nome or "Yes"


def _radio_add_state(doc: pymupdf.Document, xref: int, stato: str) -> None:
    """Dà a un pulsante di opzione uno stato acceso con un nome proprio.

    PyMuPDF crea ``/AP /N`` con ``/Off`` e ``/Yes`` per ogni pulsante: se tutte
    le opzioni di un gruppo esportassero ``Yes``, il campo padre non potrebbe
    dire quale sia stata scelta e ogni altra applicazione leggerebbe la stessa
    risposta per tutte le opzioni. Ogni pulsante ha un aspetto acceso proprio,
    quindi basta rinominarlo con il nome dell'opzione, che è il valore che
    finisce nel ``/V``.
    """
    if not stato or stato == "Yes":
        return
    try:
        aspetto = doc.xref_get_key(xref, "AP")
        if aspetto[0] != "dict":
            return
        dentro = re.search(r"/N\s*<<(.*?)>>", aspetto[1], re.S)
        if dentro is None:
            return
        interno = dentro.group(1).rstrip()
        if re.search(rf"(?:^|/){re.escape(stato)}\s", interno):
            return
        acceso = re.search(r"/(?:Yes|On|1)\s+(\d+)\s+0\s+R", interno)
        if acceso is None:
            return
        rinominato = interno.replace(
            f"/Yes {acceso.group(1)} 0 R", f"/{stato} {acceso.group(1)} 0 R"
        )
        doc.xref_set_key(xref, "AP", f"<</N<<{rinominato}>>>>")
    except Exception:
        # un aspetto non rinominabile non deve far fallire la creazione del
        # gruppo: il pulsante resta funzionante con il /Yes di PyMuPDF
        return


def _radio_own_state(doc: pymupdf.Document, xref: int, stato: str) -> str:
    """Nome dello stato acceso da usare per un pulsante, se il gruppo ne ha uno.

    Nei gruppi creati dall'editor ogni pulsante ha uno stato proprio; in quelli
    arrivati da altri programmi c'e' solo il ``/Yes`` comune, e va usato quello.
    """
    if not stato:
        return "/Yes"
    try:
        aspetto = doc.xref_get_key(xref, "AP")
        if aspetto[0] != "dict":
            return "/Yes"
        dentro = re.search(r"/N\s*<<(.*?)>>", aspetto[1], re.S)
        if dentro is not None and re.search(rf"(?:^|/){re.escape(stato)}\s", dentro.group(1)):
            return f"/{stato}"
    except Exception:
        pass
    return "/Yes"


def _normalize_field_props(props: dict[str, Any]) -> dict[str, Any]:
    """Riconduce le proprietà di un campo ai tipi che PyMuPDF accetta.

    ``Widget.border_style`` vuole una lettera e non un intero: la finestra
    invia l'indice della tendina (perché è quello che conosce l'utente) e
    l'assegnazione riusciva, ma il ``w.update()`` successivo sollevava
    ``AttributeError: 'int' object has no attribute 'upper'``. Così
    «Proprietà del campo…» non applicava niente e mostrava solo l'errore.
    Anche ``text_font`` va ricondotto a un nome che la ``/DA`` accetta.
    """
    out = dict(props)
    if "border_style" in out:
        out["border_style"] = border_style_code(out["border_style"])
    if "text_font" in out:
        out["text_font"] = textlayout.font_da_name(out["text_font"])
    if "field_flags" in out:
        try:
            out["field_flags"] = int(out["field_flags"])
        except (TypeError, ValueError):
            out.pop("field_flags")
    if "text_fontsize" in out:
        try:
            out["text_fontsize"] = float(out["text_fontsize"])
        except (TypeError, ValueError):
            out.pop("text_fontsize")
    return out


FIELD_KIND = {
    "Text": "text",
    "CheckBox": "toggle",
    "RadioButton": "toggle",
    "ComboBox": "choice",
    "ListBox": "choice",
    "Button": "button",
    "Signature": "signature",
}

WIDGET_TYPES = {
    "text": pymupdf.PDF_WIDGET_TYPE_TEXT,
    "checkbox": pymupdf.PDF_WIDGET_TYPE_CHECKBOX,
    "radio": pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON,
    "combo": pymupdf.PDF_WIDGET_TYPE_COMBOBOX,
    "list": pymupdf.PDF_WIDGET_TYPE_LISTBOX,
    "button": pymupdf.PDF_WIDGET_TYPE_BUTTON,
    "signature": pymupdf.PDF_WIDGET_TYPE_SIGNATURE,
}


@dataclass
class FieldInfo:
    """Descrizione normalizzata di un campo modulo."""

    xref: int
    page: int
    name: str
    type: str
    value: Any
    rect: geo.Rect
    flags: int = 0
    maxlen: int = 0
    font: str = "Helv"
    fontsize: float = 0.0
    text_color: tuple[float, float, float] = (0, 0, 0)
    fill_color: tuple[float, float, float] | None = None
    border_style: str = "S"
    border_width: float = 1.0
    border_color: tuple[float, float, float] = (0, 0, 0)
    options: list[str] = field(default_factory=list)
    is_signed: bool = False
    tooltip: str = ""
    choice_editable: bool = False
    #: vero per il campo padre che raggruppa i pulsanti di opzione: copre
    #: l'intera area del gruppo ma non è un pulsante e non va cliccato
    is_group: bool = False

    @property
    def read_only(self) -> bool:
        return bool(self.flags & 1)

    @property
    def required(self) -> bool:
        return bool(self.flags & 2)

    @property
    def multiline(self) -> bool:
        return bool(self.flags & (1 << 12))

    @property
    def password(self) -> bool:
        return bool(self.flags & (1 << 13))

    @property
    def comb(self) -> bool:
        return bool(self.flags & (1 << 24))

    @property
    def kind(self) -> str:
        """Categoria larga usata dalla UI."""
        return FIELD_KIND.get(self.type, "text")

    @property
    def label(self) -> str:
        return self.name or f"campo_{self.xref}"


# --------------------------------------------------------------------------- comandi


class SnapshotCommand(Command):
    """Annullamento basato su due copie complete del documento."""

    byte_cost = 0

    def __init__(self, doc: "Document", text: str, before: bytes, after: bytes) -> None:
        self.doc = doc
        self.text = text
        self._before = before
        self._after = after
        self.byte_cost = len(before) + len(after)

    def redo(self) -> None:
        self.doc._restore(self._after)

    def undo(self) -> None:
        self.doc._restore(self._before)

    def drop(self) -> None:
        self._before = b""
        self._after = b""
        self.byte_cost = 0


# --------------------------------------------------------------------------- documento


class BoxLike(Protocol):
    """Riquadro con origine e dimensioni, come i QRectF di Qt.

    Il nucleo resta indipendente da Qt: questa forma permette di passare
    direttamente i rettangoli della vista senza importare PySide6 qui.
    """

    def x(self) -> float: ...
    def y(self) -> float: ...
    def width(self) -> float: ...
    def height(self) -> float: ...


class Document:
    """Documento PDF aperto in memoria, con cronologia e stato di modifica."""

    def __init__(self, events: EventBus | None = None) -> None:
        self.doc: pymupdf.Document | None = None
        self.path: Path | None = None
        self.dirty = False
        self.events = events or EventBus()
        self.history = HistoryStack(limit=120)
        self._view_rot: dict[int, int] = {}
        self._pixmap_cache: dict[tuple, pymupdf.Pixmap] = {}
        self._word_cache: dict[int, list[tuple[geo.Rect, str]]] = {}
        self._undo_enabled = True
        # il file di partenza era protetto e la cifratura e' andata perduta
        # in memoria: salvare cosi' produrrebbe un PDF senza password
        self._was_encrypted = False
        self._encryption_lost = False

    # ---------------------------------------------------------------- ciclo di vita

    def open(self, path: str | os.PathLike[str], password: str = "") -> None:
        """Apre un PDF esistente."""
        p = Path(path)
        if not p.exists():
            raise DocumentError(tr("File non trovato: {file}").format(file=p))
        if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"):
            self.open_images([p])
            return
        try:
            doc = pymupdf.open(str(p))
        except pymupdf.FileDataError as exc:
            raise DocumentError(
                    tr("File non leggibile come PDF: {errore}").format(errore=exc)
                ) from exc
        except pymupdf.EmptyFileError as exc:
            raise DocumentError("File vuoto o non valido.") from exc
        except Exception as exc:
            raise DocumentError(
                    tr("Impossibile aprire il file: {errore}").format(errore=exc)
                ) from exc
        if doc.needs_pass and not doc.authenticate(password):
            doc.close()
            raise DocumentError("Password errata o documento protetto.")
        if doc.page_count == 0:
            doc.close()
            raise DocumentError("Il file non contiene pagine: non è un documento valido.")
        if not doc.is_pdf:
            # MuPDF apre anche i file di testo come documento: qui non sono
            # utilizzabili, ed è meglio dirlo che mostrarne un rendering vuoto.
            fmt = (doc.metadata or {}).get("format", "sconosciuto")
            doc.close()
            raise DocumentError(
                tr("Il file è un documento di formato «{formato}», non un PDF.").format(formato=fmt)
            )
        # va registrato prima di _adopt: dopo, has_encryption potrebbe già
        # valere False se MuPDF ha già rilasciato il cifrario. Si legge solo
        # sui PDF veri: su altri formati pdf_trailer solleva un'eccezione.
        protetto = "/Encrypt" in doc.pdf_trailer()
        self._adopt(doc)
        self.path = p
        self.dirty = False
        self._was_encrypted = protetto
        self._encryption_lost = False
        self.history.clear()
        self.events.emit("opened", self)
        self.events.emit("pages", self.page_count)
        self.events.emit("dirty", False)

    def new(self, width: float | None = None, height: float | None = None) -> None:
        """Crea un documento vuoto con una pagina (A4 per default)."""
        w, h = (width, height) if width and height else units.PAGE_SIZES["A4"]
        doc = pymupdf.open()
        doc.new_page(width=w, height=h)
        self._adopt(doc)
        self.path = None
        self.dirty = True
        self._was_encrypted = False
        self._encryption_lost = False
        self.history.clear()
        self.events.emit("opened", self)
        self.events.emit("pages", self.page_count)
        self.events.emit("dirty", True)

    def open_images(self, paths: Sequence[str | os.PathLike[str]]) -> None:
        """Crea un PDF da una o piu immagini, una per pagina."""
        doc = pymupdf.open()
        for p in paths:
            img = pymupdf.open(str(p))
            rect = img.load_page(0).rect
            pdf_bytes = img.convert_to_pdf()
            img.close()
            src = pymupdf.open("pdf", pdf_bytes)
            page = doc.new_page(width=rect.width, height=rect.height)
            page.show_pdf_page(page.rect, src, 0)
            src.close()
        self._adopt(doc)
        self.path = None
        self.dirty = True
        self._was_encrypted = False
        self._encryption_lost = False
        self.history.clear()
        self.events.emit("opened", self)
        self.events.emit("pages", self.page_count)
        self.events.emit("dirty", True)

    def close(self) -> None:
        if self.doc is not None:
            try:
                self.doc.close()
            except Exception:
                pass
        self.doc = None
        self.path = None
        self.dirty = False
        self._was_encrypted = False
        self._encryption_lost = False
        self._invalidate_caches()
        self.history.clear()
        self.events.emit("closed", self)

    def _adopt(self, doc: pymupdf.Document) -> None:
        if self.doc is not None and self.doc is not doc:
            try:
                self.doc.close()
            except Exception:
                pass
        self.doc = doc
        self._view_rot = {}
        self._invalidate_caches()

    def _invalidate_caches(self) -> None:
        """Svuota le cache di rendering e di selezione del testo.

        Tutte le cache derivate dal contenuto del documento vanno svuotate
        insieme: dimenticarne una porta a evidenziazioni e ritagli obsoleti.
        """
        self._pixmap_cache.clear()
        self._word_cache.clear()

    def _note_encryption_loss(self) -> None:
        """Segnala che la cifratura del documento e' andata perduta in memoria.

        ``tobytes()``, usato per la cronologia, fa cadere il ``/Encrypt`` dal
        trailer del documento in memoria: da quel momento salvare produrrebbe
        un file **senza password e senza permessi**, senza avvisare nessuno.
        Il controllo guarda il trailer e non ``has_encryption``, che appunto
        continua a rispondere ``True`` per non far perdere di vista la
        protezione del file di origine.
        """
        if not self._was_encrypted or self._encryption_lost:
            return
        try:
            ancora = "/Encrypt" in self._require().pdf_trailer()
        except Exception:
            return
        if not ancora:
            self._encryption_lost = True

    def _check_can_save(self) -> None:
        if self._encryption_lost:
            raise DocumentError(
                "La protezione del documento non può essere conservata durante la "
                "modifica, perché il file in memoria ha perso la cifratura. "
                "Salvare ora produrrebbe un PDF senza password. "
                "Usa «Esporta…» indicando una password, oppure rimuovi la "
                "protezione e riapplicala con le impostazioni desiderate."
            )

    def _require(self) -> pymupdf.Document:
        if self.doc is None:
            raise DocumentError("Nessun documento aperto.")
        return self.doc

    # ------------------------------------------------------------- proprietà base

    @property
    def page_count(self) -> int:
        return self.doc.page_count if self.doc is not None else 0

    @property
    def is_open(self) -> bool:
        return self.doc is not None

    @property
    def filename(self) -> str:
        return self.path.name if self.path else "Senza titolo.pdf"

    @property
    def is_encrypted(self) -> bool:
        """True se il file richiede una password per essere aperto."""
        return bool(self.doc is not None and self.doc.needs_pass)

    @property
    def has_encryption(self) -> bool:
        """True se il file contiene un dizionario /Encrypt.

        Diversamente da ``is_encrypted``, che MuPDF azzera dopo l'autenticazione,
        questo descrive il file su disco ed e' cio' che interessa all'utente.
        Se la cifratura e' stata persa in memoria si continua a rispondere
        ``True``: il file di partenza era protetto e va trattato come tale.
        """
        if self._encrypt_fields() is not None:
            return True
        return bool(self._was_encrypted)

    def remove_encryption(self, password: str = "") -> None:
        """Toglie la protezione dal documento (richiede la password proprietario).

        MuPDF non consente scritture incrementali cambiando la cifratura: il
        documento viene quindi riscritto per intero in memoria e riaperto al
        posto di quello corrente.
        """
        if not self.has_encryption:
            raise DocumentError("Il documento non è protetto.")
        if self.is_encrypted and not self.authenticate(password):
            raise DocumentError("Password del proprietario non corretta.")
        grezzo = self._require().tobytes(garbage=3, deflate=True)
        sorgente = pymupdf.open("pdf", grezzo)
        try:
            out = pymupdf.open()
            try:
                out.insert_pdf(sorgente)
                # tobytes() restituisce il contenuto in memoria: non si usa save(),
                # che scriverebbe davvero un file chiamato ":memory:"
                dati = out.tobytes(
                    encryption=pymupdf.PDF_ENCRYPT_NONE, garbage=3, deflate=True
                )
            finally:
                out.close()
        finally:
            sorgente.close()
        self._adopt(pymupdf.open("pdf", dati))
        # La protezione e' stata tolta di proposito: senza azzerare qui il
        # documento continuava a dichiararsi protetto (``has_encryption``),
        # la prima modifica dopo la rimozione veniva scambiata per una perdita
        # di cifratura e da quel momento il salvataggio era sempre rifiutato.
        self._was_encrypted = False
        self._encryption_lost = False
        self.mark_dirty()
        self._invalidate_caches()
        self.events.emit("pages", self.page_count)
        self.events.emit("changed", self)

    def _encrypt_fields(self) -> dict[str, str] | None:
        """Chiavi del dizionario /Encrypt letti dal trailer.

        ``pdf_trailer`` restituisce il trailer come testo, quindi i valori vanno
        estratti con un'espressione regolare invece che per chiave.
        """
        if self.doc is None:
            return None
        try:
            testo = self.doc.pdf_trailer() or ""
        except Exception:
            return None
        if not isinstance(testo, str):
            return dict(testo) if testo else None
        m = re.search(r"/Encrypt\s*(<<.*?>>|\d+\s+\d+\s+R)", testo, re.S)
        if not m:
            return None
        corpo = m.group(1)
        if corpo.startswith("<<"):
            return {k: v for k, v in re.findall(r"/(\w+)\s*(\d+|-?\d*\s*[\d.]*)", corpo)}
        xref = int(re.match(r"(\d+)", corpo).group(1))
        try:
            return {
                k: v
                for k, v in re.findall(
                    r"/(\w+)\s*(\d+|/\w+|<<.*?>>)",
                    self.doc.xref_object(xref, compressed=False),
                    re.S,
                )
            }
        except Exception:
            return {}

    @property
    def has_form_fields(self) -> bool:
        try:
            return bool(self.doc is not None and self.doc.is_form_pdf)
        except Exception:
            return any(True for _ in self.fields())

    @property
    def has_signature_fields(self) -> bool:
        return any(f.type == "Signature" for f in self.fields())

    @property
    def is_signed(self) -> bool:
        return any(f.is_signed for f in self.fields())

    def page(self, index: int) -> pymupdf.Page:
        doc = self._require()
        if not 0 <= index < doc.page_count:
            raise DocumentError(tr("Indice pagina non valido: {indice}").format(indice=index))
        return doc[index]

    def mark_dirty(self, value: bool = True) -> None:
        if self.dirty != value:
            self.dirty = value
            self.events.emit("dirty", value)

    def _emit_pages(self) -> None:
        self._invalidate_caches()
        self.events.emit("pages", self.page_count)
        self.events.emit("changed", self)

    # ------------------------------------------------------------------ geometria

    def page_info(self, index: int) -> PageInfo:
        """Geometria della pagina nel sistema visualizzato."""
        page = self.page(index)
        rot = (page.rotation + self._view_rot.get(index, 0)) % 360
        box = page.cropbox if page.cropbox and not page.cropbox.is_empty else page.mediabox
        if rot in (90, 270):
            disp = geo.Rect(0, 0, box.height, box.width)
        else:
            disp = geo.Rect(0, 0, box.width, box.height)
        return PageInfo(
            index=index,
            rect=disp,
            mediabox=geo.Rect(page.mediabox),
            cropbox=geo.Rect(box),
            rotation=rot,
        )

    def page_points(self, index: int) -> tuple[float, float]:
        r = self.page_info(index).rect
        return r.width, r.height

    def view_rotation(self, index: int) -> int:
        return self._view_rot.get(index, 0) % 360

    def set_view_rotation(self, index: int, deg: int) -> None:
        """Ruota la vista della pagina senza modificare il contenuto del PDF."""
        self._view_rot[index] = deg % 360
        self._invalidate_caches()
        self.events.emit("changed", self)

    def _rot_rect(self, rect: geo.Rect, angle: int, width: float, height: float) -> geo.Rect:
        """Ruota un rettangolo di ``angle`` gradi (orario) in un canvas WxH.

        Le annotazioni e i campi vivono sempre nello spazio pagina *non ruotato*,
        mentre il rendering le mostra ruotate: questa e' la trasformazione che
        collega i due sistemi, verificata contro l'output rasterizzato.
        """
        r = geo.Rect(rect)
        angle %= 360
        if angle == 0:
            return r
        if angle == 90:
            return geo.Rect(height - r.y1, r.x0, height - r.y0, r.x1)
        if angle == 180:
            return geo.Rect(width - r.x1, height - r.y1, width - r.x0, height - r.y0)
        return geo.Rect(r.y0, width - r.x1, r.y1, width - r.x0)

    def _unrot_rect(self, rect: geo.Rect, angle: int, width: float, height: float) -> geo.Rect:
        """Inverso di :meth:`_rot_rect`.

        Ruotando di 90 o 270 gradi la tela si scambia, quindi l'inverso va
        applicato a un riquadro con le dimensioni invertite.
        """
        a = angle % 360
        if a == 0:
            return geo.Rect(rect)
        if a == 180:
            return self._rot_rect(rect, 180, width, height)
        return self._rot_rect(rect, (360 - a) % 360, height, width)

    def _map_rect(self, index: int, rect: geo.Rect, forward: bool) -> geo.Rect:
        """Converte fra spazio pagina (non ruotato) e spazio visualizzato.

        La rotazione del PDF e quella di visualizzazione vengono composte in
        quest'ordine, come nel rendering.
        """
        page = self.page(index)
        box = page.cropbox if page.cropbox and not page.cropbox.is_empty else page.mediabox
        w, h = float(box.width), float(box.height)
        pdf_rot = int(page.rotation or 0) % 360
        view_rot = self.view_rotation(index) % 360
        r = geo.Rect(rect)

        if forward:
            out = self._rot_rect(r, pdf_rot, w, h)
            if view_rot:
                cw, ch = (h, w) if pdf_rot in (90, 270) else (w, h)
                out = self._rot_rect(out, view_rot, cw, ch)
            return out
        if view_rot:
            cw, ch = (h, w) if pdf_rot in (90, 270) else (w, h)
            r = self._unrot_rect(r, view_rot, cw, ch)
        return self._unrot_rect(r, pdf_rot, w, h)

    def to_display_rect(self, index: int, rect: geo.Rect) -> geo.Rect:
        """Dallo spazio pagina (non ruotato) allo spazio visualizzato."""
        return self._map_rect(index, rect, forward=True)

    def to_page_rect(self, index: int, rect: geo.Rect) -> geo.Rect:
        """Dallo spazio visualizzato allo spazio pagina (non ruotato)."""
        return self._map_rect(index, rect, forward=False)

    # ---------------------------------------------------------------- rendering

    def render(
        self,
        index: int,
        zoom: float = 1.0,
        dpi: int | None = None,
        annots: bool = True,
        view_rotation: bool = True,
    ) -> pymupdf.Pixmap:
        """Rasterizza la pagina alla scala richiesta.

        La rotazione di visualizzazione e' incorporata nella matrice di rendering
        invece di ruotare il pixmap: il risultato e' identico a imposta
        ``set_rotation`` ma il documento non viene toccato.
        """
        page = self.page(index)
        scale = dpi / 72.0 if dpi else zoom
        rot = self.view_rotation(index) if view_rotation else 0
        key = (index, round(scale, 4), 1 if annots else 0, rot)
        cached = self._pixmap_cache.get(key)
        if cached is not None:
            return cached
        box = page.cropbox if page.cropbox and not page.cropbox.is_empty else page.mediabox
        pdf_rot = int(page.rotation or 0) % 360
        w, h = float(box.width), float(box.height)
        # Dimensioni della pagina dopo la rotazione del PDF, su cui applico quella
        # di visualizzazione.
        wv, hv = (h, w) if pdf_rot in (90, 270) else (w, h)
        m = _view_rotation_matrix(scale, rot, wv, hv)
        pix = page.get_pixmap(matrix=m, alpha=False, annots=annots)
        self._pixmap_cache[key] = pix
        if len(self._pixmap_cache) > 48:
            for k in list(self._pixmap_cache)[:16]:
                if k != key:
                    self._pixmap_cache.pop(k, None)
        return pix

    def render_thumbnail(self, index: int, width_px: int) -> pymupdf.Pixmap:
        info = self.page_info(index)
        if info.rect.width <= 0:
            raise DocumentError("Pagina non valida.")
        return self.render(index, zoom=width_px / info.rect.width)

    def render_region(self, page_index: int, rect: geo.Rect, dpi: int = 200, alpha: bool = True) -> pymupdf.Pixmap:
        """Rasterizza una porzione di pagina (per ritaglio o anteprima)."""
        m = pymupdf.Matrix(dpi / 72.0, dpi / 72.0)
        return self.page(page_index).get_pixmap(matrix=m, clip=geo.Rect(rect), alpha=alpha)

    def extract_page_image(
        self, page_index: int, dpi: int = 300, fmt: str = "png", quality: int = 95
    ) -> bytes:
        """La pagina come immagine.

        ``quality`` vale solo per i formati con perdita (JPEG): prima non
        arrivava al motore e la casella «Qualità JPEG» della finestra di
        esportazione non cambiava nulla.
        """
        px = self.render(page_index, dpi=dpi)
        if fmt.lower() in ("jpg", "jpeg"):
            return px.tobytes(output="jpg", jpg_quality=max(1, min(100, int(quality))))
        return px.tobytes(output=fmt)

    # --------------------------------------------------- snapshot e mutazioni

    def snapshot(self) -> bytes:
        """Copia completa del documento in memoria."""
        try:
            dati = self._require().tobytes(garbage=0, deflate=True)
        except Exception:
            dati = self._require().tobytes()
        # la serializzazione fa cadere /Encrypt: va segnalato subito, non quando
        # si arriva al salvataggio e il file e' ormai senza protezione
        self._note_encryption_loss()
        return dati

    def _restore(self, data: bytes) -> None:
        if not data:
            return
        try:
            doc = pymupdf.open("pdf", data)
        except Exception as exc:
            raise DocumentError(
                    tr("Impossibile ripristinare il documento: {errore}").format(errore=exc)
                ) from exc
        self._adopt(doc)
        self.dirty = True
        self._invalidate_caches()
        self.events.emit("pages", self.page_count)
        self.events.emit("changed", self)
        self.events.emit("dirty", True)

    def _mutate(
        self,
        text: str,
        fn: Callable[[], Any],
        emit_pages: bool = False,
    ) -> Any:
        """Applica una modifica registrandola per l'annullamento.

        Se l'operazione solleva un'eccezione il documento viene riportato allo
        stato precedente, così un'operazione fallita non lascia mezze modifiche.
        """
        before = self.snapshot() if self._undo_enabled else b""
        try:
            out = fn()
        except Exception:
            if before:
                self._restore(before)
            raise
        if before and self._undo_enabled:
            after = self.snapshot()
            self.history.run(SnapshotCommand(self, text, before, after))
            self.history.trim(UNDO_BUDGET)
        self.mark_dirty()
        # ogni modifica puo' cambiare il testo: le cache vanno svuotate,
        # altrimenti la selezione evidenzierebbe parole vecchie
        self._invalidate_caches()
        if emit_pages:
            self._emit_pages()
        else:
            self._invalidate_caches()
            self.events.emit("changed", self)
        return out

    def _rebuild(self, order: Sequence[int]) -> None:
        """Riordina le pagine del documento in posto (``Document.select``)."""
        self._require().select(list(order))
        self._invalidate_caches()

    # ----------------------------------------------------------------- salvataggio

    def save(self, path: str | os.PathLike[str] | None = None, incremental: bool = False) -> Path:
        """Salva il documento; in modo incrementale se richiesto e possibile.

        Non chiede se il documento è stato modificato: salvare è sempre
        consentito, anche quando non è cambiato nulla. Serve a chi ha aperto
        un file solo per correggerlo a mano fuori dal programma, o per
        riacquistare i permessi di scrittura dopo averlo protetto a mano.
        """
        doc = self._require()
        target = Path(path) if path else self.path
        if target is None:
            raise DocumentError("Nessun percorso di destinazione.")
        self._check_can_save()
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if incremental and self.path and self.path.exists() and self.path.resolve() == target.resolve():
                doc.save(str(target), incremental=True, encryption=pymupdf.PDF_ENCRYPT_KEEP)
            else:
                self._salva_completo(doc, target)
        except Exception as exc:
            raise DocumentError(
                tr("Salvataggio non riuscito: {errore}").format(errore=exc)
            ) from exc
        self.path = target
        self.dirty = False
        self.history.clear()
        self.events.emit("saved", target)
        self.events.emit("dirty", False)
        return target

    def _salva_completo(self, doc: pymupdf.Document, target: Path) -> None:
        """Scrive il documento su ``target`` riscrivendolo da capo.

        MuPDF rifiuta la riscrittura completa del file da cui il documento è
        stato aperto: pretende il salvataggio incrementale e solleva «save to
        original must be incremental». Il salvataggio normale finiva quindi
        sempre in errore, con o senza modifiche, e la finestra mostrava la
        traduzione di quell'errore invece di scrivere il file.

        Si scrive su un provvisorio e lo si mette al posto del file, come
        già si fa per l'esportazione in PDF/A: il contenuto è lo stesso, il
        file precedente resta intatto se qualcosa va storto e sul disco non
        resta nessun ricordo del passaggio. Il confronto è fra i percorsi e
        non chiede che il file esista ancora: MuPDF guarda da quale nome è
        stato aperto il documento, e se il file è stato cancellato o mosso
        proprio quel confronto continua a valere.

        Sul file che non si può sostituire, cioè su Windows, dove è aperto
        perché lo sta leggendo MuPDF, il contenuto viene scritto dentro: il
        file resta valido e le letture successive tornano, perché sono quelle
        del documento appena riscritto.
        """
        sullo_stesso = (
            self.path is not None and self.path.resolve() == target.resolve()
        )
        if not sullo_stesso:
            doc.save(str(target), garbage=3, deflate=True, clean=True)
            return
        provvisorio = target.with_name(f"{target.name}.{os.getpid()}.tmp")
        try:
            doc.save(str(provvisorio), garbage=3, deflate=True, clean=True)
            # il provvisorio nasce con i permessi della cartella: se il file
            # c'era già, gli si ridanno quelli che aveva
            if target.exists():
                os.chmod(provvisorio, target.stat().st_mode & 0o7777)
            _sostituisci(provvisorio, target)
        finally:
            if provvisorio.exists():
                provvisorio.unlink()

    # ------------------------------------------------------- riduzione del file

    def image_inventory(self) -> list[dict[str, Any]]:
        """Immagini del documento con dimensioni e peso in memoria.

        Serve a capire quanto si può risparmiare prima di scegliere una
        qualita' di compressione.
        """
        out: list[dict[str, Any]] = []
        visti: set[int] = set()
        for i in range(self.page_count):
            for info in self._require()[i].get_images(full=True):
                xref = info[0]
                if xref in visti:
                    continue
                visti.add(xref)
                try:
                    px = pymupdf.Pixmap(self._require(), xref)
                    w, h, n = px.width, px.height, px.n
                except Exception:
                    continue
                out.append(
                    {
                        "xref": xref,
                        "page": i,
                        "width": w,
                        "height": h,
                        "megapixels": w * h / 1e6,
                        "colors": n,
                    }
                )
        return out

    def reduce_size(
        self,
        path: str | os.PathLike[str],
        quality: int = 85,
        max_dpi: int | None = 150,
        recompress_all: bool = False,
    ) -> dict[str, Any]:
        """Scrive una copia del documento con le immagini ridimensionate.

        Le immagini piu' grandi di ``max_dpi`` (in punti rispetto alla misura in
        cui sono mostrate) vengono ridimensionate e ricodificate in JPEG; se
        ``recompress_all`` e' attivo vengono ricodificate anche quelle gia'
        piccole. Il testo e i vettori non vengono toccati: la riduzione riguarda
        solo le immagini, che sono la causa quasi sempre delle dimensioni
        eccessive.

        Restituisce un riepilogo con le dimensioni prima e dopo.
        """
        if not (1 <= int(quality) <= 100):
            raise DocumentError("La qualità JPEG deve stare fra 1 e 100.")
        # la riduzione lavora su una copia: il documento aperto non deve
        # cambiare, altrimenti la ricodifica sarebbe irreversibile e non
        # annullabile, e il confronto con la dimensione precedente sarebbe falso
        origine = len(self.save_bytes())
        lavoro = pymupdf.open("pdf", self.save_bytes())
        rifatta = 0
        for i in range(lavoro.page_count):
            for info in lavoro[i].get_images(full=True):
                xref, smask = info[0], info[1]
                if smask:
                    # un'immagine con maschera di trasparenza non si ricodifica
                    # in JPEG: si rischierebbe di perdere l'alpha
                    continue
                try:
                    px = pymupdf.Pixmap(lavoro, xref)
                except Exception:
                    continue
                if px.n not in (1, 3):
                    continue  # CMYK o altri spazi non gestiti
                mostra = lavoro[i].get_image_rects(xref)
                if max_dpi and mostra:
                    larghezza_pt = max(r.width for r in mostra)
                else:
                    larghezza_pt = px.width
                if larghezza_pt <= 0:
                    continue
                richiesti = px.width * 72.0 / larghezza_pt
                if not recompress_all and px.n == 3 and richiesti <= float(max_dpi or 0):
                    continue
                fattore = 1.0
                if max_dpi and richiesti > float(max_dpi):
                    fattore = float(max_dpi) / richiesti
                nuovo = _ricodifica_immagine(px, fattore, int(quality))
                if nuovo is None:
                    continue
                dati, w, h = nuovo
                # conviene solo se il nuovo stream e' davvero piu' piccolo di
                # quello attuale: su un'immagine gia' compressa la ricodifica
                # JPEG spesso peggiora il file
                try:
                    attuale = len(lavoro.xref_stream_raw(xref))
                except Exception:
                    attuale = len(px.samples)
                if len(dati) >= attuale:
                    continue
                try:
                    lavoro.update_stream(xref, dati, compress=False)
                except Exception:
                    continue
                for chiave, valore in (
                    ("Filter", "/DCTDecode"),
                    ("ColorSpace", "/DeviceRGB" if px.n == 3 else "/DeviceGray"),
                    ("Width", str(w)),
                    ("Height", str(h)),
                    ("BitsPerComponent", "8"),
                    ("DecodeParms", "null"),
                ):
                    try:
                        lavoro.xref_set_key(xref, chiave, valore)
                    except Exception:
                        pass
                rifatta += 1
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            lavoro.save(str(out), garbage=4, deflate=True, deflate_images=True, clean=True)
        finally:
            lavoro.close()
        finale = out.stat().st_size
        return {
            "path": out,
            "images": rifatta,
            "before": origine,
            "after": finale,
            "saved": max(0, origine - finale),
            "ratio": (finale / origine) if origine else 1.0,
        }

    # -------------------------------------------------------- numerazione pagine

    def add_page_numbers(
        self,
        indices: Sequence[int] | None = None,
        *,
        first: int = 1,
        fmt: str = "{n}",
        position: str = "bottom_center",
        margin: float = 28.0,
        fontsize: float = 9.0,
        skip_first: bool = False,
        total: bool = False,
        color: tuple[float, float, float] = (0.2, 0.2, 0.2),
    ) -> int:
        """Scrive il numero di pagina nel pie' delle pagine indicate.

        La numerazione parte da ``first`` ed e' indipendente dalla posizione delle
        pagine nel documento: con ``skip_first`` la copertina resta senza numero,
        con ``total`` si scrive «3 / 12». Il testo viene inserito come contenuto
        marcato ``/ScrNum``, che permette di rimuoverlo in seguito senza toccare
        il resto della pagina.
        """
        idxs = list(range(self.page_count)) if indices is None else sorted(set(indices))
        idxs = [i for i in idxs if 0 <= i < self.page_count]
        if skip_first:
            idxs = [i for i in idxs if i != 0]
        if not idxs:
            return 0
        if not (5.0 <= float(fontsize) <= 72.0):
            raise DocumentError("La dimensione del numero deve stare fra 5 e 72 pt.")
        if margin < 0:
            raise DocumentError("Il margine non può essere negativo.")
        if position not in ("bottom_left", "bottom_center", "bottom_right"):
            raise DocumentError(tr("Posizione non valida: {posizione}").format(posizione=position))
        # con «n / N» il totale e' l'ultimo numero stampato, non quante pagine
        # sono state numerate: altrimenti «5 / 2» sarebbe incomprensibile
        ultimo = first + len(idxs) - 1

        def _op() -> int:
            fatte = 0
            for pos, i in enumerate(idxs):
                n = first + pos
                testo = fmt.format(n=n, page=n, total=ultimo if total else n)
                # il numero viene scritto come contenuto della pagina, quindi
                # nello spazio pagina: le misure vanno prese dal CropBox e non
                # dal riquadro mostrato, che su una pagina ruotata ha gli assi
                # scambiati e mandava il numero fuori dal foglio
                r = self.page(i).cropbox
                larghezza = len(testo) * float(fontsize) * 0.5
                if position == "bottom_left":
                    x = margin
                elif position == "bottom_right":
                    x = r.width - margin - larghezza
                else:
                    x = (r.width - larghezza) / 2
                # y nello spazio pagina, che ha l'origine in basso
                y = margin
                blocco = _page_number_block(
                    testo, x, y, float(fontsize), color
                )
                if _append_page_content(self._require(), i, blocco):
                    fatte += 1
            return fatte

        return int(self._mutate("Numerazione pagine", _op, emit_pages=True))

    def has_page_numbers(self, indices: Sequence[int] | None = None) -> list[int]:
        """Pagine che portano già una numerazione aggiunta dal programma."""
        idxs = list(range(self.page_count)) if indices is None else sorted(set(indices))
        return [i for i in idxs if 0 <= i < self.page_count and _has_page_number(self._require(), i)]

    def remove_page_numbers(self, indices: Sequence[int] | None = None) -> int:
        """Rimuove la numerazione aggiunta con :meth:`add_page_numbers`.

        Si cancellano solo i blocchi marcati ``/ScrNum``: il resto del
        contenuto della pagina resta intatto.
        """
        idxs = list(range(self.page_count)) if indices is None else sorted(set(indices))
        idxs = [i for i in idxs if 0 <= i < self.page_count]
        if not idxs:
            return 0

        def _op() -> int:
            tolte = 0
            for i in idxs:
                tolte += _strip_page_numbers(self._require(), i)
            if not tolte:
                raise DocumentError("Nessuna numerazione da rimuovere.")
            return tolte

        return int(self._mutate("Rimuovi numerazione", _op, emit_pages=True))

    def save_copy(self, path: str | os.PathLike[str]) -> Path:
        """Salva una copia lasciando intatti documento, percorso e cronologia.

        Scrivere sul file corrente azzererebbe l'annullamento e lascerebbe
        l'applicazione su un file diverso da quello che si sta modificando.
        """
        target = Path(path)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(self.save_bytes())
        except Exception as exc:
            raise DocumentError(
                    tr("Salvataggio della copia non riuscito: {errore}").format(errore=exc)
                ) from exc
        self.events.emit("saved", target)
        return target

    def save_bytes(self) -> bytes:
        return self._require().tobytes(garbage=3, deflate=True, clean=True)

    def export(
        self,
        path: str | os.PathLike[str],
        pages: Sequence[int] | None = None,
        permissions: int = -1,
        owner_pass: str | None = None,
        user_pass: str | None = None,
        algorithm: int = pymupdf.PDF_ENCRYPT_AES_256,
    ) -> Path:
        """Esporta tutte le pagine o un sottoinsieme, eventualmente cifrato."""
        out = pymupdf.open()
        if pages is None:
            idx = list(range(self.page_count))
        else:
            idx = sorted(set(pages))
            fuori = [i for i in idx if not (0 <= i < self.page_count)]
            if fuori:
                # MuPDF accetterebbe un indice inesistente e aggiungerebbe una
                # pagina vuota: l'esportazione produrrebbe piu' pagine di quante
                # ne abbia il documento, senza alcun avviso
                out.close()
                numeri = ", ".join(str(i) for i in fuori)
                raise DocumentError(
                    tr("Indici di pagina fuori intervallo: {indici} "
                       "(il documento ha {totale} pagine).")
                    .format(indici=numeri, totale=self.page_count)
                )
        if not idx:
            out.close()
            raise DocumentError("Nessuna pagina da esportare.")
        src = self._require()
        if idx == list(range(idx[0], idx[-1] + 1)):
            out.insert_pdf(src, from_page=idx[0], to_page=idx[-1])
        else:
            for i in idx:
                out.insert_pdf(src, from_page=i, to_page=i)
        # ``insert_pdf`` porta il contenuto ma non il dizionario delle
        # informazioni: senza questo ogni file esportato perdeva titolo,
        # autore, oggetto e parole chiave del documento di partenza
        try:
            if src.metadata:
                out.set_metadata({k: v for k, v in src.metadata.items() if v is not None})
            xmp = self.xmp_metadata()
            if xmp:
                out.set_xml_metadata(xmp)
        except Exception:
            # i metadati non sono il contenuto: se non si possono copiare
            # l'esportazione va comunque avanti
            pass
        kwargs: dict[str, Any] = {"garbage": 3, "deflate": True}
        if permissions != -1 or owner_pass is not None or user_pass is not None:
            kwargs.update(
                encryption=algorithm,
                owner_pw=owner_pass or "",
                user_pw=user_pass or "",
                permissions=int(permissions),
            )
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            out.save(str(p), **kwargs)
        finally:
            out.close()
        return p

    # ----------------------------------------------------------------- metadati

    def metadata(self) -> dict[str, str]:
        if self.doc is None:
            return {}
        return dict(self.doc.metadata or {})

    def set_metadata(self, values: dict[str, str]) -> None:
        def _op() -> None:
            self._require().set_metadata({k: v for k, v in values.items() if v is not None})

        self._mutate("Proprietà documento", _op)

    def xmp_metadata(self) -> str:
        try:
            return self._require().get_xml_metadata() or ""
        except Exception:
            return ""

    def language(self) -> str:
        """Lingua dichiarata nel documento (``/Lang``), vuota se assente."""
        try:
            return str(getattr(self._require(), "language", None) or "")
        except Exception:
            return ""

    def set_document_language(self, lingua: str) -> None:
        """Dichiara la lingua del documento.

        È il dato che permette a uno screen reader di scegliere la corretta
        pronuncia: senza, il testo italiano viene letto con fonetiche inglesi.
        """
        codice = str(lingua or "").strip().replace("_", "-")
        if not codice:
            raise DocumentError("Indica la lingua del documento, per esempio «it-IT».")
        if not re.fullmatch(r"[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*", codice):
            raise DocumentError(
                tr("«{lingua}» non sembra un codice lingua valido (per esempio it-IT, en-GB).")
                .format(lingua=lingua)
            )
        self._mutate("Lingua documento", lambda: self._require().set_language(codice))

    def sort_fields_in_reading_order(self) -> int:
        """Riordina i campi modulo secondo l'ordine in cui si leggono.

        Con il tabulatore l'utente attraversa i campi seguendo l'ordine delle
        annotazioni nella pagina: se non coincide con quello di lettura si
        salta avanti e indietro.
        """
        campi = self.fields()
        if len(campi) < 2:
            return 0
        ordine = sorted(campi, key=lambda f: (f.page, round(f.rect.y0, 1), f.rect.x0))
        if ordine == campi:
            return 0
        self.set_tab_order([(f.page, f.xref) for f in ordine])
        return len(campi)

    def set_xmp_metadata(self, xml: str) -> None:
        self._mutate("Metadati XMP", lambda: self._require().set_xml_metadata(xml))

    # --------------------------------------------------------------------- pagine

    def insert_page(
        self,
        at: int,
        width: float | None = None,
        height: float | None = None,
        text: str = "",
        size_name: str = "A4",
    ) -> int:
        """Inserisce una pagina vuota alla posizione ``at``.

        ``text``, se indicato, viene scritto in alto a sinistra: il parametro
        esisteva ma non veniva usato, e una pagina inserita con un titolo
        restava bianca.
        """
        if width is None or height is None:
            width, height = units.paper_size(size_name)

        def _op() -> int:
            pagina = self._require().new_page(pno=at, width=width, height=height)
            if text.strip():
                pagina.insert_textbox(
                    geo.Rect(40, 40, max(60.0, width - 40), 140),
                    text.strip(),
                    fontsize=18,
                    color=(0, 0, 0),
                    fontname="helv",
                    align=0,
                )
            return at

        return self._mutate("Inserisci pagina", _op, emit_pages=True)

    def append_page(self, width: float, height: float) -> int:
        return self.insert_page(self.page_count, width, height)

    def insert_pdf_pages(self, src_path: str, at: int, pages: Sequence[int] | None = None) -> int:
        """Inserisce pagine di un altro PDF alla posizione ``at``."""
        try:
            src = pymupdf.open(src_path)
        except Exception as exc:
            # un percorso inesistente o un file illeggibile deve dare un
            # errore del modulo, non un'eccezione grezza di MuPDF
            raise DocumentError(
                tr("Impossibile aprire «{file}»: {errore}").format(file=Path(src_path).name, errore=exc)
            ) from exc
        try:
            idx = sorted(set(pages)) if pages else list(range(src.page_count))
            if not idx:
                raise DocumentError("Nessuna pagina da inserire.")
            fuori = [i for i in idx if not (0 <= i < src.page_count)]
            if fuori:
                numeri = ", ".join(str(i + 1) for i in fuori)
                raise DocumentError(
                    tr("Le pagine {pagine} non esistono nel file di origine "
                       "(ha {totale} pagine).")
                    .format(pagine=numeri, totale=src.page_count)
                )

            def _op() -> int:
                doc = self._require()
                if idx == list(range(idx[0], idx[-1] + 1)):
                    doc.insert_pdf(src, from_page=idx[0], to_page=idx[-1], start_at=at)
                else:
                    # Pagine non contigue: si inseriscono una alla volta.
                    for offset, i in enumerate(idx):
                        doc.insert_pdf(src, from_page=i, to_page=i, start_at=at + offset)
                return len(idx)

            try:
                return int(self._mutate("Inserisci pagine", _op, emit_pages=True))
            except DocumentError:
                raise
            except Exception as exc:
                # il file risultato non essere un PDF valido: l'errore di MuPDF
                # arriva solo al momento dell'inserimento
                raise DocumentError(
                    tr("«{file}» non è un PDF valido: {errore}")
                    .format(file=Path(src_path).name, errore=exc)
                ) from exc
        finally:
            src.close()

    def delete_pages(self, indices: Sequence[int]) -> None:
        idx = sorted({int(i) for i in indices})
        if not idx:
            return
        fuori = [i for i in idx if not (0 <= i < self.page_count)]
        if fuori:
            # senza questo controllo MuPDF sollevava un ``ValueError`` grezzo
            # («bad page number(s)») che all'utente arrivava come errore del
            # programma, non come «questa pagina non esiste»
            raise DocumentError(
                "Una delle pagine da eliminare non esiste nel documento."
            )
        if len(idx) >= self.page_count:
            raise DocumentError("Non è possibile eliminare tutte le pagine.")

        def _op() -> None:
            for i in reversed(idx):
                self._require().delete_page(i)

        self._mutate(
            "Elimina pagina" if len(idx) == 1 else f"Elimina {len(idx)} pagine", _op, emit_pages=True
        )

    def duplicate_pages(self, indices: Sequence[int]) -> list[int]:
        """Duplica le pagine, inserendo ogni copia subito dopo l'originale.

        Le copie si inseriscono dall'ultima pagina alla prima: ogni inserimento
        sposta in avanti gli indici successivi, quindi procedendo dall'alto verso
        il basso ogni indice resta quello giusto. Procedendo dal bassi verso
        l'alto, con piu' pagine selezionate la stessa pagina veniva duplicata
        due volte e una delle scelte non veniva duplicata affatto.
        """
        idx = sorted({int(i) for i in indices if 0 <= int(i) < self.page_count})
        if not idx:
            return []
        # Le copie si inseriscono dall'ultima pagina alla prima: ogni inserimento
        # sposta in avanti gli indici successivi, quindi procedendo dall'alto verso
        # il basso ogni indice resta quello giusto. Procedendo dal bassi verso
        # l'alto, con piu' pagine selezionate la stessa pagina veniva duplicata
        # due volte e una delle scelte non veniva duplicata affatto.
        #
        # La posizione finale di ogni copia e' quella al momento dell'inserimento
        # piu' uno per ogni inserimento successivo (fatto a un indice minore, che
        # la spinge in avanti).
        # La posizione finale di ogni copia è quella del momento dell'inserimento
        # più uno per ogni copia successiva inserita a un indice minore, che la
        # spinge in avanti.
        for i in reversed(idx):
            def _op(i: int = i) -> None:
                doc = self._require()
                # ``insert_pdf`` non accetta se stesso come sorgente: si copia prima.
                one = pymupdf.open()
                try:
                    one.insert_pdf(doc, from_page=i, to_page=i)
                    doc.insert_pdf(one, from_page=0, to_page=0, start_at=i + 1)
                finally:
                    one.close()

            self._mutate("Duplica pagina", _op, emit_pages=True)
        return [i + 1 + k for k, i in enumerate(idx)]

    def rotate_pages(self, indices: Sequence[int], degrees: int) -> None:
        idx = sorted(set(indices))
        if not idx:
            return

        def _op() -> None:
            for i in idx:
                p = self._require()[i]
                p.set_rotation((p.rotation + degrees) % 360)

        label = {90: "Ruota a destra", 270: "Ruota a sinistra", 180: "Ruota di 180°"}.get(
            degrees % 360, "Ruota pagina"
        )
        self._mutate(label, _op, emit_pages=True)

    # ------------------------------------------------------------------ ritaglio

    def set_page_size(self, pages: Sequence[int], width: float, height: float) -> None:
        """Cambia dimensione e orientamento delle pagine indicate.

        Va da ``_mutate`` come ogni altra modifica: scritto direttamente sulla
        pagina dalla finestra saltava l'annullamento, e «Cambia dimensione
        pagina» non si poteva disfare con Ctrl+Z come tutto il resto.
        """
        indici = [int(p) for p in pages if 0 <= int(p) < self.page_count]
        if not indici:
            raise DocumentError("Nessuna pagina da ridimensionare.")
        w, h = float(width), float(height)
        if w <= 0 or h <= 0:
            raise DocumentError("La dimensione della pagina deve essere positiva.")

        def _op() -> None:
            for p in indici:
                page = self.page(p)
                box = pymupdf.Rect(0, 0, w, h)
                page.set_mediabox(box)
                page.set_cropbox(box)

        self._mutate("Dimensione pagina", _op, emit_pages=True)

    def crop_page(self, page_index: int, rect: geo.Rect) -> None:
        """Ritaglia la pagina, riducendo l'area visibile.

        Il ritaglio agisce sul ``/CropBox`` e lascia intatti i contenuti: e' il
        comportamento di Acrobat e serve soprattutto sulle scansioni, dove i
        bordi neri dello scanner vanno tolti senza alterare l'immagine.
        ``rect`` e' in coordinate mostrate a schermo.
        """
        self.crop_pages([page_index], rect)

    def crop_pages(self, indices: Sequence[int], rect: geo.Rect) -> int:
        """Ritaglia più pagine con lo stesso rettangolo di margine.

        Le pagine ruotate o di formato diverso vengono ritagliate per difetto
        (stessi margini), che e' cio' che serve a una pila di scansioni.
        Restituisce quante pagine sono state modificate.
        """
        idx = [i for i in sorted(set(indices)) if 0 <= i < self.page_count]
        if not idx:
            return 0
        if rect.width < 10 or rect.height < 10:
            raise DocumentError("L'area da ritagliare è troppo piccola.")

        def _op() -> int:
            fatte = 0
            righe: list[str] = []
            riferimento = self.page_info(idx[0]).rect
            for i in idx:
                info = self.page_info(i)
                # il rettangolo arriva dalla pagina di riferimento: si riporta
                # come margine per non tagliare fuori quando i formati cambiano
                margine = geo.Rect(
                    info.rect.x0 + (rect.x0 - riferimento.x0),
                    info.rect.y0 + (rect.y0 - riferimento.y0),
                    info.rect.x0 + (rect.x1 - riferimento.x0),
                    info.rect.y0 + (rect.y1 - riferimento.y0),
                )
                margine = geo.clamp_rect(margine, info.rect)
                if margine.width < 10 or margine.height < 10:
                    continue
                nuova = geo.Rect(self.to_page_rect(i, margine))
                try:
                    self._require()[i].set_cropbox(pymupdf.Rect(nuova))
                except Exception as exc:
                    # MuPDF rifiuta un CropBox fuori dal MediaBox e solleva un
                    # ValueError grezzo: senza questo la finestra mostrava
                    # «CropBox not in MediaBox» e la pagina restava com'era senza
                    # spiegare nulla
                    righe.append(f"pagina {i + 1}: {exc}")
                    continue
                fatte += 1
            if not fatte:
                dettaglio = (" (" + "; ".join(righe[:3]) + ")") if righe else ""
                raise DocumentError(
                    tr("Nessuna pagina è stata ritagliata{dettaglio}.").format(dettaglio=dettaglio)
                )
            return fatte

        return int(self._mutate("Ritaglia pagina", _op, emit_pages=True))

    def reset_crop(self, indices: Sequence[int]) -> int:
        """Ripristina l'area visibile di tutto il foglio."""
        idx = [i for i in sorted(set(indices)) if 0 <= i < self.page_count]
        if not idx:
            return 0

        def _op() -> int:
            for i in idx:
                p = self._require()[i]
                p.set_cropbox(pymupdf.Rect(p.mediabox))
            return len(idx)

        return int(self._mutate("Ripristina ritaglio", _op, emit_pages=True))

    def auto_crop_rect(self, page_index: int, padding: float = 4.0) -> geo.Rect | None:
        """Rettangolo del contenuto reale di una pagina, in coordinate schermo.

        Serve a ritagliare automaticamente le scansioni: si rasterizza la pagina
        e si cerca il bordo esterno dei pixel non bianchi. Restituisce ``None``
        se la pagina sembra vuota o gia' ritagliata.
        """
        if not (0 <= page_index < self.page_count):
            return None
        info = self.page_info(page_index)
        if info.cropbox.width < info.mediabox.width - 1 or info.cropbox.height < info.mediabox.height - 1:
            return None  # gia' ritagliata: non si tocca
        pix = self.render(page_index, dpi=36, annots=False, view_rotation=False)
        campioni = pix.samples
        n = pix.n
        larghezza, altezza = pix.width, pix.height
        if larghezza < 4 or altezza < 4:
            return None
        minx, miny, maxx, maxy = larghezza, altezza, -1, -1
        # campionamento a passo 2: il bordo non cambia e il costo si dimezza
        for y in range(0, altezza, 2):
            base = y * pix.stride
            for x in range(0, larghezza, 2):
                off = base + x * n
                if campioni[off] < 245 or campioni[off + 1] < 245 or campioni[off + 2] < 245:
                    if x < minx:
                        minx = x
                    if x > maxx:
                        maxx = x
                    if y < miny:
                        miny = y
                    if y > maxy:
                        maxy = y
        if maxx < minx or maxy < miny:
            return None
        fattore_x = info.rect.width / larghezza
        fattore_y = info.rect.height / altezza
        zona = geo.Rect(
            info.rect.x0 + minx * fattore_x,
            info.rect.y0 + miny * fattore_y,
            info.rect.x0 + (maxx + 1) * fattore_x,
            info.rect.y0 + (maxy + 1) * fattore_y,
        )
        zona = geo.Rect(zona.x0 - padding, zona.y0 - padding, zona.x1 + padding, zona.y1 + padding)
        zona = geo.clamp_rect(zona, info.rect)
        if zona.width < 10 or zona.height < 10:
            return None
        return zona

    def move_pages(self, order: Sequence[int]) -> None:
        """Riordina le pagine secondo ``order``."""
        # ``order`` può arrivare come generatore: ``sorted`` lo consumerebbe e il
        # controllo successivo riceverebbe una lista vuota
        ordine = list(order)
        if sorted(ordine) != list(range(self.page_count)):
            raise DocumentError("Ordinamento pagine non valido.")
        if ordine == list(range(self.page_count)):
            return
        self._mutate("Riordina pagine", lambda: self._rebuild(ordine), emit_pages=True)

    def move_page(self, src: int, dst: int) -> None:
        """Sposta una singola pagina in una nuova posizione."""
        if src == dst:
            return
        n = self.page_count
        if not (0 <= src < n):
            raise DocumentError("La pagina da spostare non esiste nel documento.")
        order = list(range(n))
        order.remove(src)
        order.insert(dst, src)
        self.move_pages(order)

    def extract_pages(self, indices: Sequence[int]) -> pymupdf.Document:
        """Restituisce un nuovo documento con le pagine richieste."""
        out = pymupdf.open()
        idx = sorted({int(i) for i in indices})
        if not idx:
            raise DocumentError("Nessuna pagina selezionata.")
        fuori = [i for i in idx if not (0 <= i < self.page_count)]
        if fuori:
            # MuPDF accetta un indice inesistente e aggiunge una pagina vuota:
            # chiedere la pagina 99 di un file di 5 pagine produceva un
            # documento con una pagina bianca in più, senza avviso
            out.close()
            raise DocumentError("Una delle pagine richieste non esiste nel documento.")
        src = self._require()
        if idx == list(range(idx[0], idx[-1] + 1)):
            out.insert_pdf(src, from_page=idx[0], to_page=idx[-1])
        else:
            for i in idx:
                out.insert_pdf(src, from_page=i, to_page=i)
        return out

    def split_document(self, indices: Sequence[int]) -> pymupdf.Document:
        return self.extract_pages(indices)

    # ---------------------------------------------------------------- annotazioni

    def annots(self, index: int, include_widgets: bool = True) -> list[dict[str, Any]]:
        """Elenco annotazioni (ed eventuali campi) della pagina."""
        page = self.page(index)
        out: list[dict[str, Any]] = []
        for annot in page.annots() or ():
            try:
                out.append(
                    {
                        "xref": annot.xref,
                        "type": (annot.type or ("", ""))[1],
                        "rect": geo.Rect(annot.rect),
                        "info": dict(annot.info or {}),
                        "vertices": _annot_vertices(annot),
                        "colors": annot.colors,
                        "opacity": annot.opacity,
                        "flags": int(annot.flags or 0),
                        "is_widget": False,
                    }
                )
            except Exception:
                continue
        if include_widgets:
            for w in page.widgets() or ():
                out.append(self._field_info(w, index))
        return out

    def _field_info(self, w: Any, page_index: int) -> dict[str, Any]:
        try:
            rect = geo.Rect(w.rect)
        except Exception:
            rect = geo.Rect()
        try:
            options = list(w.choice_values or [])
        except Exception:
            options = []
        try:
            fill = tuple(w.fill_color) if w.fill_color else None
        except Exception:
            fill = None
        return {
            "xref": w.xref,
            "type": w.field_type_string or "Text",
            "rect": rect,
            "is_widget": True,
            "name": w.field_name or f"campo_{w.xref}",
            "value": w.field_value,
            "flags": int(w.field_flags or 0),
            "options": options,
            "is_signed": bool(getattr(w, "is_signed", False)),
            "tooltip": w.field_label or "",
            "is_group": self._e_genitore_di_pulsanti(w),
            "maxlen": int(w.text_maxlen or 0),
            "font": w.text_font or "Helv",
            "fontsize": float(w.text_fontsize or 0),
            "text_color": tuple(w.text_color or (0, 0, 0)),
            "fill_color": fill,
            "border_style": border_style_code(w.border_style),
            "border_width": float(w.border_width or 1),
            "border_color": tuple(w.border_color or (0, 0, 0)),
            "page": page_index,
        }

    def _e_genitore_di_pulsanti(self, w: Any) -> bool:
        """True se il widget è il campo padre di un gruppo di pulsanti.

        Il padre ha un array ``/Kids`` e copre l'intera area del gruppo: se
        viene trattato come un pulsante come gli altri, un clic su una
        qualunque delle opzioni cade sul padre e spegne tutte le opzioni
        invece di scegliere quella. ``Widget.parent`` non è affidabile qui — per
        i widget restituiti da ``page.widgets()`` è vuoto — quindi si legge
        direttamente dal dizionario.
        """
        try:
            tipo, valore = self._require().xref_get_key(w.xref, "Kids")
        except Exception:
            return False
        return tipo == "array" and bool(valore)

    def xref_key(self, xref: int, key: str) -> tuple[str, str]:
        """Chiave grezza di un oggetto PDF, per ispezione e diagnostica."""
        try:
            return self._require().xref_get_key(xref, key)
        except Exception:
            return ("", "")

    def links(self, index: int) -> list[dict[str, Any]]:
        """Collegamenti presenti nella pagina, esterni e interni.

        Esterno significa un indirizzo (``uri``), interno un salto a un'altra
        pagina del documento (``page``). Prima si tenevano solo i primi: un
        collegamento a un'altra pagina del documento spariva dall'elenco e non
        aveva nemmeno un riquadro da cliccare.
        """
        out = []
        try:
            for l in self.page(index).get_links() or ():
                r = l.get("from")
                if r is None:
                    continue
                box = geo.Rect(r)
                if box.is_empty:
                    continue
                if l.get("uri"):
                    out.append({"uri": l["uri"], "rect": box, "page": None})
                elif l.get("kind") == pymupdf.LINK_GOTO and l.get("page", -1) >= 0:
                    out.append({"uri": "", "rect": box, "page": int(l["page"])})
        except Exception:
            pass
        return out

    def widget_objects(self, index: int) -> list[Any]:
        """Widget legati alla pagina: validi per ``update()``.

        La pagina va tenuta viva da chi riceve i widget: ``Widget.update()``
        risolve la pagina di appartenenza tramite un riferimento debole e
        solleva un errore se questa e' gia' stata liberata.
        """
        page = self.page(index)
        return list(page.widgets() or [])

    def fields(self, page_index: int | None = None) -> list[FieldInfo]:
        """Tutti i campi del documento (o di una sola pagina)."""
        idxs = range(self.page_count) if page_index is None else [page_index]
        out: list[FieldInfo] = []
        for i in idxs:
            for w in self.page(i).widgets() or ():
                d = self._field_info(w, i)
                out.append(
                    FieldInfo(
                        xref=d["xref"],
                        page=i,
                        name=d["name"],
                        type=d["type"],
                        value=d["value"],
                        rect=d["rect"],
                        flags=d["flags"],
                        maxlen=d["maxlen"],
                        font=d["font"],
                        fontsize=d["fontsize"],
                        text_color=d["text_color"],
                        fill_color=d["fill_color"],
                        border_style=d["border_style"],
                        border_width=d["border_width"],
                        border_color=d["border_color"],
                        options=d["options"],
                        is_signed=d["is_signed"],
                        tooltip=d["tooltip"],
                        choice_editable=bool(d["flags"] & (1 << 18)),
                        is_group=bool(d["is_group"]),
                    )
                )
        return out

    def field_kinds_count(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for f in self.fields():
            counts[f.kind] = counts.get(f.kind, 0) + 1
        return counts

    def delete_annot(self, page_index: int, xref: int) -> None:
        page = self.page(page_index)
        widget = next((w for w in page.widgets() or () if w.xref == xref), None)
        kind = "widget" if widget is not None else "annot"

        def _op() -> None:
            pg = self.page(page_index)
            if kind == "widget":
                w = next((x for x in pg.widgets() or () if x.xref == xref), None)
                if w is None:
                    raise DocumentError("Campo non trovato durante l'eliminazione.")
                pg.delete_widget(w)
            else:
                # ``delete_annot`` accetta l'oggetto annotazione, non l'xref
                a = next((x for x in pg.annots() or () if x.xref == xref), None)
                if a is None:
                    raise DocumentError("Annotazione non trovata durante l'eliminazione.")
                pg.delete_annot(a)

        self._mutate("Elimina campo" if kind == "widget" else "Elimina annotazione", _op)

    def annot_rect(self, page_index: int, xref: int) -> geo.Rect | None:
        page = self.page(page_index)
        for a in page.annots() or ():
            if a.xref == xref:
                return geo.Rect(a.rect)
        for w in page.widgets() or ():
            if w.xref == xref:
                return geo.Rect(w.rect)
        return None

    @staticmethod
    def _gonfio_del_bordo(annot: Any) -> float:
        """Di quanto ``set_rect`` gonfia il riquadro, per lato.

        PyMuPDF scrive il ``/Rect`` comprehensive del bordo: ``add_rect_annot``
        e ``set_rect`` entrambi allargano di ``max(bordatura, 2) / 2`` per
        lato, mentre il lettore ``annot.rect`` restituisce il ``/Rect`` cosi'
        com'e'. Riscrivere il valore letto gonfiava quindi l'annotazione di due
        punti a ogni spostamento: un rettangolo da 100x60, trascinato quattro
        volte, era diventato 110x70 e continuava a crescere.
        """
        try:
            larghezza = float(annot.border["width"])
        except Exception:
            try:
                larghezza = float(annot.border[1])
            except Exception:
                return 1.0
        return max(larghezza, 2.0) / 2.0

    def _rect_come_lettorlo(self, annot: Any, rect: geo.Rect) -> geo.Rect:
        """Il riquadro da passare a ``set_rect`` perché il lettore torni ``rect``."""
        r = geo.Rect(rect)
        m = self._gonfio_del_bordo(annot)
        dentro = geo.Rect(r.x0 + m, r.y0 + m, r.x1 - m, r.y1 - m)
        # un riquadro piu' piccolo del bordo non si puo' restringere: meglio
        # lasciarlo com'e' che scrivere coordinate invertite
        return dentro if (r.width > 2 * m and r.height > 2 * m) else r

    def set_annot_rect(self, page_index: int, xref: int, rect: geo.Rect) -> bool:
        """Sposta un'annotazione aggiornandone il riquadro.

        Riporta ``True`` se l'elemento c'era davvero. Prima riportava sempre
        ``False``: la closure non restituiva nulla, e ``bool(None)`` vale
        ``False``, quindi un chiamante che controllava il risultato leggeva
        sempre «non riuscito» anche quando il riquadro era stato spostato.
        """
        page = self.page(page_index)
        annot = next((a for a in page.annots() or () if a.xref == xref), None)

        def _op() -> bool:
            if annot is not None:
                annot.set_rect(self._rect_come_lettorlo(annot, rect))
                annot.update()
                return True
            pg = self.page(page_index)
            for w in pg.widgets() or ():
                if w.xref == xref:
                    w.rect = geo.Rect(rect)
                    w.update()
                    return True
            return False

        return bool(self._mutate("Sposta elemento", _op))


    def set_annot_props(self, page_index: int, xref: int, props: dict[str, Any]) -> bool:
        """Aggiorna proprietà di annotazione o campo (colori, opacità, testo…).

        Riporta ``True`` se l'elemento c'era: come ``set_annot_rect``, prima
        riportava sempre ``False`` perche' la closure non restituiva nulla.
        """
        page = self.page(page_index)
        annot = next((a for a in page.annots() or () if a.xref == xref), None)
        widget = None
        if annot is None:
            widget = next((w for w in page.widgets() or () if w.xref == xref), None)
            if widget is None:
                return False

        def _op() -> bool:
            if annot is not None:
                if "colors" in props:
                    c = props["colors"] or {}
                    annot.set_colors(stroke=c.get("stroke"), fill=c.get("fill"))
                if "opacity" in props:
                    annot.set_opacity(float(props["opacity"]))
                if "border_width" in props:
                    annot.set_border(width=props["border_width"])
                if "border_dashes" in props:
                    annot.set_border(dashes=props["border_dashes"])
                if props.get("text") is not None:
                    annot.set_info(content=props["text"])
                if props.get("title") is not None:
                    annot.set_info(title=props["title"])
                if props.get("icon") is not None:
                    annot.set_info(icon=props["icon"])
                if props.get("vertices") is not None and props.get("type") in ("line",):
                    annot.set_vertices(props["vertices"])
                annot.update()
            else:
                for key, val in props.items():
                    try:
                        setattr(widget, key, val)
                    except Exception:
                        continue
                widget.update()
            return True

        return bool(self._mutate("Modifica proprietà", _op))

    def add_annot(
        self,
        page_index: int,
        kind: str,
        rect: geo.Rect,
        *,
        quads: Sequence[geo.Rect] | None = None,
        vertices: Sequence[tuple[float, float]] | None = None,
        color: tuple[float, float, float] = (1, 0, 0),
        fill: tuple[float, float, float] | None = None,
        opacity: float = 1.0,
        width: float = 1.0,
        text: str = "",
        icon: str = "Note",
        name: str | None = None,
        attachment_bytes: bytes | None = None,
        filename: str = "allegato.txt",
        target_page: int | None = None,
        fontsize: float = 11.0,
        text_color: tuple[float, float, float] = (0, 0, 0),
        align: int = 0,
        underline: bool = False,
        border: tuple[float, float, float] | None = None,
    ) -> int:
        """Crea un'annotazione e ne restituisce l'xref.

        La creazione avviene interamente dentro ``_mutate``: se l'annotazione
        fosse creata prima, la copia di stato usata per l'annullamento
        conterrebbe gia' la modifica e l'undo risulterebbe inefficace.
        """
        qs = [geo.Rect(q) for q in (quads or [rect])]
        stato: dict[str, Any] = {}

        def _op() -> int:
            page = self.page(page_index)
            annot = None

            if kind == "highlight":
                annot = page.add_highlight_annot(geo.union(qs))
                annot.set_colors(stroke=color)
            elif kind in ("underline", "strikeout", "squiggly"):
                annot = _add_text_marker(page, kind, geo.union(qs), qs)
                annot.set_colors(stroke=color)
            elif kind == "freetext":
                annot = page.add_freetext_annot(
                    geo.Rect(rect), text=text, fontsize=float(fontsize),
                    text_color=tuple(text_color), align=int(align),
                )
                annot.set_border(width=0)
                annot.set_info(content=text)
                annot.update()
                if fill is not None or border is not None or underline:
                    # MuPDF rifiuta ``set_colors`` sulle annotazioni FreeText
                    # («cannot be used for FreeText annotations»): lo sfondo e
                    # il bordo vengono quindi disegnati sulla pagina, come fa
                    # la casella di testo, mentre l'annotazione porta il testo
                    if fill is not None or border is not None:
                        page.draw_rect(
                            geo.Rect(rect), color=border, fill=fill,
                            width=width if border is not None else 0,
                            fill_opacity=opacity, stroke_opacity=opacity, overlay=True,
                        )
                    if underline and text.strip():
                        # il testo sta nella appearance dell'annotazione e non
                        # nel flusso di contenuto: le righe si tracciano sotto
                        # con lo stesso modello di impaginazione delle caselle
                        _sottolinea_layout(
                            page, geo.Rect(rect), text, float(fontsize), tuple(text_color)
                        )
            elif kind == "note":
                annot = page.add_text_annot(geo.Rect(rect).tl + (2, 14), text, icon=icon)
                annot.set_info(title=name or "", content=text)
                annot.update()
            elif kind == "rect":
                annot = page.add_rect_annot(geo.Rect(rect))
                annot.set_colors(stroke=color, fill=fill)
                annot.set_border(width=width)
            elif kind == "circle":
                annot = page.add_circle_annot(geo.Rect(rect))
                annot.set_colors(stroke=color, fill=fill)
                annot.set_border(width=width)
            elif kind in ("line", "arrow"):
                pts = list(vertices or [])
                if len(pts) < 2:
                    raise DocumentError("Servono due punti per una linea.")
                annot = page.add_line_annot(pts[0], pts[1])
                annot.set_colors(stroke=color)
                annot.set_border(width=width)
                if kind == "arrow":
                    # PyMuPDF non espone le estremita' di linea: la punta della
                    # freccia si imposta scrivendo /LE nell'oggetto annotazione.
                    r, g, b = color
                    _set_line_ends(self._require(), annot.xref, True, color=f"[{r:g} {g:g} {b:g}]")
            elif kind == "polygon":
                pts = list(vertices or [])
                if len(pts) < 3:
                    raise DocumentError("Servono almeno tre punti per un poligono.")
                annot = page.add_polygon_annot(pts)
                annot.set_colors(stroke=color, fill=fill)
                annot.set_border(width=width)
            elif kind == "polyline":
                pts = list(vertices or [])
                if len(pts) < 2:
                    raise DocumentError("Servono almeno due punti per una polilinea.")
                annot = page.add_polyline_annot(pts)
                annot.set_colors(stroke=color)
                annot.set_border(width=width)
            elif kind == "ink":
                strokes = _group_points(list(vertices or []))
                if not strokes:
                    raise DocumentError("Nessun tratto da salvare.")
                annot = page.add_ink_annot(strokes)
                annot.set_colors(stroke=color)
                annot.set_border(width=width)
            elif kind == "stamp":
                annot = page.add_stamp_annot(geo.Rect(rect), stamp=-1)
                annot.set_colors(stroke=color)
            elif kind == "file":
                data = attachment_bytes
                if data is None:
                    data = text.encode() if isinstance(text, str) else bytes(text)
                annot = page.add_file_annot(
                    geo.Rect(rect), buffer_=data, filename=filename
                )
                annot.set_info(content=filename, title=name or "")
                annot.update()
            elif kind == "link":
                # I collegamenti non sono annotazioni: vivono in un array separato.
                # Con `target_page` il salto resta dentro il documento; senza,
                # `text` e' l'indirizzo esterno.
                if target_page is not None:
                    if not 0 <= int(target_page) < self.page_count:
                        raise DocumentError("La pagina di destinazione non esiste.")
                    page.insert_link(
                        {"kind": pymupdf.LINK_GOTO, "from": geo.Rect(rect),
                         "page": int(target_page)}
                    )
                else:
                    page.insert_link(
                        {"kind": pymupdf.LINK_URI, "from": geo.Rect(rect), "uri": text}
                    )
                return 0
            else:
                raise DocumentError(
                    tr("Tipo di annotazione non supportato: {tipo}").format(tipo=kind)
                )

            if annot is None:
                raise DocumentError("Impossibile creare l'annotazione.")
            if opacity < 1.0:
                try:
                    annot.set_opacity(opacity)
                except Exception:
                    pass
            annot.update()
            if name and kind != "link":
                annot.set_info(title=name)
                annot.update()
            stato["xref"] = annot.xref
            return annot.xref

        return int(self._mutate("Aggiungi annotazione", _op))

    def annotation_types_present(self, page_index: int) -> set[str]:
        return {a["type"] for a in self.annots(page_index, include_widgets=False)}

    def flatten_annotations(self, page_index: int | None = None) -> None:
        """Trasforma annotazioni e campi in contenuto permanente.

        ``Page.apply_annots`` non esiste in PyMuPDF 1.28: chiamarlo faceva
        fallire la voce di menu con un AttributeError. La procedura
        disponibile è ``bake`` sull'intero documento, quindi ``page_index``
        viene accettato per compatibilità ma non restringe l'operazione.

        I campi modulo vengono lasciati in piedi: ``bake(annots=True,
        widgets=True)`` — cioè quello che faceva questa funzione — cancellava
        anche i campi, e «Appiattisci annotazioni» e «Appiattisci campi» erano
        la stessa operazione distruttiva.
        """

        def _op() -> None:
            self._require().bake(annots=True, widgets=False)

        self._mutate("Appiattisci annotazioni", _op, emit_pages=True)

    def flatten_fields(self, page_index: int | None = None) -> None:
        """Appiattisci i campi modulo, rendendoli testo non modificabile.

        Come per :meth:`flatten_annotations`, ``page_index`` viene accettato ma
        non restringe l'operazione: ``bake`` agisce sull'intero documento. Qui
        però si lasciano in piedi le annotazioni, che appartengono a un'altra
        voce di menu: prima sparivano anch'esse, con commenti, evidenziazioni e
        timbri.
        """

        def _op() -> None:
            # ``bake`` agisce sull'intero documento: PyMuPDF 1.28 lo espone qui
            # e non sulla singola pagina.
            self._require().bake(annots=False, widgets=True)

        self._mutate("Appiattisci campi", _op, emit_pages=True)

    def reset_form(self, page_index: int | None = None) -> None:
        """Azzera i campi modulo al valore iniziale."""
        idxs = range(self.page_count) if page_index is None else [page_index]

        def _op() -> None:
            doc = self._require()
            for i in idxs:
                page = doc[i]  # va tenuto viva: vedi widget_objects
                # ``reset`` e ``update`` vanno eseguiti in due passate con liste
                # di widget nuove: riusando gli stessi oggetti, PyMuPDF non li
                # collega piu' alla pagina e il valore non viene azzerato.
                for w in list(page.widgets() or ()):
                    w.reset()
                for w in list(page.widgets() or ()):
                    w.update()

        self._mutate("Azzera campi", _op, emit_pages=True)

    # ------------------------------------------------------------------ redazione

    def redact(
        self,
        page_index: int,
        rects: Sequence[geo.Rect],
        images: str = "remove",
        drawings: str = "remove",
        fill: tuple[float, float, float] = (1, 1, 1),
    ) -> None:
        """Rimuove in modo permanente il contenuto nelle aree indicate.

        ``images`` e ``drawings`` accettano ``remove`` o ``keep``; il testo
        sotto l'area viene sempre rimosso (e' il punto della redazione).
        """
        if not rects:
            return
        rs = [geo.Rect(r) for r in rects]
        image_mode = pymupdf.PDF_REDACT_IMAGE_REMOVE if images == "remove" else pymupdf.PDF_REDACT_IMAGE_NONE
        graphic_mode = (
            pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED
            if drawings == "remove"
            else pymupdf.PDF_REDACT_LINE_ART_NONE
        )

        def _op() -> None:
            page = self.page(page_index)
            for r in rs:
                page.add_redact_annot(r, fill=fill, cross_out=False)
            try:
                page.apply_redactions(
                    images=image_mode,
                    graphics=graphic_mode,
                    text=pymupdf.PDF_REDACT_TEXT_REMOVE,
                )
            except Exception as exc:
                raise DocumentError(
                    tr("Redazione non riuscita: {errore}").format(errore=exc)
                ) from exc

        self._mutate("Redazione", _op, emit_pages=True)

    def find_redact_targets(self, page_index: int, needle: str) -> list[geo.Rect]:
        return [geo.Rect(r) for r in self.page(page_index).search_for(needle)]

    def redact_search(self, page_index: int, needle: str, **kw: Any) -> int:
        """Redige tutte le occorrenze di un testo nella pagina."""
        rects = self.find_redact_targets(page_index, needle)
        if rects:
            self.redact(page_index, rects, **kw)
        return len(rects)

    # ----------------------------------------------------------------------- testo

    def text(self, page_index: int) -> str:
        """Testo della pagina, nell'ordine in cui si legge.

        ``get_text`` segue l'ordine del flusso di contenuto, non quello
        visivo: il testo inserito da una sostituzione viene accodato in fondo
        e finiva letto per ultimo. Riordinando per posizione l'estrazione
        torna quella che si vede, che e' quella che serve per copiare,
        esportare e per gli screen reader.
        """
        page = self.page(page_index)
        try:
            blocchi = page.get_text("blocks")
        except Exception:
            return page.get_text("text")
        righe = [
            (blocco[1], blocco[3], blocco[0], blocco[4])
            for blocco in blocchi
            if len(blocco) >= 7 and blocco[6] == 0 and blocco[4].strip()
        ]
        if not righe:
            return page.get_text("text")
        # i blocchi sulla stessa riga vanno uniti e riordinati da sinistra a
        # destra: dopo una sostituzione la parola nuova e' un blocco a se
        righe.sort(key=lambda r: (round(r[0], 1), r[2]))
        uscite: list[list] = []
        for y0, y1, x0, testo in righe:
            if uscite:
                ultima = uscite[-1]
                altezza = max(ultima[1] - ultima[0], 1.0)
                # sovrapposizione verticale: stessa riga
                if min(ultima[1], y1) - max(ultima[0], y0) > altezza * 0.5:
                    ultima[2].append((x0, testo))
                    ultima[0] = min(ultima[0], y0)
                    ultima[1] = max(ultima[1], y1)
                    continue
            uscite.append([y0, y1, [(x0, testo)]])
        righe_testo = []
        for _, _, pezzi in uscite:
            pezzi.sort(key=lambda p: p[0])
            # ogni blocco porta con se' il terminatore di riga: va tolto prima
            # di accostare i pezzi della stessa riga
            righe_testo.append(" ".join(t.strip() for _, t in pezzi if t.strip()).strip())
        return "\n".join(r for r in righe_testo if r)

    # ------------------------------------------------------------ selezione testo

    def words(self, page_index: int) -> list[tuple[geo.Rect, str]]:
        """Parole di una pagina, con il riquadro in coordinate schermo.

        Il risultato e' in cache finche' la pagina non cambia: serve sia per
        evidenziare la selezione sia per contare le parole, e va ricalcolato
        dopo ogni modifica.
        """
        cached = self._word_cache.get(page_index)
        if cached is not None:
            return cached
        out: list[tuple[geo.Rect, str]] = []
        for x0, y0, x1, y1, word, *_ in self.page(page_index).get_text("words"):
            testo = str(word).strip()
            if not testo:
                continue
            out.append((self.to_display_rect(page_index, geo.Rect(x0, y0, x1, y1)), testo))
        self._word_cache[page_index] = out
        return out

    def words_in_rect(self, page_index: int, rect: geo.Rect | BoxLike) -> list[geo.Rect]:
        """Riquadri delle parole che intersecano ``rect``.

        Una parola basta a essere presa: e' il comportamento atteso da chi
        trascina un segno di selezione su una riga di testo.
        """
        zona = _as_rect(rect)
        if zona.is_empty:
            return []
        prese: list[geo.Rect] = []
        for r, _ in self.words(page_index):
            if r.intersects(zona):
                prese.append(r)
        return prese

    def selected_text(self, page_index: int, rect: geo.Rect | BoxLike) -> str:
        """Testo delle parole comprese in ``rect``, in ordine di lettura.

        ``rect`` e' nello spazio mostrato della pagina, come i riquadri che
        restituisce :meth:`words`. ``get_text(clip=...)`` vuole invece lo spazio
        pagina: senza la conversione, su una pagina ruotata il ritaglio
        finiva nel vuoto e la copia risultava una stringa vuota.

        Si estrae dall'unione dei riquadri delle parole scelte: il risultato
        e' il testo vero, senza spezzare le parole a meta' ne' lasciare dentro
        le righe vicine.
        """
        scelte = self.words_in_rect(page_index, rect)
        if not scelte:
            return ""
        unione = scelte[0]
        for r in scelte[1:]:
            unione = unione | r
        ritaglio = pymupdf.Rect(self.to_page_rect(page_index, unione))
        testo = self.page(page_index).get_text("text", clip=ritaglio, sort=True)
        # l'unione puo' contenere righe vuote: si normalizza come in un copia-incolla
        righe = [r.rstrip() for r in testo.splitlines()]
        return "\n".join(r for r in righe if r.strip())

    def extract_text(self, page_index: int | None = None) -> str:
        if page_index is not None:
            return self.text(page_index)
        return "\n".join(self.page(i).get_text("text") for i in range(self.page_count))

    def insert_text_box(
        self,
        page_index: int,
        rect: geo.Rect,
        content: str,
        *,
        fontname: str = "helv",
        fontsize: float = 12.0,
        color: tuple[float, float, float] = (0, 0, 0),
        align: int = 0,
        rotate: int = 0,
        lineheight: float | None = None,
        fill: tuple[float, float, float] | None = None,
        border: tuple[float, float, float] | None = None,
        border_width: float = 0.8,
        margin: float = 2.0,
        opacity: float = 1.0,
        fit: str = "none",
        underline: bool = False,
    ) -> dict[str, Any]:
        """Crea una casella di testo riportando l'eventuale overflow.

        ``fit``: ``none``, ``shrink`` (riduce il corpo finche entra) oppure ``grow``
        (estende l'altezza del riquadro). Un valore negativo restituito da
        ``insert_textbox`` indica spazio insufficiente.

        ``underline`` disegna la sottolineatura: ``insert_textbox`` non la
        prevede, quindi le righe vengono tracciate sulle misure restituite da
        MuPDF per il testo appena inserito, non calcolate a parte.
        """
        page = self.page(page_index)
        box = geo.Rect(rect)
        inner = geo.Rect(box.x0 + margin, box.y0 + margin, box.x1 - margin, box.y1 - margin)
        if inner.width < 4 or inner.height < 4:
            raise DocumentError("Riquadro troppo piccolo per il testo.")
        if fit == "grow":
            need = textlayout.layout_text(content, fontname, fontsize, inner.width).height
            box = geo.Rect(box.x0, box.y0, box.x1, box.y0 + need + 2 * margin)
            inner = geo.Rect(box.x0 + margin, box.y0 + margin, box.x1 - margin, box.y1 - margin)
        elif fit == "shrink":
            fontsize = textlayout.fit_fontsize(content, fontname, fontsize, inner.width, inner.height)
        captured: dict[str, Any] = {}

        def _op() -> None:
            # ``insert_textbox`` non gestisce bordo ne margini: li disegniamo a parte.
            if fill is not None or border is not None:
                page.draw_rect(
                    box,
                    color=border,
                    fill=fill,
                    width=border_width if border is not None else 0,
                    fill_opacity=opacity,
                    stroke_opacity=opacity,
                    overlay=True,
                )
            gia_presenti = _chiavi_span(page) if underline else set()
            rc = page.insert_textbox(
                inner,
                content,
                fontname=fontname,
                fontsize=fontsize,
                color=color,
                align=align,
                rotate=rotate,
                lineheight=lineheight,
                overlay=True,
            )
            captured["spare"] = rc
            if underline and content.strip():
                _sottolinea(page, gia_presenti, color, fontsize, opacity)

        self._mutate("Aggiungi casella di testo", _op)
        if captured.get("spare", 0) is not None and captured["spare"] < 0:
            self._invalidate_caches()
        return {"rect": box, "fontsize": fontsize, "spare": captured.get("spare", 0)}

    def add_text(self, page_index: int, point: tuple[float, float], content: str, **kw: Any) -> None:
        self._mutate("Aggiungi testo", lambda: self.page(page_index).insert_text(point, content, **kw))

    def replace_text(
        self,
        needle: str,
        replacement: str,
        page_index: int | None = None,
        *,
        case: bool = False,
        whole_word: bool = False,
    ) -> int:
        """Sostituisce le occorrenze di un testo riscrivendo la pagina.

        Le parole coperte vengono redatte e il nuovo testo reinserito nella stessa
        posizione: e il metodo usato dagli editor che modificano testi esistenti.

        ``case`` e ``whole_word`` hanno lo stesso significato che in
        :meth:`search`. Prima non esistevano e venivano sostituite tutte le
        occorrenze: le caselle «Maiusc/minuscole» e «Parola intera» della ricerca
        non avevano effetto quando si sostituiva.
        """
        if not needle:
            return 0
        idxs = list(range(self.page_count)) if page_index is None else [page_index]
        cercati: list[tuple[int, geo.Rect]] = []
        for i in idxs:
            for hit in self.search(needle, i, case=case, whole_word=whole_word):
                cercati.append((i, geo.Rect(hit["rect"])))
        if not cercati:
            return 0

        def _op() -> int:
            # la redazione e' distruttiva: senza un passaggio da _mutate non
            # restava traccia e l'annullamento non riportava il testo indietro
            return sum(self._replace_hit(i, hit, replacement) for i, hit in cercati)

        return self._mutate(f"Sostituisci «{needle}»", _op)

    def _replace_hit(self, page_index: int, hit: geo.Rect, replacement: str) -> int:
        page = self.page(page_index)
        words = page.get_text("words")
        touched: list[tuple[float, float, float]] = []
        for w in words:
            wr = geo.Rect(w[:4])
            if wr.intersects(hit):
                inter = wr & hit
                if not inter.is_empty:
                    touched.append((inter.x0, inter.y0, inter.width))
                    page.add_redact_annot(inter)
        if not touched:
            return 0
        # Lo stile va letto PRIMA della redazione: dopo, il testo originale e'
        # sparito e la ricerca cadeva sui 11 pt neri di ripiego. Ogni parola
        # sostituita perdeva corpo, colore e font.
        size, colore, font = _stile_da_riquadro(page, hit)
        # ``PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED`` (il default) cancella anche
        # le regole e i bordi che toccano la parola: sostituire una parola
        # dentro una tabella o un modulo ne cancellava la cornice.
        page.apply_redactions(
            images=pymupdf.PDF_REDACT_IMAGE_NONE,
            graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
        )
        rgb = _span_color(colore)
        x = hit.x0
        y = hit.y1 - size * 0.2
        # senza ``overlay`` MuPDF metteva il testo sostitutivo in un nuovo
        # flusso di contenuto piazzato per primo: la sostituzione finiva
        # sotto tutto il resto della pagina e risultava invisibile
        page.insert_text(
            (x, y), replacement, fontsize=size, fontname=font, color=rgb, overlay=True
        )
        return 1

    def fonts(self, page_index: int = 0) -> list[str]:
        try:
            names = self.page(page_index).get_fonts(full=True)
        except Exception:
            return []
        return sorted({f[3] for f in names if len(f) > 3 and f[3]})

    def embed_font(self, page_index: int, fontfile: str, alias: str = "F0") -> str:
        """Incorpora un font TTF/OTF e restituisce l'alias utilizzabile."""
        return self.page(page_index).insert_font(fontname=alias, fontfile=fontfile)

    # -------------------------------------------------------------------- immagini

    def insert_image(
        self,
        page_index: int,
        rect: geo.Rect,
        source: str | bytes | io.BytesIO | pymupdf.Pixmap,
        *,
        keep_proportion: bool = True,
    ) -> None:
        """Inserisce un'immagine nel riquadro indicato."""
        box = geo.Rect(rect)
        if keep_proportion and not isinstance(source, pymupdf.Pixmap):
            size = _image_size(source)
            if size and size[0] > 0 and size[1] > 0:
                box = geo.aspect_limited(box, size[0] / size[1])

        def _op() -> None:
            self.page(page_index).insert_image(box, stream=_as_image_stream(source),
                                               keep_proportion=False, overlay=True)

        self._mutate("Inserisci immagine", _op)

    def find_free_spot(
        self, page_index: int, width: float, height: float, margin: float = 18.0
    ) -> geo.Rect:
        """Trova una posizione libera per un elemento nuovo.

        Si preferisce il fondo pagina a destra, poi si risale; se la colonna e'
        occupata si prova il lato sinistro. Il controllo avviene riquadro per
        riquadro: confrontarsi con l'ingombro complessivo di tutto il contenuto
        renderebbe inutilizzabile la pagina.
        """
        info = self.page_info(page_index)
        left = margin
        top = margin
        right = max(left + 1, info.rect.width - margin)
        bottom = max(top + 1, info.rect.height - margin)
        if width <= 0 or height <= 0:
            width, height = 170.0, 60.0
        w = min(float(width), right - left)
        h = min(float(height), bottom - top)

        busy: list[geo.Rect] = []
        try:
            # tutto in coordinate mostrate: le annotazioni e i campi arrivano
            # nello spazio pagina e vanno convertiti, mentre i blocchi di testo
            # e i riquadri delle immagini vanno nel modo opposto. Senza la
            # conversione gli ostacoli finivano fuori dal foglio di lavoro e la
            # firma automatica si posava sopra il testo
            for a in self.annots(page_index):
                busy.append(self.to_display_rect(page_index, a["rect"]))
            for f in self.fields(page_index):
                busy.append(self.to_display_rect(page_index, f.rect))
            # anche le immagini gia' inserite (firme comprese) occupano spazio
            for info_i in self.image_rects(page_index):
                busy.append(self.to_display_rect(page_index, info_i["rect"]))
            for b in self.page(page_index).get_text("blocks") or ():
                busy.append(self.to_display_rect(page_index, geo.Rect(b[:4])))
        except Exception:
            pass
        busy = [r for r in busy if not r.is_empty]

        def is_free(x: float, y: float) -> bool:
            probe = geo.Rect(x, y, x + w, y + h)
            for b in busy:
                if probe.intersects(b) and not (probe & b).is_empty:
                    return False
            return True

        # colonna destra, dal basso verso l'alto
        y = bottom - h
        step = h + margin
        while y >= top:
            if is_free(right - w, y):
                return geo.Rect(right - w, y, right, y + h)
            y -= step
        # colonna sinistra
        y = bottom - h
        while y >= top:
            if is_free(left, y):
                return geo.Rect(left, y, left + w, y + h)
            y -= step
        # stessa colonna, piu' stretta
        for w2 in (w * 0.75, w * 0.5):
            h2 = min(h, (bottom - top) * 0.12)
            y = bottom - h2
            while y >= top:
                if is_free(right - w2, y):
                    return geo.Rect(right - w2, y, right, y + h2)
                y -= h2 + margin
        return geo.Rect(left, top, left + w, top + h)

    def image_rects(self, page_index: int) -> list[dict[str, Any]]:
        """Le immagini realmente disegnate nella pagina.

        MuPDF, quando un'immagine viene cancellata, lascia al suo posto un
        segnaposto di un pixel per mantenere valide le referenze: quel
        segnaposto non disegna nulla ma continua a comparire in
        ``get_image_info`` con il riquadro vecchio. Se lo si lascia passare,
        l'inventario e il rilevamento sotto il cursore contano un'immagine
        invisibile, e trascinarla reinserisce un rettangolo di un pixel.
        """
        out = []
        for info in self.page(page_index).get_image_info(xrefs=True):
            larghezza = int(info.get("width", 0) or 0)
            altezza = int(info.get("height", 0) or 0)
            if larghezza <= 1 and altezza <= 1:
                continue  # segnaposto di MuPDF, non un'immagine del documento
            out.append(
                {
                    "xref": info.get("xref"),
                    "rect": geo.Rect(info["bbox"]),
                    "width": larghezza,
                    "height": altezza,
                    "bpc": info.get("bpc", 8),
                    "cs": info.get("cs-name", ""),
                }
            )
        return out

    def extract_image(self, xref: int) -> bytes:
        """I dati dell'immagine, con la trasparenza quando c'e'.

        ``Document.extract_image`` di PyMuPDF restituisce i campi RGB e lascia
        la maschera di trasparenza in un oggetto separato, indicato dalla voce
        ``smask``. Prendere solo ``image`` perdeva l'alpha: la firma, che MuPDF
        salva come RGB piu' SMask, tornava con lo sfondo nero a ogni
        spostamento. Qui i due pezzi vengono uniti in un PNG RGBA.
        """
        d = self._require()
        info = d.extract_image(xref)
        smask = info.get("smask") or 0
        if not smask:
            return info["image"]
        try:
            base = pymupdf.Pixmap(d, xref)
            mask = pymupdf.Pixmap(d, smask)
            if mask.width != base.width or mask.height != base.height:
                return info["image"]
            return pymupdf.Pixmap(base, mask).tobytes("png")
        except Exception:
            return info["image"]

    def move_image(self, page_index: int, xref: int, rect: geo.Rect) -> None:
        """Sposta o ridimensiona un'immagine già inserita nella pagina.

        Le immagini non sono annotazioni e non si possono spostare da sole:
        vengono rilette e reinserite nella nuova posizione, così si comportano
        come una casella di testo e si possono trascinare con il mouse.

        Fra la cancellazione e la reinserimento il documento viene riaperto
        dai suoi stessi byte. Senza questo, alla seconda immagine spostata la
        nuova finiva sul segnaposto di un pixel lasciato da MuPDF e
        l'immagine spariva dal file: trascinare due volte una firma la faceva
        svanire. Riaprire ricostruisce il dizionario delle risorse, ed è il
        costo che il progetto paga gia' a ogni modifica.
        """
        box = geo.Rect(rect)
        if box.is_empty:
            raise DocumentError("Il riquadro dell'immagine è vuoto.")
        dati = self.extract_image(xref)

        def _op() -> None:
            page = self.page(page_index)
            try:
                page.delete_image(xref)
            except Exception as exc:
                raise DocumentError(
                    tr("Impossibile spostare l'immagine: {errore}").format(errore=exc)
                ) from exc
            # vedi la docstring: senza la riapertura la seconda mossa distrugge
            # l'immagine
            grezzo = self._require().tobytes(garbage=0, deflate=True)
            rotazioni = self._view_rot
            self._adopt(pymupdf.open("pdf", grezzo))
            self._view_rot = rotazioni  # `_adopt` la svuota: e' stato della vista
            self.page(page_index).insert_image(
                box, stream=dati, keep_proportion=False, overlay=True
            )

        self._mutate("Sposta immagine", _op)

    def delete_image(self, page_index: int, xref: int) -> None:
        """Elimina un'immagine inserita nella pagina.

        Serve a «Elimina selezione»: senza di questo, cancellare una firma o
        un'immagine non era possibile, perche' non sono annotazioni e
        ``delete_annot`` non le tocca.
        """
        rect = self.image_rect(page_index, xref)
        if rect is None:
            raise DocumentError("Immagine non trovata sulla pagina indicata.")

        def _op() -> None:
            page = self.page(page_index)
            try:
                page.delete_image(xref)
            except Exception as exc:
                raise DocumentError(
                    tr("Impossibile eliminare l'immagine: {errore}").format(errore=exc)
                ) from exc

        self._mutate("Elimina immagine", _op)

    def image_rect(self, page_index: int, xref: int) -> geo.Rect | None:
        """Il riquadro di un'immagine nella pagina, se c'e'."""
        for im in self.image_rects(page_index):
            if im.get("xref") == xref:
                return geo.Rect(im["rect"])
        return None

    def extract_image_to_file(self, xref: int, path: str | os.PathLike[str]) -> Path:
        data = self.extract_image(xref)
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p

    # ---------------------------------------------------------------------- moduli

    def validate_field_value(self, page_index: int, xref: int, value: Any) -> tuple[bool, str]:
        """Verifica un valore prima di assegnarlo a un campo.

        Restituisce ``(valido, messaggio)``. Serve all'interfaccia per avvisare
        l'utente prima che il valore venga troncato o rifiutato.
        """
        target = self._field_widget(page_index, xref)
        if target is None:
            return False, "Campo non trovato."
        tipo = target.field_type
        if tipo == pymupdf.PDF_WIDGET_TYPE_TEXT:
            massimo = int(getattr(target, "text_maxlen", 0) or 0)
            testo = "" if value is None else str(value)
            if massimo > 0 and len(testo) > massimo:
                return False, f"Il campo ammette al massimo {massimo} caratteri."
        elif tipo in (pymupdf.PDF_WIDGET_TYPE_COMBOBOX, pymupdf.PDF_WIDGET_TYPE_LISTBOX):
            opzioni = [str(v) for v in (getattr(target, "choice_values", None) or [])]
            if value not in ("", None) and opzioni and str(value) not in opzioni:
                return False, "Il valore non è fra le opzioni del menu."
        return True, ""

    def set_field_value(self, page_index: int, xref: int, value: Any) -> bool:
        """Imposta il valore di un campo e lo rende persistente nel PDF."""
        target = self._field_widget(page_index, xref)
        if target is None:
            return False
        if target.field_type == pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON:
            # I pulsanti di opzione di un gruppo valgono una scelta sola:
            # impostandoli come caselle di spunta indipendenti restavano
            # accese piu' opzioni contemporaneamente e il campo padre
            # continuava a riportare «Off».
            return self.select_radio(page_index, xref)
        page = self.page(page_index)

        def _op() -> None:
            pg = self.page(page_index)
            w = next((x for x in pg.widgets() or () if x.xref == xref), None)
            if w is None:
                raise DocumentError("Campo non trovato durante l'aggiornamento.")
            w.field_value = _normalize_field_value(w, value)
            w.update()

        try:
            # Non si ricostruisce la scena delle pagine: l'editor del campo
            # verrebbe distrutto a ogni tasto premuto e la digitazione
            # andrebbe perduta. Basta invalidare le cache: chi chiama si
            # occupa di ridisegnare la pagina.
            self._mutate("Compila campo", _op, emit_pages=False)
        except DocumentError:
            return False
        self.events.emit("field", page_index, xref)
        return True

    def _field_widget(self, page_index: int, xref: int) -> pymupdf.Widget | None:
        if not (0 <= page_index < self.page_count):
            return None
        try:
            return next((w for w in self.page(page_index).widgets() or () if w.xref == xref), None)
        except Exception:
            return None

    def set_field_properties(self, page_index: int, xref: int, props: dict[str, Any]) -> bool:
        target = self._field_widget(page_index, xref)
        if target is None:
            return False
        dati = _normalize_field_props(props)

        def _op() -> None:
            pg = self.page(page_index)
            w = next((x for x in pg.widgets() or () if x.xref == xref), None)
            if w is None:
                raise DocumentError("Campo non trovato.")
            for key, val in dati.items():
                try:
                    setattr(w, key, val)
                except Exception as exc:
                    # Le impostazioni venivano scartate in silenzio e il
                    # fallimento emergeva solo dopo, da ``w.update()``, con un
                    # errore di PyMuPDF che non diceva quale campo fosse.
                    raise DocumentError(
                        tr("Impossibile impostare «{chiave}» del campo: {errore}")
                        .format(chiave=key, errore=exc)
                    ) from exc
            try:
                w.update()
            except Exception as exc:
                raise DocumentError(
                    tr("Impossibile applicare le proprietà del campo: {errore}").format(errore=exc)
                ) from exc

        try:
            self._mutate("Proprietà campo", _op, emit_pages=True)
        except DocumentError:
            return False
        return True

    def set_field_tooltip(self, page_index: int, xref: int, testo: str) -> bool:
        """Scrive la descrizione (``/TU``) mostrata passando col mouse sul campo.

        Va scritta come chiave grezza e non come attributo del widget: PyMuPDF
        non espone ``/TU``, quindi la finestra delle proprietà poteva raccoglierla
        ma non conservarla.
        """
        if self._field_widget(page_index, xref) is None:
            return False

        def _op() -> bool:
            self._require().xref_set_key(xref, "TU", f"({_pdf_escape(testo.strip())})")
            return True

        return bool(self._mutate("Descrizione campo", _op, emit_pages=False))

    def add_field(
        self,
        page_index: int,
        kind: str,
        rect: geo.Rect,
        name: str = "",
        value: Any = "",
        *,
        fontsize: float = 12.0,
        font: str = "Helv",
        text_color: tuple[float, float, float] = (0, 0, 0),
        fill_color: tuple[float, float, float] | None = None,
        border_color: tuple[float, float, float] = (0, 0, 0),
        border_style: int | str = 1,
        border_width: float = 1.0,
        maxlen: int = 0,
        multiline: bool = False,
        password: bool = False,
        read_only: bool = False,
        required: bool = False,
        comb: bool = False,
        options: Sequence[str] | None = None,
        tooltip: str = "",
        button_caption: str = "",
    ) -> int:
        """Crea un campo modulo e ne restituisce l'xref."""
        ftype = WIDGET_TYPES.get(kind)
        if ftype is None:
            raise DocumentError(
                tr("Tipo di campo non supportato: {tipo}").format(tipo=kind)
            )
        page = self.page(page_index)
        box = geo.Rect(rect)
        field_name = name or f"{kind}_{uuid.uuid4().hex[:6]}"
        created: dict[str, int] = {}

        def _op() -> int:
            w = pymupdf.Widget()
            w.field_type = ftype
            w.rect = box
            w.field_name = field_name
            if kind == "text":
                w.field_value = value if value is not None else ""
                w.text_fontsize = float(fontsize)
                # il font va ricondotto a un volto base del PDF: nella /DA di
                # un widget MuPDF scarta gli altri alias e scriverebbe /Helv,
                # cosi' il font scelto dalla finestra spariva senza avviso
                w.text_font = textlayout.font_da_name(font)
                w.text_color = text_color
                w.text_maxlen = int(maxlen or 0)
            elif kind == "checkbox":
                w.field_value = bool(value)
                w.button_caption = button_caption or "X"
            elif kind in ("combo", "list"):
                vals = list(options or ["Opzione 1", "Opzione 2"])
                w.choice_values = vals
                w.field_value = value if value in vals else (vals[0] if vals else "")
                w.text_fontsize = float(fontsize)
                w.text_font = textlayout.font_da_name(font)
                w.text_color = text_color
            elif kind == "button":
                w.field_value = ""
                w.button_caption = button_caption or name or "OK"
            elif kind == "signature":
                w.field_value = ""
            if fill_color:
                w.fill_color = fill_color
            w.border_color = border_color
            w.border_style = border_style_code(border_style)
            w.border_width = border_width
            flags = 0
            if read_only:
                flags |= 1
            if required:
                flags |= 2
            if multiline:
                flags |= 1 << 12
            if password:
                flags |= 1 << 13
            if comb:
                flags |= 1 << 24
            w.field_flags = flags
            annot = page.add_widget(w)
            if annot is None:
                raise DocumentError("Impossibile creare il campo.")
            xref = annot.xref
            doc = self._require()
            if kind == "checkbox" and not value:
                doc.xref_set_key(xref, "AS", "/Off")
            if kind == "signature":
                doc.xref_set_key(xref, "FT", "/Sig")
            if tooltip:
                doc.xref_set_key(xref, "TU", f"({_pdf_escape(tooltip)})")
            created["xref"] = xref
            return xref

        xref = int(self._mutate("Aggiungi campo", _op, emit_pages=True))
        self.events.emit("field", page_index, xref)
        return xref

    def add_radio_group(
        self,
        page_index: int,
        rects: Sequence[geo.Rect],
        name: str = "",
        selected: int = -1,
        tooltip: str = "",
    ) -> list[int]:
        """Crea un gruppo coerente di pulsanti di opzione.

        ``PyMuPDF`` non popola ``/Kids`` e il suo controllo interno fallisce su un
        parent privo di array: qui il parent nasce come campo nascosto e ``/Kids``
        viene scritto esplicitamente, insieme agli stati ``/AS`` e ``/V``.
        """
        if len(rects) < 2:
            raise DocumentError("Servono almeno due opzioni per un gruppo.")
        page = self.page(page_index)
        doc = self._require()
        box = geo.union([geo.Rect(r) for r in rects])
        group = name or f"grp_{uuid.uuid4().hex[:6]}"
        state: dict[str, Any] = {}

        def _op() -> list[int]:
            parent = pymupdf.Widget()
            parent.field_type = pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON
            parent.field_name = group
            parent.rect = geo.Rect(box)
            parent.field_value = False
            pa = page.add_widget(parent)
            pxref = pa.xref
            ff = doc.xref_get_key(pxref, "Ff")
            try:
                cur = int(ff[1]) if ff[0] == "int" else 0
            except Exception:
                cur = 0
            doc.xref_set_key(pxref, "Ff", str(cur | (1 << 13)))
            xrefs: list[int] = []
            for i, r in enumerate(rects):
                kid = pymupdf.Widget()
                kid.field_type = pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON
                kid.field_name = f"{group}#{i}"
                kid.rect = geo.Rect(r)
                kid.field_value = False
                kid.rb_parent = pxref
                ka = page.add_widget(kid)
                xrefs.append(ka.xref)
            doc.xref_set_key(pxref, "Kids", "[" + " ".join(f"{x} 0 R" for x in xrefs) + "]")
            for i, x in enumerate(xrefs):
                doc.xref_set_key(x, "Parent", f"{pxref} 0 R")
                # Ogni opzione riceve uno stato acceso proprio nel suo /AP:
                # con il solo /Yes di PyMuPDF tutte esporterebbero «Yes» e un
                # lettore esterno non saprebbe quale sia stata scelta.
                _radio_add_state(doc, x, _radio_state_name(group, f"{group}#{i}"))
                st = f"/{_radio_state_name(group, f'{group}#{i}')}" if i == selected else "/Off"
                doc.xref_set_key(x, "AS", st)
                doc.xref_set_key(x, "V", st)
                if tooltip:
                    doc.xref_set_key(x, "TU", f"({_pdf_escape(tooltip)})")
            if 0 <= selected < len(xrefs):
                doc.xref_set_key(
                    pxref, "V", f"/{_radio_state_name(group, f'{group}#{selected}')}"
                )
            state["parent"] = pxref
            state["kids"] = xrefs
            return xrefs

        xrefs = list(self._mutate("Aggiungi gruppo pulsanti", _op, emit_pages=True))
        return xrefs

    def select_radio(self, page_index: int, xref: int) -> bool:
        """Seleziona un pulsante di opzione spegnendo gli altri del gruppo.

        Un gruppo di pulsanti di opzione vale una scelta sola: il campo padre
        riceve il valore dell'opzione scelta e le altre passano a ``/Off``.
        Ricliccare l'opzione già attiva la deseleziona, come in Acrobat.
        """
        target = self._field_widget(page_index, xref)
        if target is None or target.field_type != pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON:
            return False
        if self._e_genitore_di_pulsanti(target):
            # il padre di un gruppo raccoglie tutte le opzioni: accenderlo o
            # spegnerlo non significa scegliere nulla
            return False
        nome = target.field_name or ""
        gruppo = _radio_group_of(nome)
        gia_accesa = target.field_value not in (False, "Off", "", None)

        def _op() -> None:
            pg = self.page(page_index)
            doc = self._require()
            padre = 0
            for w in list(pg.widgets() or ()):
                if w.field_type != pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON:
                    continue
                wnome = w.field_name or ""
                if _radio_group_of(wnome) != gruppo:
                    continue
                scelto = w.xref == xref
                if scelto:
                    padre = int(getattr(w, "rb_parent", 0) or 0)
                st = (
                    _radio_own_state(doc, xref, _radio_state_name(gruppo, nome))
                    if scelto and not gia_accesa
                    else "/Off"
                )
                doc.xref_set_key(w.xref, "AS", st)
                doc.xref_set_key(w.xref, "V", st)
                if scelto:
                    accesso = st
            if padre:
                doc.xref_set_key(padre, "V", accesso)

        self._mutate("Seleziona opzione", _op, emit_pages=True)
        return True

    def radio_is_on(self, page_index: int, xref: int) -> bool:
        page = self.page(page_index)
        for w in page.widgets() or ():
            if w.xref == xref:
                v = w.field_value
                return v not in (False, "Off", "", None)
        return False

    def tab_order(self) -> list[tuple[int, int]]:
        """Ordine di tabulazione, desunto dall'ordine delle annotazioni."""
        out: list[tuple[int, int]] = []
        for i in range(self.page_count):
            for entry in self.page(i).annot_xrefs() or []:
                xref = entry[0] if isinstance(entry, (tuple, list)) else entry
                try:
                    if self._require().xref_get_key(xref, "Subtype")[1] == "/Widget":
                        out.append((i, xref))
                except Exception:
                    continue
        return out

    def set_tab_order(self, order: Sequence[tuple[int, int]]) -> None:
        """Applica un ordine di tabulazione personalizzato.

        In PDF l'ordine di tabulazione segue la sequenza delle annotazioni nella
        matrice ``/Annots`` della pagina: basta riordinarla.
        """
        wanted = list(order)
        pos = 0

        def _op() -> None:
            nonlocal pos
            doc = self._require()
            pos = 0
            for i in range(doc.page_count):
                xrefs = [e[0] if isinstance(e, (tuple, list)) else e for e in (doc[i].annot_xrefs() or [])]
                page_items = [x for x in wanted if x[0] == i]
                order_x = [x[1] for x in page_items]
                rest = [x for x in xrefs if x not in order_x]
                new = order_x + rest
                if new != xrefs:
                    doc.xref_set_key(doc[i].xref, "Annots", "[" + " ".join(f"{x} 0 R" for x in new) + "]")

        self._mutate("Ordine campi", _op, emit_pages=True)

    def field_stats(self) -> dict[str, Any]:
        fs = self.fields()
        by_kind: dict[str, int] = {}
        for f in fs:
            by_kind[f.kind] = by_kind.get(f.kind, 0) + 1
        return {
            "total": len(fs),
            "by_kind": by_kind,
            "filled": sum(1 for f in fs if f.value not in (None, "", False, "Off")),
            "required": sum(1 for f in fs if f.required),
            "signed": sum(1 for f in fs if f.is_signed),
        }

    # --------------------------------------------------------------------- ricerca

    def search(
        self,
        needle: str,
        page_index: int | None = None,
        case: bool = False,
        whole_word: bool = False,
    ) -> list[dict[str, Any]]:
        """Cerca un testo e restituisce tutte le corrispondenze.

        ``Page.search_for`` in PyMuPDF 1.28 non distingue mai maiuscole/minuscole:
        la sensibilita' al caso viene quindi verificata confrontando il testo
        realmente presente nel rettangolo trovato.
        """
        if not needle:
            return []
        hits: list[dict[str, Any]] = []
        idxs = range(self.page_count) if page_index is None else [page_index]
        for i in idxs:
            page = self.page(i)
            try:
                rects = page.search_for(needle) or []
            except Exception:
                rects = []
            for r in rects:
                rect = geo.Rect(r)
                if not self._match_case(page, rect, needle, case):
                    continue
                if whole_word and not _whole_word(page, rect, needle, case):
                    continue
                hits.append(
                    {
                        "page": i,
                        "rect": rect,
                        "quads": self._hit_quads(page, rect),
                        "text": needle,
                    }
                )
        return hits

    def _match_case(self, page: pymupdf.Page, rect: geo.Rect, needle: str, case: bool) -> bool:
        """Verifica la corrispondenza di maiuscole/minuscole sul testo trovato."""
        if not case:
            return True
        band = geo.Rect(rect.x0 - 1, rect.y0 - 1, rect.x1 + 1, rect.y1 + 1)
        try:
            found = page.get_text("text", clip=band).strip()
        except Exception:
            return True
        if not found:
            return True
        return needle in found or found in needle

    def _hit_quads(self, page: pymupdf.Page, rect: geo.Rect) -> list[geo.Rect]:
        """Riquadri dei caratteri trovati, per evidenziare bene il testo su piu' righe."""
        out = [geo.Rect(rect)]
        try:
            band = geo.Rect(rect) + (-1, -1, 1, 1)
            blocks = page.get_text("dict", clip=band).get("blocks", [])
            for b in blocks:
                for line in b.get("lines", []):
                    for span in line.get("spans", []):
                        for ch in span.get("chars", []):
                            out.append(geo.Rect(ch["bbox"]))
        except Exception:
            pass
        return out

    def highlight_hits(
        self, needle: str, page_index: int, color: tuple[float, float, float] = (1, 0.85, 0),
        **kw: Any,
    ) -> int:
        """Evidenzia tutte le occorrenze trovate con la ricerca.

        Il colore si dichiara qui e non fra i parametri della ricerca: passarlo
        a ``search`` non accettato e il programma si fermava con un ``TypeError``
        ogni volta che si provava a scegliere il colore dell'evidenziazione.
        """
        hits = [h["rect"] for h in self.search(needle, page_index, **kw)]
        if not hits:
            return 0
        self._mutate(
            "Evidenzia risultati",
            lambda: self._add_highlights(page_index, hits, tuple(color)),
            emit_pages=True,
        )
        return len(hits)

    def _add_highlights(
        self, page_index: int, rects: Sequence[geo.Rect], color: tuple[float, float, float]
    ) -> None:
        page = self.page(page_index)
        for r in rects:
            a = page.add_highlight_annot(geo.Rect(r))
            a.set_colors(stroke=color)
            a.update()

    # ------------------------------------------------------------------ sicurezza

    def permissions(self) -> int:
        try:
            return int(self._require().permissions)
        except Exception:
            return -1

    def authenticate(self, password: str) -> bool:
        try:
            return bool(self._require().authenticate(password))
        except Exception:
            return False

    def encryption_algorithm(self) -> int:
        """Algoritmo di cifratura in uso, letto dal dizionario /Encrypt."""
        campi = self._encrypt_fields()
        if not campi:
            return pymupdf.PDF_ENCRYPT_NONE
        try:
            r = int(campi.get("R", "0").strip() or 0)
            v = int(campi.get("V", "0").strip() or 0)
            n = int(campi.get("Length", "0").strip() or 0)
        except (ValueError, TypeError):
            return pymupdf.PDF_ENCRYPT_AES_256
        if r >= 5:
            return pymupdf.PDF_ENCRYPT_AES_256
        if r == 4 or v >= 4:
            return pymupdf.PDF_ENCRYPT_AES_128
        if v == 2:
            return pymupdf.PDF_ENCRYPT_RC4_128
        if v == 1:
            return pymupdf.PDF_ENCRYPT_RC4_40
        return pymupdf.PDF_ENCRYPT_AES_256 if n >= 256 else pymupdf.PDF_ENCRYPT_RC4_128

    # ---------------------------------------------------- segnalibri e allegati

    def outline(self) -> list[dict[str, Any]]:
        try:
            toc = self._require().get_toc(simple=False) or []
        except Exception:
            return []
        out = []
        for t in toc:
            to = None
            if len(t) > 3 and t[3] is not None:
                try:
                    to = tuple(float(v) for v in t[3])
                except (TypeError, ValueError):
                    to = None
            out.append({"level": t[0], "title": t[1], "page": t[2] - 1, "to": to})
        return out

    def set_outline(self, entries: Sequence[dict[str, Any]]) -> None:
        toc = [[int(e.get("level", 1)), str(e.get("title", "")), int(e.get("page", 0)) + 1] for e in entries]
        self._mutate("Segnalibri", lambda: self._require().set_toc(toc), emit_pages=True)

    def add_bookmark(self, title: str, page: int, level: int = 1) -> None:
        entries = self.outline()
        entries.append({"level": level, "title": title, "page": page})
        self.set_outline(entries)

    def rename_bookmark(self, old_title: str, new_title: str, occurrence: int = 1) -> bool:
        """Rinomina un segnalibro.

        I titoli possono ripetersi: con ``occurrence`` si sceglie quale dei
        segnalibri omonimi rinominare (1 = il primo).
        """
        titolo = str(new_title or "").strip()
        if not titolo:
            raise DocumentError("Il titolo del segnalibro non può essere vuoto.")
        voci = self.outline()
        indici = [i for i, e in enumerate(voci) if e["title"] == old_title]
        if not indici:
            raise DocumentError(
                    tr("Nessun segnalibro chiamato «{nome}».").format(nome=old_title)
                )
        if not (1 <= int(occurrence) <= len(indici)):
            raise DocumentError(
                tr("Sono presenti {quanti} segnalibri chiamati «{nome}».")
                .format(quanti=len(indici), nome=old_title)
            )
        voci[indici[int(occurrence) - 1]]["title"] = titolo
        self.set_outline(voci)
        return True

    def move_bookmark(self, old_title: str, page: int, occurrence: int = 1) -> bool:
        """Sposta un segnalibro su un'altra pagina."""
        voci = self.outline()
        indici = [i for i, e in enumerate(voci) if e["title"] == old_title]
        if not indici:
            raise DocumentError(
                    tr("Nessun segnalibro chiamato «{nome}».").format(nome=old_title)
                )
        if not (1 <= int(occurrence) <= len(indici)):
            raise DocumentError(
                tr("Sono presenti {quanti} segnalibri chiamati «{nome}».")
                .format(quanti=len(indici), nome=old_title)
            )
        if not (0 <= int(page) < self.page_count):
            raise DocumentError(
                tr("La pagina {n} non esiste: il documento ha {totale} pagine.")
                .format(n=int(page) + 1, totale=self.page_count)
            )
        voci[indici[int(occurrence) - 1]]["page"] = int(page)
        self.set_outline(voci)
        return True

    def rename_bookmark_at(self, index: int, new_title: str) -> bool:
        """Rinomina il segnalibro alla posizione indicata nell'elenco."""
        voci = self.outline()
        if not (0 <= int(index) < len(voci)):
            raise DocumentError("Il segnalibro indicato non esiste.")
        titolo = str(new_title or "").strip()
        if not titolo:
            raise DocumentError("Il titolo del segnalibro non può essere vuoto.")
        voci[int(index)]["title"] = titolo
        self.set_outline(voci)
        return True

    def move_bookmark_at(self, index: int, page: int) -> bool:
        """Sposta sulla pagina indicata il segnalibro all'indice dato."""
        voci = self.outline()
        if not (0 <= int(index) < len(voci)):
            raise DocumentError("Il segnalibro indicato non esiste.")
        if not (0 <= int(page) < self.page_count):
            raise DocumentError(
                tr("La pagina {n} non esiste: il documento ha {totale} pagine.")
                .format(n=int(page) + 1, totale=self.page_count)
            )
        voci[int(index)]["page"] = int(page)
        self.set_outline(voci)
        return True

    def remove_bookmark(self, title: str) -> None:
        voci = self.outline()
        if not any(e["title"] == title for e in voci):
            raise DocumentError(
                tr("Nessun segnalibro chiamato «{nome}».").format(nome=title)
            )
        self.set_outline([e for e in voci if e["title"] != title])

    def remove_bookmark_at(self, index: int) -> bool:
        """Rimuove il segnalibro all'indice indicato nell'elenco.

        Rimuovere per titolo non basta più: con l'outline gerarchico due
        segnalibili possono avere lo stesso nome e il percorso
        «Padre/Figlio» non corrisponde a nessun titolo. L'indice è univoco,
        come per rinomina e spostamento.
        """
        voci = self.outline()
        if not (0 <= int(index) < len(voci)):
            raise DocumentError("Il segnalibro indicato non esiste.")
        voce = voci.pop(int(index))
        # con il segnalibro genitore spariscono anche i figli: lasciarli
        # appesi a un ramo inesistente li renderebbe irraggiungibili
        while voce and voce["level"] > 1:
            if not any(v["level"] == voce["level"] - 1 for v in voci):
                voci = [v for v in voci if not (v["level"] >= voce["level"])]
                break
            voce = next(v for v in voci if v["level"] == voce["level"] - 1)
        self.set_outline(voci)
        return True

    def attachments(self) -> list[dict[str, Any]]:
        """Allegati incorporati nel documento."""
        out = []
        try:
            doc = self._require()
            for name in doc.embfile_names() or ():
                try:
                    info = doc.embfile_info(name) or {}
                except Exception:
                    info = {}
                out.append(
                    {
                        "name": name,
                        "desc": info.get("description", "") or "",
                        "size": int(info.get("size", 0) or 0),
                    }
                )
        except Exception:
            pass
        return out

    def attachment_bytes(self, name: str) -> bytes:
        """Contenuto di un allegato, per nome o indice."""
        return bytes(self._require().embfile_get(name))

    def add_attachment(self, path: str | os.PathLike[str], name: str = "", desc: str = "") -> None:
        """Allega un file al documento, incorporandolo nel PDF."""
        p = Path(path)
        if p.is_dir():
            raise DocumentError(tr("«{nome}» è una cartella, non un file.").format(nome=p.name))
        if not p.is_file():
            raise DocumentError(tr("Il file «{nome}» non esiste.").format(nome=p.name))
        try:
            data = p.read_bytes()
        except OSError as exc:
            raise DocumentError(
                tr("Impossibile leggere «{nome}»: {errore}").format(nome=p.name, errore=exc)
            ) from exc
        self._mutate(
            "Allega file",
            lambda: self._require().embfile_add(name or p.name, data, filename=p.name, desc=desc),
        )

    def remove_attachment(self, name: str) -> None:
        if name not in [a.get("name") for a in self.attachments()]:
            raise DocumentError(tr("Nessun allegato chiamato «{nome}».").format(nome=name))
        self._mutate("Rimuovi allegato", lambda: self._require().embfile_del(name))


# --------------------------------------------------------------------------- helper


#: nome del contenuto marcato con cui si scrive la numerazione delle pagine
PAGE_NUMBER_TAG = b"ScrNum"

_NUMBER_BLOCK_RE = re.compile(
    rb"\s*/" + PAGE_NUMBER_TAG + rb"\s+BMC.*?EMC", re.S
)

#: Quante volte si ritenta un'operazione sul file prima di rinunciarci. Un
#: antivirus o un programma di sincronizzazione possono tenere il file aperto
#: per qualche decimo di secondo, e basta un tentativo per accorgersene.
_TENTATIVI_SU_FILE = 5

#: Se il file da cui il documento e' aperto puo' essere sostituito.
#:
#: Su Linux e macOS si', anche aperto. Su Windows no, e non e' un caso sporadico:
#: MuPDF tiene aperto il file da cui ha aperto il documento per poter salvare
#: in incrementale, e Windows non permette di sostituire un file aperto. Salvare
#: sul file stesso da cui il documento era stato aperto finiva quindi sempre con
#: «Access is denied» e il file non veniva scritto.
_SOSTITUZIONE_DISPONIBILE = os.name != "nt"


def _aspetta(tentativo: int) -> None:
    """Pausa crescente fra un tentativo e l'altro: un blocco breve passa da solo."""
    time.sleep(0.05 * (tentativo + 1))


def _scrivi_su_file_aperto(provvisorio: Path, target: Path) -> None:
    """Scrive il contenuto di ``provvisorio`` dentro ``target``.

    È la via quando il file non si può sostituire. L'handle con cui MuPDF
    tiene aperto ``target`` resta valido: il contenuto e le posizioni degli
    oggetti sono quelli del documento appena riscritto, quindi anche le
    letture successive tornano. Il file resta quello di prima, con il suo
    nome e la sua identità, che è ciò che ci si aspetta da un salvataggio.
    """
    shutil.copyfile(provvisorio, target)


def _sostituisci(provvisorio: Path, target: Path) -> None:
    """Mette ``provvisorio`` al posto di ``target``, o ci scrive dentro.

    Prima si sostituisce, che è l'operazione che non lascia mai il file a
    metà. Se il file è aperto non si può sostituire: si aspetta qualche
    decimo di secondo, si riprova, e poi si scrive dentro. L'ultimo errore
    non viene tacito, perché un file che sembra salvato e che invece è
    quello di prima è peggio di un salvataggio dichiarato fallito.
    """
    if _SOSTITUZIONE_DISPONIBILE:
        for tentativo in range(_TENTATIVI_SU_FILE):
            try:
                provvisorio.replace(target)
                return
            except PermissionError:
                if tentativo + 1 < _TENTATIVI_SU_FILE:
                    _aspetta(tentativo)
    for tentativo in range(_TENTATIVI_SU_FILE):
        try:
            _scrivi_su_file_aperto(provvisorio, target)
            return
        except PermissionError:
            if tentativo + 1 < _TENTATIVI_SU_FILE:
                _aspetta(tentativo)
    raise DocumentError(
        "il file è aperto da un altro programma e non può essere scritto: "
        "chiudilo e riprova, oppure usa «Salva come…»"
    )


def _escape_pdf_string(text: str) -> bytes:
    """Testo pronto per un operatore PDF ``(...)``."""
    out = bytearray()
    for c in text:
        if c in "()\\":
            out += b"\\" + c.encode("latin-1", "replace")
        elif ord(c) < 32:
            out += b" "
        else:
            out += c.encode("latin-1", "replace")
    return bytes(out)


def _page_number_block(
    testo: str, x: float, y: float, fontsize: float, color: tuple[float, float, float]
) -> bytes:
    """Operatori PDF che scrivono il numero di pagina in un punto preciso."""
    r, g, b = color
    return (
        f"\n/{PAGE_NUMBER_TAG.decode()} BMC\n"
        f"BT /Helv {fontsize:g} Tf {r:g} {g:g} {b:g} rg "
        f"1 0 0 1 {x:g} {y:g} Tm ({_escape_pdf_string(testo).decode('latin-1')}) Tj ET\n"
        f"EMC\n"
    ).encode("latin-1", "replace")


def _append_page_content(doc: pymupdf.Document, index: int, blocco: bytes) -> bool:
    """Aggiunge operatori in coda al contenuto di una pagina."""
    page = doc[index]
    xrefs = page.get_contents()
    if not xrefs:
        xref = doc.get_new_xref()
        doc.update_object(xref, "<<>>")
        doc.update_stream(xref, blocco)
        page.clean_contents()
        contents = page.get_contents()
        if not contents:
            doc.xref_set_key(page.xref, "Contents", f"{xref} 0 R")
            return True
        xrefs = contents
    ultimo = xrefs[-1]
    try:
        raw = doc.xref_stream(ultimo)
    except Exception:
        return False
    doc.update_stream(ultimo, raw + blocco if raw.endswith(b"\n") else raw + b"\n" + blocco)
    return True


def _has_page_number(doc: pymupdf.Document, index: int) -> bool:
    for xref in doc[index].get_contents() or ():
        try:
            if b"/" + PAGE_NUMBER_TAG + b" BMC" in doc.xref_stream(xref):
                return True
        except Exception:
            continue
    return False


def _strip_page_numbers(doc: pymupdf.Document, index: int) -> int:
    tolte = 0
    for xref in doc[index].get_contents() or ():
        try:
            raw = doc.xref_stream(xref)
        except Exception:
            continue
        nuovo, n = _NUMBER_BLOCK_RE.subn(b"", raw)
        if n:
            doc.update_stream(xref, nuovo)
            tolte += n
    return tolte


def _ricodifica_immagine(
    px: pymupdf.Pixmap, fattore: float, qualita: int
) -> tuple[bytes, int, int] | None:
    """Ridimensiona e ricodifica in JPEG un'immagine.

    Restituisce i byte JPEG e le nuove dimensioni, oppure ``None`` se non
    conviene procedere.
    """
    from PIL import Image

    w = max(1, int(round(px.width * fattore)))
    h = max(1, int(round(px.height * fattore)))
    if w < 2 or h < 2:
        return None
    try:
        grezzo = bytes(px.samples)
        if px.n == 1:
            immagine = Image.frombytes("L", (px.width, px.height), grezzo)
        else:
            immagine = Image.frombytes("RGB", (px.width, px.height), grezzo)
    except Exception:
        return None
    if (w, h) != immagine.size:
        immagine = immagine.resize((w, h), Image.LANCZOS)
    buf = io.BytesIO()
    try:
        immagine.save(buf, "JPEG", quality=qualita, optimize=True)
    except Exception:
        return None
    dati = buf.getvalue()
    if not dati:
        return None
    return dati, w, h


def _normalize_field_value(widget: pymupdf.Widget, value: Any) -> Any:
    """Adegua il valore ai vincoli del campo.

    PyMuPDF non fa rispettare ``/MaxLen``: salvare un valore troppo lungo
    produrrebbe un file in cui il campo mostra una cosa e gli altri lettori
    un'altra. Qui il valore viene troncato come fa Acrobat.
    """
    tipo = getattr(widget, "field_type", None)
    if tipo == pymupdf.PDF_WIDGET_TYPE_TEXT:
        testo = "" if value is None else str(value)
        massimo = int(getattr(widget, "text_maxlen", 0) or 0)
        if massimo > 0 and len(testo) > massimo:
            return testo[:massimo]
        return testo
    if tipo == pymupdf.PDF_WIDGET_TYPE_CHECKBOX:
        return bool(value)
    return value


def _quad_of(rect: geo.Rect) -> pymupdf.Quad:
    """Quad di testo da un rettangolo.

    Gli angoli di ``Quad`` sono parametri solo nominali e vanno passati come
    punti espliciti: non si puo' costruire da un ``Rect``.
    """
    r = geo.Rect(rect)
    return pymupdf.Quad(
        ul=pymupdf.Point(r.x0, r.y0),
        ur=pymupdf.Point(r.x1, r.y0),
        ll=pymupdf.Point(r.x0, r.y1),
        lr=pymupdf.Point(r.x1, r.y1),
    )


def _add_text_marker(page: pymupdf.Page, kind: str, rect: geo.Rect, quads: list[geo.Rect]) -> Any:
    """Crea un marcatore di testo (sottolineatura, barratura, onda)."""
    markers = [_quad_of(q) for q in (quads or [rect])]
    if kind == "underline":
        return page.add_underline_annot(quads=markers)
    if kind == "strikeout":
        return page.add_strikeout_annot(quads=markers)
    return page.add_squiggly_annot(quads=markers)


def _as_rect(rect: geo.Rect | BoxLike) -> geo.Rect:
    """Accetta un Rect di PyMuPDF o un QRectF di Qt e restituisce geo.Rect.

    Il nucleo non dipende da Qt: basta che l'oggetto abbia x/y/width/height.
    """
    if isinstance(rect, geo.Rect):
        return rect
    return geo.Rect(rect.x(), rect.y(), rect.x() + rect.width(), rect.y() + rect.height())


def _span_color(value: Any) -> tuple[float, float, float]:
    """Colore di uno span di testo come terna 0-1.

    PyMuPDF puo' restituire il colore come intero RGB, come terna di float o come
    stringa CSS: qui viene normalizzato in ogni caso.
    """
    if isinstance(value, (tuple, list)) and len(value) >= 3:
        return (float(value[0]), float(value[1]), float(value[2]))
    if isinstance(value, int):
        return ((value >> 16 & 255) / 255, (value >> 8 & 255) / 255, (value & 255) / 255)
    if isinstance(value, str) and value.startswith("#"):
        try:
            v = value.lstrip("#")
            if len(v) == 6:
                return tuple(int(v[i : i + 2], 16) / 255 for i in (0, 2, 4))
        except ValueError:
            pass
    return (0.0, 0.0, 0.0)


def _pdf_escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _stile_da_riquadro(page: pymupdf.Page, rect: geo.Rect) -> tuple[float, int, str]:
    """Corpo, colore e font del testo che copre il riquadro indicato.

    Serve a sostituire una parola mantenendone l'aspetto. Il font viene
    ricondotto a uno dei volti base del PDF: solo quelli si possono riscrivere
    senza incorporare un font nuovo nel documento.
    """
    banda = geo.Rect(
        0, max(0, rect.y0 - 3), page.rect.width, min(page.rect.height, rect.y1 + 3)
    )
    try:
        pezzi = page.get_text("dict", clip=banda)
    except Exception:
        return 11.0, 0, "helv"
    for blocco in pezzi.get("blocks", []):
        for riga in blocco.get("lines", []):
            for span in riga.get("spans", []):
                corpo = float(span.get("size", 11.0) or 11.0)
                nome = str(span.get("font", "") or "")
                alias = textlayout.BASE_FONTS.get(nome)
                if alias is None:
                    alias = nome.lower()
                    if alias not in _PDF_BASE_ALIASES:
                        alias = _pdf_fontname(corpo)
                return corpo, int(span.get("color", 0) or 0), alias
    return 11.0, 0, "helv"


#: Alias dei font base del PDF che ``insert_text`` sa usare senza incorporare
#: un font nuovo nel documento.
_PDF_BASE_ALIASES = frozenset(
    (
        "helv", "hebo", "hebi",
        "tiro", "tibo", "tiit",
        "cour", "cobo", "cobi",
        "symbol", "zadb",
    )
)


def _pdf_fontname(size: float) -> str:
    """Sceglie un font base coerente con la dimensione del testo."""
    if size >= 18:
        return "tiro"
    if size >= 13:
        return "tiro" if size >= 16 else "helv"
    if size <= 7.5:
        return "cour"
    return "helv"


def _view_rotation_matrix(scale: float, angle: int, width: float, height: float) -> pymupdf.Matrix:
    """Matrice di rendering con scala e rotazione di visualizzazione.

    ``get_pixmap`` applica la matrice dopo la rotazione della pagina, quindi qui
    la rotazione richiesta e' espressa sulla tela gia' ruotata. Le formule sono
    state verificate byte per byte contro ``Page.set_rotation``.
    """
    angle %= 360
    if angle == 0:
        return pymupdf.Matrix(scale, scale)
    if angle == 90:
        return pymupdf.Matrix(0, scale, -scale, 0, scale * height, 0)
    if angle == 180:
        return pymupdf.Matrix(-scale, 0, 0, -scale, scale * width, scale * height)
    return pymupdf.Matrix(0, -scale, scale, 0, 0, scale * width)


def _set_line_ends(doc: pymupdf.Document, xref: int, end_arrow: bool = True,
                   start_arrow: bool = False, color: str = "[0 0 0]") -> None:
    """Imposta ``/LE`` per disegnare le punte di una freccia.

    Il dizionario di bordo usa ``/S /R`` (punta chiusa) sulla punta e ``/S /N``
    (nessuna) sull'altra estremita'.
    """

    def border(arrow: bool) -> str:
        s = "/R" if arrow else "/N"
        return f"<< /Type /Border /S {s} /Len 0 /C {color} >>"

    doc.xref_set_key(xref, "LE", f"[{border(start_arrow)} {border(end_arrow)}]")


def _annot_vertices(annot: Any) -> list[tuple[float, float]]:
    """Vertici di un'annotazione, se disponibili in questa versione."""
    try:
        verts = annot.vertices
    except Exception:
        return []
    if not verts:
        return []
    try:
        return [(float(v[0]), float(v[1])) for v in verts]
    except Exception:
        return []


def _chiavi_span(page: pymupdf.Page) -> set[tuple]:
    """Identificatori dei tratti di testo gia' presenti nella pagina.

    Serve a distinguere il testo appena inserito da quello che c'era: e' la
    via piu' sicura perche' MuPDF continua a riportare subito il contenuto
    nuovo, senza bisogno di ricaricare la pagina.
    """
    chiavi: set[tuple] = set()
    for blocco in page.get_text("dict").get("blocks", []):
        for riga in blocco.get("lines", []):
            for span in riga.get("spans", []):
                b = span["bbox"]
                chiavi.add((
                    round(float(b[0]), 1), round(float(b[1]), 1),
                    round(float(b[2]), 1), round(float(b[3]), 1),
                    str(span.get("text", "")),
                ))
    return chiavi


def _sottolinea(
    page: pymupdf.Page,
    gia_presenti: set[tuple],
    color: tuple[float, float, float],
    fontsize: float,
    opacity: float = 1.0,
) -> None:
    """Traccia la sottolineatura sotto i tratti di testo comparsi di fresco.

    ``insert_textbox`` non ha un modo per sottolineare, quindi le righe
    vengono disegnate sui riquadri che lo stesso MuPDF ha misurato: le
    posizioni sono quindi esatte anche con allineamento o rotazione.
    """
    spessore = max(0.5, float(fontsize) * 0.05)
    distanza = max(0.6, float(fontsize) * 0.08)
    for blocco in page.get_text("dict").get("blocks", []):
        for riga in blocco.get("lines", []):
            for span in riga.get("spans", []):
                b = span["bbox"]
                chiave = (
                    round(float(b[0]), 1), round(float(b[1]), 1),
                    round(float(b[2]), 1), round(float(b[3]), 1),
                    str(span.get("text", "")),
                )
                if chiave in gia_presenti or float(b[2]) - float(b[0]) < 0.2:
                    continue
                y = float(b[3]) + distanza
                page.draw_line(
                    (float(b[0]), y), (float(b[2]), y),
                    color=color, width=spessore, stroke_opacity=opacity, overlay=True,
                )


def _sottolinea_layout(
    page: pymupdf.Page,
    rect: geo.Rect,
    text: str,
    fontsize: float,
    color: tuple[float, float, float],
    fontname: str = "helv",
) -> None:
    """Sottolinea un blocco di testo con il modello di impaginazione interno.

    Serve per il testo dentro un'annotazione, dove le misure del rendering
    non sono leggibili dalla pagina. Le righe sono tracciate sotto l'area
    occupata dal testo, riga per riga.
    """
    righe = textlayout.wrap(text, fontname, fontsize, max(20.0, rect.width - 4.0))
    passo = textlayout.line_height_for(fontsize, fontname)
    discesa = abs(textlayout.load_font(fontname).descender) * fontsize
    spessore = max(0.5, float(fontsize) * 0.05)
    y = rect.y0 + discesa * 0.6
    for riga in righe:
        if riga.strip():
            larghezza = textlayout.text_width(riga, fontname, fontsize)
            page.draw_line(
                (rect.x0 + 2, y), (rect.x0 + 2 + larghezza, y),
                color=color, width=spessore, overlay=True,
            )
        y += passo


def _group_points(points: Sequence[tuple[float, float]]) -> list[list[tuple[float, float]]]:
    """Raggruppa punti in tratti, spezzando dove il salto e netto."""
    strokes: list[list[tuple[float, float]]] = []
    cur: list[tuple[float, float]] = []
    for p in points:
        if cur:
            dx, dy = p[0] - cur[-1][0], p[1] - cur[-1][1]
            if dx * dx + dy * dy > 1200:
                strokes.append(cur)
                cur = []
        cur.append(p)
    if cur:
        strokes.append(cur)
    return strokes


def _as_image_stream(source: Any) -> Any:
    """Normalizza l'origine di un'immagine in un flusso accettato da PyMuPDF.

    ``Page.insert_image`` con ``stream=`` accetta solo oggetto simile a byte:
    un percorso va quindi letto e aperto come flusso.
    """
    if isinstance(source, pymupdf.Pixmap):
        return source.tobytes("png")
    if isinstance(source, (bytes, bytearray, memoryview)):
        return bytes(source)
    if isinstance(source, io.BytesIO):
        source.seek(0)
        return source
    if isinstance(source, (str, os.PathLike)):
        p = Path(source)
        if not p.exists():
            raise DocumentError(tr("Immagine non trovata: {file}").format(file=p))
        return io.BytesIO(p.read_bytes())
    if hasattr(source, "read"):
        try:
            source.seek(0)
        except Exception:
            pass
        # va riletto in memoria: PyMuPDF accetta solo BytesIO
        return io.BytesIO(source.read())
    raise DocumentError("Formato di immagine non supportato.")


def _image_size(source: Any) -> tuple[int, int] | None:
    """Dimensioni in pixel di un'immagine, senza caricarla interamente."""
    try:
        if isinstance(source, pymupdf.Pixmap):
            return source.width, source.height
        stream = source
        pos = 0
        if isinstance(source, (bytes, bytearray)):
            stream = io.BytesIO(bytes(source))
        elif hasattr(source, "read") and hasattr(source, "seek"):
            pos = source.tell()
            source.seek(0)
        info = pymupdf.Pixmap(stream)
        size = (info.width, info.height)
        if hasattr(source, "seek"):
            source.seek(pos)
        return size
    except Exception:
        try:
            if hasattr(source, "seek"):
                source.seek(0)
        except Exception:
            pass
        return None


def _whole_word(page: pymupdf.Page, rect: geo.Rect, needle: str, case: bool) -> bool:
    """True se la corrispondenza cade su parole intere.

    Il confronto era ``needle in testo``, cioe' una ricerca di sotto-stringa:
    tornava sempre vero e l'opzione «parola intera» della ricerca non
    filtrava nulla, «ore» trovava anche dentro «Lorem». Qui si prendono le
    parole che toccano il riquadro trovato e si confrontano con il testo
    cercato: sono parole intere per costruzione.
    """
    parole: list[str] = []
    for w in page.get_text("words"):
        box = geo.Rect(w[0], w[1], w[2], w[3])
        # sovrapposizione anche parziale: il riquadro della corrispondenza
        # tocca quasi sempre i caratteri di confine
        if box.x1 < rect.x0 - 1 or box.x0 > rect.x1 + 1:
            continue
        if box.y1 < rect.y0 - 2 or box.y0 > rect.y1 + 2:
            continue
        parole.append(str(w[4]))
    testo = " ".join(parole)
    if case:
        return testo == needle
    return testo.lower() == needle.lower()


def load_document(path: str, password: str = "") -> Document:
    """Apre un documento e lo restituisce pronto all'uso."""
    d = Document()
    d.open(path, password)
    return d
