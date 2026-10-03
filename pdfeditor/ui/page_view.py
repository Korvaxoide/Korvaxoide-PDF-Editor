"""Vista del documento: scena, zoom, panoramica e strumenti di disegno."""

from __future__ import annotations

import math
from typing import Any, Callable

from PySide6.QtCore import QEvent, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QGuiApplication,
    QKeySequence,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QComboBox,
    QGraphicsScene,
    QGraphicsView,
    QLineEdit,
    QPlainTextEdit,
    QWidget,
)

from ..core import geometry as geo
from ..core import document as docmod
from ..core import units
from . import icons, theme
from .page_items import (
    LinkItem,
    PageNode,
    SelectionItem,
    TextSelectionItem,
    ToolOverlay,
    pixmap_to_qpixmap,
)

# Strumenti disponibili
TOOLS = (
    "select",
    "hand",
    "text",
    "image",
    "signature",
    "highlight",
    "underline",
    "strikeout",
    "squiggly",
    "ink",
    "note",
    "rect",
    "circle",
    "line",
    "arrow",
    "polygon",
    "stamp",
    "link",
    "field_text",
    "field_check",
    "field_radio",
    "field_combo",
    "field_button",
    "redact",
)

DRAG_TOOLS = {"rect", "circle", "field_text", "field_check", "field_radio", "field_combo", "field_button", "redact", "image"}
POINT_TOOLS = {"note", "stamp", "link", "text", "freetext", "signature", "field_text"}
LINE_TOOLS = {"line", "arrow"}
POLY_TOOLS = {"ink", "polygon", "highlight", "underline", "strikeout", "squiggly"}

#: Dimensione data a uno strumento quando l'utente preme e rilascia senza
#: trascinare. Senza questo, un semplice clic non produceva nulla: il campo
#: richiedeva una dimensione minima e il resto degli strumenti restava muto.
AREA_CLIC: dict[str, tuple[float, float]] = {
    "field_text": (200.0, 26.0),
    "field_check": (18.0, 18.0),
    "field_radio": (18.0, 18.0),
    "field_combo": (140.0, 24.0),
    "field_button": (90.0, 24.0),
    "rect": (90.0, 60.0),
    "circle": (90.0, 60.0),
    "redact": (90.0, 24.0),
    "image": (90.0, 60.0),
}


def _posizione(event) -> QPoint:
    """Il punto del mouse in coordinate del widget.

    In Qt 6 ``QMouseEvent.pos()`` e' deprecato e ogni chiamata emette un
    avviso: la posizione si legge da ``position()``, che pero' restituisce un
    ``QPointF``. Qui si riconverte a ``QPoint`` perche' ``mapToScene`` e gli
    arrotondamenti delle maniglie lavorano su interi, e la differenza di
    mezzo punto cambierebbe il riquadro agganciato dal magnetismo.
    """
    try:
        return event.position().toPoint()
    except AttributeError:  # pragma: no cover - solo per Qt 5
        return event.pos()


class PdfScene(QGraphicsScene):
    """Scena contenente un nodo per ogni pagina."""

    def __init__(self, view: "PdfView") -> None:
        super().__init__()
        self.view = view
        self.nodes: list[PageNode] = []
        self.links: list[LinkItem] = []
        self.selection = SelectionItem(view)
        self.overlay = ToolOverlay(view)
        self.text_selection = TextSelectionItem(view)
        self.addItem(self.selection)
        self.addItem(self.overlay)
        self.addItem(self.text_selection)

    def rebuild(self) -> None:
        """Ricrea i nodi pagina in base allo stato del documento.

        Gli editor dei campi vanno rimossi *prima* di ``clear()``: la scena ne
        distrugge gli oggetti Qt e i proxy rimasti nella lista punterebbero a
        memoria liberata. Se pero' un campo era in fase di compilazione, l'editor
        viene riapperto subito dopo: altrimenti una ricostruzione durante la
        digitazione (per esempio cambiando la rotazione della pagina) farebbe
        perdere tutto quello che e' stato scritto.
        """
        attivo = self.view.active_field
        self.view.hide_field_editor()
        self.clear()
        self.nodes = []
        # `clear()` distrugge anche i riquadri dei collegamenti: la lista va
        # svuotata qui, altrimenti il giro dopo prova a togliere dalla scena
        # oggetti Qt gia' liberati e si ferma con un errore
        self.links = []
        self.selection = SelectionItem(self.view)
        self.overlay = ToolOverlay(self.view)
        self.text_selection = TextSelectionItem(self.view)
        self.addItem(self.selection)
        self.addItem(self.overlay)
        self.addItem(self.text_selection)
        doc = self.view.doc
        if doc is None or not doc.is_open:
            return
        y = 0.0
        gap = theme.METRICS.page_gap
        for i in range(doc.page_count):
            info = doc.page_info(i)
            node = PageNode(self.view, i, info.rect.width, info.rect.height)
            node.setPos(0, y)
            self.addItem(node)
            self.nodes.append(node)
            y += info.rect.height + gap
        self.setSceneRect(0, -gap, self._max_width(), y)
        self.view.load_field_states()
        self.rebuild_links()
        if attivo is not None and self.view.doc is not None:
            pagina, xref = attivo
            stato = self.view.field_states.get((pagina, xref))
            # Solo i campi di testo hanno un editor che vale la pena riaprire:
            # per gli altri la ricostruzione ripeterebbe l'azione che l'ha
            # causata (spuntare una casella, scegliere da un elenco, premere un
            # pulsante) e il ciclo non finiva
            if (
                0 <= pagina < self.view.doc.page_count
                and stato is not None
                and getattr(stato["info"], "kind", "") == "text"
            ):
                self.view.begin_field_edit(pagina, xref, seleziona_tutto=False)

    def rebuild_links(self) -> None:
        """Rifà i riquadri cliccabili dei collegamenti.

        I collegamenti non sono annotazioni: vivono in un array separato della
        pagina. Senza questo strato il collegamento si poteva creare e si leggeva
        nell'elenco, ma in pagina non c'era nulla da cliccare e il gestore
        esistendo non aveva mai chi lo chiamasse.
        """
        from shiboken6 import isValid

        for item in self.links:
            if isValid(item):
                self.removeItem(item)
        self.links = []
        doc = self.view.doc
        if doc is None or not doc.is_open or self.view.tool != "select":
            return
        for i in range(doc.page_count):
            node = self.node(i)
            if node is None:
                continue
            for l in doc.links(i):
                r = geo.Rect(l.get("rect") or geo.Rect())
                if r.is_empty:
                    continue
                uri = l.get("uri") or ""
                interno = l.get("page")
                if not uri and interno is None:
                    continue
                # un collegamento interno porta a un'altra pagina invece che a
                # un indirizzo: si passa la pagina di destinazione e la vista
                # ci va, al posto di mostrare un messaggio vuoto
                etichetta = uri or f"Pagina {interno + 1}"
                azione = None
                if not uri and interno is not None:
                    vista = self.view

                    def azione(destinazione=interno):  # type: ignore[misc]
                        vista.go_to_page(destinazione)
                disp = doc.to_display_rect(i, r)
                item = LinkItem(self.view, i, self.view._scene_rect(i, disp), etichetta, azione)
                self.addItem(item)
                self.links.append(item)

    def _max_width(self) -> float:
        if not self.nodes:
            return 100.0
        return max(n.page_size()[0] for n in self.nodes)

    def node(self, index: int) -> PageNode | None:
        return self.nodes[index] if 0 <= index < len(self.nodes) else None

    def index_at(self, y: float) -> int:
        """Indice della pagina sotto la coordinata di scena, ``-1`` nel vuoto.

        Prima ricadeva sull'ultima pagina: cliccando nel corridoio fra due
        pagine (o nella fascia sopra la prima) con uno strumento di disegno si
        disegnava sull'ultima pagina, e con lo strumento di selezione si
        afferrava un elemento che non era sotto il cursore.
        """
        for i, n in enumerate(self.nodes):
            r = n.sceneBoundingRect()
            if r.top() <= y < r.bottom():
                return i
        return -1 if self.nodes else 0

    def refresh_pixmaps(self) -> None:
        for n in self.nodes:
            n.refresh_pixmap()

    def sync_geometry(self) -> None:
        """Riallinea i nodi dopo un cambio di dimensione o rotazione."""
        doc = self.view.doc
        if doc is None or not doc.is_open:
            return
        y = 0.0
        gap = theme.METRICS.page_gap
        width = 0.0
        for i, n in enumerate(self.nodes):
            info = doc.page_info(i)
            n.set_page_size(info.rect.width, info.rect.height)
            n.setPos(0, y)
            n.refresh_pixmap()
            width = max(width, info.rect.width)
            y += info.rect.height + gap
        self.setSceneRect(0, -gap, width, y)


class PdfView(QGraphicsView):
    """Vista interattiva del documento con tutti gli strumenti."""

    status = Signal(str)
    page_changed = Signal(int)
    selection_changed = Signal(list)
    tool_changed = Signal(str)
    zoom_changed = Signal(float)
    link_activated = Signal(str)
    field_committed = Signal(int, int, object)
    signature_requested = Signal(int, object)
    request_tool_action = Signal(str, object)
    #: numero di parole selezionate con il mouse (0 se nessuna)
    text_selected = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.doc: docmod.Document | None = None
        self.palette = theme.corrente()
        self.tool = "select"
        self._zoom = 1.0
        self._zoom_mode = "fit_page"
        self._view_mode = "continuous"
        self.field_states: dict[tuple[int, int], dict[str, Any]] = {}
        self.active_field: tuple[int, int] | None = None
        self._editor: QWidget | None = None
        self._sel_page: int = -1
        self._sel_rect: geo.Rect | None = None
        self._sel_xref: int | None = None
        self._sel_kind: str = ""
        self.grid_on = False
        self.grid_step = 18.0
        self.highlight_fields = True
        self.snap_on = True
        self.snap_guides = True
        self.annots_color = "#c8362f"
        self.annots_width = 1.4
        self.annots_fill: str | None = None
        self.text_size = 12.0
        self.text_font = "helv"
        self.text_color = "#1b1f27"
        self._text_selection: tuple[int, geo.Rect] | None = None
        self._drag_from: QPointF | None = None
        self._drag_points: list[QPointF] = []
        self._drag_page = -1
        self._moving: dict[str, Any] = {}
        self._panning = False
        self._pan_origin = QPointF()
        self._space_down = False
        self._active_link: str = ""
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setFocusPolicy(Qt.StrongFocus)
        self.scene_obj = PdfScene(self)
        self.setScene(self.scene_obj)

    # ------------------------------------------------------------------ stato

    def set_document(self, doc: docmod.Document | None) -> None:
        self.doc = doc
        # La selezione apparteneva al documento precedente: lasciarla indietro
        # faceva fallire Ctrl+C e «Elimina» con «Indice pagina non valido»
        # dopo l'apertura di un altro file, e la finestra di ridimensionamento
        # restava disegnata a caso sulla pagina nuova.
        self._sel_page = -1
        self._sel_rect = None
        self._sel_xref = None
        self._sel_kind = ""
        self._moving = {}
        self._drag_from = None
        self._drag_points = []
        self._drag_page = -1
        self._text_selection = None
        self.scene_obj.rebuild()
        self.apply_zoom_mode()

    def set_palette_colors(self, pal: theme.Palette) -> None:
        self.palette = pal
        self.scene_obj.selection.update()
        self.scene_obj.refresh_pixmaps()
        self.viewport().update()

    def set_theme(self, pal: theme.Palette) -> None:
        self.set_palette_colors(pal)
        if self._editor is not None:
            # l'editor ha uno stile proprio, costruito con i colori del tema
            self._applica_stile_editor()
        self.viewport().update()

    def current_zoom(self) -> float:
        return self._zoom

    def current_page(self) -> int:
        if not self.scene_obj.nodes:
            return 0
        center = self.mapToScene(self.viewport().rect().center())
        idx = self.scene_obj.index_at(center.y())
        # nel corridoio fra le pagine si resta sulla pagina piu' vicina, come
        # fa Acrobat: nessuna pagina sotto il cursore non deve portare a zero
        return max(0, min(idx, len(self.scene_obj.nodes) - 1))

    def page_count(self) -> int:
        return len(self.scene_obj.nodes)

    def set_grid(self, on: bool, step: float = 18.0) -> None:
        self.grid_on = on
        self.grid_step = step
        self.viewport().update()

    def set_snap(self, on: bool, guides: bool = True) -> None:
        """Il magnetismo e le guide di riferimento che lo accompagnano."""
        self.snap_on = bool(on)
        self.snap_guides = bool(guides)
        if not self.snap_on:
            self.scene_obj.overlay.set_guides([])

    def snap_enabled(self) -> bool:
        return self.snap_on

    def grid_visible(self) -> bool:
        return self.grid_on

    def grid_size(self) -> float:
        return self.grid_step

    def set_highlight_fields(self, on: bool) -> None:
        self.highlight_fields = on
        self.viewport().update()

    def set_view_mode(self, mode: str) -> None:
        """``continuous``, ``single`` o ``facing``."""
        self._view_mode = mode
        self.scene_obj.sync_geometry()
        if mode == "single":
            self.set_page_visible_range(0, 0)
        else:
            self.set_page_visible_range(-1, -1)
        self.apply_zoom_mode()

    def view_mode(self) -> str:
        return self._view_mode

    def set_page_visible_range(self, first: int, last: int) -> None:
        for i, n in enumerate(self.scene_obj.nodes):
            visible = True if first < 0 else (first <= i <= last)
            n.setVisible(visible)
        if first >= 0:
            y = first * 0
            node = self.scene_obj.node(first)
            if node is not None:
                self.centerOn(node.sceneBoundingRect().center())
        self.viewport().update()

    def load_field_states(self) -> None:
        """Legge i campi dal documento e prepara il loro disegno e la compilazione."""
        self.hide_field_editor()
        self.field_states = {}
        self.active_field = None
        doc = self.doc
        if doc is None or not doc.is_open:
            return
        for i in range(doc.page_count):
            try:
                fields = doc.fields(i)
            except Exception:
                continue
            for f in fields:
                self.field_states[(i, f.xref)] = {
                    "info": f,
                    "value": f.value,
                    "password": f.password,
                }

    def refresh_field_states(self) -> None:
        """Ricarica i valori dei campi dopo una modifica al documento.

        I campi che non esistono più vengono tolti: tenere la loro voce faceva
        sì che il punto dove il campo era stato cancellato aprisse comunque una
        casella di testo, e quello che si digitava finiva nel nulla.
        """
        doc = self.doc
        if doc is None or not doc.is_open:
            return
        for (page, xref), state in list(self.field_states.items()):
            if not (0 <= page < doc.page_count):
                del self.field_states[(page, xref)]
                continue
            try:
                campi = {f.xref: f for f in doc.fields(page)}
            except Exception:
                campi = {}
            info = campi.get(xref)
            if info is None:
                del self.field_states[(page, xref)]
                continue
            state["info"] = info
            state["value"] = info.value
            state["password"] = info.password
        if self.active_field:
            page, xref = self.active_field
            state = self.field_states.get((page, xref))
            if state is None:
                self._distruggi_editor()
            else:
                self._sync_editor_value(state.get("value"))

    def _node(self, page: int):
        """Nodo della pagina, se esiste ed è ancora valido.

        Ricostruendo la scena i nodi vecchi vengono distrutti: usarli subito
        dopo, per esempio dallo scorrimento, provoca un errore fatale.
        """
        from shiboken6 import isValid

        node = self.scene_obj.node(page)
        if node is None or not isValid(node):
            return None
        return node

    def _scene_rect(self, page: int, rect) -> QRectF:
        """Riquadro di una pagina in coordinate di scena.

        Le coordinate di scena sono già espresse in punti: la scala allo
        schermo la fa la trasformazione della vista (``setTransform`` in
        ``set_zoom``). Moltiplicare qui per ``self._zoom`` applicherebbe lo
        zoom una seconda volta e ogni elemento finirebbe fuori posto.
        """
        node = self._node(page)
        if node is None:
            return QRectF()
        return QRectF(
            node.scenePos().x() + rect.x0,
            node.scenePos().y() + rect.y0,
            rect.width,
            rect.height,
        )

    def _scene_point(self, page: int, point) -> QPointF:
        """Punto di una pagina in coordinate di scena (vedi ``_scene_rect``)."""
        node = self._node(page)
        if node is None:
            return QPointF()
        return QPointF(node.scenePos().x() + point.x(), node.scenePos().y() + point.y())

    def _page_local(self, page: int, scene_pos: QPointF) -> QPointF:
        """Punto di scena riportato alla pagina, in punti (vedi ``_scene_rect``)."""
        node = self._node(page)
        if node is None:
            return QPointF()
        return QPointF(scene_pos.x() - node.scenePos().x(), scene_pos.y() - node.scenePos().y())

    def field_rect_viewport(self, page: int, xref: int) -> QRectF | None:
        """Riquadro del campo in coordinate viewport, per l'editor."""
        state = self.field_states.get((page, xref))
        if state is None or self.doc is None or self._node(page) is None:
            return None
        disp = self.doc.to_display_rect(page, state["info"].rect)
        return self.mapFromScene(self._scene_rect(page, disp)).boundingRect()

    def field_at(self, page: int, scene_pos: QPointF) -> tuple[int, int] | None:
        """Campo modulo sotto il puntatore, se presente.

        I campi padre dei gruppi di pulsanti di opzione vengono ignorati:
        coprono l'intera area del gruppo, quindi catturerebbero il clic su
        una qualunque delle opzioni senza attivare quella.
        """
        for (p, xref) in self.field_states:
            if p != page:
                continue
            node = self.scene_obj.node(page)
            if node is None or self.doc is None:
                continue
            info = self.field_states[(p, xref)]["info"]
            if getattr(info, "is_group", False):
                continue
            disp = self.doc.to_display_rect(page, info.rect)
            local = self._page_local(p, scene_pos)
            if geo.contains_point(disp, local.x(), local.y()):
                return (p, xref)
        return None

    def begin_field_edit(self, page: int, xref: int, seleziona_tutto: bool = True) -> None:
        """Apre l'editor sul campo e lo tiene aperto fino al click esterno.

        ``seleziona_tutto`` va disattivato quando l'editor viene riaperto dopo
        una ricostruzione della scena: selezionare tutto a metà della scrittura
        fa perdere il testo già digitato al carattere successivo.
        """
        rect = self.field_rect_viewport(page, xref)
        state = self.field_states.get((page, xref))
        if rect is None or state is None or self.doc is None:
            return
        info: docmod.FieldInfo = state["info"]
        if getattr(info, "is_group", False):
            # il padre di un gruppo non è un campo da compilare
            return
        if info.read_only:
            self.status.emit(f"Campo '{info.label}' in sola lettura")
            return
        self.hide_field_editor()
        self.active_field = (page, xref)
        kind = info.kind
        if kind == "toggle":
            # Una casella di spunta e un pulsante di opzione non hanno un editor
            # da tenere aperto: il campo attivo va chiuso PRIMA di scrivere il
            # valore. La modifica notifica un cambiamento di pagine, che
            # ricostruisce la scena e riaprirebbe l'editor su quel campo, che
            # ripeterebbe la modifica: un ciclo che faceva sparire la pagina
            # dalla vista.
            value = state.get("value") not in (False, "Off", "", None)
            self._distruggi_editor()
            self.doc.set_field_value(page, xref, not value)
            self.refresh_field_states()
            self.scene_obj.refresh_pixmaps()
            self.viewport().update()
            return
        elif kind == "choice":
            w = QComboBox(self)
            w.addItems(info.options or [str(state.get("value") or "")])
            i = w.findText(str(state.get("value") or ""))
            w.setCurrentIndex(i if i >= 0 else 0)
            w.currentTextChanged.connect(lambda t: self._editor_commit(t))
            self._editor = w
        elif kind == "button":
            self.doc.set_field_value(page, xref, "1")
            self._distruggi_editor()
            self.refresh_field_states()
            self.scene_obj.refresh_pixmaps()
            self.viewport().update()
            return
        elif kind == "signature":
            self._distruggi_editor()
            self.signature_requested.emit(page, info)
            return
        elif info.multiline:
            w = QPlainTextEdit(self)
            w.setPlainText(str(state.get("value") or ""))
            w.textChanged.connect(lambda: self._editor_commit(w.toPlainText()))
            self._editor = w
        else:
            w = QLineEdit(self)
            if info.password:
                w.setEchoMode(QLineEdit.Password)
            if info.maxlen:
                w.setMaxLength(info.maxlen)
            w.setText(str(state.get("value") or ""))
            w.textChanged.connect(lambda t: self._editor_commit(t))
            self._editor = w
        if self._editor is None:
            return
        self._applica_stile_editor()
        self._editor.installEventFilter(self)
        self._editor.setGeometry(rect.adjusted(0, 0, 0, 0))
        self._editor.show()
        self._editor.setFocus()
        if seleziona_tutto and isinstance(self._editor, (QLineEdit, QPlainTextEdit)):
            self._editor.selectAll()
        self.viewport().update()

    def _applica_stile_editor(self) -> None:
        """Colora l'editor aperto con i colori del tema in uso."""
        if self._editor is None:
            return
        self._editor.setStyleSheet(
            f"background: {self.palette.surface}; color: {self.palette.text};"
            f"border: 1px solid {self.palette.accent}; border-radius: 3px; padding: 0px 2px;"
        )

    def _editor_commit(self, value: Any) -> None:
        if self.active_field is None or self.doc is None:
            return
        page, xref = self.active_field
        state = self.field_states.get((page, xref))
        if state is not None:
            state["value"] = value
        self.commit_field(page, xref, value)

    def _sync_editor_value(self, value: Any) -> None:
        w = self._editor
        if w is None:
            return
        blocked = w.blockSignals(True)
        try:
            if isinstance(w, QLineEdit):
                if w.text() != str(value or ""):
                    w.setText(str(value or ""))
            elif isinstance(w, QPlainTextEdit):
                if w.toPlainText() != str(value or ""):
                    w.setPlainText(str(value or ""))
            elif isinstance(w, QComboBox):
                i = w.findText(str(value or ""))
                if i >= 0:
                    w.setCurrentIndex(i)
        finally:
            w.blockSignals(blocked)

    def _distruggi_editor(self) -> None:
        """Butta via l'editor del campo senza rileggerne i valori.

        Va tenuto separato da :meth:`hide_field_editor` perché quello chiama
        ``refresh_field_states``, che a sua volta chiama questo: senza la
        separazione i due si richiamerebbero a vicenda.
        """
        if self._editor is not None:
            w = self._editor
            self._editor = None
            w.removeEventFilter(self)
            w.setParent(None)
            w.deleteLater()
        self.active_field = None

    def hide_field_editor(self) -> None:
        """Chiude l'editor del campo attivo.

        Il valore non va salvato qui: l'editor del campo invia ogni modifica
        appena digitata, quindi chiuderlo perde solo la selezione del testo.
        Per questo non accetta un parametro «commit», che sarebbe stato
        ignorato.
        """
        if self._editor is None and self.active_field is None:
            return
        self._distruggi_editor()
        if self.doc is not None:
            self.refresh_field_states()
        self.viewport().update()

    # ------------------------------------------------------------------- zoom

    def set_zoom(self, value: float, mode: str | None = None) -> None:
        if mode:
            self._zoom_mode = mode
        self._zoom = max(0.05, min(16.0, float(value)))
        self.setTransform(_scaling(self._zoom))
        self.scene_obj.refresh_pixmaps()
        self._reposition_field_editor()
        self.viewport().update()
        self.zoom_changed.emit(self._zoom)

    def zoom(self) -> float:
        return self._zoom

    def zoom_in(self) -> None:
        self.set_zoom(self._zoom * 1.25, mode="custom")

    def zoom_out(self) -> None:
        self.set_zoom(self._zoom / 1.25, mode="custom")

    def apply_zoom_mode(self) -> None:
        """Ricalcola lo zoom in base alla modalita' corrente."""
        mode = self._zoom_mode
        doc = self.doc
        if doc is None or not doc.is_open or not self.scene_obj.nodes:
            return
        vp = self.viewport().rect()
        if mode == "fit_page":
            info = doc.page_info(self.current_page())
            factor = min(vp.width() / max(info.rect.width, 1), vp.height() / max(info.rect.height, 1))
            self.set_zoom(factor, mode="fit_page")
        elif mode == "fit_width":
            width = max(n.page_size()[0] for n in self.scene_obj.nodes)
            self.set_zoom((vp.width() - 24) / max(width, 1), mode="fit_width")
        elif mode == "actual":
            self.set_zoom(1.0, mode="actual")

    def _reposition_field_editor(self) -> None:
        """Riaccoloca l'editor sul campo attivo.

        L'editor è un widget figlio della vista, quindi vive in coordinate
        viewport: se la pagina scorre o cambia lo zoom, il campo si sposta ma
        l'editor resterebbe fermo, e si scriverebbe fuori dal riquadro.

        ``scrollContentsBy`` può essere chiamata da Qt già durante la
        costruzione della vista, quindi qui gli attributi si leggono in modo
        tollerante.
        """
        if getattr(self, "_editor", None) is None or getattr(self, "active_field", None) is None:
            return
        page, xref = self.active_field
        rect = self.field_rect_viewport(page, xref)
        if rect is None or not self.viewport().rect().intersects(rect):
            # il campo e' uscito dalla vista: non ha senso tenere aperto un
            # editor che non si vede
            self.hide_field_editor()
            return
        self._editor.setGeometry(rect)

    def scrollContentsBy(self, dx: int, dy: int) -> None:  # type: ignore[override]
        super().scrollContentsBy(dx, dy)
        self._reposition_field_editor()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if self._zoom_mode in ("fit_width", "fit_page"):
            self.apply_zoom_mode()
        self._reposition_field_editor()

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        if event.modifiers() & Qt.ControlModifier:
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
            return
        super().wheelEvent(event)

    # ------------------------------------------------------------------ strumenti

    def set_tool(self, tool: str) -> None:
        self.tool = tool
        cursors = {
            "hand": Qt.OpenHandCursor,
            "text": Qt.IBeamCursor,
            "select": Qt.ArrowCursor,
        }
        self.viewport().setCursor(QCursor(cursors.get(tool, Qt.CrossCursor)))
        self.scene_obj.overlay.clear()
        # Anche il trascinamento in corso va abbandonato: lasciarlo vivo
        # mentre il nuovo strumento e' gia' selezionato faceva terminare il
        # rilascio emettendo un'azione dello strumento precedente, con dati
        # incompatibili con quello nuovo.
        self._moving = {}
        self._drag_from = None
        self._drag_points = []
        self._drag_page = -1
        # i riquadri dei collegamenti devono stare solo con lo strumento di
        # selezione: con un altro strumento coprirebbero il disegno
        self.scene_obj.rebuild_links()
        self.tool_changed.emit(tool)

    def set_annots_style(self, color: str, width: float, fill: str | None) -> None:
        self.annots_color = color
        self.annots_width = width
        self.annots_fill = fill

    # ------------------------------------------------------------- navigazione

    def go_to_page(self, index: int) -> None:
        if not self.scene_obj.nodes:
            return
        index = max(0, min(index, len(self.scene_obj.nodes) - 1))
        node = self.scene_obj.node(index)
        if node is None:
            return
        self.centerOn(node.sceneBoundingRect().center())
        self.page_changed.emit(index)
        if self._view_mode == "single":
            self.set_page_visible_range(index, index)

    def current_page_index(self) -> int:
        return self.current_page()

    def page_rect_scene(self, index: int) -> QRectF:
        node = self.scene_obj.node(index)
        return node.sceneBoundingRect() if node else QRectF()

    def zoom_to_rect(self, index: int, rect, margin: float = 24.0, adatta: bool = False) -> None:
        """Porta in vista un riquadro, conservando lo zoom corrente.

        ``rect`` e' un riquadro **nello spazio pagina** (quello che danno
        ``Document.search`` e ``FieldInfo.rect``), non in quello mostrato: su
        una pagina ruotata la differenza porta a centrare un punto vuoto.

        Salto a un risultato di ricerca o a un campo non deve cambiare la
        scala: basta centrare il riquadro. Con ``adatta`` lo zoom si riduce
        solo se il riquadro non entra nella vista, e comunque entro il 400%:
        un singolo risultato e' alto poche decine di punti e ingrandirlo
        porterebbe a zoom assurdi rendendo illeggibile il resto della pagina.
        """
        node = self.scene_obj.node(index)
        r = _come_rect(rect)
        if node is None or r.is_empty:
            return
        mostrato = geo.Rect(self.doc.to_display_rect(index, r)) if self.doc is not None else r
        fattore = self._zoom
        if adatta:
            vp = self.viewport().rect()
            necessario = min(
                vp.width() / (mostrato.width + margin),
                vp.height() / (mostrato.height + margin),
            )
            fattore = min(max(self._zoom, necessario), 4.0)
        # la modalita' corrente viene conservata: un ridimensionamento della
        # finestra continua a ricalcolare 'adatta pagina' o 'adatta larghezza'
        self.set_zoom(fattore, mode=self._zoom_mode)
        self.centerOn(node.scenePos() + QPointF(mostrato.x0 + mostrato.width / 2, mostrato.y0 + mostrato.height / 2))

    def set_fields_visible(self, on: bool) -> None:
        self.highlight_fields = on
        self.viewport().update()

    def commit_field(self, page: int, xref: int, value: Any) -> None:
        state = self.field_states.get((page, xref))
        if state is not None:
            state["value"] = value
        self.field_committed.emit(page, xref, value)

    def open_link(self, uri: str) -> None:
        self.link_activated.emit(uri)

    def refresh_links(self) -> None:
        """Rifà i riquadri dei collegamenti dopo un cambio del documento."""
        self.scene_obj.rebuild_links()

    # ------------------------------------------------------------ selezione

    def selected_rects(self) -> list[tuple[int, int, geo.Rect]]:
        """Riquadri dei campi modulo, nello spazio in cui sono disegnati.

        Non e' la selezione: e' l'inventario dei campi della pagina, usato dal
        controllo di qualita' per capire dove passano i bordi.
        """
        out = []
        for (p, x), st in self.field_states.items():
            if self.doc is None:
                continue
            r = self.doc.to_display_rect(p, st["info"].rect)
            out.append((p, x, geo.Rect(r)))
        return out

    def clear_selection(self) -> None:
        self.scene_obj.selection.clear()
        self.scene_obj.overlay.set_guides([])
        self._sel_page = -1
        self._sel_rect = None
        self._sel_xref = None
        self._sel_kind = ""
        self.selection_changed.emit([])

    def select_rect(self, page: int, rect, show_handles: bool = True) -> None:
        """Mostra il riquadro di un elemento selezionato.

        ``rect`` e' nello spazio mostrato della pagina. Accetta un ``Rect`` di
        PyMuPDF, un ``geo.Rect`` o un ``QRectF`` di Qt: i tre compaiono nella
        finestra e la firma dichiarava solo il terzo.
        """
        if self.scene_obj.node(page) is None:
            return
        r = _come_rect(rect)
        if r.is_empty:
            return
        self.scene_obj.selection.set_rect(self._scene_rect(page, r), show_handles)
        # la selezione va ricordata come stato vero: `_moving` viene azzerato al
        # rilascio del mouse, e da li' in poi non restava più nulla su cui
        # basare il ridimensionamento
        self._sel_page = page
        self._sel_rect = geo.Rect(r)
        self.selection_changed.emit([(page, r)])

    def selection_scene_rect(self) -> QRectF:
        return self.scene_obj.selection.rect

    # ------------------------------------------------------------- interazione

    def _page_pos(self, scene_pos: QPointF) -> tuple[int, QPointF]:
        """Traduce una posizione di scena in (indice pagina, punto in punti PDF).

        Il punto restituito e' nello **spazio mostrato** della pagina, cioe'
        gia' ruotato come l'utente lo vede. Le API del documento (``add_annot``,
        ``insert_image``, ``set_annot_rect``, ...) vogliono invece lo spazio
        pagina: la conversione si fa con ``Document.to_page_rect``.
        Fuori da qualunque pagina si restituisce ``-1``, cosi' il chiamante puo'
        capire che il punto non e' su carta.
        """
        idx = self.scene_obj.index_at(scene_pos.y())
        if idx < 0 or self.scene_obj.node(idx) is None:
            return -1, QPointF()
        return idx, self._page_local(idx, scene_pos)

    def _to_scene(self, page: int, point: QPointF) -> QPointF:
        if self.scene_obj.node(page) is None:
            return point
        return self._scene_point(page, point)

    def _clic_un_collegamento(self, scene_pos: QPointF) -> bool:
        """Segue il collegamento sotto il cursore. True se l'ha seguito.

        I riquadri dei collegamenti sono figli della scena ma la vista gestisce
        la pressione del mouse per conto proprio e non lascia passare la
        dispatch di Qt, quindi il collegamento va interrogato qui. Con lo
        strumento di selezione un clic su un link non deve spostare nulla.
        """
        if self.tool != "select":
            return False
        for item in self.scene_obj.links:
            if item.rect().contains(scene_pos):
                if item.azione is not None:
                    item.azione()
                else:
                    self.open_link(item.uri)
                self.scene_obj.selection.clear()
                self.clear_selection()
                self.clear_text_selection()
                return True
        return False

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self.setFocus()
        scene_pos = self.mapToScene(_posizione(event))
        button = event.button()

        if self._space_down or self.tool == "hand" or button == Qt.MiddleButton:
            self._panning = True
            self._pan_origin = _posizione(event)
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return

        if button != Qt.LeftButton:
            super().mousePressEvent(event)
            return

        idx, local = self._page_pos(scene_pos)
        if idx < 0:
            # il punto non è su nessuna pagina: niente da selezionare, niente da
            # disegnare. Senza questo controllo un clic nel corridoio fra due
            # pagine finiva sulla prima pagina (o sull'ultima, per l'indicizzatore
            # che ricadeva sempre in fondo) con coordinate inventate.
            if self.active_field is not None:
                self.hide_field_editor()
            self.clear_selection()
            self.clear_text_selection()
            event.accept()
            return

        if self.tool == "select":
            # 1) maniglie di ridimensionamento della selezione corrente
            zone = self.scene_obj.selection.zone_at(scene_pos)
            if zone:
                self._drag_from = local
                self._drag_page = idx
                # la maniglia si trascina nello spazio mostrato: qui si
                # conserva il riquadro come l'utente lo vede
                base = self.selection_page_rect()
                self._moving = {
                    "mode": "resize", "zone": zone,
                    "start": self.selection_page_rect(),
                    "orig_display": geo.Rect(self.doc.to_display_rect(idx, base))
                    if base is not None and self.doc is not None
                    else None,
                    # il rilascio deve sapere di quale elemento si tratta: la
                    # selezione resta valida anche dopo che _moving e' stato
                    # azzerato, quindi queste informazioni vengono da li'
                    "xref": self._sel_xref, "kind": self._sel_kind,
                }
                event.accept()
                return

            # 2) click su un campo modulo
            hit = self.field_at(idx, scene_pos)
            if hit is not None:
                self.clear_text_selection()
                if event.modifiers() & (Qt.AltModifier | Qt.MetaModifier):
                    # Alt+clic sul campo: lo si seleziona e lo si prepara al
                    # trascinamento. Prima il ramo usciva subito e il campo non
                    # era mai spostabile col mouse.
                    info = self.field_states[hit]["info"]
                    self._select_hit(idx, hit[1], info.rect, "field")
                    self._drag_from = local
                    self._drag_page = idx
                    self._moving = {
                        "mode": "move", "kind": "field", "xref": hit[1],
                        "start": local,
                        # `orig` e' il riquadro come lo schermo lo mostra: lo
                        # spostamento e' calcolato con un delta di schermo, e su
                        # una pagina ruotata i due spazi hanno assi scambiati
                        "orig": geo.Rect(self.doc.to_display_rect(idx, info.rect)),
                        "page_rect": geo.Rect(info.rect),
                    }
                else:
                    self.begin_field_edit(*hit)
                event.accept()
                return

            # 3) annotazioni, campi e immagini hanno la precedenza sul
            # collegamento. La prova del collegamento veniva prima di ogni
            # altra e vinceva sempre: un'annotazione appoggiata su un
            # collegamento non si poteva piu' selezionare, spostare,
            # ridimensionare o cancellare, e con gli strumenti di disegno il
            # clic su un collegamento apriva il browser invece di disegnare.
            if self._hit_test(idx, local) is not None:
                if self.active_field is not None:
                    self.hide_field_editor()
                self._start_select(idx, local, event.modifiers())
                event.accept()
                return

            # 4) il collegamento, adesso che sotto il cursore non c'e' nient'altro
            if self._clic_un_collegamento(scene_pos):
                event.accept()
                return

            # 5) rettangolo di selezione
            if self.active_field is not None:
                self.hide_field_editor()
            self._start_select(idx, local, event.modifiers())
            event.accept()
            return

        if self.tool in DRAG_TOOLS:
            self._drag_from = local
            self._drag_page = idx
            self._moving = {"mode": "create", "start": local}
            event.accept()
            return

        if self.tool in LINE_TOOLS:
            self._drag_from = local
            self._drag_page = idx
            self._drag_points = [local, local]
            event.accept()
            return

        if self.tool in POLY_TOOLS:
            self._drag_from = local
            self._drag_page = idx
            self._drag_points = [local]
            event.accept()
            return

        if self.tool in POINT_TOOLS:
            self.request_tool_action.emit(self.tool, (idx, local))
            event.accept()
            return

        super().mousePressEvent(event)

    def _start_select(self, idx: int, local: QPointF, mods) -> None:
        doc = self.doc
        if doc is None:
            return
        hit = self._hit_test(idx, local)
        if hit:
            kind, xref, rect = hit
            self._select_hit(idx, xref, rect, kind)
            # un solo elemento puo' essere selezionato: cliccando un'annotazione
            # o un'immagine l'evidenziazione del testo sparisce, come in Acrobat
            self.clear_text_selection()
            self._drag_from = local
            self._drag_page = idx
            # geo.move ragiona su un Rect: racchiuderlo in un QRectF non
            # solo e' inutile, PySide6 rifiuta la costruzione e il clic su
            # un'annotazione esistente terminava con un errore
            self._moving = {
                "mode": "move", "kind": kind, "xref": xref, "start": local,
                # lo spostamento parte dal riquadro come lo schermo lo mostra:
                # il delta e' un delta di schermo, quindi su una pagina ruotata
                # i due spazi non si possono mescolare
                "orig": geo.Rect(doc.to_display_rect(idx, rect)),
                "page_rect": geo.Rect(rect),
            }
        else:
            self.clear_selection()
            # anche l'evidenziazione del testo va via: il clic su un punto
            # qualunque deve toglierla, altrimenti la selezione restava a
            # schermo e si poteva scacciare solo scegliendo altro testo. Il
            # riquadro che segue e' quello che il trascinamento sta facendo,
            # quindi un nuovo rettangolo di selezione continua a funzionare.
            self.clear_text_selection()
            self._drag_from = local
            self._drag_page = idx
            self._moving = {"mode": "marquee", "start": local}

    def _hit_test(self, page: int, local: QPointF) -> tuple[str, int, geo.Rect] | None:
        doc = self.doc
        if doc is None:
            return None
        point = geo.Rect(local.x() - 0.5, local.y() - 0.5, local.x() + 0.5, local.y() + 0.5)
        best = None
        best_area = None
        for f in doc.fields(page):
            r = doc.to_display_rect(page, f.rect)
            if r.contains(point) and not r.is_empty:
                best = ("field", f.xref, geo.Rect(f.rect))
                best_area = r.get_area()
                break
        for a in doc.annots(page, include_widgets=False):
            r = doc.to_display_rect(page, a["rect"])
            if r.contains(point):
                area = r.get_area()
                if best_area is None or area < best_area:
                    best = ("annot", a["xref"], geo.Rect(a["rect"]))
                    best_area = area
        # anche le immagini si possono afferrare: senza questo la firma e
        # ogni immagine inserita restavano immobili e non si potevano spostare
        for im in doc.image_rects(page):
            if im["xref"] is None:
                continue
            r = doc.to_display_rect(page, im["rect"])
            if r.contains(point) and not r.is_empty:
                area = r.get_area()
                if best_area is None or area < best_area:
                    best = ("image", im["xref"], geo.Rect(im["rect"]))
                    best_area = area
        return best

    def _select_hit(self, page: int, xref: int, rect: geo.Rect, kind: str) -> None:
        doc = self.doc
        if doc is None:
            return
        disp = doc.to_display_rect(page, rect)
        self._sel_xref = xref
        self._sel_kind = kind
        self.select_rect(page, disp)
        # «Annotazione selezionato»: in italiano il sostantivo e l'aggettivo
        # concordano nel genere
        self.status.emit("Campo selezionato" if kind == "field" else "Annotazione selezionata")
        if kind == "field":
            # il clic normale apre l'editor, quindi senza un indizio non
            # si saprebbe che il campo si sposta tenendo premuto Alt
            self.status.emit("Campo selezionato: trascinalo per spostarlo, "
                             "usa le maniglie per cambiarne la dimensione")

    def selection_page_rect(self) -> geo.Rect | None:
        """Riquadro dell'elemento selezionato, in coordinate pagina.

        Il riquadro memorizzato (``_sel_rect``) e' nello spazio mostrato, quindi
        per ricavare il riquadro pagina delle immagini — che non sono
        annotazioni e non compaiono in ``annots()`` — serve convertirlo. Prima la
        funzione restituiva quello mostrato: ridimensionare un'immagine su una
        pagina ruotata partiva da un rettangolo con gli assi scambiati.
        """
        doc = self.doc
        if doc is None:
            return None
        page = self._drag_page if self._drag_page >= 0 else self._sel_page
        if page < 0 or self._sel_rect is None:
            return None
        xref = self._moving.get("xref", self._sel_xref)
        if xref is not None and doc.annots(page):
            for a in doc.annots(page):
                if a["xref"] == xref:
                    return geo.Rect(a["rect"])
        state = self.field_states.get((page, xref)) if xref is not None else None
        if state is not None:
            return geo.Rect(state["info"].rect)
        for im in doc.image_rects(page):
            if im["xref"] == xref:
                return geo.Rect(im["rect"])
        return geo.Rect(doc.to_page_rect(page, geo.Rect(self._sel_rect)))

    def selection_display_rect(self) -> QRectF | None:
        """Riquadro della selezione nello spazio in cui e' disegnata."""
        r = self._sel_rect
        if r is None or self._sel_page < 0:
            return None
        return QRectF(r.x0, r.y0, r.width, r.height)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        scene_pos = self.mapToScene(_posizione(event))
        if self._panning:
            delta = _posizione(event) - self._pan_origin
            self._pan_origin = _posizione(event)
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            # senza ``accept`` Qt segnala che il rilascio non e' stato
            # accettato da nessuno: la pressione lo era stata
            event.accept()
            return

        if self._moving and self._drag_from is not None:
            self._handle_drag(scene_pos, event.modifiers())
            return

        if self.tool in POLY_TOOLS and self._drag_points:
            self._append_point(scene_pos)
            self._mostra_tracciato()
            return

        if self.tool in LINE_TOOLS and self._drag_from is not None:
            # la linea e' tracciata a partire dal tasto premuto: senza questo
            # l'utente non vedeva nulla seguire il cursore e rilasciava «alla
            # cieca». Il punto finale è solo un anteprima: al rilascio viene ricalcolato.
            idx, local = self._page_pos(scene_pos)
            if idx >= 0 and idx == self._drag_page:
                self.scene_obj.overlay.set_points(
                    [self._to_scene(self._drag_page, self._drag_from), self._to_scene(idx, local)],
                    self.tool,
                    self.annots_color,
                )
            return

        if self.tool == "select":
            self._update_cursor(scene_pos)
        super().mouseMoveEvent(event)

    def _mostra_tracciato(self) -> None:
        """Disegna il tracciato di inchiostro, poligono o polilinea in corso."""
        punti = self._drag_points
        if len(punti) < 2 or self.scene_obj.node(self._drag_page) is None:
            return
        self.scene_obj.overlay.set_points(
            [self._to_scene(self._drag_page, p) for p in punti],
            self.tool,
            self.annots_color,
        )

    def _append_point(self, scene_pos: QPointF) -> None:
        idx, local = self._page_pos(scene_pos)
        if idx != self._drag_page:
            return
        pts = self._drag_points
        if not pts:
            return
        last = pts[-1]
        if (local.x() - last.x()) ** 2 + (local.y() - last.y()) ** 2 < 4:
            return
        pts.append(local)

    def _handle_drag(self, scene_pos: QPointF, mods) -> None:
        mode = self._moving.get("mode")
        doc = self.doc
        if doc is None:
            return
        # Il trascinamento appartiene alla pagina su cui e' iniziato: ricalcolare
        # l'indice dal punto di rilascio faceva finire un elemento spostato da
        # una pagina all'altra, e un disegno che attraversa due pagine finiva
        # sull'altra con le coordinate della prima.
        idx = self._drag_page if self._drag_page >= 0 else self._sel_page
        punto_idx, local = self._page_pos(scene_pos)
        if idx < 0:
            return
        if punto_idx != idx:
            # fuori dalla pagina d'origine si continua a usare l'ultima posizione
            # valida invece di scrivere coordinate di un'altra pagina
            last = self._moving.get("last_local")
            if last is not None:
                local = last
            else:
                return
        self._moving["last_local"] = local

        if mode == "create":
            r = geo.rect_of(self._drag_from.x(), self._drag_from.y(), local.x(), local.y())
            info = doc.page_info(idx)
            r = geo.clamp_rect(r, info.rect)
            if self.tool == "image":
                r = geo.aspect_limited(r, 1.0)
            self._show_overlay_rect(idx, r)
            # `current` resta nello spazio mostrato (ci vive l'anteprima);
            # la conversione allo spazio pagina avviene al rilascio
            self._moving["current"] = geo.Rect(r)
            return

        if mode == "marquee":
            r = geo.rect_of(self._drag_from.x(), self._drag_from.y(), local.x(), local.y())
            self._show_overlay_rect(idx, r, mode="select", color=self.palette.selection)
            self._moving["current"] = geo.Rect(r)
            # le parole toccate dal rettangolo vengono evidenziate subito:
            # si vede cosa verra' copiato ancora prima di rilasciare
            if doc is not None and r.width > 2 and r.height > 2:
                parole = doc.words_in_rect(idx, geo.Rect(r))
                if parole:
                    if self.scene_obj.node(idx) is not None:
                        self.scene_obj.text_selection.set_rects(
                            [
                                self._scene_rect(idx, geo.Rect(w.x0, w.y0, w.x1, w.y1))
                                for w in parole
                            ]
                        )
            return

        if mode == "move":
            start = self._moving.get("orig")
            if start is None:
                return
            dx = local.x() - self._moving["start"].x()
            dy = local.y() - self._moving["start"].y()
            spostato = geo.Rect(geo.move(start, dx, dy))
            info = doc.page_info(idx)
            spostato = geo.clamp_rect(spostato, info.rect)
            if self.snap_on:
                targets = [geo.Rect(doc.to_display_rect(idx, a["rect"])) for a in doc.annots(idx)]
                res = geo.compute_snap(
                    spostato,
                    targets,
                    info.rect,
                    theme.METRICS.snap_tol,
                    grid=self._grid_pass(),
                    guides_enabled=self.snap_guides,
                )
                ancorato = geo.Rect(
                    res.x, res.y, res.x + spostato.width, res.y + spostato.height
                )
                spostato = geo.clamp_rect(ancorato, info.rect)
                if self.snap_guides:
                    self._mostra_guide(idx, res.guides)
            # Si scrive sempre nello spazio pagina: e' li' che il documento
            # registra il riquadro, e su una pagina ruotata i due spazi hanno
            # anche dimensioni diverse.
            self._moving["current_page_rect"] = geo.Rect(doc.to_page_rect(idx, spostato))
            self.select_rect(idx, spostato)
            return

        if mode == "resize":
            # la maniglia e' nello spazio mostrato: anche il riquadro da
            # ridimensionare va ridimensionato li'. Mescolare il riquadro
            # pagina con il punto mostrato dava riquadri enormi su una pagina
            # ruotata.
            start = self._moving.get("orig_display")
            if start is None:
                base = self.selection_page_rect()
                start = geo.Rect(doc.to_display_rect(idx, base)) if base is not None else geo.Rect(0, 0, 100, 100)
                self._moving["orig_display"] = start
            nuovo = _resize_rect(start, self._moving.get("zone", "se"), QPointF(local.x(), local.y()), mods)
            nuovo = geo.clamp_rect(nuovo, doc.page_info(idx).rect)
            self._moving["current_page_rect"] = geo.Rect(doc.to_page_rect(idx, nuovo))
            self.select_rect(idx, nuovo)
            return

    def _grid_pass(self) -> float:
        """Il passo della griglia quando la griglia e' attiva, altrimenti zero.

        ``compute_snap`` usa zero come "nessuna griglia": passare il passo
        anche a griglia spenta aggancierebbe agli incroci invisibili.
        """
        return float(self.grid_size()) if self.grid_on else 0.0

    def _mostra_guide(self, page: int, guides) -> None:
        """Porta le guide di magnetismo dalla pagina alla scena e le disegna."""
        if not guides or self.scene_obj.node(page) is None:
            self.scene_obj.overlay.set_guides([])
            return
        in_scena = []
        for x1, y1, x2, y2 in guides:
            a = self._to_scene(page, QPointF(x1, y1))
            b = self._to_scene(page, QPointF(x2, y2))
            in_scena.append((a.x(), a.y(), b.x(), b.y()))
        self.scene_obj.overlay.set_guides(in_scena, self.palette.accent)

    def selection_xref(self) -> int | None:
        """Xref dell'elemento selezionato, o ``None`` se non c'e'."""
        return self._sel_xref

    def selection_kind(self) -> str:
        """Come trattare la selezione: ``field``, ``image`` o annotazione."""
        return self._sel_kind

    def selected_page(self) -> int | None:
        """Indice della pagina dove sta l'elemento selezionato, o ``None``."""
        return self._sel_page if self._sel_page >= 0 else None

    def _show_overlay_rect(self, page: int, rect: geo.Rect, mode: str | None = None, color: str | None = None) -> None:
        """Mostra il rettangolo di trascinamento.

        ``rect`` e' gia' nello spazio mostrato della pagina: e' cosi' che la
        cornice segue il cursore. La conversione allo spazio pagina avviene al
        rilascio, dove l'elemento viene davvero creato.
        """
        node = self.scene_obj.node(page)
        if node is None:
            return
        qr = self._scene_rect(page, rect)
        ov = self.scene_obj.overlay
        m = mode or ("circle" if self.tool == "circle" else "rect")
        c = color or self.annots_color
        if self.tool in ("field_text", "field_check", "field_radio", "field_combo", "field_button"):
            c = self.palette.field_border
        if self.tool == "redact":
            c = "#101828"
        ov.set_rect(qr, m, c)

    def _update_cursor(self, scene_pos: QPointF) -> None:
        zone = self.scene_obj.selection.zone_at(scene_pos)
        cursors = {
            "nw": Qt.SizeFDiagCursor, "se": Qt.SizeFDiagCursor,
            "ne": Qt.SizeBDiagCursor, "sw": Qt.SizeBDiagCursor,
            "n": Qt.SizeVerCursor, "s": Qt.SizeVerCursor,
            "e": Qt.SizeHorCursor, "w": Qt.SizeHorCursor,
        }
        if zone:
            self.viewport().setCursor(QCursor(cursors.get(zone, Qt.SizeAllCursor)))
        else:
            self.viewport().setCursor(Qt.ArrowCursor)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        # le guide del magnetismo valgono per il trascinamento in corso: se
        # restassero, dopo aver posato l'elemento si vedrebbe un aggancio che
        # non piu' esiste
        self.scene_obj.overlay.set_guides([])
        if self._panning:
            self._panning = False
            self.set_tool(self.tool)
            event.accept()
            return
        scene_pos = self.mapToScene(_posizione(event))
        moving = self._moving
        self._moving = {}
        # La pagina e' quella premuta: ricalcolarla sul punto di rilascio
        # spostava l'elemento su un'altra pagina (e per i nuovi elementi li
        # creava li' con le coordinate della pagina di partenza).
        idx = self._drag_page if self._drag_page >= 0 else self._sel_page
        punto_idx, local = self._page_pos(scene_pos)
        if idx < 0:
            idx = punto_idx
        elif punto_idx != idx and moving.get("last_local") is not None:
            local = moving["last_local"]

        if moving.get("mode") == "create":
            rect = moving.get("current")
            self.scene_obj.overlay.clear()
            if rect is None or rect.width <= 1 or rect.height <= 1:
                # clic secco: si usa la dimensione prevista per lo strumento
                predef = AREA_CLIC.get(self.tool)
                if predef is None:
                    self._drag_from = None
                    event.accept()
                    return
                start = moving.get("start")
                if start is None:
                    self._drag_from = None
                    event.accept()
                    return
                rect = geo.Rect(
                    start.x(), start.y(), start.x() + predef[0], start.y() + predef[1]
                )
            # il riquadro arriva dallo spazio mostrato e va consegnato nello
            # spazio pagina: su una pagina ruotata le due cose non coincidono,
            # e senza la conversione ogni forma finiva nel posto sbagliato
            pagina = geo.Rect(self.doc.to_page_rect(idx, geo.Rect(rect)))
            self.request_tool_action.emit(self.tool, (idx, pagina))
            self._drag_from = None
            event.accept()
            return

        if moving.get("mode") == "move":
            new = moving.get("current_page_rect")
            if new is not None:
                self.request_tool_action.emit("move", (idx, moving["xref"], new, moving.get("kind")))
            self._drag_from = None
            event.accept()
            return

        if moving.get("mode") == "resize":
            new = moving.get("current_page_rect")
            if new is not None and new.width > 2 and new.height > 2:
                self.request_tool_action.emit("resize", (idx, moving["xref"], new, moving.get("kind")))
            self._drag_from = None
            event.accept()
            return

        if moving.get("mode") == "marquee":
            rect = moving.get("current")
            self.scene_obj.overlay.clear()
            if rect is not None and rect.width > 3 and rect.height > 3:
                self._select_inside(idx, geo.Rect(rect))
            self._drag_from = None
            event.accept()
            return

        if self.tool in LINE_TOOLS and self._drag_from is not None:
            punti = [self._drag_from, local]
            self._drag_points = list(punti)
            self.scene_obj.overlay.set_points(
                [self._to_scene(self._drag_page, p) for p in punti],
                self.tool, self.annots_color,
            )
            # anche i vertici vanno nello spazio pagina, come tutti gli altri
            # elementi che il documento registra
            in_pagina = [
                _pt_to_page(self.doc, idx, p.x(), p.y()) for p in punti
            ]
            self.request_tool_action.emit(self.tool, (self._drag_page, in_pagina))
            self._drag_from = None
            self._drag_points = []
            event.accept()
            return

        if self.tool in POLY_TOOLS and self._drag_points:
            punti = list(self._drag_points)
            if len(punti) >= 2:
                in_pagina = [
                    _pt_to_page(self.doc, idx, p.x(), p.y()) for p in punti
                ]
                self.request_tool_action.emit(self.tool, (idx, in_pagina))
            self._drag_points = []
            self._drag_from = None
            self.scene_obj.overlay.clear()
            event.accept()
            return

        self._drag_from = None
        self._drag_points = []
        super().mouseReleaseEvent(event)

    def _select_inside(self, page: int, rect: geo.Rect) -> None:
        """Conclude il trascinamento del rettangolo di selezione.

        Si privilegia il testo: e' cio' che l'utente si aspetta di copiare. Se
        invece il rettangolo racchiude annotazioni, queste vengono selezionate
        e contate, come fa Acrobat.
        """
        doc = self.doc
        if doc is None:
            return
        parole = doc.words_in_rect(page, rect)
        if parole:
            self._set_text_selection(page, rect, parole)
            return
        trovate = [
            a for a in doc.annots(page, include_widgets=False)
            if (doc.to_display_rect(page, a["rect"]) & rect).get_area() > 0
        ]
        if trovate:
            self.clear_text_selection()
            self.select_rect(page, doc.to_display_rect(page, trovate[0]["rect"]), show_handles=False)
            if len(trovate) > 1:
                # il riquangolo racchiude piu' elementi ma ne muove uno solo:
                # conviene dirlo, altrimenti la barra di stato promette una
                # selezione multipla che non esiste
                self.status.emit(
                    f"{len(trovate)} elementi nel riquadro: selezionato il primo"
                )
        else:
            self.clear_text_selection()
            self.clear_selection()

    # ------------------------------------------------- selezione e copia del testo

    def _set_text_selection(self, page: int, rect: geo.Rect, parole: list[geo.Rect]) -> None:
        """Mostra l'evidenziazione delle parole selezionate."""
        doc = self.doc
        if doc is None:
            return
        self.clear_selection()
        if self.scene_obj.node(page) is None:
            return
        scena = [self._scene_rect(page, r) for r in parole]
        self.scene_obj.text_selection.set_rects(scena)
        self._text_selection = (page, geo.Rect(rect))
        self.text_selected.emit(len(parole))

    def clear_text_selection(self) -> None:
        self.scene_obj.text_selection.clear()
        self._text_selection = None
        self.text_selected.emit(0)

    def selected_text(self) -> str:
        """Testo attualmente selezionato, pronto per la clipboard."""
        doc = self.doc
        if doc is None or self._text_selection is None:
            return ""
        page, rect = self._text_selection
        return doc.selected_text(page, rect)

    def copy_selection(self) -> bool:
        """Copia il testo selezionato negli appunti. True se qualcosa e' stato copiato."""
        testo = self.selected_text()
        if not testo.strip():
            return False
        QGuiApplication.clipboard().setText(testo)
        return True

    def select_all_text(self, page: int | None = None) -> None:
        """Seleziona tutto il testo di una pagina, come Ctrl+A in Acrobat."""
        doc = self.doc
        if doc is None or not doc.is_open:
            return
        idx = self.current_page() if page is None else page
        if not (0 <= idx < doc.page_count):
            return
        info = doc.page_info(idx)
        parole = doc.words_in_rect(idx, info.rect)
        if not parole:
            self.clear_text_selection()
            return
        unione = parole[0]
        for r in parole[1:]:
            unione = unione | r
        self._set_text_selection(idx, geo.Rect(unione), parole)

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() == Qt.Key_Space and not self._space_down:
            self._space_down = True
            self.setCursor(Qt.OpenHandCursor)
            event.accept()
            return
        if self._gestisci_tasto_chiusura(event.key()):
            event.accept()
            return
        if event.matches(QKeySequence.Copy):
            if self.copy_selection():
                self.status.emit("Testo copiato negli appunti")
                event.accept()
                return
        if event.matches(QKeySequence.SelectAll):
            self.select_all_text()
            event.accept()
            return
        super().keyPressEvent(event)

    def eventFilter(self, watched, event) -> bool:  # type: ignore[override]
        # Mentre si compila un campo i tasti li riceve l'editor, non la vista:
        # un QLineEdit con Escape e Tab non fa nulla. Senza questo filtro non
        # c'era modo di chiudere l'editor da tastiera, e Tab si limitava a
        # togliere il focus lasciando la casella disegnata sulla pagina con la
        # digitazione persa.
        if watched is self._editor and event.type() == QEvent.KeyPress:
            if self._gestisci_tasto_chiusura(event.key()):
                return True
        return super().eventFilter(watched, event)

    def _gestisci_tasto_chiusura(self, key: int) -> bool:
        """Gestisce Esc, Invio e Tab mentre un campo è in compilazione."""
        if self._editor is None or self.active_field is None:
            return False
        if key == Qt.Key_Escape:
            self.hide_field_editor()
            self.status.emit("Campo chiuso")
            return True
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self.hide_field_editor()
            self.status.emit("Campo compilato")
            return True
        if key in (Qt.Key_Tab, Qt.Key_Backtab):
            prossimo = self._campo_successivo(*self.active_field)
            indietro = key == Qt.Key_Backtab
            if indietro:
                prossimo = self._campo_precedente(*self.active_field)
            self.hide_field_editor()
            if prossimo is not None:
                self.begin_field_edit(*prossimo)
            return True
        return False

    def _ordine_campi(self) -> list[tuple[int, int]]:
        """Campi presenti, nell'ordine in cui si compilano."""
        try:
            ordine = self.doc.tab_order() if self.doc is not None else []
        except Exception:
            ordine = []
        return [c for c in ordine if c in self.field_states] or sorted(self.field_states)

    def _campo_successivo(self, page: int, xref: int) -> tuple[int, int] | None:
        """Il campo successivo nell'ordine di tabulazione, se c'è."""
        chiavi = self._ordine_campi()
        if (page, xref) not in chiavi:
            return None
        i = chiavi.index((page, xref))
        return chiavi[i + 1] if i + 1 < len(chiavi) else chiavi[0]

    def _campo_precedente(self, page: int, xref: int) -> tuple[int, int] | None:
        """Il campo precedente nell'ordine di tabulazione, se c'è."""
        chiavi = self._ordine_campi()
        if (page, xref) not in chiavi:
            return None
        i = chiavi.index((page, xref))
        return chiavi[i - 1] if i > 0 else chiavi[-1]

    def keyReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.key() == Qt.Key_Space:
            self._space_down = False
            self.set_tool(self.tool)
            event.accept()
            return
        super().keyReleaseEvent(event)


def _scaling(zoom: float):
    from PySide6.QtGui import QTransform

    t = QTransform()
    t.scale(zoom, zoom)
    return t


def _come_rect(rect) -> geo.Rect:
    """Un riquadro qualsiasi (``Rect``, ``geo.Rect``, ``QRectF``) come ``geo.Rect``.

    Nella finestra circolano riquadri di tre tipi diversi; ``geo.Rect`` accetta
    solo i primi due e PySide6 rifiuta la costruzione dagli altri, quindi la
    conversione va fatta per coordinate.
    """
    if isinstance(rect, geo.Rect):
        return rect
    if isinstance(rect, (QRectF, QRect)):
        return geo.Rect(rect.x(), rect.y(), rect.x() + rect.width(), rect.y() + rect.height())
    return geo.Rect(rect)


def _pt_to_page(doc, page: int, x: float, y: float) -> tuple[float, float]:
    """Un punto dello spazio mostrato riportato nello spazio pagina.

    Le API del documento lavorano in punti PDF non ruotati; la vista lavora
    invece nello spazio in cui la pagina e' disegnata a schermo. Su una pagina
    ruotata i due sistemi hanno gli assi scambiati, quindi la differenza si
    nota subito: ogni forma, linea e campo finiva nel punto sbagliato.
    """
    if doc is None:
        return (float(x), float(y))
    r = doc.to_page_rect(page, geo.Rect(float(x), float(y), float(x), float(y)))
    return (float(r.x0), float(r.y0))


def _resize_rect(start: geo.Rect, zone: str, point: QPointF, mods) -> geo.Rect:
    """Ricalcola il rettangolo durante il trascinamento di una maniglia."""
    r = geo.Rect(start)
    x0, y0, x1, y1 = r.x0, r.y0, r.x1, r.y1
    px, py = point.x(), point.y()
    if "w" in zone:
        x0 = min(px, x1 - 1)
    if "e" in zone:
        x1 = max(px, x0 + 1)
    if "n" in zone:
        y0 = min(py, y1 - 1)
    if "s" in zone:
        y1 = max(py, y0 + 1)
    out = geo.Rect(x0, y0, x1, y1)
    if mods & Qt.ShiftModifier:
        factor = max(out.width, out.height)
        cx, cy = (start.x0 + start.x1) / 2, (start.y0 + start.y1) / 2
        out = geo.Rect(cx - factor / 2, cy - factor / 2, cx + factor / 2, cy + factor / 2)
    if mods & Qt.AltModifier:
        # ridimensiona dal centro: la maniglia trascinata segue il puntatore e
        # il lato opposto si allontana dalla stessa misura. Il centro è quello
        # del riquadro di partenza, non quello del riquadro già allargato dalla
        # maniglia, altrimenti un lato resterebbe fermo e il riquadro
        # collasserebbe su se stesso con la maniglia a nord-ovest.
        cx, cy = (start.x0 + start.x1) / 2, (start.y0 + start.y1) / 2
        if "e" in zone:
            dx = px - cx
        elif "w" in zone:
            dx = cx - px
        else:
            dx = (x1 - x0) / 2
        if "s" in zone:
            dy = py - cy
        elif "n" in zone:
            dy = cy - py
        else:
            dy = (y1 - y0) / 2
        out = geo.Rect(cx - abs(dx), cy - abs(dy), cx + abs(dx), cy + abs(dy))
    return out
