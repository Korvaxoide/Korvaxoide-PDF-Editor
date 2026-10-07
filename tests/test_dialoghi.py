"""Verifica che ogni dialogo si apra, si usi e resti entro lo schermo.

Un dialogo che chiede piu' spazio dello schermo spinge fuori vista pulsanti e
opzioni: la funzione sembra non funzionare. Qui ogni dialogo viene aperto, si
visitano tutte le schede, si cliccano i pulsanti e si controlla che le sue
dimensioni e il suo contenuto minimo entrino nello schermo.
"""

import pymupdf
import pytest
from PySide6.QtCore import QTimer
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
    """Le opzioni di pagina non devono uscire dal dialogo.

    Le sei coppie di opzioni erano in una fila sola: la riga larga 1262px dentro
    un dialogo di 752px, ``adatta_a_schermo`` lo infilava in un'area scorrevole
    e i controlli finivano oltre il bordo destro, con i pulsanti schiacciati a
    una striscia di un pixel. Per arrivarci bisognava scorrare in orizzontale.

    Si controlla dove i controlli arrivano davvero e non la dimensione minima
    del dialogo: quella la riporta a 90x90 qualunque cosa ci sia dentro, e con
    lei la verifica passava anche col dialogo rotto.
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
        assert opzioni.sizeHint().width() <= dlg.width(), (
            f"le opzioni di pagina larghe {opzioni.sizeHint().width()}px in un "
            f"dialogo di {dlg.width()}px: metà fuori, e serve scorrere per reachesarle"
        )
        controlli = {"Formato": dlg.formato, "Orientamento": dlg.orientamento,
                     "Adattamento": dlg.adattamento, "Margini": dlg.margini,
                     "Immagini per pagina": dlg.per_pagina, "Risoluzione": dlg.dpi}
        for nome, controllo in controlli.items():
            assert controllo.height() >= 20, (
                f"«{nome}» è alto {controllo.height()}px: schiacciato e non premibile"
            )
            dentro = controllo.mapTo(dlg, controllo.rect().topLeft())
            assert 0 <= dentro.x() and dentro.x() + controllo.width() <= dlg.width(), (
                f"«{nome}» sta a x={dentro.x()} in un dialogo largo {dlg.width()}px: "
                "fuori dalla vista"
            )
            assert dentro.y() + controllo.height() <= dlg.height(), (
                f"«{nome}» è sotto il bordo del dialogo: non si vede"
            )
    finally:
        dlg.close()
        for _ in range(2):
            QApplication.instance().processEvents()
