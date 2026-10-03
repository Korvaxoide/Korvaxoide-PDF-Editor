"""Pannello delle miniature con riordino per trascinamento."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QMimeData, QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QDrag, QFont, QPainter, QPen, QPixmap
from PySide6.QtCore import QModelIndex
from PySide6.QtWidgets import (
    QAbstractItemView,
    QStyle,
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QWidget,
)

from ..core import document as docmod
from ..core import units
from . import icons, theme
from .page_items import pixmap_to_qpixmap

MIME = "application/x-korvaxoide-pdf-editor-pages"


class PageThumb(QListWidgetItem):
    """Miniatura di una pagina."""

    def __init__(self, index: int, view: "ThumbnailsPanel") -> None:
        super().__init__()
        self.index = index
        self.panel = view
        self._pix: QPixmap | None = None
        self.setSizeHint(QSize(view.thumb_width() + 28, view.thumb_height() + 34))
        self.setFlags(self.flags() | Qt.ItemIsDragEnabled)
        self.setData(Qt.UserRole, index)
        self.setData(Qt.UserRole + 1, self)

    def refresh(self) -> None:
        self._pix = None
        self.panel.schedule(self.index)

    def pixmap(self) -> QPixmap | None:
        if self._pix is not None:
            return self._pix
        doc = self.panel.doc
        if doc is None or not doc.is_open or self.index >= doc.page_count:
            return None
        try:
            w = self.panel.thumb_width()
            pix = doc.render_thumbnail(self.index, w)
            self._pix = pixmap_to_qpixmap(pix)
        except Exception:
            self._pix = None
        return self._pix


class ThumbDelegate(QStyledItemDelegate):
    """Disegna la miniatura della pagina.

    ``QListWidgetItem.paint`` non viene invocata dal delegate predefinito di Qt,
    quindi il disegno delle miniature vive qui.
    """

    def __init__(self, panel: "ThumbnailsPanel") -> None:
        super().__init__(panel.list)
        # ``QObject.parent`` e' un metodo: il pannello va tenuto esplicitamente.
        self.panel = panel

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        panel = self.panel
        item = index.data(Qt.UserRole + 1)
        thumb = item if isinstance(item, PageThumb) else None
        pal = panel.palette
        painter.save()
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor(pal.accent_soft))
        elif option.state & QStyle.State_MouseOver:
            painter.fillRect(option.rect, QColor(pal.surface_alt))

        rect = option.rect
        area = QRect(rect.x() + 8, rect.y() + 6, rect.width() - 16, rect.height() - 30)
        pm = thumb.pixmap() if thumb is not None else None
        if pm is not None and not pm.isNull():
            target = pm.scaled(area.width(), area.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = area.x() + (area.width() - target.width()) // 2
            y = area.y() + (area.height() - target.height()) // 2
            pen = QPen(QColor(pal.border_strong))
            pen.setWidthF(1.0)
            painter.setPen(pen)
            painter.setBrush(QColor("#ffffff"))
            painter.drawRect(QRect(x - 1, y - 1, target.width() + 2, target.height() + 2))
            painter.drawPixmap(x, y, target)
        else:
            painter.setPen(QColor(pal.text_disabled))
            f = QFont()
            f.setPointSize(8)
            painter.setFont(f)
            painter.drawText(area, int(Qt.AlignCenter), str(thumb.index + 1 if thumb else ""))

        if option.state & QStyle.State_Selected:
            pen = QPen(QColor(pal.accent), 1.6)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect.adjusted(1, 1, -2, -2))

        label = QRect(rect.x() + 10, rect.bottom() - 24, rect.width() - 20, 19)
        number = str(thumb.index + 1 if thumb else "")
        if option.state & QStyle.State_Selected:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(pal.accent))
            painter.drawRoundedRect(label, 7, 7)
        f = QFont()
        f.setPointSize(7)
        painter.setFont(f)
        painter.setPen(QColor("#ffffff") if option.state & QStyle.State_Selected else QColor(pal.text_dim))
        painter.drawText(label, int(Qt.AlignCenter), number)
        painter.restore()


class ThumbnailsPanel(QWidget):
    """Elenco delle miniature con selezione multipla e riordino."""

    page_activated = Signal(int)
    selection_changed = Signal(list)
    reorder_requested = Signal(list)
    context_action = Signal(str, list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.doc: docmod.Document | None = None
        self.palette = theme.corrente()
        self._pending: set[int] = set()
        self._width = theme.METRICS.thumb_w
        self.list = QListWidget(self)
        self.list.setViewMode(QListWidget.ListMode)
        self.list.setFlow(QListWidget.LeftToRight)
        self.list.setWrapping(True)
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setIconSize(QSize(self._width, self._width))
        self.list.setSpacing(6)
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.setUniformItemSizes(False)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        lay = __import__("PySide6.QtWidgets", fromlist=["QVBoxLayout"]).QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addWidget(self.list)
        self.delegate = ThumbDelegate(self)
        self.list.setItemDelegate(self.delegate)
        self.list.itemClicked.connect(self._on_click)
        self.list.itemSelectionChanged.connect(self._on_selection)
        self.list.customContextMenuRequested.connect(self._on_menu)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.model().rowsMoved.connect(self._on_rows_moved)
        self.list.model().rowsInserted.connect(lambda *_: self._resort())
        self.list.model().rowsRemoved.connect(lambda *_: self._resort())
        self.list.setDragDropOverwriteMode(False)
        self._suppress_reorder = False

    # ------------------------------------------------------------------- stato

    def set_document(self, doc: docmod.Document | None) -> None:
        self.doc = doc
        self.rebuild()

    def set_palette_colors(self, pal: theme.Palette) -> None:
        self.palette = pal
        self.list.viewport().update()

    def set_width(self, value: int) -> None:
        self._width = max(70, min(320, int(value)))
        self.list.setIconSize(QSize(self._width, self._width))
        for i in range(self.list.count()):
            self.list.item(i).setSizeHint(QSize(self._width + 28, self.thumb_height() + 34))
        self.list.viewport().update()

    def thumb_width(self) -> int:
        return self._width

    def thumb_height(self) -> int:
        doc = self.doc
        if doc is None or not doc.is_open:
            return int(self._width * 1.414)
        try:
            r = doc.page_info(0).rect
        except Exception:
            return int(self._width * 1.414)
        ratio = r.height / max(r.width, 1)
        return int(self._width * min(max(ratio, 0.3), 3.2))

    def set_doc(self, doc: docmod.Document | None) -> None:
        self.set_document(doc)

    # -------------------------------------------------------------- popolamento

    def rebuild(self) -> None:
        self._suppress_reorder = True
        self.list.clear()
        doc = self.doc
        if doc is not None and doc.is_open:
            for i in range(doc.page_count):
                self.list.addItem(PageThumb(i, self))
        self._suppress_reorder = False
        self.list.viewport().update()

    def refresh_all(self) -> None:
        for i in range(self.list.count()):
            item = self.list.item(i)
            if isinstance(item, PageThumb):
                item.refresh()
        self.list.viewport().update()

    def refresh_page(self, index: int) -> None:
        for i in range(self.list.count()):
            item = self.list.item(i)
            if isinstance(item, PageThumb) and item.index == index:
                item.refresh()
                self.list.viewport().update()
                return

    def schedule(self, index: int) -> None:
        """Carica la miniatura in modo differito (solo se visibile)."""
        self._pending.add(index)
        for i in range(self.list.count()):
            item = self.list.item(i)
            if isinstance(item, PageThumb) and item.index == index:
                if item.pixmap() is not None:
                    self._pending.discard(index)
                self.list.viewport().update()
                return

    def _on_click(self, item: QListWidgetItem) -> None:
        if isinstance(item, PageThumb):
            self.page_activated.emit(item.index)

    def _on_selection(self) -> None:
        self.selection_changed.emit(self.selected_pages())

    def _on_rows_moved(self, *args) -> None:
        if self._suppress_reorder:
            return
        order = self.order()
        if sorted(order) == list(range(len(order))):
            self.reorder_requested.emit(order)

    def _resort(self) -> None:
        if self._suppress_reorder:
            return
        for pos in range(self.list.count()):
            item = self.list.item(pos)
            if isinstance(item, PageThumb):
                item.index = pos
                item.setData(Qt.UserRole, pos)

    # ---------------------------------------------------------------- selezione

    def order(self) -> list[int]:
        out = []
        for i in range(self.list.count()):
            item = self.list.item(i)
            if isinstance(item, PageThumb):
                out.append(item.index)
        return out

    def selected_pages(self) -> list[int]:
        out = []
        for item in self.list.selectedItems():
            if isinstance(item, PageThumb):
                out.append(item.index)
        return sorted(out)

    def select_pages(self, pages: list[int]) -> None:
        self._suppress_reorder = True
        self.list.clearSelection()
        for p in pages:
            item = self.list.item(p)
            if item is not None:
                item.setSelected(True)
        self._suppress_reorder = False
        self.selection_changed.emit(sorted(pages))

    def select_page(self, index: int) -> None:
        item = self.list.item(index)
        if item is None:
            return
        self._suppress_reorder = True
        self.list.clearSelection()
        item.setSelected(True)
        self.list.scrollToItem(item)
        self._suppress_reorder = False
        self.selection_changed.emit([index])

    def current_page(self) -> int:
        sel = self.selected_pages()
        return sel[0] if sel else 0

    # ------------------------------------------------------------ menu contesto

    def _on_menu(self, pos: QPoint) -> None:
        pages = self.selected_pages()
        if not pages:
            return
        menu = QMenu(self)
        entries = [
            ("rotate_left", "Ruota a sinistra", "rotate-left"),
            ("rotate_right", "Ruota a destra", "rotate-right"),
            (None, None, None),
            ("duplicate", "Duplica", "pages"),
            ("extract", "Estrai in un nuovo documento", "export"),
            (None, None, None),
            ("delete", "Elimina", "trash"),
            ("insert_after", "Inserisci pagina vuota dopo", "add-page"),
            (None, None, None),
            ("select_all", "Seleziona tutte", "check"),
        ]
        for key, label, ico in entries:
            if key is None:
                menu.addSeparator()
                continue
            act = QAction(icons.icon(ico, self.palette.text, 18), label, menu)
            act.triggered.connect(lambda _c=False, k=key: self.context_action.emit(k, pages))
            menu.addAction(act)
        menu.exec(self.list.viewport().mapToGlobal(pos))
