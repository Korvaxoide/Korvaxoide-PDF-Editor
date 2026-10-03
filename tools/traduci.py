"""Rende traducibili le stringhe dell'interfaccia, una volta sola.

Mette ``tr("…")`` attorno ai letterali che finiscono a schermo. Il lavoro è
meccanico perché i testi sono già in italiano e la chiave di traduzione è il
testo stesso: non si sceglie nulla, si cambia solo dove viene costruito il
testo. Gli f-string non vengono toccati, perché per tradurli serve un
segnaposto con nome e vanno riscritti a mano: metterli in chiaro si vedrebbe
solo in italiano, che è la metà del problema.

    python tools/traduci.py            applica
    python tools/traduci.py --solo     conta e non scrive
    python tools/traduci.py --tutto    elenca ogni stringa toccata
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Chiamate da tradurre, con la posizione dell'argomento: 0 è il primo, 1 il
#: secondo. ``_error(exc, "Titolo")`` ha l'eccezione al primo posto, quindi la
#: sua firma non è in elenco: il titolo la chiama già con `_status(tr(…))``.
CALLS: tuple[tuple[str, int], ...] = (
    ("setText", 0),
    ("setToolTip", 0),
    ("setPlaceholderText", 0),
    ("setStatusTip", 0),
    ("setWindowTitle", 0),
    ("setWhatsThis", 0),
    ("setItemText", 0),
    ("addTab", 1),   # addTab(widget, titolo): il testo e' il secondo
    ("setWindowTitle", 0),
    ("addItem", 0),
    ("insertItem", 0),
    ("addRow", 0),
    ("QAction", 0),
    ("QLabel", 0),
    ("QCheckBox", 0),
    ("QRadioButton", 0),
    ("QPushButton", 0),
    ("QGroupBox", 0),
    ("_status", 0),
    ("_confirm", 0),
    ("_confirm", 1),
    # aiuti propri del progetto: il testo non e' il primo argomento
    ("_mi", 1),          # (menu, testo, scorciatoia, slot, icona)
    ("add", 1),          # add(chiave, testo, icona, slot, scorciatoia, suggerimento)
    # i messaggi di Qt: il primo argomento e' il genitore
    # il primo argomento di tutti questi e' il genitore, il secondo il titolo,
    # il terzo il testo: serve tradurre titolo e testo, non il genitore
    ("QMessageBox.warning", 1),
    ("QMessageBox.warning", 2),
    ("QMessageBox.information", 1),
    ("QMessageBox.information", 2),
    ("QMessageBox.critical", 1),
    ("QMessageBox.critical", 2),
    ("QMessageBox.question", 1),
    ("QMessageBox.question", 2),
)

#: Un argomento, da saltare per arrivare al successivo. Non puo' contenere una
#: virgola in cima, altrimenti ``add("new", "Nuovo", "doc", slot, "Ctrl+N")``
#: verrebbe letto come se il testo fosse l'ultimo argomento e la traduzione
#: finirebbe sulle scorciatoie. Le parentesi, le graffe e le quadre si possono
#: contenere: ``lambda: x``, ``[a, b]`` e ``{"k": "v"}`` sono un argomento solo.
_ARG = r"(?:[^,()\[\]{}]|\([^()]*\)|\[[^\]]*\]|\{[^}]*\})*"
#: Un letterale. Stringhe attaccate una all'altra sono una sola frase: vanno
#: racchiuse tutte insieme in ``tr``, altrimenti la seconda resta fuori e
#: non viene tradotta. Le concatenazioni esplicite con «+» non si toccano:
#: sono gia' separate e volute.
_FRAGMENTO = r'"(?:[^"\\\n]|\\.)*"'
_TESTO = rf'((?:{_FRAGMENTO})(?:\s*(?:\n\s*)?{_FRAGMENTO})*)'

_toccate: list[str] = []


#: Chiamati che non possono essere preceduti da un punto, perché il nome è
#: generico e `qualcosa.add(…)` non è il nostro aiuto. Gli altri si chiamano
#: anche come metodi (`tabs.addTab`, `self.setText`) e vietare il punto li
#: escludeva: la traduzione delle voci di menu non partiva.
SOLO_CHIAMATI: frozenset[str] = frozenset({"add"})


def _costruisci(metodo: str, posizione: int) -> re.Pattern[str]:
    """Il chiamato, con l'argomento alla posizione richiesta.

    Si saltano tanti argomenti quanti ne servono: ``QMessageBox.information``
    ha il genitore al primo posto e il testo al terzo, e saltarne uno solo
    traduceva il titolo e lasciava in italiano la domanda.
    """
    dietro = r'(?<![\w.])' if metodo in SOLO_CHIAMATI else r'(?<![\w])'
    saltati = "".join(rf"{_ARG}\s*,\s*" for _ in range(posizione))
    return re.compile(rf"{dietro}{re.escape(metodo)}\(\s*{saltati}{_TESTO}")


def _sostituisci(m: re.Match[str]) -> str:
    """Il chiamato con l'argomento racchiuso in ``tr``.

    Le stringhe attaccate una all'altra diventano un argomento solo dentro
    ``tr``: senza questo la seconda frase resta fuori dalla traduzione e in
    inglese si vede metà messaggio in una lingua e metà nell'altra.
    """
    intero = m.group(0)
    grezzi = re.findall(_FRAGMENTO, m.group(1))
    contenuto = "".join(g[1:-1] for g in grezzi)
    # già tradotto: ``tr("…")`` ha la parentesi aperta subito prima
    if intero[: intero.rindex('"')].rstrip().endswith("tr("):
        return intero
    # f-string e stringhe con interpolazione: da riscrivere a mano
    if "{" in contenuto:
        return intero
    # La lettera si cerca dopo aver tolto gli escape: in «\n» la «n» è una
    # lettera, e senza questo il separatore di una ``"\n".join(…)`` finiva
    # dentro la traduzione, con metà messaggio in italiano e metà in inglese.
    spoglia = re.sub(r"\\.", "", contenuto)
    if not re.search(r"[A-Za-zÀ-ÿ]", spoglia):
        return intero  # numeri, segni, chiavi di formato
    if re.fullmatch(r"#[0-9a-fA-F]{3,8}", contenuto.strip()):
        return intero  # codice colore: e' il valore che va al motore, non un testo
    _toccate.append(f"{contenuto[:78]}")
    return intero.replace(m.group(1), f'tr({m.group(1)})', 1)


def traduci_file(percorso: Path, scrivi: bool) -> int:
    testo = percorso.read_text(encoding="utf-8")
    iniziale = len(_toccate)
    for metodo, posizione in CALLS:
        testo = _costruisci(metodo, posizione).sub(_sostituisci, testo)
    if scrivi and testo != percorso.read_text(encoding="utf-8"):
        percorso.write_text(testo, encoding="utf-8")
    return len(_toccate) - iniziale


def chiavi_mancanti() -> list[str]:
    """Le chiavi che il codice dichiara traducibili e il catalogo non ha.

    Serve al controllo sulla copertura e a chi aggiunge una lingua: il
    catalogo si guarda da solo, ma le chiavi stanno nel sorgente e non si
    vedono a colpo d'occhio.

    Le chiavi che passano da una variabile — i nomi degli strumenti, delle
    schede e dei menu — non si trovano con questa ricerca: sono elencate a
    mano in tests/test_i18n.py, dove si spiega il perche' ognuna sta dove sta.
    """
    mancanti: list[str] = []
    for sorgente in sorted((ROOT / "pdfeditor").rglob("*.py")):
        for chiave in _chiavi(sorgente):
            if not _ha(chiave):
                mancanti.append(chiave)
    return mancanti


def _ha(chiave: str) -> bool:
    import json

    percorso = ROOT / "resources" / "lang" / f"{lingua_catalogo()}.json"
    try:
        return chiave in json.loads(percorso.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False


#: Un codice lingua: due lettere, eventualmente con regione.
CODICE_LINGUA = re.compile(r"^[a-z]{2,3}(-[A-Za-z]{2,4})?$")


def lingua_catalogo() -> str:
    """Il codice della lingua di cui si controlla la copertura.

    Si accetta ``traduci.py en`` o ``traduci.py -l en``, ma solo se l'argomento
    *sembra* un codice lingua. Prima si leggeva il primo argomento qualsiasi:
    sotto pytest quello era il percorso del test, il catalogo non si apriva e
    ogni chiave risultava mancante.
    """
    argomenti = [a for a in sys.argv[1:] if a != "--solo"]
    if argomenti and CODICE_LINGUA.match(argomenti[0]):
        return argomenti[0]
    for posizione, valore in enumerate(argomenti):
        if valore in {"-l", "--lingua"} and posizione + 1 < len(argomenti):
            return argomenti[posizione + 1]
    return "en"


def _chiavi(sorgente: Path) -> set[str]:
    """Le chiavi di un file, lette con ``ast``.

    Con l'albero le stringhe attaccate su piu' righe sono gia' unite e un
    ``tr("…")`` dentro una docstring non viene preso: con un'espressione
    regolare si erano presentati entrambi come chiavi, e una era una frase che
    spiega il codice.
    """
    chiavi: set[str] = set()
    for nodo in ast.walk(ast.parse(sorgente.read_text(encoding="utf-8"))):
        if not isinstance(nodo, ast.Call) or not nodo.args:
            continue
        nome = getattr(nodo.func, "id", None) or getattr(nodo.func, "attr", None)
        if nome != "tr" or not isinstance(nodo.args[0], ast.Constant):
            continue
        valore = nodo.args[0].value
        if isinstance(valore, str) and re.search(r"[A-Za-zÀ-ÿ]", re.sub(r"\\.", "", valore)):
            chiavi.add(valore)
    return chiavi


def main() -> int:
    scrivi = "--solo" not in sys.argv
    obiettivi = sorted(
        p for p in (ROOT / "pdfeditor/ui").rglob("*.py") if "items" not in p.parts
    )
    totale = 0
    for p in obiettivi:
        inizio = len(_toccate)
        traduci_file(p, scrivi)
        if len(_toccate) > inizio:
            print(f"{len(_toccate) - inizio:4}  {p.relative_to(ROOT)}")
            totale += len(_toccate) - inizio
    if "--tutto" in sys.argv:
        for riga in _toccate:
            print(f"    {riga}")
    print(f"\n{totale} stringhe rese traducibili")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())