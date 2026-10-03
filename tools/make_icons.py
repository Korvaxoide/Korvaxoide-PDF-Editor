"""Genera le icone dell'applicazione (PNG multi-risoluzione, ICO, ICNS).

Le icone sono disegnate a runtime: nessun file binario va mantenuto nel
progetto. Eseguire ``python -m tools.make_icons`` dopo aver modificato il tema.
"""

from __future__ import annotations

import os
import struct
import sys
import tempfile
import zlib
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPixmap  # noqa: E402

from pdfeditor.ui import icons  # noqa: E402

OUT = ROOT / "resources" / "icons"
ACCENT = QColor("#2f6fdb")
ACCENT_DARK = QColor("#1e4fa3")
PAPER = QColor("#ffffff")
EDGE = QColor("#9aa6b8")
INK = QColor("#2b303a")


def _draw(size: int) -> QPixmap:
    """Icona: foglio con bordo piegato e stilografica."""
    pm = QPixmap(size, size)
    pm.fill(Qt_transparent())
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    s = float(size)
    # foglio
    m = s * 0.13
    w, h = s * 0.62, s * 0.76
    fold = s * 0.20
    p.setPen(_pen(EDGE, s * 0.035))
    p.setBrush(PAPER)
    p.drawPolygon(_poly(
        [(m, m), (m + w - fold, m), (m + w, m + fold), (m + w, m + h), (m, m + h)]
    ))
    p.setBrush(ACCENT)
    p.setPen(_pen(ACCENT, s * 0.01))
    p.drawPolygon(_poly([(m, m), (m + w - fold, m), (m + w, m + fold), (m + w, m + fold * 0.9), (m, m + fold * 0.9)]))
    # righe di testo
    p.setPen(_pen(QColor("#c2c9d4"), s * 0.028))
    for i, frac in enumerate((0.30, 0.40, 0.50, 0.60)):
        y = m + h * frac
        x2 = m + w * (0.72 if i % 2 == 0 else 0.55)
        p.drawLine(_pt(m + w * 0.10, y), _pt(x2, y))
    # stilografica
    p.setPen(_pen(ACCENT_DARK, s * 0.02))
    p.setBrush(ACCENT)
    p.drawPolygon(_poly([
        (s * 0.40, s * 0.90), (s * 0.47, s * 0.72), (s * 0.72, s * 0.34),
        (s * 0.84, s * 0.44), (s * 0.66, s * 0.68), (s * 0.58, s * 0.74),
    ]))
    p.setBrush(PAPER)
    p.setPen(Qt_NoPen_())
    p.drawEllipse(_pt(s * 0.79, s * 0.40), s * 0.035, s * 0.035)
    p.end()
    return pm


# --- piccole funzioni per non ripetere i costruttori Qt -------------------


def _pen(color: QColor, width: float):
    from PySide6.QtGui import QPen

    from PySide6.QtCore import Qt

    pen = QPen(color, max(1.0, width))
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def _pt(x: float, y: float):
    from PySide6.QtCore import QPointF

    return QPointF(x, y)


def _poly(points: list[tuple[float, float]]):
    from PySide6.QtGui import QPolygonF

    return QPolygonF([_pt(x, y) for x, y in points])


def Qt_transparent():
    from PySide6.QtCore import Qt

    return Qt.transparent


def Qt_NoPen_():
    from PySide6.QtCore import Qt

    return Qt.NoPen


def _png_bytes(pm: QPixmap, tmpdir: Path) -> bytes:
    """Byte PNG di un pixmap, scrivendo su file.

    ``QBuffer`` costruito su un ``QByteArray`` temporaneo e' fragile in PySide:
    il buffer puo' conservare un riferimento a un oggetto gia' liberato. Il
    file temporaneo evita il problema e resta comprensibile.
    """
    path = tmpdir / "tmp.png"
    pm.save(str(path), "PNG")
    data = path.read_bytes()
    path.unlink(missing_ok=True)
    return data


def make_ico(pm: QPixmap, path: Path, tmpdir: Path) -> None:
    """Scrive un .ico con piu' risoluzioni (Windows)."""
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [_png_bytes(pm.scaled(s, s), tmpdir) for s in sizes]
    out = bytearray(struct.pack("<HHH", 0, 1, len(sizes)))
    offset = 6 + 16 * len(sizes)
    for s, data in zip(sizes, images):
        out += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    for data in images:
        out += data
    path.write_bytes(bytes(out))


def make_icns(pm: QPixmap, path: Path, tmpdir: Path) -> None:
    """Scrive un .icns (macOS) con i formati richiesti."""

    def icns_element(tag: bytes, data: bytes) -> bytes:
        return tag + struct.pack(">I", len(data) + 8) + data

    def png_at(w: int) -> bytes:
        return _png_bytes(pm.scaled(w, w), tmpdir)

    body = b"".join(
        [
            icns_element(b"icp4", png_at(16)),
            icns_element(b"icp5", png_at(32)),
            icns_element(b"ic07", png_at(128)),
            icns_element(b"ic08", png_at(256)),
        ]
    )
    path.write_bytes(b"icns" + struct.pack(">I", len(body) + 8) + body)


def main() -> int:
    app = QGuiApplication.instance() or QGuiApplication([])
    OUT.mkdir(parents=True, exist_ok=True)
    grande = _draw(1024)
    grande.save(str(OUT / "korvaxoide_pdf_editor.png"), "PNG")
    for s in (16, 24, 32, 48, 64, 128, 256, 512):
        _draw(s).save(str(OUT / f"korvaxoide_pdf_editor_{s}.png"), "PNG")
    with tempfile.TemporaryDirectory(prefix="icone_") as td:
        tmpdir = Path(td)
        make_ico(grande, OUT / "korvaxoide_pdf_editor.ico", tmpdir)
        make_icns(grande, OUT / "korvaxoide_pdf_editor.icns", tmpdir)
    print(f"Icone generate in {OUT}")
    for f in sorted(OUT.iterdir()):
        print(f"  {f.name}: {f.stat().st_size} byte")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
