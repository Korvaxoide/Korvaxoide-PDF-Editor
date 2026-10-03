"""Misurazione e impaginazione del testo.

``Page.insert_textbox`` scrive il testo anche quando il contenuto non entra nel
riquadro, quindi non puo' essere usato come semplice sonda. Qui il testo viene
misurato con ``pymupdf.Font`` e impaginato a mano: serve per calcolare l'altezza
necessaria, l'adattamento automatico e l'anteprima delle caselle.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass

import pymupdf

# Font di base disponibili in ogni PDF senza incorporamento.
BASE_FONTS: dict[str, str] = {
    "Helvetica": "helv",
    "Helvetica-Bold": "hebo",
    "Helvetica-Oblique": "hebi",
    "Helvetica-BoldOblique": "hebi",
    "Times-Roman": "tiro",
    "Times-Bold": "tibo",
    "Times-Italic": "tiit",
    "Times-BoldItalic": "tibo",
    "Courier": "cour",
    "Courier-Bold": "cobo",
    "Courier-Oblique": "cobi",
    "Symbol": "symbol",
    "ZapfDingbats": "zadb",
}

SERIF_FONTS = ("tiro", "tibo", "tiit", "tibo", "tiro")
MONO_FONTS = ("cour", "cobo", "cobi", "cour")

#: I font che un campo modulo può davvero usare, con il nome da scrivere
#: nella ``/DA``. Nella ``/DA`` di un widget MuPDF accetta solo i volti base
#: del PDF: ogni altro alias ricade in silenzio su ``/Helv``, quindi
#: offrire grassetti e corsivi a un campo significherebbe far scegliere una
#: variante che il motore scarterebbe scrivendo un altro font.
FIELD_FONTS: tuple[tuple[str, str], ...] = (
    ("Helvetica", "Helv"),
    ("Times", "TiRo"),
    ("Courier", "Cour"),
    ("Symbol", "Symbol"),
    ("ZapfDingbats", "ZaDb"),
)


def font_da_name(name: str) -> str:
    """Il nome da scrivere nella ``/DA`` di un campo modulo.

    Accetta il nome in ``/DA`` (``TiRo``), l'alias MuPDF (``tiro``), il nome
    esteso (``Times-Roman``) e quello leggibile che mostrano le finestre
    (``Times``), e riconduce tutto al volto base della famiglia: scegliere
    «Times corsivo» dà Times, non Helvetica come faceva prima la lista fissa,
    che ammetteva quattro nomi e scartava tutto il resto.
    """
    grezzo = str(name).strip()
    chiave = BASE_FONTS.get(grezzo, grezzo).lower()
    if chiave in ("helv", "hebo", "hebi", "helvetica"):
        return "Helv"
    if chiave in ("tiro", "tibo", "tiit", "times", "timesnewroman", "times-roman"):
        return "TiRo"
    if chiave in ("cour", "cobo", "cobi", "courier", "couriernew"):
        return "Cour"
    if chiave == "symbol":
        return "Symbol"
    if chiave in ("zadb", "zapfdingbats"):
        return "ZaDb"
    return "Helv"


@functools.lru_cache(maxsize=64)
def load_font(name: str) -> pymupdf.Font:
    """Carica un font di base (con cache)."""
    key = BASE_FONTS.get(name, name)
    try:
        return pymupdf.Font(key)
    except Exception:
        return pymupdf.Font("helv")


def is_mono(name: str) -> bool:
    return BASE_FONTS.get(name, name) in MONO_FONTS


def is_serif(name: str) -> bool:
    return BASE_FONTS.get(name, name) in SERIF_FONTS


def text_width(text: str, fontname: str, fontsize: float) -> float:
    """Larghezza di una stringa in punti."""
    if not text:
        return 0.0
    try:
        return load_font(fontname).text_length(text, fontsize)
    except Exception:
        return len(text) * fontsize * 0.5


@dataclass
class Layout:
    """Risultato dell'impaginazione di un blocco di testo."""

    lines: list[str]
    line_height: float
    width: float
    height: float
    overflow: bool = False

    @property
    def line_count(self) -> int:
        return len(self.lines)


def wrap(text: str, fontname: str, fontsize: float, width: float) -> list[str]:
    """Manda a capo il testo rispettando i confini espliciti e la larghezza."""
    if width <= 0:
        return text.split("\n")
    out: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw == "":
            out.append("")
            continue
        if text_width(raw, fontname, fontsize) <= width:
            out.append(raw)
            continue
        words = raw.split(" ")
        cur = ""
        for word in words:
            trial = word if not cur else f"{cur} {word}"
            if text_width(trial, fontname, fontsize) <= width:
                cur = trial
                continue
            if cur:
                out.append(cur)
            # Parola singola piu' larga della riga: si spezza per carattere.
            if text_width(word, fontname, fontsize) > width:
                chunk = ""
                for ch in word:
                    if text_width(chunk + ch, fontname, fontsize) <= width or not chunk:
                        chunk += ch
                    else:
                        out.append(chunk)
                        chunk = ch
                cur = chunk
            else:
                cur = word
        if cur:
            out.append(cur)
    return out


# Il modello di altezza e' stato ricavato misurando l'altezza occupata da
# insert_textbox su tutti i font di base: l'avanzamento di riga e' esattamente
# ascender + |descender| del font, mentre la prima riga ha in piu' la discesa.
def _font_extent(fontname: str) -> tuple[float, float]:
    """(ascesa, discesa) normalizzate del font."""
    try:
        f = load_font(fontname)
        return abs(f.ascender), abs(f.descender)
    except Exception:
        return 0.905, 0.212


def line_height_for(fontsize: float, fontname: str, factor: float | None = None) -> float:
    """Avanzamento di riga come lo calcola MuPDF in ``insert_textbox``."""
    if factor and factor > 0:
        return fontsize * factor
    asc, desc = _font_extent(fontname)
    return (asc + desc) * fontsize


def layout_text(
    text: str,
    fontname: str,
    fontsize: float,
    width: float,
    height: float | None = None,
    line_factor: float | None = None,
) -> Layout:
    """Impagina il testo e indica se eccede l'altezza disponibile."""
    lines = wrap(text, fontname, fontsize, width)
    lh = line_height_for(fontsize, fontname, line_factor)
    total = block_height_for(len(lines), fontsize, fontname, line_factor)
    overflow = height is not None and total > height + 0.01
    return Layout(lines=lines, line_height=lh, width=width, height=total, overflow=overflow)


def block_height_for(
    n_lines: int, fontsize: float, fontname: str = "helv", line_factor: float | None = None
) -> float:
    """Altezza totale di un blocco di ``n_lines`` righe."""
    if n_lines <= 0:
        return 0.0
    lh = line_height_for(fontsize, fontname, line_factor)
    return lh * n_lines + _font_extent(fontname)[1] * fontsize


def required_size(
    text: str, fontname: str, fontsize: float, width: float, line_factor: float | None = None
) -> tuple[float, float]:
    """Dimensioni minime (larghezza, altezza) per contenere il testo."""
    lay = layout_text(text, fontname, fontsize, width, line_factor=line_factor)
    longest = max((text_width(ln, fontname, fontsize) for ln in lay.lines), default=0.0)
    return longest, lay.height


def fit_fontsize(
    text: str,
    fontname: str,
    fontsize: float,
    width: float,
    height: float,
    min_size: float = 4.0,
    line_factor: float | None = None,
) -> float:
    """Il corpo piu' grande (non superiore a ``fontsize``) che fa entrare il testo."""
    size = float(fontsize)
    while size > min_size:
        if not layout_text(text, fontname, size, width, height, line_factor).overflow:
            return size
        size -= 0.5
    return min_size


def baseline_offset(fontname: str, fontsize: float) -> float:
    """Distanza dalla linea di base al bordo superiore del rigo."""
    try:
        return load_font(fontname).ascender * fontsize
    except Exception:
        return fontsize * 0.8


def text_rects(
    text: str, fontname: str, fontsize: float, box: pymupdf.Rect, align: int = 0
) -> list[pymupdf.Rect]:
    """Riquadri occupati da ogni riga, utili per evidenziare le corrispondenze."""
    lay = layout_text(text, fontname, fontsize, box.width)
    asc = baseline_offset(fontname, fontsize)
    out = []
    y = box.y0
    for line in lay.lines:
        w = text_width(line, fontname, fontsize)
        if align == 1:
            x = box.x0 + (box.width - w) / 2
        elif align == 2:
            x = box.x1 - w
        else:
            x = box.x0
        out.append(pymupdf.Rect(x, y, x + w, y + lay.line_height))
        y += lay.line_height
    return out


def font_display_name(name: str) -> str:
    """Nome leggibile del font."""
    for pretty, key in BASE_FONTS.items():
        if key == name:
            return pretty
    return name
