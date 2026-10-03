"""Conversioni e formattazione di unità di misura PDF."""

from __future__ import annotations

# 1 inch = 72 punti PDF
PT_PER_INCH = 72.0
PT_PER_CM = 72.0 / 2.54
PT_PER_MM = 72.0 / 25.4
PT_PER_PX = 72.0 / 96.0

UNITS = {
    "pt": ("punto", "pt", PT_PER_INCH),
    "mm": ("millimetro", "mm", PT_PER_MM),
    "cm": ("centimetro", "cm", PT_PER_CM),
    "in": ("pollice", "in", PT_PER_INCH),
}

PAGE_SIZES = {
    "A0": (2383.94, 3370.39),
    "A1": (1683.78, 2383.94),
    "A2": (1190.55, 1683.78),
    "A3": (841.89, 1190.55),
    "A4": (595.28, 841.89),
    "A5": (419.53, 595.28),
    "A6": (297.64, 419.53),
    "Letter": (612.0, 792.0),
    "Legal": (612.0, 1008.0),
    "Tabloid": (792.0, 1224.0),
    "B5": (498.90, 708.66),
    "B4": (708.66, 1000.63),
    "Executive": (521.86, 756.0),
}


def to_pt(value: float, unit: str) -> float:
    """Converte `value` espresso in `unit` in punti PDF."""
    return float(value) * UNITS.get(unit, UNITS["pt"])[2]


def from_pt(points: float, unit: str) -> float:
    """Converte punti PDF nell'unità richiesta."""
    factor = UNITS.get(unit, UNITS["pt"])[2]
    return float(points) / factor


def fmt(value: float, unit: str = "pt", decimals: int = 2) -> str:
    """Formatta un valore in punti PDF con l'unità richiesta."""
    return f"{from_pt(value, unit):.{decimals}f} {UNITS.get(unit, UNITS['pt'])[1]}"


def paper_size(name: str) -> tuple[float, float]:
    """Dimensioni in punti per un formato carta noto."""
    return PAGE_SIZES.get(name, PAGE_SIZES["A4"])
