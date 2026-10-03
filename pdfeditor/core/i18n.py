"""Traduzione dei testi dell'interfaccia.

L'italiano è la lingua del sorgente: le stringhe sono scritte in italiano nel
codice e non esiste un catalogo italiano. L'inglese vive in
``resources/lang/en.json``, che è una corrispondenza italiano → inglese. Una
chiave assente dal catalogo resta in italiano, come in ogni altra traduzione:
è il comportamento che si vuole, perché un testo nuovo si vede subito in
italiano invece di sparire.

Non si è scelto di scrivere anche un ``it.json``. Significherebbe copiare
cinquecento stringhe dal sorgente e tenerle d'accordo a mano: la prima volta
che una voce di menu cambia e ``it.json`` no, l'italiano mostra il testo vecchio
mentre l'inglese mostra quello nuovo, senza che nessuno se ne accorga.

Il modulo non importa Qt. ``core/`` non deve conoscere l'interfaccia, e qui si
traducono anche i messaggi di errore del motore, che finiscono in una
finestra. La lingua di sistema la decide l'avvio con ``QLocale`` e la comunica
con :func:`set_lingua_di_sistema`; in sua assenza si ricava dalle variabili
d'ambiente, che su Linux e macOS danno lo stesso risultato e su Windows
servono solo come riserva.
"""

from __future__ import annotations

import json
import os
import sys
from functools import lru_cache
from pathlib import Path

#: L'etichetta della voce «auto» è l'unica che si traduce. I nomi delle
#: lingue sono endonimi e restano come sono: chi cerca «English» la trova anche
#: con l'interfaccia in italiano.
ETICHETTA_AUTO = "Sistema"

#: Lingue offerte nell'interfaccia, nell'ordine in cui sono mostrate.
#: Il codice è quello di ISO 639-1; «auto» segue la lingua del sistema.
LINGUE: tuple[tuple[str, str], ...] = (
    ("auto", ETICHETTA_AUTO),
    ("en", "English"),
    ("it", "Italiano"),
)

#: Lingue con un catalogo. «it» non ce l'ha perche' e' la lingua del sorgente.
LINGUE_CON_CATALOGO: tuple[str, ...] = ("en",)

#: La lingua del sistema, quando non e' riconosciuta.
LINGUA_PREDEFINITA = "en"

_corrente = "it"
_catalogo: dict[str, str] = {}
_lingua_di_sistema = ""


# --------------------------------------------------------------- catalogo


def _carelle() -> list[Path]:
    """Dove può stare il catalogo, nell'ordine in cui va provato.

    Il primo percorso vale quando si esegue dal sorgente. Gli altri servono
    per l'eseguibile pacchettizzato, dove i dati finiscono sotto
    ``sys._MEIPASS`` e il percorso del sorgente non esiste più.
    """
    radice = Path(__file__).resolve().parents[2]
    candidati = [radice / "resources" / "lang", Path(sys.executable).resolve().parent / "resources" / "lang"]
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        candidati.insert(1, Path(meipass) / "resources" / "lang")
    return candidati


@lru_cache(maxsize=8)
def _carica(codice: str) -> dict[str, str]:
    """Il catalogo di una lingua, vuoto se non c'è.

    Il risultato è messo in cache: il catalogo non cambia durante la sessione e
    ``tr`` si chiama qualche centinaia di volte all'avvio.
    """
    if not codice:
        return {}
    for cartella in _carelle():
        percorso = cartella / f"{codice}.json"
        try:
            if percorso.is_file():
                dati = json.loads(percorso.read_text(encoding="utf-8"))
                if isinstance(dati, dict):
                    return {str(k): str(v) for k, v in dati.items()}
        except (OSError, ValueError):
            # Un catalogo illeggibile non deve impedire di avviare il
            # programma: si resta nella lingua del sorgente.
            return {}
    return {}


def _applica(codice: str) -> None:
    global _corrente, _catalogo
    _corrente = codice
    _catalogo = _carica(codice) if codice in LINGUE_CON_CATALOGO else {}


# ------------------------------------------------------------- rilevamento


def _base(codice: str) -> str:
    """La parte di lingua di un codice: «it_IT.UTF-8» e «it-CH» diventano «it».

    Tutti i codici che arrivano da QLocale e dalle variabili d'ambiente passano
    di qui. La normalizzazione sta in un posto solo perche' dividerla era
    quello che l'aveva rotta: ``it_IT`` non veniva riconosciuto e un computer
    italiano partiva in inglese.
    """
    return (codice or "").split("@")[0].split(".")[0].replace("-", "_").split("_")[0].lower()


def _da_ambiente() -> str:
    """La lingua dichiarata dalle variabili d'ambiente.

    ``LC_ALL`` ha la precedenza su ``LC_MESSAGES`` e su ``LANG``, come in POSIX.
    ``LANGUAGE`` è la forma di GNU per più lingue ed ha la precedenza sulle
    altre quando elenca il punto e virgola.
    """
    per_langua = os.environ.get("LANGUAGE", "")
    if per_langua:
        prima = per_langua.split(":")[0]
        if prima and prima not in ("C", "POSIX"):
            return _base(prima)
    for nome in ("LC_ALL", "LC_MESSAGES", "LANG"):
        valore = os.environ.get(nome, "")
        if valore and valore not in ("C", "POSIX"):
            return _base(valore)
    return ""


def _riconosci(codice: str) -> str:
    """Il codice riconosciuto fra quelli che il programma sa usare.

    «it-CH» e «it_IT» diventano «it»: quello che conta è la lingua, non la
    regione. Un codice che il programma non offre torna vuoto e lascia scegliere
    la lingua predefinita, perché è sempre meglio un testo in inglese che un
    testo in italiano a metà.
    """
    base = _base(codice)
    return base if base in LINGUE_CON_CATALOGO or base == "it" else ""


def set_lingua_di_sistema(codice: str) -> None:
    """Comunica la lingua del sistema, se ``QLocale`` e' disponibile.

    Su Windows la lingua del sistema non viene dalle variabili d'ambiente ma
    dalle impostazioni regionali: solo Qt la legge correttamente, e questa e'
    la ragione per cui la chiama l'avvio invece di farlo qui.
    """
    global _lingua_di_sistema
    _lingua_di_sistema = _riconosci(codice or "")


def lingua_di_sistema() -> str:
    """La lingua che si userebbe se non ce ne fosse una scelta esplicita."""
    if _lingua_di_sistema:
        return _lingua_di_sistema
    riconosciuta = _riconosci(_da_ambiente())
    if riconosciuta:
        return riconosciuta
    return LINGUA_PREDEFINITA


# ------------------------------------------------------------------ stato


def lingua() -> str:
    """Il codice della lingua in uso, «auto» se segue il sistema."""
    return _corrente


def set_lingua(preferita: str) -> str:
    """Imposta la lingua e restituisce quella effettivamente adottata.

    «auto», la stringa vuota e un codice sconosciuto tornano alla lingua del
    sistema. Una lingua senza catalogo (l'italiano) resta l'italiano: e' il
    sorgente, quindi non ha bisogno di traduzione per essere usata.
    """
    codice = (preferita or "").strip().lower()
    if codice in ("", "auto"):
        codice = lingua_di_sistema()
    if codice not in LINGUE_CON_CATALOGO and codice != "it":
        codice = lingua_di_sistema()
    _applica(codice)
    return codice


def inizializza(preferita: str = "") -> str:
    """Imposta la lingua all'avvio: scelta dell'utente, altrimenti il sistema."""
    return set_lingua(preferita)


# ------------------------------------------------------------- traduzione


def tr(testo: str) -> str:
    """Il testo nella lingua in uso.

    La chiave e' il testo italiano del sorgente. Una chiave assente, o uguale
    al valore, restituisce il testo stesso: e' cio' che rende possibile
    aggiungere una voce nuova senza toccare nessun catalogo e vederla comunque
    in italiano.
    """
    if not _catalogo:
        return testo
    return _catalogo.get(testo, testo)


def esiste(testo: str) -> bool:
    """Il testo è una chiave del catalogo della lingua in uso.

    Serve al controllo sulla copertura: il catalogo non può essere valutato a
    occhio, e una chiave dimenticata si vede solo in inglese, dove il lettore
    non ha nulla su cui confrontarla.
    """
    return testo in _catalogo


_applica(LINGUA_PREDEFINITA)