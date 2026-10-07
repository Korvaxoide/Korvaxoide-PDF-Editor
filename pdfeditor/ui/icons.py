"""Icone vettoriali disegnate a runtime.

Non si distribuiscono file immagine: ogni icona e' una funzione di disegno che
produce un ``QIcon`` nitida a qualunque risoluzione, su Linux come su Windows.
"""

from __future__ import annotations

import math
import warnings
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)

Cache: dict[tuple[str, str, int], QIcon] = {}

#: L'icona dell'applicazione ha una cache tutta sua, perche' dipende solo dalla
#: dimensione e non dal colore come le altre. Non sta in `Cache` per non mescolare
#: due chiavi di forma diversa.
AppIconCache: dict[int, QIcon] = {}


def _pen(p: QPainter, color: str, width: float = 1.6) -> None:
    p.setPen(QPen(QColor(color), width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)


def _fill(p: QPainter, color: str) -> None:
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(color)))


def _page(p: QPainter, s: float, c: str, fold: bool = True) -> None:
    m = s * 0.18
    w, h = s - 2 * m, s - 2 * m
    p.setPen(QPen(QColor(c), s * 0.075))
    p.setBrush(Qt.NoBrush)
    if fold:
        f = s * 0.24
        path = QPainterPath()
        path.moveTo(m, m)
        path.lineTo(m + w - f, m)
        path.lineTo(m + w, m + f)
        path.lineTo(m + w, m + h)
        path.lineTo(m, m + h)
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(QPointF(m + w - f, m), QPointF(m + w - f, m + f))
        p.drawLine(QPointF(m + w - f, m + f), QPointF(m + w, m + f))
    else:
        p.drawRect(QRectF(m, m, w, h))


# ------------------------------------------------------------------ disegni


def _doc(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        _page(p, s, c)
        p.setPen(QPen(QColor(c), s * 0.06))
        for i, y in enumerate((0.42, 0.55, 0.68)):
            p.drawLine(QPointF(s * 0.32, s * y), QPointF(s * 0.68 - (0.12 if i == 2 else 0), s * y))

    return d


def _doc_open(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        _page(p, s, c, fold=False)
        p.setBrush(QBrush(QColor(c)))
        p.setPen(Qt.NoPen)
        p.drawPath(
            _path(
                [
                    (s * 0.1, s * 0.78), (s * 0.24, s * 0.78), (s * 0.3, s * 0.6),
                    (s * 0.9, s * 0.6), (s * 0.78, s * 0.9), (s * 0.22, s * 0.9),
                ],
                close=True,
            )
        )

    return d


def _save(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.075))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(s * 0.16, s * 0.16, s * 0.68, s * 0.68))
        p.setBrush(QBrush(QColor(c)))
        p.setPen(Qt.NoPen)
        p.drawRect(QRectF(s * 0.32, s * 0.16, s * 0.36, s * 0.22))
        p.drawRect(QRectF(s * 0.28, s * 0.52, s * 0.44, s * 0.32))

    return d


def _text(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.11, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(s * 0.2, s * 0.3), QPointF(s * 0.8, s * 0.3))
        p.drawLine(QPointF(s * 0.2, s * 0.5), QPointF(s * 0.8, s * 0.5))
        p.drawLine(QPointF(s * 0.2, s * 0.7), QPointF(s * 0.56, s * 0.7))

    return d


def _image(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        _pen(p, c, s * 0.075)
        p.drawRoundedRect(QRectF(s * 0.14, s * 0.2, s * 0.72, s * 0.6), s * 0.08, s * 0.08)
        _fill(p, c)
        p.drawEllipse(QPointF(s * 0.36, s * 0.42), s * 0.07, s * 0.07)
        pen = _path(
            [(s * 0.18, s * 0.74), (s * 0.4, s * 0.5), (s * 0.56, s * 0.64), (s * 0.68, s * 0.54), (s * 0.84, s * 0.74)]
        )
        p.setPen(Qt.NoPen)
        p.drawPath(pen)

    return d


def _images(s: float, c: str) -> None:
    """Piu' immagini: cornici sfalsate e una in primo piano."""

    def d(p: QPainter) -> None:
        _pen(p, c, s * 0.07)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(s * 0.08, s * 0.12, s * 0.52, s * 0.42), s * 0.06, s * 0.06)
        p.drawRoundedRect(QRectF(s * 0.21, s * 0.25, s * 0.52, s * 0.42), s * 0.06, s * 0.06)
        p.drawRoundedRect(QRectF(s * 0.34, s * 0.38, s * 0.58, s * 0.47), s * 0.06, s * 0.06)
        _fill(p, c)
        p.drawEllipse(QPointF(s * 0.49, s * 0.52), s * 0.05, s * 0.05)
        p.setPen(Qt.NoPen)
        p.drawPath(_path(
            [(s * 0.38, s * 0.81), (s * 0.52, s * 0.61), (s * 0.62, s * 0.73),
             (s * 0.7, s * 0.65), (s * 0.88, s * 0.81)]
        ))

    return d


def _sign(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        _pen(p, c, s * 0.085)
        path = QPainterPath()
        path.moveTo(s * 0.12, s * 0.7)
        path.cubicTo(s * 0.3, s * 0.22, s * 0.4, s * 0.86, s * 0.54, s * 0.44)
        path.cubicTo(s * 0.64, s * 0.14, s * 0.68, s * 0.8, s * 0.9, s * 0.36)
        p.drawPath(path)
        p.drawLine(QPointF(s * 0.12, s * 0.86), QPointF(s * 0.88, s * 0.86))

    return d


def _pen_tool(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.08, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(
            _path(
                [(s * 0.2, s * 0.8), (s * 0.28, s * 0.44), (s * 0.56, s * 0.16),
                 (s * 0.72, s * 0.32), (s * 0.56, s * 0.6), (s * 0.44, s * 0.62), (s * 0.2, s * 0.8)],
                close=True,
            )
        )
        p.drawLine(QPointF(s * 0.56, s * 0.62), QPointF(s * 0.6, s * 0.88))

    return d


def _keyboard(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        _pen(p, c, s * 0.07)
        p.drawRoundedRect(QRectF(s * 0.12, s * 0.28, s * 0.76, s * 0.46), s * 0.07, s * 0.07)
        _fill(p, c)
        for r in range(2):
            for col in range(4):
                p.drawRect(QRectF(s * (0.22 + col * 0.14), s * (0.37 + r * 0.12), s * 0.08, s * 0.07))
        p.drawRect(QRectF(s * 0.36, s * 0.61, s * 0.28, s * 0.07))

    return d


def _highlight(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.3, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(s * 0.16, s * 0.44), QPointF(s * 0.84, s * 0.44))
        _pen(p, c, s * 0.08)
        for x in (0.18, 0.26, 0.5, 0.58, 0.8):
            p.drawLine(QPointF(s * x, s * 0.44), QPointF(s * x - s * 0.05, s * 0.78))

    return d


def _underline(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        _pen(p, c, s * 0.08)
        for x in (0.2, 0.28, 0.52, 0.6, 0.8):
            p.drawLine(QPointF(s * x, s * 0.24), QPointF(s * x - s * 0.05, s * 0.58))
        p.setPen(QPen(QColor(c), s * 0.09, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(s * 0.14, s * 0.78), QPointF(s * 0.86, s * 0.78))

    return d


def _strike(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        _pen(p, c, s * 0.08)
        for x in (0.2, 0.28, 0.52, 0.6, 0.8):
            p.drawLine(QPointF(s * x, s * 0.24), QPointF(s * x - s * 0.05, s * 0.58))
        p.setPen(QPen(QColor(c), s * 0.09, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(s * 0.14, s * 0.41), QPointF(s * 0.86, s * 0.41))

    return d


def _squiggle(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        _pen(p, c, s * 0.08)
        for x in (0.2, 0.28, 0.52, 0.6, 0.8):
            p.drawLine(QPointF(s * x, s * 0.24), QPointF(s * x - s * 0.05, s * 0.58))
        path = QPainterPath()
        path.moveTo(s * 0.12, s * 0.74)
        x = s * 0.12
        up = True
        while x < s * 0.88:
            path.lineTo(x + s * 0.06, s * 0.68 if up else s * 0.8)
            up = not up
            x += s * 0.06
        p.setPen(QPen(QColor(c), s * 0.07, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(path)

    return d


def _rect(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        _pen(p, c, s * 0.08)
        p.drawRect(QRectF(s * 0.16, s * 0.24, s * 0.68, s * 0.52))

    return d


def _circle(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        _pen(p, c, s * 0.08)
        p.drawEllipse(QRectF(s * 0.16, s * 0.2, s * 0.68, s * 0.6))

    return d


def _line(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.09, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(s * 0.18, s * 0.82), QPointF(s * 0.82, s * 0.18))

    return d


def _arrow(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.09, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawLine(QPointF(s * 0.16, s * 0.84), QPointF(s * 0.78, s * 0.22))
        p.drawPath(_path([(s * 0.78, s * 0.22), (s * 0.5, s * 0.26), (s * 0.74, s * 0.5)], close=True))

    return d


def _ink(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        path = QPainterPath()
        path.moveTo(s * 0.12, s * 0.74)
        path.cubicTo(s * 0.3, s * 0.16, s * 0.42, s * 0.9, s * 0.56, s * 0.42)
        path.cubicTo(s * 0.66, s * 0.16, s * 0.74, s * 0.7, s * 0.9, s * 0.3)
        p.setPen(QPen(QColor(c), s * 0.085, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(path)

    return d


def _note(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.075))
        p.setBrush(Qt.NoBrush)
        p.drawPath(
            _path(
                [(s * 0.2, s * 0.18), (s * 0.8, s * 0.18), (s * 0.8, s * 0.62),
                 (s * 0.56, s * 0.86), (s * 0.2, s * 0.62)],
                close=True,
            )
        )
        _fill(p, c)
        for y in (0.34, 0.46, 0.58):
            p.drawRect(QRectF(s * 0.32, s * y, s * 0.36, s * 0.05))

    return d


def _stamp(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.075))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(s * 0.14, s * 0.3, s * 0.72, s * 0.4), s * 0.06, s * 0.06)
        _fill(p, c)
        p.drawRect(QRectF(s * 0.26, s * 0.42, s * 0.48, s * 0.07))
        p.drawRect(QRectF(s * 0.26, s * 0.53, s * 0.3, s * 0.06))

    return d


def _select(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.075, Qt.DashLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(s * 0.18, s * 0.18, s * 0.64, s * 0.64))
        _fill(p, c)
        for pt in ((0.18, 0.18), (0.82, 0.18), (0.18, 0.82), (0.82, 0.82)):
            p.drawRect(QRectF(s * pt[0] - s * 0.045, s * pt[1] - s * 0.045, s * 0.09, s * 0.09))

    return d


def _hand(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.075, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawPath(
            _path(
                [(s * 0.34, s * 0.84), (s * 0.24, s * 0.6), (s * 0.2, s * 0.4),
                 (s * 0.28, s * 0.38), (s * 0.34, s * 0.54), (s * 0.32, s * 0.22),
                 (s * 0.42, s * 0.2), (s * 0.44, s * 0.5), (s * 0.46, s * 0.16),
                 (s * 0.56, s * 0.16), (s * 0.57, s * 0.5), (s * 0.62, s * 0.26),
                 (s * 0.71, s * 0.29), (s * 0.68, s * 0.62), (s * 0.6, s * 0.84)],
                close=True,
            )
        )

    return d


def _zoom_in(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.09, Qt.SolidLine, Qt.RoundCap))
        p.drawEllipse(QRectF(s * 0.16, s * 0.16, s * 0.52, s * 0.52))
        p.drawLine(QPointF(s * 0.62, s * 0.62), QPointF(s * 0.86, s * 0.86))
        p.drawLine(QPointF(s * 0.28, s * 0.42), QPointF(s * 0.56, s * 0.42))
        p.drawLine(QPointF(s * 0.42, s * 0.28), QPointF(s * 0.42, s * 0.56))

    return d


def _zoom_out(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.09, Qt.SolidLine, Qt.RoundCap))
        p.drawEllipse(QRectF(s * 0.16, s * 0.16, s * 0.52, s * 0.52))
        p.drawLine(QPointF(s * 0.62, s * 0.62), QPointF(s * 0.86, s * 0.86))
        p.drawLine(QPointF(s * 0.28, s * 0.42), QPointF(s * 0.56, s * 0.42))

    return d


def _fit_page(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.075))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(s * 0.2, s * 0.14, s * 0.6, s * 0.72))
        _fill(p, c)
        for pt in ((0.12, 0.5), (0.88, 0.5), (0.5, 0.06), (0.5, 0.94)):
            p.drawPolygon(
                QPolygonF(
                    [
                        QPointF(s * pt[0], s * pt[1]),
                        QPointF(s * (pt[0] - 0.07), s * (pt[1] - 0.05)),
                        QPointF(s * (pt[0] - 0.07), s * (pt[1] + 0.05)),
                    ]
                )
            )

    return d


def _rotazione(s: float, c: str, orario: bool) -> None:
    """Freccia circolare di rotazione: ``↻`` per ``orario``, ``↺`` al contrario.

    Le due icone erano l'una la copia speculare dell'altra con la punta della
    freccia piccola e di lato: a 22 pixel, nella barra, si leggevano come due
    "C" identici e i due pulsanti di rotazione sembravano duplicati. Ora
    l'arco ha il varco in alto e la punta, grossa e tangente, guarda nel verso
    della rotazione: la destra e' un arco che gira a destra, la sinistra il suo
    contrario, e non si confondono piu'.
    """
    def d(p: QPainter) -> None:
        cx = cy = s * 0.5
        r = s * 0.30
        # angoli in gradi di Qt: 0 a destra, positivo in senso antiorario
        a0 = 40.0 if orario else 140.0
        passo = -300.0 if orario else 300.0
        p.setPen(QPen(QColor(c), s * 0.09, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(cx - r, cy - r, r * 2, r * 2), a0 * 16, passo * 16)

        fine = a0 + passo
        lunga = s * 0.135
        _fill(p, c)
        p.drawPolygon(
            QPolygonF(
                [
                    _polare(cx, cy, fine, r + lunga),
                    _polare(cx, cy, fine - 21.0, r),
                    _polare(cx, cy, fine + 21.0, r),
                ]
            )
        )

    return d


def _polare(cx: float, cy: float, gradi: float, raggio: float) -> QPointF:
    a = math.radians(gradi)
    return QPointF(cx + raggio * math.cos(a), cy - raggio * math.sin(a))


def _rotate_left(s: float, c: str) -> None:
    return _rotazione(s, c, orario=False)


def _rotate_right(s: float, c: str) -> None:
    return _rotazione(s, c, orario=True)


def _search(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.085, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(s * 0.16, s * 0.16, s * 0.5, s * 0.5))
        p.drawLine(QPointF(s * 0.6, s * 0.6), QPointF(s * 0.86, s * 0.86))

    return d


def _freccia(s: float, c: str, verso: int) -> None:
    """Freccia dritta, punta a sinistra (``verso`` -1) o a destra (``verso`` 1).

    Annulla e ripeti erano due archi con la punta addosso, cioe' le stesse
    frecce circolari della rotazione: nella barra i quattro pulsanti di
    annulla, ripeti, ruota a sinistra e ruota a destra sembravano due coppie
    identiche. Le frecce dritte, con la punta rivolta nel verso dell'azione,
    si distinguono a colpo d'occhio anche a 22 pixel.
    """
    def d(p: QPainter) -> None:
        meta = s * 0.5
        punta = s * 0.14 if verso < 0 else s * 0.86
        p.setPen(QPen(QColor(c), s * 0.09, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        # l'asta parte dalla base della punta e arriva al lato opposto
        p.drawLine(
            QPointF(punta + verso * s * 0.2, meta),
            QPointF(s * (0.86 if verso < 0 else 0.14), meta),
        )
        _fill(p, c)
        p.drawPolygon(
            QPolygonF(
                [
                    QPointF(punta, meta),
                    QPointF(s * (0.34 if verso < 0 else 0.66), s * 0.28),
                    QPointF(s * (0.34 if verso < 0 else 0.66), s * 0.72),
                ]
            )
        )

    return d


def _undo(s: float, c: str) -> None:
    return _freccia(s, c, -1)


def _redo(s: float, c: str) -> None:
    return _freccia(s, c, 1)


def _print(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.075))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(s * 0.2, s * 0.12, s * 0.6, s * 0.24), s * 0.04, s * 0.04)
        p.drawRoundedRect(QRectF(s * 0.14, s * 0.4, s * 0.72, s * 0.34), s * 0.04, s * 0.04)
        _pen(p, c, s * 0.06)
        p.drawRect(QRectF(s * 0.28, s * 0.62, s * 0.44, s * 0.26))
        _fill(p, c)
        p.drawEllipse(QPointF(s * 0.78, s * 0.48), s * 0.035, s * 0.035)

    return d


def _add_page(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.075))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(s * 0.16, s * 0.12, s * 0.52, s * 0.68))
        p.setPen(QPen(QColor(c), s * 0.08, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(s * 0.7, s * 0.5), QPointF(s * 0.92, s * 0.5))
        p.drawLine(QPointF(s * 0.81, s * 0.39), QPointF(s * 0.81, s * 0.61))

    return d


def _trash(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.075, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(s * 0.16, s * 0.26), QPointF(s * 0.84, s * 0.26))
        p.drawPath(
            _path(
                [(s * 0.26, s * 0.26), (s * 0.32, s * 0.88), (s * 0.68, s * 0.88), (s * 0.74, s * 0.26)]
            )
        )
        p.drawPath(_path([(s * 0.38, s * 0.26), (s * 0.38, s * 0.14), (s * 0.62, s * 0.14), (s * 0.62, s * 0.26)]))

    return d


def _form(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        _page(p, s, c)
        _pen(p, c, s * 0.06)
        for i in range(3):
            y = s * (0.36 + i * 0.2)
            p.drawLine(QPointF(s * 0.3, y), QPointF(s * 0.56, y))
            p.drawRect(QRectF(s * 0.6, y - s * 0.09, s * 0.2, s * 0.12))

    return d


def _lock(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.08, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(s * 0.24, s * 0.44, s * 0.52, s * 0.4), s * 0.07, s * 0.07)
        p.drawArc(QRectF(s * 0.34, s * 0.16, s * 0.32, s * 0.36), 0, 180 * 16)
        _fill(p, c)
        p.drawEllipse(QPointF(s * 0.5, s * 0.62), s * 0.05, s * 0.05)

    return d


def _shield(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.075))
        p.setBrush(Qt.NoBrush)
        p.drawPath(
            _path(
                [(s * 0.5, s * 0.1), (s * 0.86, s * 0.26), (s * 0.86, s * 0.54),
                 (s * 0.5, s * 0.9), (s * 0.14, s * 0.54), (s * 0.14, s * 0.26)],
                close=True,
            )
        )
        p.drawLine(QPointF(s * 0.32, s * 0.5), QPointF(s * 0.45, s * 0.64))
        p.drawLine(QPointF(s * 0.45, s * 0.64), QPointF(s * 0.7, s * 0.36))

    return d


def _export(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.075))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(s * 0.16, s * 0.42, s * 0.68, s * 0.42))
        p.setBrush(QBrush(QColor(c)))
        p.setPen(Qt.NoPen)
        p.drawPath(_path([(s * 0.5, s * 0.1), (s * 0.78, s * 0.38), (s * 0.22, s * 0.38)], close=True))

    return d


def _bookmark(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.075))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(s * 0.2, s * 0.12, s * 0.6, s * 0.76), s * 0.05, s * 0.05)
        p.drawLine(QPointF(s * 0.34, s * 0.12), QPointF(s * 0.34, s * 0.88))
        p.drawLine(QPointF(s * 0.5, s * 0.3), QPointF(s * 0.68, s * 0.3))
        p.drawLine(QPointF(s * 0.5, s * 0.46), QPointF(s * 0.68, s * 0.46))
        p.drawLine(QPointF(s * 0.5, s * 0.62), QPointF(s * 0.62, s * 0.62))

    return d


def _attach(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.075, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(s * 0.7, s * 0.3), QPointF(s * 0.34, s * 0.66))
        p.drawArc(QRectF(s * 0.24, s * 0.34, s * 0.34, s * 0.34), 90 * 16, 180 * 16)
        p.drawArc(QRectF(s * 0.46, s * 0.34, s * 0.34, s * 0.34), 270 * 16, 180 * 16)

    return d


def _comment(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.075))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(s * 0.12, s * 0.16, s * 0.76, s * 0.54), s * 0.1, s * 0.1)
        p.drawPath(_path([(s * 0.3, s * 0.7), (s * 0.3, s * 0.9), (s * 0.48, s * 0.7)]))

    return d


def _pages(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.07))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(s * 0.1, s * 0.2, s * 0.4, s * 0.56))
        p.drawRect(QRectF(s * 0.26, s * 0.14, s * 0.4, s * 0.56))
        p.drawRect(QRectF(s * 0.42, s * 0.2, s * 0.44, s * 0.6))

    return d


def _fullscreen(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.09, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        for x, y, dx, dy in ((0.16, 0.16, 1, 1), (0.84, 0.16, -1, 1), (0.16, 0.84, 1, -1), (0.84, 0.84, -1, -1)):
            p.drawLine(QPointF(s * x, s * y + dy * s * 0.2), QPointF(s * x, s * y))
            p.drawLine(QPointF(s * x, s * y), QPointF(s * x + dx * s * 0.2, s * y))

    return d


def _align_left(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.08, Qt.SolidLine, Qt.RoundCap))
        for w, y in ((0.6, 0.26), (0.44, 0.44), (0.6, 0.62), (0.36, 0.78)):
            p.drawLine(QPointF(s * 0.18, s * y), QPointF(s * (0.18 + w), s * y))

    return d


def _align_center(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.08, Qt.SolidLine, Qt.RoundCap))
        for w, y in ((0.6, 0.26), (0.44, 0.44), (0.6, 0.62), (0.36, 0.78)):
            p.drawLine(QPointF(s * (0.5 - w / 2), s * y), QPointF(s * (0.5 + w / 2), s * y))

    return d


def _align_right(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.08, Qt.SolidLine, Qt.RoundCap))
        for w, y in ((0.6, 0.26), (0.44, 0.44), (0.6, 0.62), (0.36, 0.78)):
            p.drawLine(QPointF(s * (0.82 - w), s * y), QPointF(s * 0.82, s * y))

    return d


def _close(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.1, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(s * 0.26, s * 0.26), QPointF(s * 0.74, s * 0.74))
        p.drawLine(QPointF(s * 0.74, s * 0.26), QPointF(s * 0.26, s * 0.74))

    return d


def _grid(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.06))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(s * 0.14, s * 0.14, s * 0.72, s * 0.72))
        for i in (1, 2):
            p.drawLine(QPointF(s * 0.14, s * (0.14 + i * 0.24)), QPointF(s * 0.86, s * (0.14 + i * 0.24)))
            p.drawLine(QPointF(s * (0.14 + i * 0.24), s * 0.14), QPointF(s * (0.14 + i * 0.24), s * 0.86))

    return d


def _magic(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.09, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(s * 0.3, s * 0.86), QPointF(s * 0.66, s * 0.2))
        p.drawLine(QPointF(s * 0.56, s * 0.9), QPointF(s * 0.78, s * 0.5))
        _fill(p, c)
        for pt, r in (((0.24, 0.26), 0.05), ((0.82, 0.2), 0.04), ((0.2, 0.6), 0.035)):
            p.drawEllipse(QPointF(s * pt[0], s * pt[1]), s * r, s * r)

    return d


def _crop(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.07))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(s * 0.16, s * 0.16, s * 0.68, s * 0.68))
        p.setPen(QPen(QColor(c), s * 0.09, Qt.SolidLine, Qt.RoundCap))
        for pt in ((0.3, 0.14), (0.3, 0.86), (0.14, 0.3), (0.86, 0.3)):
            pass
        p.drawLine(QPointF(s * 0.3, s * 0.16), QPointF(s * 0.3, s * 0.34))
        p.drawLine(QPointF(s * 0.7, s * 0.16), QPointF(s * 0.7, s * 0.34))
        p.drawLine(QPointF(s * 0.3, s * 0.66), QPointF(s * 0.3, s * 0.84))
        p.drawLine(QPointF(s * 0.7, s * 0.66), QPointF(s * 0.7, s * 0.84))
        p.drawLine(QPointF(s * 0.16, s * 0.3), QPointF(s * 0.34, s * 0.3))
        p.drawLine(QPointF(s * 0.16, s * 0.7), QPointF(s * 0.34, s * 0.7))
        p.drawLine(QPointF(s * 0.66, s * 0.3), QPointF(s * 0.84, s * 0.3))
        p.drawLine(QPointF(s * 0.66, s * 0.7), QPointF(s * 0.84, s * 0.7))

    return d


def _ocr(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        _page(p, s, c)
        p.setPen(QPen(QColor(c), s * 0.07, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(s * 0.32, s * 0.4), QPointF(s * 0.5, s * 0.4))
        p.drawLine(QPointF(s * 0.32, s * 0.52), QPointF(s * 0.62, s * 0.52))
        p.drawLine(QPointF(s * 0.32, s * 0.64), QPointF(s * 0.46, s * 0.64))
        _fill(p, c)
        p.drawRect(QRectF(s * 0.56, s * 0.3, s * 0.24, s * 0.06))

    return d


def _text_field(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        _pen(p, c, s * 0.07)
        p.drawRect(QRectF(s * 0.14, s * 0.36, s * 0.72, s * 0.3))
        p.setPen(QPen(QColor(c), s * 0.06, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(s * 0.24, s * 0.56), QPointF(s * 0.6, s * 0.56))
        p.drawLine(QPointF(s * 0.24, s * 0.44), QPointF(s * 0.44, s * 0.44))

    return d


def _check(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.08))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(s * 0.16, s * 0.16, s * 0.68, s * 0.68), s * 0.08, s * 0.08)
        p.setPen(QPen(QColor(c), s * 0.11, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPolyline(QPolygonF([QPointF(s * 0.32, s * 0.52), QPointF(s * 0.44, s * 0.66), QPointF(s * 0.7, s * 0.34)]))

    return d


def _radio(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.08))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(s * 0.16, s * 0.16, s * 0.68, s * 0.68))
        _fill(p, c)
        p.drawEllipse(QPointF(s * 0.5, s * 0.5), s * 0.16, s * 0.16)

    return d


def _dropdown(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.08))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(s * 0.12, s * 0.28, s * 0.76, s * 0.44), s * 0.06, s * 0.06)
        p.setPen(QPen(QColor(c), s * 0.07, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(s * 0.24, s * 0.5), QPointF(s * 0.6, s * 0.5))
        _fill(p, c)
        p.drawPolygon(
            QPolygonF([QPointF(s * 0.64, s * 0.46), QPointF(s * 0.8, s * 0.46), QPointF(s * 0.72, s * 0.58)])
        )

    return d


def _handwrite(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.085, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        path = QPainterPath()
        path.moveTo(s * 0.1, s * 0.72)
        path.cubicTo(s * 0.24, s * 0.3, s * 0.34, s * 0.82, s * 0.46, s * 0.5)
        path.cubicTo(s * 0.56, s * 0.26, s * 0.62, s * 0.78, s * 0.72, s * 0.46)
        path.cubicTo(s * 0.78, s * 0.3, s * 0.84, s * 0.5, s * 0.9, s * 0.36)
        p.drawPath(path)

    return d


def _replace(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.08, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawLine(QPointF(s * 0.14, s * 0.7), QPointF(s * 0.5, s * 0.34))
        p.drawLine(QPointF(s * 0.5, s * 0.34), QPointF(s * 0.86, s * 0.34))
        p.drawPolyline(QPolygonF([QPointF(s * 0.76, s * 0.24), QPointF(s * 0.86, s * 0.34), QPointF(s * 0.76, s * 0.44)]))

    return d


def _merge(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.07))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(s * 0.1, s * 0.3, s * 0.36, s * 0.42))
        p.drawRect(QRectF(s * 0.4, s * 0.24, s * 0.36, s * 0.42))
        p.drawRect(QRectF(s * 0.56, s * 0.36, s * 0.34, s * 0.42))

    return d


def _split(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.07))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(s * 0.16, s * 0.12, s * 0.34, s * 0.4))
        p.drawRect(QRectF(s * 0.16, s * 0.56, s * 0.34, s * 0.4))
        p.setPen(QPen(QColor(c), s * 0.09, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(s * 0.6, s * 0.22), QPointF(s * 0.9, s * 0.22))
        p.drawLine(QPointF(s * 0.6, s * 0.5), QPointF(s * 0.9, s * 0.5))
        p.drawLine(QPointF(s * 0.6, s * 0.78), QPointF(s * 0.9, s * 0.78))

    return d


def _flatten(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        p.setPen(QPen(QColor(c), s * 0.08))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(s * 0.16, s * 0.2, s * 0.68, s * 0.3), s * 0.05, s * 0.05)
        p.setBrush(QBrush(QColor(c)))
        p.setPen(Qt.NoPen)
        p.drawPath(_path([(s * 0.42, s * 0.66), (s * 0.58, s * 0.66), (s * 0.5, s * 0.86)], close=True))
        p.drawRect(QRectF(s * 0.16, s * 0.6, s * 0.68, s * 0.05))

    return d


def _redact(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        _page(p, s, c)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(c)))
        p.drawRect(QRectF(s * 0.26, s * 0.46, s * 0.48, s * 0.14))

    return d


def _highlight_fields(s: float, c: str) -> None:
    def d(p: QPainter) -> None:
        _page(p, s, c)
        p.setPen(QPen(QColor(c), s * 0.06, Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(s * 0.28, s * 0.34, s * 0.44, s * 0.13))
        p.drawRect(QRectF(s * 0.28, s * 0.56, s * 0.3, s * 0.13))

    return d


DRAWERS: dict[str, Callable[[float, str], Callable[[QPainter], None]]] = {
    "doc": _doc,
    "doc-open": _doc_open,
    "save": _save,
    "text": _text,
    "image": _image,
    "images": _images,
    "sign": _sign,
    "pen": _pen_tool,
    "keyboard": _keyboard,
    "highlight": _highlight,
    "underline": _underline,
    "strikeout": _strike,
    "squiggly": _squiggle,
    "rect": _rect,
    "circle": _circle,
    "line": _line,
    "arrow": _arrow,
    "ink": _ink,
    "note": _note,
    "stamp": _stamp,
    "select": _select,
    "hand": _hand,
    "zoom-in": _zoom_in,
    "zoom-out": _zoom_out,
    "fit-page": _fit_page,
    "rotate-left": _rotate_left,
    "rotate-right": _rotate_right,
    "search": _search,
    "undo": _undo,
    "redo": _redo,
    "print": _print,
    "add-page": _add_page,
    "trash": _trash,
    "form": _form,
    "lock": _lock,
    "shield": _shield,
    "export": _export,
    "bookmark": _bookmark,
    "attach": _attach,
    "comment": _comment,
    "pages": _pages,
    "fullscreen": _fullscreen,
    "align-left": _align_left,
    "align-center": _align_center,
    "align-right": _align_right,
    "close": _close,
    "grid": _grid,
    "magic": _magic,
    "crop": _crop,
    "ocr": _ocr,
    "text-field": _text_field,
    "check": _check,
    "radio": _radio,
    "dropdown": _dropdown,
    "handwrite": _handwrite,
    "replace": _replace,
    "merge": _merge,
    "split": _split,
    "flatten": _flatten,
    "redact": _redact,
    "fields": _highlight_fields,
}


def _path(points: list[tuple[float, float]], close: bool = False) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(points[0][0], points[0][1])
    for x, y in points[1:]:
        path.lineTo(x, y)
    if close:
        path.closeSubpath()
    return path


def _disegna(pm: QPixmap, drawer, size: float, color: str) -> None:
    """Disegna un'icona e, se il disegno fallisce, lo segnala.

    Prima l'errore veniva inghiotito e l'icona restava semplicemente vuota:
    ``Qt.RashCap`` al posto di ``Qt.RoundCap`` faceva sparire l'icona dello
    strumento predefinito, e non si vedeva nulla in barra. Un'icona rotta e'
    un difetto silenzioso, quindi ora avvisa.
    """
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    try:
        drawer(size, color)(p)
    except Exception as exc:
        p.end()
        warnings.warn(f"icona non disegnata: {exc!r}", RuntimeWarning, stacklevel=2)
        return
    p.end()


def icon(name: str, color: str = "#2b303a", size: int = 22) -> QIcon:
    """Icona vettoriale, con cache per colore e dimensione."""
    key = (name, color, size)
    hit = Cache.get(key)
    if hit is not None:
        return hit
    drawer = DRAWERS.get(name, DRAWERS["doc"])
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    _disegna(pm, drawer, size, color)
    ic = QIcon(pm)
    Cache[key] = ic
    return ic


def app_icon(size: int = 256) -> QIcon:
    """Icona dell'applicazione: foglio con penna stilografica.

    E' l'unica che non passava da `icon()` e quindi non aveva cache: veniva
    ridisegnata a ogni chiamata, e il desktop la chiede piu' volte per le
    dimensioni diverse del riquadro, del menu del programma e delle anteprime.
    Sono 256×256 pixel ridisegnati ogni volta, circa 2 ms.
    """
    hit = AppIconCache.get(size)
    if hit is not None:
        return hit
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    s = size
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor("#ffffff")))
    p.drawRoundedRect(QRectF(s * 0.14, s * 0.08, s * 0.62, s * 0.84), s * 0.06, s * 0.06)
    p.setBrush(QBrush(QColor("#e6ebf2")))
    p.drawRect(QRectF(s * 0.14, s * 0.08, s * 0.62, s * 0.1))
    p.setPen(QPen(QColor("#9aa6b8"), s * 0.018))
    p.setBrush(Qt.NoBrush)
    for y in (0.32, 0.44, 0.56, 0.68):
        p.drawLine(QPointF(s * 0.24, s * y), QPointF(s * 0.66, s * y))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor("#2f6fdb")))
    p.drawPath(
        _path(
            [
                (s * 0.36, s * 0.86), (s * 0.44, s * 0.66), (s * 0.74, s * 0.24),
                (s * 0.86, s * 0.34), (s * 0.66, s * 0.62), (s * 0.56, s * 0.68),
            ],
            close=True,
        )
    )
    p.setBrush(QBrush(QColor("#ffffff")))
    p.drawEllipse(QPointF(s * 0.8, s * 0.3), s * 0.03, s * 0.03)
    p.end()
    icona = QIcon(pm)
    AppIconCache[size] = icona
    return icona


def pixmap(name: str, color: str = "#2b303a", size: int = 22) -> QPixmap:
    """Versione come immagine, per l'anteprima nei pulsanti."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    _disegna(pm, DRAWERS.get(name, DRAWERS["doc"]), size, color)
    return pm
