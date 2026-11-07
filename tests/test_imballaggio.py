"""Controlli statici sull'imballaggio delle risorse.

Lo spec di PyInstaller non si può importare in un test: esegue subito
``Analysis`` e compila. L'elenco dei dati, però, sta in ``tools/risorse.py`` e
si può chiamare: questi controlli ricostruiscono la cartella che PyInstaller
produrrebbe e verificano che il catalogo inglese si trovi dove ``i18n`` lo
cerca. Il difetto che impediscono è silenzioso: dalla sorgente l'inglese
funziona, nei binari resta italiano, e nessun altro test lo vede.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from tools.risorse import CARTELLE, dati_risorse

RADICE = Path(__file__).resolve().parents[1]
SPEC = (RADICE / "KorvaxoidePDF.spec").read_text(encoding="utf-8")


def test_lo_spec_usa_la_funzione_che_elenca_i_dati():
    """La verifica qui sotto vale solo se la build usa la stessa funzione."""
    assert "from tools.risorse import dati_risorse" in SPEC
    assert "dati_risorse(ROOT)" in SPEC


@pytest.mark.parametrize("nome", CARTELLE)
def test_le_cartelle_di_risorse_esistenti_finiscono_nei_dati(nome):
    """Ogni file delle cartelle runtime deve essere impacchettato."""
    cartella = RADICE / "resources" / nome
    if not cartella.is_dir():
        pytest.skip(f"resources/{nome} non esiste: la build lo salta")
    attese = {
        (str(f), f"resources/{nome}")
        for f in cartella.iterdir()
        if f.is_file()
    }
    assert attese <= set(dati_risorse(RADICE))


def test_ogni_destinazione_e_una_cartella():
    """Il secondo elemento di ``datas`` è una cartella, mai un file.

    PyInstaller copia il sorgente *dentro* la destinazione: se questa porta il
    nome del file, il risultato è ``resources/lang/en.json/en.json``.
    """
    for _, destinazione in dati_risorse(RADICE):
        assert destinazione in {f"resources/{n}" for n in CARTELLE}
        assert Path(destinazione).suffix == ""


def test_il_catalogo_inglese_arriva_dove_il_programma_lo_cerca():
    """Ricostruisce la cartella dei dati come la fa PyInstaller.

    È il controllo che sarebbe fallito con la 0.1.3: il catalogo c'era, ma
    annidato in una cartella che si chiamava come il file, quindi ``i18n`` non
    lo trovava e l'inglese restava italiano proprio e solo nei binari.
    """
    with tempfile.TemporaryDirectory() as temporanea:
        base = Path(temporanea)
        for sorgente, destinazione in dati_risorse(RADICE):
            (base / destinazione).mkdir(parents=True, exist_ok=True)
            shutil.copy2(sorgente, base / destinazione)
        assert (base / "resources" / "lang" / "en.json").is_file()
        assert sorted(p.name for p in (base / "resources" / "lang").iterdir()) == ["en.json"]


def test_il_catalogo_inglese_esiste_nel_repository():
    """Lo spec può copiare solo un file che esiste davvero."""
    assert (RADICE / "resources" / "lang" / "en.json").is_file()
