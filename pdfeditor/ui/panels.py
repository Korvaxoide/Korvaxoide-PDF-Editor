"""Pannelli laterali: ricerca, segnalibri, campi, allegati, commenti, proprietà."""

from __future__ import annotations

import datetime as _dt
from typing import Any

import pymupdf
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core import document as docmod
from ..core import i18n
from ..core import units
from ..core.i18n import tr
from ..features import quality
from . import icons, theme

# Le etichette dei tipi di campo sono funzioni e non dizionari di modulo:
# in un dizionario la lingua resterebbe quella del primo import, che non è
# necessariamente quella scelta poi dall'utente.


def kind_labels() -> dict[str, str]:
    """Il tipo di campo per esteso, per la descrizione estesa."""
    return {
        "text": tr("Campo di testo"),
        "toggle": tr("Casella / pulsante di opzione"),
        "choice": tr("Elenco / menu"),
        "button": tr("Pulsante"),
        "signature": tr("Firma"),
    }


# etichette brevi per la tabella: la colonna Tipo e' stretta e non deve rubare
# spazio al nome del campo
def kind_labels_short() -> dict[str, str]:
    """Il tipo di campo abbreviato, per la colonna stretta della tabella."""
    return {
        "text": tr("Testo"),
        "toggle": tr("Casella"),
        "choice": tr("Elenco"),
        "button": tr("Pulsante"),
        "signature": tr("Firma"),
    }


def _hsep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setFrameShadow(QFrame.Sunken)
    return f


#: I nomi delle schede del pannello laterale, nell'ordine in cui compaiono.
#: Stanno qui e non dentro la finestra perche' sono chiavi di traduzione: il
#: controllo sul catalogo deve poterle trovare senza sapere com'e' fatta la
#: finestra, e senza questo finirebbero fuori dal catalogo senza accorgersene.
NOMI_SCHEDE: tuple[str, ...] = (
    "Ricerca",
    "Campi",
    "Segnalibri",
    "Commenti",
    "Allegati",
    "Proprietà",
    "Qualità",
)


def _etichette_metadati() -> tuple[str, ...]:
    """Le intestazioni del riquadro proprietà, nell'ordine di `PropertiesPanel.FIELDS`."""
    return (
        tr("Titolo"),
        tr("Autore"),
        tr("Oggetto"),
        tr("Parole chiave"),
        tr("Applicazione"),
        tr("Produttore"),
    )


def _conta(n: int, italiano: tuple[str, str], inglese: tuple[str, str]) -> str:
    """«1 errore», «3 errori»: il numero con il nome contato.

    Le due coppie servono perche' il nome singolare e plurale cambia da una
    lingua all'altra, mentre il numero no.
    """
    singolare, plurale = inglese if i18n.lingua() == "en" else italiano
    return f"{n} {singolare if n == 1 else plurale}"


# ---------------------------------------------------------------- ricerca


class SearchPanel(QWidget):
    """Ricerca e sostituzione del testo con l'elenco dei risultati."""

    navigate = Signal(int, object)      # pagina, rect
    replace_all = Signal(str, str, bool, bool)
    replace_one = Signal(str, str, bool, bool)
    highlight_all = Signal(str, bool, bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.palette = theme.corrente()
        self.hits: list[dict[str, Any]] = []
        self.current = -1

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        self.find = QLineEdit()
        self.find.setPlaceholderText(tr("Cerca nel documento"))
        self.find.returnPressed.connect(self.search)
        root.addWidget(self.find)

        self.replace = QLineEdit()
        self.replace.setPlaceholderText(tr("Sostituisci con"))
        root.addWidget(self.replace)

        opts = QHBoxLayout()
        self.case = QCheckBox(tr("Maiuscole"))
        self.whole = QCheckBox(tr("Parola intera"))
        opts.addWidget(self.case)
        opts.addWidget(self.whole)
        opts.addStretch(1)
        root.addLayout(opts)

        row = QHBoxLayout()
        self.btn_prev = QPushButton(tr("Precedente"))
        self.btn_next = QPushButton(tr("Successivo"))
        self.btn_prev.clicked.connect(lambda: self.step(-1))
        self.btn_next.clicked.connect(lambda: self.step(1))
        row.addWidget(self.btn_prev)
        row.addWidget(self.btn_next)
        root.addLayout(row)

        row2 = QHBoxLayout()
        b_rep = QPushButton(tr("Sostituisci"))
        b_rep.clicked.connect(self._replace_one)
        b_all = QPushButton(tr("Sostituisci tutto"))
        b_all.clicked.connect(self._replace_all)
        b_hl = QPushButton(tr("Evidenzia tutto"))
        b_hl.clicked.connect(self._highlight)
        row2.addWidget(b_rep)
        row2.addWidget(b_all)
        row2.addWidget(b_hl)
        root.addLayout(row2)

        self.info = QLabel("")
        self.info.setProperty("role", "hint")
        root.addWidget(self.info)

        self.results = QListWidget()
        self.results.itemClicked.connect(self._on_result)
        root.addWidget(self.results, 1)


    def set_palette_colors(self, pal: theme.Palette) -> None:
        """Adotta il pannello al tema: senza, resta sul colore precedente."""
        self.palette = pal
        self.update()

    def search(self, doc: docmod.Document | None = None) -> list[dict[str, Any]]:
        """Esegue la ricerca e popola l'elenco dei risultati."""
        if doc is None or not doc.is_open:
            self.hits = []
            self.results.clear()
            return []
        self.hits = doc.search(self.find.text(), case=self.case.isChecked(), whole_word=self.whole.isChecked())
        self.results.clear()
        self.current = -1
        for i, h in enumerate(self.hits):
            it = QListWidgetItem(f"Pagina {h['page'] + 1}")
            it.setData(Qt.UserRole, i)
            it.setToolTip(self._snippet(doc, h))
            self.results.addItem(it)
        self._update_info()
        if self.hits:
            self.step(1)
        return self.hits

    def _snippet(self, doc: docmod.Document, hit: dict[str, Any]) -> str:
        try:
            band = hit["rect"] + (-30, -4, 30, 4)
            text = doc.page(hit["page"]).get_text("text", clip=band).strip().replace("\n", " ")
        except Exception:
            text = ""
        return f"Pagina {hit['page'] + 1}: {text[:90]}"

    def _update_info(self) -> None:
        if not self.hits:
            self.info.setText(tr("Nessun risultato") if self.find.text() else "")
        else:
            self.info.setText(tr("{n} risultati").format(n=len(self.hits)))

    def step(self, delta: int) -> None:
        if not self.hits:
            return
        self.current = (self.current + delta) % len(self.hits)
        self.results.setCurrentRow(self.current)
        self.results.scrollToItem(self.results.item(self.current))
        h = self.hits[self.current]
        self.info.setText(
            tr("{n} di {tot} — pagina {pagina}").format(
                n=self.current + 1, tot=len(self.hits), pagina=h["page"] + 1
            )
        )
        self.navigate.emit(h["page"], h["rect"])

    def current_hit(self) -> dict[str, Any] | None:
        if 0 <= self.current < len(self.hits):
            return self.hits[self.current]
        return None

    def _on_result(self, item: QListWidgetItem) -> None:
        self.current = item.row()
        h = self.hits[self.current]
        self.navigate.emit(h["page"], h["rect"])

    def _replace_one(self) -> None:
        self.replace_one.emit(self.find.text(), self.replace.text(), self.case.isChecked(), self.whole.isChecked())

    def _replace_all(self) -> None:
        self.replace_all.emit(self.find.text(), self.replace.text(), self.case.isChecked(), self.whole.isChecked())

    def _highlight(self) -> None:
        self.highlight_all.emit(self.find.text(), self.case.isChecked(), self.whole.isChecked())


# ------------------------------------------------------------- segnalibri


class BookmarksPanel(QWidget):
    """Elenco dei segnalibri con navigazione e modifica."""

    navigate = Signal(int)
    changed = Signal()
    add_requested = Signal(int)
    #: indice del segnalibro da togliere: il titolo non basta quando due
    #: segnalibili hanno lo stesso nome o quando uno e' annidato
    remove_requested = Signal(int)
    #: indice nell'elenco dei segnalibri e nuovo titolo
    rename_requested = Signal(int, str)
    #: indice del segnalibro da portare sulla pagina mostrata
    move_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(True)
        self.tree.itemDoubleClicked.connect(self._go)
        self.tree.itemChanged.connect(self._renamed)
        root.addWidget(self.tree, 1)
        row = QHBoxLayout()
        b_add = QPushButton(tr("Aggiungi"))
        b_add.clicked.connect(lambda: self.add_requested.emit(-1))
        b_del = QPushButton(tr("Elimina"))
        b_del.clicked.connect(self._remove)
        b_move = QPushButton(tr("Porta qui"))
        b_move.setToolTip(tr("Sposta il segnalibro sulla pagina mostrata"))
        b_move.clicked.connect(self._move)
        row.addWidget(b_add)
        row.addWidget(b_move)
        row.addWidget(b_del)
        root.addLayout(row)
        self._loading = False


    def set_palette_colors(self, pal: theme.Palette) -> None:
        """Adotta il pannello al tema: senza, resta sul colore precedente."""
        self.palette = pal
        self.update()

    def load(self, doc: docmod.Document | None) -> None:
        self._loading = True
        self.tree.clear()
        if doc is not None and doc.is_open:
            entries = doc.outline()
            parents: dict[int, QTreeWidgetItem] = {}
            for posizione, e in enumerate(entries):
                item = QTreeWidgetItem([e["title"]])
                item.setData(0, Qt.UserRole, e["page"])
                # la posizione nell'elenco identifica il segnalibro anche quando
                # due titoli coincidono
                item.setData(0, Qt.UserRole + 1, posizione)
                item.setFlags(item.flags() | Qt.ItemIsEditable)
                lvl = max(1, int(e.get("level", 1)))
                parent = parents.get(lvl - 1)
                if parent is not None:
                    parent.addChild(item)
                else:
                    self.tree.addTopLevelItem(item)
                # La pulizia va fatta PRIMA di registrare la voce: mettendola
                # prima si cancellava da sola, perché il ciclo successivo
                # eliminava anche la chiave appena inserita. Il risultato era un
                # elenco piatto, con l'outline del documento perso tutto.
                for k in [k for k in parents if k >= lvl]:
                    parents.pop(k, None)
                parents[lvl] = item
        self._loading = False
        self.tree.expandAll()

    def _go(self, item: QTreeWidgetItem, _col: int) -> None:
        page = item.data(0, Qt.UserRole)
        if page is None:
            return
        self.navigate.emit(int(page))

    def _renamed(self, item: QTreeWidgetItem, _col: int) -> None:
        if self._loading:
            return
        posizione = item.data(0, Qt.UserRole + 1)
        if posizione is None:
            return
        self.rename_requested.emit(int(posizione), item.text(0))

    def _remove(self) -> None:
        item = self.tree.currentItem()
        if item is None:
            return
        posizione = item.data(0, Qt.UserRole + 1)
        if posizione is None:
            return
        self.remove_requested.emit(int(posizione))

    def _move(self) -> None:
        item = self.tree.currentItem()
        if item is None:
            return
        posizione = item.data(0, Qt.UserRole + 1)
        if posizione is not None:
            self.move_requested.emit(int(posizione))

    def _path(self, item: QTreeWidgetItem) -> str:
        parts = [item.text(0)]
        p = item.parent()
        while p is not None:
            parts.insert(0, p.text(0))
            p = p.parent()
        return "/".join(parts)


# ------------------------------------------------------ qualità del documento


class QualityPanel(QWidget):
    """Verifica di accessibilità e controllo pre-stampa del documento.

    I due elenchi restano separati perché rispondono a domande diverse: la
    prima riguarda chi deve poter leggere il documento, la seconda se è
    adatto a essere stampato o pubblicato.
    """

    fix_requested = Signal(str)
    goto_page_requested = Signal(int)
    refresh_requested = Signal()



    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        self.tabs = QTabWidget()
        self.fix_button = QPushButton(tr("Correggi selezionato"))
        self.fix_button.clicked.connect(self._fix)
        self.access_list = QTreeWidget()
        self.access_list.setHeaderLabels(["Problema", "Dove"])
        self.access_list.setRootIsDecorated(False)
        wrap_a = QWidget()
        va = QVBoxLayout(wrap_a)
        va.setContentsMargins(0, 0, 0, 0)
        va.addWidget(self.access_list, 1)
        va.addWidget(self.fix_button)
        self.access_list.itemDoubleClicked.connect(self._goto)
        self.tabs.addTab(wrap_a, tr("Accessibilità"))

        self.print_list = QTreeWidget()
        self.print_list.setHeaderLabels(["Problema", "Dove"])
        self.print_list.setRootIsDecorated(False)
        wrap_p = QWidget()
        vp = QVBoxLayout(wrap_p)
        vp.setContentsMargins(0, 0, 0, 0)
        vp.addWidget(self.print_list, 1)
        # anche l'elenco di pre-stampa: senza questa collegamento il pulsante
        # restava disabilitato e «Correggi selezionato» non faceva nulla
        # proprio nelle schede che hanno le correzioni (OCR, protezione, peso)
        self.access_list.itemSelectionChanged.connect(self._sync_fix)
        self.print_list.itemSelectionChanged.connect(self._sync_fix)
        self.tabs.currentChanged.connect(lambda _i: self._sync_fix())
        self.print_list.itemDoubleClicked.connect(self._goto)
        self.tabs.addTab(wrap_p, tr("Pre-stampa"))
        root.addWidget(self.tabs, 1)

        self.summary = QLabel("")
        self.summary.setProperty("role", "hint")
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)
        self._findings: list[list[quality.Finding]] = [[], []]
        self.fix_button.setEnabled(False)


    def set_palette_colors(self, pal: theme.Palette) -> None:
        """Adotta il pannello al tema: senza, resta sul colore precedente."""
        self.palette = pal
        self.update()

    def _fill(self, tree: QTreeWidget, esito: list[quality.Finding]) -> None:
        tree.clear()
        for f in esito:
            gravita = {
                "error": tr("Errore"),
                "warning": tr("Attenzione"),
                "info": tr("Informazione"),
            }
            gravita_nome = gravita.get(f.severity, f.severity)
            voce = QTreeWidgetItem([f"{gravita_nome}: {tr(f.title)}", self._dove(f)])
            voce.setData(0, Qt.UserRole, f.action)
            if (f.detail or "").strip():
                voce.setToolTip(0, f.detail)
            colore = {
                "error": "#b3261e",
                "warning": "#a16207",
                "info": "#1f6feb",
            }.get(f.severity)
            if colore:
                voce.setForeground(0, QBrush(QColor(colore)))
            tree.addTopLevelItem(voce)
        tree.resizeColumnToContents(0)

    def _dove(self, f: quality.Finding) -> str:
        """Dove si trova il problema, in italiano o in inglese."""
        if f.count > 1 and f.pages:
            if len(f.pages) == 1:
                return tr("pagina {n}").format(n=f.pages[0] + 1)
            return tr("pagine {prima}–{ultima} ({n})").format(
                prima=f.pages[0] + 1, ultima=f.pages[-1] + 1, n=f.count
            )
        if f.pages:
            return tr("pagina {n}").format(n=f.pages[0] + 1)
        if f.count:
            return f"{f.count}"
        return tr("documento")

    def load(self, doc: docmod.Document | None) -> None:
        self._findings = [[], []]
        if doc is None or not doc.is_open:
            self._fill(self.access_list, [])
            self._fill(self.print_list, [])
            self.summary.setText(tr("Nessun documento aperto."))
            self._sync_fix()
            return
        self._findings[0] = quality.accessibility_report(doc)
        self._findings[1] = quality.preflight_report(doc)
        self._fill(self.access_list, self._findings[0])
        self._fill(self.print_list, self._findings[1])
        errori = sum(1 for f in self._findings[0] if f.severity == "error")
        attenzioni = sum(1 for f in self._findings[0] if f.severity == "warning")
        if not self._findings[0] and not self._findings[1]:
            testo = tr("Nessun problema rilevato.")
        else:
            # La frase intera si traduce, il nome contato no: in italiano e in
            # inglese «3 problemi» e «3 problems» sono la stessa cosa, ma la
            # frase attorno puo' cambiare ordine. Per questo il numero non
            # viene messo dentro la stringa da tradurre.
            testo = tr(
                "Accessibilità: {errori}, {attenzioni}. "
                "Pre-stampa: {problemi}."
            ).format(
                errori=_conta(errori, ("errore", "errori"), ("error", "errors")),
                attenzioni=_conta(attenzioni, ("avviso", "avvisi"), ("warning", "warnings")),
                problemi=_conta(
                    len(self._findings[1]), ("problema", "problemi"), ("problem", "problems")
                ),
            )
        self.summary.setText(testo)
        self._sync_fix()

    def _current(self) -> tuple[QTreeWidget, int]:
        tree = self.print_list if self.tabs.currentIndex() == 1 else self.access_list
        items = tree.selectedItems()
        indice = tree.indexOfTopLevelItem(items[0]) if items else -1
        return tree, indice

    def _selected_action(self) -> str:
        tree, indice = self._current()
        if indice < 0:
            return ""
        voce = tree.topLevelItem(indice)
        return str(voce.data(0, Qt.UserRole) or "")

    def _sync_fix(self) -> None:
        self.fix_button.setEnabled(self._selected_action() != "")

    def _fix(self) -> None:
        azione = self._selected_action()
        if azione:
            self.fix_requested.emit(azione)

    def _goto(self, voce: QTreeWidgetItem, _col: int) -> None:
        testo = voce.text(1)
        if not testo.lower().startswith("pagina"):
            return
        numero = testo.replace("pagine", "").split("–")[0].strip()
        try:
            self.goto_page_requested.emit(int(numero) - 1)
        except ValueError:
            pass


# ------------------------------------------------------------- campi modulo


class FieldsPanel(QWidget):
    """Elenco dei campi modulo riconosciuti, con filtro per tipo."""

    edit_requested = Signal(int, int)
    focus_requested = Signal(int, int)
    clear_requested = Signal()
    flatten_requested = Signal()
    order_requested = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.fields: list[docmod.FieldInfo] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)
        self.filter = QComboBox()
        self.filter.addItems(["Tutti i campi", "Campi di testo", "Caselle e pulsanti",
                              "Elenchi", "Pulsanti", "Campi firma", "Non compilati"])
        self.filter.currentIndexChanged.connect(lambda _: self.refresh_table())
        root.addWidget(self.filter)
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(
            [tr("Nome"), tr("Tipo"), tr("Pag."), tr("Valore")]
        )
        intestazione = self.table.horizontalHeader()
        # Nome e Valore condividono lo spazio rimasto: con una colonna sola
        # elastica il nome finiva troncato e il valore spariva oltre il bordo
        intestazione.setSectionResizeMode(0, QHeaderView.Stretch)
        intestazione.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        intestazione.setSectionResizeMode(2, QHeaderView.Fixed)
        intestazione.setSectionResizeMode(3, QHeaderView.Stretch)
        intestazione.setStretchLastSection(False)
        self.table.setColumnWidth(2, 44)
        self.table.setTextElideMode(Qt.ElideRight)
        # la barra orizzontale permette di allargare le colonne a piacere
        intestazione.setSectionsClickable(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._on_select)
        self.table.itemDoubleClicked.connect(self._on_activate)
        root.addWidget(self.table, 1)
        row = QHBoxLayout()
        b_clear = QPushButton(tr("Azzera"))
        b_clear.clicked.connect(self.clear_requested)
        b_flat = QPushButton(tr("Appiattisci"))
        b_flat.clicked.connect(self.flatten_requested)
        row.addWidget(b_clear)
        row.addWidget(b_flat)
        root.addLayout(row)
        self.stats = QLabel("")
        self.stats.setProperty("role", "hint")
        root.addWidget(self.stats)


    def set_palette_colors(self, pal: theme.Palette) -> None:
        """Adotta il pannello al tema: senza, resta sul colore precedente."""
        self.palette = pal
        self.update()

    def load(self, doc: docmod.Document | None) -> None:
        self.fields = doc.fields() if (doc is not None and doc.is_open) else []
        self.refresh_table()

    def _visible_fields(self) -> list[docmod.FieldInfo]:
        mode = self.filter.currentIndex()
        out = []
        for f in self.fields:
            keep = True
            if mode == 1:
                keep = f.kind == "text"
            elif mode == 2:
                keep = f.kind == "toggle"
            elif mode == 3:
                keep = f.kind == "choice"
            elif mode == 4:
                keep = f.kind == "button"
            elif mode == 5:
                keep = f.kind == "signature"
            elif mode == 6:
                keep = f.value in (None, "", False, "Off")
            if keep:
                out.append(f)
        return out

    def refresh_table(self) -> None:
        rows = self._visible_fields()
        self.table.setRowCount(len(rows))
        for i, f in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(f.label))
            # etichetta breve: la descrizione estesa resta nel tooltip
            etichetta = kind_labels_short().get(f.kind, f.type)
            voce = QTableWidgetItem(etichetta)
            voce.setToolTip(kind_labels().get(f.kind, f.type))
            self.table.setItem(i, 1, voce)
            self.table.setItem(i, 2, QTableWidgetItem(str(f.page + 1)))
            val = "" if f.value in (None, False) else str(f.value)
            if f.password and val:
                val = "•" * min(10, len(val))
            valore = QTableWidgetItem(val[:60])
            valore.setToolTip(val)
            self.table.setItem(i, 3, valore)
        total = len(self.fields)
        filled = sum(1 for f in self.fields if f.value not in (None, "", False, "Off"))
        self.stats.setText(tr("{tot} campi — {compilati} compilati").format(tot=total, compilati=filled))
        self.table.resizeRowsToContents()

    def _on_select(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        i = rows[0].row()
        rowsf = self._visible_fields()
        if 0 <= i < len(rowsf):
            f = rowsf[i]
            self.edit_requested.emit(f.page, f.xref)

    def _on_activate(self, item: QTableWidgetItem) -> None:
        self._on_select()

    def focus(self, page: int, xref: int) -> None:
        rows = self._visible_fields()
        for i, f in enumerate(rows):
            if f.page == page and f.xref == xref:
                self.table.selectRow(i)
                return


# ------------------------------------------------------------- allegati


class AttachmentsPanel(QWidget):
    """File allegati al documento."""

    open_requested = Signal(str)
    save_requested = Signal(str)
    add_requested = Signal()
    remove_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self._open)
        root.addWidget(self.list, 1)
        row = QHBoxLayout()
        b_add = QPushButton(tr("Allega"))
        b_add.clicked.connect(self.add_requested)
        b_save = QPushButton(tr("Salva"))
        b_save.clicked.connect(self._save)
        b_del = QPushButton(tr("Rimuovi"))
        b_del.clicked.connect(self._remove)
        for b in (b_add, b_save, b_del):
            row.addWidget(b)
        root.addLayout(row)
        self.items: list[dict[str, Any]] = []


    def set_palette_colors(self, pal: theme.Palette) -> None:
        """Adotta il pannello al tema: senza, resta sul colore precedente."""
        self.palette = pal
        self.update()

    def load(self, doc: docmod.Document | None) -> None:
        self.items = doc.attachments() if (doc is not None and doc.is_open) else []
        self.list.clear()
        for a in self.items:
            size = _human_size(a.get("size", 0))
            it = QListWidgetItem(f"{a['name']}  ({size})")
            it.setData(Qt.UserRole, a["name"])
            if a.get("desc"):
                it.setToolTip(a["desc"])
            self.list.addItem(it)
        if not self.items:
            it = QListWidgetItem("Nessun allegato")
            it.setFlags(Qt.NoItemFlags)
            self.list.addItem(it)

    def _current(self) -> str:
        it = self.list.currentItem()
        return str(it.data(Qt.UserRole)) if it else ""

    def _open(self, item: QListWidgetItem) -> None:
        name = item.data(Qt.UserRole)
        if name:
            self.open_requested.emit(str(name))

    def _save(self) -> None:
        name = self._current()
        if name:
            self.save_requested.emit(name)

    def _remove(self) -> None:
        name = self._current()
        if name:
            self.remove_requested.emit(name)


# ------------------------------------------------------------- commenti


class CommentsPanel(QWidget):
    """Commenti e annotazioni testuali presenti nel documento."""

    navigate = Signal(int, object)
    delete_requested = Signal(int, int)
    reply_requested = Signal(int, int, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.rows: list[dict[str, Any]] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)
        self.list = QListWidget()
        self.list.itemClicked.connect(self._go)
        root.addWidget(self.list, 1)
        row = QHBoxLayout()
        self.reply = QLineEdit()
        self.reply.setPlaceholderText(tr("Scrivi una risposta"))
        b_send = QPushButton(tr("Rispondi"))
        b_send.clicked.connect(self._send)
        b_del = QPushButton(tr("Elimina"))
        b_del.clicked.connect(self._delete)
        row.addWidget(self.reply, 1)
        row.addWidget(b_send)
        row.addWidget(b_del)
        root.addLayout(row)


    def set_palette_colors(self, pal: theme.Palette) -> None:
        """Adotta il pannello al tema: senza, resta sul colore precedente."""
        self.palette = pal
        self.update()

    def load(self, doc: docmod.Document | None) -> None:
        self.rows = []
        self.list.clear()
        if doc is None or not doc.is_open:
            return
        for i in range(doc.page_count):
            for a in doc.annots(i, include_widgets=False):
                if a["type"] in ("Text", "Popup", "FreeText"):
                    info = a.get("info") or {}
                    self.rows.append(
                        {
                            "page": i,
                            "xref": a["xref"],
                            "title": info.get("title") or "Autore",
                            "text": info.get("content") or "",
                            "date": info.get("creationDate") or info.get("modDate") or "",
                            "rect": a["rect"],
                        }
                    )
        if not self.rows:
            it = QListWidgetItem("Nessun commento")
            it.setFlags(Qt.NoItemFlags)
            self.list.addItem(it)
            return
        for indice, r in enumerate(self.rows):
            head = f"{r['title']} — pagina {r['page'] + 1}"
            if r["date"]:
                head += f"  ({_pretty_date(r['date'])})"
            it = QListWidgetItem(f"{head}\n{r['text'][:160]}")
            # l'indice della riga, non il numero totale: con quest'ultimo tutte
            # le voci puntavano fuori dall'elenco e «Vai», «Rispondi» ed
            # «Elimina» non facevano nulla
            it.setData(Qt.UserRole, indice)
            self.list.addItem(it)

    def _go(self, item: QListWidgetItem) -> None:
        i = item.data(Qt.UserRole)
        if i is None or not (0 <= i < len(self.rows)):
            return
        r = self.rows[i]
        self.navigate.emit(r["page"], r["rect"])

    def _send(self) -> None:
        it = self.list.currentItem()
        text = self.reply.text().strip()
        if not text or it is None:
            return
        i = it.data(Qt.UserRole)
        if i is None or not (0 <= i < len(self.rows)):
            return
        r = self.rows[i]
        self.reply_requested.emit(r["page"], r["xref"], text)
        self.reply.clear()

    def _delete(self) -> None:
        it = self.list.currentItem()
        if it is None:
            return
        i = it.data(Qt.UserRole)
        if i is None or not (0 <= i < len(self.rows)):
            return
        r = self.rows[i]
        self.delete_requested.emit(r["page"], r["xref"])


# ------------------------------------------------------------- proprietà


class PropertiesPanel(QWidget):
    """Proprietà del documento, con campi modificabili."""

    changed = Signal(dict)
    xmp_requested = Signal()
    xmp_apply = Signal(str)

    #: Solo le chiavi, che sono di PDF e non cambiano. Le intestazioni le
    #: dà `_etichette_metadati`, che le traduce ogni volta che il riquadro si
    #: costruisce: in una costante di modulo la lingua sarebbe fissata a quella
    #: del primo import, che non è necessariamente quella scelta poi.
    FIELDS = ("title", "author", "subject", "keywords", "creator", "producer")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)
        self.edits: dict[str, QLineEdit] = {}
        form = QFormLayout()
        for key, label in zip(self.FIELDS, _etichette_metadati()):
            e = QLineEdit()
            e.editingFinished.connect(self._emit)
            self.edits[key] = e
            form.addRow(label, e)
        root.addLayout(form)
        root.addWidget(_hsep())
        self.info = QLabel("")
        self.info.setProperty("role", "hint")
        self.info.setWordWrap(True)
        root.addWidget(self.info)
        self.pages_box = QSpinBox()
        self.pages_box.setPrefix(tr("Pagine: "))
        root.addWidget(self.pages_box)
        b_xmp = QPushButton(tr("Metadati XMP…"))
        b_xmp.clicked.connect(self.xmp_requested)
        root.addWidget(b_xmp)
        root.addStretch(1)


    def set_palette_colors(self, pal: theme.Palette) -> None:
        """Adotta il pannello al tema: senza, resta sul colore precedente."""
        self.palette = pal
        self.update()

    def load(self, doc: docmod.Document | None) -> None:
        if doc is None or not doc.is_open:
            for e in self.edits.values():
                e.clear()
            self.info.setText("")
            self.pages_box.setValue(0)
            return
        meta = doc.metadata()
        for key in self.FIELDS:
            self.edits[key].setText(str(meta.get(key) or ""))
        try:
            from pathlib import Path

            size = doc.path.stat().st_size if doc.path else 0
        except Exception:
            size = 0
        enc = tr("nessuna")
        try:
            # le costanti sono quelle di PyMuPDF, non i numeri di /V del
            # dizionario: la tabella era sfalsata di una posizione e un PDF
            # senza protezione si dichiarava cifrato con RC4-40
            alg = doc.encryption_algorithm()
            enc = {
                pymupdf.PDF_ENCRYPT_NONE: tr("nessuna"),
                pymupdf.PDF_ENCRYPT_RC4_40: "RC4-40",
                pymupdf.PDF_ENCRYPT_RC4_128: "RC4-128",
                pymupdf.PDF_ENCRYPT_AES_128: "AES-128",
                pymupdf.PDF_ENCRYPT_AES_256: "AES-256",
            }.get(alg, tr("sconosciuta"))
        except Exception:
            pass
        self.info.setText(
            tr("Dimensione: {dimensione}\n"
               "Versione PDF: {formato}\n"
               "Cifratura: {cifratura}\n"
               "Moduli: {moduli}\n"
               "Firme: {firme}").format(
                dimensione=_human_size(size),
                formato=doc.metadata().get("format", "?"),
                cifratura=enc,
                moduli=tr("sì") if doc.field_stats()["total"] else tr("no"),
                firme=tr("sì") if doc.is_signed else tr("no"),
            )
        )
        self.pages_box.setValue(doc.page_count)
        self.pages_box.setReadOnly(True)

    def _emit(self) -> None:
        self.changed.emit({k: e.text() for k, e in self.edits.items()})


def _human_size(n: int) -> str:
    n = int(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def _pretty_date(raw: str) -> str:
    if not raw:
        return ""
    txt = raw.replace("D:", "").replace("'", "")
    for fmt in ("%Y%m%d%H%M%S", "%Y%m%d%H%M", "%Y%m%d"):
        try:
            return _dt.datetime.strptime(txt[: len(_dt.datetime.now().strftime(fmt))], fmt).strftime("%d/%m/%Y %H:%M")
        except ValueError:
            continue
    return raw
