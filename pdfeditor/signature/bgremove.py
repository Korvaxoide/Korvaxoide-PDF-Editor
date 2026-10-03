"""Rimozione dello sfondo dalle immagini della firma.

Un'immagine di firma scattata con il telefono o scansione ha uno sfondo che
occorre eliminare per ottenere una trasparenza pulita. Sono implementate piu'
tecniche combinabili, tutte basate su NumPy per restare veloci:

``white``
    Soglia sui canali: rimuove i pixel quasi bianchi (tipico di scanner e
    documenti). E' la tecnica predefinita perche' non richiede interventi.
``luminance``
    Soglia sulla luminosita': utile per sfondi colorati o in scala di grigi.
``color``
    Chroma key: rimuove i pixel simili a un colore campionato (foglio azzurro,
    cartoncino, fondo verde di un tavolo).
``flood``
    Magic wand a partire da un punto: propaga sui pixel entro una tolleranza
    continua, cosi' conserva i dettagli scuri interni alla firma.
``border``
    Rimuove la cornice esterna continua attorno al contenuto, utile per
    raddrizzare foto di firme su fogli.
``manual``
    Spazzola di cancellazione aggiuntiva, per rifinire a mano i bordi.

L'anti-aliasing dei bordi viene stimato dal gradiente di copertura, cosi' la
firma non risulta "spezzata" quando viene ridimensionata nel PDF.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

RGBA = tuple[int, int, int, int]


@dataclass
class RemovalSettings:
    """Parametri della rimozione dello sfondo."""

    method: str = "white"           # white | luminance | color | flood | border | none
    threshold: int = 34             # soglia 0-255
    tolerance: int = 42             # tolleranza del magic wand
    key_color: RGBA = (255, 255, 255, 255)
    seed: tuple[int, int] | None = None
    feather: int = 2                # sfumatura del bordo in pixel
    softness: int = 6               # ampiezza della zona di transizione
    despeckle: int = 0              # rimozione di macchioline isolate (0-255)
    keep_color: bool = True         # mantiene il colore originale della penna
    invert: bool = False            # opera sulla polarita' opposta
    auto_crop: bool = True          # ritaglia attorno al contenuto
    pad: int = 4                    # margine lasciato dal ritaglio
    mask_only: bool = False         # produce solo la maschera (per l'anteprima)
    erase_strokes: list[tuple[float, float, float]] = field(default_factory=list)

    def copy(self) -> "RemovalSettings":
        return RemovalSettings(**{**self.__dict__})


def to_rgba_array(img: Image.Image) -> np.ndarray:
    """Converte un'immagine in un array numpy RGBA a 8 bit."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    return np.asarray(img, dtype=np.uint8)


def _soft_ramp(distance: np.ndarray, threshold: float, span: float) -> np.ndarray:
    """Copertura continua 0..1 a partire dalla distanza da una soglia.

    ``distance`` e' quanto un pixel si discosta dallo sfondo: sotto ``threshold``
    la copertura e' zero, sopra ``threshold + span`` e' piena, e tra i due cresce
    linearmente. E' cosi' che i bordi della penna restano morbidi.
    """
    if span <= 0:
        return (distance > threshold).astype(np.float32)
    return np.clip((distance - threshold) / span, 0.0, 1.0).astype(np.float32)


def _smooth_mask(mask: np.ndarray, feather: int) -> np.ndarray:
    """Sfuma la copertura con un filtro gaussiano, senza aggiungere rumore.

    Il filtro e' a media zero: le zone piatte a zero restano a zero, quindi lo
    sfondo resta completamente trasparente.
    """
    if feather <= 0:
        return np.clip(mask, 0.0, 1.0)
    img = Image.fromarray((np.clip(mask, 0.0, 1.0) * 255).astype(np.uint8), mode="L")
    img = img.filter(ImageFilter.GaussianBlur(radius=feather))
    out = np.asarray(img, dtype=np.float32) / 255.0
    return np.clip(out, 0.0, 1.0)


def _despeckle(alpha: np.ndarray, threshold: int) -> np.ndarray:
    """Rimuove componenti isolate piu' piccole di una soglia di copertura."""
    if threshold <= 0:
        return alpha
    strong = alpha > 0.6
    try:
        from scipy import ndimage  # type: ignore

        # connessione a 8: una firma è fatta di tratti sottili che passano in
        # diagonale, e con la croce a 4 ogni capello diventa una macchiolina
        labels, n = ndimage.label(strong, structure=np.ones((3, 3), dtype=bool))
        if n == 0:
            return alpha
        sizes = ndimage.sum(strong, labels, range(1, n + 1))
        keep = np.zeros(n + 1, dtype=bool)
        for i, s in enumerate(sizes, start=1):
            keep[i] = s >= threshold
        keep[0] = True
        return np.where(keep[labels], alpha, 0.0)
    except Exception:
        # Senza SciPy si toglie per peeling: ad ogni passata spariscono i pixel
        # pieni che non hanno vicini pieni, quindi una componente di una macchiolina
        # (1 px), di due pixel, di tre… sparisce in una passata per dimensione.
        # Un tratto di penna ha invece ogni punto circondato da altri punti del
        # tratto e resta intatto: la versione precedente usava una media mobile,
        # che non toglieva nulla (restava alpha*0.15) e anzi cancellava i tratti
        # lunghi e sottili, cioè esattamente la firma.
        #
        # Il limite di questa via è che le macchie «piene» più grandi della
        # soglia restano: senza le librerie di scienza non si contano le
        # componenti, e contarle male significherebbe cancellare pezzi di firma.
        for _ in range(min(int(threshold), 64)):
            pieno = alpha > 0.6
            if not pieno.any():
                return np.where(pieno, 0.0, alpha)
            vicini = np.zeros(pieno.shape, dtype=np.int16)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    vicini += np.roll(np.roll(pieno, dy, axis=0), dx, axis=1)
            alpha = np.where(pieno & (vicini == 0), 0.0, alpha)
        return alpha


def build_mask(rgb: np.ndarray, st: RemovalSettings) -> np.ndarray:
    """Calcola la copertura della firma (1 = piena, 0 = sfondo) sull'immagine.

    Tutte le tecniche producono una copertura continua, non binaria, cosi' i
    bordi delle lettere conservano l'anti-aliasing anche dopo il ridimensionamento.
    """
    h, w = rgb.shape[:2]
    # l'inversione riguarda i colori, non la copertura: invertendo anche
    # l'alpha una firma con sfondo trasparente diventava un rettangolo bianco
    # opaco con la penna invisibile, cioe' il caso peggiore
    a_in = rgb[:, :, 3].astype(np.float32) / 255.0
    if st.invert:
        colori = 255 - rgb[:, :, :3]
    else:
        colori = rgb[:, :, :3]
    r = colori[:, :, 0].astype(np.float32)
    g = colori[:, :, 1].astype(np.float32)
    b = colori[:, :, 2].astype(np.float32)
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    minc = colori.min(axis=2).astype(np.float32)
    sat = colori.max(axis=2).astype(np.float32) - minc

    thr = float(st.threshold)
    span = max(4.0, float(st.softness) * 2.0)

    if st.method == "white":
        # Distanza dallo bianco: il canale piu' chiaro definisce lo sfondo.
        mask = _soft_ramp(255.0 - minc, thr, span)
    elif st.method == "luminance":
        mask = _soft_ramp(255.0 - lum, thr, span)
    elif st.method == "color":
        kr, kg, kb, _ = st.key_color
        dist = np.sqrt((r - kr) ** 2 + (g - kg) ** 2 + (b - kb) ** 2)
        mask = _soft_ramp(dist, thr * 2.2, max(6.0, span * 2.0))
    elif st.method == "flood":
        mask = _flood_mask(rgb, st)
    elif st.method == "border":
        mask = _border_mask(lum, sat, st)
    elif st.method == "none":
        mask = np.ones((h, w), dtype=np.float32)
    else:
        mask = _soft_ramp(255.0 - minc, thr, span)

    return np.clip(mask, 0.0, 1.0) * a_in


def _flood_mask(rgb: np.ndarray, st: RemovalSettings) -> np.ndarray:
    """Magic wand: propaga dai pixel di semiina entro una tolleranza continua."""
    h, w = rgb.shape[:2]
    seed = st.seed or (w // 2, max(1, h // 8))
    sx = min(max(0, int(seed[0])), w - 1)
    sy = min(max(0, int(seed[1])), h - 1)
    target = rgb[sy, sx, :3].astype(np.int16)
    tol = max(1, st.tolerance)

    # Propagazione a scacchiera (BFS) sul colore: rispetta i bordi reali.
    visited = np.zeros((h, w), dtype=bool)
    stack = [(sy, sx)]
    visited[sy, sx] = True
    tol3 = np.array([tol, tol, tol], dtype=np.int16)
    while stack:
        y, x = stack.pop()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if ny < 0 or ny >= h or nx < 0 or nx >= w or visited[ny, nx]:
                continue
            px = rgb[ny, nx, :3].astype(np.int16)
            if np.all(np.abs(px - target) <= tol3):
                visited[ny, nx] = True
                stack.append((ny, nx))
    return (~visited).astype(np.float32)


def _border_mask(lum: np.ndarray, sat: np.ndarray, st: RemovalSettings) -> np.ndarray:
    """Rimuove la cornice esterna del foglio, in modo continuo."""
    h, w = lum.shape
    # Il fondo e' la tinta periferica dominante.
    border = np.concatenate(
        [lum[0, :], lum[-1, :], lum[:, 0], lum[:, -1]]
    )
    bg = float(np.median(border))
    thr = max(12.0, float(st.threshold))
    fg = np.abs(lum - bg) > thr
    # Si espande il foreground verso l'interno per non mangiare la firma.
    out = fg.astype(np.float32)
    try:
        from scipy import ndimage  # type: ignore

        out = ndimage.binary_fill_holes(fg).astype(np.float32)
    except Exception:
        out = fg.astype(np.float32)
    return out


def apply_erasure(rgb: np.ndarray, alpha: np.ndarray, strokes: Sequence[tuple[float, float, float]]) -> np.ndarray:
    """Applica le spazzole di cancellazione manuale alla maschera."""
    if not strokes:
        return alpha
    h, w = alpha.shape
    layer = Image.new("L", (w, h), 255)
    draw = ImageDraw.Draw(layer)
    for x, y, radius in strokes:
        # un raggio negativo faceva sollevare a Pillow un ValueError che usciva
        # dalla rimozione dello sfondo: la spazzola veniva trattata come un
        # errore invece di non cancellare nulla
        r = abs(float(radius))
        draw.ellipse((x - r, y - r, x + r, y + r), fill=0)
    keep = np.asarray(layer, dtype=np.float32) / 255.0
    return alpha * keep


def remove_background(
    image: Image.Image, settings: RemovalSettings | None = None
) -> Image.Image:
    """Applica la rimozione dello sfondo e restituisce un'immagine RGBA."""
    st = settings or RemovalSettings()
    if st.method == "none" and not st.erase_strokes:
        return image.convert("RGBA")
    arr = to_rgba_array(image)
    mask = build_mask(arr, st)
    mask = _despeckle(mask, st.despeckle)
    mask = apply_erasure(arr, mask, st.erase_strokes)
    mask = _smooth_mask(mask, st.feather)
    out = arr.copy()
    if st.keep_color:
        out[:, :, 3] = (mask * 255).astype(np.uint8)
    else:
        grey = (0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2])
        grey = np.clip(grey * mask, 0, 255).astype(np.uint8)
        out = np.dstack([grey, grey, grey, (mask * 255).astype(np.uint8)])
    img = Image.fromarray(out, mode="RGBA")
    if st.auto_crop:
        img = crop_to_content(img, pad=st.pad)
    return img


def crop_to_content(img: Image.Image, pad: int = 4, threshold: int = 8) -> Image.Image:
    """Ritaglia l'immagine attorno al contenuto non trasparente."""
    a = np.asarray(img.convert("RGBA"), dtype=np.uint8)
    alpha = a[:, :, 3]
    if alpha.max() == 0:
        return img
    ys, xs = np.where(alpha > threshold)
    if len(ys) == 0:
        return img
    y0 = max(0, int(ys.min()) - pad)
    y1 = min(a.shape[0], int(ys.max()) + pad + 1)
    x0 = max(0, int(xs.min()) - pad)
    x1 = min(a.shape[1], int(xs.max()) + pad + 1)
    return img.crop((x0, y0, x1, y1))


def alpha_bounds(alpha: np.ndarray, threshold: int = 8) -> tuple[int, int, int, int] | None:
    """Riquadro del contenuto opaco, in pixel."""
    ys, xs = np.where(alpha > threshold)
    if len(ys) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def stats(image: Image.Image) -> dict[str, float]:
    """Statistiche utili a mostrare all'utente la qualita' del risultato."""
    arr = to_rgba_array(image)
    a = arr[:, :, 3]
    total = a.size
    opaque = float((a > 128).sum())
    return {
        "width": float(image.width),
        "height": float(image.height),
        "opaque_ratio": opaque / total if total else 0.0,
        "has_transparency": bool((a < 250).any()),
    }


def suggest_method(image: Image.Image) -> RemovalSettings:
    """Suggerisce la tecnica piu' adatta a un'immagine data."""
    arr = to_rgba_array(image)
    rgb = arr[:, :, :3].astype(np.float32)
    lum = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
    border = np.concatenate([lum[0, :], lum[-1, :], lum[:, 0], lum[:, -1]])
    bg = float(np.median(border))
    deviation = float(np.mean(np.abs(lum - bg)))
    if bg > 235 and deviation < 40:
        return RemovalSettings(method="white", threshold=30, softness=6)
    if deviation < 25:
        return RemovalSettings(method="flood", tolerance=38, seed=(image.width // 2, max(1, image.height // 10)))
    return RemovalSettings(method="luminance", threshold=int(max(20, min(70, deviation))))


def checkerboard(size: tuple[int, int], cell: int = 12) -> Image.Image:
    """Sfondo a scacchiera per l'anteprima della trasparenza."""
    w, h = size
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    for y in range(0, h, cell):
        for x in range(0, w, cell):
            if ((x // cell) + (y // cell)) % 2 == 0:
                d.rectangle((x, y, x + cell, y + cell), fill=(222, 226, 232))
    return img


def preview_on_checker(img: Image.Image, cell: int = 12) -> Image.Image:
    """Compone l'immagine trasparente su uno sfondo a scacchiera."""
    base = checkerboard(img.size, cell).convert("RGBA")
    base.alpha_composite(img.convert("RGBA"))
    return base.convert("RGB")
