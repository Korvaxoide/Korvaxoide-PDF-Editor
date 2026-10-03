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
import shutil
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


def cartella(nome: str) -> Path:
    """Cartella di lavoro per i file che i test devono produrre.

    Dentro la radice dell'isolamento e non in ``/tmp``: su Windows un
    percorso POSIX diventa ``\\tmp\\...`` sulla radice del disco, dove i test
    non hanno i permessi e dove il file resta aperto da MuPDF con il
    permesso di sostituirlo negato. Cinquanta prove di interazione fallivano
    perche' il PDF di prova finiva li'.
    """
    isola()
    return _cartella(nome)


def ricrea(nome: str) -> Path:
    """Come :func:`cartella`, ma vuota: serve agli script che producono immagini."""
    d = cartella(nome)
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    return d


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


#: Font in cui cercare quello che serve alle verifiche, per sistema. Sono gli
#: stessi candidati che il programma elenca in ``signature/typed.py``.
_FONT = (
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "/System/Library/Fonts/Supplemental/Georgia Italic.ttf",
    r"C:\Windows\Fonts\georgiai.ttf",
    r"C:\Windows\Fonts\timesi.ttf",
)

_font: str | None = None


def font_serif() -> str:
    """Un font serif corsivo presente sul computer, o ``""`` se non ce n'e' uno.

    Le verifiche che scrivono una firma nell'immagine non possono supporre i
    font di Linux: su Windows ``/usr/share/fonts`` non esiste, la firma di
    prova diventava un foglio bianco e la rimozione dello sfondo cancellava
    tutto, facendo fallire otto controlli. Qui il font si cerca dove il
    computer lo mette, e se proprio non c'e' la prova che lo richiede salta
    invece di misurare un foglio vuoto.
    """
    global _font
    if _font is not None:
        return _font
    for cand in _FONT:
        if os.path.exists(cand):
            _font = cand
            return _font
    # nessuno dei noti: si passa per la ricerca del programma, che conosce le
    # cartelle di ogni sistema
    from pdfeditor.signature import typed

    trovati = typed.list_fonts()
    for nome in ("serif", "times", "georgia", "dejavu"):
        for f in trovati:
            if nome in str(f["name"]).lower():
                _font = str(f["path"])
                return _font
    _font = ""
    return _font
