"""Elementi grafici per la visualizzazione delle pagine.

Ogni pagina e' un ``PageNode`` che disegna il proprio rendering e ospita gli
elementi interattivi (campi modulo, annotazioni selezionate). Le coordinate sono
espresse in punti PDF: la vista applica lo zoom, quindi il disegno e' indipendente
dalla risoluzione.
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QComboBox,
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QStyleOptionGraphicsItem,
    QWidget,
)

from ..core import document as docmod
from ..ui import theme

HANDLE = 8
HANDLE_HIT = 11


def pixmap_to_qimage(pix) -> QImage:
    """Converte un ``pymupdf.Pixmap`` in ``QImage`` senza copie superflue."""
    n = pix.n
    if n == 1:
        fmt = QImage.Format_Grayscale8
    elif n == 3:
        fmt = QImage.Format_RGB888
    elif n == 4:
        fmt = QImage.Format_RGBA8888
    else:
        fmt = QImage.Format_RGB888
    data = bytes(pix.samples)
    img = QImage(data, pix.width, pix.height, pix.stride, fmt)
    return img.copy()  # owns its buffer


def pixmap_to_qpixmap(pix) -> QPixmap:
    """``pymupdf.Pixmap`` -> ``QPixmap``."""
    return QPixmap.fromImage(pixmap_to_qimage(pix))


def pil_to_qpixmap(img) -> QPixmap:
    """Immagine Pillow -> ``QPixmap`` (con alpha se presente).

    La conversione diretta da ``QImage.loadFromData`` fallisce su alcuni buffer,
    quindi si passa da un costruttore esplicito.
    """
    if img is None:
        return QPixmap()
    if img.mode == "RGBA":
        data = img.tobytes("raw", "RGBA")
        qimg = QImage(data, img.width, img.height, img.width * 4, QImage.Format_RGBA8888)
    elif img.mode == "RGB":
        data = img.tobytes("raw", "RGB")
        qimg = QImage(data, img.width, img.height, img.width * 3, QImage.Format_RGB888)
    elif img.mode == "L":
        data = img.tobytes("raw", "L")
        qimg = QImage(data, img.width, img.height, img.width, QImage.Format_Grayscale8)
    else:
        img = img.convert("RGBA")
        return pil_to_qpixmap(img)
    return QPixmap.fromImage(qimg.copy())


class PageNode(QGraphicsObject):
    """Una pagina: rendering, griglia, ombra e contenuti interattivi."""

    def __init__(self, view: "PdfView", index: int, width: float, height: float) -> None:
        super().__init__()
        self.view = view
        self.index = index
        self._w = width
        self._h = height
        self._pixmap: QPixmap | None = None
        self._pixmap_key: Any = None
        self.setFlag(QGraphicsItem.ItemUsesExtendedStyleOption, True)
        self.setAcceptHoverEvents(True)
        self.setCacheMode(QGraphicsItem.DeviceCoordinateCache)
        self.setZValue(0)

    # --------------------------------------------------------------- geometria

    def page_size(self) -> tuple[float, float]:
        return self._w, self._h

    def set_page_size(self, w: float, h: float) -> None:
        self.prepareGeometryChange()
        self._w, self._h = w, h

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._w, self._h)

    def refresh_pixmap(self) -> None:
        self._pixmap = None
        self._pixmap_key = None
        self.update()

    # ------------------------------------------------------------------ disegno

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None) -> None:
        pal = self.view.palette
        rect = self.boundingRect()
        scale = self.view.current_zoom()

        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(pal.surface)))
        painter.drawRect(rect)

        pix = self._ensure_pixmap(scale)
        if pix is not None:
            # Il pixmap viene generato alla scala corrente per essere nitido,
            # ma il nodo misura la pagina in punti: va quindi adattato al
            # riquadro del nodo. Disegnandolo alla sua dimensione naturale
            # finiva più grande del proprio riquadro, e l'errore cresceva con
            # lo zoom: l'immagine della pagina e gli sovrapposti (campi,
            # annotazioni) finivano su due sistemi di coordinate diversi.
            painter.drawPixmap(rect, pix, QRectF(pix.rect()))

        if self.view.doc and getattr(self.view.doc, "doc", None) is not None:
            if self.view.grid_visible():
                self._paint_grid(painter, rect)

        painter.setRenderHint(QPainter.Antialiasing, True)
        self._paint_content_overlays(painter, rect)
        self._paint_field_values(painter)

    def _ensure_pixmap(self, scale: float) -> QPixmap | None:
        doc = self.view.doc
        if doc is None or not doc.is_open:
            return None
        key = (round(scale, 4), doc.view_rotation(self.index))
        if self._pixmap is not None and self._pixmap_key == key:
            return self._pixmap
        try:
            pix = doc.render(self.index, zoom=scale)
        except Exception:
            return None
        self._pixmap = pixmap_to_qpixmap(pix)
        self._pixmap_key = key
        return self._pixmap

    def _paint_grid(self, painter: QPainter, rect: QRectF) -> None:
        pal = self.view.palette
        step = self.view.grid_size()
        if step <= 0:
            return
        scale = self.view.current_zoom()
        if step * scale < 4:
            return
        pen = QPen(QColor(pal.grid))
        pen.setWidthF(0.4)
        pen.setCosmetic(True)
        painter.setPen(pen)
        x = step
        while x < rect.width():
            painter.drawLine(QPointF(x, 0), QPointF(x, rect.height()))
            x += step
        y = step
        while y < rect.height():
            painter.drawLine(QPointF(0, y), QPointF(rect.width(), y))
            y += step

    def _paint_content_overlays(self, painter: QPainter, rect: QRectF) -> None:
        """Evidenzia i campi modulo riconosciuti.

        Le annotazioni non vengono circondate: i loro bordi sono gia' disegnati
        dal rendering della pagina e un riquadro aggiuntivo coprirebbe il testo.
        """
        doc = self.view.doc
        if doc is None or not doc.is_open or not self.view.highlight_fields:
            return
        pal = self.view.palette
        active = self.view.active_field
        for f in doc.fields(self.index):
            if active == (self.index, f.xref):
                continue
            r = doc.to_display_rect(self.index, f.rect)
            if r.is_empty:
                continue
            color = QColor(pal.signature) if f.kind == "signature" else QColor(pal.field_border)
            pen = QPen(color)
            pen.setWidthF(1.0)
            pen.setCosmetic(True)
            painter.setPen(pen)
            fill = QColor(color)
            fill.setAlpha(20)
            painter.setBrush(QBrush(fill))
            painter.drawRect(QRectF(r.x0, r.y0, r.width, r.height))

    def _paint_field_values(self, painter: QPainter) -> None:
        """Disegna il valore del campo attivo, per un aggiornamento immediato.

        I campi non attivi sono gia' disegnati dal rendering della pagina (PyMuPDF
        rigenera l'aspetto del widget a ogni ``update()``): ridisegnarli qui
        produrrebbe testo sovrapposto. Il valore del campo in editing viene invece
        ridisegnato sopra uno sfondo opaco, cosi' la digitazione e' immediata
        senza dover rasterizzare la pagina a ogni tasto.
        """
        view = self.view
        doc = view.doc
        if doc is None or not doc.is_open or view.active_field is None:
            return
        page, xref = view.active_field
        if page != self.index:
            return
        state = view.field_states.get((page, xref))
        if state is None:
            return
        info = state["info"]
        value = state.get("value")
        r = doc.to_display_rect(page, info.rect)
        if r.is_empty:
            return
        q = QRectF(r.x0, r.y0, r.width, r.height)
        pal = view.palette
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(pal.field_bg)))
        painter.drawRect(q)
        if info.kind == "toggle":
            self._paint_check(painter, q, value not in (False, "Off", "", None), pal)
        elif info.kind == "choice":
            self._paint_choice(painter, q, str(value or ""), info, pal)
        elif info.kind == "button":
            self._paint_button(painter, q, str(value or info.name or "OK"), pal)
        elif info.kind == "signature":
            self._paint_signature_slot(painter, q, bool(info.is_signed), pal)
        else:
            shown = str(value or "")
            if info.password and shown:
                shown = "\u2022" * min(12, len(shown))
            self._paint_text(painter, q, shown, info, pal)

    def _field_pen(self, pal: theme.Palette) -> QPen:
        """Il bordo del campo in compilazione: accento e un filo piu' spesso.

        Il parametro «attivo» che c'era prima non e' stato tolto perche' non
        c'e' una seconda forma di disegnare il campo: la pagina rasterizzata
        porta gia' i campi inattivi, questo codice disegna solo quello aperto.
        """
        pen = QPen(QColor(pal.accent))
        pen.setWidthF(1.1)
        pen.setCosmetic(True)
        return pen

    def _paint_text(self, painter: QPainter, q: QRectF, value: str, info, pal) -> None:
        if not value:
            return
        size = max(3.0, float(info.fontsize or 11.0))
        font = QFont(_qt_font_family(info.font), int(round(size)))
        font.setPointSizeF(size)
        painter.setFont(font)
        painter.setPen(QPen(QColor(pal.text)))
        painter.drawText(q.adjusted(2, 0, -2, 0), int(Qt.AlignLeft | Qt.AlignVCenter), value)

    def _paint_check(self, painter: QPainter, q: QRectF, on: bool, pal) -> None:
        size = min(q.width(), q.height()) * 0.72
        box = QRectF(q.center().x() - size / 2, q.center().y() - size / 2, size, size)
        painter.setPen(self._field_pen(pal))
        painter.setBrush(QBrush(QColor(pal.surface)))
        painter.drawRect(box)
        if on:
            pen = QPen(QColor(pal.accent))
            pen.setWidthF(max(1.2, size * 0.14))
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawPolyline(
                QPolygonF(
                    [
                        QPointF(box.left() + box.width() * 0.22, box.center().y()),
                        QPointF(box.center().x() - box.width() * 0.04, box.bottom() - box.height() * 0.24),
                        QPointF(box.right() - box.width() * 0.18, box.top() + box.height() * 0.22),
                    ]
                )
            )

    def _paint_choice(self, painter: QPainter, q: QRectF, value: str, info, pal) -> None:
        size = max(3.0, float(info.fontsize or 11.0))
        font = QFont(_qt_font_family(info.font), int(round(size)))
        painter.setFont(font)
        painter.setPen(QColor(pal.text))
        painter.drawText(q.adjusted(3, 0, -14, 0), int(Qt.AlignLeft | Qt.AlignVCenter), value)
        pen = QPen(QColor(pal.text_dim))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        cx = q.right() - 6
        cy = q.center().y()
        painter.drawPolyline(
            QPolygonF([QPointF(cx - 4, cy - 2), QPointF(cx, cy + 2), QPointF(cx + 4, cy - 2)])
        )

    def _paint_button(self, painter: QPainter, q: QRectF, value: str, pal) -> None:
        painter.setPen(self._field_pen(pal))
        painter.setBrush(QBrush(QColor(pal.accent_soft)))
        painter.drawRoundedRect(q, 2, 2)
        font = QFont()
        font.setPointSizeF(max(3.0, min(9.0, q.height() * 0.42)))
        painter.setFont(font)
        painter.setPen(QColor(pal.text))
        painter.drawText(q, int(Qt.AlignCenter), value)

    def _paint_signature_slot(self, painter: QPainter, q: QRectF, signed: bool, pal) -> None:
        color = QColor(pal.signature)
        pen = QPen(color)
        pen.setWidthF(1.1)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(pal.field_bg)))
        painter.drawRoundedRect(q, 2, 2)
        font = QFont()
        font.setPointSizeF(max(3.5, min(8.0, q.height() * 0.34)))
        font.setItalic(True)
        painter.setFont(font)
        painter.setPen(color)
        label = "Firma presente" if signed else "Firma qui"
        painter.drawText(q, int(Qt.AlignCenter), label)


def _qt_font_family(pdf_font: str) -> str:
    """Traduce il nome font PDF in una famiglia Qt."""
    name = (pdf_font or "Helv").lower()
    if name.startswith(("cour", "cobo", "cobi")):
        return "Courier New"
    if name.startswith(("tiro", "tibo", "tiit")):
        return "Times New Roman"
    return "Helvetica"


class SelectionItem(QGraphicsObject):
    """Riquadro di selezione con maniglie di ridimensionamento."""

    def __init__(self, view: "PdfView") -> None:
        super().__init__()
        self.view = view
        self.rect = QRectF()
        self.zones: list[tuple[QRectF, str]] = []
        self.visible_sel = False
        self.setZValue(1000)
        self.setAcceptedMouseButtons(Qt.NoButton)

    def set_rect(self, rect: QRectF, show_handles: bool = True) -> None:
        self.prepareGeometryChange()
        self.rect = QRectF(rect)
        self.zones = self._build_zones() if show_handles else []
        self.update()

    def clear(self) -> None:
        self.prepareGeometryChange()
        self.rect = QRectF()
        self.zones = []
        self.update()

    def _build_zones(self) -> list[tuple[QRectF, str]]:
        r = self.rect
        h = HANDLE
        cx, cy = r.center().x(), r.center().y()
        pts = {
            "nw": (r.left(), r.top()),
            "n": (cx, r.top()),
            "ne": (r.right(), r.top()),
            "e": (r.right(), cy),
            "se": (r.right(), r.bottom()),
            "s": (cx, r.bottom()),
            "sw": (r.left(), r.bottom()),
            "w": (r.left(), cy),
        }
        return [(QRectF(x - h / 2, y - h / 2, h, h), name) for name, (x, y) in pts.items()]

    def boundingRect(self) -> QRectF:
        m = HANDLE
        return self.rect.adjusted(-m, -m, m, m)

    def zone_at(self, pos: QPointF) -> str:
        """Nome della maniglia sotto il punto.

        Le maniglie sono disegnate grandi ``HANDLE`` ma afferrabili su
        ``HANDLE_HIT``: i riquadri vivono in coordinate di scena, quindi a zoom
        basso una maniglia da 8 punti diventa un paio di pixel e non si
        prende più.
        """
        for r, nome in self.zones:
            if r.adjusted(-(HANDLE_HIT - HANDLE) / 2, -(HANDLE_HIT - HANDLE) / 2,
                          (HANDLE_HIT - HANDLE) / 2, (HANDLE_HIT - HANDLE) / 2).contains(pos):
                return nome
        return ""

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None) -> None:
        if self.rect.isNull():
            return
        pal = self.view.palette
        pen = QPen(QColor(pal.selection))
        pen.setWidthF(1.2)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(self.rect)
        # i colori delle maniglie stanno nella palette, come gli altri: erano
        # fermi sul tema chiario e a tema scuro restavano bianchi con bordo
        # blu, quindi non si vedevano
        fill = QPen(QColor(pal.handle_border))
        fill.setWidthF(1.0)
        painter.setPen(fill)
        painter.setBrush(QBrush(QColor(pal.handle_fill)))
        for r, _ in self.zones:
            painter.drawRect(r)


class TextSelectionItem(QGraphicsObject):
    """Evidenziazione delle parole selezionate con il mouse.

    Copre solo i riquadri delle parole scelte, come in Acrobat: un rettangolo
    pieno coprirebbe anche le righe vuote e sarebbe fuorviante.
    """

    def __init__(self, view: "PdfView") -> None:
        super().__init__()
        self.view = view
        self.rects: list[QRectF] = []
        self.setZValue(950)
        self.setAcceptedMouseButtons(Qt.NoButton)

    def set_rects(self, rects: list[QRectF]) -> None:
        self.prepareGeometryChange()
        self.rects = [QRectF(r) for r in rects]
        self.update()

    def clear(self) -> None:
        self.prepareGeometryChange()
        self.rects = []
        self.update()

    def boundingRect(self) -> QRectF:
        if not self.rects:
            return QRectF()
        return self.rects[0].united(self.rects[-1]).adjusted(-2, -2, 2, 2)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None) -> None:
        if not self.rects:
            return
        pal = self.view.palette
        painter.setPen(Qt.NoPen)
        # lo stesso azzurro usato dal cursore di inserimento del testo
        painter.setBrush(QColor(47, 111, 219, 70))
        for r in self.rects:
            painter.drawRect(r)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(pal.selection), 0))
        for r in self.rects:
            painter.drawRect(r)


class ToolOverlay(QGraphicsObject):
    """Disegno in corso per gli strumenti a trascinamento."""

    def __init__(self, view: "PdfView") -> None:
        super().__init__()
        self.view = view
        self.rect = QRectF()
        self.points: list[QPointF] = []
        self.guides: list[tuple[float, float, float, float]] = []
        self.mode = ""
        self.color = QColor("#2f6fdb")
        self.setZValue(900)
        self.setAcceptedMouseButtons(Qt.NoButton)

    def set_rect(self, rect: QRectF, mode: str = "rect", color: str = "#2f6fdb") -> None:
        self.prepareGeometryChange()
        self.rect = QRectF(rect)
        self.mode = mode
        self.color = QColor(color)
        self.points = []
        self.guides = []
        self.update()

    def set_points(self, points: list[QPointF], mode: str = "line", color: str = "#2f6fdb") -> None:
        self.prepareGeometryChange()
        self.points = list(points)
        self.rect = QRectF()
        self.guides = []
        self.mode = mode
        self.color = QColor(color)
        self.update()

    def set_guides(self, guides: list[tuple[float, float, float, float]], color: str = "#e0803a") -> None:
        """Le linee di riferimento del magnetismo, gia' in coordinate di scena.

        Sono state calcolate e mai disegnate: senza di esse l'utente vede
        l'elemento che scatta ma non sa a cosa si e' agganciato.
        """
        self.prepareGeometryChange()
        self.guides = list(guides)
        if guides:
            self.guide_color = QColor(color)
        self.update()

    def clear(self) -> None:
        self.prepareGeometryChange()
        self.rect = QRectF()
        self.points = []
        self.guides = []
        self.update()

    def boundingRect(self) -> QRectF:
        box = QRectF()
        if self.points:
            xs = [p.x() for p in self.points]
            ys = [p.y() for p in self.points]
            m = 40
            box = QRectF(min(xs) - m, min(ys) - m, max(xs) - min(xs) + 2 * m, max(ys) - min(ys) + 2 * m)
        elif not self.rect.isNull():
            box = self.rect.adjusted(-30, -30, 30, 30)
        for x1, y1, x2, y2 in self.guides:
            box = box.united(QRectF(x1, y1, x2, y2).normalized().adjusted(-4, -4, 4, 4))
        return box

    def _paint_guides(self, painter: QPainter) -> None:
        if not self.guides:
            return
        pen = QPen(getattr(self, "guide_color", QColor("#e0803a")))
        pen.setWidthF(1.0)
        pen.setStyle(Qt.DashLine)
        pen.setCosmetic(True)
        painter.setPen(pen)
        for x1, y1, x2, y2 in self.guides:
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None) -> None:
        pen = QPen(self.color)
        pen.setWidthF(1.4)
        pen.setCosmetic(True)
        if self.mode in ("rect", "circle", "line", "arrow", "polygon", "polyline", "highlight", "signature"):
            pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.setRenderHint(QPainter.Antialiasing, True)
        self._paint_guides(painter)
        m = self.mode
        if m == "circle":
            painter.drawEllipse(self.rect)
        elif m in ("line", "arrow"):
            if len(self.points) >= 2:
                painter.drawLine(self.points[0], self.points[1])
                if m == "arrow":
                    self._arrow_head(painter, self.points[0], self.points[1])
        elif m in ("ink", "freehand"):
            if len(self.points) >= 2:
                painter.setPen(QPen(self.color, 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                painter.drawPolyline(QPolygonF(self.points))
        elif m in ("polygon", "polyline"):
            if len(self.points) >= 2:
                painter.drawPolyline(QPolygonF(self.points))
        elif m in ("highlight", "select"):
            if not self.rect.isNull():
                fill = QColor(self.color)
                fill.setAlpha(60 if m == "highlight" else 26)
                painter.setBrush(QBrush(fill))
                painter.drawRect(self.rect)
        else:
            if not self.rect.isNull():
                painter.drawRect(self.rect)

    def _arrow_head(self, painter: QPainter, a: QPointF, b: QPointF) -> None:
        import math

        ang = math.atan2(b.y() - a.y(), b.x() - a.x())
        size = 11.0
        p1 = QPointF(b.x() - size * math.cos(ang - 0.42), b.y() - size * math.sin(ang - 0.42))
        p2 = QPointF(b.x() - size * math.cos(ang + 0.42), b.y() - size * math.sin(ang + 0.42))
        painter.setBrush(QBrush(self.color))
        painter.drawPolygon(QPolygonF([b, p1, p2]))


class LinkItem(QGraphicsRectItem):
    """Collegamento cliccabile sovrapposto alla pagina.

    Era un ``QGraphicsPathItem`` con una ``setRect`` che quell tipo non ha:
    appena se ne creava uno il programma si fermava con un errore. Per questo
    non era mai comparso in pagina nessun riquadro cliccabile, e il collegamento
    si poteva creare e leggere ma non usare.
    """

    def __init__(self, view: "PdfView", page: int, rect: QRectF, uri: str, azione=None) -> None:
        super().__init__()
        self.view = view
        self.page = page
        self.uri = uri
        self.azione = azione
        self.setRect(rect)
        self.setPen(QPen(QColor(view.palette.accent), 0.8, Qt.DotLine))
        self.setBrush(Qt.NoBrush)
        self.setCursor(Qt.PointingHandCursor)
        self.setZValue(5)
        self.setToolTip(uri)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton:
            if self.azione is not None:
                self.azione()
            else:
                self.view.open_link(self.uri)
        super().mousePressEvent(event)
