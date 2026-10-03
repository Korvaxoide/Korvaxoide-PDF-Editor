"""Pannello di rimozione dello sfondo con anteprima immediata."""

from __future__ import annotations

import time
from typing import Any

import numpy as np
from PIL import Image
from PySide6.QtCore import QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...signature import bgremove
from .. import theme
from ...core.i18n import tr
from ..page_items import pil_to_qpixmap

def methods() -> tuple[tuple[str, str], ...]:
    """Le tecniche di rimozione, con l'etichetta tradotta.

    Una funzione e non una costante: le etichette sono parole chiave e in una
    costante di modulo la lingua resterebbe quella del primo import.
    """
    return (
        ("white", tr("Soglia sui canali (carta bianca)")),
        ("luminance", tr("Soglia sulla luminosità")),
        ("color", tr("Chroma key (colore campionato)")),
        ("flood", tr("Magic wand (dal punto indicato)")),
        ("border", tr("Rimuovi cornice del foglio")),
        ("none", tr("Nessuna ( mantieni tutto)")),
    )


class BackgroundRemovalPanel(QWidget):
    """Impostazioni di rimozione dello sfondo con anteprima live.

    Ogni modifica ai parametri ricalcola l'anteprima in modo differito, cosi'
    l'utente vede subito l'effetto prima di confermare.
    """

    changed = Signal(object)          # RemovalSettings
    accepted = Signal(object)         # RemovalSettings confermati

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.palette = theme.corrente()
        self.source: Image.Image | None = None
        self._key_color = QColor(255, 255, 255)
        self.result: Image.Image | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(140)
        self._timer.timeout.connect(self._recompute)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # anteprima
        self.preview = _Preview(self)
        self.preview.setMinimumHeight(190)
        self.preview.sample_clicked.connect(self._on_sample)
        root.addWidget(self.preview, 1)

        # metodo
        g1 = QGroupBox(tr("Tecnica"))
        v1 = QVBoxLayout(g1)
        self.method = QComboBox()
        for key, label in methods():
            self.method.addItem(label, key)
        self.method.currentIndexChanged.connect(self._schedule)
        v1.addWidget(self.method)
        self.hint = QLabel("")
        self.hint.setProperty("role", "hint")
        self.hint.setWordWrap(True)
        v1.addWidget(self.hint)
        root.addWidget(g1)

        # parametri
        g2 = QGroupBox(tr("Regolazione"))
        grid = QGridLayout(g2)
        self.slider_thr = _Slider(0, 255, 34)
        self.slider_soft = _Slider(0, 40, 6)
        self.slider_tol = _Slider(0, 200, 42)
        self.slider_feather = _Slider(0, 12, 2)
        self.slider_despeckle = _Slider(0, 200, 0)
        for wdg in (self.slider_thr, self.slider_soft, self.slider_tol, self.slider_feather, self.slider_despeckle):
            wdg.valueChanged.connect(self._schedule)
        grid.addWidget(self._labelled("Soglia", self.slider_thr), 0, 0)
        grid.addWidget(self._labelled("Morbidezza bordo", self.slider_soft), 0, 1)
        grid.addWidget(self._labelled("Tolleranza wand", self.slider_tol), 1, 0)
        grid.addWidget(self._labelled("Sfocatura bordo", self.slider_feather), 1, 1)
        grid.addWidget(self._labelled("Rimuovi macchie", self.slider_despeckle), 2, 0, 1, 2)
        root.addWidget(g2)

        # colore campionato
        g3 = QGroupBox(tr("Colore di sfondo"))
        h3 = QHBoxLayout(g3)
        self.key_color = QPushButton(tr(" campiona "))
        self.key_color.setToolTip(tr("Scegli il colore dello sfondo da rimuovere"))
        self.key_color.clicked.connect(self._pick_color)
        h3.addWidget(QLabel(tr("Colore:")))
        h3.addWidget(self.key_color)
        self.auto_btn = QPushButton(tr("Rileva automaticamente"))
        self.auto_btn.clicked.connect(self._auto)
        h3.addWidget(self.auto_btn)
        h3.addStretch(1)
        root.addWidget(g3)

        # opzioni
        opts = QHBoxLayout()
        self.keep_color = QCheckBox(tr("Mantieni il colore della penna"))
        self.keep_color.setChecked(True)
        self.auto_crop = QCheckBox(tr("Ritaglia automaticamente"))
        self.auto_crop.setChecked(True)
        self.show_checker = QCheckBox(tr("Mostra trasparenza"))
        self.show_checker.setChecked(True)
        for wdg in (self.keep_color, self.auto_crop, self.show_checker):
            wdg.toggled.connect(self._schedule)
        opts.addWidget(self.keep_color)
        opts.addWidget(self.auto_crop)
        opts.addWidget(self.show_checker)
        opts.addStretch(1)
        root.addLayout(opts)

        row = QHBoxLayout()
        self.stats = QLabel("")
        self.stats.setProperty("role", "hint")
        row.addWidget(self.stats, 1)
        b_reset = QPushButton(tr("Reimposta"))
        b_reset.clicked.connect(self._reset)
        b_ok = QPushButton(tr("Applica"))
        b_ok.setProperty("accent", True)
        b_ok.clicked.connect(self._accept)
        row.addWidget(b_reset)
        row.addWidget(b_ok)
        root.addLayout(row)

    def _labelled(self, text: str, wdg: QWidget) -> QWidget:
        box = QVBoxLayout()
        w = QWidget()
        lab = QLabel(text)
        lab.setProperty("role", "hint")
        box.addWidget(lab)
        box.addWidget(wdg)
        w.setLayout(box)
        return w

    # ------------------------------------------------------------------ dati

    def set_image(self, image: Image.Image) -> None:
        self.source = image.convert("RGBA")
        self._auto_settings()
        self._recompute()

    def settings(self) -> bgremove.RemovalSettings:
        key = self._key_color
        return bgremove.RemovalSettings(
            method=str(self.method.currentData()),
            threshold=self.slider_thr.value(),
            tolerance=self.slider_tol.value(),
            key_color=(key.red(), key.green(), key.blue(), 255),
            seed=self.preview.seed,
            feather=self.slider_feather.value(),
            softness=self.slider_soft.value(),
            despeckle=self.slider_despeckle.value(),
            keep_color=self.keep_color.isChecked(),
            auto_crop=self.auto_crop.isChecked(),
        )

    def set_settings(self, st: bgremove.RemovalSettings) -> None:
        i = self.method.findData(st.method)
        if i >= 0:
            self.method.setCurrentIndex(i)
        self.slider_thr.setValue(st.threshold)
        self.slider_soft.setValue(st.softness)
        self.slider_tol.setValue(st.tolerance)
        self.slider_feather.setValue(st.feather)
        self.slider_despeckle.setValue(st.despeckle)
        self.keep_color.setChecked(st.keep_color)
        self.auto_crop.setChecked(st.auto_crop)
        self._set_key_color(st.key_color)
        if st.seed:
            self.preview.seed = st.seed
        self._schedule()

    def _auto_settings(self) -> None:
        if self.source is None:
            return
        guess = bgremove.suggest_method(self.source)
        i = self.method.findData(guess.method)
        if i >= 0:
            self.method.setCurrentIndex(i)
        self.slider_thr.setValue(guess.threshold)
        self.slider_tol.setValue(guess.tolerance)
        # il punto di partenza suggerito faceva parte della proposta e veniva
        # buttato: la bacchetta magica ripartiva dal proprio default
        if guess.seed is not None:
            self.preview.seed = tuple(guess.seed)
        med = _median_border_color(self.source)
        self._set_key_color(med)
        self._update_hint()

    def _auto(self) -> None:
        self._auto_settings()
        self._schedule()

    def key_color_value(self) -> QColor:
        return QColor(self._key_color)

    def _set_key_color(self, rgba: tuple[int, int, int, int]) -> None:
        c = QColor(rgba[0], rgba[1], rgba[2])
        self._key_color = c
        self.key_color.setStyleSheet(
            f"background: {c.name()}; border: 1px solid {self.palette.border_strong};"
        )

    def _pick_color(self) -> None:
        from PySide6.QtWidgets import QColorDialog

        c = QColorDialog.getColor(self._key_color, self, "Scegli il colore dello sfondo")
        if c.isValid():
            self._set_key_color((c.red(), c.green(), c.blue(), 255))
            if str(self.method.currentData()) != "color":
                self.method.setCurrentIndex(self.method.findData("color"))
            self._schedule()

    def _on_sample(self, x: int, y: int) -> None:
        self.preview.seed = (x, y)
        if str(self.method.currentData()) != "flood":
            self.method.setCurrentIndex(self.method.findData("flood"))
        self._schedule()

    # ------------------------------------------------------------- anteprima

    def _schedule(self) -> None:
        self._update_hint()
        self._timer.start()

    def _recompute(self) -> None:
        if self.source is None:
            self.result = None
            self.preview.set_images(None, None)
            return
        st = self.settings()
        t0 = time.perf_counter()
        try:
            self.result = bgremove.remove_background(self.source, st)
        except Exception as exc:
            self.stats.setText(f"Errore: {exc}")
            return
        dt = (time.perf_counter() - t0) * 1000
        self.preview.set_images(self.source, self.result, checker=self.show_checker.isChecked())
        if self.result is not None:
            a = np.asarray(self.result)[:, :, 3]
            cover = float((a > 128).mean()) * 100
            self.stats.setText(
                f"{self.result.width}×{self.result.height} px — contenuto {cover:.0f}% — {dt:.0f} ms"
            )
        self.changed.emit(st)

    def _update_hint(self) -> None:
        m = str(self.method.currentData())
        hints = {
            "white": "Adatta a foto e scansioni su carta bianca o chiara.",
            "luminance": "Adatta a sfondi chiari di qualsiasi tinta.",
            "color": "Scegli o campiona il colore dello sfondo: adatto a cartoncini colorati.",
            "flood": "Fai clic sull'immagine sul punto da cui partire (tipicamente l'angolo).",
            "border": "Rimuove la cornice continua attorno al foglio.",
            "none": "L'immagine viene usata così com'è.",
        }
        self.hint.setText(hints.get(m, ""))
        method = m
        for wdg in (self.slider_thr, self.slider_soft, self.slider_tol, self.slider_feather, self.slider_despeckle):
            wdg.setEnabled(method not in ("none",))

    def _reset(self) -> None:
        self.slider_thr.setValue(34)
        self.slider_soft.setValue(6)
        self.slider_tol.setValue(42)
        self.slider_feather.setValue(2)
        self.slider_despeckle.setValue(0)
        self.keep_color.setChecked(True)
        self.auto_crop.setChecked(True)
        self.method.setCurrentIndex(0)
        # anche il punto campionato e il colore dello sfondo: tornare al
        # «Magic wand» o al «Chroma key» dopo un reimpostazione riusava la
        # scelta che si era appena dichiarato di annullare
        self.preview.seed = None
        self._set_key_color(_median_border_color(self.source) if self.source else (255, 255, 255, 255))
        self._schedule()

    def _accept(self) -> None:
        # il risultato visibile puo' risalire a 140 ms prima: le impostazioni
        # confermate vengono ricalcolate subito, cosi' l'immagine che verrà
        # inserita corrisponde a quello che l'utente vede
        self._timer.stop()
        self._recompute()
        self.accepted.emit(self.settings())


class _Slider(QWidget):
    """Cursore con etichetta del valore corrente."""

    valueChanged = Signal(int)

    def __init__(self, lo: int, hi: int, value: int) -> None:
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(lo, hi)
        self.slider.setValue(value)
        self.spin = QSpinBox()
        self.spin.setRange(lo, hi)
        self.spin.setValue(value)
        self.spin.setFixedWidth(58)
        self.slider.valueChanged.connect(self._on_slider)
        self.spin.valueChanged.connect(self._on_spin)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.spin)

    def _on_slider(self, v: int) -> None:
        self.spin.blockSignals(True)
        self.spin.setValue(v)
        self.spin.blockSignals(False)
        self.valueChanged.emit(v)

    def _on_spin(self, v: int) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(v)
        self.slider.blockSignals(False)
        self.valueChanged.emit(v)

    def value(self) -> int:
        return self.slider.value()

    def setValue(self, v: int) -> None:  # noqa: N802 (API Qt)
        self.slider.blockSignals(True)
        self.spin.blockSignals(True)
        self.slider.setValue(int(v))
        self.spin.setValue(int(v))
        self.slider.blockSignals(False)
        self.spin.blockSignals(False)


class _Preview(QWidget):
    """Anteprima affiancata dell'originale e del risultato."""

    sample_clicked = Signal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.original: Image.Image | None = None
        self.result: Image.Image | None = None
        self.checker = True
        self.seed: tuple[int, int] | None = None
        self.setMinimumHeight(180)
        self.setMouseTracking(True)

    def set_images(
        self, original: Image.Image | None, result: Image.Image | None, checker: bool = True
    ) -> None:
        self.original = original
        self.result = result
        self.checker = checker
        self.update()

    def sizeHint(self) -> QSize:  # type: ignore[override]
        return QSize(420, 220)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), QColor("#eef0f3"))
        if self.original is None:
            p.setPen(QColor("#9aa2b1"))
            p.drawText(self.rect(), int(Qt.AlignCenter), "Nessuna immagine")
            p.end()
            return
        gap = 8
        half = max(1, (self.width() - gap) // 2)
        self._draw_one(p, self.original, QRect(0, 0, half, self.height() - 20), "Originale", checker=False)
        if self.result is not None:
            self._draw_one(
                p, self.result, QRect(half + gap, 0, half, self.height() - 20), "Senza sfondo", checker=self.checker
            )
        p.end()

    def _draw_one(self, p: QPainter, img: Image.Image, rect: QRect, title: str, checker: bool) -> None:
        if img is None:
            return
        avail_w, avail_h = max(1, rect.width() - 8), max(1, rect.height() - 24)
        scale = min(avail_w / img.width, avail_h / img.height, 3.0)
        w, h = max(1, int(img.width * scale)), max(1, int(img.height * scale))
        base = bgremove.preview_on_checker(img) if checker else img.convert("RGB")
        pm = pil_to_qpixmap(base.convert('RGBA')).scaled(
            w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        x = rect.x() + (rect.width() - w) // 2
        y = rect.y() + 20
        p.fillRect(rect, QColor("#ffffff"))
        p.setPen(QColor("#b6bcc7"))
        p.drawRect(rect.x(), y, rect.width(), h)
        p.drawPixmap(x, y, pm)
        p.setPen(QColor("#5b6472"))
        f = p.font()
        f.setPointSize(8)
        p.setFont(f)
        p.drawText(rect.x() + 2, rect.y() + 13, title)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if self.original is None or event.button() != Qt.LeftButton:
            return
        gap = 8
        half = max(1, (self.width() - gap) // 2)
        x = event.position().x()
        if x > half + gap:
            return
        rect = QRect(0, 0, half, self.height() - 20)
        avail_w, avail_h = max(1, rect.width() - 8), max(1, rect.height() - 24)
        scale = min(avail_w / self.original.width, avail_h / self.original.height, 3.0)
        w, h = self.original.width * scale, self.original.height * scale
        ox = rect.x() + (rect.width() - w) / 2
        oy = rect.y() + 20
        px = int((event.position().x() - ox) / max(scale, 1e-6))
        py = int((event.position().y() - oy) / max(scale, 1e-6))
        if 0 <= px < self.original.width and 0 <= py < self.original.height:
            self.sample_clicked.emit(px, py)


def _median_border_color(img: Image.Image) -> tuple[int, int, int, int]:
    a = np.asarray(img.convert("RGB"), dtype=np.uint8)
    border = np.concatenate([a[0, :, :], a[-1, :, :], a[:, 0, :], a[:, -1, :]])
    med = np.median(border, axis=0).astype(int)
    return (int(med[0]), int(med[1]), int(med[2]), 255)
