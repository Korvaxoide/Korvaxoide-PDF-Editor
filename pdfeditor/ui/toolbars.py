"""Barre degli strumenti e scorciatoie."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QLineEdit,
    QSpinBox,
    QToolBar,
    QWidget,
)

from ..core.i18n import tr
from . import icons, theme

# Strumento -> (etichetta, icona, tasto, descrizione)
#
# Il terzo campo e' un tasto singolo *non registrato*. Le scorciatoie da una
# lettera sola non possono vivere sulla finestra principale perche' i campi
# modulo si compilano dentro la finestra, con lo stesso contesto di scorciatoie:
# digitare «v» in un campo di testo attiverebbe lo strumento di selezione e
# perderebbe la lettera. Vengono mostrate perche' sono un richiamo utile, ma
# non nelle descrizioni, dove sembrerebbero attive.
TOOL_ITEMS: tuple[tuple[str, str, str, str, str], ...] = (
    ("select", "Seleziona", "select", "V", "Seleziona e sposta gli elementi"),
    ("hand", "Mano", "hand", "H", "Sposta la pagina"),
    ("text", "Casella di testo", "text", "T", "Aggiungi una casella di testo"),
    ("image", "Immagine", "image", "I", "Inserisci un'immagine"),
    ("signature", "Firma", "sign", "S", "Inserisci una firma"),
    ("highlight", "Evidenzia", "highlight", "", "Evidenzia il testo"),
    ("underline", "Sottolinea", "underline", "", "Sottolinea il testo"),
    ("strikeout", "Barratura", "strikeout", "", "Barra il testo"),
    ("squiggly", "Onda", "squiggly", "", "Sottolinea con onda"),
    ("ink", "Inchiostro", "ink", "", "Disegna a mano libera"),
    ("note", "Nota", "note", "", "Aggiungi una nota"),
    ("rect", "Rettangolo", "rect", "", "Disegna un rettangolo"),
    ("circle", "Ellisse", "circle", "", "Disegna un'ellisse"),
    ("line", "Linea", "line", "", "Disegna una linea"),
    ("arrow", "Freccia", "arrow", "", "Disegna una freccia"),
    ("polygon", "Poligono", "polygon", "", "Disegna un poligono"),
    ("stamp", "Timbro", "stamp", "", "Applica un timbro"),
    ("link", "Collegamento", "link", "", "Inserisci un collegamento"),
    ("redact", "Redazione", "redact", "", "Redigi in modo permanente"),
)


#: Gli strumenti del menu *Annota*. Sono diversi da ``TOOL_ITEMS`` per due
#: ragioni: *Seleziona* e *Mano* sono azioni e non strumenti di annotazione, e
#: *Testo libero* non c'è tra gli strumenti della barra perché è un'annotazione
#: e non una casella di testo. Vive qui e non dentro il menu perché il suo
#: nome è una chiave di traduzione e va trovabile dal controllo sul catalogo.
TOOL_ITEMS_ANNOTA: tuple[tuple[str, str, str], ...] = (
    ("highlight", "Evidenzia", "highlight"),
    ("underline", "Sottolinea", "underline"),
    ("strikeout", "Barra", "strikeout"),
    ("squiggly", "Onda", "squiggly"),
    ("note", "Nota", "note"),
    ("freetext", "Testo libero", "text"),
    ("ink", "Inchiostro", "ink"),
    ("rect", "Rettangolo", "rect"),
    ("circle", "Ellisse", "circle"),
    ("line", "Linea", "line"),
    ("arrow", "Freccia", "arrow"),
    ("polygon", "Poligono", "polygon"),
    ("stamp", "Timbro", "stamp"),
)

FIELD_TOOL_ITEMS: tuple[tuple[str, str, str], ...] = (
    ("field_text", "text-field", "Campo di testo"),
    ("field_check", "check", "Casella di spunta"),
    ("field_radio", "radio", "Pulsante di opzione"),
    ("field_combo", "dropdown", "Menu a tendina"),
    ("field_button", "form", "Pulsante"),
)


def build_main_toolbar(window, theme_pal: theme.Palette) -> tuple[QToolBar, dict[str, QAction]]:
    """Barra principale: file, modifica, strumenti, zoom, pagine."""
    tb = QToolBar("Principale")
    tb.setObjectName("mainToolbar")
    tb.setIconSize(QSize(22, 22))
    tb.setToolButtonStyle(Qt.ToolButtonIconOnly)
    window.addToolBar(tb)
    acts: dict[str, QAction] = {}

    def add(key: str, text: str, icon: str, slot: Callable[[], None], shortcut: str = "", tip: str = "") -> QAction:
        a = QAction(icons.icon(icon, theme_pal.text, 22), text, window)
        _marchia(a, icon, 22)
        # la scorciatoia resta sulle voci di menu, che la mostrano all'utente:
        # metterla anche qui la rende ambigua e Qt smette di gestirla
        a.setToolTip(f"{text} ({shortcut})" if shortcut else (tip or text))
        a.triggered.connect(slot)
        tb.addAction(a)
        acts[key] = a
        return a

    add("new", tr("Nuovo"), "doc", window.file_new, "Ctrl+N")
    add("open", tr("Apri"), "doc-open", window.file_open, "Ctrl+O")
    add("save", tr("Salva"), "save", window.file_save, "Ctrl+S")
    add("save_as", tr("Salva come"), "export", window.file_save_as, "Ctrl+Shift+S")
    tb.addSeparator()
    add("print", tr("Stampa"), "print", window.file_print, "Ctrl+P")
    add("find", tr("Cerca"), "search", window.edit_find, "Ctrl+F")
    add("sign", tr("Firma"), "sign", window.action_signature, "Ctrl+Shift+G")
    tb.addSeparator()
    add("undo", tr("Annulla"), "undo", window.edit_undo, "Ctrl+Z")
    add("redo", tr("Ripeti"), "redo", window.edit_redo, "Ctrl+Y")
    tb.addSeparator()

    tools_menu = tb.addWidget(_tool_selector(window, theme_pal))
    acts["tools"] = tools_menu  # type: ignore[assignment]
    tb.addSeparator()
    add("zoom_out", tr("Riduci"), "zoom-out", window.view_zoom_out, "Ctrl+-")
    zoom_label = QLabel("100%")
    zoom_label.setMinimumWidth(46)
    zoom_label.setAlignment(Qt.AlignCenter)
    acts["zoom_label"] = QLabel  # type: ignore[assignment]
    tb.addWidget(zoom_label)
    add("zoom_in", tr("Ingrandisci"), "zoom-in", window.view_zoom_in, "Ctrl++")
    add("fit_page", tr("Adatta alla pagina"), "fit-page", window.view_fit_page, "Ctrl+0")
    tb.addSeparator()
    add("rotate_left", tr("Ruota a sinistra"), "rotate-left", lambda: window.pages_rotate(-90), "Ctrl+Shift+Left")
    add("rotate_right", tr("Ruota a destra"), "rotate-right", lambda: window.pages_rotate(90), "Ctrl+Shift+Right")
    tb.addSeparator()
    add("fullscreen", tr("Schermo intero"), "fullscreen", window.toggle_fullscreen, "F11")
    return tb, acts


def _tool_selector(window, pal: theme.Palette) -> QWidget:
    """Menu a tendina con tutti gli strumenti, raggruppati."""
    box = QWidget()
    from PySide6.QtWidgets import QHBoxLayout, QToolButton

    h = QHBoxLayout(box)
    h.setContentsMargins(2, 0, 2, 0)
    btn = QToolButton()
    btn.setText(tr("Seleziona"))
    btn.setIcon(icons.icon("select", pal.text, 20))
    _marchia(btn, "select", 20)
    btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    btn.setPopupMode(QToolButton.InstantPopup)
    menu = btn.menu()
    if menu is None:
        from PySide6.QtWidgets import QMenu

        menu = QMenu(btn)
        btn.setMenu(menu)
    # I nomi degli strumenti stanno in tabelle di dati, non in una chiamata
    # con un letterale: si traducono qui, dove diventano testo. Le tabelle
    # restano in italiano e sono anche il riferimento del catalogo.
    for key, label, ico, _tasto, tip in TOOL_ITEMS:
        a = QAction(icons.icon(ico, pal.text, 20), tr(label), btn)
        _marchia(a, ico, 20)
        a.setToolTip(tr(tip))
        a.triggered.connect(lambda _c=False, k=key: window.select_tool(k))
        menu.addAction(a)
    menu.addSeparator()
    for key, ico, label in FIELD_TOOL_ITEMS:
        a = QAction(icons.icon(ico, pal.text, 20), tr(label), btn)
        _marchia(a, ico, 20)
        a.triggered.connect(lambda _c=False, k=key: window.select_tool(k))
        menu.addAction(a)
    h.addWidget(btn)
    window._tool_button = btn
    return box


def _marchia(azione, nome: str, size: int) -> None:
    """Ricorda il nome e la dimensione dell'icona, per ridisegnarla dopo.

    Le icone sono disegnate a mano e prendono il colore dal tema: senza questo
    segno al cambio tema la barra restava con le icone del tema precedente.
    """
    azione.setProperty("nome_icona", nome)
    azione.setProperty("size_icona", size)


def _ridisegna(azione, pal: theme.Palette) -> None:
    nome = azione.property("nome_icona")
    if not nome:
        return
    size = int(azione.property("size_icona") or 20)
    azione.setIcon(icons.icon(nome, pal.text, size))


def refresh_icons(window, pal: theme.Palette) -> None:
    """Ridisegna le icone delle barre e del menu strumenti con la palette data.

    Le icone sono vettoriali e colorate a mano, quindi cambiar tema le lasciava
    del colore vecchio: sulla barra scura restavano icone scure, invisibili.
    """
    for tb in window.findChildren(QToolBar):
        for a in tb.actions():
            _ridisegna(a, pal)
    btn = getattr(window, "_tool_button", None)
    if btn is None:
        return
    _ridisegna(btn, pal)
    menu = btn.menu()
    if menu is not None:
        for a in menu.actions():
            _ridisegna(a, pal)


def build_annot_toolbar(window, pal: theme.Palette) -> tuple[QToolBar, dict[str, QAction]]:
    """Barra contestuale degli strumenti di annotazione."""
    tb = QToolBar("Annotazione")
    tb.setObjectName("annotToolbar")
    tb.setIconSize(QSize(20, 20))
    window.addToolBar(tb)
    acts: dict[str, QAction] = {}

    def add(key: str, text: str, icon: str, slot, shortcut: str = "", checkable: bool = False) -> QAction:
        a = QAction(icons.icon(icon, pal.text, 20), text, window)
        _marchia(a, icon, 20)
        # le scorciatoie sono già sulle voci di menu: duplicarle qui le rende
        # ambigue e Qt non le gestisce più
        a.setToolTip(f"{text} ({shortcut})" if shortcut else text)
        a.setCheckable(checkable)
        a.triggered.connect(slot)
        tb.addAction(a)
        acts[key] = a
        return a

    add("annot_style", tr("Stile"), "magic", window.action_annot_style)
    add("marker_style", tr("Colore evidenziazione"), "highlight", window.action_marker_style)
    tb.addSeparator()
    add("snap", tr("Magnetismo"), "grid", window.action_toggle_snap, "", True)
    add("grid", tr("Griglia"), "grid", window.action_toggle_grid, "Ctrl+'", True)
    add("fields", tr("Evidenzia campi"), "fields", window.action_toggle_fields, "", True)
    tb.addSeparator()
    add("text_style", tr("Stile testo"), "text", window.action_text_style)
    add("image_style", tr("Proprietà immagine"), "image", window.action_image_props)
    add("field_props", tr("Proprietà campo"), "form", window.action_field_props)
    tb.addSeparator()
    add("delete", tr("Elimina selezione"), "trash", window.action_delete_selection, "Delete")
    add("flatten", tr("Appiattisci annotazioni"), "flatten", window.action_flatten_annots)
    return tb, acts


def build_text_toolbar(window, pal: theme.Palette) -> tuple[QToolBar, dict[str, QWidget]]:
    """Barra per le proprietà del testo selezionato."""
    tb = QToolBar("Testo")
    tb.setObjectName("textToolbar")
    window.addToolBar(tb)
    widgets: dict[str, QWidget] = {}

    font = QComboBox()
    font.setMinimumWidth(150)
    for name in ("Helvetica", "Helvetica-Bold", "Times-Roman", "Courier", "Symbol", "ZapfDingbats"):
        font.addItem(name, name)
    font.currentIndexChanged.connect(lambda: window.apply_text_style())
    tb.addWidget(QLabel(tr(" Font ")))
    tb.addWidget(font)
    widgets["font"] = font

    size = QSpinBox()
    size.setRange(4, 200)
    size.setValue(12)
    size.setSuffix(" pt")
    size.valueChanged.connect(lambda: window.apply_text_style())
    tb.addWidget(QLabel(tr("  Dimensione ")))
    tb.addWidget(size)
    widgets["size"] = size

    color = QLineEdit()
    color.setFixedWidth(76)
    # il valore di partenza e' un codice colore, non un testo da tradurre: e'
    # quello che l'utente vede nel campo e quello che va in parametro al motore
    color.setText("#1b1f27")
    color.editingFinished.connect(lambda: window.apply_text_style())
    tb.addWidget(QLabel(tr("  Colore ")))
    tb.addWidget(color)
    widgets["color"] = color

    from PySide6.QtWidgets import QPushButton

    for key, text, slot in (
        ("bold", "B", window.action_text_bold),
        ("italic", "I", window.action_text_italic),
        ("underline", "U", window.action_text_underline),
    ):
        b = QPushButton(text)
        b.setFixedWidth(34)
        b.setCheckable(True)
        b.clicked.connect(slot)
        tb.addWidget(b)
        widgets[key] = b

    for key, label, align in (
        ("align_left", "Sinistra", 0),
        ("align_center", "Centrato", 1),
        ("align_right", "Destra", 2),
        ("align_justify", "Giustificato", 3),
    ):
        b = QPushButton(label)
        b.clicked.connect(lambda _c=False, a=align: window.apply_text_align(a))
        tb.addWidget(b)
        widgets[key] = b
    return tb, widgets


def build_zoom_toolbar(window, pal: theme.Palette) -> tuple[QToolBar, dict[str, QWidget]]:
    """Barra dello zoom e della modalità di visualizzazione."""
    tb = QToolBar("Visualizzazione")
    tb.setObjectName("viewToolbar")
    window.addToolBar(tb)
    widgets: dict[str, QWidget] = {}
    mode = QComboBox()
    for label, val in (
        ("Adatta alla larghezza", "fit_width"),
        ("Adatta alla pagina", "fit_page"),
        ("Dimensione reale", "actual"),
    ):
        mode.addItem(label, val)
    mode.currentIndexChanged.connect(lambda: window.apply_zoom_mode())
    tb.addWidget(mode)
    widgets["zoom_mode"] = mode

    layout = QComboBox()
    for label, val in (("Scorrimento continuo", "continuous"), ("Pagina singola", "single"), ("Pagine affiancate", "facing")):
        layout.addItem(label, val)
    layout.currentIndexChanged.connect(lambda: window.apply_view_mode())
    tb.addWidget(layout)
    widgets["layout"] = layout
    return tb, widgets
