"""Il log locale: creazione, rotazione, gestione delle eccezioni.

I test spostano la cartella dati in una directory temporanea: senza questo
scriverebbero nel log vero dell'utente, e il difetto si vedrebbe solo dopo.
"""

from __future__ import annotations

import logging
import sys
import threading

import pytest

from pdfeditor.core import log


@pytest.fixture()
def log_isolato(tmp_path, monkeypatch):
    """Una cartella dati usa e getta per ogni prova."""
    dati = tmp_path / "dati"
    monkeypatch.setenv("XDG_DATA_HOME", str(dati))
    monkeypatch.setenv("APPDATA", str(dati))
    monkeypatch.delenv("KORVAXOIDE_LOG", raising=False)
    livello = logging.getLogger().level
    hook = sys.excepthook
    hook_thread = threading.excepthook
    yield
    log._rimuovi_handler()
    log._excepthook_installato = False
    sys.excepthook = hook
    threading.excepthook = hook_thread
    logging.getLogger().setLevel(livello)


def _svuota_handler() -> None:
    """Porta su disco quello che i gestori hanno ancora in memoria."""
    for gestore in logging.getLogger().handlers:
        try:
            gestore.flush()
        except Exception:
            pass


def test_setup_crea_il_file_e_scrive_una_riga(log_isolato):
    """Il caso normale: la cartella viene creata e il messaggio arriva."""
    log.setup()
    log.info("riga di prova del log")

    assert log.log_file().is_file()
    _svuota_handler()
    assert "riga di prova del log" in log.log_file().read_text(encoding="utf-8")


def test_due_chiamate_non_duplicano_gli_handler(log_isolato):
    """``setup`` è idempotente: due avvii nello stesso processo non raddoppiano."""
    radice = logging.getLogger()
    log.setup()
    quanti = len(radice.handlers)
    log.setup()
    assert len(radice.handlers) == quanti


def test_oltre_la_soglia_ruota_il_file(log_isolato):
    """Superati i 512 KiB deve comparire ``korvaxoide.log.1``."""
    log.setup()
    for _ in range(600):
        log.info("%s", "x" * 1024)
    _svuota_handler()

    ruotato = log.log_file().with_name(log.log_file().name + ".1")
    assert ruotato.is_file()


def test_un_eccezione_finta_finisce_nel_file(log_isolato):
    """L'hook del thread principale scrive il traceback, non solo il messaggio."""
    log.setup()
    log.install_excepthook()
    try:
        raise RuntimeError("errore finto del test")
    except RuntimeError:
        sys.excepthook(*sys.exc_info())
    _svuota_handler()

    contenuto = log.log_file().read_text(encoding="utf-8")
    assert "RuntimeError: errore finto del test" in contenuto
    assert "Traceback" in contenuto


def test_una_cartella_non_scrivibile_non_solleva(log_isolato, tmp_path, monkeypatch):
    """Se il log non si può scrivere si ripiega su stderr, senza fermare l'app."""
    blocco = tmp_path / "blocco"
    blocco.write_text("non è una cartella", encoding="utf-8")
    monkeypatch.setattr(log, "log_dir", lambda: blocco / "logs")

    log.setup()  # non deve sollevare

    gestori = logging.getLogger().handlers
    assert any(
        isinstance(g, logging.StreamHandler)
        and not isinstance(g, log.RotatingFileHandler)
        for g in gestori
    )


def test_debug_accende_il_dettaglio(log_isolato, monkeypatch):
    """``KORVAXOIDE_LOG=debug`` abbassa il livello senza toccare il codice."""
    monkeypatch.setenv("KORVAXOIDE_LOG", "debug")
    log.setup()
    assert logging.getLogger("korvaxoide").getEffectiveLevel() == logging.DEBUG
