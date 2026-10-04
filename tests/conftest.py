"""Configurazione condivisa dei test."""

import os
import sys
import time
from pathlib import Path

import pytest

# l'isolamento va per primo, prima di qualunque import del programma: e' lui
# che impedisce alla suite di scrivere nelle preferenze e nella libreria firme
# vere dell'utente
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ambiente  # noqa: E402

ambiente.configura_qt()
ambiente.isola()
ambiente.prepara_percorso()
# va prima di qualunque costruzione di finestra: l'interfaccia segue la lingua
# del computer e su una macchina inglese le verifiche che citano una voce di
# menu per nome non la troverebbero
ambiente.fissa_lingua()


@pytest.fixture(scope="session")
def app():
    """Applicazione Qt condivisa: una sola per tutta la sessione di test."""
    from PySide6.QtWidgets import QApplication

    from pdfeditor.core import settings as sm
    from pdfeditor.ui import theme

    st = sm.Settings()
    st.set("recover", False)
    st.set("confirm_destructive", False)
    a = QApplication.instance() or QApplication([])
    a.setStyleSheet(theme.stylesheet(theme.LIGHT))
    return a


@pytest.fixture(scope="session")
def documento_modello():
    """PDF di prova con testo, campi modulo e un'immagine."""
    global _MODELLO
    if _MODELLO is None:
        import test_interazione

        _MODELLO = str(test_interazione._documento_modello())
    return _MODELLO


_MODELLO = None


@pytest.fixture()
def finestra(app):
    """Finestra principale, pronta per l'interazione."""
    from pdfeditor.ui.main_window import MainWindow

    w = MainWindow()
    w.resize(1300, 850)
    w.show()
    for _ in range(3):
        app.processEvents()
    yield w
    # chiudere con modifiche non salvate apre una richiesta modale: nei test va
    # evitata, altrimenti il processo resterebbe in attesa
    w.closeEvent = lambda *_a: None
    w.close()


@pytest.fixture(autouse=True)
def _un_dialogo_modale_non_puo_fermare_la_suite():
    """Chiude ciò che è rimasto aperto troppo a lungo, prima che la suite si fermi.

    Un dialogo modale gira un ciclo di eventi tutto suo: se la verifica aspetta
    che qualcuno lo chiuda e nessuno lo fa, l'attesa non finisce mai. Successe
    anche per un solo test, e la macchina restò occupata sei ore. Qui un
    dialogo o un avviso visibile da più di qualche secondo viene chiuso: la
    verifica che non arriva da nessuna parte fallisce e la suite va avanti.

Il timer appartiene a questa verifica e muore con lei: se sopravvivesse,
    chiuderebbe i dialoghi delle verifiche successive.
    """
    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication, QDialog
    except ImportError:
        # il controllo delle licenze non installa PySide6 e non ha bisogno di
        # guardare i dialoghi: la documentazione si controlla senza Qt
        yield
        return

    app = QApplication.instance()
    if app is None:  # una verifica senza interfaccia non ha dialoghi
        yield
        return

    da_quando: dict[object, float] = {}

    def chiudi():
        adesso = time.monotonic()
        for w in list(app.topLevelWidgets()):
            if isinstance(w, QDialog) and w.isModal() and w.isVisible():
                if w not in da_quando:
                    da_quando[w] = adesso
                elif adesso - da_quando[w] > 5:
                    w.reject()
            else:
                da_quando.pop(w, None)

    timer = QTimer()
    timer.setInterval(500)
    timer.timeout.connect(chiudi)
    timer.start()
    yield
    timer.stop()
    da_quando.clear()


def test_i_test_non_toccano_i_dati_utente():
    """Le cartelle di configurazione e dati devono stare fuori da casa.

    Senza questo, eseguire la suite scriveva nelle preferenze vere e creava
    una libreria firme sull'utente: un test poteva cambiare il tema o
    disattivare il recupero, e lo si scopriva solo dopo, riavviando il
    programma.
    """
    from pdfeditor.core import settings as sm
    from pdfeditor.signature import manager as sig

    radice = ambiente.radice()
    casa = Path.home().resolve()
    for cartella in (sm.config_dir(), sm.data_dir(), sig.library_dir()):
        assert casa not in cartella.resolve().parents or cartella.resolve() == radice, (
            f"i test scrivono nei dati dell'utente: {cartella}"
        )
        assert str(cartella).startswith(str(radice)), (
            f"cartella fuori dalla radice temporanea dei test: {cartella}"
        )
