"""Trova i messaggi con un valore dentro che non passano dalla traduzione.

Un testo senza variabili si traduce racchiudendolo in ``tr``: il lavoro è
meccanico e il catalogo lo controlla da sé. Un testo con un valore dentro è
un'altra cosa: per tradurlo serve un segnaposto con nome, altrimenti l'ordine
delle parole resta quello dell'italiano e in inglese il messaggio suona
sbagliato anche se tutte le parole ci sono.

Il pericolo di questi è che non si vedono: ``f"File non trovato: {p}"`` è
un testo perfettamente funzionante in italiano, e senza un controllo non si
scopre che in inglese resta italiano. Qui si cercano con ``ast``, che distingue
una ``f``-stringa da una stringa con una ``tr`` intorno.
"""

from __future__ import annotations

import ast
import re
import string
import sys
from pathlib import Path

import pytest

RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RADICE / "tools"))

import traduci  # noqa: E402

#: Chiamate che finiscono in una finestra o nella barra di stato. `_error` ha
#: l'eccezione al primo posto e il titolo al secondo: si guarda il primo
#: argomento che sia una stringa, altrimenti si tradurrebbe il titolo due volte
#: e il messaggio dell'eccezione resterebbe italiano.
DESTINATARI = {"_status", "_confirm", "_warn_encryption_lost"}

#: Metodi di Qt che mettono il testo sul schermo.
QUANTITA = {"setText", "setToolTip", "setPlaceholderText", "setStatusTip",
            "setWindowTitle", "setWhatsThis", "addTab", "setItemText"}

#: Nomi di eccezione: il testo finisce nella finestra di errore.
ECCEZIONI = {"Error", "DocumentError", "SignatureError", "QualityError"}


def _messaggi_non_tradotti(sorgente: Path) -> list[tuple[int, str]]:
    """Le ``f``-stringhe che arrivano all'utente senza passare da ``tr``."""
    albero = ast.parse(sorgente.read_text(encoding="utf-8"))
    trovati: list[tuple[int, str]] = []

    for nodo in ast.walk(albero):
        if isinstance(nodo, ast.Call):
            nome = getattr(nodo.func, "attr", None)
            # un messaggio composto prima: `messaggio = f"…"` e poi
            # `self._status(messaggio)` non si vedono dal chiamato, e sono
            # metà dei casi. Si guarda anche la variabile che si passa.
            if nome in DESTINATARI or nome in QUANTITA:
                for argomento in nodo.args:
                    trovati += [(nodo.lineno, t) for t in _messaggi_negli_argomenti(argomento, sorgente)]
            elif nome == "_error":
                # l'eccezione puo' essere una stringa gia' composta
                if nodo.args:
                    primo = nodo.args[0]
                    if isinstance(primo, ast.JoinedStr) and _ha_testo(primo):
                        trovati.append((nodo.lineno, _testo(primo)))
                    elif isinstance(primo, ast.Name):
                        trovati += [
                            (nodo.lineno, t) for t in _assegnazioni(sorgente, primo.id)
                        ]
            elif nome and nome.startswith("QMessageBox"):
                # il testo e' il terzo argomento, il titolo il secondo
                for argomento in nodo.args[1:]:
                    trovati += [(nodo.lineno, t) for t in _messaggi_negli_argomenti(argomento, sorgente)]
        # raise DocumentError(f"…")
        if isinstance(nodo, ast.Raise) and isinstance(nodo.exc, ast.Call):
            eccezione = getattr(nodo.exc.func, "id", "")
            if eccezione in ECCEZIONI:
                for argomento in nodo.exc.args:
                    if isinstance(argomento, ast.JoinedStr) and _ha_testo(argomento):
                        trovati.append((nodo.lineno, _testo(argomento)))
    return trovati


def _messaggi_negli_argomenti(nodo: ast.AST, sorgente: Path) -> list[str]:
    """I testi da tradurre fra gli argomenti di una chiamata."""
    if isinstance(nodo, ast.JoinedStr):
        return [_testo(nodo)] if _ha_testo(nodo) else []
    if isinstance(nodo, ast.Name):
        # una variabile: si risale a chi l'ha costruita, nello stesso file
        return _assegnazioni(sorgente, nodo.id)
    return []


def _assegnazioni(sorgente: Path, nome: str) -> list[str]:
    """I testi con un valore dentro assegnati a ``nome`` nello stesso file.

    La ricerca e' limitata al file che usa la variabile perche' il nome da solo
    non basta: `testo` e' il nome piu' comune del programma e cercandolo in
    tutto il repository si trovavano le frasi di un altro file, con lo stesso
    nome di variabile e un significato completamente diverso.
    """
    if (sorgente, nome) in _PER_VARIABILE:
        return _PER_VARIABILE[(sorgente, nome)]
    trovati: list[str] = []
    for nodo in ast.walk(ast.parse(sorgente.read_text(encoding="utf-8"))):
        target = valore = None
        if isinstance(nodo, ast.Assign) and nodo.targets:
            target, valore = nodo.targets[0], nodo.value
        elif isinstance(nodo, ast.AnnAssign) and nodo.value is not None:
            target, valore = nodo.target, nodo.value
        if (
            isinstance(target, ast.Name)
            and target.id == nome
            and isinstance(valore, ast.JoinedStr)
            and _ha_testo(valore)
        ):
            trovati.append(_testo(valore))
    _PER_VARIABILE[(sorgente, nome)] = trovati
    return trovati


#: I testi trovati finora, per file e variabile: si cercano una volta sola.
_PER_VARIABILE: dict[tuple[Path, str], list[str]] = {}


def _ha_testo(nodo: ast.JoinedStr) -> bool:
    """La ``f``-stringa contiene testo, e non solo un valore.

    ``f"{v}"`` non e' un messaggio: e' un numero o un nome che passa. Senza
    questo controllo ogni etichetta che mostra una misura verrebbe segnalata
    come traduzione mancante, e il controllo diventerebbe rumore.
    """
    lettere = "".join(
        str(v.value) for v in nodo.values if isinstance(v, ast.Constant) and isinstance(v.value, str)
    )
    return bool(re.search(r"[A-Za-zÀ-ÿ]{2}", re.sub(r"\\.", "", lettere)))


def _testo(nodo: ast.JoinedStr) -> str:
    """Il testo di una ``f``-stringa, con i segnaposto al loro posto."""
    parti = []
    for valore in nodo.values:
        if isinstance(valore, ast.Constant):
            parti.append(str(valore.value))
        else:
            parti.append("{…}")
    return "".join(parti)


def _messaggi_in_qualita(sorgente: Path) -> list[tuple[int, str]]:
    """I testi dei controlli di qualità, che finiscono nel pannello."""
    albero = ast.parse(sorgente.read_text(encoding="utf-8"))
    trovati: list[tuple[int, str]] = []
    for nodo in ast.walk(albero):
        if isinstance(nodo, ast.Call):
            nome = getattr(nodo.func, "id", "")
            if nome not in {"Finding", "_plurale"}:
                continue
            for argomento in nodo.args:
                # `message=` e non il primo argomento: il primo e' il codice
                if isinstance(argomento, ast.JoinedStr):
                    trovati.append((nodo.lineno, _testo(argomento)))
    return trovati


#: Dove si cercano, e come.
SORGENTI = [
    ("core/document.py", _messaggi_non_tradotti),
    ("features/quality.py", _messaggi_in_qualita),
    ("features/digitalsign.py", _messaggi_non_tradotti),
    ("signature/manager.py", _messaggi_non_tradotti),
    ("ui/main_window.py", _messaggi_non_tradotti),
    ("ui/ocr.py", _messaggi_non_tradotti),
    ("ui/panels.py", _messaggi_non_tradotti),
    ("ui/page_view.py", _messaggi_non_tradotti),
    ("ui/printing.py", _messaggi_non_tradotti),
    ("ui/dialogs/props.py", _messaggi_non_tradotti),
    ("ui/dialogs/signature_dialog.py", _messaggi_non_tradotti),
]


@pytest.mark.parametrize("relativo, cerca", SORGENTI, ids=[s for s, _ in SORGENTI])
def test_nessun_messaggio_con_valore_salta_la_traduzione(relativo, cerca):
    """Nessuna ``f``-stringa che arriva all'utente resta in italiano.

    Il messaggio con un valore dentro si traduce con un segnaposto:
    ``tr("File non trovato: {file}").format(file=p)``. Senza, in inglese esce
    metà testo nella lingua sbagliata — e non è un errore che si vede
    confrontando le due versioni, perché manca la versione.
    """
    sorgente = RADICE / "pdfeditor" / relativo
    rimasti = cerca(sorgente)
    assert not rimasti, (
        f"{relativo}: {len(rimasti)} messaggi con un valore dentro non tradotti. "
        f"Primi dieci:\n"
        + "\n".join(f"    riga {riga}: {testo[:70]}" for riga, testo in rimasti[:10])
    )


def test_il_catalogo_conosce_tutti_i_segnaposto():
    """Ogni ``tr`` del programma deve stare nel catalogo.

    Vale per i messaggi con un segnaposto come per gli altri: un segnaposto
    dimenticato non dà errore, lascia solo il messaggio con le parentesi
    graffe al posto del valore.
    """
    mancanti = [k for k in traduci.chiavi_mancanti() if "{…" not in k]
    assert not mancanti, (
        f"{len(mancanti)} chiavi con segnaposto non sono nel catalogo: {mancanti[:10]}"
    )

def _segnaposto_e_parole_formato(relativo: str) -> list[tuple[int, str]]:
    """Chiamate ``tr(...).format(...)`` in cui nome e parola non coincidono.

    ``tr("Operazione «{modo}»…").format(mode=modo)`` si legge bene e funziona
    male: `format` cerca ``{modo}``, non trova la parola ``mode`` e solleva
    `KeyError`. L'errore arriva quando l'utente preme Taglia o Incolla su un
    elemento che non li accetta, e in una finestra sembra che il programma
    abbia scritto qualcosa in console.
    """
    albero = ast.parse((RADICE / "pdfeditor" / relativo).read_text(encoding="utf-8"))
    sbagliati: list[tuple[int, str]] = []
    for nodo in ast.walk(albero):
        if not isinstance(nodo, ast.Call):
            continue
        funzione = nodo.func
        if not (isinstance(funzione, ast.Attribute) and funzione.attr == "format"):
            continue
        chiamata = funzione.value
        if not isinstance(chiamata, ast.Call):
            continue
        nome = getattr(chiamata.func, "id", None) or getattr(chiamata.func, "attr", None)
        if nome not in {"tr", "_tr"} or not chiamata.args:
            continue
        testo = chiamata.args[0]
        if not (isinstance(testo, ast.Constant) and isinstance(testo.value, str)):
            continue
        try:
            campi = {nome for _, nome, _, _ in string.Formatter().parse(testo.value) if nome}
        except ValueError:
            continue
        parole = {kw.arg for kw in nodo.keywords if kw.arg}
        if campi and campi != parole:
            sbagliati.append((nodo.lineno, f"{testo.value!r} con {sorted(parole)}"))
    return sbagliati


@pytest.mark.parametrize("relativo, cerca", SORGENTI, ids=[s for s, _ in SORGENTI])
def test_nessun_segnaposto_ha_il_nome_di_un_altro(relativo, cerca):
    """Ogni segnaposto deve essere riempito con una parola dello stesso nome."""
    sbagliati = _segnaposto_e_parole_formato(relativo)
    assert not sbagliati, (
        f"{relativo}: {len(sbagliati)} messaggi con un segnaposto riempito "
        f"col nome sbagliato:\n"
        + "\n".join(f"    riga {riga}: {testo}" for riga, testo in sbagliati)
    )
