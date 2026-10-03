"""Libreria delle firme salvate.

Le firme vengono conservate come PNG trasparenti piu' i dati vettoriali dei
tratti, cosi' si possono rieditare (cambiare penna, dimensione) senza perdere
qualita'. Ogni voce occupa un file nella cartella dati dell'utente.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from ..core.settings import data_dir
from . import bgremove, render, strokes as sk, typed


def library_dir() -> Path:
    d = data_dir() / "signatures"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        # cartella non scrivibile o disco pieno: si dice perché, invece di
        # lasciar emergere un PermissionError da metà del salvataggio
        raise SignatureLibraryError(
            f"Non si può usare la cartella delle firme ({d}): {exc}. "
            "La libreria non è raggiungibile."
        ) from exc
    return d


def index_path() -> Path:
    return library_dir() / "index.json"


class SignatureLibraryError(Exception):
    """La libreria delle firme non è utilizzabile (cartella non scrivibile)."""


@dataclass
class SignatureEntry:
    """Una firma salvata nella libreria."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    source: str = "draw"        # draw | typed | image
    created: float = field(default_factory=time.time)
    width: int = 0
    height: int = 0
    text: str = ""
    pen_color: str = "#101828"
    pen_width: float = 2.6
    font_path: str = ""
    data_file: str = ""
    strokes_file: str = ""

    @property
    def display_name(self) -> str:
        return self.name or (self.text or f"Firma {self.id[:6]}")


class SignatureLibrary:
    """Elenco delle firme salvate, con persistenza su disco."""

    def __init__(self, folder: Path | None = None) -> None:
        self.folder = folder or library_dir()
        self.folder.mkdir(parents=True, exist_ok=True)
        self.entries: list[SignatureEntry] = []
        self.load()

    # ------------------------------------------------------------- persistenza

    def load(self) -> None:
        p = index_path() if self.folder == library_dir() else self.folder / "index.json"
        self.entries = []
        if not p.exists():
            return
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        campi = set(SignatureEntry.__dataclass_fields__)
        for item in raw if isinstance(raw, list) else []:
            if not isinstance(item, dict):
                continue
            try:
                # le chiavi in più vengono scartate invece di far fallire
                # l'intera voce: una firma salvata da una versione futura (o
                # modificata a mano) spariva dall'elenco pur avendo il PNG su
                # disco, e la successiva riscrittura dell'indice la perdeva per
                # sempre
                self.entries.append(
                    SignatureEntry(**{k: v for k, v in item.items() if k in campi})
                )
            except TypeError:
                continue
        # una voce senza file non è utilizzabile, ma non viene scartata in
        # silenzio: resterebbe nell'indice e verrebbe riscritta al prossimo
        # salvataggio, sparendo per sempre
        self.entries = [
            e for e in self.entries if e.data_file and (self.folder / e.data_file).exists()
        ]

    def save(self) -> None:
        p = index_path() if self.folder == library_dir() else self.folder / "index.json"
        try:
            p.write_text(
                json.dumps([asdict(e) for e in self.entries], indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass

    # ----------------------------------------------------------------- accesso

    def add_png(self, image: Image.Image, name: str = "", source: str = "draw", **meta: Any) -> SignatureEntry:
        """Salva un'immagine di firma (gia' con sfondo rimosso)."""
        entry = SignatureEntry(
            name=name,
            source=source,
            width=image.width,
            height=image.height,
            data_file=f"{uuid.uuid4().hex}.png",
            **{k: v for k, v in meta.items() if k in SignatureEntry.__dataclass_fields__},
        )
        rgba = image if image.mode == "RGBA" else image.convert("RGBA")
        try:
            rgba.save(self.folder / entry.data_file, format="PNG", optimize=True)
        except OSError as exc:
            # prima l'errore usciva crudo dal dialogo «Salva in libreria» e
            # chiudeva la finestra; ora dice cosa è andato storto
            raise SignatureLibraryError(
                f"Non si è potuto salvare la firma: {exc}"
            ) from exc
        self.entries.append(entry)
        self.save()
        return entry

    def add_canvas(
        self, canvas: sk.SignatureCanvas, name: str = "", scale: float = 2.0
    ) -> SignatureEntry:
        """Salva una firma disegnata, conservando anche i tratti vettoriali."""
        img = render.render_strokes(canvas, scale=scale)
        entry = self.add_png(
            img,
            name=name,
            source="draw",
            pen_color=_hex(canvas.default_style.color),
            pen_width=canvas.default_style.width,
        )
        entry.strokes_file = f"{entry.id}.strokes.json"
        canvas.to_dict()
        try:
            (self.folder / entry.strokes_file).write_text(
                json.dumps(canvas.to_dict()), encoding="utf-8"
            )
        except OSError:
            entry.strokes_file = ""
        self.save()
        return entry

    def add_typed(self, text: str, style: typed.TypedStyle, name: str = "") -> SignatureEntry:
        """Salva una firma digitata con la tastiera."""
        img = typed.render_typed(text, style)
        entry = self.add_png(
            img,
            name=name or text,
            source="typed",
            text=text,
            font_path=style.font_path,
            pen_color=_hex(style.color),
            pen_width=style.size,
        )
        self.save()
        return entry

    def image(self, entry: SignatureEntry) -> Image.Image | None:
        p = self.folder / entry.data_file
        if not p.exists():
            return None
        try:
            return Image.open(p).convert("RGBA")
        except OSError:
            return None

    def canvas(self, entry: SignatureEntry) -> sk.SignatureCanvas | None:
        """Ricostruisce i tratti vettoriali di una firma disegnata."""
        if not entry.strokes_file:
            return None
        p = self.folder / entry.strokes_file
        if not p.exists():
            return None
        try:
            return sk.SignatureCanvas.from_dict(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return None

    def bytes(self, entry: SignatureEntry) -> bytes:
        img = self.image(entry)
        return render.to_png(img) if img else b""

    def remove(self, entry: SignatureEntry) -> None:
        for name in (entry.data_file, entry.strokes_file):
            if name:
                try:
                    (self.folder / name).unlink(missing_ok=True)
                except OSError:
                    pass
        self.entries = [e for e in self.entries if e.id != entry.id]
        self.save()

    def rename(self, entry: SignatureEntry, name: str) -> None:
        entry.name = name
        self.save()

    def clear(self) -> None:
        for e in list(self.entries):
            self.remove(e)

    def by_id(self, sig_id: str) -> SignatureEntry | None:
        return next((e for e in self.entries if e.id == sig_id), None)

    def __len__(self) -> int:
        return len(self.entries)


def _hex(color: tuple[int, int, int]) -> str:
    r, g, b = color[:3]
    return f"#{r:02x}{g:02x}{b:02x}"


# ------------------------------------------------------------------ rimozione bg


def prepare_image(
    image: Image.Image, settings: bgremove.RemovalSettings | None = None
) -> Image.Image:
    """Applica la rimozione dello sfondo a un'immagine importata dall'utente."""
    return bgremove.remove_background(image, settings or bgremove.RemovalSettings())
