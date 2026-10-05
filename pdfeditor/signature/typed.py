"""Firma scritta con la tastiera, resa in stile manoscritto.

Scrivere con la tastiera produce testo in un font standard, che non somiglia a
una firma. Qui ogni carattere viene reso singolarmente e sottoposto a piccole
deformazioni (inclinazione, rotazione, oscillazione della base, variazione delle
dimensioni) con uno schema deterministico: il risultato ha l'aspetto di una
scrittura manuale senza dipendere da font calligrafici con licenza incerta.

Se l'utente dispone di un vero font calligrafico puo' indicarlo: in tal caso il
testo viene reso normalmente e si applica solo una lieve inclinazione.
"""

from __future__ import annotations

import math
import os
import random
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont

from . import bgremove

Point = tuple[float, float]


@dataclass
class TypedStyle:
    """Aspetto della firma digitata."""

    font_path: str = ""
    size: float = 88.0
    color: tuple[int, int, int] = (16, 24, 40)
    slant: float = 0.22          # inclinazione corsiva (0 = nessuna)
    wobble: float = 0.030        # oscillazione verticale della base
    rotate: float = 3.2          # rotazione massima per carattere (gradi)
    size_variation: float = 0.06  # variazione delle dimensioni
    spacing: float = -0.02       # spaziatura extra (frazione della dimensione)
    ascender_height: float = 1.0  # quanto sono alte le lettere alte rispetto alla x
    seed: int = 7
    transparent: bool = True


def font_dirs() -> list[Path]:
    """Cartelle in cui cercare i font di sistema."""
    home = Path.home()
    if sys.platform.startswith("win"):
        dirs = [Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts", home / "AppData/Local/Microsoft/Windows/Fonts"]
    elif sys.platform == "darwin":
        dirs = [Path("/System/Library/Fonts"), Path("/Library/Fonts"), home / "Library/Fonts"]
    else:
        dirs = [
            Path("/usr/share/fonts"),
            Path("/usr/local/share/fonts"),
            home / ".fonts",
            home / ".local/share/fonts",
        ]
    return [d for d in dirs if d.exists()]


# Font che, se disponibili, rendono gia' una scrittura simile a una firma.
SCRIPT_HINTS = (
    "script", "hand", "chancery", "cursive", "brush", "comic", "ink",
    "zapfchancery", "segoeprint", "javatext", "segoesc",
)

#: lettere che un font deve avere per servire una firma scritta a tastiera.
#: Sono le forme pi' comuni nei nomi; senza questo un font di scrittura antica
#: (che nel nome contiene «script») finiva in testa alla lista e il nome
#: digitato usciva fatto di quadratini.
LETTERE_FIRMA = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzàèéìòù"


def ha_lettere(path: str, caratteri: str = LETTERE_FIRMA, minimo: int = 40) -> bool:
    """True se il font contiene davvero le lettere richieste.

    Il nome del file dice «script» ma il font può essere una scrittura antica
    priva delle lettere latine: in quel caso il testo esce come una fila di
    rettangoli. Qui si guarda la copertura re dei glifi.

    ``minimo`` è una percentuale: va confrontata con il numero di caratteri
    chiesti. Con ``min`` il confronto valeva sempre vero e il controllo si
    riduceva a «almeno metà dei caratteri», cioè il 34% invece del 40%.
    """
    try:
        font = pymupdf.Font(fontfile=path)
    except Exception:
        return False
    richiesti = [c for c in caratteri]
    if not richiesti:
        return True
    presenti = sum(1 for c in richiesti if font.has_glyph(ord(c)))
    soglia = max(1, (len(richiesti) * max(0, min(minimo, 100))) // 100)
    return presenti >= soglia


def list_fonts(include_scripts: bool = True) -> list[dict[str, object]]:
    """Elenco dei font disponibili, con i calligrafici in evidenza.

    I font che non hanno le lettere latine restano in fondo, non in testa: sono
    inutili per una firma e vengono scambiati per un errore del programma.

    Ogni voce è una copia: la ricerca è in cache e va riutilizzata, ma una voce
    restituita non può essere quella dell'archivio, altrimenti un chiamante che
    la modifica (per esempio aggiungendo un'etichetta) scriverebbe dentro la
    cache e il secondo chiamante troverebbe il font diversamente.
    """
    return [dict(voce) for voce in _elenco_font(include_scripts)]


def svuota_cache_font() -> None:
    """Dimentica i font trovati, per rivederli dopo averne installati di nuovi.

    La ricerca è costosa — apre ogni font con MuPDF per guardare le lettere che
    ha — quindi il risultato si tiene per la sessione. Un font installato a
    programma aperto non compare nelle finestre successive: si chiama questa e la
    ricerca ricomincia. Il programma non lo chiama da solo, perché installare un
    font mentre si lavora è rarissimo e la ricerca costa circa un secondo.
    """
    _elenco_font.cache_clear()


@lru_cache(maxsize=4)
def _elenco_font(include_scripts: bool) -> tuple[dict[str, object], ...]:
    """I font trovati, una volta sola per ogni modo di ricerca.

    Il risultato non cambia mentre il programma gira, e il calcolo è pesante:
    su una macchina con i font di sistema sono qualche centinaio di file, e per
    ognuno `ha_lettere` apre il font in MuPDF. Senza cache, aprire la finestra
    della firma costava due scansioni (l'elenco e il font predefinito che lo
    richiede) e ogni firma digitata senza percorso valido ne chiedeva una terza
    a ogni ridisegno.
    """
    found: dict[str, dict[str, object]] = {}
    exts = (".ttf", ".otf", ".ttc")
    for d in font_dirs():
        try:
            for p in d.rglob("*"):
                if p.suffix.lower() not in exts:
                    continue
                low = p.name.lower()
                script = any(h in low for h in SCRIPT_HINTS)
                if not script and not include_scripts:
                    continue
                entry = found.setdefault(
                    str(p),
                    {"path": str(p), "name": p.stem, "script": script},
                )
                entry["script"] = bool(entry["script"]) or script
        except (OSError, PermissionError):
            continue
    for entry in found.values():
        entry["latino"] = ha_lettere(str(entry["path"]))
    out = list(found.values())
    # nell'ordine: calligrafici utilizzabili, altri utilizzabili, poi il resto
    out.sort(
        key=lambda e: (
            not (e["script"] and e["latino"]),
            not e["latino"],
            str(e["name"]).lower(),
        )
    )
    return tuple(out)


def pick_default_font() -> str:
    """Font predefinito: un calligrafico che abbia le lettere, altrimenti un serif.

    Il font scelto deve poter scrivere il nome: molti font con «script» nel nome
    coprono solo una scrittura antica e il nome digitato verrebbe fuori come
    una fila di quadratini.
    """
    fonts = list_fonts()
    for f in fonts:
        if f["script"] and f["latino"]:
            return str(f["path"])
    for f in fonts:
        name = str(f["name"]).lower()
        if "serif" in name and "italic" not in name:
            return str(f["path"])
    for f in fonts:
        if "serif" in str(f["name"]).lower():
            return str(f["path"])
    return str(fonts[0]["path"]) if fonts else ""


def _load_font(path: str, size: float) -> ImageFont.FreeTypeFont:
    """Carica un font, con ricerca automatica se il percorso non e' valido."""
    if path:
        try:
            return ImageFont.truetype(path, int(round(size)))
        except Exception:
            pass
    # Ricerca fra i font di sistema, con preferenza per un corsivo.
    wanted = ("italic", "oblique", "cursive", "script")
    fallback = ""
    for f in list_fonts():
        name = str(f["name"]).lower()
        try:
            if any(w in name for w in wanted):
                return ImageFont.truetype(str(f["path"]), int(round(size)))
            if not fallback and ("serif" in name or "times" in name):
                fallback = str(f["path"])
        except Exception:
            continue
    for cand in (fallback, _first_existing((
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/System/Library/Fonts/Supplemental/Georgia Italic.ttf",
        r"C:\Windows\Fonts\georgiai.ttf",
        r"C:\Windows\Fonts\times.ttf",
    ))):
        if cand:
            try:
                return ImageFont.truetype(cand, int(round(size)))
            except Exception:
                continue
    return ImageFont.load_default()


def _first_existing(paths: tuple[str, ...]) -> str:
    for p in paths:
        if os.path.exists(p):
            return p
    return ""


def _char_metrics(font: ImageFont.FreeTypeFont, ch: str) -> tuple[float, float, float]:
    """Larghezza, altezza e salita del carattere."""
    try:
        bbox = font.getbbox(ch)
        w = bbox[2] - bbox[0]
        asc = bbox[1]
        desc = bbox[3] - bbox[1]
        return w, asc, desc
    except Exception:
        w = font.getlength(ch)
        return w, font.size * 0.7, font.size * 0.25


def _is_upper(ch: str) -> bool:
    return ch.isalpha() and ch.isupper()


def _advance_width(font: ImageFont.FreeTypeFont, ch: str) -> float:
    try:
        return float(font.getlength(ch))
    except Exception:
        return font.size * 0.5


def render_typed(
    text: str,
    style: TypedStyle | None = None,
    canvas: tuple[int, int] | None = None,
) -> Image.Image:
    """Rende il testo come firma manoscritta su sfondo trasparente."""
    st = style or TypedStyle()
    text = text.strip()
    if not text:
        return Image.new("RGBA", canvas or (600, 220), (0, 0, 0, 0))

    rnd = random.Random(st.seed)
    size = float(st.size)
    probe = _load_font(st.font_path, size)
    x_height = max(size * 0.42, _char_metrics(probe, "x")[1] or size * 0.42)
    ascent = max(size * 0.95, probe.getmetrics()[0] if hasattr(probe, "getmetrics") else size)

    # Larghezza totale stimata per il dimensionamento automatico.
    total_w = sum(_advance_width(probe, c) for c in text)
    total_w += len(text) * size * st.spacing
    if total_w <= 0:
        total_w = size

    if canvas is None:
        pad = int(size * 0.35)
        w = int(total_w + 2 * pad + abs(st.slant) * size * 2.0)
        h = int(ascent + size * 0.6 + 2 * pad)
    else:
        w, h = canvas

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    pen_x = size * 0.30
    base_y = h - size * 0.34

    for ch in text:
        if ch == " ":
            pen_x += _advance_width(probe, ch) + size * st.spacing
            continue
        jitter_size = size * (1.0 + rnd.uniform(-st.size_variation, st.size_variation))
        # La cella deve contenere il glifo anche inclinato: la trasformazione
        # affetta l'inchiostro dal bordo e le lettere larghe (W, M, @) perdevano
        # un pezzo di tracciato. Le spazio per lo spostamento dell'inclinazione.
        cell_w, cell_h = int(size * 2.6), int(size * 2.8)
        # l'inclinazione è uno scarto di quanto la sommità della «x» si sposta:
        # applicarla sull'altezza della cella spostava il glifo di oltre un
        # corpo intero e le lettere si accavallavano
        spostamento = int(abs(st.slant) * size) + 2
        larghezza_box = cell_w + spostamento
        glyph = Image.new("RGBA", (larghezza_box, cell_h), (0, 0, 0, 0))
        d = ImageDraw.Draw(glyph)
        f = _load_font(st.font_path, jitter_size)
        try:
            bbox = f.getbbox(ch)
            larghezza_glifo = bbox[2] - bbox[0]
            altezza_glifo = bbox[3] - bbox[1]
            # il glifo viene centrato orizzontalmente e appoggiato alla base
            # della cella: è questo che tiene maiuscole e minuscole sulla stessa
            # riga di fondo
            centro = cell_w / 2 + spostamento
            ox = centro - larghezza_glifo / 2 - bbox[0]
            oy = cell_h - size * 0.30 - altezza_glifo - bbox[1]
        except Exception:
            ox = oy = cell_w * 0.15
        d.text((ox, oy), ch, font=f, fill=(*st.color, 255))

        if abs(st.slant) > 1e-4 or abs(st.rotate) > 1e-4:
            # inclinazione che lascia ferma la base e sposta la sommità
            glyph = glyph.transform(
                (larghezza_box, cell_h),
                Image.AFFINE,
                (1, st.slant, -st.slant * size, 0, 1, 0),
                resample=Image.BICUBIC,
            )
            rot = rnd.uniform(-st.rotate, st.rotate)
            if abs(rot) > 0.05:
                glyph = glyph.rotate(rot, resample=Image.BICUBIC, expand=False)

        # Oscillazione della base: sale sulle lettere alte, scende sulle discendenti.
        # Il font disegna già le maiuscole sulla riga di fondo corretta, quindi
        # il sollevamento è solo quanto le si vuole più alte di quanto sarebbero
        # per natura: prima la cella centrata in verticale e uno scarto fisso
        # facevano galleggiare la maiuscola sopra le minuscole del nome.
        if _is_upper(ch):
            dy = -x_height * max(0.0, st.ascender_height - 1.0) * 0.5
            dy -= rnd.uniform(0, size * 0.03)
        elif ch.islower() and ch not in "gjpqy":
            dy = rnd.uniform(-size * 0.02, size * 0.02)
        else:
            dy = rnd.uniform(-size * st.wobble, size * st.wobble)

        adv = _advance_width(probe, ch) + size * st.spacing
        # l'inchiostro resta centrato sulla cella anche dopo l'inclinazione:
        # si posiziona quindi sul centro dell'avanzamento
        x_grafico = pen_x + (adv - cell_w) / 2
        img.alpha_composite(glyph, (int(x_grafico), int(base_y + dy - cell_h + size * 0.30)))
        pen_x += adv

    return _trim(img)


def _trim(img: Image.Image, pad: int = 2) -> Image.Image:
    """Ritaglia la trasparenza attorno al testo."""
    bbox = bgremove.alpha_bounds(
        __import__("numpy").asarray(img.convert("RGBA"), dtype=__import__("numpy").uint8)[:, :, 3]
    )
    if bbox is None:
        return img
    x0, y0, x1, y1 = bbox
    return img.crop((max(0, x0 - pad), max(0, y0 - pad), min(img.width, x1 + pad + 1), min(img.height, y1 + pad + 1)))


def to_png_bytes(img: Image.Image) -> bytes:
    import io

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def fit_into(
    img: Image.Image, max_width: float, max_height: float, keep: bool = True
) -> Image.Image:
    """Riduce l'immagine per entrare nei limiti indicati."""
    if img.width == 0 or img.height == 0:
        return img
    scale = min(max_width / img.width, max_height / img.height, 1.0) if keep else min(
        max_width / img.width, max_height / img.height
    )
    if scale >= 1.0:
        return img
    nw = max(1, int(img.width * scale))
    nh = max(1, int(img.height * scale))
    return img.resize((nw, nh), Image.LANCZOS)
