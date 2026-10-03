"""Geometria: rettangoli, trasformazioni, allineamenti, magnetismo.

Usa ``pymupdf.Rect`` come tipo nativo per coerenza con il motore PDF, ma espone
funzioni pure che non richiedono Qt (testabili headless).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pymupdf

Rect = pymupdf.Rect
Point = pymupdf.Point
Matrix = pymupdf.Matrix

ALIGN_H = ("left", "center", "right", "justify")
ALIGN_V = ("top", "center", "bottom")

Z_ALIGN = {
    "left": lambda r: (r.x0, (r.y0 + r.y1) / 2),
    "hcenter": lambda r: ((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2),
    "right": lambda r: (r.x1, (r.y0 + r.y1) / 2),
    "top": lambda r: ((r.x0 + r.x1) / 2, r.y0),
    "vcenter": lambda r: ((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2),
    "bottom": lambda r: ((r.x0 + r.x1) / 2, r.y1),
}

Z_DISTRIBUTE = ("h", "v")


def rect_of(x0: float, y0: float, x1: float, y1: float) -> Rect:
    """Crea un rettangolo normalizzando gli angoli."""
    return Rect(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def normalize(rect: Rect) -> Rect:
    """Restituisce il rettangolo con coordinate ordinate."""
    return rect_of(rect.x0, rect.y0, rect.x1, rect.y1)


def inflate(rect: Rect, amount: float) -> Rect:
    """Ingrandisce (o riduce, se negativo) il rettangolo di `amount` punti."""
    return Rect(rect.x0 - amount, rect.y0 - amount, rect.x1 + amount, rect.y1 + amount)


def contains_point(rect: Rect, x: float, y: float, tol: float = 0.0) -> bool:
    return (rect.x0 - tol) <= x <= (rect.x1 + tol) and (rect.y0 - tol) <= y <= (rect.y1 + tol)


def union(rects: list[Rect]) -> Rect:
    """Bounding box di un insieme di rettangoli."""
    rects = [r for r in rects if r is not None and not r.is_empty]
    if not rects:
        return Rect()
    out = Rect(rects[0])
    for r in rects[1:]:
        out |= r
    return out


def move(rect: Rect, dx: float, dy: float) -> Rect:
    return Rect(rect.x0 + dx, rect.y0 + dy, rect.x1 + dx, rect.y1 + dy)


def scale_about(rect: Rect, factor: float, cx: float | None = None, cy: float | None = None) -> Rect:
    """Riscala il rettangolo mantenendo fermo il centro (o un punto dato)."""
    cx = (rect.x0 + rect.x1) / 2 if cx is None else cx
    cy = (rect.y0 + rect.y1) / 2 if cy is None else cy
    w = (rect.x1 - rect.x0) * factor
    h = (rect.y1 - rect.y0) * factor
    return Rect(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def clamp_rect(rect: Rect, bounds: Rect) -> Rect:
    """Vincola il rettangolo entro i limiti, spostandolo o ridimensionandolo.

    Se l'elemento e' piu' grande dei limiti viene ridimensionato: spostarlo
    semplicemente lo lascerebbe uscire comunque.
    """
    w = min(rect.width, bounds.width)
    h = min(rect.height, bounds.height)
    x0 = min(max(rect.x0, bounds.x0), max(bounds.x0, bounds.x1 - w))
    y0 = min(max(rect.y0, bounds.y0), max(bounds.y0, bounds.y1 - h))
    return Rect(x0, y0, x0 + w, y0 + h)


def aspect_limited(rect: Rect, ratio: float) -> Rect:
    """Ricalcola il rettangolo preservando il rapporto larghezza/altezza."""
    if ratio <= 0 or rect.is_empty:
        return Rect(rect)
    w, h = rect.width, rect.height
    if w / h > ratio:
        w = h * ratio
    else:
        h = w / ratio
    cx, cy = (rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2
    return Rect(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


@dataclass
class SnapResult:
    """Esito di un'operazione di magnetismo."""

    x: float
    y: float
    guides: list[tuple[float, float, float, float]]
    snapped: bool = False


def snap_value(value: float, candidates: list[float], tol: float) -> tuple[float, float | None]:
    """Trova il candidato più vicino entro la tolleranza."""
    best, best_d = None, tol
    for c in candidates:
        d = abs(c - value)
        if d <= best_d:
            best, best_d = c, d
    return (best, best) if best is not None else (value, None)


def compute_snap(
    rect: Rect,
    targets: list[Rect],
    page_rect: Rect,
    tol: float = 4.0,
    grid: float = 0.0,
    guides_enabled: bool = True,
) -> SnapResult:
    """Calcola lo scarto di magnetismo per un rettangolo in movimento.

    Allinea bordi e centri agli elementi di riferimento e alla pagina, e opzionalmente
    alla griglia. Restituisce il rettangolo traslato e le guide da disegnare.
    """
    guides: list[tuple[float, float, float, float]] = []
    dx = dy = 0.0
    snapped = False

    hx_self = [rect.x0, (rect.x0 + rect.x1) / 2, rect.x1]
    vy_self = [rect.y0, (rect.y0 + rect.y1) / 2, rect.y1]
    hx_tgt: list[tuple[float, float]] = []
    vy_tgt: list[tuple[float, float]] = []

    for t in targets + [page_rect]:
        if t is None or t.is_empty:
            continue
        for v in (t.x0, (t.x0 + t.x1) / 2, t.x1):
            hx_tgt.append((v, t.y0))
            hx_tgt.append((v, t.y1))
        for v in (t.y0, (t.y0 + t.y1) / 2, t.y1):
            vy_tgt.append((v, t.x0))
            vy_tgt.append((v, t.x1))

    if guides_enabled:
        agganciato_x = False
        for sv in hx_self:
            for tv, _ in hx_tgt:
                if abs(sv + dx - tv) <= tol:
                    dx = tv - sv
                    agganciato_x = True
                    guides.append((tv, page_rect.y0, tv, page_rect.y1))
                    break
            if agganciato_x:
                break
        # il flag va reimpostato per la verticale: riusando quello orizzontale
        # il ciclo verticale terminava al primo candidato senza aver agganciato
        # nulla, e allineare il bordo inferiore o il centro era impossibile
        # ogni volta che l'orizzontale era riuscito
        agganciato_y = False
        for sv in vy_self:
            for tv, _ in vy_tgt:
                if abs(sv + dy - tv) <= tol:
                    dy = tv - sv
                    agganciato_y = True
                    guides.append((page_rect.x0, tv, page_rect.x1, tv))
                    break
            if agganciato_y:
                break
        snapped = agganciato_x or agganciato_y

    if grid > 0:
        gx = round((rect.x0 + dx) / grid) * grid
        gy = round((rect.y0 + dy) / grid) * grid
        if not guides_enabled:
            dx, dy = gx - rect.x0, gy - rect.y0
        else:
            if abs(rect.x0 + dx - gx) < 1e-6:
                dx = gx - rect.x0
            if abs(rect.y0 + dy - gy) < 1e-6:
                dy = gy - rect.y0

    if guides_enabled and not guides:
        cx, cy = (rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2
        guides.append((cx, page_rect.y0, cx, page_rect.y1))
        guides.append((page_rect.x0, cy, page_rect.x1, cy))
    return SnapResult(rect.x0 + dx, rect.y0 + dy, guides, snapped)


def align_rects(rects: list[Rect], mode: str) -> list[Rect]:
    """Allinea un insieme di rettangoli secondo `Z_ALIGN`."""
    if len(rects) < 2:
        return list(rects)
    box = union(rects)
    fn = Z_ALIGN.get(mode)
    if fn is None:
        return list(rects)
    out = []
    for r in rects:
        ax, ay = fn(box)
        bx, by = fn(r)
        out.append(move(r, ax - bx, ay - by))
    return out


def distribute_rects(rects: list[Rect], axis: str = "h") -> list[Rect]:
    """Distribuisce uniformemente i rettangoli lungo un asse."""
    if len(rects) < 3:
        return list(rects)
    key = (lambda r: r.x0) if axis == "h" else (lambda r: r.y0)
    ordered = sorted(rects, key=key)
    box = union(ordered)
    if axis == "h":
        total = sum(r.width for r in ordered)
        gap = (box.width - total) / (len(ordered) - 1)
        pos = box.x0
        out = []
        for r in ordered:
            out.append(Rect(pos, r.y0, pos + r.width, r.y1))
            pos += r.width + gap
    else:
        total = sum(r.height for r in ordered)
        gap = (box.height - total) / (len(ordered) - 1)
        pos = box.y0
        out = []
        for r in ordered:
            out.append(Rect(r.x0, pos, r.x1, pos + r.height))
            pos += r.height + gap
    return out


def rotate_point(x: float, y: float, cx: float, cy: float, deg: float) -> tuple[float, float]:
    """Ruota un punto attorno a un centro."""
    a = math.radians(deg)
    dx, dy = x - cx, y - cy
    return (cx + dx * math.cos(a) - dy * math.sin(a), cy + dx * math.sin(a) + dy * math.cos(a))


def quad_corners(rect: Rect, rotation: float = 0.0) -> list[tuple[float, float]]:
    """Angoli del rettangolo ruotato attorno al proprio centro."""
    cx, cy = (rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2
    return [
        rotate_point(x, y, cx, cy, rotation)
        for x, y in ((rect.x0, rect.y0), (rect.x1, rect.y0), (rect.x1, rect.y1), (rect.x0, rect.y1))
    ]


def page_rotation_matrix(rotation: int, page_rect: Rect) -> Matrix:
    """Matrice di trasformazione per una pagina ruotata di multipli di 90°."""
    rotation %= 360
    if rotation == 90:
        return Matrix(0, 1, -1, 0, page_rect.y1, 0)
    if rotation == 180:
        return Matrix(-1, 0, 0, -1, page_rect.x1, page_rect.y1)
    if rotation == 270:
        return Matrix(0, -1, 1, 0, 0, page_rect.x0)
    return Matrix(1, 0, 0, 1, 0, 0)
