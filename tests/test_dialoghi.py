"""Verifica che ogni dialogo si apra, si usi e resti entro lo schermo.

Un dialogo che chiede piu' spazio dello schermo spinge fuori vista pulsanti e
opzioni: la funzione sembra non funzionare. Qui ogni dialogo viene aperto, si
visitano tutte le schede, si cliccano i pulsanti e si controlla che le sue
dimensioni e il suo contenuto minimo entrino nello schermo.
"""

import pymupdf
import pytest
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QDialog, QPushButton, QTabWidget

from pdfeditor.ui.dialogs import props
from pdfeditor.ui.dialogs.signature_dialog import SignatureDialog


def _chiudi_modali(escluso):
    """Chiude i dialoghi che i pulsanti aprono (colori, file, ...)."""
    for wid in QApplication.instance().topLevelWidgets():
        if wid is escluso or not wid.isVisible() or not isinstance(wid, QDialog):
            continue
        wid.reject()


@pytest.fixture()
def documento(finestra, documento_modello):
    finestra.load_path(documento_modello)
    for _ in range(6):
        QApplication.instance().processEvents()
    return finestra.doc


def _esamina(nome, dlg):
    """Apre il dialogo, visita le schede, clicca i pulsanti e lo misura."""
    schermo = QApplication.instance().primaryScreen().availableGeometry()
    timer = QTimer()
    timer.setInterval(40)
    timer.timeout.connect(lambda: _chiudi_modali(dlg))
    timer.start()
    try:
        dlg.show()
        for _ in range(4):
            QApplication.instance().processEvents()
        for tab in dlg.findChildren(QTabWidget):
            for i in range(tab.count()):
                tab.setCurrentIndex(i)
                for _ in range(2):
                    QApplication.instance().processEvents()
        for pulsante in dlg.findChildren(QPushButton):
            if pulsante.isEnabled() and pulsante.isVisible():
                pulsante.click()
                for _ in range(3):
                    QApplication.instance().processEvents()
                if not dlg.isVisible():
                    dlg.show()
                    for _ in range(2):
                        QApplication.instance().processEvents()
    finally:
        timer.stop()
        dlg.close()
        for _ in range(2):
            QApplication.instance().processEvents()

    assert dlg.size().width() <= schermo.width(), (
        f"{nome}: largo {dlg.size().width()}px su uno schermo di {schermo.width()}px"
    )
    assert dlg.size().height() <= schermo.height(), (
        f"{nome}: alto {dlg.size().height()}px su uno schermo di {schermo.height()}px"
    )
    assert dlg.minimumSizeHint().height() <= schermo.height(), (
        f"{nome}: il contenuto richiede {dlg.minimumSizeHint().height()}px, "
        f"lo schermo ne ha {schermo.height()}: opzioni fuori vista"
    )


def _con_piu_immagini(finestra):
    """Il dialogo di conversione con delle immagini vere dentro.

    Vuoto il dialogo non mostra miniature ne' riepilogo: sono le cose che
    possono stare fuori dallo schermo o non aggiornarsi, e vanno provate con il
    contenuto dentro.
    """
    import ambiente

    from PIL import Image

    scelte = []
    for idx in range(3):
        p = ambiente.cartella("immagini") / f"dialogo{idx}.png"
        Image.new("RGB", (400, 300), (40 * idx, 80, 160)).save(p)
        scelte.append(str(p))
    return props.ImagesToPdfDialog(finestra, files=scelte)


DIALOGHI = [
    ("TextBoxDialog", lambda w, d: props.TextBoxDialog(w, "helv", 12)),
    ("AnnotationStyleDialog", lambda w, d: props.AnnotationStyleDialog("rect", w)),
    ("MarkerStyleDialog", lambda w, d: props.MarkerStyleDialog("highlight", w)),
    ("NewFieldDialog", lambda w, d: props.NewFieldDialog(w)),
    ("SecurityDialog", lambda w, d: props.SecurityDialog(d, w)),
    ("PageSetupDialog", lambda w, d: props.PageSetupDialog((595, 842), w)),
    ("CropPageDialog automatico", lambda w, d: props.CropPageDialog((595, 842), (50, 50, 545, 792), w)),
    ("CropPageDialog manuale", lambda w, d: props.CropPageDialog((595, 842), None, w)),
    ("ReduceSizeDialog", lambda w, d: props.ReduceSizeDialog(d.image_inventory(), 85, w)),
    ("ReduceSizeDialog vuoto", lambda w, d: props.ReduceSizeDialog([], 85, w)),
    ("PageNumberDialog", lambda w, d: props.PageNumberDialog(1, False, w)),
    ("SplitDialog", lambda w, d: props.SplitDialog(3, w)),
    ("MergeDialog", lambda w, d: props.MergeDialog(w)),
    ("ImagesToPdfDialog vuoto", lambda w, d: props.ImagesToPdfDialog(w)),
    ("ImagesToPdfDialog con foto", lambda w, d: _con_piu_immagini(w)),
    ("ExportDialog", lambda w, d: props.ExportDialog(1, w)),
    ("SignatureSetupDialog", lambda w, d: props.SignatureSetupDialog(d, 0, w)),
    ("PreferencesDialog", lambda w, d: props.PreferencesDialog(w.settings, w)),
    ("XmpDialog", lambda w, d: props.XmpDialog("<x:xmpmeta/>", w)),
    ("SignatureDialog", lambda w, d: SignatureDialog(d, 0, w.library, w)),
]


@pytest.mark.parametrize("voce", DIALOGHI, ids=[n for n, _ in DIALOGHI])
def test_il_dialogo_sta_nello_schermo(finestra, documento, voce):
    nome, fabbrica = voce
    _esamina(nome, fabbrica(finestra, documento))


def test_i_dialogi_non_nascondono_i_metodi_di_qwidget(finestra, documento):
    """Nessun dialogo puo' sostituire ``size()``, ``width()`` o ``font()``.

    Sono metodi di QWidget: un attributo con lo stesso nome li rende
    richiamabili solo come attributo, e basta un ``dialogo.size()`` per
    riceverne un errore.
    """
    pericolosi = []
    for nome, fabbrica in DIALOGHI:
        dlg = fabbrica(finestra, documento)
        for metodo in ("size", "width", "height", "font"):
            valore = getattr(dlg, metodo, None)
            if valore is not None and not callable(valore):
                pericolosi.append(f"{nome}.{metodo}")
        dlg.close()
    assert not pericolosi, f"attributi che nascondono metodi di QWidget: {pericolosi}"


def test_il_dialogo_firma_mostra_tutte_le_opzioni(finestra, documento):
    """Le opzioni di inserimento devono stare dentro la finestra.

    Sono sotto le schede: se il dialogo chiede piu' altezza dello schermo non
    si vedono piu' e sembra che la firma non si possa creare.
    """
    dlg = SignatureDialog(documento, 0, finestra.library, finestra)
    dlg.show()
    for _ in range(6):
        QApplication.instance().processEvents()
    try:
        for scheda in range(dlg.tabs.count()):
            dlg.tabs.setCurrentIndex(scheda)
            for _ in range(3):
                QApplication.instance().processEvents()
            for controllo in (dlg.cb_page, dlg.spin_w, dlg.spin_opacity, dlg.chk_flatten):
                posizione = controllo.mapTo(dlg, controllo.rect().topLeft())
                assert posizione.y() + controllo.height() <= dlg.height(), (
                    f"controllo fuori dalla finestra sulla scheda «{dlg.tabs.tabText(scheda)}»"
                )
    finally:
        dlg.close()
        for _ in range(2):
            QApplication.instance().processEvents()


def test_il_dialogo_di_conversione_sta_nello_schermo_senza_scorrere(finestra, documento):
    """Le opzioni di pagina non devono uscire dal dialogo, ne' con i caratteri grandi.

    Le sei coppie di opzioni erano in una riga sola e i sette pulsanti erano
    tutti in fila: appena il carattere cresce un po' la riga supera il dialogo,
    ``adatta_a_schermo`` lo infila in un'area scorrevole, i pulsanti si
    schiacciano a una striscia di un pixel e per arrivare alle opzioni bisogna
    scorrere in orizzontale.

    Su Linux i caratteri sono piccoli e il dialogo sembrava starci; su Windows il
    gruppo delle opzioni misurava 1032px in un dialogo largo 752px, e la
    verifica passava lo stesso guardando la dimensione minima del dialogo, che
    vale 90x90 qualunque cosa ci sia dentro. Per questo la seconda meta' della
    verifica raddoppia il carattere e guarda dove arrivano i controlli: se il
    dialogo sta nello schermo solo con i caratteri di Linux, non ci sta.
    """
    dlg = _con_piu_immagini(finestra)
    try:
        dlg.show()
        for _ in range(8):
            QApplication.instance().processEvents()
        schermo = QApplication.instance().primaryScreen().availableGeometry()
        assert dlg.minimumSizeHint().height() <= schermo.height() * 0.92, (
            f"il dialogo chiede {dlg.minimumSizeHint().height()}px di altezza "
            f"su uno schermo di {schermo.height()}px"
        )
        opzioni = dlg.formato.parentWidget()
        controlli = {"Formato": dlg.formato, "Orientamento": dlg.orientamento,
                     "Adattamento": dlg.adattamento, "Margini": dlg.margini,
                     "Immagini per pagina": dlg.per_pagina, "Risoluzione": dlg.dpi}

        def _problema() -> str:
            """Il primo difetto trovato, o una stringa vuota se sta tutto."""
            largo = opzioni.sizeHint().width()
            if largo > dlg.width():
                return (f"le opzioni larghe {largo}px in un dialogo di {dlg.width()}px: "
                        "metà fuori, e serve scorrere per reachesarle")
            # i pulsanti non stanno tutti in fila: si guarda la larghezza della
            # riga piu' affollata, che e' quella che altrimenti esce da sola
            larghezze = sorted((b.sizeHint().width() for b in dlg.findChildren(QPushButton)
                                if b.text() not in ("Converti", "Annulla", "Cancel")),
                               reverse=True)
            affollata = sum(larghezze[:3])
            if affollata + 24 > dlg.width():
                return (f"tre pulsanti affiancati larghi {affollata}px in un dialogo di "
                        f"{dlg.width()}px: verrebbero schiacciati")
            for nome, controllo in controlli.items():
                if controllo.height() < 20:
                    return f"«{nome}» è alto {controllo.height()}px: non si può premere"
                dentro = controllo.mapTo(dlg, controllo.rect().topLeft())
                if dentro.x() < 0 or dentro.x() + controllo.width() > dlg.width():
                    return (f"«{nome}» sta a x={dentro.x()} in un dialogo di {dlg.width()}px: "
                            "fuori dalla vista")
                if dentro.y() + controllo.height() > dlg.height():
                    return f"«{nome}» è sotto il bordo del dialogo: non si vede"
            return ""

        problema = _problema()
        assert not problema, problema

        grande = QFont(dlg.font())
        grande.setPointSize(max(grande.pointSize(), 1) * 2)
        dlg.setFont(grande)
        for _ in range(8):
            QApplication.instance().processEvents()
        problema = _problema()
        assert not problema, f"con i caratteri raddoppiati: {problema}"
    finally:
        dlg.close()
        for _ in range(2):
            QApplication.instance().processEvents()
