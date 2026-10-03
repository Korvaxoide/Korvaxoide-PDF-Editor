"""Rendering dei tratti di firma in un'immagine trasparente.

I tratti vengono disegnati come polilinee con spessore variabile (pressione della
penna) e sfumatura sulle giunzioni, quindi ridimensionati in alta risoluzione per
restare nitidi quando la firma viene inserita nel PDF.
"""

from __future__ import annotations

import io
from PIL import Image, ImageDraw

from . import bgremove, strokes as sk

SS = 4  # supercampionamento per il rendering vettoriale


def render_strokes(
    canvas: sk.SignatureCanvas,
    scale: float = 2.0,
    padding: float = 6.0,
    transparent: bool = True,
) -> Image.Image:
    """Converte i tratti in un'immagine RGBA ad alta risoluzione."""
    if canvas.is_empty:
        return Image.new("RGBA", (int(canvas.width * scale), int(canvas.height * scale)), (0, 0, 0, 0))

    # L'area disegnata è quella che i tratti occupano, non la tela: un firma
    # disegnata oltre il bordo (il puntino esce dal riquadro) veniva tagliata e
    # non si poteva più recuperare, perché il ritaglio finale lavora solo su
    # ciò che resta della tela.
    xs: list[float] = []
    ys: list[float] = []
    for stroke in canvas.strokes:
        for x, y in stroke.points:
            xs.append(float(x))
            ys.append(float(y))
    if not xs:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    # il raggio della penna va lasciato attorno al tratto
    margine = padding + max((s.style.width for s in canvas.strokes), default=2.0)
    origine = (min(xs) - margine, min(ys) - margine)
    # la tela va dimensionata nello stesso sistema in cui si disegna, cioè
    # moltiplicata per la scala: misurata in punti di tela il disegno finiva
    # fuori e la firma veniva tagliata a metà
    w = max(1, int(round((max(xs) + margine - origine[0]) * scale)))
    h = max(1, int(round((max(ys) + margine - origine[1]) * scale)))

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def punto(pt: tuple[float, float]) -> tuple[float, float]:
        return ((pt[0] - origine[0]) * scale, (pt[1] - origine[1]) * scale)

    for stroke in canvas.strokes:
        pts = stroke.smoothed()
        larghezze = stroke.widths
        if not pts:
            continue
        if len(pts) == 1:
            x, y = punto(pts[0])
            r = max(0.5, stroke.style.width * scale / 2)
            d.ellipse((x - r, y - r, x + r, y + r), fill=(*stroke.style.color, 255))
            continue
        pts = sk.resample(pts, max(0.35, 0.6 / max(scale, 0.1)))
        # lo spessore segue la pressione registrata: la larghezza della penna
        # e' gia' in punti di tela, quindi il raggio e' meta' della larghezza
        # moltiplicata per la scala e basta. Prima la scala entrava due volte
        # (una nel raggio e una nel raggio del raggio) e a scale 4 una penna da
        # 2,6 punti diventava un blob di 42 pixel.
        def raggio(indice: int) -> float:
            if not stroke.style.pressure or not larghezze:
                return max(0.5, stroke.style.width * scale / 2)
            w = larghezze[min(indice, len(larghezze) - 1)]
            return max(0.5, w * scale / 2)

        n = len(pts)
        for i in range(n - 1):
            a, b = punto(pts[i]), punto(pts[i + 1])
            r0, r1 = raggio(i), raggio(i + 1)
            steps = 2
            for s in range(steps):
                f0, f1 = s / steps, (s + 1) / steps
                ax = a[0] + (b[0] - a[0]) * f0
                ay = a[1] + (b[1] - a[1]) * f0
                bx = a[0] + (b[0] - a[0]) * f1
                by = a[1] + (b[1] - a[1]) * f1
                th = (r0 * (1 - f0) + r1 * f0)
                d.line((ax, ay, bx, by), fill=(*stroke.style.color, 255), width=max(1, int(round(th * 2))))
                d.ellipse((bx - th, by - th, bx + th, by + th), fill=(*stroke.style.color, 255))
        # Chiude la punta finale.
        lx, ly = punto(pts[-1])
        r = raggio(n - 1)
        d.ellipse((lx - r, ly - r, lx + r, ly + r), fill=(*stroke.style.color, 255))

    # Il ritaglio va fatto prima di appiattire: con ``transparent=False``
    # l'alpha e' 255 ovunque e il ritaglio diventava un no-op, lasciando
    # nell'immagine tutta la tela.
    box = _content_box(img, padding * scale)
    if box:
        img = img.crop(box)
    if not transparent:
        flat = Image.new("RGBA", img.size, (255, 255, 255, 255))
        flat.alpha_composite(img)
        img = flat
    return img


def _content_box(img: Image.Image, pad: float) -> tuple[int, int, int, int] | None:
    import numpy as np

    a = np.asarray(img.convert("RGBA"), dtype=np.uint8)[:, :, 3]
    b = bgremove.alpha_bounds(a)
    if b is None:
        return None
    x0, y0, x1, y1 = b
    p = int(max(0, pad))
    return (max(0, x0 - p), max(0, y0 - p), min(img.width, x1 + p + 1), min(img.height, y1 + p + 1))


def to_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _su_rgba(img: Image.Image) -> Image.Image:
    """Immagine in RGBA con la trasparenza davvero rispettata.

    Le immagini a palette e in scala di grigi portano la trasparenza in
    ``info['transparency']``, che ``convert('RGBA')`` non applica: l'indice
    trasparente resta in carota e l'appiattimento su bianco produceva uno
    sfondo nero.
    """
    if img.mode == "RGBA":
        return img
    trasparenza = img.info.get("transparency")
    rgba = img.convert("RGBA")
    if trasparenza is None:
        return rgba
    import numpy as np

    a = np.asarray(rgba, dtype=np.uint8).copy()
    indici = a[:, :, 0]
    if isinstance(trasparenza, int):
        a[:, :, 3] = np.where(indici == trasparenza, 0, 255)
    elif isinstance(trasparenza, (bytes, bytearray)):
        tabella = list(trasparenza) + [255] * (256 - len(trasparenza))
        a[:, :, 3] = np.array(tabella, dtype=np.uint8)[indici]
    return Image.fromarray(a, mode="RGBA")


def to_jpeg_on_white(img: Image.Image, quality: int = 92) -> bytes:
    """Versione con sfondo bianco, per contesti che non supportano il canale alfa."""
    rgba = _su_rgba(img)
    base = Image.new("RGB", rgba.size, (255, 255, 255))
    base.paste(rgba, mask=rgba.split()[3])
    buf = io.BytesIO()
    base.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def flatten_for_pdf(img: Image.Image) -> Image.Image:
    """Appiattisce la trasparenza su bianco (per contesti che non la supportano)."""
    rgba = _su_rgba(img)
    base = Image.new("RGB", rgba.size, (255, 255, 255))
    base.paste(rgba, mask=rgba.split()[3])
    return base
