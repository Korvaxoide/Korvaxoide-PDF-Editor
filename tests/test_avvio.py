"""L'avvio non deve portarsi dietro cose che userà più avanti.

Il programma partiva lento e il motivo non si vedeva: le import avvenivano
tutte insieme, in testa a `main_window.py`, e ognuna sembrava ragionevole da
sola. NumPy da solo costa circa 70 ms ed entrava perché `signature.bgremove` lo
importa in cima al file; quel modulo però serve a togliere lo sfondo a una firma
fotografata, e all'avvio nessuno lo chiama. Lo stesso valeva per Pillow e per
quasi duemila righe di finestre di dialogo che l'utente può non aprire mai.

Un costo del genere è invisibile in revisione: nessuno vede un `import` in più
in cima a un file e pensa che qualcosa si sia rotto. Qui si controlla quindi il
risultato, non l'intenzione: si avvia un interprete pulito, gli si fa importare
la finestra principale e si guarda cosa si è portato dietro.

Non si controlla da dentro la sessione di test perché `sys.modules` è una
crescita mai ripresa: la prima verifica che apre una finestra o firma qualcosa
carica Pillow e NumPy per tutte le successive, e l'ordine con cui pytest
raccoglie i test cambierebbe il verdetto. Per questo la misura avviene in un
processo nuovo, una volta sola, e tutte le verifiche leggono quel risultato.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

RADICE = Path(__file__).resolve().parents[1]

#: Cosa chiede all'interprete pulito. L'import è uno solo e voluto: è il
#: momento in cui il programma, in un avvio normale, ha già deciso tutto quello
#: che gli serve per mostrare la finestra. Non si arriva a costruire la finestra
#: perché servirebbe un `QApplication` e un gestore di eventi, e qui si vuole
#: guardare solo il costo delle import.
SONDAGGIO = """
import json, sys
import pdfeditor.ui.main_window  # noqa: F401
import pdfeditor.core.i18n as i18n

print(json.dumps({
    "moduli": sorted(sys.modules),
    "catalogo": len(i18n._catalogo),
}))
"""


@pytest.fixture(scope="module")
def avvio() -> dict:
    """Il referto di un interprete che ha appena importato la finestra."""
    proc = subprocess.run(
        [sys.executable, "-c", SONDAGGIO],
        cwd=RADICE,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"il sondaggio è fallito:\n{proc.stderr}"
    riga = [r for r in proc.stdout.splitlines() if r.startswith("{")]
    assert riga, f"il sondaggio non ha risposto:\n{proc.stdout}\n{proc.stderr}"
    return json.loads(riga[-1])


def _caricati(avvio: dict, prefisso: str) -> list[str]:
    return [m for m in avvio["moduli"] if m == prefisso or m.startswith(prefisso + ".")]


# ------------------------------------------------------- il peso delle librerie


def test_avvio_non_carica_numpy(avvio):
    """NumPy non deve entrare con la finestra principale.

    Il costo è il più grosso di tutti (circa 70 ms) e non serve a nulla fino
    alla firma su sfondo. Sta dentro `signature.bgremove`, che a sua volta ci
    finiva perché `signature.manager` lo importava per poter salvare un PNG.
    """
    assert _caricati(avvio, "numpy") == []


def test_avvio_non_carica_pillow(avvio):
    """Pillow è usata solo dalle firme, non dalla finestra."""
    assert _caricati(avvio, "PIL") == []


def test_avvio_carica_le_librerie_che_servono(avvio):
    """Qt e MuPDF devono essere caricate: le due verifiche sopra sono un divieto.

    Serve a dare un senso al resto: non si chiede all'avvio di non caricare
    niente, si chiede di non caricare quello che non usa. Se un domani smettesse
    di arrivare a MuPDF, il programma non aprirebbe nessun PDF e il divieto su
    NumPy da solo passerebbe senza che nessuno se ne accorga.
    """
    presenti = {m.split(".")[0] for m in avvio["moduli"]}
    mancanti = {"PySide6", "pymupdf"} - presenti
    assert not mancanti, f"l'avvio non ha caricato le librerie che servono: {sorted(mancanti)}"


def test_avvio_non_apre_il_catalogo_inglese(avvio):
    """Importare `i18n` non deve leggere il catalogo.

    Il modulo si chiudeva con `_applica(LINGUA_PREDEFINITA)`, che leggeva e
    interpretava 36 KiB di JSON inglese prima che l'avvio avesse potuto leggere
    la preferenza della lingua. A un utente italiano quel lavoro finiva scartato:
    la lingua è «it» e l'italiano non ha catalogo.
    """
    assert avvio["catalogo"] == 0


# ------------------------------------------------------- i dialoghi pigri


def test_avvio_non_carica_i_dialoghi(avvio):
    """I dialoghi non si costruiscono e non si importano all'avvio.

    `dialogs/props.py` da solo vale circa 8 ms e `signature_dialog.py` altri
    5, più i due che trascinano. Sono finestre che l'utente apre quando vuole.
    """
    assert _caricati(avvio, "pdfeditor.ui.dialogs") == []


def test_nessun_dialoghi_e_importato_in_testa_al_modulo():
    """Il controllo sui dialoghi non può dipendere solo da quello a runtime.

    Una verifica che guarda `sys.modules` dice la verità su come va oggi, ma
    non impedisce a qualcuno di rimettere un import in cima al file domani: il
    costo ci tornerebbe e la verifica passerebbe lo stesso in un altro ordine
    di esecuzione. Qui si legge quindi il sorgente, e si pretende che i moduli
    costosi compaiano dentro i metodi che li usano.
    """
    import ast

    sorgente = (RADICE / "pdfeditor" / "ui" / "main_window.py").read_text(encoding="utf-8")
    albero = ast.parse(sorgente)
    in_testa = []
    for nodo in albero.body:  # solo il livello del modulo
        if isinstance(nodo, (ast.Import, ast.ImportFrom)):
            nomi = [a.name for a in nodo.names]
            modulo = getattr(nodo, "module", "") or ""
            if modulo.startswith("dialogs") or modulo.startswith(".dialogs"):
                in_testa += nomi
            if modulo == "PIL" or "PIL" in nomi:
                in_testa += nomi
    assert in_testa == [], (
        f"import in testa al modulo, che li riporta in ogni avvio: {sorted(in_testa)}. "
        "Vanno dentro i metodi che li usano, con `TYPE_CHECKING` per i tipi."
    )


def test_i_dialoghi_si_aprono_anche_se_importati_pigri(finestra):
    """Il dialogo di proprietà si apre: l'import pigro non l'ha rotto.

    Il rischio di un import spostato dentro il metaggio è che il nome non ci sia
    più: l'errore arriva quando l'utente apre la finestra, cioè tardi e su un
    gesto che nessuno dei test automatici fa per caso.
    """
    from pdfeditor.ui.dialogs import props

    assert props.PreferencesDialog is not None
    dlg = props.PreferencesDialog(finestra.settings, finestra)
    try:
        assert dlg.isModal() or dlg.windowModality() is not None
    finally:
        dlg.deleteLater()


# ------------------------------------------------------------- il recupero


def test_il_recupero_non_chiede_prima_che_la_finestra_esista(app, monkeypatch):
    """Con un documento da recuperare, la domanda arriva dopo la finestra.

    La finestra di recupero è modale, e una modale blocca. Chiamata dal
    costruttore, l'utente vedeva comparire la domanda *prima* della finestra del
    programma e il suo avvio sembrava lentissimo senza esserlo.
    """
    from PySide6.QtWidgets import QMessageBox

    from pdfeditor.core import settings as sm
    from pdfeditor.core.settings import data_dir
    from pdfeditor.ui.main_window import MainWindow

    recupero = data_dir() / "recupero"
    recupero.mkdir(parents=True, exist_ok=True)
    bozza = recupero / "bozza-di-prova.pdf"
    bozza.write_bytes(b"%PDF-1.4\n")

    # `recover` sta nelle preferenze, e la sessione di test lo tiene disattivato
    # per non far comparire finestre. Si accende solo per questa verifica e si
    # rimette com'era: le verifiche che costruiscono una finestra dopo questa
    # leggono le stesse preferenze e devono continuare a non chiedere nulla.
    impostazioni = sm.Settings()
    precedente = impostazioni.get("recover")
    domande: list[bool] = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *_a, **_k: (domande.append(True), QMessageBox.No)[1]),
    )
    impostazioni.set("recover", True)
    try:
        win = MainWindow()
        assert domande == [], "il recupero ha chiesto durante la costruzione"
        app.processEvents()
        assert domande == [True], "il recupero non ha chiesto quando avrebbe dovuto"
        win.deleteLater()
    finally:
        impostazioni.set("recover", precedente)
        bozza.unlink(missing_ok=True)


def test_il_recupero_non_propone_sostituire_il_documento_aperto(app, documento_modello, monkeypatch):
    """Aperto un file, il recupero non chiede di buttarlo via.

    Passando un PDF sulla riga di comando l'utente ha detto quale file vuole; il
    recupero viene valutato dopo, e a quel punto il documento è già aperto.
    """
    from PySide6.QtWidgets import QMessageBox

    from pdfeditor.core import settings as sm
    from pdfeditor.core.settings import data_dir
    from pdfeditor.ui.main_window import MainWindow

    recupero = data_dir() / "recupero"
    recupero.mkdir(parents=True, exist_ok=True)
    bozza = recupero / "bozza-di-prova.pdf"
    bozza.write_bytes(b"%PDF-1.4\n")

    impostazioni = sm.Settings()
    precedente = impostazioni.get("recover")
    domande: list[bool] = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *_a, **_k: (domande.append(True), QMessageBox.No)[1]),
    )
    impostazioni.set("recover", True)
    try:
        win = MainWindow()
        # un documento aperto, come se arrivasse dalla riga di comando
        win.load_path(documento_modello)
        assert win.doc.is_open
        app.processEvents()
        assert domande == [], "ha proposto di sostituire il documento che l'utente ha aperto"
        win.deleteLater()
    finally:
        impostazioni.set("recover", precedente)
        bozza.unlink(missing_ok=True)


# ------------------------------------------------------------ i file recenti


def test_l_elenco_dei_recenti_non_riscrive_le_preferenze(tmp_path):
    """Pulire i file recenti non deve scrivere il disco mentre si costruiscono i menu.

    `recent_files()` viene chiamata da `_rebuild_recent`, cioè durante
    l'avvio. Scrivere li lì metteva dodici controlli `exists` e una riscrittura
    del JSON fra la costruzione della finestra e la sua comparsa. La pulizia non
    si perde: `save()` alla chiusura scrive tutto il dizionario.
    """
    from pdfeditor.core.settings import Settings

    esistente = tmp_path / "resta.pdf"
    esistente.write_bytes(b"%PDF-1.4\n")
    sparito = str(tmp_path / "non-esiste.pdf")
    impostazioni = Settings(path=tmp_path / "settings.json")
    impostazioni.set("recent_files", [str(esistente), sparito])

    prima = (tmp_path / "settings.json").read_text(encoding="utf-8")
    voci = impostazioni.recent_files()
    dopo = (tmp_path / "settings.json").read_text(encoding="utf-8")

    assert sparito not in voci and str(esistente) in voci
    assert prima == dopo, "la pulizia ha scritto le preferenze mentre si costruiva la finestra"
    assert sparito not in impostazioni.get("recent_files"), (
        "la pulizia non è stata tenuta in memoria: alla chiusura riscriverebbe "
        "un file sparito nell'elenco dei recenti"
    )


# ------------------------------------------------------------- i font


def test_l_elenco_dei_font_è_messo_in_cache_e_copiato():
    """Cercare i font costa circa un secondo: si fa una volta sola.

    Ogni voce restituita è una copia. Senza, un chiamante che modifica una voce
    scriverebbe dentro l'archivio e il secondo chiamante troverebbe il font
    diverso da come l'ha ricevuto il primo.
    """
    from pdfeditor.signature import typed

    typed.svuota_cache_font()
    primo = typed.list_fonts()
    if not primo:
        pytest.skip("questa macchina non ha font da elencare")

    primo[0]["name"] = "modificato"
    secondo = typed.list_fonts()
    assert secondo[0]["name"] != "modificato", "la cache è stata modificata da un chiamante"

    info = typed._elenco_font.cache_info()
    assert info.hits >= 1, "la ricerca dei font è stata rifatta invece che presa dalla cache"


def test_svuotare_la_cache_dei_font_li_rivede():
    """Dopo aver installato un font nuovo, la ricerca deve rifarsi."""
    from pdfeditor.signature import typed

    typed.list_fonts()
    typed.svuota_cache_font()
    assert typed._elenco_font.cache_info().currsize == 0


# ------------------------------------------------------------ le icone


def test_icona_applicazione_e_messa_in_cache():
    """L'icona del programma non veniva ridisegnata a ogni richiesta.

    Il desktop la chiede più volte, per il riquadro, per il menu e per le
    anteprime, e ogni volta erano 256×256 pixel da ridisegnare.
    """
    from pdfeditor.ui import icons

    icons.AppIconCache.clear()
    prima = icons.app_icon()
    assert len(icons.AppIconCache) == 1
    assert icons.app_icon() is prima, "l'icona è stata ridisegnata"