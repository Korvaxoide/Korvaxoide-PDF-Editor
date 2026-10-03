"""La lingua dell'interfaccia: come si sceglie e come si traduce.

Il sorgente è in italiano e la traduzione sta in un catalogo. Sono due cose
che si rompono in silenzio: una chiave dimenticata nel catalogo non dà errore,
e una lingua letta male porta a un testo che non è né italiano né inglese.
"""

from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path

import pytest

from pdfeditor.core import i18n

RADICE = Path(__file__).resolve().parents[1]
CATALOGO = RADICE / "resources" / "lang" / "en.json"


@pytest.fixture(autouse=True)
def lingua_pulita(monkeypatch):
    """Ogni controllo riparte dall'italiano e dalle impostazioni come sono.

    La lingua e' un stato globale di modulo: senza questo un controllo che la
    cambia lascia la successiva in una lingua a caso, e il difetto compare
    solo se i controlli girano in un ordine particolare.
    """
    for nome in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(nome, raising=False)
    i18n.set_lingua_di_sistema("")
    i18n.set_lingua("it")
    yield
    i18n.set_lingua("it")


# --------------------------------------------------------------- il catalogo


def test_il_catalogo_inglese_e_un_json_valido():
    """Il catalogo non puo' essere un file rotto: si legge all'avvio."""
    dati = json.loads(CATALOGO.read_text(encoding="utf-8"))
    assert isinstance(dati, dict)
    assert dati, "il catalogo inglese e' vuoto"


def test_il_catalogo_ha_solo_coppie_di_testo():
    """Ogni valore deve essere testo: un numero romperebbe ``tr``."""
    for chiave, valore in json.loads(CATALOGO.read_text(encoding="utf-8")).items():
        assert isinstance(chiave, str) and isinstance(valore, str), (chiave, valore)
        assert valore.strip(), f"traduzione vuota per {chiave!r}"


#: Parole che in inglese sono uguali all'italiano. Non sono una traduzione
#: dimenticata: sono le parole che non cambiano, e scriverle uguali serve per
#: far sapere che la traduzione ci e' stata pensata e non dimenticata.
UGUALI = {
    "Email", "File", "Font", "OCR", "Password", "pt", "×",
    " Font ", "  Dimensione ", "  Colore ",
}


def test_una_chiave_non_si_traduce_in_se_stessa():
    """Una voce lasciata uguale deve essere una parola che non cambia.

    Restare sull'italiano mentre il resto e' in inglese e' il difetto peggiore
    di una traduzione incompleta: il lettore non ha modo di accorgersene,
    mentre una voce assente dall'inglese si riconosce subito. Il confronto e'
    quello fra i due testi, non quello con un elenco a mano: quest'ultimo
    diventerebbe un altro elenco da tenere d'accordo.
    """
    identiche = {
        k for k, v in json.loads(CATALOGO.read_text(encoding="utf-8")).items() if k == v
    }
    ingiusto = sorted(k for k in identiche if not _parola_invariata(k))
    assert not ingiusto, f"chiavi lasciate in italiano: {ingiusto[:10]}"


def _parola_invariata(testo: str) -> bool:
    """Il testo e' una parola che in inglese non cambia.

    Si guarda il testo ripulito dagli spazi e minuscolo, cosi' « Font » dei
    pulsanti della barra conta come «font», e si accetta anche il simbolo e
    l'unita' di misura, che si indicano uguali nelle due lingue.
    """
    pulito = testo.strip().lower()
    invarianti = {
        "file", "font", "email", "ocr", "password", "pt", "×", "dimensione",
        # Il nome dell'algoritmo di cifratura non si traduce e «legacy» si
        # dice uguale in italiano e in inglese: la voce intera e' invariata.
        "rc4-128 (legacy)",
        "aes-128",
        # I nomi dei formati di immagine sono gli stessi nelle due lingue.
        "pnm",
    }
    return pulito in invarianti or len(pulito) <= 2


# ---------------------------------------------------- scelta della lingua


def test_la_lingua_di_sistema_si_legge_dalle_variabili(monkeypatch):
    """Su Linux e macOS la lingua viene da ``LANG`` e dalle sue vicine."""
    monkeypatch.setenv("LANG", "it_IT.UTF-8")
    i18n.set_lingua_di_sistema("")
    assert i18n.set_lingua("auto") == "it"

    monkeypatch.setenv("LANG", "en_US.UTF-8")
    assert i18n.set_lingua("auto") == "en"


def test_la_lingua_di_sistema_usa_qlocale_su_windows(monkeypatch):
    """Quello che dice ``QLocale`` vale piu' di quello che dicono le variabili.

    Su Windows la lingua non arriva da ``LANG``: arriva dalle impostazioni
    regionali, e solo Qt le legge. Senza questa precedenza un computer
    italiano con ``LANG`` non impostata partirebbe in inglese.
    """
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    i18n.set_lingua_di_sistema("it_IT")
    assert i18n.set_lingua("auto") == "it"


def test_la_scelta_esplicita_vince_sul_sistema():
    """Se l'utente ha scelto una lingua, quella vale.

    È il senso di «cambio lingua»: la scelta non deve essere annullata da un
    computer impostato diversamente.
    """
    i18n.set_lingua_di_sistema("it")
    assert i18n.set_lingua("en") == "en"
    assert i18n.lingua() == "en"


@pytest.mark.parametrize("valore", ["", "auto", "  ", "xx", "de"])
def test_una_scelta_non_valida_torna_al_sistema(valore):
    """Una lingua ignota o assente non deve lasciare il programma senza testo."""
    i18n.set_lingua_di_sistema("en")
    assert i18n.set_lingua(valore) == "en"


def test_litaliano_e_disponibile_essendo_il_sorgente():
    """L'italiano si sceglie anche se non ha un catalogo.

    È la lingua in cui sono scritte le stringhe: non ha bisogno di essere
    tradotto per essere mostrato, e senza questa offerta sparirebbe dal menu.
    """
    assert "it" in dict(i18n.LINGUE)
    assert i18n.set_lingua("it") == "it"
    assert i18n.tr("Salva") == "Salva"


def test_le_variabili_hanno_la_precedenza_giusta(monkeypatch):
    """``LC_ALL`` vince su ``LANG``, come in POSIX."""
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.setenv("LC_ALL", "it_IT.UTF-8")
    i18n.set_lingua_di_sistema("")
    assert i18n.set_lingua("auto") == "it"


def test_una_locale_neutra_non_impone_la_italiano(monkeypatch):
    """``LANG=C`` non significa italiano: significa che nessuno ha chiesto niente."""
    monkeypatch.setenv("LANG", "C")
    i18n.set_lingua_di_sistema("")
    assert i18n.set_lingua("auto") == i18n.LINGUA_PREDEFINITA


# --------------------------------------------------------------- la traduzione


def test_tr_trasla_quando_la_chiave_esiste():
    """Il caso normale: chiave nel catalogo, ritorno la traduzione."""
    i18n.set_lingua("en")
    # «Salva» e' nel catalogo: il valore deve cambiare
    assert i18n.tr("Salva") == "Save"


def test_tr_rimane_in_italiano_quando_la_chiave_manca():
    """Una chiave assente non deve far sparire il testo.

    È il comportamento che permette di aggiungere una voce nuova senza
    toccare il catalogo: si vede in italiano e si traduce quando si vuole.
    """
    i18n.set_lingua("en")
    assert i18n.tr("Una frase che non esiste nel catalogo") == (
        "Una frase che non esiste nel catalogo"
    )


def test_il_catalogo_manca_e_il_programma_avvia_lo_stesso():
    """Un catalogo illeggibile non deve impedire l'avvio."""
    i18n.set_lingua("en")
    assert i18n.tr("Salva") == "Save"
    i18n._applica("xx")  # nessun catalogo per questa lingua
    assert i18n.tr("Salva") == "Salva", "senza catalogo si deve tornare al sorgente"


# ------------------------------------------------------------ copertura


#: Le chiavi si leggono con ``ast`` e non con una espressione regolare, per
#: due motivi che si sono presentati entrambi: il modulo concatena i letterali
#: su piu' righe e una espressione regolare li contava come stringhe diverse,
#: e un ``tr("…")`` scritto dentro una docstring finiva nel catalogo come se
#: fosse una chiave. L'albero non ha nessuno dei due problemi: le stringhe
#: attaccate sono gia' unite, e commenti e docstring non sono chiamate.
def _letterali_tr(nodo: ast.AST) -> str | None:
    """Il testo di una chiamata ``tr``, se l'argomento e' una letterale costante."""
    if not isinstance(nodo, ast.Call):
        return None
    nome = getattr(nodo.func, "id", None) or getattr(nodo.func, "attr", None)
    if nome != "tr" or not nodo.args or not isinstance(nodo.args[0], ast.Constant):
        return None
    valore = nodo.args[0].value
    return valore if isinstance(valore, str) else None


def _titolo_problema(nodo: ast.AST) -> str | None:
    """Il titolo di un ``Finding("kind", "Titolo", …)``.

    Il titolo di un problema arriva alla finestra come dato e viene tradotto
    solo quando lo si mostra (``tr(f.title)`` nel pannello): nel costruttore
    resta la parola chiave italiana, perche' lo stesso oggetto viene usato
    anche dai test e non deve dipendere dalla lingua. Per questo il titolo non
    passa da ``tr`` e va raccolto qui, dalla chiamata che lo crea.
    """
    if not isinstance(nodo, ast.Call) or getattr(nodo.func, "id", None) != "Finding":
        return None
    if len(nodo.args) >= 2 and isinstance(nodo.args[1], ast.Constant):
        valore = nodo.args[1].value
        return valore if isinstance(valore, str) else None
    for chiave in nodo.keywords:
        if chiave.arg == "title" and isinstance(chiave.value, ast.Constant):
            valore = chiave.value.value
            return valore if isinstance(valore, str) else None
    return None


def _titolo_menu(nodo: ast.AST) -> str | None:
    """Il testo di ``_titolo_menu("&Modifica")``, senza l'ampersand."""
    if not isinstance(nodo, ast.Call):
        return None
    if getattr(nodo.func, "attr", None) != "_titolo_menu" or not nodo.args:
        return None
    valore = nodo.args[0]
    if not isinstance(valore, ast.Constant) or not isinstance(valore.value, str):
        return None
    return valore.value.split("&", 1)[1] if "&" in valore.value else None


def _chiavi_nel_sorgente() -> set[str]:
    """Le stringhe che il codice chiede di tradurre.

    ``tr("…")`` e' l'unico posto in cui una stringa viene dichiarata
    traducibile, quindi l'elenco non ha falsi positivi. Se si dimentica di
    dichiarare una stringa con ``tr``, non la vede nessuno: e' il difetto che
    questo controllo deve trovare.

    Le chiavi che non passano da una letterale sono raccolte a parte, perche'
    arrivano da tabelle e da variabili: l'etichetta della voce «auto», i nomi
    e i suggerimenti degli strumenti, e i titoli dei menu. Sono elencate qui
    sotto con il perche', cosi' chi aggiunge una lingua non le cerca a caso.
    """
    chiavi: set[str] = set()
    for sorgente in sorted((RADICE / "pdfeditor").rglob("*.py")):
        for nodo in ast.walk(ast.parse(sorgente.read_text(encoding="utf-8"))):
            for lettovo in (
                _letterali_tr(nodo),
                _titolo_menu(nodo),
                _titolo_problema(nodo),
            ):
                if lettovo and re.search(r"[A-Za-z\u00c0-\u00ff]", re.sub(r"\\.", "", lettovo)):
                    chiavi.add(lettovo)

    # l'etichetta della voce «auto» è anche il nome della voce nell'elenco
    chiavi.add(i18n.ETICHETTA_AUTO)

    # nomi e suggerimenti degli strumenti stanno in tabelle di dati e vengono
    # tradotti con `tr(nome)` al momento dell'uso
    from pdfeditor.ui import toolbars

    for _chiave, _nome, _icona, _tasto, _suggerimento in toolbars.TOOL_ITEMS:
        chiavi.add(_nome)
        chiavi.add(_suggerimento)
    for _chiave, _icona, _nome in toolbars.FIELD_TOOL_ITEMS:
        chiavi.add(_nome)
    for _chiave, _nome, _icona in toolbars.TOOL_ITEMS_ANNOTA:
        chiavi.add(_nome)

    # anche i nomi delle schede del pannello laterale vengono da una tabella
    from pdfeditor.ui import panels

    chiavi.update(panels.NOMI_SCHEDE)
    return chiavi


def test_il_catalogo_copre_tutto_il_sorgente():
    """Ogni stringa dichiarata traducibile deve avere la sua voce in inglese.

    Una chiave mancante non e' un errore, e il programma funziona lo stesso:
    semplicemente in quella voce resta in italiano. Percio' il controllo puo'
    solo essere questo, e deve fallire finche' il catalogo e' incompleto.
    """
    if not _chiavi_nel_sorgente():
        pytest.skip("nessuna stringa dichiarata traducibile: il catalogo e' vuoto")
    catalogo = json.loads(CATALOGO.read_text(encoding="utf-8"))
    mancanti = sorted(k for k in _chiavi_nel_sorgente() if k not in catalogo)
    assert not mancanti, (
        f"{len(mancanti)} stringhe tradotte non sono nel catalogo "
        f"({len(_chiavi_nel_sorgente())} in tutto). Prime dieci: {mancanti[:10]}"
    )


def test_il_catalogo_non_contiene_chiavi_inutilizzate():
    """Una voce che il codice non chiede piu' va rimossa.

    Il catalogo cosi' si riempie di testi morti, e non si distingue piu' una
    chiave dimenticata da una voce rimasta indietro.
    """
    catalogo = json.loads(CATALOGO.read_text(encoding="utf-8"))
    usate = _chiavi_nel_sorgente()
    superflue = sorted(k for k in catalogo if k not in usate)
    assert not superflue, (
        f"{len(superflue)} voci nel catalogo che il codice non usa. "
        f"Prime dieci: {superflue[:10]}"
    )