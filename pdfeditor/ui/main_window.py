"""Finestra principale: collega documento, vista, pannelli e comandi."""

from __future__ import annotations

import os
import tempfile
import time
import webbrowser
from pathlib import Path
from typing import Any

from PIL import Image
from PySide6.QtCore import QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QCloseEvent, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __app_name__, __repo_url__, __version__
from ..core import document as docmod
from ..core import geometry as geo
from ..core import i18n
from ..core.i18n import tr
from ..core import settings as settingsmod
from ..core import textlayout
from ..core import units
from ..features import digitalsign
from ..signature import manager as sigmanager
from . import icons, panels, theme, toolbars
from .dialogs import props
from .dialogs.signature_dialog import SignatureDialog
from .page_view import AREA_CLIC, PdfView

#: I filtri delle finestre di dialogo sono funzioni e non costanti: la parte
#: leggibile e' una frase da tradurre, e in una costante di modulo la lingua
#: resterebbe quella del primo import.
def pdf_filter() -> str:
    """Il filtro dei documenti PDF."""
    return tr("Documenti PDF (*.pdf);;Tutti i file (*)")


def image_filter() -> str:
    """Il filtro delle immagini."""
    return tr("Immagini (*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp);;Tutti i file (*)")

# Annotazioni che si comportano come marcatori di testo
MARKER_TOOLS = {"highlight", "underline", "strikeout", "squiggly"}

#: Dagli strumenti di campo al tipo di campo conosciuto dal motore. La
#: corrispondenza non e' un semplice prefisso: «field_check» arriva a
#: ``Document.add_field`` come «check», nome che in ``WIDGET_TYPES`` non
#: esiste, e ogni casella di spunta moriva con «Tipo di campo non
#: supportato: check». Con la tabella il nome non si può più sbagliare.
FIELD_TOOLS: dict[str, str] = {
    "field_text": "text",
    "field_check": "checkbox",
    "field_radio": "radio",
    "field_combo": "combo",
    "field_list": "list",
    "field_button": "button",
    "field_signature": "signature",
}


#: dimensioni predefinite per gli strumenti che si usano con un clic: la vista
#: manda il punto premuto, non un riquadro, e il codice più in avanti lavora
#: con riquadri
AREA_PUNTO: dict[str, tuple[float, float]] = dict(AREA_CLIC)
AREA_PUNTO.update({
    "text": (260.0, 70.0),
    "freetext": (260.0, 70.0),
    "signature": (180.0, 60.0),
    "note": (22.0, 22.0),
    "stamp": (90.0, 60.0),
    "link": (220.0, 24.0),
})


def _come_punto(valore) -> bool:
    """True se il valore è un singolo punto, non un riquadro né una lista."""
    if isinstance(valore, (list, tuple)):
        return False
    if isinstance(valore, geo.Rect):
        return False
    return hasattr(valore, "x") or hasattr(valore, "X")


def _conta(n: int, italiano: tuple[str, str], inglese: tuple[str, str]) -> str:
    """«1 pagina selezionata» e «3 pagine selezionate».

    In italiano il singolare e il plurale cambiano anche l'aggettivo, quindi la
    forma giusta non si ottiene sostituendo solo il nome: la barra di stato
    scriveva «1 pagina selezionate». In inglese i due nomi sono diversi
    («page» e «pages»), quindi servono due coppie e non una.

    Il numero lo mette questa funzione e non va ripetuto nella parola: alcuni
    chiamanti scrivevano «3 campi rilevati (3)».
    """
    singolare, plurale = inglese if i18n.lingua() == "en" else italiano
    return f"{n} {singolare if n == 1 else plurale}"


def _font_con_stile(fontname: str, bold: bool, italic: bool) -> str:
    """Il font di base con grassetto e corsivo applicati.

    Le quattro famiglie dei font di base hanno quattro volti ciascuna: senza
    questo passaggio le caselle di testo usavano solo il romanzo e le leve
    «B» e «I» non cambiavano nulla.
    """
    chiave = textlayout.BASE_FONTS.get(fontname, fontname)
    if bold and italic:
        return {"helv": "hebi", "tiro": "tibo", "cour": "cobi"}.get(chiave, chiave)
    if bold:
        return {"helv": "hebo", "tiro": "tibo", "cour": "cobo"}.get(chiave, chiave)
    if italic:
        return {"helv": "hebi", "tiro": "tiit", "cour": "cobi"}.get(chiave, chiave)
    return chiave


def confini_di_divisione(pagine: int, segnalibri=None, ogni: int = 1) -> list[int]:
    """Le pagine di inizio di ogni pezzo, in divisione per segnalibri o per blocchi.

    I segnalibri sono un traguardo dentro il documento, non il suo inizio: il
    primo pezzo parte sempre dalla prima pagina. Prima partiva dal primo
    segnalibro, quindi con un segnalibro a pagina 5 le pagine da 0 a 4 non
    finivano in nessun file e la divisione perdeva pezzi senza dirlo.

    ``segnalibri`` a lista, anche vuota, sceglie la divisione per segnalibri:
    senza segnalibri il documento resta in un pezzo solo. A ``None`` si usa
    invece la divisione a blocchi di ``ogni`` pagine.
    """
    if segnalibri is not None:
        segni = sorted({int(p) for p in segnalibri if 0 < int(p) < pagine})
        return [0, *segni]
    passo = max(1, int(ogni))
    return list(range(0, max(pagine, 1), passo))


class MainWindow(QMainWindow):
    """Finestra principale dell'editor."""

    def __init__(self) -> None:
        super().__init__()
        self.settings = settingsmod.Settings()
        self.pal = theme.DARK if self.settings.get("theme") == "scuro" else theme.LIGHT
        self.doc = docmod.Document()
        self.library = sigmanager.SignatureLibrary()
        self._warned_encryption = False
        # le azioni dei menu vanno conservate: senza, il garbage collector le
        # elimina e i menu si svuotano da soli (vedi _mi)
        self._azioni_menu: list[Any] = []
        self._in_presentation = False
        self._stato_precedente: dict[str, Any] | None = None
        self.tool = "select"
        self.annots_style: dict[str, Any] = {
            "color": (0.78, 0.21, 0.18),
            "fill": None,
            "width": 2.0,
            "opacity": 1.0,
            "text": "",
        }
        self.marker_style: dict[str, Any] = {"mode": "highlight", "color": (1.0, 0.88, 0.4), "opacity": 1.0}
        self.text_style: dict[str, Any] = {
            "fontname": "helv",
            "fontsize": 12.0,
            "color": (0.11, 0.12, 0.15),
            "align": 0,
            "bold": False,
            "italic": False,
            "underline": False,
        }
        self._autosave_timer = QTimer(self)
        self._autosave_timer.timeout.connect(self._autosave)
        self._autosave_minutes = int(self.settings.get("autosave_minutes", 10))
        self._thumb_timer = QTimer(self)
        self._thumb_timer.setInterval(120)
        self._thumb_timer.timeout.connect(self._refresh_visible_thumbs)
        self._busy = False

        self.setWindowTitle(__app_name__)
        self.resize(1440, 900)
        self._build()
        self._apply_theme()
        self._load_recovery()
        self._start_autosave()

    # ------------------------------------------------------------------ UI

    def _build(self) -> None:
        self.view = PdfView()
        self.view.set_document(self.doc)
        self.view.status.connect(self._status)
        self.view.text_selected.connect(self._on_text_selected)
        self.view.page_changed.connect(self._on_page_changed)
        self.view.zoom_changed.connect(self._on_zoom)
        self.view.link_activated.connect(self._open_link)
        self.view.field_committed.connect(self._on_field_committed)
        self.view.signature_requested.connect(self._sign_field)
        self.view.request_tool_action.connect(self._on_tool_action)
        self.setCentralWidget(self.view)

        self.main_acts: dict[str, QAction] = {}
        self.annot_acts: dict[str, QAction] = {}
        # la barra principale viene tenuta: al cambio di lingua va rifatta,
        # e senza il riferimento non si può togliere quella vecchia
        self.tb_main, self.main_acts = toolbars.build_main_toolbar(self, self.pal)
        self.tb_annot, self.annot_acts = toolbars.build_annot_toolbar(self, self.pal)
        self.tb_text, self.text_widgets = toolbars.build_text_toolbar(self, self.pal)
        self.tb_zoom, self.view_widgets = toolbars.build_zoom_toolbar(self, self.pal)
        for t in (self.tb_annot, self.tb_text, self.tb_zoom):
            t.hide()
        self.annot_acts["snap"].setChecked(bool(self.settings.get("snap_enabled")))
        self.annot_acts["grid"].setChecked(bool(self.settings.get("grid_visible")))
        self.annot_acts["fields"].setChecked(bool(self.settings.get("highlight_fields")))
        self.view.set_snap(bool(self.settings.get("snap_enabled")),
                             bool(self.settings.get("snap_guides", True)))
        self.view.set_grid(bool(self.settings.get("grid_visible")), float(self.settings.get("grid_size", 18)))

        self._build_docks()
        self._build_menus()
        self._build_status()
        self._connect_doc_events()
        self._update_actions()

    def _build_docks(self) -> None:
        # pannello sinistro: miniature
        from .thumbnails import ThumbnailsPanel

        self.thumbs = ThumbnailsPanel()
        self.thumbs.set_document(self.doc)
        self.thumbs.page_activated.connect(self._goto_page)
        self.thumbs.selection_changed.connect(self._on_thumb_selection)
        self.thumbs.reorder_requested.connect(self._reorder_pages)
        self.thumbs.context_action.connect(self._thumb_action)
        self.dock_thumbs = self._dock(tr("Pagine"), Qt.LeftDockWidgetArea, self.thumbs)
        self.thumbs.set_width(int(self.settings.get("thumb_w", theme.METRICS.thumb_w)))

        # pannello destro a schede
        self.tabs = QTabWidget()
        self.panel_search = panels.SearchPanel()
        self.panel_search.navigate.connect(self._goto_hit)
        self.panel_search.replace_all.connect(self._replace_all)
        self.panel_search.replace_one.connect(self._replace_one)
        self.panel_search.highlight_all.connect(self._highlight_all)
        self.panel_bookmarks = panels.BookmarksPanel()
        self.panel_bookmarks.navigate.connect(self._goto_page)
        self.panel_bookmarks.changed.connect(lambda: self._reload_panels())
        self.panel_bookmarks.add_requested.connect(self._add_bookmark)
        self.panel_bookmarks.remove_requested.connect(self._remove_bookmark)
        self.panel_bookmarks.rename_requested.connect(self._rename_bookmark)
        self.panel_bookmarks.move_requested.connect(self._move_bookmark)
        self.panel_fields = panels.FieldsPanel()
        self.panel_fields.edit_requested.connect(self._goto_field)
        self.panel_fields.focus_requested.connect(self._goto_field)
        self.panel_fields.clear_requested.connect(self.reset_form)
        self.panel_fields.flatten_requested.connect(self.flatten_fields)
        self.panel_attach = panels.AttachmentsPanel()
        self.panel_attach.add_requested.connect(self._add_attachment)
        self.panel_attach.save_requested.connect(self._save_attachment)
        self.panel_attach.remove_requested.connect(self._remove_attachment)
        self.panel_attach.open_requested.connect(self._open_attachment)
        self.panel_comments = panels.CommentsPanel()
        self.panel_comments.navigate.connect(self._goto_hit)
        self.panel_comments.delete_requested.connect(self._delete_annot_at)
        self.panel_comments.reply_requested.connect(self._reply_comment)
        self.panel_quality = panels.QualityPanel()
        self.panel_quality.fix_requested.connect(self._fix_quality_issue)
        self.panel_quality.goto_page_requested.connect(self._goto_page)
        self.panel_quality.refresh_requested.connect(lambda: self.panel_quality.load(self.doc))
        self.panel_props = panels.PropertiesPanel()
        self.panel_props.changed.connect(self._apply_metadata)
        self.panel_props.xmp_requested.connect(self._edit_xmp)
        for w, label in zip(
            (
                self.panel_search,
                self.panel_fields,
                self.panel_bookmarks,
                self.panel_comments,
                self.panel_attach,
                self.panel_props,
                self.panel_quality,
            ),
            panels.NOMI_SCHEDE,
        ):
            self.tabs.addTab(w, tr(label))
        # i controlli di qualita' rasterizzano le pagine: si eseguono quando la
        # scheda viene aperta, non a ogni modifica del documento
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.panel_quality.tabs.currentChanged.connect(lambda _: self._quality_reload())
        self.dock_side = self._dock(tr("Strumenti"), Qt.RightDockWidgetArea, self.tabs)
        self.dock_side.hide()

    def _dock(self, title: str, area, widget: QWidget) -> QDockWidget:
        d = QDockWidget(title, self)
        d.setWidget(widget)
        d.setObjectName(f"dock_{title.lower()}")
        self.addDockWidget(area, d)
        return d

    def _build_menus(self) -> None:
        mb = self.menuBar()

        m = mb.addMenu(self._titolo_menu("&File"))
        self._mi(m, tr("Nuovo"), "Ctrl+N", self.file_new)
        self._mi(m, tr("Apri…"), "Ctrl+O", self.file_open)
        self._mi(m, tr("Apri recente"), None, None, submenu=True)
        self._rebuild_recent(m)
        m.addSeparator()
        self._mi(m, tr("Salva"), "Ctrl+S", self.file_save)
        self._mi(m, tr("Salva come…"), "Ctrl+Shift+S", self.file_save_as)
        self._mi(m, tr("Salva una copia…"), None, self.file_save_copy)
        m.addSeparator()
        self._mi(m, tr("Esporta…"), "Ctrl+E", self.file_export)
        self._mi(m, tr("Importa da immagini…"), None, self.file_import_images)
        self._mi(m, tr("Unisci documenti…"), None, self.file_merge)
        self._mi(m, tr("Dividi documento…"), None, self.file_split)
        self._mi(m, tr("Riduci dimensione del file…"), None, self.file_reduce_size)
        m.addSeparator()
        self._mi(m, tr("Stampa…"), "Ctrl+P", self.file_print)
        self._mi(m, tr("Esporta testo…"), None, self.export_text)
        m.addSeparator()
        self._mi(m, tr("Esci"), "Ctrl+Q", self.close)

        m = mb.addMenu(self._titolo_menu("&Modifica"))
        self._mi(m, tr("Annulla"), "Ctrl+Z", self.edit_undo)
        self._mi(m, tr("Ripeti"), "Ctrl+Y", self.edit_redo)
        m.addSeparator()
        self._mi(m, tr("Taglia"), "Ctrl+X", lambda: self._clip("cut"))
        self._mi(m, tr("Copia"), "Ctrl+C", lambda: self._clip("copy"))
        self._mi(m, tr("Incolla"), "Ctrl+V", lambda: self._clip("paste"))
        self._mi(m, tr("Elimina"), "Delete", self.action_delete_selection)
        m.addSeparator()
        self._mi(m, tr("Trova…"), "Ctrl+F", self.edit_find)
        self._mi(m, tr("Trova successivo"), "F3", lambda: self.panel_search.step(1))
        self._mi(m, tr("Trova precedente"), "Shift+F3", lambda: self.panel_search.step(-1))
        self._mi(m, tr("Sostituisci…"), "Ctrl+H", self.edit_replace)
        m.addSeparator()
        self._mi(m, tr("Seleziona tutto"), "Ctrl+A", self.action_select_all)
        self._mi(m, tr("Deseleziona"), "Esc", self.action_deselect)
        self._mi(m, tr("Proprietà del documento…"), "Ctrl+D", self.action_doc_props)

        m = mb.addMenu(self._titolo_menu("&Visualizza"))
        self._mi(m, tr("Adatta alla pagina"), "Ctrl+0", self.view_fit_page)
        self._mi(m, tr("Adatta alla larghezza"), "Ctrl+1", self.view_fit_width)
        self._mi(m, tr("Dimensione reale"), "Ctrl+2", self.view_actual_size)
        self._mi(m, tr("Ingrandisci"), "Ctrl++", self.view_zoom_in)
        self._mi(m, tr("Riduci"), "Ctrl+-", self.view_zoom_out)
        m.addSeparator()
        self._mi(m, tr("Schermo intero"), "F11", self.toggle_fullscreen)
        self._mi(m, tr("Presentazione"), "Ctrl+Shift+F", self.toggle_presentation)
        m.addSeparator()
        self._mi(m, tr("Pannello pagine"), "Ctrl+Shift+P", lambda: self.dock_thumbs.setVisible(not self.dock_thumbs.isVisible()))
        self._mi(m, tr("Pannelli laterali"), "Ctrl+Shift+L", self._toggle_side_panel)
        self._mi(m, tr("Griglia"), "Ctrl+'", self.action_toggle_grid)
        self._mi(m, tr("Magnetismo"), None, self.action_toggle_snap)
        self._mi(m, tr("Evidenzia campi"), None, self.action_toggle_fields)
        m.addSeparator()
        self._mi(m, tr("Tema scuro"), None, self.toggle_theme)

        m = mb.addMenu(self._titolo_menu("&Annota"))
        for key, label, ico in toolbars.TOOL_ITEMS_ANNOTA:
            self._mi(m, tr(label), None, lambda _c=False, k=key: self._start_tool(k), ico)
        m.addSeparator()
        self._mi(m, tr("Allega file…"), None, self._attach_annotation, "attach")
        self._mi(m, tr("Collegamento…"), None, self._insert_link, "link")
        m.addSeparator()
        self._mi(m, tr("Appiattisci annotazioni"), None, self.action_flatten_annots, "flatten")
        self._mi(m, tr("Appiattisci campi"), None, self.flatten_fields, "form")
        self._mi(m, tr("Azzera campi"), None, self.reset_form, "replace")

        m = mb.addMenu(self._titolo_menu("&Moduli"))
        for key, ico, label in toolbars.FIELD_TOOL_ITEMS:
            self._mi(m, tr(label), None, lambda _c=False, k=key: self._start_tool(k), ico)
        m.addSeparator()
        self._mi(m, tr("Proprietà del campo…"), None, self.action_field_props, "form")
        self._mi(m, tr("Compila tutti i campi vuoti"), None, self._focus_first_field)
        m.addSeparator()
        self._mi(m, tr("Verifica firma digitale"), None, self.action_verify_signatures, "shield")
        self._mi(m, tr("Firma digitalmente…"), "Ctrl+Shift+D", self.action_digital_sign, "sign")

        m = mb.addMenu(self._titolo_menu("&Pagine"))
        self._mi(m, tr("Inserisci pagina vuota…"), "Ctrl+Shift+N", self.page_insert, "add-page")
        self._mi(m, tr("Inserisci da file…"), None, self.page_insert_from_file, "doc-open")
        m.addSeparator()
        self._mi(m, tr("Duplica"), None, lambda: self._thumb_action("duplicate", self._selected_pages()), "pages")
        self._mi(m, tr("Estrai in un nuovo documento…"), None, lambda: self._thumb_action("extract", self._selected_pages()), "export")
        self._mi(m, tr("Elimina"), None, lambda: self._thumb_action("delete", self._selected_pages()), "trash")
        m.addSeparator()
        self._mi(m, tr("Ruota a sinistra"), "Ctrl+Shift+Left", lambda: self.pages_rotate(-90), "rotate-left")
        self._mi(m, tr("Ruota a destra"), "Ctrl+Shift+Right", lambda: self.pages_rotate(90), "rotate-right")
        self._mi(m, tr("Ruota di 180°"), None, lambda: self.pages_rotate(180))
        m.addSeparator()
        self._mi(m, tr("Impostazione pagina…"), None, self.page_setup, "pages")
        self._mi(m, tr("Ritaglia pagina…"), None, self.page_crop, "crop")
        self._mi(m, tr("Ripristina ritaglio"), None, lambda: self._thumb_action("reset_crop", self._selected_pages()))
        m.addSeparator()
        self._mi(m, tr("Numerazione pagine…"), None, self.pages_number, "pages")
        self._mi(m, tr("Rimuovi numerazione"), None, self.pages_unnumber)
        self._mi(m, tr("Seleziona tutte le pagine"), "Ctrl+Shift+A", lambda: self.thumbs.select_pages(list(range(self.doc.page_count))))

        m = mb.addMenu(self._titolo_menu("&Firma"))
        self.menu_firma = m
        self._mi(m, tr("Inserisci firma…"), "Ctrl+Shift+G", self.action_signature, "sign")
        self._mi(m, tr("Compila campo firma"), None, self._sign_first_field, "handwrite")
        m.addSeparator()
        self._mi(m, tr("Libreria delle firme…"), None, self.action_signature_library, "handwrite")
        self._mi(m, tr("Tutte le firme salvate"), None, None, submenu=True)
        self._rebuild_signature_menu(m)
        m.addSeparator()
        self._mi(m, tr("Firma digitale (certificato)…"), None, self.action_digital_sign, "shield")

        m = mb.addMenu(self._titolo_menu("&Strumenti"))
        self._mi(m, tr("OCR (riconosci testo)…"), None, self.action_ocr, "ocr")
        self._mi(m, tr("Proteggi documento…"), None, self.action_security, "lock")
        self._mi(m, tr("Verifica firme…"), None, self.action_verify_signatures, "shield")
        self._mi(m, tr("Rileva campi e moduli"), None, self.action_detect_fields, "fields")
        m.addSeparator()
        self._mi(m, tr("Lingua…"), None, self.action_language, "fields")
        self._mi(m, tr("Preferenze…"), "Ctrl+,", self.action_preferences, "grid")

        m = mb.addMenu("&?")
        self._mi(m, tr("Scorciatoie da tastiera"), "F1", self.action_shortcuts)
        self._mi(m, tr("Informazioni su {app}").format(app=__app_name__), None, self.action_about)
        self._mi(m, tr("Licenze di terze parti"), None, self.action_third_party)

    def _titolo_menu(self, titolo: str) -> str:
        """Il titolo di un menu, tradotto, con l'acceleratore rimesso a posto.

        L'ampersand resta fuori dalla traduzione: «&Modifica» nel catalogo
        sarebbe una chiave che nessuno scrive a mano, e una lettera sbagliata
        si vede solo con l'interfaccia in inglese. Per questo il titolo si
        traduce per intero e non si usa `addMenu(tr("&Modifica"))`.
        """
        if "&" in titolo:
            _, testo = titolo.split("&", 1)
            return "&" + tr(testo)
        return tr(titolo)

    def _mi(self, menu, text: str, shortcut: str | None, slot, icon: str = "", submenu: bool = False):
        """Crea una voce di menu.

        Le azioni vanno tenute vive esplicitamente: create con la finestra
        come genitore e aggiunte a un menu, se nessun riferimento Python le
        conserva vengono raccolte dal garbage collector e spariscono dal menu.
        Succedeva davvero: File, Modifica e Visualizza risultavano vuoti.
        """
        if submenu:
            sub = menu.addMenu(text)
            self._azioni_menu.append(sub)
            return sub
        # Non si usa QAction(icona, testo, genitore) con icona None: in quel
        # caso PySide6 sceglie l'overload sbagliato e l'azione resta senza
        # testo, cioè invisibile nel menu. File, Modifica e Visualizza erano
        # pieni di voci senza nome.
        a = QAction(text, self)
        if icon:
            a.setIcon(icons.icon(icon, self.pal.text, 20))
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        if slot is not None:
            a.triggered.connect(slot)
        menu.addAction(a)
        self._azioni_menu.append(a)
        return a

    def _build_status(self) -> None:
        sb = QStatusBar()
        self.setStatusBar(sb)
        self.lbl_status = QLabel(tr("Pronto"))
        self.lbl_page = QLabel(tr("Pagina 0 di 0"))
        self.lbl_zoom = QLabel("100%")
        self.lbl_coords = QLabel("")
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(180)
        self.progress.setVisible(False)
        sb.addWidget(self.lbl_status, 1)
        sb.addPermanentWidget(self.lbl_coords)
        sb.addPermanentWidget(self.lbl_page)
        sb.addPermanentWidget(self.lbl_zoom)
        sb.addPermanentWidget(self.progress)

    def _connect_doc_events(self) -> None:
        self.doc.events.on("pages", self._on_pages_changed)
        self.doc.events.on("changed", self._on_doc_changed)
        self.doc.events.on("dirty", self._on_dirty)
        self.doc.events.on("field", self._on_field_event)

    def _apply_theme(self) -> None:
        # la palette attiva e' aggiornata per prima: le finestre aperte dopo
        # la scelta la leggono da li' e nascono gia' del colore giusto
        theme.attiva(self.pal)
        self.setStyleSheet(theme.stylesheet(self.pal))
        self.view.set_theme(self.pal)
        self.thumbs.set_palette_colors(self.pal)
        for pannello in (self.panel_search, self.panel_fields, self.panel_bookmarks,
                         self.panel_comments, self.panel_attach, self.panel_props,
                         self.panel_quality):
            pannello.set_palette_colors(self.pal)
        toolbars.refresh_icons(self, self.pal)
        self.view_widgets["zoom_mode"].setCurrentIndex(
            max(0, self.view_widgets["zoom_mode"].findData(self.settings.get("zoom_mode")))
        )

    # ------------------------------------------------------------- documento

    def _on_doc_changed(self, *_a) -> None:
        self.view.scene_obj.refresh_pixmaps()
        self.view.refresh_field_states()
        self.view.refresh_links()
        self.view.viewport().update()
        self._update_actions()
        self._warn_encryption_lost()

    def _warn_encryption_lost(self) -> None:
        """Avvisa una volta sola che la protezione non puo' essere conservata.

        MuPDF perde la cifratura quando serializza il documento per la
        cronologia: senza un avviso, l'utente scoprirebbe il problema solo al
        salvataggio, quando ormai e' troppo tardi per il file che intendeva
        proteggere.
        """
        if not getattr(self.doc, "_encryption_lost", False) or self._warned_encryption:
            return
        self._warned_encryption = True
        self._status(
            tr("Attenzione: le modifiche hanno fatto perdere la cifratura. "
            "Per salvare usa «Esporta…» indicando una password.")
        )
        QMessageBox.warning(
            self,
            tr("Protezione non conservabile"),
            tr("Questo documento era protetto da password.\n\n"
            "Le modifiche non possono conservare la protezione: salvando sullo "
            "stesso file si otterrebbe un PDF senza password e senza restrizioni.\n\n"
            "Per procedere correttamente usa «Esporta…» e indica la password "
            "nell'esportazione, oppure rimuovi la protezione e riapplicala."),
        )

    def _on_pages_changed(self, count: int = -1) -> None:
        self.view.scene_obj.rebuild()
        self.thumbs.rebuild()
        self.thumbs.refresh_all()
        self._thumb_timer.start()
        self._reload_panels()
        self._update_actions()

    def _on_dirty(self, dirty: bool) -> None:
        base = self.doc.filename
        self.setWindowTitle(f"{'*' if dirty else ''}{base} — {__app_name__}")

    def _on_page_changed(self, index: int) -> None:
        self.lbl_page.setText(tr("Pagina {n} di {tot}").format(n=index + 1, tot=self.doc.page_count))
        self.thumbs.select_page(index)

    def _on_zoom(self, zoom: float) -> None:
        self.lbl_zoom.setText(f"{zoom * 100:.0f}%")
        self.lbl_page.setText(tr("Pagina {n} di {tot}").format(n=self.view.current_page() + 1, tot=self.doc.page_count))

    def _status(self, text: str) -> None:
        self.lbl_status.setText(text)

    def _on_text_selected(self, parole: int) -> None:
        """Conteggio delle parole selezionate, come nella barra di stato di Acrobat."""
        if parole:
            self.lbl_status.setText(_conta(parole, ("parola selezionata", "parole selezionate"),
                               ("word selected", "words selected")))
        elif self.lbl_status.text().endswith("selezionate"):
            self.lbl_status.setText(tr("Pronto"))

    def _on_tab_changed(self, indice: int) -> None:
        if self.tabs.widget(indice) is self.panel_quality:
            self._quality_reload()

    def _quality_reload(self) -> None:
        if self.doc.is_open and self.tabs.currentWidget() is self.panel_quality:
            self._busy_start("Controllo del documento…")
            try:
                self.panel_quality.load(self.doc)
            finally:
                self._busy_end()

    def _fix_quality_issue(self, azione: str) -> None:
        """Esegue la correzione suggerita dal controllo di qualita'."""
        if not self.doc.is_open:
            return
        try:
            if azione == "imposta_lingua":
                self.doc.set_document_language("it-IT")
                messaggio = "Lingua del documento impostata su italiano"
            elif azione == "imposta_titolo":
                nome = self.doc.path.stem if self.doc.path else "Documento"
                self.doc.set_metadata({"title": nome})
                messaggio = tr("Titolo impostato su «{nome}»").format(nome=nome)
            elif azione == "ordina_campi":
                n = self.doc.sort_fields_in_reading_order()
                if not n:
                    self._status(tr("I campi sono già in ordine di lettura"))
                    self.panel_quality.load(self.doc)
                    return
                messaggio = tr("Riordinati {n} campi secondo l'ordine di lettura").format(n=n)
            elif azione == "rimuovi_protezione":
                if not self._confirm(
                    tr("Rimuovendo la protezione chiunque potrà aprire e modificare "
                    "il documento. Vuoi continuare?")
                ):
                    return
                self.doc.remove_encryption("")
                messaggio = tr("Protezione rimossa")
            elif azione == "ocr":
                self.action_ocr()
                return
            elif azione == "riduci_file":
                self.file_reduce_size()
                return
            elif azione == "riduci_risoluzione":
                self._status(
                    tr("Le immagini a risoluzione bassa si risolvono alla fonte: "
                    "riesportare le figure dal foglio di origine.")
                )
                return
            else:
                self._status(tr("Nessuna correzione automatica disponibile"))
                return
        except Exception as exc:
            self._error(exc, "Correzione non riuscita")
            return
        self._on_doc_changed()
        self.panel_quality.load(self.doc)
        self._status(messaggio)

    def _reload_panels(self) -> None:
        self.panel_bookmarks.load(self.doc)
        self.panel_fields.load(self.doc)
        self.panel_attach.load(self.doc)
        self.panel_comments.load(self.doc)
        self.panel_props.load(self.doc)

    def _update_actions(self) -> None:
        has = self.doc.is_open
        for k in ("save", "save_as", "print", "find", "sign", "undo", "redo", "rotate_left", "rotate_right"):
            if k in self.main_acts:
                self.main_acts[k].setEnabled(has)
        if "undo" in self.main_acts:
            self.main_acts["undo"].setEnabled(self.doc.history.can_undo)
            self.main_acts["undo"].setToolTip(
                tr("Annulla: {azione}").format(azione=self.doc.history.undo_text())
                if self.doc.history.can_undo
                else tr("Annulla")
            )
            self.main_acts["redo"].setEnabled(self.doc.history.can_redo)
        self.lbl_page.setText(tr("Pagina {n} di {tot}").format(n=self.view.current_page() + 1, tot=self.doc.page_count))
        if has and not self.doc.has_form_fields if hasattr(self.doc, "has_form_fields") else False:
            pass
        for key in ("snap", "grid", "fields"):
            if key in self.annot_acts:
                on = {
                    "snap": self.view.snap_enabled(),
                    "grid": self.view.grid_visible(),
                    "fields": self.view.highlight_fields,
                }[key]
                self.annot_acts[key].setChecked(on)

    def _busy_start(self, text: str = "Elaborazione…") -> None:
        self._busy = True
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self._status(text)
        QApplication.processEvents()

    def _busy_end(self, text: str = "Pronto") -> None:
        self._busy = False
        self.progress.setVisible(False)
        self._status(text)

    def _error(self, exc: Exception | str, title: str = "Operazione non riuscita") -> None:
        self._status(title)
        QMessageBox.warning(self, title, str(exc))

    def _confirm(self, text: str, title: str = "Conferma") -> bool:
        if not self.settings.get("confirm_destructive", True):
            return True
        return QMessageBox.question(self, title, text) == QMessageBox.Yes

    # ------------------------------------------------------------ file menu

    def file_new(self) -> None:
        if not self._maybe_save():
            return
        self.doc.new()
        self.view.set_document(self.doc)
        self._on_pages_changed()
        self._status(tr("Nuovo documento"))

    def file_open(self) -> None:
        if not self._maybe_save():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Apri documento", self._start_dir(), pdf_filter())
        if path:
            self.load_path(path)

    def load_path(self, path: str, password: str = "") -> bool:
        self._busy_start("Apertura…")
        try:
            self.doc.open(path, password)
        except docmod.DocumentError as exc:
            if "Password" in str(exc):
                from .dialogs.props import _ask_password

                pw, ok = _ask_password(self, "Il documento è protetto: inserisci la password")
                if ok and pw:
                    self._busy_start("Apertura…")
                    try:
                        self.doc.open(path, pw)
                    except Exception as exc2:
                        self._busy_end()
                        self._error(exc2, "Apertura non riuscita")
                        return False
            else:
                self._busy_end()
                self._error(exc, "Apertura non riuscita")
                return False
        except Exception as exc:
            self._busy_end()
            self._error(exc, "Apertura non riuscita")
            return False
        self.view.set_document(self.doc)
        self._on_pages_changed()
        self._on_dirty(False)
        self.settings.add_recent(str(path))
        self._rebuild_recent(self.menuBar().actions()[0].menu())
        self._busy_end(tr("Aperto: {file}").format(file=self.doc.filename))
        return True

    def _start_dir(self) -> str:
        if self.doc.path:
            return str(self.doc.path.parent)
        return str(self.settings.get("last_export_dir") or Path.home())

    def file_save(self) -> None:
        if not self.doc.is_open:
            return
        if not self.doc.path:
            self.file_save_as()
            return
        if getattr(self.doc, "_encryption_lost", False):
            # salvare produrrebbe un file senza protezione: si porta
            # l'utente alla via che la conserva
            self._warn_encryption_lost()
            risposta = QMessageBox.question(
                self,
                tr("Protezione non conservabile"),
                tr("Salvare sullo stesso file produrrebbe un PDF senza password.\n\n"
                "Vuoi aprire la finestra di esportazione, dove puoi indicare la "
                "password?"),
                QMessageBox.Yes | QMessageBox.No,
            )
            if risposta == QMessageBox.Yes:
                self.file_export()
            return
        self._busy_start("Salvataggio…")
        try:
            self.doc.save()
        except Exception as exc:
            self._busy_end()
            self._error(exc)
            return
        self._busy_end(f"Salvato: {self.doc.filename}")
        self._update_actions()

    def file_save_as(self) -> None:
        if not self.doc.is_open:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Salva come", self._start_dir(), pdf_filter())
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        # "Salva come" cambia il file su cui si sta lavorando
        self._save_to(path)

    def file_reduce_size(self) -> None:
        """Riduce le immagini del documento e scrive il risultato in un file nuovo."""
        if not self.doc.is_open:
            return
        self._busy_start("Analisi delle immagini…")
        try:
            inventario = self.doc.image_inventory()
        except Exception as exc:
            self._busy_end()
            self._error(exc)
            return
        self._busy_end()
        if not inventario:
            self._status(tr("Il documento non contiene immagini: non c'è nulla da ridurre."))
            return
        dlg = props.ReduceSizeDialog(
            inventario, int(self.settings.get("compression_quality", 85)), self
        )
        if dlg.exec() != props.QDialog.Accepted:
            return
        v = dlg.values()
        path, _ = QFileDialog.getSaveFileName(self, "Salva il documento ridotto", self._start_dir(), pdf_filter())
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        self._busy_start("Riduzione del file…")
        try:
            r = self.doc.reduce_size(
                path, quality=v["quality"], max_dpi=v["max_dpi"], recompress_all=v["recompress_all"]
            )
        except Exception as exc:
            self._busy_end()
            self._error(exc, "Riduzione non riuscita")
            return
        self.settings.set("compression_quality", v["quality"])
        self._busy_end()
        if r["saved"] <= 0:
            QMessageBox.information(
                self,
                tr("Riduzione del file"),
                f"Nessun guadagno: il documento risultante sarebbe uguale o più grande.\n\n"
                f"File: {Path(path).name}",
            )
            return
        QMessageBox.information(
            self,
            tr("Riduzione del file"),
            f"Ridotte {r['images']} immagini.\n\n"
            f"Prima: {r['before'] / 1_048_576:.1f} MB\n"
            f"Dopo:  {r['after'] / 1_048_576:.1f} MB\n"
            f"Risparmio: {100 * (1 - r['ratio']):.0f}%\n\n"
            f"File: {Path(path).name}\n\n"
            "Il documento aperto non è stato modificato.",
        )

    def file_save_copy(self) -> None:
        if not self.doc.is_open:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Salva una copia", self._start_dir(), pdf_filter())
        if not path:
            return
        self._busy_start("Salvataggio della copia…")
        try:
            self.doc.save_copy(path)
        except Exception as exc:
            self._busy_end()
            self._error(exc, "Copia non riuscita")
            return
        self.settings.add_recent(path)
        self._rebuild_recent(self.menuBar().actions()[0].menu())
        # il documento aperto non cambia: si dice solo dove e' finita la copia
        self._busy_end(f"Copia salvata: {Path(path).name}")

    def _save_to(self, path: str) -> None:
        self._busy_start("Salvataggio…")
        try:
            self.doc.save(path)
        except Exception as exc:
            self._busy_end()
            self._error(exc)
            return
        self.settings.add_recent(path)
        self._rebuild_recent(self.menuBar().actions()[0].menu())
        self._busy_end(f"Salvato: {Path(path).name}")

    def _rebuild_recent(self, menu) -> None:
        if menu is None:
            return
        sub = None
        for a in menu.actions():
            if a.text().startswith("Apri recente"):
                sub = a.menu()
        if sub is None:
            return
        sub.clear()
        files = self.settings.recent_files()
        if not files:
            a = QAction(tr("Nessun file recente"), self)
            a.setEnabled(False)
            sub.addAction(a)
            return
        for f in files:
            act = QAction(f, self)
            act.triggered.connect(lambda _c=False, p=f: self.load_path(p))
            sub.addAction(act)
        sub.addSeparator()
        act = QAction(tr("Cancella elenco"), self)
        act.triggered.connect(self._clear_recent)
        sub.addAction(act)

    def _clear_recent(self) -> None:
        self.settings.clear_recent()
        self._rebuild_recent(self.menuBar().actions()[0].menu())

    def _maybe_save(self) -> bool:
        if not self.doc.dirty or not self.doc.is_open:
            return True
        r = QMessageBox.question(
            self,
            tr("Salvare le modifiche?"),
            f"«{self.doc.filename}» ha modifiche non salvate. Vuoi salvarle?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
        )
        if r == QMessageBox.Save:
            self.file_save()
            return not self.doc.dirty
        return r == QMessageBox.Discard

    def file_print(self) -> None:
        from .printing import print_document

        if not self.doc.is_open:
            return
        try:
            print_document(self, self.doc, float(self.settings.get("print_dpi", 300)))
        except Exception as exc:
            # senza questa guardia una stampante che rifiuta il foglio, o
            # inesistente, faceva comparire la traccia dell'errore invece di un
            # messaggio: l'errore di stampa non e' un difetto del programma
            self._error(exc, "Stampa non riuscita")

    def file_export(self) -> None:
        if not self.doc.is_open:
            return
        dlg = props.ExportDialog(self.doc.page_count, self, self.view.current_page())
        if dlg.exec() != props.QDialog.Accepted:
            return
        try:
            v = dlg.values()
        except ValueError as exc:
            self._error(exc, "Intervallo di pagine non valido")
            return
        kind = v["kind"]
        # `parse_range` non restituisce piu' una lista vuota: senza questo
        # controllo un intervallo illeggibile veniva sostituito in silenzio
        # dalla pagina corrente e l'utente riceveva un file con una pagina sola
        pages = v["pages"]
        if not pages:
            self._status(tr("Esportazione interrotta: nessuna pagina indicata"))
            return
        if kind == "text":
            path, _ = QFileDialog.getSaveFileName(self, "Esporta testo", self._start_dir(), "Testo (*.txt)")
            if path:
                Path(path).write_text(self.doc.extract_text(), encoding="utf-8")
                self._status(tr("Testo esportato in {file}").format(file=Path(path).name))
            return
        if kind == "pdfa":
            path, _ = QFileDialog.getSaveFileName(self, "Esporta PDF/A", self._start_dir(), pdf_filter())
            if path:
                self._export_pdfa(path, pages, v["pdfa"])
            return
        default_name = f"{self.doc.path.stem}_p{pages[0] + 1}.png" if self.doc.path else "pagina.png"
        folder = QFileDialog.getExistingDirectory(self, "Cartella di destinazione", self._start_dir())
        if not folder:
            return
        self._export_images(Path(folder), pages, v["dpi"], "jpg" if kind in ("image", "current") and v["quality"] < 95 else "png", v["quality"])
        self.settings.set("last_export_dir", folder)

    def _export_images(self, folder: Path, pages: list[int], dpi: int, fmt: str, quality: int) -> None:
        self._busy_start("Esportazione…")
        self.progress.setRange(0, len(pages))
        try:
            folder.mkdir(parents=True, exist_ok=True)
            for i, p in enumerate(pages):
                if p < 0 or p >= self.doc.page_count:
                    continue
                data = self.doc.extract_page_image(p, dpi=dpi, fmt=fmt, quality=quality)
                (folder / f"pagina_{p + 1:04d}.{fmt}").write_bytes(data)
                self.progress.setValue(i + 1)
                QApplication.processEvents()
        except Exception as exc:
            self._busy_end()
            self._error(exc, "Esportazione non riuscita")
            return
        self._busy_end(tr("Esportate {pagine} in {cartella}").format(
                pagine=_conta(len(pages), ("1 pagina", "pagine"), ("1 page", "pages")),
                cartella=folder,
            ))

    def _export_pdfa(self, path: str, pages: list[int], level: str) -> None:
        from .printing import convert_pdfa

        self._busy_start("Conversione PDF/A…")
        try:
            ok, msg = convert_pdfa(self.doc, path, pages, level)
        except Exception as exc:
            self._busy_end()
            self._error(exc, "Conversione non riuscita")
            return
        self._busy_end(msg)
        if not ok:
            QMessageBox.information(self, tr("Conversione PDF/A"), msg)

    def file_import_images(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Scegli le immagini", self._start_dir(), image_filter())
        if not files:
            return
        self._busy_start("Importazione immagini…")
        try:
            self.doc.open_images(files)
        except Exception as exc:
            self._busy_end()
            self._error(exc)
            return
        self.view.set_document(self.doc)
        self._on_pages_changed()
        self._busy_end(f"Importate {len(files)} immagini")

    def file_merge(self) -> None:
        dlg = props.MergeDialog(self)
        if dlg.exec() != props.QDialog.Accepted:
            return
        files = dlg.files()
        if not files:
            return
        self._busy_start("Unione documenti…")
        try:
            self.doc.insert_pdf_pages(files[0], self.doc.page_count)
            for f in files[1:]:
                self.doc.insert_pdf_pages(f, self.doc.page_count)
        except Exception as exc:
            self._busy_end()
            self._error(exc, "Unione non riuscita")
            return
        self._on_pages_changed()
        self._busy_end(f"Uniti {len(files)} documenti")

    def file_split(self) -> None:
        dlg = props.SplitDialog(self.doc.page_count, self)
        if dlg.exec() != props.QDialog.Accepted:
            return
        v = dlg.values()
        folder = QFileDialog.getExistingDirectory(self, "Cartella di destinazione", self._start_dir())
        if not folder:
            return
        self._busy_start("Divisione…")
        try:
            if v["by_bookmarks"]:
                confini = confini_di_divisione(
                    self.doc.page_count, [e["page"] for e in self.doc.outline()]
                )
            else:
                confini = confini_di_divisione(self.doc.page_count, ogni=v["every"])
            prodotti = []
            for n, inizio in enumerate(confini):
                fine = confini[n + 1] if n + 1 < len(confini) else self.doc.page_count
                if fine <= inizio:
                    continue
                destinazione = Path(folder) / f"{v['prefix']}_{n + 1:02d}.pdf"
                self.doc.export(destinazione, list(range(inizio, fine)))
                prodotti.append(destinazione.name)
        except Exception as exc:
            self._busy_end()
            self._error(exc, "Divisione non riuscita")
            return
        self._busy_end(f"Documento diviso in {len(prodotti)} file: {folder}")

    def export_text(self) -> None:
        if not self.doc.is_open:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Esporta testo", self._start_dir(), "Testo (*.txt)")
        if path:
            Path(path).write_text(self.doc.extract_text(), encoding="utf-8")
            self._status(tr("Testo esportato in {file}").format(file=Path(path).name))

    # ------------------------------------------------------------ edit menu

    def edit_undo(self) -> None:
        if not self.doc.is_open:
            return
        cmd = self.doc.history.undo()
        if cmd is None:
            return
        self._on_pages_changed()
        self._status(tr("Annullato: {azione}").format(azione=cmd.text))
        self._update_actions()

    def edit_redo(self) -> None:
        if not self.doc.is_open:
            return
        cmd = self.doc.history.redo()
        if cmd is None:
            return
        self._on_pages_changed()
        self._status(tr("Ripetuto: {azione}").format(azione=cmd.text))
        self._update_actions()

    def edit_find(self) -> None:
        self.tabs.setCurrentWidget(self.panel_search)
        self.dock_side.setVisible(True)
        self.panel_search.find.setFocus()
        self.panel_search.find.selectAll()

    def edit_replace(self) -> None:
        self.edit_find()
        self.panel_search.replace.setFocus()

    def _goto_hit(self, page: int, rect) -> None:
        self.view.go_to_page(page)
        if rect is not None:
            self.view.zoom_to_rect(page, rect)
        self.statusBar().showMessage(tr("Pagina {n}").format(n=page + 1), 3000)

    def _replace_all(self, needle: str, replacement: str, case: bool, whole: bool) -> None:
        if not self.doc.is_open:
            return
        if not needle:
            return
        n = 0
        self._busy_start("Sostituzione…")
        for i in range(self.doc.page_count):
            n += self.doc.replace_text(needle, replacement, i, case=case, whole_word=whole)
        self._on_doc_changed()
        self._busy_end(_conta(n, ("occorrenza sostituita", "occorrenze sostituite"),
                                ("occurrence replaced", "occurrences replaced"))
                if n else tr("Nessuna occorrenza trovata"))

    def _replace_one(self, needle: str, replacement: str, case: bool, whole: bool) -> None:
        hit = self.panel_search.current_hit()
        if hit is None:
            return
        n = self.doc.replace_text(
            needle, replacement, hit["page"], case=case, whole_word=whole
        )
        self._on_doc_changed()
        self._status(_conta(n, ("occorrenza sostituita", "occorrenze sostituite"),
                                ("occurrence replaced", "occurrences replaced"))
                if n else tr("Nessuna sostituzione"))
        self.panel_search.search(self.doc)

    def _highlight_all(self, needle: str, case: bool, whole: bool) -> None:
        if not self.doc.is_open or not needle:
            return
        total = 0
        self._busy_start("Evidenziazione…")
        for i in range(self.doc.page_count):
            total += self.doc.highlight_hits(needle, i, case=case, whole_word=whole)
        self._on_doc_changed()
        self._busy_end(_conta(total, ("occorrenza evidenziata", "occorrenze evidenziate"),
                          ("occurrence highlighted", "occurrences highlighted")))

    def _clip(self, mode: str) -> None:
        if mode == "copy":
            if self.view.copy_selection():
                self._status(tr("Testo copiato negli appunti"))
                return
            # nessun testo selezionato: si copia il dato del campo evidenziato
            xref = self._selected_xref()
            if xref is not None and self.doc.is_open:
                campo = next((f for f in self.doc.fields() if f.xref == xref), None)
                if campo is not None and campo.value not in (None, ""):
                    QGuiApplication.clipboard().setText(str(campo.value))
                    # `label` non esiste su FieldInfo: la chiave e' `name`, e
                    # il ramo non e' mai stato eseguito, quindi il difetto
                    # era invisibile finche' la selezione non tornava viva
                    self._status(tr("Valore di «{campo}» copiato").format(campo=campo.name))
                    return
            self._status(tr("Nessun testo selezionato da copiare"))
            return
        self._status(
            tr("Operazione «{modo}» non disponibile su questo elemento").format(modo=mode)
        )

    def action_select_all(self) -> None:
        """Nella vista seleziona tutto il testo, altrimenti tutte le pagine."""
        if self.view.hasFocus() or self.doc is None or not self.doc.is_open:
            self.view.select_all_text()
            return
        self.thumbs.select_pages(list(range(self.doc.page_count)))

    def action_deselect(self) -> None:
        # Esc è anche la scorciatoia della voce di menu, quindi Qt la intercetta
        # prima che arrivi all'editor del campo: senza questa riga premere Esc
        # mentre si compila un campo deselezionava e non chiudeva l'editor.
        if self.view.active_field is not None:
            self.view.hide_field_editor()
            self._status(tr("Campo chiuso"))
            return
        self.view.clear_text_selection()
        self.view.clear_selection()

    def action_delete_selection(self) -> None:
        if not self.doc.is_open:
            return
        xref = self._selected_xref()
        if xref is None:
            self._status(tr("Seleziona un campo o un'annotazione da eliminare"))
            return
        page = self.view.current_page()
        # la pagina va letta da dove sta l'elemento, non da quella a vista:
        # con piu' pagine selezionate si cancellava quello sbagliato
        pagina = self._selected_page()
        if pagina is not None:
            page = pagina
        try:
            if self.view.selection_kind() == "image":
                self.doc.delete_image(page, xref)
            else:
                self.doc.delete_annot(page, xref)
        except Exception as exc:
            self._error(exc)
            return
        self.view.clear_selection()
        self._on_doc_changed()
        self._reload_panels()
        self._status(tr("Elemento eliminato"))

    def _selected_page(self) -> int | None:
        """Pagina dell'elemento selezionato, se la vista la conosce."""
        return self.view.selected_page()

    def _selected_display_rect(self):
        return self.view.selection_display_rect()

    def _selected_xref(self) -> int | None:
        return self.view.selection_xref()

    def action_doc_props(self) -> None:
        self.tabs.setCurrentWidget(self.panel_props)
        self.dock_side.setVisible(True)
        self.panel_props.load(self.doc)

    def _apply_metadata(self, values: dict[str, str]) -> None:
        try:
            self.doc.set_metadata(values)
        except Exception as exc:
            self._error(exc)
            return
        self._status(tr("Proprietà aggiornate"))

    def _edit_xmp(self) -> None:
        dlg = props.XmpDialog(self.doc.xmp_metadata(), self)
        if dlg.exec() == props.QDialog.Accepted:
            self.doc.set_xmp_metadata(dlg.xml())
            self._status(tr("Metadati XMP aggiornati"))

    # --------------------------------------------------------- view menu

    def view_zoom_in(self) -> None:
        self.view.zoom_in()

    def view_zoom_out(self) -> None:
        self.view.zoom_out()

    def view_fit_page(self) -> None:
        self.view.apply_zoom_mode.__self__  # noqa: B018
        self.view._zoom_mode = "fit_page"
        self.view.apply_zoom_mode()

    def view_fit_width(self) -> None:
        self.view._zoom_mode = "fit_width"
        self.view.apply_zoom_mode()

    def view_actual_size(self) -> None:
        self.view.set_zoom(1.0, mode="actual")

    def apply_zoom_mode(self) -> None:
        self.view._zoom_mode = str(self.view_widgets["zoom_mode"].currentData())
        self.view.apply_zoom_mode()
        self.settings.set("zoom_mode", self.view._zoom_mode)

    def apply_view_mode(self) -> None:
        self.view.set_view_mode(str(self.view_widgets["layout"].currentData()))
        self.settings.set("view_mode", self.view.view_mode())

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def toggle_presentation(self) -> None:
        """Modalità presentazione: una pagina per volta, senza pannelli e barre.

        Il ritorno deve riportare tutto com'era. Prima si entrava ma non si
        usciva: docks e barre restavano nascosti in modo permanente e la vista
        restava bloccata su una sola pagina.
        """
        if self._in_presentation:
            self._in_presentation = False
            stato = self._stato_precedente
            self._stato_precedente = None
            self.dock_thumbs.setVisible(stato["pagine"])
            self.dock_side.setVisible(stato["lati"])
            self.tb_annot.setVisible(stato["annot"])
            self.tb_text.setVisible(stato["testo"])
            self.tb_zoom.setVisible(stato["zoom"])
            self.view.set_view_mode(stato["vista"])
            if stato["schermo_intero"]:
                self.showFullScreen()
            else:
                self.showNormal()
            self._update_actions()
            return

        self._stato_precedente = {
            "pagine": self.dock_thumbs.isVisible(),
            "lati": self.dock_side.isVisible(),
            "annot": self.tb_annot.isVisible(),
            "testo": self.tb_text.isVisible(),
            "zoom": self.tb_zoom.isVisible(),
            "vista": self.view.view_mode(),
            "schermo_intero": self.isFullScreen(),
        }
        self._in_presentation = True
        self.dock_thumbs.hide()
        self.dock_side.hide()
        self.tb_annot.hide()
        self.tb_text.hide()
        self.tb_zoom.hide()
        self.view.set_view_mode("single")
        self.view._zoom_mode = "fit_page"
        self.view.apply_zoom_mode()
        self.showFullScreen()
        self._update_actions()

    def _toggle_side_panel(self) -> None:
        self.dock_side.setVisible(not self.dock_side.isVisible())

    def action_toggle_grid(self) -> None:
        on = not self.view.grid_visible()
        self.view.set_grid(on, float(self.settings.get("grid_size", 18)))
        self.settings.set("grid_visible", on)
        self._update_actions()

    def action_toggle_snap(self) -> None:
        attivo = not self.view.snap_enabled()
        self.view.set_snap(attivo, self.view.snap_guides)
        self.settings.set("snap_enabled", attivo)
        self._update_actions()
        self._status(tr("Magnetismo ") + ("attivo" if attivo else "disattivato"))

    def action_toggle_fields(self) -> None:
        on = not self.view.highlight_fields
        self.view.set_fields_visible(on)
        self.settings.set("highlight_fields", on)
        self._update_actions()

    def toggle_theme(self) -> None:
        """Passa da tema chiaro a scuro e viceversa."""
        scuro = self.pal is theme.LIGHT
        self.pal = theme.DARK if scuro else theme.LIGHT
        self.settings.set("theme", "scuro" if scuro else "chiaro")
        self._apply_theme()
        self._status(tr("Tema scuro") if scuro else "Tema chiaro")

    # -------------------------------------------------------- annot menu

    def _start_tool(self, tool: str) -> None:
        self.select_tool(tool)
        self._status({
            "highlight": "Trascina sul testo da evidenziare",
            "underline": "Trascina sul testo da sottolineare",
            "strikeout": "Trascina sul testo da barrare",
            "squiggly": "Trascina sul testo da sottolineare a onda",
            "note": "Fai clic dove inserire la nota",
            "ink": "Disegna a mano libera",
            "freetext": "Trascina per creare la casella di testo",
            "stamp": "Fai clic per applicare il timbro",
        }.get(tool, "Fai clic e trascina per definire l'area"))

    def select_tool(self, tool: str) -> None:
        self.tool = tool
        self.view.set_tool(tool)
        if tool == "hand":
            self.statusBar().showMessage("Trascina per spostare la pagina", 2500)
        self.tb_annot.setVisible(tool not in ("select", "hand"))
        self.tb_text.setVisible(tool == "text")
        btn = getattr(self, "_tool_button", None)
        if btn is not None:
            for key, label, _i, _s, _t in toolbars.TOOL_ITEMS:
                if key == tool:
                    btn.setText(label)
                    btn.setIcon(icons.icon(_i, self.pal.text, 20))
                    break
            else:
                for key, i, label in toolbars.FIELD_TOOL_ITEMS:
                    if key == tool:
                        btn.setText(label)
                        btn.setIcon(icons.icon(i, self.pal.text, 20))
                        break

    def action_annot_style(self) -> None:
        shape = {"rect": "rect", "circle": "circle", "line": "line", "arrow": "arrow",
                 "ink": "ink", "polygon": "polygon", "note": "note", "stamp": "stamp"}.get(self.tool, "rect")
        dlg = props.AnnotationStyleDialog(shape, self)
        if dlg.exec() == props.QDialog.Accepted:
            v = dlg.values()
            self.annots_style.update(
                {"color": v["color"], "fill": v["fill"], "width": v["width"], "opacity": v["opacity"], "text": v["text"]}
            )
            self.view.set_annots_style("#%02x%02x%02x" % tuple(int(c * 255) for c in v["color"]), v["width"],
                                       "#%02x%02x%02x" % tuple(int(c * 255) for c in v["fill"]) if v["fill"] else None)
            self.select_tool(v["shape"])
            self._status(tr("Stile aggiornato"))

    def action_marker_style(self) -> None:
        dlg = props.MarkerStyleDialog(self.marker_style["mode"], self)
        if dlg.exec() == props.QDialog.Accepted:
            v = dlg.values()
            self.marker_style.update(v)
            self.select_tool(v["mode"])
            self._status(tr("Stile evidenziazione aggiornato"))

    def action_text_style(self) -> None:
        dlg = props.TextBoxDialog(self, self.text_style["fontname"], self.text_style["fontsize"])
        if dlg.exec() == props.QDialog.Accepted:
            v = dlg.values()
            self.text_style.update(
                {k: v[k] for k in ("fontname", "fontsize", "color", "align", "bold", "italic", "underline")}
            )
            self.tb_text.show()
            self._status(tr("Stile del testo aggiornato"))

    def apply_text_style(self) -> None:
        self.text_style["fontname"] = str(self.text_widgets["font"].currentData())
        self.text_style["fontsize"] = float(self.text_widgets["size"].value())
        col = self.text_widgets["color"].text().strip()
        try:
            from PySide6.QtGui import QColor

            c = QColor(col if col.startswith("#") else "#" + col)
            if c.isValid():
                self.text_style["color"] = (c.red() / 255, c.green() / 255, c.blue() / 255)
        except Exception:
            pass

    def _flag_testo(self, chiave: str, etichetta: str) -> None:
        """Commuta grassetto, corsivo o sottolineatura per la prossima casella.

        Le caselle della barra sono levabili: il valore segue il loro stato
        invece di restare un messaggio. Prima scrivevano solo «Grassetto
        applicato alla prossima casella di testo» e la casella usciva
        identica, con il grassetto che nessuno sapeva piu' togliere.
        """
        pulsante = self.text_widgets.get(chiave)
        stato = bool(pulsante.isChecked()) if pulsante is not None else not self.text_style[chiave]
        self.text_style[chiave] = stato
        if pulsante is not None:
            pulsante.setChecked(stato)
        self._status(
            tr("{etichetta} {stato} per la prossima casella di testo").format(
                etichetta=etichetta,
                stato=tr("attivo") if stato else tr("disattivato"),
            )
        )

    def action_text_bold(self) -> None:
        self._flag_testo("bold", tr("Grassetto"))

    def action_text_italic(self) -> None:
        self._flag_testo("italic", tr("Corsivo"))

    def action_text_underline(self) -> None:
        self._flag_testo("underline", "Sottolineatura")

    def apply_text_align(self, align: int) -> None:
        self.text_style["align"] = align
        self._status(tr("Allineamento impostato"))

    def action_image_props(self) -> None:
        """Dimensione e ritaglio dell'immagine selezionata.

        Non c'era niente da cambiare: la voce scriveva solo un messaggio. Le
        immagini non sono annotazioni, quindi non c'è una `FieldInfo` come per i
        campi: si guarda il tipo di elemento che la vista ha selezionato.
        """
        if not self.doc.is_open:
            return
        xref = self.view.selection_xref()
        if xref is None or self.view.selection_kind() != "image":
            self._status(tr("Seleziona un'immagine per cambiarne le proprietà"))
            return
        page = self.view.selected_page()
        rect = self.doc.image_rect(page, xref)
        if rect is None:
            self._status(tr("L'immagine selezionata non è più nel documento"))
            return
        info = self.doc.page_info(page)
        dlg = props.ImagePropertiesDialog((rect.width, rect.height),
                                          (info.rect.width, info.rect.height), self,
                                          (rect.x0, rect.y0))
        if dlg.exec() != props.QDialog.Accepted:
            return
        v = dlg.values()
        try:
            self.doc.move_image(page, xref, geo.Rect(v["rect"]))
        except Exception as exc:
            self._error(exc, "Ridimensionamento non riuscito")
            return
        if v["crop"]:
            try:
                self.doc.crop_page(page, info.rect)
            except Exception as exc:
                self._error(exc, "Ritaglio non riuscito")
                return
        # `move_image` toglie l'immagine e la reinserisce: l'xref cambia, quindi
        # la selezione va ricalcolata sul nuovo riquadro
        nuovo = self.doc.image_rects(page)
        for im in nuovo:
            if abs(im["rect"].width - v["rect"][2]) <= 1.5 and abs(im["rect"].height - v["rect"][3]) <= 1.5:
                self.view._sel_xref = im["xref"]
                self.view._sel_kind = "image"
                self.view.select_rect(page, self.doc.to_display_rect(page, im["rect"]))
                break
        self._on_doc_changed()
        self._status(tr("Immagine aggiornata"))

    def action_field_props(self) -> None:
        hit = self.view.active_field
        fields = self.doc.fields()
        if not fields:
            self._status(tr("Il documento non contiene campi modulo"))
            return
        if hit is None:
            info = fields[0]
        else:
            info = next((f for f in fields if f.page == hit[0] and f.xref == hit[1]), fields[0])
        dlg = props.FieldPropertiesDialog(info, self)
        if dlg.exec() == props.QDialog.Accepted:
            v = dlg.values()
            try:
                self.doc.set_field_properties(info.page, info.xref, v["props"])
                # La «Descrizione» è la chiave /TU del campo: senza questa riga
                # il testo scritto nella finestra veniva perso e il pulsante
                # annunciava comunque l'aggiornamento
                self.doc.set_field_tooltip(info.page, info.xref, v["tooltip"])
                if v["value"] != str(info.value or ""):
                    # la nuova lunghezza massima potrebbe rendere il valore
                    # appena inserito troppo lungo: si avvisa prima di salvare
                    valido, motivo = self.doc.validate_field_value(
                        info.page, info.xref, v["value"]
                    )
                    if not valido and not self._confirm(
                        tr("{motivo}\n\nSalvare comunque?").format(motivo=motivo),
                        tr("Valore non ammesso"),
                    ):
                        return
                    self.doc.set_field_value(info.page, info.xref, v["value"])
            except Exception as exc:
                self._error(exc)
                return
            self._on_doc_changed()
            self.panel_fields.load(self.doc)
            self._status(tr("Proprietà del campo aggiornate"))

    def action_flatten_annots(self) -> None:
        if not self.doc.is_open:
            return
        if not self._confirm(tr("Le annotazioni verranno incorporate nel contenuto e non saranno più modificabili. Procedere?")):
            return
        try:
            self.doc.flatten_annotations()
        except Exception as exc:
            self._error(exc)
            return
        self._on_doc_changed()
        self._status(tr("Annotazioni appiattite"))

    def flatten_fields(self) -> None:
        if not self.doc.is_open:
            return
        if not self._confirm(tr("I campi modulo diventeranno testo non modificabile. Procedere?")):
            return
        try:
            self.doc.flatten_fields()
        except Exception as exc:
            self._error(exc)
            return
        self._on_doc_changed()
        self.panel_fields.load(self.doc)
        self._status(tr("Campi appiattiti"))

    def reset_form(self) -> None:
        if not self.doc.is_open:
            return
        try:
            self.doc.reset_form()
        except Exception as exc:
            self._error(exc)
            return
        self._on_doc_changed()
        self.panel_fields.load(self.doc)
        self._status(tr("Campi azzerati"))

    def _attach_annotation(self) -> None:
        if not self.doc.is_open:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Allega file", self._start_dir(), "Tutti i file (*)")
        if not path:
            return
        data = Path(path).read_bytes()
        page = self.view.current_page()
        rect = geo.Rect(60, 60, 260, 120)
        try:
            # i byte vanno in `attachment_bytes`: passati come `text` finivano
            # in un `bytes.encode()` su un valore che era gia' bytes, e
            # l'allegato non si creava affatto
            self.doc.add_annot(
                page, "file", rect, attachment_bytes=data, filename=Path(path).name
            )
        except Exception as exc:
            self._error(exc)
            return
        self._on_doc_changed()
        self._status(tr("Allegato {file}").format(file=Path(path).name))

    def _insert_link(self) -> None:
        self.select_tool("link")
        self._status(tr("Fai clic dove inserire il collegamento"))

    def _open_link(self, uri: str) -> None:
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl

        if uri.startswith("http://") or uri.startswith("https://") or uri.startswith("mailto:"):
            if QMessageBox.question(self, tr("Collegamento"), f"Aprire nel browser?\n\n{uri}") == QMessageBox.Yes:
                QDesktopServices.openUrl(QUrl(uri))
        else:
            QMessageBox.information(self, tr("Collegamento"), uri)

    def _delete_annot_at(self, page: int, xref: int) -> None:
        try:
            self.doc.delete_annot(page, xref)
        except Exception as exc:
            self._error(exc)
            return
        self._on_doc_changed()
        self.panel_comments.load(self.doc)

    def _reply_comment(self, page: int, xref: int, text: str) -> None:
        try:
            self.doc.set_annot_props(page, xref, {"text": f"{text}"})
        except Exception as exc:
            self._error(exc)
            return
        self._on_doc_changed()
        self.panel_comments.load(self.doc)

    # ---------------------------------------------------- moduli e campi

    def _on_field_committed(self, page: int, xref: int, value: Any) -> None:
        # un campo con lunghezza massima o un menu a scelta possono rifiutare
        # il valore: meglio dirlo che salvare qualcosa che il lettore mostrera'
        # diversamente
        valido, motivo = self.doc.validate_field_value(page, xref, value)
        if not valido:
            if not self._confirm(
                    tr("{motivo}\n\nSalvare comunque?").format(motivo=motivo),
                    tr("Valore non ammesso"),
                ):
                self.view.refresh_field_states()
                self.view.viewport().update()
                return
        try:
            self.doc.set_field_value(page, xref, value)
        except Exception as exc:
            self._error(exc)
            return
        valore_salvato = next(
            (f.value for f in self.doc.fields() if f.xref == xref), value
        )
        if str(valore_salvato) != str(value):
            self._status(tr("Valore adattato al campo: {valore}").format(valore=valore_salvato))
        else:
            self._status(tr("Campo aggiornato: {valore}").format(valore=value))
        self.view.scene_obj.refresh_pixmaps()
        self.view.refresh_field_states()
        self.view.viewport().update()
        self.panel_fields.load(self.doc)

    def _on_field_event(self, page: int, xref: int) -> None:
        self.panel_fields.load(self.doc)

    def _goto_field(self, page: int, xref: int) -> None:
        self.view.go_to_page(page)
        for (p, x), st in self.view.field_states.items():
            if p == page and x == xref:
                # `zoom_to_rect` riceve il riquadro nello spazio pagina, come
                # danno i risultati di ricerca: passare quello mostrato faceva
                # centrare un punto vuoto sulle pagine ruotate
                self.view.zoom_to_rect(page, st["info"].rect)
                self.view.begin_field_edit(page, xref)
                break
        self.panel_fields.focus(page, xref)

    def _focus_first_field(self) -> None:
        for (p, x), st in self.view.field_states.items():
            if st["info"].value in (None, "", False, "Off") and not st["info"].read_only:
                self._goto_field(p, x)
                self._status(tr("Compila i campi evidenziati, poi Tab per il successivo"))
                return
        self._status(tr("Nessun campo vuoto da compilare"))

    def action_detect_fields(self) -> None:
        if not self.doc.is_open:
            return
        self.view.load_field_states()
        self.panel_fields.load(self.doc)
        self.tabs.setCurrentWidget(self.panel_fields)
        self.dock_side.setVisible(True)
        stats = self.doc.field_stats()
        if stats["total"] == 0:
            self._status(tr("Nessun campo modulo trovato nel documento"))
        else:
            kinds = ", ".join(f"{v} {k}" for k, v in stats["by_kind"].items())
            quanti = stats["total"]
            self._status(
                tr("Campi rilevati: {campi} ({tipi})").format(
                    campi=_conta(quanti, ("campo", "campi"), ("field", "fields")),
                    tipi=kinds,
                )
            )

    # ------------------------------------------------------------ pagine

    def _goto_page(self, index: int) -> None:
        self.view.go_to_page(index)

    def _on_thumb_selection(self, pages: list[int]) -> None:
        self._status(_conta(len(pages), ("pagina selezionata", "pagine selezionate"),
                       ("page selected", "pages selected"))
            if pages else "")

    def _selected_pages(self) -> list[int]:
        sel = self.thumbs.selected_pages()
        return sel or [self.view.current_page()]

    def _reorder_pages(self, order: list[int]) -> None:
        try:
            self.doc.move_pages(order)
        except Exception as exc:
            self._error(exc, "Riordino non riuscito")
            self.thumbs.rebuild()
            return
        self._on_pages_changed()
        self._status(tr("Pagine riordinate"))

    def _thumb_action(self, action: str, pages: list[int]) -> None:
        if not self.doc.is_open or not pages:
            return
        try:
            if action == "rotate_left":
                self.doc.rotate_pages(pages, -90)
            elif action == "rotate_right":
                self.doc.rotate_pages(pages, 90)
            elif action == "duplicate":
                self.doc.duplicate_pages(pages)
            elif action == "delete":
                if not self._confirm(
                        tr("Eliminare {pagine}?").format(
                            pagine=_conta(
                                len(pages),
                                ("1 pagina", "pagine"),
                                ("1 page", "pages"),
                            )
                        )
                    ):
                    return
                self.doc.delete_pages(pages)
            elif action == "extract":
                path, _ = QFileDialog.getSaveFileName(self, "Estrai pagine", self._start_dir(), pdf_filter())
                if path:
                    self.doc.export(path, pages)
                    self._status(
                        tr("Salvate {pagine} in {file}").format(
                            pagine=_conta(
                                len(pages), ("1 pagina", "pagine"), ("1 page", "pages")
                            ),
                            file=Path(path).name,
                        )
                    )
                    return
            elif action == "insert_after":
                last = max(pages)
                info = self.doc.page_info(last)
                self.doc.insert_page(last + 1, info.rect.width, info.rect.height)
            elif action == "reset_crop":
                n = self.doc.reset_crop(pages)
                self._status(
                    tr("Ritaglio ripristinato su {pagine}").format(
                        pagine=_conta(n, ("1 pagina", "pagine"), ("1 page", "pages"))
                    )
                )
                return
            elif action == "select_all":
                self.thumbs.select_pages(list(range(self.doc.page_count)))
                return
        except Exception as exc:
            self._error(exc)
            return
        self._on_pages_changed()
        self.thumbs.select_pages([p for p in pages if p < self.doc.page_count])

    def pages_rotate(self, degrees: int) -> None:
        if not self.doc.is_open:
            return
        pages = self._selected_pages()
        try:
            self.doc.rotate_pages(pages, degrees)
        except Exception as exc:
            self._error(exc)
            return
        self._on_pages_changed()
        self._status(tr("Pagine ruotate"))

    def page_insert(self) -> None:
        if not self.doc.is_open:
            return
        info = self.doc.page_info(self.view.current_page())
        dlg = props.PageSetupDialog((info.rect.width, info.rect.height), self)
        if dlg.exec() != props.QDialog.Accepted:
            return
        w, h, margin = dlg.values()
        at = self.thumbs.current_page() + 1
        try:
            self.doc.insert_page(at, w, h)
        except Exception as exc:
            self._error(exc)
            return
        self._on_pages_changed()
        self._status(tr("Pagina inserita"))

    def page_insert_from_file(self) -> None:
        if not self.doc.is_open:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Inserisci pagine da", self._start_dir(), pdf_filter())
        if not path:
            return
        at = self.thumbs.current_page() + 1
        try:
            self.doc.insert_pdf_pages(path, at)
        except Exception as exc:
            self._error(exc)
            return
        self._on_pages_changed()
        self._status(tr("Pagine inserite"))

    def page_setup(self) -> None:
        if not self.doc.is_open:
            return
        pages = self._selected_pages()
        dlg = props.PageSetupDialog(self.doc.page_info(pages[0]).rect, self)
        if dlg.exec() != props.QDialog.Accepted:
            return
        w, h, margin = dlg.values()
        self._busy_start("Ridimensionamento…")
        try:
            self.doc.set_page_size(pages, w, h)
        except Exception as exc:
            self._busy_end()
            self._error(exc)
            return
        self._busy_end("Dimensione pagina aggiornata")

    def pages_number(self) -> None:
        """Aggiunge la numerazione alle pagine selezionate."""
        if not self.doc.is_open:
            return
        dlg = props.PageNumberDialog(
            self.doc.page_count, bool(self.doc.has_page_numbers()), self
        )
        if dlg.exec() != props.QDialog.Accepted:
            return
        v = dlg.values()
        pagine = self._selected_pages() or list(range(self.doc.page_count))
        try:
            n = self.doc.add_page_numbers(
                pagine,
                first=v["first"],
                position=v["position"],
                margin=v["margin"],
                fontsize=v["fontsize"],
                skip_first=v["skip_first"],
                total=v["total"],
            )
        except Exception as exc:
            self._error(exc, "Numerazione non riuscita")
            return
        self._on_pages_changed()
        self._status(_conta(n, ("pagina numerata", "pagine numerate"),
                   ("page numbered", "pages numbered")))

    def pages_unnumber(self) -> None:
        if not self.doc.is_open:
            return
        if not self.doc.has_page_numbers():
            self._status(tr("Il documento non ha numerazione da rimuovere."))
            return
        if not self._confirm(tr("Rimuovere la numerazione dalle pagine?")):
            return
        try:
            n = self.doc.remove_page_numbers()
        except Exception as exc:
            self._error(exc)
            return
        self._on_pages_changed()
        self._status(_conta(n, ("numero di pagina rimosso", "numeri di pagina rimossi"),
                   ("page number removed", "page numbers removed")))

    def page_crop(self) -> None:
        """Ritaglia le pagine selezionate, riducendo l'area visibile."""
        if not self.doc.is_open:
            return
        pagine = self._selected_pages()
        if not pagine:
            return
        prima = self.doc.page_info(pagine[0])
        rilevato = self.doc.auto_crop_rect(pagine[0])
        dlg = props.CropPageDialog(
            (prima.rect.width, prima.rect.height),
            (rilevato.x0, rilevato.y0, rilevato.x1, rilevato.y1) if rilevato else None,
            self,
        )
        if dlg.exec() != props.QDialog.Accepted:
            return
        v = dlg.values()
        self._busy_start("Ritaglio…")
        try:
            if v["auto"]:
                if rilevato is None:
                    raise docmod.DocumentError(
                        "Non è stato possibile rilevare il contenuto della pagina."
                    )
                zona = rilevato
            else:
                x0, y0, x1, y1 = v["rect"]
                zona = geo.Rect(x0, y0, x1, y1)
            n = self.doc.crop_pages(pagine, zona)
        except Exception as exc:
            self._busy_end()
            self._error(exc, "Ritaglio non riuscito")
            return
        self._on_pages_changed()
        self.view.go_to_page(pagine[0])
        self._busy_end(_conta(n, ("pagina ritagliata", "pagine ritagliate"),
                   ("page cropped", "pages cropped")))

    # ------------------------------------------------------------- firma

    def action_signature(self) -> None:
        if not self.doc.is_open:
            return
        page = self.view.current_page()
        dlg = SignatureDialog(self.doc, page, self.library, self)
        try:
            if dlg.exec() != SignatureDialog.Accepted or dlg.result_image is None:
                return
        finally:
            # il dialogo puo' aver salvato, rinominato o cancellato una firma:
            # il menu delle firme salvate va ricalcolato comunque
            self._rebuild_signature_menu(getattr(self, "menu_firma", None))
        self._place_signature(page, dlg.result_image, dlg.spin_w.value(), dlg.spin_h.value(),
                              flatten=dlg.chk_flatten.isChecked(), field=dlg.signature_field())

    def _sign_field(self, page: int, info) -> None:
        dlg = SignatureDialog(self.doc, page, self.library, self)
        dlg.cmb_signature_field.setCurrentIndex(
            next((i for i, f in enumerate(dlg.sig_fields) if f.xref == info.xref), 0)
        )
        if dlg.exec() != SignatureDialog.Accepted or dlg.result_image is None:
            return
        # il campo firma preselezionato e' quello da firmare: la firma entra
        # nel suo riquadro e il valore viene impostato da _place_signature
        self._place_signature(page, dlg.result_image, dlg.spin_w.value(), dlg.spin_h.value(),
                              field=dlg.signature_field() or info)

    def _sign_first_field(self) -> None:
        for f in self.doc.fields():
            if f.type == "Signature":
                self._sign_field(f.page, f)
                return
        self.action_signature()

    def _posizione_per_un_elemento(self, page: int, w: float, h: float) -> geo.Rect:
        """Dove mettere un elemento nuovo: al centro di ciò che si vede.

        Prima si usava una ricerca di uno spazio libero, e la firma finiva in
        un punto a caso della pagina, lontano da dove si sta lavorando. Ora
        parte dal centro della parte della pagina effettivamente visibile, e
        resta subito selezionata, quindi si sposta con un clic.
        """
        info = self.doc.page_info(page)
        area = geo.Rect(info.rect)
        vista = self.view
        nodo = vista.scene_obj.node(page)
        if nodo is not None:
            vp = vista.viewport()
            if vp.width() > 1 and vp.height() > 1:
                alto_sx = vista.mapToScene(0, 0)
                basso_dx = vista.mapToScene(vp.width(), vp.height())
                visibile = vista._scene_rect(
                    page,
                    geo.Rect(alto_sx.x(), alto_sx.y(), basso_dx.x(), basso_dx.y()),
                )
                # la pagina puo' essere ruotata: si riporta nel suo spazio.
                # Rect non accetta un QRectF, quindi si passano le coordinate
                reale = self.doc.to_page_rect(page, geo.Rect(
                    visibile.x(), visibile.y(), visibile.x() + visibile.width(),
                    visibile.y() + visibile.height(),
                ))
                parte = geo.Rect(reale)
                if not parte.is_empty and parte.get_area() > 0:
                    area = parte & geo.Rect(info.rect)
        if area.is_empty or area.get_area() <= 0:
            area = geo.Rect(info.rect)
        limite = geo.Rect(info.rect)
        occupati = [geo.Rect(i["rect"]) for i in self.doc.image_rects(page)]

        def libero(box: geo.Rect) -> bool:
            return not any(box.intersects(o) and not (box & o).is_empty for o in occupati)

        x = area.x0 + max(0.0, (area.width - w) / 2)
        y = area.y0 + max(0.0, (area.height - h) / 2)
        # se il centro e' gia' occupato si prova poco piu' in basso e poi poco
        # piu' in alto: due elementi non devono finire uno sopra l'altro
        candidati = [y + passo * k for passo, quanti in ((h + 12, 14), (-(h + 12), 14))
                     for k in range(1, quanti + 1)]
        for tentativo in [y, *candidati]:
            box = geo.clamp_rect(geo.Rect(x, tentativo, x + w, tentativo + h), limite)
            if libero(box):
                return box
        return geo.clamp_rect(geo.Rect(x, y, x + w, y + h), limite)

    def _place_signature(self, page: int, image: Image.Image, w: float, h: float,
                         flatten: bool = False, field=None) -> None:
        if image is None:
            return
        if w <= 0 or h <= 0:
            w = 180.0
            h = 180.0 * image.height / max(image.width, 1)
        if flatten:
            image = _flatten_on_white(image)
        else:
            image = _white_to_alpha(image)
        import io

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        if field is not None:
            rect = self._rect_per_un_campo_firma(field, image)
        else:
            rect = self._posizione_per_un_elemento(page, w, h)
        try:
            self.doc.insert_image(page, rect, buf.getvalue(), keep_proportion=False)
        except Exception as exc:
            self._error(exc, "Inserimento firma non riuscito")
            return
        if field is not None:
            # Il campo firma vuoto accetta solo testo: senza questo la firma
            # finiva disegnata sopra il riquadro ma il modulo risultava ancora
            # da compilare.
            try:
                self.doc.set_field_value(field.page, field.xref, "Firmato")
            except Exception as exc:
                self._error(exc, "Valore del campo firma non impostato")
        self._on_doc_changed()
        self.panel_fields.load(self.doc)
        # la firma viene lasciata selezionata: si vede subito dove e' e si
        # trascina per metterla a posto, come qualsiasi altro elemento
        self._seleziona_ultima_immagine(page, rect)
        if field is not None:
            self._status(tr("Firma inserita nel campo «{campo}»").format(campo=field.name))
        else:
            self._status(tr("Firma inserita: trascinala per metterla a posto"))

    def _rect_per_un_campo_firma(self, field, image: Image.Image) -> geo.Rect:
        """Il riquadro in cui la firma entra nel campo firma, nello spazio pagina.

        Il riquadro del campo e' quello del modulo: la firma ci va dentro,
        proporzionata e centrata, con un piccolo margine perche' il bordo del
        campo resti visibile. Se il campo e' troppo piccolo si usa cosi' com'e',
        meglio una firma attaccata al bordo di un riquadro vuoto.
        """
        riquadro = geo.Rect(field.rect)
        if riquadro.is_empty or riquadro.width <= 0 or riquadro.height <= 0:
            return self._posizione_per_un_elemento(field.page, 180.0, 70.0)
        interno = geo.inflate(riquadro, -min(4.0, riquadro.width / 4, riquadro.height / 4))
        if interno.is_empty:
            interno = geo.Rect(riquadro)
        return geo.aspect_limited(interno, max(image.width, 1) / max(image.height, 1))

    def _seleziona_ultima_immagine(self, page: int, rect: geo.Rect) -> None:
        """Seleziona l'immagine appena inserita, con le maniglie di dimensione."""
        if self.view.tool != "select":
            self.view.set_tool("select")
        self.view.select_rect(page, self.doc.to_display_rect(page, rect))
        self.view.status.emit("Firma selezionata: trascinala, o usa le maniglie")

    def action_signature_library(self) -> None:
        dlg = SignatureDialog(self.doc, self.view.current_page(), self.library, self)
        dlg.tabs.setCurrentIndex(3)
        try:
            dlg.exec()
        finally:
            # da questa scheda si rinominano e si cancellano firme: senza il
            # ricalcolo il menu continuerebbe a mostrare quelle vecchie
            self._rebuild_signature_menu(getattr(self, "menu_firma", None))

    def _rebuild_signature_menu(self, menu) -> None:
        if menu is None:
            return
        sub = None
        for a in menu.actions():
            if a.text().startswith("Tutte le firme"):
                sub = a.menu()
        if sub is None:
            return
        sub.clear()
        if not self.library.entries:
            a = QAction(tr("Nessuna firma salvata"), self)
            a.setEnabled(False)
            sub.addAction(a)
            return
        for e in self.library.entries:
            act = QAction(e.display_name, self)
            act.triggered.connect(lambda _c=False, i=e.id: self._use_saved_signature(i))
            sub.addAction(act)
        if not self.library.entries:
            act = QAction(tr("(nessuna firma salvata)"), self)
            act.setEnabled(False)
            sub.addAction(act)

    def _use_saved_signature(self, sig_id: str) -> None:
        if not self.doc.is_open:
            return
        entry = self.library.by_id(sig_id)
        if entry is None:
            return
        img = self.library.image(entry)
        if img is None:
            return
        self._place_signature(self.view.current_page(), img, 180, 0)
        self._status(tr("Firma «{nome}» inserita").format(nome=entry.display_name))

    def action_digital_sign(self) -> None:
        if not self.doc.is_open:
            return
        dlg = props.SignatureSetupDialog(self.doc, self.view.current_page(), self)
        if dlg.exec() != props.QDialog.Accepted:
            return
        v = dlg.values()
        campo_xref = v.get("field_xref")
        # il documento firmato deve essere un file: se non e' mai stato salvato
        # si parte da una copia temporanea, altrimenti la firma non avrebbe
        # su cosa scrivere
        temporaneo: Path | None = None
        if self.doc.path:
            sorgente = self.doc.path
        else:
            temporaneo = Path(tempfile.gettempdir()) / f"korvaxoide_{os.getpid()}_da_firmare.pdf"
            self.doc.export(str(temporaneo))
            sorgente = temporaneo
        self._busy_start("Firma digitale…")
        try:
            if v["mode"] == "self":
                from ..core.settings import data_dir

                cert = digitalsign.make_self_signed(
                    v["common_name"], v["email"], v["org"], save_to=data_dir() / "certificati" / "personale.pem"
                )
            else:
                if not v["path"]:
                    raise digitalsign.SignatureError("Seleziona un file certificato.")
                cert = digitalsign.load_certificate(v["path"], v["password"])
            if self.doc.path:
                out = self.doc.path.parent / f"{self.doc.path.stem}_firmato.pdf"
            else:
                out = Path.cwd() / "firmato.pdf"
            if campo_xref:
                # firma dentro un campo esistente: il riquadro e la pagina
                # sono quelli del campo, non quelli scelti a mano
                campo = next(
                    (f for f in self.doc.fields() if f.xref == campo_xref), None
                )
                res = digitalsign.sign_document(
                    str(sorgente),
                    str(out),
                    cert,
                    page_index=campo.page if campo else self.view.current_page(),
                    rect=None,
                    field_xref=campo_xref,
                    reason=v["reason"],
                    location=v["location"],
                    name=v["common_name"] or cert.subject,
                    visible=v["visible"],
                )
            else:
                res = digitalsign.sign_document(
                    str(sorgente),
                    str(out),
                    cert,
                    page_index=self.view.current_page(),
                    rect=(72, self.doc.page_info(self.view.current_page()).rect.height - 140, 330,
                          self.doc.page_info(self.view.current_page()).rect.height - 60) if v["visible"] else None,
                    field_name="Firma digitale",
                    reason=v["reason"],
                    location=v["location"],
                    name=v["common_name"] or cert.subject,
                    visible=v["visible"],
                )
        except Exception as exc:
            self._busy_end()
            self._error(exc, "Firma non riuscita")
            return
        finally:
            if temporaneo is not None:
                try:
                    temporaneo.unlink(missing_ok=True)
                except OSError:
                    pass
        self._busy_end(res.message)
        dove = f"nel campo «{res.details.get('field')}»" if res.details.get("existing_field") else "in fondo alla pagina"
        QMessageBox.information(
            self,
            tr("Firma digitale"),
            f"{res.message}\n\nFile: {res.path}\n\n"
            f"La firma è stata apposta {dove} su una copia: "
            "il documento originale resta invariato.",
        )

    def action_verify_signatures(self) -> None:
        if not self.doc.is_open or not self.doc.path:
            self._status(tr("Salva il documento per poter verificare le firme"))
            return
        self._busy_start("Verifica firme…")
        try:
            sigs = digitalsign.verify_file(self.doc.path)
        except Exception as exc:
            self._busy_end()
            self._error(exc)
            return
        self._busy_end()
        if not sigs:
            QMessageBox.information(self, tr("Verifica firme"), tr("Il documento non contiene firme digitali."))
            return
        lines = []
        for s in sigs:
            lines.append(
                f"Pagina {s['page'] + 1} — {s.get('name', 'Firma')}\n"
                f"  Firmatario: {s.get('signer_name') or s.get('subject', '?')}\n"
                f"  Emittente: {s.get('issuer', '?')}\n"
                f"  Data: {s.get('date', '?')}\n"
                f"  Validità: {s.get('not_before', '?')} — {s.get('not_after', '?')}\n"
                f"  Attendibilità: {s.get('trust', '?')}\n"
                f"  Integrità: {s.get('integrity', '?')}\n"
            )
        QMessageBox.information(self, tr("Verifica firme"), "\n".join(lines))

    # ------------------------------------------------------------ strumenti

    def action_security(self) -> None:
        if not self.doc.is_open:
            return
        dlg = props.SecurityDialog(self.doc, self)
        if dlg.exec() != props.QDialog.Accepted:
            return
        v = dlg.values()
        if not v["user_pw"] and not v["owner_pw"] and v["permissions"] == -1:
            return
        self._busy_start("Protezione…")
        try:
            target = self.doc.path.parent / f"{self.doc.path.stem}_protetto.pdf" if self.doc.path else Path.cwd() / "protetto.pdf"
            self.doc.export(
                str(target),
                permissions=v["permissions"],
                owner_pass=v["owner_pw"],
                user_pass=v["user_pw"],
                algorithm=v["algorithm"],
            )
        except Exception as exc:
            self._busy_end()
            self._error(exc, "Protezione non riuscita")
            return
        self._busy_end(f"Documento protetto: {target.name}")
        QMessageBox.information(self, tr("Protezione"), f"Salvato il documento protetto:\n{target}")

    def action_ocr(self) -> None:
        from .ocr import run_ocr

        if not self.doc.is_open:
            return
        self._busy_start("Riconoscimento testo…")
        try:
            ok, msg = run_ocr(self.doc, str(self.settings.get("ocr_language", "ita")),
                              int(self.settings.get("ocr_dpi", 300)),
                              [self.view.current_page()])
        except Exception as exc:
            self._busy_end()
            self._error(exc)
            return
        self._busy_end(msg)
        if ok:
            self._on_doc_changed()
        else:
            QMessageBox.information(self, tr("OCR"), msg)

    def action_preferences(self) -> None:
        dlg = props.PreferencesDialog(self.settings, self)
        if dlg.exec() == props.QDialog.Accepted:
            v = dlg.values()
            self.settings.update(v)
            self.view.set_grid(v["grid_visible"], v["grid_size"])
            self.view.set_snap(v["snap_enabled"], self.settings.get("snap_guides", True))
            self.pal = theme.DARK if v["theme"] == "scuro" else theme.LIGHT
            self._apply_theme()
            self._restart_autosave()
            self._status(tr("Preferenze salvate"))

    def action_language(self) -> None:
        """Cambia la lingua dell'interfaccia.

        Le finestre che verranno aperte parlano subito la nuova lingua. Menu,
        pannelli e barra di stato già costruiti restano nella lingua di prima:
        Qt non ha un modo di ritradurre un albero di widget già creato, e
        ricostruirli tutti sul posto farebbe saltare le selezioni e i pannelli
        aperti. Si dice, perché una lingua che cambia a metà è la cosa più
        fastidiosa che possa capitare.
        """
        dlg = props.LanguageDialog(i18n.LINGUE, i18n.lingua(), self)
        if dlg.exec() != props.QDialog.Accepted:
            return
        scelta = dlg.language()
        if scelta == i18n.lingua():
            self._status(tr("Lingua invariata"))
            return
        self.settings.set("ui_language", scelta)
        i18n.set_lingua(scelta)
        from ..app import _install_translator

        _install_translator(QApplication.instance(), i18n.lingua())
        # menu e barre si rifanno davvero, e sono la parte che si vede di più:
        # la voce scelta deve comparire subito nel menu da cui si è arrivati
        self._rifac_menu_e_barre()
        # la chiave è il testo del sorgente, quindi italiano: un messaggio con
        # l'inglese come chiave resterebbe in inglese anche con l'interfaccia
        # italiana, e proprio nella lingua in cui si è sbagliato qualcosa
        self._status(
            tr("Lingua cambiata in «{lingua}». Le finestre già aperte e quelle "
               "che verranno aperte useranno la nuova lingua dal prossimo avvio.")
            .format(lingua=dict(i18n.LINGUE).get(i18n.lingua(), i18n.lingua()))
        )

    def _rifac_menu_e_barre(self) -> None:
        """Rifà menu e barre dopo un cambio di lingua.

        Non basta chiamare ``_build_menus`` di nuovo: quella aggiunge, e i menu
        di prima resterebbero a schermo con i nomi della lingua precedente. Qui
        sibutta la barra dei menu e si buttano via le barre, tenendo memoria di
        quali erano visibili, che altrimenti il cambio di lingua lascia la
        finestra con la barra del testo sparita.

        I pannelli laterali non si rifanno: sono widget con stato (contenuto
        delle liste, posizione, selezione) e ricostruirli azzererebbe tutto. Per
        quelli l'avviso dice che tornano nuovi al prossimo avvio.
        """
        visibili = {
            "annot": self.tb_annot.isVisible(),
            "testo": self.tb_text.isVisible(),
            "zoom": self.tb_zoom.isVisible(),
        }
        self.menuBar().clear()
        self._azioni_menu.clear()
        for barra in (self.tb_main, self.tb_annot, self.tb_text, self.tb_zoom):
            self.removeToolBar(barra)
            barra.deleteLater()
        self.main_acts = {}
        self.annot_acts = {}
        self.text_widgets = {}
        self.view_widgets = {}
        self.tb_main, self.main_acts = toolbars.build_main_toolbar(self, self.pal)
        self.tb_annot, self.annot_acts = toolbars.build_annot_toolbar(self, self.pal)
        self.tb_text, self.text_widgets = toolbars.build_text_toolbar(self, self.pal)
        self.tb_zoom, self.view_widgets = toolbars.build_zoom_toolbar(self, self.pal)
        for chiave, barra in (("annot", self.tb_annot), ("testo", self.tb_text), ("zoom", self.tb_zoom)):
            barra.setVisible(visibili[chiave])
        self._build_menus()
        self._update_actions()

    def _elenco_scorciatoie(self) -> str:
        """L'aiuto alle scorciatoie, ricavato dai menu.

        L'elenco una volta era scritto a mano e si era allontanato da quello
        che il programma accetta: annunciava «Ctrl+G» per la griglia, che era
        «Ctrl+'», e i tasti da una lettera per gli strumenti, che non sono mai
        stati registrati. Ricavandolo dai menu non può più mentire: se una voce
        non ha scorciatoia, non appare.
        """
        righe = []
        for azione in self.menuBar().actions():
            menu = azione.menu()
            if menu is None:
                continue
            voci = []
            for v in menu.actions():
                if not v.text() or v.isSeparator():
                    continue
                scorciatoia = v.shortcut().toString()
                voci.append(f"  {scorciatoia:22} {v.text()}" if scorciatoia else f"      {'':22} {v.text()}")
            if voci:
                righe.append(azione.text().replace("&", ""))
                righe.extend(voci)
                righe.append("")
        righe.append("Gesti e altri tasti")
        righe.append(f"  {'Spazio + trascina':22} Sposta la pagina")
        righe.append(f"  {'Alt + clic su campo':22} Seleziona e sposta un campo modulo")
        righe.append(f"  {'Invio nel campo':22} Risultato successivo / precedente")
        righe.append(f"  {'F1':22} Questa finestra")
        return "\n".join(righe)

    def action_shortcuts(self) -> None:
        QMessageBox.information(
            self, tr("Scorciatoie da tastiera"), self._elenco_scorciatoie()
        )

    def action_about(self) -> None:
        """Informazioni sul programma, con licenza e crediti.

        L'AGPL chiede che l'interfaccia mostri le avvertenze legali e come
        ottenere il testo della licenza: qui ci sono entrambe.
        """
        QMessageBox.about(
            self,
            f"Informazioni su {__app_name__}",
            f"<b>{__app_name__}</b> {__version__}<br>"
            f"Editor PDF per Linux e Windows<br><br>"
            # Nessuna riga di copyright: l'autore non ha registrato il nome e
            # non intende rivendicarlo. La licenza resta quella dichiarata qui
            # sotto e nel file LICENSE, che e' cio' che l'AGPL richiede.
            "Licenza GNU Affero General Public License, versione 3 o successiva<br>"
            "Nessuna garanzia: il programma è fornito «così com'è».<br><br>"
            '<a href="https://www.gnu.org/licenses/agpl-3.0.html">Testo della licenza</a>'
            f'<br><a href="{__repo_url__}">Codice sorgente</a><br><br>'
            "Motore PDF: PyMuPDF (AGPL-3.0) · Interfaccia: Qt 6 (LGPL-3.0)<br>"
            "Le licenze delle dipendenze sono nel file THIRD-PARTY.md<br><br>"
            "Nessun documento lascia il computer: il programma non usa la rete.",
        )

    def action_third_party(self) -> None:
        """Mostra le licenze delle dipendenze in una finestra.

        Il file THIRD-PARTY.md potrebbe non essere presente in un'installazione
        pacchettizzata, quindi si mostra comunque l'elenco dei nomi.
        """
        licenze = (
            "PyMuPDF — AGPL-3.0 (o licenza commerciale Artifex)\n"
            "PySide6 / Qt 6 — LGPL-3.0\n"
            "Pillow — MIT-CMU\n"
            "NumPy — BSD-3-Clause\n"
            "cryptography — Apache-2.0 o BSD-3-Clause\n"
            "asn1crypto — MIT\n"
            "scipy — BSD-3-Clause (facoltativa)\n"
        )
        file = Path(__file__).resolve().parents[2] / "THIRD-PARTY.md"
        dove = ""
        if file.exists():
            try:
                webbrowser.open(f"file://{file}")
                dove = f"\n\nElenco completo aperto nel browser: {file}"
            except Exception:
                pass
        QMessageBox.information(
            self,
            tr("Licenze di terze parti"),
            f"Le dipendenze di {__app_name__} usano queste licenze:\n\n"
            f"{licenze}{dove}"
            f"\n\n{__app_name__} è rilasciato sotto AGPL-3.0: la scelta di questa "
            "licenza è imposta da PyMuPDF.",
        )


    # ----------------------------------------------------- azioni strumento

    def _on_tool_action(self, tool: str, payload: Any) -> None:
        if not self.doc.is_open:
            return
        try:
            self._dispatch(tool, payload)
        except Exception as exc:
            self._error(exc)
            return
        self._on_doc_changed()
        self.panel_fields.load(self.doc)
        self.panel_comments.load(self.doc)

    def _dispatch(self, tool: str, payload: Any) -> None:
        # Gli strumenti a clic singolo (testo, firma, nota, timbro, collegamento,
        # campo di testo) mandano il punto premuto. Il resto del codice lavora con
        # riquadri: senza questa conversione ogni clic su quegli strumenti
        # finiva in un errore e non disegnava nulla.
        #
        # Il punto premuto e' nello spazio mostrato della pagina, mentre il
        # documento registra tutto nello spazio pagina: su una pagina ruotata i
        # due coincidono solo a rotazione zero.
        if tool in AREA_PUNTO and len(payload) == 2 and _come_punto(payload[1]):
            pagina, punto = payload
            larghezza, altezza = AREA_PUNTO[tool]
            x, y = float(punto.x()), float(punto.y())
            info = self.doc.page_info(pagina)
            mostrato = geo.clamp_rect(
                geo.Rect(x, y, x + larghezza, y + altezza), info.rect
            )
            payload = (pagina, geo.Rect(self.doc.to_page_rect(pagina, mostrato)))
        if tool in ("move", "resize"):
            page, xref, rect, kind = payload
            # `rect` e' gia' nello spazio pagina (arriva da
            # `selection_page_rect`). Prima veniva convertito in spazio
            # visualizzato e passato cosi' al motore: a rotazione 0 i due
            # spazi coincidono e non si vedeva, ma su una pagina ruotata
            # spostare o ridimensionare finiva fuori posto.
            try:
                if kind == "field":
                    self.doc.set_field_properties(page, xref, {"rect": geo.Rect(rect)})
                elif kind == "image":
                    # firma e immagini non sono annotazioni: si spostano
                    # rilettandole e reinserendole nella nuova posizione
                    self.doc.move_image(page, xref, geo.Rect(rect))
                else:
                    self.doc.set_annot_rect(page, xref, geo.Rect(rect))
            except Exception as exc:
                self._error(exc, "Spostamento non riuscito")
            return

        if tool == "text":
            page, rect = payload
            dlg = props.TextBoxDialog(self, self.text_style["fontname"], self.text_style["fontsize"])
            if dlg.exec() != props.QDialog.Accepted:
                return
            v = dlg.values()
            # La finestra raccoglie font, corpo, colore e allineamento, ma si
            # usava solo lo stile della barra degli strumenti: scegliere Times
            # a 18 pt in rosso centrava finiva con Helvetica 12 nero a sinistra.
            # Ora la finestra comanda, e la barra aggiorna lo stile corrente
            # così il testo successivo parte dalle stesse impostazioni.
            stile = dict(self.text_style)
            stile["fontname"] = v["fontname"]
            stile["fontsize"] = float(v["fontsize"])
            stile["color"] = v["color"]
            stile["align"] = int(v["align"])
            for k in ("bold", "italic", "underline"):
                if k in v:
                    stile[k] = bool(v[k])
            self.text_style = stile
            res = self.doc.insert_text_box(
                page, rect, v["text"],
                fontname=v["fontname"],
                fontsize=float(v["fontsize"]), color=v["color"], align=int(v["align"]),
                rotate=v["rotate"], lineheight=v["lineheight"], fill=v["fill"], border=v["border"],
                border_width=float(v["border_width"]), margin=float(v["margin"]),
                opacity=float(v["opacity"]), fit=v["fit"],
                underline=bool(v["underline"]),
            )
            if res["spare"] is not None and res["spare"] < 0:
                self._status(tr("Attenzione: il testo supera il riquadro"))
            else:
                self._status(tr("Casella di testo inserita"))
            return

        if tool == "freetext":
            # «Testo libero» e «Casella di testo» erano lo stesso strumento:
            # finivavano entrambe dentro il flusso di contenuto della pagina,
            # quindi la casella non si poteva piu' spostare, modificare o
            # cancellare e non compariva fra le annotazioni. Qui si crea
            # l'annotazione vera e propria, quella che il resto del programma
            # sa elencare, appiattire e mostrare fra i commenti.
            page, rect = payload
            dlg = props.TextBoxDialog(self, self.text_style["fontname"], self.text_style["fontsize"])
            if dlg.exec() != props.QDialog.Accepted:
                return
            v = dlg.values()
            # come per la casella di testo: il font, il corpo e il colore
            # scelti nella finestra devono valere, non quelli della barra
            stile = dict(self.text_style)
            stile["fontname"] = v["fontname"]
            stile["fontsize"] = float(v["fontsize"])
            stile["color"] = v["color"]
            stile["align"] = int(v["align"])
            for k in ("bold", "italic"):
                if k in v:
                    stile[k] = bool(v[k])
            self.text_style = stile
            try:
                self.doc.add_annot(
                    page, "freetext", geo.Rect(rect),
                    text=v["text"],
                    fontsize=float(v["fontsize"]),
                    text_color=v["color"],
                    align=int(v["align"]),
                    fill=v["fill"],
                    width=float(v["border_width"]),
                    opacity=float(v["opacity"]),
                    underline=bool(v["underline"]),
                )
            except Exception as exc:
                self._error(exc, "Inserimento non riuscito")
                return
            self._status(tr("Annotazione di testo inserita"))
            return

        if tool == "image":
            page, rect = payload
            path, _ = QFileDialog.getOpenFileName(self, "Scegli l'immagine", self._start_dir(), image_filter())
            if not path:
                return
            self.doc.insert_image(page, rect, path)
            self._status(tr("Immagine inserita"))
            return

        if tool == "signature":
            page, rect = payload
            self._open_signature_at(page, rect)
            return

        if tool in MARKER_TOOLS:
            page, data = payload
            # gli evidenziatori possono arrivare in due forme: come punti del
            # trascinamento (è ciò che manda la vista) oppure come riquadro,
            # com'è nelle chiamate programmatiche
            if isinstance(data, geo.Rect):
                rect = geo.Rect(data)
            else:
                punti = _pts(data)
                if not punti:
                    return
                rect = geo.Rect(
                    min(p[0] for p in punti), min(p[1] for p in punti),
                    max(p[0] for p in punti), max(p[1] for p in punti),
                )
            if rect.width < 2 and rect.height < 2:
                return  # un clic senza trascinamento non evidenzia nulla
            if tool == "underline" and rect.height > 3:
                rect = geo.Rect(rect.x0, rect.y1 - 2, rect.x1, rect.y1)
            elif tool != "highlight":
                rect = geo.Rect(rect.x0, max(rect.y0, rect.y1 - 1.5), rect.x1, rect.y1)
            else:
                rect = geo.Rect(rect.x0, rect.y0, rect.x1, max(rect.y0 + 2, rect.y1))
            self.doc.add_annot(page, self.marker_style["mode"], rect, color=self.marker_style["color"])
            self._status(tr("Evidenziazione applicata"))
            return

        if tool == "note":
            page, rect = payload
            from PySide6.QtWidgets import QInputDialog

            text, ok = QInputDialog.getMultiLineText(self, "Nota", "Testo della nota:")
            if not ok or not text.strip():
                return
            self.doc.add_annot(page, "note", geo.Rect(rect.x0, rect.y0, rect.x0 + 22, rect.y0 + 22), text=text)
            self._status(tr("Nota inserita"))
            return

        if tool == "link":
            page, rect = payload
            from PySide6.QtWidgets import QInputDialog

            uri, ok = QInputDialog.getText(self, "Collegamento", "Indirizzo (https://…):")
            if not ok or not uri.strip():
                return
            self.doc.add_annot(page, "link", rect, text=uri.strip())
            self._status(tr("Collegamento inserito"))
            return

        if tool == "redact":
            page, rect = payload
            if not self._confirm(tr("La redazione è permanente: il contenuto verrà rimosso dal file. Procedere?")):
                return
            self.doc.redact(page, [geo.Rect(rect)])
            self._status(tr("Contenuto redatto definitivamente"))
            return

        if tool in ("field_text", "field_check", "field_radio", "field_combo", "field_button"):
            page, rect = payload
            kind = FIELD_TOOLS[tool]
            dlg = props.NewFieldDialog(self, kind)
            if dlg.exec() != props.QDialog.Accepted:
                return
            v = dlg.values()
            if kind == "radio":
                self.doc.add_radio_group(
                    page,
                    [geo.Rect(rect.x0, rect.y0, rect.x0 + 18, rect.y0 + 18),
                     geo.Rect(rect.x0 + 26, rect.y0, rect.x0 + 44, rect.y0 + 18)],
                    v["name"], selected=-1, tooltip=v["tooltip"],
                )
            else:
                self.doc.add_field(
                    page, kind, rect,
                    v["name"], v["value"],
                    fontsize=v["fontsize"], font=v["font"],
                    options=v["options"], tooltip=v["tooltip"],
                    required=v["required"], read_only=v["read_only"],
                    multiline=v["multiline"], password=v["password"],
                    button_caption=v["button_caption"],
                )
            self._status(tr("Campo creato"))
            return

        # strumenti a forma
        page, data = payload
        st = self.annots_style
        if tool == "ink":
            self.doc.add_annot(page, "ink", geo.Rect(0, 0, 1, 1), vertices=_pts(data),
                               color=st["color"], width=st["width"], opacity=st["opacity"])
        elif tool == "polygon":
            self.doc.add_annot(page, "polygon", geo.Rect(0, 0, 1, 1), vertices=_pts(data),
                               color=st["color"], fill=st["fill"], width=st["width"], opacity=st["opacity"])
        elif tool in ("rect", "circle"):
            self.doc.add_annot(page, tool, geo.Rect(data), color=st["color"], fill=st["fill"],
                               width=st["width"], opacity=st["opacity"])
        elif tool in ("line", "arrow"):
            pts = _pts(data)
            self.doc.add_annot(page, tool, geo.Rect(0, 0, 1, 1), vertices=pts,
                               color=st["color"], width=st["width"], opacity=st["opacity"])
        elif tool == "stamp":
            self.doc.add_annot(page, "stamp", geo.Rect(data), color=st["color"], opacity=st["opacity"])
        else:
            raise docmod.DocumentError(f"Strumento non gestito: {tool}")

    def _open_signature_at(self, page: int, rect: geo.Rect) -> None:
        dlg = SignatureDialog(self.doc, page, self.library, self)
        if dlg.exec() != SignatureDialog.Accepted or dlg.result_image is None:
            return
        img = dlg.result_image
        if dlg.chk_flatten.isChecked():
            img = _flatten_on_white(img)
        else:
            img = _white_to_alpha(img)
        import io

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        info = self.doc.page_info(page)
        target = geo.clamp_rect(geo.Rect(rect), info.rect)
        try:
            self.doc.insert_image(page, target, buf.getvalue(), keep_proportion=False)
        except Exception as exc:
            self._error(exc, "Inserimento firma non riuscito")
            return
        self._status(tr("Firma inserita"))

    # ------------------------------------------------------------ allegati

    def _add_attachment(self) -> None:
        if not self.doc.is_open:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Allega file", self._start_dir(), "Tutti i file (*)")
        if not path:
            return
        try:
            self.doc.add_attachment(path)
        except Exception as exc:
            self._error(exc)
            return
        self.panel_attach.load(self.doc)
        self._status(tr("Allegato {file}").format(file=Path(path).name))

    def _save_attachment(self, name: str) -> None:
        try:
            data = self.doc.attachment_bytes(name)
        except Exception as exc:
            self._error(exc)
            return
        path, _ = QFileDialog.getSaveFileName(self, "Salva allegato", self._start_dir())
        if path:
            Path(path).write_bytes(data)
            self._status(tr("Allegato salvato in {file}").format(file=Path(path).name))

    def _remove_attachment(self, name: str) -> None:
        if not self._confirm(tr("Rimuovere l'allegato «{file}»?").format(file=name)):
            return
        self.doc.remove_attachment(name)
        self.panel_attach.load(self.doc)
        self._status(tr("Allegato rimosso"))

    def _open_attachment(self, name: str) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Salva allegato", str(Path(name).name))
        if not path:
            return
        try:
            Path(path).write_bytes(self.doc.attachment_bytes(name))
        except Exception as exc:
            self._error(exc)

    # ------------------------------------------------------------ segnalibri

    def _add_bookmark(self, page: int) -> None:
        from PySide6.QtWidgets import QInputDialog

        if not self.doc.is_open:
            return
        p = self.view.current_page() if page < 0 else page
        title, ok = QInputDialog.getText(self, tr("Nuovo segnalibro"), tr("Titolo:"))
        if ok and title.strip():
            self.doc.add_bookmark(title.strip(), p)
            self.panel_bookmarks.load(self.doc)
            self._status(tr("Segnalibro aggiunto"))

    def _remove_bookmark(self, indice: int) -> None:
        try:
            self.doc.remove_bookmark_at(indice)
        except Exception as exc:
            self._error(exc)
            return
        self.panel_bookmarks.load(self.doc)
        self._status(tr("Segnalibro rimosso"))

    def _rename_bookmark(self, indice: int, titolo: str) -> None:
        """Rinomina il segnalibro modificato direttamente nell'elenco."""
        if not self.doc.is_open:
            return
        try:
            self.doc.rename_bookmark_at(indice, titolo)
        except Exception as exc:
            self._error(exc)
            self.panel_bookmarks.load(self.doc)
            return
        self.panel_bookmarks.load(self.doc)
        self._status(tr("Segnalibro rinominato in «{titolo}»").format(titolo=titolo.strip()))

    def _move_bookmark(self, indice: int) -> None:
        """Porta il segnalibro sulla pagina mostrata nella vista."""
        if not self.doc.is_open:
            return
        pagina = self.view.current_page()
        try:
            self.doc.move_bookmark_at(indice, pagina)
        except Exception as exc:
            self._error(exc)
            return
        self.panel_bookmarks.load(self.doc)
        self._status(tr("Segnalibro spostato alla pagina {n}").format(n=pagina + 1))

    # ------------------------------------------------------------ miniature

    def _refresh_visible_thumbs(self) -> None:
        """Rasterizza solo le miniature visibili, con un margine di anticipo."""
        if not self.doc.is_open:
            return
        from .thumbnails import PageThumb

        lst = self.thumbs.list
        area = lst.viewport().rect()
        margin = 260
        for i in range(lst.count()):
            item = lst.item(i)
            if not isinstance(item, PageThumb):
                continue
            r = lst.visualItemRect(item)
            if r.bottom() < area.top() - margin:
                continue
            if r.top() > area.bottom() + margin:
                break
            item.pixmap()
        lst.viewport().update()

    # ------------------------------------------------------------ autosave

    def _start_autosave(self) -> None:
        if self.settings.get("autosave", True):
            self._autosave_timer.start(self._autosave_minutes * 60 * 1000)

    def _restart_autosave(self) -> None:
        self._autosave_timer.stop()
        self._autosave_minutes = int(self.settings.get("autosave_minutes", 10))
        self._start_autosave()

    def _autosave(self) -> None:
        if not self.doc.is_open or not self.doc.dirty or self._busy:
            return
        from ..core.settings import data_dir

        try:
            rec = data_dir() / "recupero"
            rec.mkdir(parents=True, exist_ok=True)
            name = (self.doc.path.name if self.doc.path else "senza_titolo.pdf").replace("/", "_")
            (rec / name).write_bytes(self.doc.save_bytes())
        except Exception:
            pass

    def _load_recovery(self) -> None:
        if not self.settings.get("recover", True):
            return
        from ..core.settings import data_dir

        rec = data_dir() / "recupero"
        if not rec.exists():
            return
        files = sorted(rec.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            return
        if QMessageBox.question(
            self,
            tr("Recupero documento"),
            f"È stato trovato un documento non salvato correttamente:\n{files[0].name}\n\nVuoi recuperarlo?",
        ) == QMessageBox.Yes:
            try:
                self.doc.open(files[0])
                self.doc.path = None
                self.doc.dirty = True
                self.view.set_document(self.doc)
                self._on_pages_changed()
                self._status(tr("Documento recuperato (salvalo per confermare)"))
            except Exception as exc:
                self._error(exc, "Recupero non riuscito")

    # ------------------------------------------------------------ chiusura

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        if not self._maybe_save():
            event.ignore()
            return
        self.settings.set("tool", self.tool)
        self.settings.set("grid_visible", self.view.grid_visible())
        self.settings.set("highlight_fields", self.view.highlight_fields)
        self.settings.set("snap_enabled", self.view.snap_enabled())
        self.settings.set("theme", "scuro" if self.pal is theme.DARK else "chiaro")
        self.settings.save()
        self.doc.close()
        event.accept()


def _pts(data) -> list[tuple[float, float]]:
    """Punti come coppie numeriche.

    Accetta sia coppie ``(x, y)`` sia punti ``QPointF`` o ``pymupdf.Point``,
    dove ``x``/``y`` sono attributi e non metodi.
    """
    out = []
    for p in data:
        if hasattr(p, "x") and hasattr(p, "y"):
            x, y = p.x, p.y
            out.append((float(x() if callable(x) else x), float(y() if callable(y) else y)))
        else:
            out.append((float(p[0]), float(p[1])))
    return out


def _flatten_on_white(img: Image.Image) -> Image.Image:
    base = Image.new("RGB", img.size, (255, 255, 255))
    base.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[3])
    return base


def _white_to_alpha(img: Image.Image) -> Image.Image:
    """Trasforma il bianco puro in trasparente, per firme su fondo bianco.

    Fatto con NumPy: il confronto pixel per pixel in Python costava un giro
    della scena su ogni immagine incollata, e numpy e' gia' una dipendenza del
    progetto. La soglia resta quella di prima (>250 su tutti i canali), perche'
    una firma con antialiasing ha sfumature che vanno tenute.
    """
    import numpy as np

    rgba = np.asarray(img.convert("RGBA")).astype(np.int16)
    bianco = (rgba[:, :, 0] > 250) & (rgba[:, :, 1] > 250) & (rgba[:, :, 2] > 250)
    rgba[:, :, 3] = np.where(bianco, 0, rgba[:, :, 3])
    return Image.fromarray(rgba.astype("uint8"), "RGBA")
