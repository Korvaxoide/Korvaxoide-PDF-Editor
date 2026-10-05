"""Misura l'avvio, fase per fase.

L'avvio era una scatola nera: si sapeva che «un po' lento» e basta. Questo
script stampa le fasi in ordine cosi' si vede quale costa e quale no, e le
misure sono confrontabili fra una versione e l'altra.

Non mostra finestre (``QT_QPA_PLATFORM=offscreen``) e non avvia il ciclo di
eventi: misura il lavoro che va dal primo atto del processo alla finestra
costruita e visibile, che e' quello che l'utente percepisce come attesa.

    ./venv/bin/python -m tools.bench_startup

Ogni passata gira in un processo nuovo. Non si puo' fare diversamente:
``QApplication`` e' un singleton, quindi la seconda creazione nello stesso
processo fallisce, e le import sono parte della misura: riutilizzare
l'interprete nasconderebbe proprio quelle che si cercano.

La prima passata viene buttata: paga la scrittura dei ``.pyc`` e la prima
risoluzione dei simboli delle librerie. Sulle successive si stampa il minimo,
che descrive un avvio normale, e la mediana, che racconta il caso peggiore.

I numeri servono nel confronto, non come valore assoluto: cambiano con la
macchina, con il disco e con il carico. Quello che conta e' che una fase non
cresca quando si aggiunge qualcos'altro.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

#: Le librerie di terze parti che, se sono in ``sys.modules`` dopo l'avvio,
#: vuol dire che l'avvio le ha tirate dentro. Il nome e' quello con cui il
#: pacchetto si chiama in ``requirements.txt``, non quello del modulo.
LIBRERIE = (
    "numpy",
    "pymupdf",
    "PySide6",
    "PIL",
    "cryptography",
    "asn1crypto",
)


def _passata() -> list[tuple[str, float]]:
    """Una passata dell'avvio: le fasi e i secondi trascorsi in ognuna.

    Le fasi sono quelle di ``pdfeditor.app.run``, scomposta nei pezzi che si
    vogliono distinguere. Nessuna di loro viene saltata: quello che si cerca di
    misurare sono proprio le import, quindi tralasciarle sarebbe il difetto
    che lo strumento deve trovare.
    """
    marcatori: list[tuple[str, float]] = []
    t0 = time.perf_counter()

    def segna(nome: str) -> None:
        marcatori.append((nome, time.perf_counter() - t0))

    segna("avvio interprete")
    from pdfeditor import app as appmod

    segna("import di pdfeditor")

    appmod._prepare_environment()
    segna("MuPDF")
    for p in ("resources", "pdfeditor/resources"):
        if Path(p).exists():
            sys.path.insert(0, p)

    from PySide6.QtCore import QLocale, Qt
    from PySide6.QtWidgets import QApplication

    segna("PySide6")

    from pdfeditor import __app_id__, __app_name__, __org_name__, __version__
    from pdfeditor.core import i18n
    from pdfeditor.core import settings as settingsmod
    from pdfeditor.ui import icons, theme
    from pdfeditor.ui.main_window import MainWindow

    segna("import di main_window")

    QApplication.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings, True)
    qapp = QApplication(sys.argv[:1])
    segna("QApplication")

    st = settingsmod.Settings()
    i18n.set_lingua_di_sistema(QLocale.system().name())
    lingua = i18n.inizializza(str(st.get("ui_language") or ""))
    appmod._install_translator(qapp, lingua)
    segna("lingua e traduttore")

    qapp.setApplicationName(__app_name__)
    qapp.setApplicationVersion(__version__)
    qapp.setOrganizationName(__org_name__)
    qapp.setDesktopFileName(__app_id__)
    qapp.setWindowIcon(icons.app_icon())
    segna("icona dell'applicazione")

    pal = theme.DARK if st.get("theme") == "scuro" else theme.LIGHT
    theme.attiva(pal)
    qapp.setStyleSheet(theme.stylesheet(pal))
    segna("foglio di stile")

    win = MainWindow()
    segna("MainWindow()")

    win.show()
    qapp.processEvents()
    segna("finestra visibile")
    return marcatori


def _librerie_presenti() -> list[str]:
    """I pacchetti di terze parti che l'avvio si e' portato dietro."""
    return [nome for nome in LIBRERIE if nome in sys.modules]


def _figlio() -> int:
    """Una passata in un processo separato, che referisce in JSON su stderr.

    Su stdout non si puo' scrivere niente: ci va tutto quello che Qt decide di
    dire, e il suo ``propagateSizeHints`` finirebbe dentro il JSON.
    """
    marcatori = _passata()
    sys.stderr.write(
        "\n"
        + json.dumps(
            {
                "fasi": [nome for nome, _ in marcatori],
                "secondi": [t for _, t in marcatori],
                "librerie": _librerie_presenti(),
            }
        )
        + "\n"
    )
    return 0


def _esegui_una_passata() -> dict:
    """Lancia il figlio e ne legge il referto."""
    proc = subprocess.run(
        [sys.executable, "-m", "tools.bench_startup", "--passata"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise SystemExit(f"la passata è fallita:\n{proc.stderr}")
    riga = [r for r in proc.stderr.splitlines() if r.startswith("{")]
    if not riga:
        raise SystemExit(f"la passata non ha referto:\n{proc.stderr}")
    return json.loads(riga[-1])


def _tabella(referti: list[dict]) -> None:
    """Stampa le fasi con il minimo e la mediana di ogni passata."""
    fasi = referti[0]["fasi"]
    larghezza = max(len(f) for f in fasi)
    print(f"{'fase'.ljust(larghezza)}  {'minimo':>8}  {'mediana':>8}")
    print("-" * (larghezza + 21))
    for i, nome in enumerate(fasi):
        campioni = []
        for r in referti:
            if i == 0:
                campioni.append(r["secondi"][0] * 1000)
            else:
                campioni.append((r["secondi"][i] - r["secondi"][i - 1]) * 1000)
        print(
            f"{nome.ljust(larghezza)}  {min(campioni):7.1f}  "
            f"{statistics.median(campioni):7.1f}"
        )
    totali = [r["secondi"][-1] * 1000 for r in referti]
    print("-" * (larghezza + 21))
    print(
        f"{'totale'.ljust(larghezza)}  {min(totali):7.1f}  "
        f"{statistics.median(totali):7.1f}"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Misura le fasi dell'avvio.")
    ap.add_argument(
        "--ripeti", type=int, default=5, help="quante passate misurare (default: 5)"
    )
    ap.add_argument(
        "--passata",
        action="store_true",
        help="interno: una passata e basta, per il processo figlio",
    )
    args = ap.parse_args(argv)
    if args.passata:
        return _figlio()

    n = max(1, args.ripeti)
    print(f"Python {sys.version.split()[0]} su {sys.platform}")
    print(f"{n} passate in processi separati, finestra non mostrata\n")

    # Una passata di riscaldamento: senza, il minimo di quelle che seguono
    # direbbe piu' del vero e il confronto fra due versioni diventerebbe un
    # confronto fra due dischi.
    _esegui_una_passata()

    referti = [_esegui_una_passata() for _ in range(n)]
    _tabella(referti)

    caricate = sorted(set().union(*(set(r["librerie"]) for r in referti)))
    print("\nlibrerie di terze parti che l'avvio si porta dietro:")
    if caricate:
        for nome in caricate:
            print(f"  {nome}")
    else:
        print("  nessuna")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())