"""Elenco dei dati da impacchettare con PyInstaller.

Sta fuori dallo spec perché lo spec viene eseguito subito da PyInstaller e non
si può importare in un test. Qui invece la funzione che costruisce ``datas``
può essere verificata, e serve: il secondo elemento di ogni coppia è una
**cartella** di destinazione, non un percorso di file. PyInstaller copia il
sorgente dentro quella cartella; passandogli ``resources/lang/en.json`` si
ottiene ``resources/lang/en.json/en.json``, il catalogo non viene più trovato
e nei binari l'inglese resta italiano.
"""

from __future__ import annotations

from pathlib import Path

#: Cartelle di ``resources/`` che il programma legge a runtime. Le icone sono
#: disegnate a runtime, ma i PNG servono alla voce di menu del sistema.
CARTELLE = ("icons", "fonts", "lang")


def dati_risorse(radice: Path) -> list[tuple[str, str]]:
    """Le coppie *(sorgente, cartella di destinazione)* per ``datas``.

    Ogni cartella esistente viene copiata con lo stesso nome sotto
    ``resources/``. I file sono ordinati perché due build dello stesso commit
    producano lo stesso elenco.
    """
    dati: list[tuple[str, str]] = []
    for nome in CARTELLE:
        cartella = radice / "resources" / nome
        if not cartella.is_dir():
            continue
        for f in sorted(cartella.iterdir()):
            if f.is_file():
                dati.append((str(f), f"resources/{nome}"))
    return dati
