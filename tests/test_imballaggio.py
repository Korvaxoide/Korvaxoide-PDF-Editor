"""Controlli statici sull'imballaggio delle risorse.

Lo spec di PyInstaller non si può importare in un test: esegue subito
``Analysis`` e compila. Basta però leggerlo come testo e confrontarlo con le
cartelle di risorse che il programma cerca a runtime. Il difetto che questi
controlli impediscono è silenzioso: dalla sorgente il catalogo inglese c'è,
nei binari no, e nessun test lo vedeva.
"""

from __future__ import annotations

from pathlib import Path

import pytest

RADICE = Path(__file__).resolve().parents[1]
SPEC = (RADICE / "KorvaxoidePDF.spec").read_text(encoding="utf-8")

#: Cartelle di ``resources/`` che il programma legge a runtime e che lo spec
#: deve copiare accanto all'eseguibile.
CARTELLE_RUNTIME = ("icons", "fonts", "lang")


def test_lo_spec_include_il_catalogo_delle_lingue():
    """Senza questa coppia l'inglese nei binari resta italiano."""
    assert '("resources/lang", "resources/lang")' in SPEC


@pytest.mark.parametrize("nome", CARTELLE_RUNTIME)
def test_ogni_cartella_di_risorse_runtime_e_nello_spec(nome):
    """Ogni cartella letta a runtime deve finire nei dati dell'eseguibile."""
    assert f'"resources/{nome}"' in SPEC


def test_il_catalogo_inglese_esiste_nel_repository():
    """Lo spec può copiare solo un file che esiste davvero."""
    assert (RADICE / "resources" / "lang" / "en.json").is_file()
