"""Avvio dell'applicazione."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _precarica_pymupdf() -> None:
    """Carica MuPDF prima di Qt, per una ragione che vale la pena conoscere.

    L'ordine delle due import non è indifferente. PyMuPDF e Qt caricano
    librerie native in comune — FreeType, HarfBuzz, libjpeg, zlib — e chi arriva
    primo le tiene residenti per l'altro: importando MuPDF prima di PySide6 si
    guadagna una decina di millisecondi rispetto all'ordine opposto, misurato
    e non supposto (``tools/bench_startup.py``).

    MuPDF verrebbe importato comunque un attimo dopo, da ``core.document``, ma
    importing qui nel mezzo si sceglie l'ordine invece di subirlo.

    Qui prima c'era anche ``TOOLS.store_shrink(100)`` e
    ``TOOLS.store_size(200 * 1024 * 1024)``. La seconda chiamata non poteva
    funzionare: in PyMuPDF 1.28 ``store_size`` e ``store_maxsize`` sono
    **getter** che restituiscono ``None`` e non hanno un setter, quindi quel
    limite di 200 MiB non era solo non applicato, era proprio inexpressibile.
    Sollevavano ``TypeError``, il ``except`` se lo accettava in silenzio e la
    riga sembrava lavorare. Neppure ``store_shrink(100)`` serviva: il deposito
    di MuPDF è vuoto in un processo che non ha ancora aperto un documento.
    Se un giorno quel limite servirà davvero, va impostato dove si apre un
    documento.
    """
    try:
        import pymupdf  # noqa: F401
    except Exception:
        # Senza MuPDF il programma non parte, ma è `core.document` a dirlo con
        # un messaggio suo: qui non si deve coprire un errore che non c'è.
        pass


def _prepare_environment() -> None:
    """Impostazioni d'ambiente per Qt, prima che Qt venga importato."""
    if sys.platform.startswith("linux"):
        # Wayland senza supporto: si ripiega su X11, altrimenti Qt non parte.
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            os.environ["QT_QPA_PLATFORM"] = "offscreen"
    _precarica_pymupdf()


#: I traduttori installati. Qt li cerca in ordine di installazione, quindi
#: tenerli tutti fa vincere il primo: al cambio di lingua vanno tolti.
_TRADUTTORI: list = []


def _install_translator(app, lingua: str) -> None:
    """Traduce nella lingua scelta i testi che vengono da Qt.

    Sono i pulsanti standard dei dialoghi (OK, Annulla, Chiudi, Salva, Scegli
    file) e i menu contestuali di sistema: senza questo resterebbero in inglese
    mentre il resto dell'interfaccia parla un'altra lingua.

    Prima la ricerca era scritta su ``_it.qm`` e non guardava nulla: con
    l'interfaccia in inglese i pulsanti dei dialoghi sarebbero usciti in
    italiano, che è il mezzo peggio.
    """
    from PySide6.QtCore import QLibraryInfo, QTranslator

    # I traduttori si accumulano e Qt li cerca in ordine: installare quello
    # dell'inglese sopra quello dell'italiano lasciava i pulsanti in italiano,
    # cioe' il cambio di lingua non cambiava niente. Si toglie tutto quello che
    # c'e' prima di mettere quello nuovo.
    _rimuovi_traduttori(app)
    for modulo in ("qtbase", "qt"):
        for candidate in (
            Path(QLibraryInfo.path(QLibraryInfo.TranslationsPath)) / f"{modulo}_{lingua}.qm",
            _percorso_pyinstaller() / f"{modulo}_{lingua}.qm",
        ):
            if not candidate.is_file():
                continue
            traduttore = QTranslator(app)
            if traduttore.load(str(candidate)):
                app.installTranslator(traduttore)
                # vanno tenuti vivi: un QTranslator non referenziato viene
                # distrutto e sparisce anche dall'applicazione
                _TRADUTTORI.append(traduttore)
                return


def _rimuovi_traduttori(app) -> None:
    """Scollega i traduttori installati al cambio di lingua."""
    while _TRADUTTORI:
        app.removeTranslator(_TRADUTTORI.pop())


def _percorso_pyinstaller() -> Path:
    """La cartella delle traduzioni dentro PySide6, se esiste.

    In un eseguibile pacchettizzato le traduzioni non sono nella directory di
    PySide6 ma in quella dell'applicazione: senza questo il pacchetto non
    traduce niente e la differenza si nota solo guardando i pulsanti.
    """
    try:
        import PySide6

        base = Path(PySide6.__file__).parent / "Qt" / "translations"
    except Exception:
        return Path("/nonexistent")
    return base if base.is_dir() else Path("/nonexistent")


def run(argv: list[str] | None = None) -> int:
    """Avvia l'editor; restituisce il codice di uscita."""
    argv = list(argv if argv is not None else sys.argv)
    _prepare_environment()
    for p in ("resources", "pdfeditor/resources"):
        if Path(p).exists():
            sys.path.insert(0, p)

    from PySide6.QtCore import QLocale, Qt
    from PySide6.QtWidgets import QApplication

    from . import __app_id__, __app_name__, __org_name__, __version__
    from .core import i18n, settings as settingsmod
    from .ui import icons, theme
    from .ui.main_window import MainWindow

    QApplication.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings, True)
    app = QApplication(argv)

    # La lingua si sceglie prima di costruire qualunque cosa: il traduttore di
    # Qt va installato prima che i dialogi nascano, e le preferenze dicono se
    # l'utente ne ha impostata una o se vale quella del sistema. QLocale e' la
    # sola lettura affidabile su Windows, dove la lingua non viene dalle
    # variabili d'ambiente.
    st = settingsmod.Settings()
    i18n.set_lingua_di_sistema(QLocale.system().name())
    lingua = i18n.inizializza(str(st.get("ui_language") or ""))
    _install_translator(app, lingua)

    app.setApplicationName(__app_name__)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(__org_name__)
    app.setDesktopFileName(__app_id__)
    app.setWindowIcon(icons.app_icon())

    pal = theme.DARK if st.get("theme") == "scuro" else theme.LIGHT
    theme.attiva(pal)
    app.setStyleSheet(theme.stylesheet(pal))

    win = MainWindow()
    win.show()

    for arg in argv[1:]:
        if arg.lower().endswith(".pdf") and Path(arg).exists():
            win.load_path(arg)
            break
    return app.exec()


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
