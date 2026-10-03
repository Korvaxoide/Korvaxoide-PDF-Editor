"""Tela per disegnare la firma con mouse, stilo o tastiera."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QWidget

from ...signature import render as sigrender
from ...signature import strokes as sk


class DrawPad(QWidget):
    """Area di disegno che raccoglie i tratti e li mostra in tempo reale.

    E' pensata per essere usata sia come editor a schermo intero sia come
    anteprima: il disegno e' mantenuto come lista di punti, quindi la firma puo'
    essere ridimensionata senza perdita.
    """

    stroke_finished = Signal()
    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.canvas = sk.SignatureCanvas(width=560.0, height=200.0)
        self.setMinimumSize(320, 150)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self._drawing = False
        self._active: sk.Stroke | None = None
        self._last: QPointF | None = None
        self._pressure = 1.0
        self.pen_color = QColor("#101828")
        self.pen_width = 2.6
        self.show_guide = True
        self.enabled = True

    # ------------------------------------------------------------------ stato

    def set_pen(self, color: str, width: float) -> None:
        self.pen_color = QColor(color)
        self.pen_width = float(width)
        self.canvas.default_style.color = (self.pen_color.red(), self.pen_color.green(), self.pen_color.blue())
        self.canvas.default_style.width = float(width)
        self.update()

    def clear(self) -> None:
        self.canvas.clear()
        self._active = None
        self.update()
        self.changed.emit()

    def undo(self) -> bool:
        if self.canvas.undo_stroke():
            self.update()
            self.changed.emit()
            return True
        return False

    def is_empty(self) -> bool:
        return self.canvas.is_empty

    def set_canvas(self, data: dict) -> None:
        self.canvas = sk.SignatureCanvas.from_dict(data)
        self.update()
        self.changed.emit()

    def to_image(self, scale: float = 2.0) -> QPixmap:
        """Firma come immagine trasparente."""
        from ..page_items import pil_to_qpixmap

        return pil_to_qpixmap(sigrender.render_strokes(self.canvas, scale=scale))

    # ---------------------------------------------------------------- disegno

    def paintEvent(self, event) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(QColor("#c8ccd4")))
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawRoundedRect(rect, 6, 6)

        if self.show_guide:
            self._paint_guide(p, rect)

        p.save()
        p.setClipRect(rect)
        self._paint_strokes(p)
        p.restore()

        if self.canvas.is_empty:
            p.setPen(QColor("#9aa2b1"))
            f = QFont()
            f.setPointSize(11)
            p.setFont(f)
            p.drawText(rect, int(Qt.AlignCenter), "Disegna qui la tua firma con il mouse o lo stilo")
        p.end()

    def _paint_guide(self, p: QPainter, rect: QRectF) -> None:
        pen = QPen(QColor("#dfe3e9"))
        pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        baseline = rect.bottom() - rect.height() * 0.30
        p.drawLine(QPointF(rect.left() + 12, baseline), QPointF(rect.right() - 12, baseline))
        p.setPen(QColor("#b6bcc7"))
        f = QFont()
        f.setPointSize(7)
        p.setFont(f)
        p.drawText(QRectF(rect.left() + 14, baseline - 15, 120, 14), int(Qt.AlignLeft | Qt.AlignVCenter), "riga di base")

    def _paint_strokes(self, p: QPainter) -> None:
        for s in self.canvas.strokes:
            pts = s.smoothed()
            if not pts:
                continue
            col = QColor(*s.style.color)
            if len(pts) == 1:
                x, y = pts[0]
                r = max(0.7, s.style.width / 2)
                p.setPen(Qt.NoPen)
                p.setBrush(QBrush(col))
                p.drawEllipse(QPointF(x, y), r, r)
                continue
            for i in range(len(pts) - 1):
                w0 = s.widths[i] if i < len(s.widths) else s.style.width
                w1 = s.widths[i + 1] if i + 1 < len(s.widths) else s.style.width
                w0 = w0 if s.style.pressure else s.style.width
                w1 = w1 if s.style.pressure else s.style.width
                steps = 3
                for k in range(steps):
                    f0, f1 = k / steps, (k + 1) / steps
                    ax = pts[i][0] + (pts[i + 1][0] - pts[i][0]) * f0
                    ay = pts[i][1] + (pts[i + 1][1] - pts[i][1]) * f0
                    bx = pts[i][0] + (pts[i + 1][0] - pts[i][0]) * f1
                    by = pts[i][1] + (pts[i + 1][1] - pts[i][1]) * f1
                    th = (w0 * (1 - f0) + w1 * f0)
                    pen = QPen(col, max(0.6, th), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
                    p.setPen(pen)
                    p.drawLine(QPointF(ax, ay), QPointF(bx, by))
            lx, ly = pts[-1]
            lw = (s.widths[-1] if s.widths else s.style.width)
            r = max(0.7, (lw if s.style.pressure else s.style.width) / 2)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(col))
            p.drawEllipse(QPointF(lx, ly), r, r)

    # ---------------------------------------------------------------- eventi

    def _pos(self, event) -> QPointF:
        return QPointF(event.position())

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if not self.enabled or event.button() != Qt.LeftButton:
            return
        self._drawing = True
        self.setFocus()
        self.canvas.default_style.color = (self.pen_color.red(), self.pen_color.green(), self.pen_color.blue())
        self.canvas.default_style.width = self.pen_width
        # _pos restituisce un QPointF, che non e' iterabile: lo spacchettamento
        # sollevava un TypeError al primo clic e il riquadro di disegno della
        # firma non accettava nessun tratto
        p = self._pos(event)
        self._active = self.canvas.new_stroke(p.x(), p.y(), self.pen_width)
        self._last = p
        self.update()

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if not self._drawing or self._active is None:
            return
        p = self._pos(event)
        # pressione dello stilo: in Qt 6 si legge dagli event point.
        # QMouseEvent non ha piu' point(), chiamarlo sollevava un TypeError a
        # ogni movimento del mouse e il tracciato si interrompeva subito.
        try:
            for punto in event.points():
                pr = punto.pressure()
                if 0 < pr <= 1.0:
                    self._pressure = 0.45 + pr * 0.85
                break
        except (AttributeError, TypeError):
            pass
        self._active.add(p.x(), p.y(), self.pen_width * self._pressure)
        self._last = p
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if not self._drawing:
            return
        self._drawing = False
        self._active = None
        self._pressure = 1.0
        self.update()
        self.stroke_finished.emit()
        self.changed.emit()

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        if self._drawing:
            self._drawing = False
            self._active = None
            self.update()
        super().leaveEvent(event)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        # La firma viene eseguita su una tela fissa: si adatta alle proporzioni.
        w, h = max(1.0, float(self.width())), max(1.0, float(self.height()))
        scale = min(w / self.canvas.width, h / self.canvas.height)
        self.update()
