"""Finestra di creazione e inserimento della firma.

Riunisce le quattro sorgenti (disegno, tastiera, immagine, libreria) e la
rimozione dello sfondo, quindi inserisce la firma nella pagina scelta.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from PIL import Image
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QScrollArea,
    QCheckBox,
    QDoubleSpinBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...core import document as docmod
from ...core import geometry as geo
from ...signature import bgremove, manager, render as sigrender, typed
from ...signature import strokes as sk
from .. import icons, theme
from ...core.i18n import tr
from ..page_items import pil_to_qpixmap
from . import util as dlgutil
from .bgremove_panel import BackgroundRemovalPanel
from .pad import DrawPad

#: Come in `main_window`: funzione e non costante, perche' la parte leggibile
#: del filtro e' una frase da tradurre.
def image_filter() -> str:
    """Il filtro delle immagini per la firma."""
    return tr(
        "Immagini (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp *.gif);;"
        "PNG (*.png);;JPEG (*.jpg *.jpeg);;Tutti i file (*)"
    )


class SignatureDialog(QDialog):
    """Crea una firma e la inserisce nel documento."""

    def __init__(
        self,
        doc: docmod.Document,
        page: int,
        library: manager.SignatureLibrary,
        parent: QWidget | None = None,
        target_rect: geo.Rect | None = None,
    ) -> None:
        super().__init__(parent)
        self.doc = doc
        self.page = page
        self.library = library
        self.palette = theme.corrente()
        self.target_rect = target_rect
        self.result_image: Image.Image | None = None
        self.result_source = "draw"
        self.result_name = ""
        self.setWindowTitle(tr("Inserisci firma"))
        self.setModal(True)
        self._build()
        self._refresh_library()
        self._adatta_allo_schermo()

    def _adatta_allo_schermo(self) -> None:
        """Dimensioni entro lo schermo e contenuto scorrevole.

        Le opzioni di inserimento e i pulsanti stanno sotto le schede: se il
        dialogo chiede piu' altezza dello schermo, finiscono fuori vista e non
        si vede piu' niente. Il contenuto va quindi reso scorrevole e le
        dimensioni iniziali contenute.
        """
        dlgutil.adatta_a_schermo(self, 920, 660)

    # ------------------------------------------------------------------ UI

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._tab_draw(), icons.icon("pen", self.palette.text, 18), "Disegna")
        self.tabs.addTab(self._tab_type(), icons.icon("keyboard", self.palette.text, 18), "Tastiera")
        self.tabs.addTab(self._tab_image(), icons.icon("image", self.palette.text, 18), "Immagine")
        self.tabs.addTab(self._tab_library(), icons.icon("handwrite", self.palette.text, 18), "Libreria")
        # il riquadro di disegno e il pannello di rimozione dello sfondo
        # chiedono molta altezza: senza area scorrevole le opzioni sotto
        # finivano fuori dalla finestra
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QScrollArea.NoFrame)
        self.area.setWidget(self.tabs)
        root.addWidget(self.area, 1)

        # --- pannello di inserimento ---
        place = QGroupBox(tr("Inserimento nel documento"))
        g = QGrid = QFormLayout(place)
        self.cb_page = QComboBox()
        for i in range(self.doc.page_count):
            self.cb_page.addItem(f"Pagina {i + 1}", i)
        self.cb_page.setCurrentIndex(min(self.page, self.doc.page_count - 1))
        g.addRow(tr("Pagina"), self.cb_page)
        self.spin_w = QDoubleSpinBox()
        self.spin_h = QDoubleSpinBox()
        self.spin_w.setRange(5, 2000)
        self.spin_h.setRange(5, 2000)
        self.spin_w.setDecimals(1)
        self.spin_h.setDecimals(1)
        self.spin_w.setValue(180)
        self.spin_h.setValue(70)
        self.spin_w.setSuffix(' pt')
        self.spin_h.setSuffix(' pt')
        row = QHBoxLayout()
        row.addWidget(self.spin_w)
        row.addWidget(QLabel(tr("×")))
        row.addWidget(self.spin_h)
        row.addWidget(QLabel(tr("pt")))
        wbox = QWidget()
        wbox.setLayout(row)
        g.addRow(tr("Dimensione"), wbox)
        self.spin_opacity = QSlider(Qt.Horizontal)
        self.spin_opacity.setRange(10, 100)
        self.spin_opacity.setValue(100)
        g.addRow(tr("Opacità"), self.spin_opacity)
        checks = QHBoxLayout()
        self.chk_flatten = QCheckBox(tr("Appiattisci su bianco"))
        self.chk_flatten.setToolTip(tr("Incide la firma nel contenuto della pagina"))
        checks.addWidget(self.chk_flatten)
        checks.addStretch(1)
        cbox = QWidget()
        cbox.setLayout(checks)
        g.addRow("", cbox)
        root.addWidget(place)

        # --- campi firma esistenti ---
        # Una sola scelta, non una casella di spunta piu' una tendina: la
        # casella diceva solo "in un campo firma" senza dire quale, e la
        # tendina restava scollegata, quindi il valore non arrivava mai al
        # motore. Ora la scelta e' il campo firma, e arriva.
        self.sig_fields = self.doc.fields(self.page) if self.doc.has_signature_fields else []
        self.cmb_signature_field = QComboBox()
        self.cmb_signature_field.addItem(tr("Nessuno (posizione libera)"), None)
        for f in self.sig_fields:
            self.cmb_signature_field.addItem(f.name, f)
        self.cmb_signature_field.setToolTip(
            tr("Inserisce la firma dentro il riquadro del campo firma scelto, e ne compila il valore")
        )
        g.addRow(tr("Campo firma"), self.cmb_signature_field)

        self.status = QLabel("")
        self.status.setProperty("role", "hint")
        root.addWidget(self.status)

        buttons = QDialogButtonBox()
        b_save = buttons.addButton("Salva in libreria", QDialogButtonBox.ActionRole)
        b_save.clicked.connect(self._save_to_library)
        b_clear = buttons.addButton("Cancella", QDialogButtonBox.ResetRole)
        b_clear.clicked.connect(self._clear_current)
        buttons.addButton(QDialogButtonBox.Cancel)
        ok = buttons.addButton("Inserisci", QDialogButtonBox.AcceptRole)
        ok.setProperty("accent", True)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    # ------------------------------------------------------------ tab disegno

    def _tab_draw(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self.pad = DrawPad()
        self.pad.changed.connect(self._on_pad_changed)
        v.addWidget(self.pad, 1)
        row = QHBoxLayout()
        b_undo = QPushButton(tr("Annulla tratto"))
        b_undo.clicked.connect(self.pad.undo)
        b_clear = QPushButton(tr("Cancella tutto"))
        b_clear.clicked.connect(self.pad.clear)
        row.addWidget(b_undo)
        row.addWidget(b_clear)
        row.addStretch(1)
        self.pen_color_btn = QPushButton(tr("Colore penna"))
        self.pen_color_btn.clicked.connect(self._pick_pen)
        row.addWidget(QLabel(tr("Penna")))
        row.addWidget(self.pen_color_btn)
        self.spin_pen = QSpinBox()
        self.spin_pen.setRange(1, 30)
        self.spin_pen.setValue(3)
        self.spin_pen.setSuffix(" px")
        self.spin_pen.valueChanged.connect(self._apply_pen)
        row.addWidget(self.spin_pen)
        v.addLayout(row)
        self._apply_pen()
        return w

    def _pick_pen(self) -> None:
        from PySide6.QtWidgets import QColorDialog

        c = QColorDialog.getColor(self.pad.pen_color, self, "Colore della penna")
        if c.isValid():
            self.pad.pen_color = c
            self._apply_pen()

    def _apply_pen(self) -> None:
        self.pad.set_pen(self.pad.pen_color.name(), float(self.spin_pen.value()))
        self._on_pad_changed()

    def _on_pad_changed(self) -> None:
        if self.tabs.currentIndex() == 0 and not self.pad.is_empty():
            self.result_image = None
            self.status.setText(tr("Firma disegnata pronta per l'inserimento."))

    def _clear_current(self) -> None:
        idx = self.tabs.currentIndex()
        if idx == 0:
            self.pad.clear()
        elif idx == 1:
            self.type_text.clear()
        elif idx == 2:
            self.img_result = None
            self.img_preview.clear()
            self.bg_panel.set_image(Image.new("RGBA", (1, 1)))
        self.status.setText("")

    # ----------------------------------------------------------- tab tastiera

    def _tab_type(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        form = QFormLayout()
        self.type_text = QLineEdit()
        self.type_text.setPlaceholderText(tr("Scrivi il tuo nome"))
        self.type_text.textChanged.connect(self._render_typed)
        form.addRow(tr("Nome"), self.type_text)
        self.font_box = QComboBox()
        # i font senza le lettere latine restano in fondo, ma si vedono dal
        # nome: scegliendone uno il testo uscirebbe fatto di quadratini
        for f in typed.list_fonts():
            etichetta = f"{f['name']}"
            if f["script"] and f["latino"]:
                etichetta += "  ✎"
            elif not f["latino"]:
                etichetta += "  (senza lettere)"
            self.font_box.addItem(etichetta, f["path"])
        if self.font_box.count() == 0:
            self.font_box.addItem(tr("(nessun font trovato)"), "")
        else:
            # si parte dal font che meglio somiglia a una firma e sa scrivere
            predefinito = typed.pick_default_font()
            for i in range(self.font_box.count()):
                if self.font_box.itemData(i) == predefinito:
                    self.font_box.setCurrentIndex(i)
                    break
        self.font_box.currentIndexChanged.connect(self._render_typed)
        form.addRow(tr("Font"), self.font_box)
        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setRange(24, 200)
        self.size_slider.setValue(96)
        self.size_slider.valueChanged.connect(self._render_typed)
        form.addRow(tr("Corpo"), self.size_slider)
        v.addLayout(form)

        grp = QGroupBox(tr("Stile manoscritto"))
        f2 = QFormLayout(grp)
        self.slant_slider = LabeledSlider(0, 60, 22)
        self.wobble_slider = LabeledSlider(0, 80, 30)
        self.rotate_slider = LabeledSlider(0, 120, 32)
        self.variation_slider = LabeledSlider(0, 60, 6)
        self.spacing_slider = LabeledSlider(-40, 40, -2)
        f2.addRow(tr("Inclinazione"), self.slant_slider)
        f2.addRow(tr("Oscillazione base"), self.wobble_slider)
        f2.addRow(tr("Rotazione caratteri"), self.rotate_slider)
        f2.addRow(tr("Variazione dimensioni"), self.variation_slider)
        f2.addRow(tr("Spaziatura"), self.spacing_slider)
        v.addWidget(grp)

        self.type_preview = QLabel()
        self.type_preview.setAlignment(Qt.AlignCenter)
        self.type_preview.setMinimumHeight(120)
        self.type_preview.setStyleSheet(
            f"background: {self.palette.surface_alt}; border: 1px solid {self.palette.border};"
            "border-radius: 6px;"
        )
        v.addWidget(self.type_preview, 1)
        return w

    def _typed_style(self) -> typed.TypedStyle:
        return typed.TypedStyle(
            font_path=str(self.font_box.currentData() or ""),
            size=float(self.size_slider.value()),
            color=(self.pad.pen_color.red(), self.pad.pen_color.green(), self.pad.pen_color.blue()),
            slant=self.slant_slider.value() / 100.0,
            wobble=self.wobble_slider.value() / 100.0,
            rotate=self.rotate_slider.value() / 10.0,
            size_variation=self.variation_slider.value() / 100.0,
            spacing=self.spacing_slider.value() / 100.0,
        )

    def _render_typed(self) -> None:
        text = self.type_text.text().strip()
        if not text:
            self.type_preview.clear()
            self.type_preview.setText(tr("L'anteprima della firma compare qui"))
            return
        try:
            img = typed.render_typed(text, self._typed_style())
        except Exception:
            return
        self._typed_image = img
        self.type_preview.setPixmap(pil_to_qpixmap(img))
        self.result_image = None
        self.status.setText(tr("Firma digitata pronta per l'inserimento."))

    # ----------------------------------------------------------- tab immagine

    def _tab_image(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        row = QHBoxLayout()
        b_open = QPushButton(tr("Apri immagine…"))
        b_open.clicked.connect(self._load_image)
        b_paste = QPushButton(tr("Incolla dagli appunti"))
        b_paste.clicked.connect(self._paste_image)
        row.addWidget(b_open)
        row.addWidget(b_paste)
        row.addStretch(1)
        v.addLayout(row)
        self.bg_panel = BackgroundRemovalPanel()
        self.bg_panel.accepted.connect(self._on_bg_accepted)
        v.addWidget(self.bg_panel, 1)
        return w

    def _on_bg_accepted(self, st) -> None:
        """Rimozione dello sfondo confermata: l'immagine è già ricalcolata."""
        self.status.setText(tr("Rimozione sfondo applicata all'anteprima."))

    def _load_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Scegli l'immagine della firma", "", image_filter())
        if not path:
            return
        try:
            img = Image.open(path)
            img.load()
        except Exception as exc:
            QMessageBox.warning(self, tr("Immagine"), f"Impossibile aprire il file:\n{exc}")
            return
        self._source_image = img.convert("RGBA")
        self._source_path = path
        self.bg_panel.set_image(self._source_image)
        self.status.setText(tr("Immagine caricata: {file}").format(file=Path(path).name))

    def _paste_image(self) -> None:
        from PySide6.QtGui import QGuiApplication

        mime = QGuiApplication.clipboard().mimeData()
        if not mime.hasImage():
            QMessageBox.information(self, tr("Appunti"), tr("Non c'è nessuna immagine negli appunti."))
            return
        img = QImage(mime.imageData().toImage() if hasattr(mime.imageData(), "toImage") else mime.imageData())
        if img.isNull():
            QMessageBox.information(self, tr("Appunti"), tr("Immagine non valida."))
            return
        img = img.convertToFormat(QImage.Format_RGBA8888)
        w, h = img.width(), img.height()
        ptr = img.constBits()
        arr = ptr.asstring(w * h * 4)
        pil = Image.frombytes("RGBA", (w, h), arr)
        self._source_image = pil
        self._source_path = ""
        self.bg_panel.set_image(pil)
        self.status.setText(tr("Immagine incollata dagli appunti."))

    def signature_field(self):
        """Il campo firma in cui inserire la firma, o ``None`` se libera.

        Il dato che torna dalla tendina e' l'oggetto ``FieldInfo`` stesso, non
        il suo indice: la finestra ne ha bisogno per il riquadro dentro cui
        mettere la firma.
        """
        return self.cmb_signature_field.currentData()

    def current_image(self) -> Image.Image | None:
        """Firma pronta, secondo la scheda attiva."""
        idx = self.tabs.currentIndex()
        if idx == 0:
            if self.pad.is_empty():
                return None
            return sigrender.render_strokes(self.pad.canvas, scale=2.0)
        if idx == 1:
            return getattr(self, "_typed_image", None)
        if idx == 2:
            return self.bg_panel.result
        return None

    # ---------------------------------------------------------- tab libreria

    def _tab_library(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self.lib_list = QListWidget()
        self.lib_list.setIconSize(QSize(120, 60))
        self.lib_list.itemSelectionChanged.connect(self._on_lib_selected)
        v.addWidget(self.lib_list, 1)
        row = QHBoxLayout()
        b_use = QPushButton(tr("Usa selezionata"))
        b_use.clicked.connect(self._use_library)
        b_ren = QPushButton(tr("Rinomina"))
        b_ren.clicked.connect(self._rename_library)
        b_del = QPushButton(tr("Elimina"))
        b_del.clicked.connect(self._delete_library)
        for b in (b_use, b_ren, b_del):
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        return w

    def _refresh_library(self) -> None:
        self.lib_list.clear()
        for e in self.library.entries:
            img = self.library.image(e)
            item = QListWidgetItem(e.display_name)
            item.setData(Qt.UserRole, e.id)
            if img is not None:
                pm = pil_to_qpixmap(img)
                item.setIcon(QIcon(pm.scaled(120, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
            self.lib_list.addItem(item)
        if self.library.entries:
            self.lib_list.setCurrentRow(0)
        else:
            # una libreria vuota e' comunque una schermata utile: da qui si
            # salva la prima firma, quindi si dice come, invece di lasciare
            # una lista muta che sembra rotta
            self.status.setText(
                tr("La libreria è vuota: crea la firma su un'altra scheda e premi «Salva in libreria».")
            )

    def _on_lib_selected(self) -> None:
        entry = self._lib_entry()
        if entry is None:
            return
        img = self.library.image(entry)
        if img is not None:
            self.result_image = img
            self.result_name = entry.display_name
            self.status.setText(
                tr("Firma dalla libreria: {nome}").format(nome=entry.display_name)
            )

    def _lib_entry(self):
        it = self.lib_list.currentItem()
        if it is None:
            return None
        return self.library.by_id(str(it.data(Qt.UserRole)))

    def _use_library(self) -> None:
        entry = self._lib_entry()
        if entry is None:
            return
        self.result_image = self.library.image(entry)
        self.result_name = entry.display_name
        self.status.setText(tr("Firma selezionata: {nome}").format(nome=entry.display_name))

    def _rename_library(self) -> None:
        entry = self._lib_entry()
        if entry is None:
            return
        from PySide6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(self, "Rinomina firma", "Nome:", text=entry.display_name)
        if ok and name.strip():
            self.library.rename(entry, name.strip())
            self._refresh_library()

    def _delete_library(self) -> None:
        entry = self._lib_entry()
        if entry is None:
            return
        if QMessageBox.question(self, tr("Elimina"), f"Eliminare la firma «{entry.display_name}»?") == QMessageBox.Yes:
            self.library.remove(entry)
            self._refresh_library()

    # ------------------------------------------------------------- inserimento

    def _save_to_library(self) -> None:
        img = self.current_image()
        if img is None:
            QMessageBox.information(self, tr("Libreria"), tr("Prima crea una firma (disegna, scrivi o carica un'immagine)."))
            return
        idx = self.tabs.currentIndex()
        if idx == 0:
            self.library.add_canvas(self.pad.canvas, name=self.result_name or "")
        elif idx == 1:
            self.library.add_typed(self.type_text.text().strip(), self._typed_style())
        else:
            self.library.add_png(img, name=self.result_name or "", source="image")
        self._refresh_library()
        self.status.setText(tr("Firma salvata nella libreria."))

    def signature_size(self, img: Image.Image) -> tuple[float, float]:
        """Dimensione di inserimento calcolata sul rapporto dell'immagine."""
        w, h = self.spin_w.value(), self.spin_h.value()
        if w <= 0 or h <= 0:
            w, h = 180.0, 70.0
            if img.height:
                ratio = img.width / img.height
                w = 180.0
                h = w / max(ratio, 0.05)
        return float(w), float(h)

    def _accept(self) -> None:
        idx = self.tabs.currentIndex()
        img = self.current_image()
        if img is None and idx == 3:
            img = self.result_image
        if img is None:
            QMessageBox.information(
                self, tr("Firma"), tr("Crea una firma: disegnala, scrivila, carica un'immagine o sceglila dalla libreria.")
            )
            return
        self.result_image = img
        self.accept()


class LabeledSlider(QWidget):
    """Cursore con etichetta del valore corrente."""

    valueChanged = Signal(int)

    def __init__(self, lo: int, hi: int, value: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(lo, hi)
        self.slider.setValue(value)
        self.label = QLabel(f"{value}")
        self.label.setMinimumWidth(36)
        self.label.setProperty("role", "hint")
        self.slider.valueChanged.connect(self._on_change)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.label)

    def _on_change(self, v: int) -> None:
        self.label.setText(f"{v}")
        self.valueChanged.emit(v)

    def value(self) -> int:
        return int(self.slider.value())

    def setValue(self, v: int) -> None:  # noqa: N802
        self.slider.setValue(int(v))
