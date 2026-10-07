"""Finestre di dialogo per proprietà, sicurezza, esportazione e certificati."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any, Sequence

import pymupdf
from PySide6.QtCore import QDate, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSlider,
    QRadioButton,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from . import util as dlgutil
from ...core import document as docmod
from ...core import i18n, textlayout, units
from ...core.i18n import tr
from .. import icons, theme


def _nome_lingua(codice: str, nome: str) -> str:
    """Il nome di una lingua nell'elenco, con quello del sistema in chiaro.

    «auto» mostra «Sistema» e il seguito dice quale: una voce che dice solo
    «Sistema» non dice niente quando il menu è aperto, e la lingua che verrà
    usata è proprio la cosa che l'utente sta per scegliere.
    """
    # I nomi delle lingue restano nella propria lingua, com'e' uso: chi cerca
    # «English» la trova anche con l'interfaccia italiana. «Sistema» invece è
    # un'etichetta, e quella si traduce.
    if codice != "auto":
        return nome
    in_corso = i18n.lingua_di_sistema()
    return f"{tr(nome)} ({dict(i18n.LINGUE).get(in_corso, in_corso.upper())})"


def _color_btn(color: str, title: str = "Scegli il colore") -> tuple[QPushButton, dict[str, QColor]]:
    """Pulsante che apre un selettore colore, con valore conservato."""
    state = {"color": QColor(color)}
    b = QPushButton(color)
    b.setFixedWidth(84)

    def pick() -> None:
        c = QColorDialog.getColor(state["color"], b, title)
        if c.isValid():
            state["color"] = c
            b.setText(c.name())
            b.setStyleSheet(f"background: {c.name()}; color: {_contrast(c)};")

    b.clicked.connect(pick)
    b.setStyleSheet(f"background: {color}; color: {_contrast(QColor(color))};")
    return b, state


def _contrast(c: QColor) -> str:
    lum = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
    return "#000000" if lum > 150 else "#ffffff"


def rgb(c: QColor) -> tuple[float, float, float]:
    return (c.red() / 255.0, c.green() / 255.0, c.blue() / 255.0)


def pt_color(c: QColor) -> tuple[float, float, float]:
    """Colore Qt in componenti 0-1 per PyMuPDF."""
    return rgb(c)


# --------------------------------------------------------------- testo


class TextBoxDialog(QDialog):
    """Inserimento di una casella di testo con tutte le proprietà."""

    def __init__(self, parent: QWidget | None = None, fontname: str = "helv", size: float = 12.0) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Casella di testo"))
        dlgutil.adatta_a_schermo(self, 560, 620)
        self.palette = theme.corrente()
        v = QVBoxLayout(self)

        v.addWidget(QLabel(tr("Contenuto")))
        self.text = QPlainTextEdit()
        self.text.setPlainText("")
        self.text.setMinimumHeight(120)
        self.text.textChanged.connect(self._update_info)
        v.addWidget(self.text)

        g = QGroupBox(tr("Carattere"))
        f = QFormLayout(g)
        self.font_box = QComboBox()
        # la coppia era al contrario: la lista mostrava il codice interno
        # («helv», «tibo») e conservava come dato il nome esteso, cosi'
        # ``font_name`` non trovava mai le sue chiavi e le caselle Grassetto
        # e Corsivo restavano mute
        for nome, chiave in textlayout.BASE_FONTS.items():
            self.font_box.addItem(nome, chiave)
        idx = self.font_box.findData(textlayout.BASE_FONTS.get(fontname, fontname))
        self.font_box.setCurrentIndex(idx if idx >= 0 else 0)
        self.font_box.currentIndexChanged.connect(self._update_info)
        f.addRow(tr("Font"), self.font_box)
        self.size_box = QSpinBox()
        self.size_box.setRange(4, 200)
        self.size_box.setValue(int(size))
        self.size_box.valueChanged.connect(self._update_info)
        f.addRow(tr("Corpo (pt)"), self.size_box)
        row = QHBoxLayout()
        self.bold = QCheckBox(tr("Grassetto"))
        self.italic = QCheckBox(tr("Corsivo"))
        self.underline = QCheckBox(tr("Sottolineato"))
        for c in (self.bold, self.italic, self.underline):
            c.toggled.connect(self._update_info)
            row.addWidget(c)
        row.addStretch(1)
        rb = QWidget()
        rb.setLayout(row)
        f.addRow(tr("Stile"), rb)
        self.color_btn, self.color = _color_btn("#1b1f27", "Colore del testo")
        f.addRow(tr("Colore"), self.color_btn)
        self.align = QComboBox()
        for label, val in (("Sinistra", 0), ("Centrato", 1), ("Destra", 2), ("Giustificato", 3)):
            self.align.addItem(label, val)
        f.addRow(tr("Allineamento"), self.align)
        self.lineheight = QSpinBox()
        self.lineheight.setRange(80, 300)
        self.lineheight.setValue(120)
        self.lineheight.setSuffix(" %")
        f.addRow(tr("Interlinea"), self.lineheight)
        self.rotate = QComboBox()
        for val in (0, 90, 180, 270):
            self.rotate.addItem(f"{val}°", val)
        f.addRow(tr("Rotazione"), self.rotate)
        v.addWidget(g)

        g2 = QGroupBox(tr("Riquadro"))
        f2 = QFormLayout(g2)
        self.fill_chk = QCheckBox(tr("Colore di riempimento"))
        self.border_chk = QCheckBox(tr("Bordo"))
        f2.addRow("", self.fill_chk)
        self.fill_btn, self.fill = _color_btn("#ffffff", "Colore di riempimento")
        f2.addRow(tr("Riempimento"), self.fill_btn)
        f2.addRow("", self.border_chk)
        self.border_btn, self.border = _color_btn("#2f6fdb", "Colore del bordo")
        f2.addRow(tr("Bordo"), self.border_btn)
        self.border_w = QSpinBox()
        self.border_w.setRange(0, 20)
        self.border_w.setValue(1)
        self.border_w.setSuffix(" pt")
        f2.addRow(tr("Spessore bordo"), self.border_w)
        self.margin = QSpinBox()
        self.margin.setRange(0, 60)
        self.margin.setValue(3)
        self.margin.setSuffix(" pt")
        f2.addRow(tr("Margine interno"), self.margin)
        self.opacity = QSpinBox()
        self.opacity.setRange(10, 100)
        self.opacity.setValue(100)
        self.opacity.setSuffix(" %")
        f2.addRow(tr("Opacità"), self.opacity)
        self.fit = QComboBox()
        self.fit.addItem(tr(" Nessun adattamento"), "none")
        self.fit.addItem(tr(" Riduci il testo per farlo entrare"), "shrink")
        self.fit.addItem(tr(" Ingrandisci il riquadro"), "grow")
        f2.addRow(tr("Testo troppo grande"), self.fit)
        v.addWidget(g2)

        self.info = QLabel("")
        self.info.setProperty("role", "hint")
        v.addWidget(self.info)
        self._update_info()

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("Inserisci"))
        bb.button(QDialogButtonBox.Ok).setProperty("accent", True)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        dlgutil.adatta_a_schermo(self, 560, 680)

    def _update_info(self) -> None:
        text = self.text.toPlainText()
        if not text.strip():
            self.info.setText(tr("Inserisci il testo da aggiungere."))
            return
        name = str(self.font_box.currentData())
        size = float(self.size_box.value())
        need_w, need_h = textlayout.required_size(text, name, size, 400.0)
        lines = textlayout.wrap(text, name, size, 400.0)
        self.info.setText(
            tr("{n} righe — serve almeno {larghezza}×{altezza} pt a questa dimensione.")
                .format(n=len(lines), larghezza=f"{need_w:.0f}", altezza=f"{need_h:.0f}")
        )

    def font_name(self) -> str:
        base = str(self.font_box.currentData())
        if self.bold.isChecked() and self.italic.isChecked():
            return {"helv": "hebi", "tiro": "tibo", "cour": "cobi"}.get(base, base)
        if self.bold.isChecked():
            return {"helv": "hebo", "tiro": "tibo", "cour": "cobo"}.get(base, base)
        if self.italic.isChecked():
            return {"helv": "hebi", "tiro": "tiit", "cour": "cobi"}.get(base, base)
        return base

    def values(self) -> dict[str, Any]:
        return {
            "text": self.text.toPlainText(),
            "fontname": self.font_name(),
            "fontsize": float(self.size_box.value()),
            "color": rgb(self.color["color"]),
            "align": int(self.align.currentData()),
            "rotate": int(self.rotate.currentData()),
            "lineheight": float(self.lineheight.value()) / 100.0,
            "fill": rgb(self.fill["color"]) if self.fill_chk.isChecked() else None,
            "border": rgb(self.border["color"]) if self.border_chk.isChecked() else None,
            "border_width": float(self.border_w.value()),
            "margin": float(self.margin.value()),
            "opacity": float(self.opacity.value()) / 100.0,
            "fit": str(self.fit.currentData()),
            "bold": self.bold.isChecked(),
            "italic": self.italic.isChecked(),
            "underline": self.underline.isChecked(),
        }


# --------------------------------------------------------------- annotazioni


class AnnotationStyleDialog(QDialog):
    """Stile delle annotazioni disegnate (forma, penna, testo)."""

    @staticmethod
    def shapes() -> tuple[tuple[str, str, str], ...]:
        """Le forme disegnabili, con l'etichetta tradotta."""
        return (
            ("rect", tr("Rettangolo"), "rect"),
            ("circle", tr("Ellisse"), "circle"),
            ("line", tr("Linea"), "line"),
            ("arrow", tr("Freccia"), "arrow"),
            ("ink", tr("Inchiostro libero"), "ink"),
            ("polygon", tr("Poligono"), "polygon"),
            ("note", tr("Nota"), "note"),
            ("stamp", tr("Timbro"), "stamp"),
        )

    def __init__(self, shape: str = "rect", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Stile annotazione"))
        self.palette = theme.corrente()
        v = QVBoxLayout(self)
        f = QFormLayout()
        self.shape = QComboBox()
        for key, label, ico in self.shapes():
            self.shape.addItem(icons.icon(ico, self.palette.text, 18), label, key)
        i = self.shape.findData(shape)
        self.shape.setCurrentIndex(i if i >= 0 else 0)
        f.addRow(tr("Forma"), self.shape)
        self.color_btn, self.color = _color_btn("#c8362f", "Colore della penna")
        f.addRow(tr("Colore"), self.color_btn)
        self.fill_chk = QCheckBox(tr("Riempimento"))
        f.addRow("", self.fill_chk)
        self.fill_btn, self.fill = _color_btn("#ffd54f", "Colore di riempimento")
        f.addRow(tr("Riempimento"), self.fill_btn)
        self.width_box = QSpinBox()
        self.width_box.setRange(1, 40)
        self.width_box.setValue(2)
        self.width_box.setSuffix(" pt")
        f.addRow(tr("Spessore"), self.width_box)
        self.opacity = QSpinBox()
        self.opacity.setRange(5, 100)
        self.opacity.setValue(100)
        self.opacity.setSuffix(" %")
        f.addRow(tr("Opacità"), self.opacity)
        self.dash = QCheckBox(tr("Tratteggio"))
        f.addRow("", self.dash)
        self.note_text = QTextEdit()
        self.note_text.setMaximumHeight(70)
        f.addRow(tr("Testo nota"), self.note_text)
        v.addLayout(f)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("Applica"))
        bb.button(QDialogButtonBox.Ok).setProperty("accent", True)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def values(self) -> dict[str, Any]:
        return {
            "shape": str(self.shape.currentData()),
            "color": rgb(self.color["color"]),
            "fill": rgb(self.fill["color"]) if self.fill_chk.isChecked() else None,
            "width": float(self.width_box.value()),
            "opacity": float(self.opacity.value()) / 100.0,
            "dash": self.dash.isChecked(),
            "text": self.note_text.toPlainText(),
        }


class MarkerStyleDialog(QDialog):
    """Stile per evidenzianza, sottolineatura, barratura e onda."""

    PRESETS = {
        "giallo": "#ffe066",
        "verde": "#8ce99a",
        "azzurro": "#74c0fc",
        "rosa": "#faa2c1",
        "arancione": "#ffc078",
    }

    def __init__(self, mode: str = "highlight", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Stile evidenziazione"))
        self.palette = theme.corrente()
        v = QVBoxLayout(self)
        self.mode = QComboBox()
        for key, label in (("highlight", "Evidenziazione"), ("underline", "Sottolineatura"),
                           ("strikeout", "Barratura"), ("squiggly", "Ondata")):
            self.mode.addItem(label, key)
        i = self.mode.findData(mode)
        self.mode.setCurrentIndex(i if i >= 0 else 0)
        v.addWidget(QLabel(tr("Tipo")))
        v.addWidget(self.mode)
        grid = QGridLayout()
        for n, (name, col) in enumerate(self.PRESETS.items()):
            b = QPushButton()
            b.setFixedSize(52, 30)
            b.setStyleSheet(f"background: {col}; border: 1px solid {theme.LIGHT.border_strong};")
            b.clicked.connect(lambda _c=False, c=col: self._set(c))
            grid.addWidget(b, n // 5, n % 5)
        v.addLayout(grid)
        self.color_btn, self.color = _color_btn(self.PRESETS["giallo"], "Colore")
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Colore")))
        row.addWidget(self.color_btn)
        row.addStretch(1)
        v.addLayout(row)
        self.opacity = QSpinBox()
        self.opacity.setRange(10, 100)
        self.opacity.setValue(100)
        self.opacity.setSuffix(" %")
        row2 = QHBoxLayout()
        row2.addWidget(QLabel(tr("Opacità")))
        row2.addWidget(self.opacity)
        row2.addStretch(1)
        v.addLayout(row2)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("Applica"))
        bb.button(QDialogButtonBox.Ok).setProperty("accent", True)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _set(self, c: str) -> None:
        self.color["color"] = QColor(c)
        self.color_btn.setText(c)
        self.color_btn.setStyleSheet(f"background: {c};")

    def values(self) -> dict[str, Any]:
        return {
            "mode": str(self.mode.currentData()),
            "color": rgb(self.color["color"]),
            "opacity": float(self.opacity.value()) / 100.0,
        }


# --------------------------------------------------------------- campo modulo


class FieldPropertiesDialog(QDialog):
    """Proprietà di un campo modulo esistente."""

    @staticmethod
    def kinds() -> dict[str, str]:
        """Il nome leggibile di ogni tipo di campo, tradotto."""
        return {
            "Text": tr("Campo di testo"),
            "CheckBox": tr("Casella di spunta"),
            "RadioButton": tr("Pulsante di opzione"),
            "ComboBox": tr("Menu a tendina"),
            "ListBox": tr("Elenco"),
            "Button": tr("Pulsante"),
            "Signature": tr("Campo firma"),
        }

    def __init__(self, info: docmod.FieldInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.info = info
        self.palette = theme.corrente()
        self.setWindowTitle(tr("Proprietà campo — {campo}").format(campo=info.label))
        dlgutil.adatta_a_schermo(self, 480, 520)
        v = QVBoxLayout(self)
        f = QFormLayout()
        self.type_lbl = QLabel(self.kinds().get(info.type, info.type))
        f.addRow(tr("Tipo"), self.type_lbl)
        self.name = QLineEdit(info.name)
        f.addRow(tr("Nome"), self.name)
        self.tooltip = QLineEdit(info.tooltip)
        self.tooltip.setPlaceholderText(tr("Testo mostrato passando col mouse"))
        f.addRow(tr("Descrizione"), self.tooltip)
        self.value = QLineEdit("" if info.value in (None, False) else str(info.value))
        f.addRow(tr("Valore"), self.value)
        self.font_box = QComboBox()
        for label, da_nome in textlayout.FIELD_FONTS:
            self.font_box.addItem(label, da_nome)
        i = self.font_box.findData(textlayout.font_da_name(info.font))
        self.font_box.setCurrentIndex(i if i >= 0 else 0)
        f.addRow(tr("Font"), self.font_box)
        self.size_box = QSpinBox()
        self.size_box.setRange(3, 120)
        self.size_box.setValue(int(info.fontsize or 11))
        f.addRow(tr("Corpo"), self.size_box)
        self.color_btn, self.color = _color_btn(_hex(info.text_color), "Colore testo")
        f.addRow(tr("Colore testo"), self.color_btn)
        self.fill_chk = QCheckBox(tr("Colore di sfondo"))
        self.fill_chk.setChecked(bool(info.fill_color))
        f.addRow("", self.fill_chk)
        self.fill_btn, self.fill = _color_btn(_hex(info.fill_color or (1, 1, 1)), "Colore sfondo")
        f.addRow(tr("Sfondo"), self.fill_btn)
        self.border = QComboBox()
        for k, label in docmod.border_style_names().items():
            self.border.addItem(label, k)
        i = self.border.findData(docmod.BORDER_STYLES.get(info.border_style, 1))
        self.border.setCurrentIndex(max(0, i))
        f.addRow(tr("Bordo"), self.border)
        self.border_w = QSpinBox()
        self.border_w.setRange(0, 10)
        self.border_w.setValue(int(info.border_width or 1))
        f.addRow(tr("Spessore bordo"), self.border_w)
        self.maxlen = QSpinBox()
        self.maxlen.setRange(0, 4000)
        self.maxlen.setValue(int(info.maxlen or 0))
        self.maxlen.setSpecialValueText("illimitato")
        f.addRow(tr("Caratteri max"), self.maxlen)
        flags = QHBoxLayout()
        self.required = QCheckBox(tr("Obbligatorio"))
        self.required.setChecked(info.required)
        self.readonly = QCheckBox(tr("Sola lettura"))
        self.readonly.setChecked(info.read_only)
        self.multiline = QCheckBox(tr("Più righe"))
        self.multiline.setChecked(info.multiline)
        self.password = QCheckBox(tr("Password"))
        self.password.setChecked(info.password)
        self.comb = QCheckBox(tr("Caratteri equidistanti"))
        self.comb.setChecked(info.comb)
        for c in (self.required, self.readonly, self.multiline, self.password, self.comb):
            flags.addWidget(c)
        flags.addStretch(1)
        fb = QWidget()
        fb.setLayout(flags)
        f.addRow(tr("Opzioni"), fb)
        self.options = QLineEdit(", ".join(info.options))
        self.options.setPlaceholderText(tr("Opzione 1, Opzione 2, …"))
        f.addRow(tr("Opzioni elenco"), self.options)
        v.addLayout(f)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("Applica"))
        bb.button(QDialogButtonBox.Ok).setProperty("accent", True)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def values(self) -> dict[str, Any]:
        props: dict[str, Any] = {
            "field_name": self.name.text().strip(),
            "text_font": str(self.font_box.currentData()),
            "text_fontsize": float(self.size_box.value()),
            "text_color": rgb(self.color["color"]),
            "fill_color": rgb(self.fill["color"]) if self.fill_chk.isChecked() else None,
            "border_style": int(self.border.currentData()),
            "border_width": float(self.border_w.value()),
            "text_maxlen": int(self.maxlen.value()),
        }
        flags = 0
        if self.required.isChecked():
            flags |= 2
        if self.readonly.isChecked():
            flags |= 1
        if self.multiline.isChecked():
            flags |= 1 << 12
        if self.password.isChecked():
            flags |= 1 << 13
        if self.comb.isChecked():
            flags |= 1 << 24
        props["field_flags"] = flags
        if self.options.text().strip():
            props["choice_values"] = [s.strip() for s in self.options.text().split(",") if s.strip()]
        return {"props": props, "value": self.value.text(), "tooltip": self.tooltip.text().strip()}


class NewFieldDialog(QDialog):
    """Creazione di un nuovo campo modulo."""

    def __init__(self, parent: QWidget | None = None, tipo: str = "text") -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Nuovo campo"))
        self.palette = theme.corrente()
        dlgutil.adatta_a_schermo(self, 440, 470)
        v = QVBoxLayout(self)
        f = QFormLayout()
        self.kind = QComboBox()
        for key, label, ico in (
            ("text", "Campo di testo", "text-field"),
            ("checkbox", "Casella di spunta", "check"),
            ("combo", "Menu a tendina", "dropdown"),
            ("list", "Elenco", "dropdown"),
            ("button", "Pulsante", "form"),
            ("signature", "Campo firma", "sign"),
        ):
            self.kind.addItem(icons.icon(ico, self.palette.text, 18), label, key)
        # il tipo arriva dallo strumento scelto: senza questo la finestra
        # diceva sempre «Campo di testo» anche per la casella di spunta
        i = self.kind.findData(tipo)
        self.kind.setCurrentIndex(i if i >= 0 else 0)
        f.addRow(tr("Tipo"), self.kind)
        self.name = QLineEdit()
        f.addRow(tr("Nome"), self.name)
        self.default = QLineEdit()
        f.addRow(tr("Valore iniziale"), self.default)
        self.tooltip = QLineEdit()
        f.addRow(tr("Descrizione"), self.tooltip)
        self.font_box = QComboBox()
        for label, da_nome in textlayout.FIELD_FONTS:
            self.font_box.addItem(label, da_nome)
        self.font_box.setCurrentIndex(max(0, self.font_box.findData("Helv")))
        f.addRow(tr("Font"), self.font_box)
        self.size_box = QSpinBox()
        self.size_box.setRange(3, 120)
        self.size_box.setValue(12)
        f.addRow(tr("Corpo"), self.size_box)
        self.options = QLineEdit("Opzione 1, Opzione 2")
        f.addRow(tr("Opzioni elenco"), self.options)
        self.caption = QLineEdit()
        self.caption.setPlaceholderText(tr("Testo del pulsante / della casella"))
        f.addRow(tr("Didascalia"), self.caption)
        flags = QHBoxLayout()
        self.required = QCheckBox(tr("Obbligatorio"))
        self.readonly = QCheckBox(tr("Sola lettura"))
        self.multiline = QCheckBox(tr("Più righe"))
        self.password = QCheckBox(tr("Password"))
        for c in (self.required, self.readonly, self.multiline, self.password):
            flags.addWidget(c)
        flags.addStretch(1)
        fb = QWidget()
        fb.setLayout(flags)
        f.addRow(tr("Opzioni"), fb)
        v.addLayout(f)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("Crea"))
        bb.button(QDialogButtonBox.Ok).setProperty("accent", True)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def values(self) -> dict[str, Any]:
        return {
            "kind": str(self.kind.currentData()),
            "name": self.name.text().strip(),
            "value": self.default.text(),
            "tooltip": self.tooltip.text().strip(),
            "font": str(self.font_box.currentData()),
            "fontsize": float(self.size_box.value()),
            "options": [s.strip() for s in self.options.text().split(",") if s.strip()],
            "button_caption": self.caption.text().strip(),
            "required": self.required.isChecked(),
            "read_only": self.readonly.isChecked(),
            "multiline": self.multiline.isChecked(),
            "password": self.password.isChecked(),
        }


# --------------------------------------------------------------- sicurezza


def _permissions() -> tuple[tuple[str, int], ...]:
    """I permessi in italiano, con la loro etichetta tradotta."""
    return (
        (tr("Stampa"), pymupdf.PDF_PERM_PRINT),
        (tr("Modificare il documento"), pymupdf.PDF_PERM_MODIFY),
        (tr("Copia testo e immagini"), pymupdf.PDF_PERM_COPY),
        (tr("Aggiungere annotazioni"), pymupdf.PDF_PERM_ANNOTATE),
        (tr("Compilare i moduli"), pymupdf.PDF_PERM_FORM),
        (tr("Assemblare il documento"), pymupdf.PDF_PERM_ASSEMBLE),
        (tr("Stampa ad alta qualità"), pymupdf.PDF_PERM_PRINT_HQ),
        (tr("Accessibilità"), pymupdf.PDF_PERM_ACCESSIBILITY),
    )


def _algoritmi() -> tuple[tuple[str, int], ...]:
    """Gli algoritmi di cifratura, con l'etichetta tradotta."""
    return (
        (tr("AES-256 (consigliato)"), pymupdf.PDF_ENCRYPT_AES_256),
        (tr("AES-128"), pymupdf.PDF_ENCRYPT_AES_128),
        (tr("RC4-128 (legacy)"), pymupdf.PDF_ENCRYPT_RC4_128),
    )


class SecurityDialog(QDialog):
    """Password di apertura, permessi e cifratura."""

    def __init__(self, doc: docmod.Document, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.doc = doc
        self.palette = theme.corrente()
        self.setWindowTitle(tr("Protezione del documento"))
        dlgutil.adatta_a_schermo(self, 520, 560)
        v = QVBoxLayout(self)

        g = QGroupBox(tr("Password di apertura"))
        f = QFormLayout(g)
        self.user_pw = QLineEdit()
        self.user_pw.setEchoMode(QLineEdit.Password)
        self.user_pw.setPlaceholderText(tr("necessaria per aprire il file"))
        f.addRow(tr("Password utente"), self.user_pw)
        self.owner_pw = QLineEdit()
        self.owner_pw.setEchoMode(QLineEdit.Password)
        self.owner_pw.setPlaceholderText(tr("necessaria per modificare i permessi"))
        f.addRow(tr("Password proprietario"), self.owner_pw)
        self.alg = QComboBox()
        for label, val in _algoritmi():
            self.alg.addItem(label, val)
        f.addRow(tr("Cifratura"), self.alg)
        v.addWidget(g)

        g2 = QGroupBox(tr("Permessi"))
        grid = QGridLayout(g2)
        self.checks: dict[int, QCheckBox] = {}
        current = doc.permissions() if doc.is_open else -1
        for i, (label, bit) in enumerate(_permissions()):
            cb = QCheckBox(label)
            cb.setChecked(bool(current == -1 or (current & bit)))
            self.checks[bit] = cb
            grid.addWidget(cb, i // 2, i % 2)
        v.addWidget(g2)

        self.status = QLabel("")
        self.status.setProperty("role", "hint")
        self.status.setWordWrap(True)
        v.addWidget(self.status)

        row = QHBoxLayout()
        b_remove = QPushButton(tr("Rimuovi protezione"))
        b_remove.clicked.connect(self._remove)
        row.addWidget(b_remove)
        row.addStretch(1)
        v.addLayout(row)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("Applica e salva"))
        bb.button(QDialogButtonBox.Ok).setProperty("accent", True)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self._update_status()

    def _update_status(self) -> None:
        if self.doc.has_encryption:
            self.status.setText(tr("Il documento è attualmente protetto."))
        else:
            self.status.setText(tr("Il documento non è protetto."))

    def _remove(self) -> None:
        if not self.doc.is_open:
            return
        pw, ok = _ask_password(self, "Password del proprietario")
        if not ok:
            return
        try:
            self.doc.remove_encryption(pw)
            self._update_status()
            QMessageBox.information(self, tr("Protezione"), tr("Protezione rimossa. Salva il file per confermare."))
        except Exception as exc:
            QMessageBox.warning(self, tr("Protezione"), str(exc))

    def permissions_value(self) -> int:
        v = 0
        for bit, cb in self.checks.items():
            if cb.isChecked():
                v |= bit
        return v

    def values(self) -> dict[str, Any]:
        return {
            "user_pw": self.user_pw.text(),
            "owner_pw": self.owner_pw.text(),
            "algorithm": int(self.alg.currentData()),
            "permissions": self.permissions_value(),
        }


def _ask_password(parent: QWidget, title: str) -> tuple[str, bool]:
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    v = QVBoxLayout(dlg)
    v.addWidget(QLabel(title))
    e = QLineEdit()
    e.setEchoMode(QLineEdit.Password)
    v.addWidget(e)
    bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    bb.button(QDialogButtonBox.Ok).setText(tr("Conferma"))
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    v.addWidget(bb)
    if dlg.exec() == QDialog.Accepted:
        return e.text(), True
    return "", False


# --------------------------------------------------------------- pagine


class PageSetupDialog(QDialog):
    """Dimensione, orientamento e margini di una pagina."""

    def __init__(self, current: tuple[float, float] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.palette = theme.corrente()
        self.setWindowTitle(tr("Impostazione pagina"))
        dlgutil.adatta_a_schermo(self, 440, 400)
        v = QVBoxLayout(self)
        f = QFormLayout()
        self.size_box = QComboBox()
        for name in ("A4", "A3", "A5", "Letter", "Legal", "Tabloid", "B5", "B4", "A0", "A1", "A2", "A6", "Executive"):
            if name in units.PAGE_SIZES:
                self.size_box.addItem(name, name)
        if current:
            best = _closest_size(current)
            self.size_box.setCurrentIndex(self.size_box.findData(best))
        f.addRow(tr("Formato"), self.size_box)
        self.orient = QComboBox()
        self.orient.addItem(tr("Verticale"), "portrait")
        self.orient.addItem(tr("Orizzontale"), "landscape")
        f.addRow(tr("Orientamento"), self.orient)
        self.w = QSpinBox()
        self.w.setRange(50, 5000)
        self.w.setSuffix(" pt")
        self.h = QSpinBox()
        self.h.setRange(50, 5000)
        self.h.setSuffix(" pt")
        box = QHBoxLayout()
        box.addWidget(self.w)
        box.addWidget(QLabel(tr("×")))
        box.addWidget(self.h)
        bw = QWidget()
        bw.setLayout(box)
        f.addRow(tr("Dimensione"), bw)
        self.margin = QSpinBox()
        self.margin.setRange(0, 300)
        self.margin.setValue(40)
        self.margin.setSuffix(" pt")
        f.addRow(tr("Margine"), self.margin)
        v.addLayout(f)
        self.size_box.currentIndexChanged.connect(self._apply)
        self.orient.currentIndexChanged.connect(self._apply)
        self._apply()
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("Applica"))
        bb.button(QDialogButtonBox.Ok).setProperty("accent", True)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _apply(self) -> None:
        w, h = units.paper_size(str(self.size_box.currentData()))
        if self.orient.currentData() == "landscape":
            w, h = h, w
        self.w.blockSignals(True)
        self.h.blockSignals(True)
        self.w.setValue(int(w))
        self.h.setValue(int(h))
        self.w.blockSignals(False)
        self.h.blockSignals(False)

    def values(self) -> tuple[float, float, int]:
        return float(self.w.value()), float(self.h.value()), int(self.margin.value())


class CropPageDialog(QDialog):
    """Ritaglio della pagina: margini automatici o manuali.

    Il ritaglio agisce sull'area visibile e non altera i contenuti, come in
    Acrobat: e' lo strumento giusto per togliere i bordi neri dello scanner.
    """

    def __init__(
        self,
        page_rect: tuple[float, float],
        detected: tuple[float, float, float, float] | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.palette = theme.corrente()
        self.setWindowTitle(tr("Ritaglia pagina"))
        dlgutil.adatta_a_schermo(self, 430, 330)
        self._full = page_rect
        v = QVBoxLayout(self)
        self.hint = QLabel("")
        self.hint.setProperty("role", "hint")
        self.hint.setWordWrap(True)
        v.addWidget(self.hint)

        f = QFormLayout()
        self.top = QSpinBox()
        self.bottom = QSpinBox()
        self.left = QSpinBox()
        self.right = QSpinBox()
        for w in (self.top, self.bottom, self.left, self.right):
            w.setRange(0, 5000)
            w.setSuffix(" pt")
            w.valueChanged.connect(self._sync_hint)
        f.addRow(tr("Margine superiore"), self.top)
        f.addRow(tr("Margine inferiore"), self.bottom)
        f.addRow(tr("Margine sinistro"), self.left)
        f.addRow(tr("Margine destro"), self.right)
        v.addLayout(f)

        self.auto = QCheckBox(tr("Rileva il contenuto automaticamente"))
        self.auto.setChecked(detected is not None)
        self.auto.toggled.connect(self._on_auto)
        v.addWidget(self.auto)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("Ritaglia"))
        bb.button(QDialogButtonBox.Ok).setProperty("accent", True)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

        self._on_auto(detected is not None)
        if detected:
            self._set_margins(detected)
        else:
            self._sync_hint()

    def _set_margins(self, detected: tuple[float, float, float, float]) -> None:
        larghezza, altezza = self._full
        for w, v in (
            (self.left, detected[0]),
            (self.top, detected[1]),
            (self.right, larghezza - detected[2]),
            (self.bottom, altezza - detected[3]),
        ):
            w.blockSignals(True)
            w.setValue(max(0, int(round(v))))
            w.blockSignals(False)
        self._sync_hint()

    def _on_auto(self, on: bool) -> None:
        for w in (self.top, self.bottom, self.left, self.right):
            w.setEnabled(not on)
        self._sync_hint()

    def _sync_hint(self) -> None:
        larghezza, altezza = self._full
        w = max(0, larghezza - self.left.value() - self.right.value())
        h = max(0, altezza - self.top.value() - self.bottom.value())
        if self.auto.isChecked():
            self.hint.setText(tr("L'area viene ricavata dal contenuto della pagina."))
        elif w < 20 or h < 20:
            self.hint.setText(tr("L'area risultante è troppo piccola."))
            self.hint.setProperty("role", "warning")
        else:
            self.hint.setText(
                tr("Area visibile: {larghezza} × {altezza} pt").format(
                    larghezza=f"{w:.0f}", altezza=f"{h:.0f}"
                )
            )
            self.hint.setProperty("role", "hint")
        self.hint.style().unpolish(self.hint)
        self.hint.style().polish(self.hint)

    def values(self) -> dict[str, Any]:
        larghezza, altezza = self._full
        auto = self.auto.isChecked()
        return {
            "auto": auto,
            "rect": None
            if auto
            else (
                float(self.left.value()),
                float(self.top.value()),
                larghezza - float(self.right.value()),
                altezza - float(self.bottom.value()),
            ),
        }


class ReduceSizeDialog(QDialog):
    """Riduzione delle dimensioni del file: qualita' e risoluzione delle immagini."""

    @staticmethod
    def scelte_dpi() -> tuple[tuple[str, int], ...]:
        """Le risoluzioni offerte, con l'etichetta tradotta.

        Non una costante: le etichette sono lunghe e contengono italiano, e in
        una costante di classe la lingua resterebbe quella del primo import.
        """
        return (
            (tr("Mantieni la risoluzione attuale"), 0),
            (tr("300 dpi (stampa di qualità)"), 300),
            (tr("200 dpi (buon compromesso)"), 200),
            (tr("150 dpi (solo schermo)"), 150),
            (tr("96 dpi (schermo e internet)"), 96),
        )

    def __init__(self, inventario: list[dict[str, Any]], default_quality: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.palette = theme.corrente()
        self.inventario = list(inventario)
        self.setWindowTitle(tr("Riduci dimensione del file"))
        dlgutil.adatta_a_schermo(self, 470, 420)
        v = QVBoxLayout(self)

        self.info = QLabel("")
        self.info.setProperty("role", "hint")
        self.info.setWordWrap(True)
        v.addWidget(self.info)

        f = QFormLayout()
        self.quality = QSlider(Qt.Horizontal)
        self.quality.setRange(10, 100)
        self.quality.setValue(default_quality)
        self.quality.setTickInterval(10)
        self.quality.setTickPosition(QSlider.TicksBelow)
        self.quality.valueChanged.connect(lambda _: self._update())
        riga = QHBoxLayout()
        riga.addWidget(self.quality, 1)
        self.quality_lbl = QLabel("")
        self.quality_lbl.setMinimumWidth(34)
        riga.addWidget(self.quality_lbl)
        box = QWidget()
        box.setLayout(riga)
        f.addRow(tr("Qualità JPEG"), box)

        self.dpi = QComboBox()
        for label, valore in self.scelte_dpi():
            self.dpi.addItem(label, valore)
        self.dpi.setCurrentIndex(2)
        self.dpi.currentIndexChanged.connect(lambda _: self._update())
        f.addRow(tr("Risoluzione massima"), self.dpi)

        self.all_images = QCheckBox(tr("Ricomprimi anche le immagini già ottimizzate"))
        self.all_images.toggled.connect(lambda _: self._update())
        f.addRow("", self.all_images)
        v.addLayout(f)

        self.estimate = QLabel("")
        self.estimate.setProperty("role", "hint")
        self.estimate.setWordWrap(True)
        v.addWidget(self.estimate)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("Riduci"))
        bb.button(QDialogButtonBox.Ok).setProperty("accent", True)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self._update()

    def _update(self) -> None:
        q = int(self.quality.value())
        self.quality_lbl.setText(f"{q}")
        max_dpi = int(self.dpi.currentData() or 0)
        megapixel = sum(i["megapixels"] for i in self.inventario)
        grandi = [i for i in self.inventario if i["megapixels"] >= 0.25]
        if not self.inventario:
            self.info.setText(tr("Il documento non contiene immagini: ridurlo non cambierebbe nulla."))
        else:
            self.info.setText(
                tr("{tot} immagini, {megapixel} megapixel in totale.\n"
                   "{grandi} superano 0,25 MP e vengono ridimensionate.")
                .format(
                    tot=len(self.inventario),
                    megapixel=f"{megapixel:.1f}",
                    grandi=len(grandi),
                )
            )
        if not self.inventario:
            self.estimate.setText(tr("Nessuna immagine da ridurre."))
            return
        # stima grezza: il peso segue i megapixel e la qualita' scelta
        fattore_q = 0.9 + (q / 100.0) * 3.2
        peso = 0.0
        for i in self.inventario:
            mp = i["megapixels"]
            if max_dpi:
                # stima la riduzione assumendo 150 dpi sul foglio
                limite = (max_dpi / 72.0) ** 2
                if mp > limite:
                    # la stima deve stare sotto il limite: con ``max`` si
                    # sceglieva il valore piu' alto dei due e la dimensione
                    # annunciata era proprio quella evitata
                    mp = min(limite, mp * 0.35)
            peso += mp * fattore_q * 40000
        peso = max(peso, 4000)
        if peso > 1_000_000:
            testo = tr("Dimensione stimata: circa {mb} MB").format(mb=f"{peso / 1_000_000:.1f}")
        else:
            testo = tr("Dimensione stimata: circa {kb} kB").format(kb=f"{peso / 1000:.0f}")
        if self.all_images.isChecked():
            testo += tr(" (tutte le immagini)")
        self.estimate.setText(testo)

    def values(self) -> dict[str, Any]:
        return {
            "quality": int(self.quality.value()),
            "max_dpi": int(self.dpi.currentData() or 0) or None,
            "recompress_all": self.all_images.isChecked(),
        }


class PageNumberDialog(QDialog):
    """Numerazione delle pagine: posizione, formato e numero iniziale."""

    def __init__(self, page_count: int, presente: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.palette = theme.corrente()
        self.page_count = page_count
        self.setWindowTitle(tr("Numerazione pagine"))
        dlgutil.adatta_a_schermo(self, 430, 380)
        v = QVBoxLayout(self)

        if presente:
            nota = QLabel(tr("Il documento ha già una numerazione: applicandone una nuova "
                          "si affiancherebbe all'esistente."))
            nota.setProperty("role", "warning")
            nota.setWordWrap(True)
            v.addWidget(nota)

        f = QFormLayout()
        self.first = QSpinBox()
        self.first.setRange(0, 9999)
        self.first.setValue(1)
        f.addRow(tr("Numero iniziale"), self.first)

        self.position = QComboBox()
        for label, valore in (
            ("In basso a sinistra", "bottom_left"),
            ("In basso al centro", "bottom_center"),
            ("In basso a destra", "bottom_right"),
        ):
            self.position.addItem(label, valore)
        f.addRow(tr("Posizione"), self.position)

        self.margin = QSpinBox()
        self.margin.setRange(0, 300)
        self.margin.setValue(28)
        self.margin.setSuffix(" pt")
        f.addRow(tr("Margine dal bordo"), self.margin)

        self.size_box = QSpinBox()
        self.size_box.setRange(5, 72)
        self.size_box.setValue(9)
        self.size_box.setSuffix(" pt")
        f.addRow(tr("Corpo del testo"), self.size_box)

        self.total = QCheckBox(tr("Mostra anche il totale («3 / 12»)"))
        f.addRow("", self.total)

        self.skip_first = QCheckBox(tr("Non numerare la prima pagina (copertina)"))
        f.addRow("", self.skip_first)
        v.addLayout(f)

        self.anteprima = QLabel("")
        self.anteprima.setProperty("role", "hint")
        v.addWidget(self.anteprima)
        self.first.valueChanged.connect(lambda _: self._update())
        self.total.toggled.connect(lambda _: self._update())
        self.skip_first.toggled.connect(lambda _: self._update())
        self._update()

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("Applica"))
        bb.button(QDialogButtonBox.Ok).setProperty("accent", True)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _update(self) -> None:
        quante = max(0, self.page_count - (1 if self.skip_first.isChecked() else 0))
        if not quante:
            self.anteprima.setText(tr("Non ci sono pagine da numerare."))
            return
        ultimo = self.first.value() + quante - 1
        if self.total.isChecked():
            # il totale e' l'ultimo numero stampato, come in «3 / 12»
            self.anteprima.setText(
                tr("Verranno numerate {quante} pagine: la prima mostra "
                   "«{primo} / {ultimo}», l'ultima «{ultimo} / {ultimo}».")
                .format(
                    quante=quante,
                    primo=self.first.value(),
                    ultimo=ultimo,
                )
            )
        else:
            self.anteprima.setText(
                tr("Verranno numerate {quante} pagine, da {primo} a {ultimo}.")
                .format(quante=quante, primo=self.first.value(), ultimo=ultimo)
            )

    def values(self) -> dict[str, Any]:
        return {
            "first": int(self.first.value()),
            "position": str(self.position.currentData()),
            "margin": float(self.margin.value()),
            "fontsize": float(self.size_box.value()),
            "total": self.total.isChecked(),
            "skip_first": self.skip_first.isChecked(),
        }


def _closest_size(current: tuple[float, float]) -> str:
    best, best_d = "A4", 1e18
    for name, (w, h) in units.PAGE_SIZES.items():
        for a, b in ((w, h), (h, w)):
            d = abs(a - current[0]) + abs(b - current[1])
            if d < best_d:
                best, best_d = name, d
    return best


class SplitDialog(QDialog):
    """Divisione di un documento in parti."""

    def __init__(self, page_count: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.palette = theme.corrente()
        self.setWindowTitle(tr("Dividi documento"))
        v = QVBoxLayout(self)
        f = QFormLayout()
        self.every = QSpinBox()
        self.every.setRange(1, max(1, page_count))
        self.every.setValue(1)
        f.addRow(tr("Ogni quante pagine"), self.every)
        self.by_bookmarks = QCheckBox(tr("Dividi in base ai segnalibri"))
        f.addRow("", self.by_bookmarks)
        self.prefix = QLineEdit("parte")
        f.addRow(tr("Prefisso file"), self.prefix)
        v.addLayout(f)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("Dividi"))
        bb.button(QDialogButtonBox.Ok).setProperty("accent", True)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def values(self) -> dict[str, Any]:
        return {
            "every": int(self.every.value()),
            "by_bookmarks": self.by_bookmarks.isChecked(),
            "prefix": self.prefix.text().strip() or "parte",
        }


class MergeDialog(QDialog):
    """Unione di più documenti."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.palette = theme.corrente()
        self.setWindowTitle(tr("Unisci documenti"))
        dlgutil.adatta_a_schermo(self, 520, 420)
        v = QVBoxLayout(self)
        self.list = QListWidget()
        v.addWidget(self.list, 1)
        row = QHBoxLayout()
        b_add = QPushButton(tr("Aggiungi file…"))
        b_add.clicked.connect(self._add)
        b_rm = QPushButton(tr("Rimuovi"))
        b_rm.clicked.connect(lambda: self.list.takeItem(self.list.currentRow()))
        b_up = QPushButton(tr("Sposta su"))
        b_up.clicked.connect(lambda: self._move(-1))
        b_down = QPushButton(tr("Sposta giù"))
        b_down.clicked.connect(lambda: self._move(1))
        for b in (b_add, b_rm, b_up, b_down):
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("Unisci"))
        bb.button(QDialogButtonBox.Ok).setProperty("accent", True)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _add(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Scegli i documenti", "", "PDF (*.pdf)")
        for f in files:
            self.list.addItem(QListWidgetItem(f))

    def _move(self, delta: int) -> None:
        r = self.list.currentRow()
        if r < 0:
            return
        nr = r + delta
        if 0 <= nr < self.list.count():
            it = self.list.takeItem(r)
            self.list.insertItem(nr, it)
            self.list.setCurrentRow(nr)

    def files(self) -> list[str]:
        return [self.list.item(i).text() for i in range(self.list.count())]


# ------------------------------------------------------- conversione da immagini

#: lato lungo dell'anteprima, in punti: la miniatura deve stare nella casella
#: della griglia, non essere l'immagine intera rimpicciolita
LATO_MINIATURA = 110


def _conta(n: int, italiano: tuple[str, str], inglese: tuple[str, str]) -> str:
    """«1 immagine», «3 immagini»: il numero con il nome contato.

    Le due coppie servono perche' il nome singolare e plurale cambia da una
    lingua all'altra, mentre il numero no.
    """
    singolare, plurale = inglese if i18n.lingua() == "en" else italiano
    return f"{n} {singolare if n == 1 else plurale}"


def _anteprima(percorso: Path) -> tuple[QPixmap, tuple[int, int] | None]:
    """Miniatura e dimensione in pixel di un'immagine, leggendola una volta sola.

    L'immagine si dimezza finche' non sta nella casella della griglia:
    decodificare dodici megapixel per disegnare centoventi punti costerebbe
    piu' di tutto il resto della conversione. Un'anteprima che non si genera non
    e' un errore: sotto il nome del file non ci sara' la dimensione, e il file
    si inserisce lo stesso. Se non si puo' leggere, a dirlo non basta il
    dialogo delle scelte: lo dice la conversione.
    """
    try:
        pix = pymupdf.Pixmap(str(percorso))
    except Exception:
        return QPixmap(), None
    misura = (pix.width, pix.height)
    try:
        while max(pix.width, pix.height) > LATO_MINIATURA * 2:
            pix.shrink(1)
        pm = QPixmap()
        if pm.loadFromData(pix.tobytes("png")):
            return pm, misura
    except Exception:
        pass
    return QPixmap(), misura


class ImagesToPdfDialog(QDialog):
    """Conversione di un gruppo di immagini in un unico PDF.

    Le immagini si scelgono, si mettono in ordine e si dispongono sulla pagina
    secondo le opzioni: il risultato e' un file nuovo, e il documento aperto non
    ci passa per un pelo.
    """

    @staticmethod
    def adattamenti() -> tuple[tuple[str, str], ...]:
        """Gli adattamenti dell'immagine alla cella, con la spiegazione.

        Nella finestra l'etichetta e' breve e la spiegazione va nella
        suggerimento: un menu a tendina con dentro «Adatta alla pagina (si vede
        tutta l'immagine)» e' largo il doppio del foglio, e il dialogo che
        contiene tutte le opzioni smette di stare nello schermo.
        """
        return (
            ("pagina", tr("Adatta alla pagina"), tr("L'immagine si vede intera, con spazi bianchi")),
            ("piena", tr("Riempi la pagina"), tr("La pagina si riempie e l'immagine viene tagliata")),
            ("originale", tr("Dimensione reale"), tr("L'immagine non viene ridimensionata")),
        )

    @staticmethod
    def orientamenti() -> tuple[tuple[str, str], ...]:
        return (("verticale", tr("Verticale")), ("orizzontale", tr("Orizzontale")))

    @staticmethod
    def formati() -> tuple[tuple[str, str], ...]:
        """I formati pagina, con i piu' richiesti in cima e la foto in fondo."""
        # l'ordine del dizionario parte da A0, che nessuno stampa: in cima a un
        # elenco che si apre per scegliere la carta vanno A4 e Letter
        primi = ("A4", "Letter", "A3", "A5", "Legal")
        scelti = [n for n in primi if n in units.PAGE_SIZES]
        scelti += [n for n in units.PAGE_SIZES if n not in scelti]
        return tuple((n, n) for n in scelti) + (("immagine", tr("Come la prima immagine")),)

    def __init__(
        self,
        parent: QWidget | None = None,
        start_dir: str = "",
        files: Sequence[str] = (),
    ) -> None:
        super().__init__(parent)
        self.palette = theme.corrente()
        self.start_dir = start_dir
        self.setWindowTitle(tr("Converti immagini in PDF"))
        dlgutil.adatta_a_schermo(self, 840, 660)
        v = QVBoxLayout(self)
        self.list = QListWidget()
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setWordWrap(True)
        self.list.setIconSize(QSize(LATO_MINIATURA, LATO_MINIATURA))
        self.list.setGridSize(QSize(LATO_MINIATURA + 40, LATO_MINIATURA + 56))
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        # le miniature si riordinano anche a mano: e' l'unico modo per mettere
        # delle foto in ordine senza leggerne i nomi uno per uno
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        v.addWidget(self.list, 1)
        v.addLayout(self._barra_pulsanti())
        # l'etichetta esiste prima delle opzioni: costruendole si accendono e
        # si spengono a vicenda, e una di loro chiede subito il riepilogo
        self.riepilogo = QLabel("")
        v.addWidget(self._barra_opzioni())
        v.addWidget(self.riepilogo)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("Converti"))
        bb.button(QDialogButtonBox.Ok).setProperty("accent", True)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        for f in files:
            self._aggiungi(Path(f))
        self._aggiorna_riepilogo()

    def _barra_pulsanti(self) -> QHBoxLayout:
        row = QHBoxLayout()
        b_add = QPushButton(tr("Aggiungi…"))
        b_add.clicked.connect(self._scegli)
        b_rm = QPushButton(tr("Rimuovi"))
        b_rm.clicked.connect(self._rimuovi)
        b_clear = QPushButton(tr("Svuota"))
        b_clear.clicked.connect(self._svuota)
        b_up = QPushButton(tr("Sposta su"))
        b_up.clicked.connect(lambda: self._sposta(-1))
        b_down = QPushButton(tr("Sposta giù"))
        b_down.clicked.connect(lambda: self._sposta(1))
        b_nome = QPushButton(tr("Ordina per nome"))
        b_nome.clicked.connect(lambda: self._ordina("nome"))
        b_data = QPushButton(tr("Ordina per data"))
        b_data.clicked.connect(lambda: self._ordina("data"))
        for b in (b_add, b_rm, b_clear, b_up, b_down, b_nome, b_data):
            row.addWidget(b)
        row.addStretch(1)
        return row

    def _barra_opzioni(self) -> QGroupBox:
        """Le opzioni di pagina, in un gruppo con due colonne.

        Non in una fila sola: sei coppie di etichetta e controllo in fila
        occuperebbero una larghezza che il dialogo non riesce a tenere nello
        schermo, e a quel punto si autoannida in un'area scorrevole e tutto
        si schiaccia. In due colonne la larghezza resta quella di una coppia.
        """
        gruppo = QGroupBox(tr("Disposizione sulla pagina"))
        griglia = QGridLayout(gruppo)
        self.formato = QComboBox()
        for codice, etichetta in self.formati():
            self.formato.addItem(etichetta, codice)
        self.formato.setCurrentIndex(max(0, self.formato.findData("A4")))
        self.orientamento = QComboBox()
        for codice, etichetta in self.orientamenti():
            self.orientamento.addItem(etichetta, codice)
        self.adattamento = QComboBox()
        for codice, etichetta, spiegazione in self.adattamenti():
            self.adattamento.addItem(etichetta, codice)
            indice = self.adattamento.count() - 1
            self.adattamento.setItemData(indice, spiegazione, Qt.ToolTipRole)
        self.adattamento.setToolTip(
            tr("Come l'immagine viene messa nel posto che le e' stato assegnato")
        )
        self.margini = QDoubleSpinBox()
        self.margini.setRange(0.0, 60.0)
        self.margini.setDecimals(1)
        self.margini.setSingleStep(1.0)
        self.margini.setValue(1.0)
        self.margini.setSuffix(" mm")
        self.margini.setToolTip(tr("Spazio bianco attorno a ogni immagine"))
        self.per_pagina = QSpinBox()
        self.per_pagina.setRange(1, docmod.MAX_IMMAGINI_PER_PAGINA)
        self.per_pagina.setValue(1)
        self.per_pagina.setToolTip(tr("Quante immagini su ogni pagina, disposte in griglia"))
        self.dpi = QSpinBox()
        self.dpi.setRange(36, 1200)
        self.dpi.setValue(150)
        self.dpi.setSingleStep(10)
        self.dpi.setSuffix(" dpi")
        self.dpi.setToolTip(tr("Risoluzione con cui viene stampata l'immagine"))
        self.dpi.setEnabled(False)
        sinistra = ((tr("Formato"), self.formato),
                    (tr("Orientamento"), self.orientamento),
                    (tr("Immagini per pagina"), self.per_pagina))
        destra = ((tr("Adattamento"), self.adattamento),
                  (tr("Margini"), self.margini),
                  (tr("Risoluzione"), self.dpi))
        for colonna, coppie in enumerate((sinistra, destra)):
            for riga, (etichetta, controllo) in enumerate(coppie):
                griglia.addWidget(QLabel(etichetta), riga, colonna * 2)
                griglia.addWidget(controllo, riga, colonna * 2 + 1)
        griglia.setColumnStretch(1, 1)
        griglia.setColumnStretch(3, 1)
        self.formato.currentIndexChanged.connect(self._opzioni_disponibili)
        self.adattamento.currentIndexChanged.connect(self._opzioni_disponibili)
        self.per_pagina.valueChanged.connect(lambda _v: self._opzioni_disponibili())
        self._opzioni_disponibili()
        return gruppo

    def _opzioni_disponibili(self, *_a: Any) -> None:
        """Spegne le opzioni che non cambierebbero il risultato.

        Girare la pagina non ha senso con il formato «immagine»: la decide la
        foto, e ruotarla cambierebbe la forma attesa dall'immagine. La
        risoluzione serve solo con la dimensione reale, e altrove starebbe li'
        come un numero che non influenza niente.
        """
        formato = self.formato.currentData()
        adattamento = self.adattamento.currentData()
        self.orientamento.setEnabled(formato != "immagine")
        self.dpi.setEnabled(adattamento == "originale")
        self._aggiorna_riepilogo()

    # ------------------------------------------------------------- le immagini

    def _aggiungi(self, percorso: Path) -> None:
        """Mette in lista un'immagine, saltando un percorso gia' presente."""
        testo = str(percorso)
        if testo in self.images():
            return
        miniatura, misura = _anteprima(percorso)
        nome = percorso.name
        if misura is not None:
            nome = f"{nome}\n{misura[0]}×{misura[1]} px"
        item = QListWidgetItem(nome)
        item.setData(Qt.UserRole, testo)
        item.setToolTip(percorso.name)
        if not miniatura.isNull():
            item.setIcon(QIcon(miniatura))
        self.list.addItem(item)

    def _scegli(self) -> None:
        from ..main_window import image_filter

        scelte, _ = QFileDialog.getOpenFileNames(self, tr("Scegli le immagini"),
                                                 self.start_dir, image_filter())
        for f in scelte:
            self._aggiungi(Path(f))
        self._aggiorna_riepilogo()

    def _rimuovi(self) -> None:
        for item in self.list.selectedItems():
            self.list.takeItem(self.list.row(item))
        self._aggiorna_riepilogo()

    def _svuota(self) -> None:
        self.list.clear()
        self._aggiorna_riepilogo()

    def _sposta(self, delta: int) -> None:
        """Sposta di un posto le voci selezionate, tenendone l'ordine relativo.

        Le voci selezionate si muovono insieme, come un blocco dalla prima
        all'ultima: muoverle una per una le farebbe scavalcare a vicenda, perche'
        ognuna occuperebbe il posto appena liberato da quella davanti. Fuori dai
        bordi non si muove niente, invece di spostare quello che non puo' scendere
        e lasciare indietro quello che non puo' salire.
        """
        voci = self.list.selectedItems()
        if not voci:
            return
        righe = sorted(self.list.row(it) for it in voci)
        primo, ultimo = righe[0], righe[-1]
        nuovo = primo + delta
        if nuovo < 0:
            nuovo = 0
        if nuovo + (ultimo - primo) >= self.list.count():
            nuovo = self.list.count() - 1 - (ultimo - primo)
        if nuovo == primo:
            return
        # dall'ultima in alto: togliere prima quella sopra lascia valide le
        # righe sotto, che senza questo si sarebbero spostate di una
        scelte = [self.list.takeItem(r) for r in reversed(righe)]
        scelte.reverse()
        for offset, it in enumerate(scelte):
            self.list.insertItem(nuovo + offset, it)
        # la selezione segue le voci spostate: lasciarla sul numero di riga
        # selezionerebbe un'altra immagine, quella finita li' dopo il passaggio
        self.list.clearSelection()
        for r in range(nuovo, nuovo + len(scelte)):
            self.list.item(r).setSelected(True)
        self._aggiorna_riepilogo()

    def _ordina(self, criterio: str) -> None:
        voci = [self.list.takeItem(0) for _ in range(self.list.count())]
        if criterio == "data":
            voci.sort(key=lambda it: -_modifica(it))
        else:
            # per nome e' il nome del file, non il percorso: altrimenti le
            # cartelle, che vengono prima in ordine alfabetico, deciderebbero
            # l'ordine di tutto quello che c'e' dentro
            voci.sort(key=lambda it: (Path(it.data(Qt.UserRole)).name.lower(),
                                      (it.data(Qt.UserRole) or "").lower()))
        for it in voci:
            self.list.addItem(it)
        self._aggiorna_riepilogo()

    def _aggiorna_riepilogo(self) -> None:
        quante = self.list.count()
        per = int(self.per_pagina.value())
        pagine = -(-quante // per)
        self.riepilogo.setText(
            tr("{immagini} in {pagine}.").format(
                immagini=_conta(quante, ("immagine", "immagini"), ("image", "images")),
                pagine=_conta(pagine, ("pagina", "pagine"), ("page", "pages")),
            )
        )

    def images(self) -> list[str]:
        """I percorsi nell'ordine in cui verranno inseriti."""
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())]

    def values(self) -> dict[str, Any]:
        return {
            "page": self.formato.currentData(),
            "orientation": self.orientamento.currentData(),
            "fit": self.adattamento.currentData(),
            "margin": units.to_pt(float(self.margini.value()), "mm"),
            "per_page": int(self.per_pagina.value()),
            "dpi": int(self.dpi.value()),
        }


def _modifica(voce: QListWidgetItem) -> float:
    """Quando e' stato scritto il file della voce, o zero se non si sa."""
    try:
        return Path(voce.data(Qt.UserRole)).stat().st_mtime
    except Exception:
        return 0.0


# --------------------------------------------------------------- esportazione


class ExportDialog(QDialog):
    """Esportazione delle pagine in immagini, testo o PDF/A."""

    @staticmethod
    def formati() -> tuple[tuple[str, str], ...]:
        """I formati di esportazione, con la descrizione tradotta."""
        return (
            ("png", tr("PNG (immagine con perdita di qualità minima)")),
            ("jpg", tr("JPEG (più leggero)")),
            ("tiff", tr("TIFF (per stampa)")),
            ("pnm", tr("PNM")),
        )

    def __init__(
        self,
        page_count: int,
        parent: QWidget | None = None,
        current_page: int = 0,
    ) -> None:
        super().__init__(parent)
        self.palette = theme.corrente()
        self.page_count = page_count
        # «Pagina singola» riguarda la pagina che si sta guardando: senza
        # questo valore l'intervallo restava su «1» e si esportava sempre la
        # prima pagina, qualunque pagina fosse a schermo
        self.current_page = current_page
        self.setWindowTitle(tr("Esporta"))
        dlgutil.adatta_a_schermo(self, 520, 500)
        v = QVBoxLayout(self)
        f = QFormLayout()
        self.kind = QComboBox()
        self.kind.addItem(tr("Immagini delle pagine"), "image")
        self.kind.addItem(tr("Testo semplice (.txt)"), "text")
        self.kind.addItem(tr("PDF/A (archiviazione)"), "pdfa")
        self.kind.addItem(tr("Pagina singola come immagine"), "current")
        f.addRow(tr("Formato"), self.kind)
        self.range = QLineEdit("1")
        self.range.setToolTip(tr("Intervallo: 1-3, 5, 8-10"))
        self.range_label = QLabel(tr("Pagine"))
        f.addRow(self.range_label, self.range)
        self.dpi = QSpinBox()
        self.dpi.setRange(36, 1200)
        self.dpi.setValue(300)
        self.dpi.setSingleStep(50)
        f.addRow(tr("Risoluzione (DPI)"), self.dpi)
        self.quality = QSpinBox()
        self.quality.setRange(30, 100)
        self.quality.setValue(88)
        f.addRow(tr("Qualità JPEG"), self.quality)
        self.pdfa_level = QComboBox()
        for label, val in (("PDF/A-1b (PDF 1.4)", "1b"), ("PDF/A-2b (PDF 1.7)", "2b"), ("PDF/A-3b (PDF 1.7)", "3b")):
            self.pdfa_level.addItem(label, val)
        f.addRow(tr("Livello PDF/A"), self.pdfa_level)
        v.addLayout(f)
        self.info = QLabel("")
        self.info.setProperty("role", "hint")
        self.info.setWordWrap(True)
        v.addWidget(self.info)
        self.kind.currentIndexChanged.connect(self._update)
        self._update()
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("Esporta"))
        bb.button(QDialogButtonBox.Ok).setProperty("accent", True)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _update(self) -> None:
        k = str(self.kind.currentData())
        self.pdfa_level.setEnabled(k == "pdfa")
        self.quality.setEnabled(k in ("image", "current"))
        # in «pagina singola» il campo delle pagine resta visibile ma non
        # modificabile, e mostra la pagina corrente
        singola = k == "current"
        self.range.setEnabled(not singola)
        self.range.setText(str(self.current_page + 1) if singola else self.range.text())
        if k == "pdfa":
            self.info.setText(
                tr("La conversione in PDF/A avviene tramite Ghostscript, se installato nel sistema.\n"
                "Su Windows: installa Ghostscript. Su Linux: pacchetto «ghostscript».")
            )
        elif k == "text":
            self.info.setText(tr("Viene estratto il testo di tutte le pagine selezionate."))
        elif k == "current":
            self.info.setText(
                tr("Viene esportata la pagina {n} di {tot}.")
                    .format(n=self.current_page + 1, tot=self.page_count)
            )
        else:
            self.info.setText(tr("Il documento ha {n} pagine.").format(n=self.page_count))

    def parse_range(self) -> list[int]:
        """Trasforma «1-3, 5, 8-10» in indici di pagina (base 0).

        Un intervallo con una sola estremita' arriva all'ultima pagina: «3-» e
        «-2» sono richieste sensate, non errori. Quello che non si puo'
        accettare e' un testo che non indica nessuna pagina: senza questo
        controllo l'esportazione ripiegava sulla pagina corrente e l'utente
        riceveva un file con una pagina sola, senza avvisi.
        """
        testo = self.range.text().replace(" ", "")
        if not testo:
            raise ValueError(
                "Indica le pagine da esportare, per esempio «1-3, 5, 8-10»."
            )
        out: list[int] = []
        inesatti: list[str] = []
        for part in testo.split(","):
            if not part:
                continue
            if "-" in part:
                a, _, b = part.partition("-")
                try:
                    # senza il controllo, «abc-3» arrivava all'utente come
                    # «invalid literal for int() with base 10: 'abc'»
                    lo = int(a) if a else 1
                    hi = int(b) if b else self.page_count
                except ValueError:
                    inesatti.append(part)
                    continue
                if lo > hi:
                    lo, hi = hi, lo
                out.extend(range(lo - 1, hi))
            else:
                try:
                    out.append(int(part) - 1)
                except ValueError:
                    inesatti.append(part)
        if inesatti:
            # una voce illeggibile dentro un intervallo altrimenti valido
            # verrebbe scartata in silenzio, e l'utente riceverebbe un file con
            # meno pagine di quante ne aveva chiesto
            raise ValueError(
                f"Nell'intervallo «{testo}» la voce «{inesatti[0]}» non e' un numero."
            )
        fuori = sorted({p + 1 for p in out if not (0 <= p < self.page_count)})
        if fuori:
            # ignorare in silenzio gli indici inesistenti esporterebbe un
            # file con meno pagine di quanto chiesto, senza avvisare nessuno
            plurale = "pagine" if self.page_count != 1 else "pagina"
            if len(fuori) <= 3:
                numeri = ", ".join(str(n) for n in fuori)
                testo_errore = f"La pagina {numeri} non esiste" if len(fuori) == 1 else f"Le pagine {numeri} non esistono"
            else:
                testo_errore = f"{len(fuori)} pagine richieste non esistono"
            raise ValueError(f"{testo_errore}: il documento ha {self.page_count} {plurale}.")
        if not out:
            raise ValueError("L'intervallo non indica nessuna pagina.")
        # «1, 1» esportava due volte la stessa pagina, con due file identici
        return sorted(dict.fromkeys(out))

    def values(self) -> dict[str, Any]:
        k = str(self.kind.currentData())
        return {
            "kind": k,
            "pages": [self.current_page] if k == "current" else self.parse_range(),
            "dpi": int(self.dpi.value()),
            "quality": int(self.quality.value()),
            "pdfa": str(self.pdfa_level.currentData()),
        }


# --------------------------------------------------------------- certificato


class SignatureSetupDialog(QDialog):
    """Firma digitale: certificato, posizione e aspetto."""

    def __init__(self, doc: docmod.Document, page: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.doc = doc
        self.page = page
        self.palette = theme.corrente()
        self.setWindowTitle(tr("Firma digitale"))
        dlgutil.adatta_a_schermo(self, 560, 560)
        v = QVBoxLayout(self)
        self.status = QLabel("")
        self.status.setProperty("role", "hint")
        self.status.setWordWrap(True)
        v.addWidget(self.status)

        g = QGroupBox(tr("Certificato"))
        f = QFormLayout(g)
        self.mode = QComboBox()
        self.mode.addItem(tr("Genera un certificato personale (autofirmato)"), "self")
        self.mode.addItem(tr("Usa un certificato da file (PFX / PEM)"), "file")
        f.addRow(tr("Origine"), self.mode)
        self.path = QLineEdit()
        self.path.setPlaceholderText(tr("certificato.p12"))
        b_browse = QPushButton(tr("Sfoglia…"))
        b_browse.clicked.connect(self._browse)
        hb = QHBoxLayout()
        hb.addWidget(self.path, 1)
        hb.addWidget(b_browse)
        hw = QWidget()
        hw.setLayout(hb)
        f.addRow(tr("File"), hw)
        self.cert_pw = QLineEdit()
        self.cert_pw.setEchoMode(QLineEdit.Password)
        f.addRow(tr("Password certificato"), self.cert_pw)
        self.cn = QLineEdit()
        f.addRow(tr("Nome e cognome"), self.cn)
        self.email = QLineEdit()
        f.addRow(tr("Email"), self.email)
        self.org = QLineEdit()
        f.addRow(tr("Organizzazione"), self.org)
        self.reason = QLineEdit()
        self.reason.setPlaceholderText(tr("Motivo della firma"))
        f.addRow(tr("Motivo"), self.reason)
        self.location = QLineEdit()
        f.addRow(tr("Luogo"), self.location)
        v.addWidget(g)

        g2 = QGroupBox(tr("Aspetto"))
        f2 = QFormLayout(g2)
        self.visible = QCheckBox(tr("Mostra la firma (firma a vista)"))
        self.visible.setChecked(True)
        f2.addRow("", self.visible)
        self.reason_box = QCheckBox(tr("Mostra motivo e data"))
        self.reason_box.setChecked(True)
        f2.addRow("", self.reason_box)
        self.sign_field = QComboBox()
        for fld in doc.fields():
            if fld.type == "Signature":
                self.sign_field.addItem(f"Campo: {fld.name} (pagina {fld.page + 1})", fld.xref)
        f2.addRow(tr("Usa campo firma"), self.sign_field)
        v.addWidget(g2)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("Firma"))
        bb.button(QDialogButtonBox.Ok).setProperty("accent", True)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        # senza questa collegamento i campi «File» e «Password certificato»
        # restavano grigi anche scegliendo «Usa un certificato da file»: la
        # modalità era inutilizzabile e la firma falliva con «Seleziona un
        # file certificato» su un percorso che non si poteva scrivere
        self.mode.currentIndexChanged.connect(self._update_state)
        self._update_state()

    def _browse(self) -> None:
        f, _ = QFileDialog.getOpenFileName(
            self, "Scegli il certificato", "", "Certificati (*.p12 *.pfx *.pem *.crt);;Tutti i file (*)"
        )
        if f:
            self.path.setText(f)

    def _update_state(self) -> None:
        is_self = self.mode.currentData() == "self"
        for w in (self.cn, self.email, self.org):
            w.setEnabled(is_self)
        self.path.setEnabled(not is_self)
        self.cert_pw.setEnabled(not is_self)

    def values(self) -> dict[str, Any]:
        return {
            "mode": str(self.mode.currentData()),
            "path": self.path.text().strip(),
            "password": self.cert_pw.text(),
            "common_name": self.cn.text().strip(),
            "email": self.email.text().strip(),
            "org": self.org.text().strip(),
            "reason": self.reason.text().strip(),
            "location": self.location.text().strip(),
            "visible": self.visible.isChecked(),
            "show_reason": self.reason_box.isChecked(),
            "field_xref": self.sign_field.currentData(),
        }


# --------------------------------------------------------------- preferenze


class PreferencesDialog(QDialog):
    """Preferenze generali dell'applicazione."""

    def __init__(self, settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.palette = theme.corrente()
        self.setWindowTitle(tr("Preferenze"))
        dlgutil.adatta_a_schermo(self, 520, 520)
        v = QVBoxLayout(self)
        tabs = QTabWidget()
        v.addWidget(tabs)

        g = QWidget()
        f = QFormLayout(g)
        self.unit = QComboBox()
        for u, (long, short, _) in units.UNITS.items():
            self.unit.addItem(f"{long} ({short})", u)
        # ``max(0, …)``: con un valore sconosciuto nel file di preferenze
        # ``findData`` dà -1, ``currentData()`` diventa None e il salvataggio
        # scriveva la lettera «None» al posto dell'unita'
        self.unit.setCurrentIndex(max(0, self.unit.findData(settings.get("unit"))))
        f.addRow(tr("Unità di misura"), self.unit)
        self.zoom_mode = QComboBox()
        for label, val in (("Adatta alla larghezza", "fit_width"), ("Adatta alla pagina", "fit_page"),
                           ("Dimensione reale", "actual"), ("Personalizzato", "custom")):
            self.zoom_mode.addItem(label, val)
        self.zoom_mode.setCurrentIndex(max(0, self.zoom_mode.findData(settings.get("zoom_mode"))))
        f.addRow(tr("Zoom predefinito"), self.zoom_mode)
        self.grid = QCheckBox(tr("Mostra la griglia"))
        self.grid.setChecked(bool(settings.get("grid_visible")))
        f.addRow("", self.grid)
        self.grid_size = QSpinBox()
        self.grid_size.setRange(4, 200)
        self.grid_size.setValue(int(settings.get("grid_size")))
        f.addRow(tr("Passo griglia (pt)"), self.grid_size)
        self.snap = QCheckBox(tr(" magnetismo attivo"))
        self.snap.setChecked(bool(settings.get("snap_enabled")))
        f.addRow("", self.snap)
        self.fields_hl = QCheckBox(tr("Evidenzia i campi dei moduli"))
        self.fields_hl.setChecked(bool(settings.get("highlight_fields")))
        f.addRow("", self.fields_hl)
        self.language = QComboBox()
        # «auto» viene per primo perché è il default: se non si sceglie nulla la
        # lingua è quella del sistema, e la scelta si vede come tale invece di
        # sembrare una lingua fissata che si cambia dimenticandola.
        for codice, nome in i18n.LINGUE:
            self.language.addItem(_nome_lingua(codice, nome), codice)
        scelta = str(settings.get("ui_language") or "auto")
        self.language.setCurrentIndex(max(0, self.language.findData(scelta)))
        self.language.setToolTip(
            tr("La lingua si applica subito alle finestre che verranno aperte. "
            "Menu e pannelli già aperti restano nella lingua precedente fino "
            "alla prossima apertura del programma.")
        )
        f.addRow(tr("Lingua dell'interfaccia"), self.language)
        tabs.addTab(g, tr("Generali"))

        g2 = QWidget()
        f2 = QFormLayout(g2)
        self.autosave = QCheckBox(tr("Salvataggio automatico"))
        self.autosave.setChecked(bool(settings.get("autosave")))
        f2.addRow("", self.autosave)
        self.autosave_min = QSpinBox()
        self.autosave_min.setRange(1, 120)
        self.autosave_min.setValue(int(settings.get("autosave_minutes")))
        self.autosave_min.setSuffix(" minuti")
        f2.addRow(tr("Ogni"), self.autosave_min)
        self.recover = QCheckBox(tr("Recupera i documenti non chiusi correttamente"))
        self.recover.setChecked(bool(settings.get("recover")))
        f2.addRow("", self.recover)
        self.confirm = QCheckBox(tr("Chiedi conferma per le operazioni distruttive"))
        self.confirm.setChecked(bool(settings.get("confirm_destructive")))
        f2.addRow("", self.confirm)
        tabs.addTab(g2, tr("Salvataggio"))

        g3 = QWidget()
        f3 = QFormLayout(g3)
        self.ocr_lang = QComboBox()
        for code, label in (("ita", "Italiano"), ("eng", "Inglese"), ("fra", "Francese"),
                            ("deu", "Tedesco"), ("spa", "Spagnolo"), ("osd", "Solo direzioni")):
            self.ocr_lang.addItem(label, code)
        self.ocr_lang.setCurrentIndex(max(0, self.ocr_lang.findData(settings.get("ocr_language"))))
        f3.addRow(tr("Lingua OCR"), self.ocr_lang)
        self.ocr_dpi = QSpinBox()
        self.ocr_dpi.setRange(150, 600)
        self.ocr_dpi.setValue(int(settings.get("ocr_dpi")))
        self.ocr_dpi.setSingleStep(50)
        f3.addRow(tr("Risoluzione OCR"), self.ocr_dpi)
        self.print_dpi = QSpinBox()
        self.print_dpi.setRange(72, 1200)
        self.print_dpi.setValue(int(settings.get("print_dpi")))
        self.print_dpi.setSingleStep(50)
        f3.addRow(tr("Risoluzione stampa"), self.print_dpi)
        self.theme = QComboBox()
        for label, val in (("Chiaro", "chiaro"), ("Scuro", "scuro")):
            self.theme.addItem(label, val)
        self.theme.setCurrentIndex(max(0, self.theme.findData(settings.get("theme"))))
        f3.addRow(tr("Tema"), self.theme)
        tabs.addTab(g3, tr("Avanzate"))

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("Salva"))
        bb.button(QDialogButtonBox.Ok).setProperty("accent", True)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def values(self) -> dict[str, Any]:
        return {
            "unit": str(self.unit.currentData()),
            "zoom_mode": str(self.zoom_mode.currentData()),
            "grid_visible": self.grid.isChecked(),
            "grid_size": float(self.grid_size.value()),
            "snap_enabled": self.snap.isChecked(),
            "highlight_fields": self.fields_hl.isChecked(),
            "ui_language": str(self.language.currentData()),
            "autosave": self.autosave.isChecked(),
            "autosave_minutes": int(self.autosave_min.value()),
            "recover": self.recover.isChecked(),
            "confirm_destructive": self.confirm.isChecked(),
            "ocr_language": str(self.ocr_lang.currentData()),
            "ocr_dpi": int(self.ocr_dpi.value()),
            "print_dpi": int(self.print_dpi.value()),
            "theme": str(self.theme.currentData()),
        }


class LanguageDialog(QDialog):
    """Sceglie la lingua dell'interfaccia.

    Sta in una finestra sua e non nelle Preferenze perché cambiare lingua è
    una cosa che si fa una volta sola, mentre Preferenze si apre e si richiude
    di continuo: metterla lì la nasconderebbe. Nelle Preferenze c'è comunque,
    per chi le cerca lì.
    """

    def __init__(self, lingue: tuple[tuple[str, str], ...], corrente: str, parent=None) -> None:
        super().__init__(parent)
        self.palette = theme.corrente()
        self.setWindowTitle(tr("Lingua dell'interfaccia"))
        dlgutil.adatta_a_schermo(self, 460, 260)
        v = QVBoxLayout(self)

        self.lingua = QComboBox()
        for codice, nome in lingue:
            self.lingua.addItem(_nome_lingua(codice, nome), codice)
        scelta = corrente if (corrente or "") in dict(lingue) else "auto"
        self.lingua.setCurrentIndex(max(0, self.lingua.findData(scelta)))
        v.addWidget(self.lingua)

        nota = QLabel(
            tr("«Sistema» segue la lingua del computer e cambia da sola se cambi "
            "le impostazioni regionali. Scegliendo una lingua precisa, il "
            "programma continua a usarla anche se il computer passa a un'altra.")
        )
        nota.setWordWrap(True)
        nota.setStyleSheet("color: #6b7280;")
        v.addWidget(nota)

        avviso = QLabel(
            tr("Il cambio si vede subito sui menu. Le finestre già aperte e quelle "
            "che verranno aperte torneranno nuove al prossimo avvio del programma.")
        )
        avviso.setWordWrap(True)
        v.addWidget(avviso)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("Applica"))
        bb.button(QDialogButtonBox.Ok).setProperty("accent", True)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def language(self) -> str:
        return str(self.lingua.currentData())


class ImagePropertiesDialog(QDialog):
    """Dimensione e ritaglio di un'immagine gia' presente nella pagina.

    Le immagini non sono annotazioni e non hanno una finestra di proprieta'
    come tutte le altre, quindi la voce «Proprietà immagine» non poteva che
    scrivere un messaggio. Qui si sceglie la nuova dimensione, in punti, e se
    tagliare la parte che esce dai bordi della pagina.
    """

    def __init__(
        self,
        current: tuple[float, float],
        page_size: tuple[float, float],
        parent: QWidget | None = None,
        posizione: tuple[float, float] = (0.0, 0.0),
    ) -> None:
        super().__init__(parent)
        self.palette = theme.corrente()
        self.setWindowTitle(tr("Proprietà immagine"))
        dlgutil.adatta_a_schermo(self, 430, 300)
        self._pagina = (float(page_size[0]), float(page_size[1]))
        self._rapporto = (float(current[0]) / float(current[1])) if current[1] else 1.0
        self._bloccato = False
        # angolo in cui l'immagine si trova: la finestra cambia la dimensione,
        # non la posizione
        self.posizione = (float(posizione[0]), float(posizione[1]))
        v = QVBoxLayout(self)
        self.hint = QLabel("")
        self.hint.setProperty("role", "hint")
        self.hint.setWordWrap(True)
        v.addWidget(self.hint)

        f = QFormLayout()
        self.w = QDoubleSpinBox()
        self.w.setRange(4.0, 20000.0)
        self.w.setDecimals(1)
        self.w.setSuffix(" pt")
        self.w.setValue(float(current[0]))
        f.addRow(tr("Larghezza"), self.w)
        self.h = QDoubleSpinBox()
        self.h.setRange(4.0, 20000.0)
        self.h.setDecimals(1)
        self.h.setSuffix(" pt")
        self.h.setValue(float(current[1]))
        f.addRow(tr("Altezza"), self.h)
        v.addLayout(f)

        self.proporzioni = QCheckBox(tr("Mantieni le proporzioni"))
        self.proporzioni.setChecked(True)
        self.proporzioni.setToolTip(tr("Cambiando una misura si adegua anche l'altra"))
        v.addWidget(self.proporzioni)
        self.crop = QCheckBox(tr("Ritaglia alla pagina"))
        self.crop.setToolTip(tr("Taglia la parte di immagine che esce dai bordi della pagina"))
        v.addWidget(self.crop)

        self.w.valueChanged.connect(self._allineata)
        self.h.valueChanged.connect(self._allineata)
        self._sync_hint()

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("Applica"))
        bb.button(QDialogButtonBox.Ok).setProperty("accent", True)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _allineata(self, valore: float) -> None:
        """Adegua l'altra misura quando le proporzioni vanno mantenute."""
        if self._bloccato:
            return
        if not self.proporzioni.isChecked():
            # senza proporzioni l'utente sta cambiando una misura per volta:
            # l'avviso sulla pagina va comunque aggiornato
            self._sync_hint()
            return
        self._bloccato = True
        try:
            if self.sender() is self.w:
                self.h.setValue(max(4.0, self.w.value() / max(self._rapporto, 0.01)))
            else:
                self.w.setValue(max(4.0, self.h.value() * self._rapporto))
        finally:
            self._bloccato = False
        self._sync_hint()

    def _sync_hint(self) -> None:
        larghezza, altezza = self._pagina
        w, h = self.w.value(), self.h.value()
        if w > larghezza or h > altezza:
            self.hint.setText(
                tr("L'immagine supera la pagina ({larghezza} x {altezza} pt): "
                   "riducila o usa il ritaglio.")
                .format(larghezza=f"{larghezza:.0f}", altezza=f"{altezza:.0f}")
            )
            self.hint.setProperty("role", "warning")
        else:
            testo = (
                tr("Dimensione {larghezza} x {altezza} pt su una pagina di "
                   "{pagina_larghezza} x {pagina_altezza} pt.")
                .format(
                    larghezza=f"{w:.0f}",
                    altezza=f"{h:.0f}",
                    pagina_larghezza=f"{larghezza:.0f}",
                    pagina_altezza=f"{altezza:.0f}",
                )
            )
            if self.proporzioni.isChecked():
                testo += tr(" Le proporzioni restano quelle attuali.")
            self.hint.setText(testo)
            self.hint.setProperty("role", "hint")
        self.hint.style().unpolish(self.hint)
        self.hint.style().polish(self.hint)

    def values(self) -> dict[str, Any]:
        """Dimensione nuova, posizione invariata e ritaglio.

        Il riquadro conserva l'angolo attuale: la finestra parla di dimensione,
        non di spostamento, e reinserire l'immagine nell'angolo alto sinistro
        la spostava di colpo al bordo della pagina ogni volta che si cambiava
        solo la dimensione.
        """
        w, h = self.w.value(), self.h.value()
        x0, y0 = self.posizione
        return {
            "rect": (x0, y0, x0 + w, y0 + h),
            "crop": self.crop.isChecked(),
        }


class XmpDialog(QDialog):
    """Metadati XMP grezzi."""

    def __init__(self, xml: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.palette = theme.corrente()
        self.setWindowTitle(tr("Metadati XMP"))
        dlgutil.adatta_a_schermo(self, 640, 520)
        v = QVBoxLayout(self)
        v.addWidget(QLabel(tr("Metadati XMP del documento (XML)")))
        self.text = QPlainTextEdit()
        self.text.setPlainText(xml)
        v.addWidget(self.text, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("Applica"))
        bb.button(QDialogButtonBox.Ok).setProperty("accent", True)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def xml(self) -> str:
        return self.text.toPlainText()


def _hex(c: tuple[float, float, float]) -> str:
    r, g, b = (int(round(max(0.0, min(1.0, x)) * 255)) for x in c[:3])
    return f"#{r:02x}{g:02x}{b:02x}"
