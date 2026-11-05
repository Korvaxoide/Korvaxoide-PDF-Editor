"""Log locale dell'applicazione e gestione delle eccezioni non catturate.

Il modulo non importa Qt: deve restare utilizzabile anche da un processo
headless e va importato prima di PyMuPDF e dell'interfaccia, così un guasto
nell'avvio lascia una traccia. Il file vive nella cartella dati dell'utente,
accanto alle preferenze e alle firme salvate: non viene mai inviato da nessuna
parte, perché il programma non usa la rete.

Nei log non finiscono contenuti dei documenti, valori dei campi, password o
percorsi di firme. Si registrano solo versione, sistema, percorso del file
aperto ed eventuale eccezione: abbastanza per capire un guasto senza
raccogliere dati che l'utente non vorrebbe condividere.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import settings

#: Nome del file di log nella cartella dedicata.
NOME_FILE = "korvaxoide.log"

#: Dimensione massima di un file prima della rotazione (512 KiB).
DIMENSIONE_MASSIMA = 512 * 1024

#: Quanti file ruotati vengono conservati (``.1``, ``.2``, ``.3``).
COPIE = 3

#: Il logger usato da tutto il programma. I moduli lo importano come
#: ``from ..core.log import log`` e chiamano ``log.debug(...)``.
log = logging.getLogger("korvaxoide")

def debug(messaggio: str, *argomenti, **parole) -> None:
    """Scrive un messaggio di dettaglio."""
    log.debug(messaggio, *argomenti, **parole)


def info(messaggio: str, *argomenti, **parole) -> None:
    """Scrive un messaggio informativo."""
    log.info(messaggio, *argomenti, **parole)


def warning(messaggio: str, *argomenti, **parole) -> None:
    """Scrive un avviso."""
    log.warning(messaggio, *argomenti, **parole)


def error(messaggio: str, *argomenti, **parole) -> None:
    """Scrive un errore."""
    log.error(messaggio, *argomenti, **parole)


def critical(messaggio: str, *argomenti, **parole) -> None:
    """Scrive un errore grave."""
    log.critical(messaggio, *argomenti, **parole)


#: Handler installato da :func:`setup`, per non duplicarlo e per poterlo
#: sostituire quando cambia la cartella dati (cosa che fanno i test).
_handler: logging.Handler | None = None
_destinazione: Path | None = None
_excepthook_installato = False


def log_dir() -> Path:
    """La cartella dei log, dentro i dati dell'utente."""
    return settings.data_dir() / "logs"


def log_file() -> Path:
    """Il percorso del file di log corrente."""
    return log_dir() / NOME_FILE


def _livello() -> int:
    """Il livello richiesto: ``KORVAXOIDE_LOG=debug`` accende il dettaglio."""
    if os.environ.get("KORVAXOIDE_LOG", "").strip().lower() == "debug":
        return logging.DEBUG
    return logging.INFO


def _rimuovi_handler() -> None:
    """Scollega e chiude l'handler installato in precedenza."""
    global _handler
    if _handler is None:
        return
    radice = logging.getLogger()
    radice.removeHandler(_handler)
    try:
        _handler.close()
    except Exception:
        # chiudere un handler già chiuso o su un file sparito non deve
        # impedire la configurazione del nuovo
        pass
    _handler = None


def setup(verbose: bool = False) -> logging.Logger:
    """Configura il log su file ruotato; è idempotente.

    Chiamata due volte con la stessa cartella non aggiunge un secondo handler.
    Se la cartella non è scrivibile si ripiega su ``stderr`` senza sollevare
    eccezioni: un log mancante non deve impedire l'avvio del programma.
    """
    global _handler, _destinazione

    destinazione = log_file()
    if _handler is not None and _destinazione == destinazione:
        return log

    _rimuovi_handler()
    livello = logging.DEBUG if verbose else _livello()

    radice = logging.getLogger()
    # Il livello della radice non deve alzare quello dei logger già silenziosi
    # di terze parti, ma deve lasciar passare i nostri messaggi.
    if radice.level > livello or radice.level == logging.NOTSET:
        radice.setLevel(livello)

    formato = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        destinazione.parent.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = RotatingFileHandler(
            destinazione,
            maxBytes=DIMENSIONE_MASSIMA,
            backupCount=COPIE,
            encoding="utf-8",
        )
    except (OSError, ValueError):
        # Cartella non scrivibile, permessi negati, percorso che è un file:
        # si scrive su stderr e si prosegue.
        handler = logging.StreamHandler(sys.stderr)

    handler.setFormatter(formato)
    handler.setLevel(livello)
    radice.addHandler(handler)
    _handler = handler
    _destinazione = destinazione
    return log


def install_excepthook() -> None:
    """Registra gli hook per le eccezioni non catturate.

    Scrivono il traceback nel log, sia per il thread principale sia per gli
    altri thread. Non aprono un dialogo: l'eccezione può arrivare mentre Qt sta
    gestendo un evento, e mostrare una finestra da lì è il modo più semplice
    per bloccare l'applicazione o rientrare nell'errore.
    """
    global _excepthook_installato
    if _excepthook_installato:
        return

    def _hook_principale(tipo, valore, traceback_oggetto) -> None:
        if valore is None:
            return
        try:
            log.critical(
                "Eccezione non gestita",
                exc_info=(tipo, valore, traceback_oggetto),
            )
        except Exception:
            # se anche il logging fallisce non si deve ricorrere all'infinito
            pass

    def _hook_thread(argomenti) -> None:
        if argomenti.exc_value is None:
            return
        try:
            nome = getattr(argomenti.thread, "name", "sconosciuto")
            log.critical(
                "Eccezione non gestita nel thread %s",
                nome,
                exc_info=(argomenti.exc_type, argomenti.exc_value, argomenti.exc_traceback),
            )
        except Exception:
            pass

    sys.excepthook = _hook_principale
    threading.excepthook = _hook_thread
    _excepthook_installato = True
