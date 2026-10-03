"""Modello di tracciato per la firma scritta con mouse o stilo.

I tratti sono memorizzati come liste di punti in coordinate canvas, indipendenti
dalla risoluzione: la firma puo' essere ridimensionata e salvata senza perdite.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence

Point = tuple[float, float]


@dataclass
class StrokeStyle:
    """Aspetto della penna."""

    color: tuple[int, int, int] = (16, 24, 40)
    width: float = 2.6
    pressure: bool = True
    smoothing: float = 0.5
    opacity: float = 1.0

    def copy(self) -> "StrokeStyle":
        return StrokeStyle(self.color, self.width, self.pressure, self.smoothing, self.opacity)


@dataclass
class Stroke:
    """Un tratto continuo di penna."""

    points: list[Point] = field(default_factory=list)
    style: StrokeStyle = field(default_factory=StrokeStyle)
    widths: list[float] = field(default_factory=list)

    def add(self, x: float, y: float, width: float | None = None) -> None:
        self.points.append((float(x), float(y)))
        self.widths.append(float(width) if width is not None else self.style.width)

    def bounds(self) -> tuple[float, float, float, float] | None:
        if not self.points:
            return None
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        return (min(xs), min(ys), max(xs), max(ys))

    def smoothed(self, factor: float | None = None) -> list[Point]:
        """Restituisce i punti filtrati (media mobile pesata)."""
        f = self.style.smoothing if factor is None else factor
        if f <= 0 or len(self.points) < 3:
            return list(self.points)
        out: list[Point] = [self.points[0]]
        for i in range(1, len(self.points) - 1):
            p0 = self.points[i - 1]
            p1 = self.points[i]
            p2 = self.points[i + 1]
            out.append(
                (
                    p1[0] * (1 - f) + (p0[0] + p2[0]) / 2 * f,
                    p1[1] * (1 - f) + (p0[1] + p2[1]) / 2 * f,
                )
            )
        out.append(self.points[-1])
        return out


@dataclass
class SignatureCanvas:
    """Insieme di tratti che forma una firma."""

    strokes: list[Stroke] = field(default_factory=list)
    width: float = 600.0
    height: float = 220.0
    default_style: StrokeStyle = field(default_factory=StrokeStyle)

    def new_stroke(self, x: float, y: float, width: float | None = None) -> Stroke:
        s = Stroke(style=self.default_style.copy())
        s.add(x, y, width)
        self.strokes.append(s)
        return s

    def extend(self, x: float, y: float, width: float | None = None) -> None:
        if not self.strokes:
            self.new_stroke(x, y, width)
            return
        s = self.strokes[-1]
        if s.points:
            lx, ly = s.points[-1]
            if math.hypot(x - lx, y - ly) < 0.7:
                return
        s.add(x, y, width)

    def undo_stroke(self) -> bool:
        return bool(self.strokes and self.strokes.pop())

    def clear(self) -> None:
        self.strokes.clear()

    @property
    def is_empty(self) -> bool:
        return not self.strokes

    def bounds(self) -> tuple[float, float, float, float] | None:
        boxes = [s.bounds() for s in self.strokes]
        boxes = [b for b in boxes if b]
        if not boxes:
            return None
        pad = max((s.style.width for s in self.strokes), default=1.0)
        return (
            min(b[0] for b in boxes) - pad,
            min(b[1] for b in boxes) - pad,
            max(b[2] for b in boxes) + pad,
            max(b[3] for b in boxes) + pad,
        )

    def bounds_in_canvas(self) -> tuple[float, float, float, float]:
        """Riquadro dei tratti, limitato all'area del canvas."""
        b = self.bounds()
        if b is None:
            return (0.0, 0.0, self.width, self.height)
        return (
            max(0.0, b[0]),
            max(0.0, b[1]),
            min(self.width, b[2]),
            min(self.height, b[3]),
        )

    def to_dict(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            # la penna corrente fa parte della firma: senza questa voce
            # riaprire una firma salvata ripartiva dal colore e dallo spessore
            # predefiniti, e la ricostruzione non tornava più
            "default_style": {
                "color": list(self.default_style.color),
                "width": self.default_style.width,
                "smoothing": self.default_style.smoothing,
                "pressure": self.default_style.pressure,
                "opacity": self.default_style.opacity,
            },
            "strokes": [
                {
                    "points": [list(p) for p in s.points],
                    "widths": list(s.widths),
                    "color": list(s.style.color),
                    "width": s.style.width,
                    "smoothing": s.style.smoothing,
                    "pressure": s.style.pressure,
                    "opacity": s.style.opacity,
                }
                for s in self.strokes
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SignatureCanvas":
        c = cls(width=data.get("width", 600.0), height=data.get("height", 220.0))
        predef = data.get("default_style") or {}
        if isinstance(predef, dict):
            c.default_style = StrokeStyle(
                color=tuple(predef.get("color", c.default_style.color)),  # type: ignore[arg-type]
                width=float(predef.get("width", c.default_style.width)),
                smoothing=float(predef.get("smoothing", c.default_style.smoothing)),
                pressure=bool(predef.get("pressure", c.default_style.pressure)),
                opacity=float(predef.get("opacity", c.default_style.opacity)),
            )
        for sd in data.get("strokes", []):
            s = Stroke(
                style=StrokeStyle(
                    color=tuple(sd.get("color", (16, 24, 40))),  # type: ignore[arg-type]
                    width=float(sd.get("width", 2.6)),
                    smoothing=float(sd.get("smoothing", 0.5)),
                    pressure=bool(sd.get("pressure", True)),
                    opacity=float(sd.get("opacity", 1.0)),
                )
            )
            s.points = [(float(p[0]), float(p[1])) for p in sd.get("points", [])]
            s.widths = [float(w) for w in sd.get("widths", [])] or [
                s.style.width for _ in s.points
            ]
            if s.points:
                c.strokes.append(s)
        return c


def resample(points: Sequence[Point], step: float) -> list[Point]:
    """Ricampiona una polilinea a passo costante (interpolazione lineare).

    L'ultimo punto della polilinea viene sempre emesso: senza questo la fine di
    ogni firma — cioe' l'ultimo tratto di penna — restava indietro di una
    frazione di passo a ogni salvataggio e ridisegno.
    """
    if len(points) < 2 or step <= 0:
        return list(points)
    out: list[Point] = [points[0]]
    carry = 0.0
    ultimo = points[-1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        seg = math.hypot(x1 - x0, y1 - y0)
        if seg <= 1e-9:
            continue
        d = step - carry
        while d < seg:
            t = d / seg
            out.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
            d += step
        carry = seg - (d - step)
    if out[-1] != ultimo:
        out.append(ultimo)
    return out


def path_length(points: Iterable[Point]) -> float:
    total = 0.0
    prev: Point | None = None
    for p in points:
        if prev is not None:
            total += math.hypot(p[0] - prev[0], p[1] - prev[1])
        prev = p
    return total
