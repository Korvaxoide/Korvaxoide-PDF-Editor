"""Ambiente di prova: tiene i test lontani dai dati dell'utente.

Il programma scrive in due cartelle: la configurazione e i dati. Le funzioni
che le calcolano leggono le variabili d'ambiente a ogni chiamata, quindi basta
spostarle prima di creare qualunque ``Settings`` o ``SignatureLibrary`` perché
i test non tocchino più le preferenze e la libreria firme vere.

Prima non era cosi': la suite scriveva davvero in ``~/.config/korvaxoide-pdf-editor``
e costruiva una libreria firme sull'utente vero, e un test poteva cambiare il
tema, disattivare il recupero o aggiungere voci all'elenco dei recenti.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_globale: Path | None = None


def _cartella(nome: str) -> Path:
    base = _globale
    if base is None:  # pragma: no cover - difensivo
        base = Path(tempfile.mkdtemp(prefix="korvaxoide-test-"))
    d = base / nome
    d.mkdir(parents=True, exist_ok=True)
    return d


def isola() -> Path:
    """Sposta configurazione e dati in una cartella temporanea. Idempotente."""
    global _globale
    if _globale is not None:
        return _globale
    _globale = Path(tempfile.mkdtemp(prefix="korvaxoide-test-"))
    conf = _cartella("config")
    dati = _cartella("dati")
    os.environ["XDG_CONFIG_HOME"] = str(conf)
    os.environ["XDG_DATA_HOME"] = str(dati)
    # su Windows e macOS la base e' una variabile diversa
    os.environ["APPDATA"] = str(conf)
    os.environ["HOME"] = str(_globale)
    return _globale


def radice() -> Path:
    """La cartella temporanea dei test, se l'isolamento e' attivo."""
    return _globale if _globale is not None else Path.home()


def prepara_percorso() -> None:
    """Aggiunge la radice del progetto e la cartella dei test a ``sys.path``."""
    for p in (ROOT, Path(__file__).resolve().parent):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))


def configura_qt() -> None:
    """Headless: senza schermo la finestra non potrebbe crearsi."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def fissa_lingua() -> str:
    """Fissa l'italiano per le verifiche.

    L'interfaccia segue la lingua del computer, e quello che c'è su una
    macchina non dice niente di come sta scritta una verifica: sulla CI, che è
    in inglese, un controllo che cerca una voce di menu per nome la troverebbe
    tradotta. Qui si mette l'italico, che è la lingua del sorgente e quella che
    i controlli citano.

    Le verifiche dell'inglese sono a parte, in ``test_i18n.py``, e non passano
    di qui: impostano la lingua loro.
    """
    from pdfeditor.core import i18n

    i18n.set_lingua_di_sistema("it")
    return i18n.set_lingua("it")
