"""La documentazione è parte del programma: deve stare in piedi da sola.

Una riga di README che punta a un'ancora inesistente, o a un file che non
esiste piu', non si vede subito: GitHub la mostra come testo e chi ci clicca
davanti trova niente. Qui i documenti vengono controllati come il resto.

Sono controlli sui file, non sull'interfaccia: eseguono quello che GitHub
eseguirebbe, quindi non serve Qt.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RADICE = Path(__file__).resolve().parents[1]

#: I documenti in inglese, nella radice: sono il testo di riferimento.
DOCUMENTI_EN = (
    "README.md",
    "MANUAL.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "THIRD-PARTY.md",
    "SECURITY.md",
)

#: Le traduzioni italiane. Devono stare tutte sotto docs/it/ e contenere gli
#: stessi documenti: senza questo controllo un documento tralasciato nella
#: traduzione restava indietro senza che nessuno se ne accorgesse.
DOCUMENTI_IT = (
    "docs/it/README.md",
    "docs/it/MANUALE.md",
    "docs/it/SVILUPPO.md",
    "docs/it/CHANGELOG.md",
    "docs/it/THIRD-PARTY.md",
    "docs/it/SECURITY.md",
)

DOCUMENTI = DOCUMENTI_EN + DOCUMENTI_IT

#: Le coppie (versione inglese, traduzione) devono esistere entrambe e citarsi.
COPPIE = (
    ("README.md", "docs/it/README.md"),
    ("MANUAL.md", "docs/it/MANUALE.md"),
    ("CONTRIBUTING.md", "docs/it/SVILUPPO.md"),
    ("CHANGELOG.md", "docs/it/CHANGELOG.md"),
    ("THIRD-PARTY.md", "docs/it/THIRD-PARTY.md"),
    ("SECURITY.md", "docs/it/SECURITY.md"),
)


# ------------------------------------------------------------------ utilità


def _testo(nome: str) -> str:
    return (RADICE / nome).read_text(encoding="utf-8")


def _ancora(titolo: str) -> str:
    """Come GitHub trasforma un titolo di intestazione in collegamento.

    Minuscolo, via i caratteri che non sono alfanumerici (tranne il trattino
    e l'underscore), spazi diventano trattini. Le lettere accentuate restano:
    toglierle darebbe un'ancora diversa da quella che GitHub genera.
    """
    t = titolo.strip().rstrip("`#").lower()
    t = re.sub(r"[^\w\- ]", "", t, flags=re.UNICODE)
    return t.replace(" ", "-")


def _ancore(nome: str) -> set[str]:
    return {
        _ancora(m.group(2))
        for m in re.finditer(r"^(#{1,6})\s+(.*)$", _testo(nome), re.M)
    }


def _graffe_chiusse(nome: str) -> list[int]:
    """Le righe in cui una cancellata contiene il delimitatore di un blocco.

    Nell'indice e nella struttura del codice il delimitatore era attaccato
    al titolo: la cancellata si chiudeva con ``` dentro e il blocco di codice
    non veniva riconosciuto da nessun renderer.
    """
    return [
        i
        for i, riga in enumerate(_testo(nome).splitlines(), 1)
        if re.search(r"^#{1,6} .*```", riga)
    ]


# --------------------------------------------------------- collegamenti interni


@pytest.mark.parametrize("nome", DOCUMENTI)
def test_ogni_ancora_esiste(nome):
    """Nessun collegamento interno può puntare a un'ancora assente."""
    ancore = _ancore(nome)
    mancanti = [
        m.group(1)
        for m in re.finditer(r"\]\(#([^)]+)\)", _testo(nome))
        if m.group(1) not in ancore
    ]
    assert not mancanti, f"{nome}: collegamenti a un'ancora inesistente: {mancanti}"


#: Anche i modelli di issue hanno dei collegamenti, e sono relativi: vengono
#: controllati insieme ai documenti perche' il meccanismo e' lo stesso.
MODELLI_ISSUE = tuple(
    str(p.relative_to(RADICE)) for p in sorted((RADICE / ".github").rglob("*.md"))
)


@pytest.mark.parametrize("nome", DOCUMENTI + MODELLI_ISSUE)
def test_i_file_citati_esistono(nome):
    """Un collegamento a un file che non c'è porta a una pagina 404 su GitHub.

    Il percorso si risolve rispetto alla cartella del documento che lo cita, non
    alla radice: le traduzioni italiane stanno in ``docs/it/`` e tornano su con
    ``../../``, mentre quelle in inglese sono nella radice e ci arrivano senza
    risalire. Con la radice come base ogni collegamento delle traduzioni
    risultava rotto e viceversa.
    """
    documento = RADICE / nome
    mancanti = []
    for m in re.finditer(r"\]\((?!https?://|#|mailto:)([^)]+)\)", _testo(nome)):
        bersaglio = m.group(1).split("#")[0].strip()
        if not bersaglio:
            continue
        if (documento.parent / bersaglio).exists():
            continue
        mancanti.append(bersaglio)
    assert not mancanti, f"{nome}: collegamenti a un file assente: {sorted(set(mancanti))}"


@pytest.mark.parametrize("nome", DOCUMENTI)
def test_nessun_delimitatore_attaccato_al_titolo(nome):
    """Un titolo non deve chiudersi con il delimitatore di un blocco."""
    righe = _graffe_chiusse(nome)
    assert not righe, (
        f"{nome}: il delimitatore ``` e' attaccato al titolo nelle righe {righe}"
    )


# ------------------------------------------------------------------ versione


def test_il_registro_delle_modifiche_cita_la_versione():
    """Il CHANGELOG deve avere una voce per la versione corrente.

    La versione sta in un posto solo e da lì la derivano i nomi dei file
    distribuiti: senza una voce corrispondente, chi legge il registro non
    trova quello che sta usando.
    """
    from pdfeditor import __version__

    testo = _testo("CHANGELOG.md")
    assert re.search(rf"^## {re.escape(__version__)}\b", testo, re.M), (
        f"CHANGELOG.md non ha una voce per {__version__}"
    )


def test_il_registro_ha_la_forma_prevista():
    """Il formato dichiarato nel registro deve essere quello che segue."""
    testo = _testo("CHANGELOG.md")
    # ogni versione e' una intestazione di secondo livello con la data
    voci = re.findall(r"^## (\S+)\s+—\s+(\d{4}-\d{2}-\d{2})$", testo, re.M)
    assert voci, "nessuna voce nel formato «## versione — data»"
    # e sono in ordine decrescente
    import packaging.version as pv

    numeri = [pv.Version(v.lstrip("v")) for v, _ in voci if re.match(r"^v?\d+\.\d+\.\d+$", v)]
    assert numeri == sorted(numeri, reverse=True), (
        f"le versioni non sono in ordine decrescente: {[str(n) for n in numeri]}"
    )


def test_la_licenza_dichiarata_e_quella_del_repository():
    """Il badge del README e la licenza dichiarata devono concordare."""
    import pdfeditor

    assert pdfeditor.__license__ == "AGPL-3.0-or-later"
    assert "AGPL" in _testo("README.md")


def test_l_indirizzo_del_repository_e_quello_del_progetto():
    """Il link nelle informazioni sul programma deve puntare al repository.

    Era un segnaposto: la finestra *Informazioni sul programma* portava a un
    indirizzo che non esiste, e su un repository pubblico è il primo link che
    qualcuno clicca.
    """
    import pdfeditor

    url = pdfeditor.__repo_url__
    assert url.startswith("https://github.com/"), url
    assert not re.search(r"/(example|user|tuo|your|test)\b", url, re.I), (
        f"l'indirizzo sembra ancora un segnaposto: {url}"
    )
    assert url.rstrip("/").count("/") == 4, f"indirizzo inatteso: {url}"


def test_l_indirizzo_del_repository_e_quello_documentato():
    """Ogni URL che parla di questo progetto deve puntare al repository giusto.

    I collegamenti a librerie di terzi (tesseract, asn1crypto…) sono legittimi
    e non vengono toccati: qui si controllano solo quelli che nominano il
    progetto, che sono quelli che un refuso fa sbagliare.
    """
    import pdfeditor

    url = pdfeditor.__repo_url__.rstrip("/")
    sbagliati: set[str] = set()
    for nome in DOCUMENTI:
        for m in re.finditer(r"https://github\.com/[^\s)`\"]+", _testo(nome)):
            candidato = m.group(0).rstrip("/.,").removesuffix(".git")
            if "korvaxoide" not in candidato.lower():
                continue
            if candidato != url and not candidato.startswith(f"{url}/"):
                sbagliati.add(candidato)
    assert not sbagliati, f"indirizzi diversi da __repo_url__ ({url}): {sorted(sbagliati)}"


# ------------------------------------------------------- file che devono esistere


@pytest.mark.parametrize(
    "percorso",
    [
        "LICENSE",
        ".gitignore",
        ".gitattributes",
        "requirements.txt",
        "run.sh",
        "run.bat",
        "build_linux.sh",
        "build_windows.ps1",
        "KorvaxoidePDF.spec",
        "avvia.py",
        "resources/korvaxoide-pdf-editor.desktop",
    ],
)
def test_il_file_esiste(percorso):
    """I file di cui parlano i documenti devono esserci davvero."""
    assert (RADICE / percorso).exists(), f"{percorso} manca"


@pytest.mark.parametrize("percorso", DOCUMENTI)
def test_il_documento_esiste(percorso):
    """Ogni documento dichiarato in questa suite deve esistere.

    La lista e' scritta qui a mano: un documento nuovo o spostato in
    ``docs/it/`` deve essere aggiunto, altrimenti i controlli su ancole e
    collegamenti smettono di coprirlo senza che nessuno se ne accorga.
    """
    assert (RADICE / percorso).is_file(), f"{percorso} manca"


# ------------------------------------------------------------- le due lingue


@pytest.mark.parametrize("inglese,italiano", COPPIE)
def test_ogni_documento_inglese_ha_la_traduzione(inglese, italiano):
    """Un documento inglese senza la traduzione italiana è un buco.

    Le due versioni vanno tenute insieme: senza questo controllo la traduzione
    di un documento nuovo semplicemente non viene scritta, e nessuno se ne
    accorge perché il controllo legge solo i file che esistono.
    """
    assert (RADICE / inglese).is_file(), f"{inglese} manca"
    assert (RADICE / italiano).is_file(), (
        f"{inglese} non ha la traduzione italiana ({italiano})"
    )


@pytest.mark.parametrize("inglese,italiano", COPPIE)
def test_le_due_versioni_si_citano(inglese, italiano):
    """Ogni versione deve rimandare all'altra, in cima.

    Dalla radice il percorso verso la traduzione non sale (``docs/it/…``),
    dalla tradizione verso l'originale sale di due livelli (``../../``). Un
    livello di troppo o di troppo poco non si vede: il file sembra fare
    riferimento a qualcosa che esiste, e il controllo sui file non lo nota
    perche' cerca solo i collegamenti scritti bene.
    """
    verso_italiano = f"](docs/it/{Path(italiano).name})"
    assert verso_italiano in _testo(inglese), (
        f"{inglese} non rimanda a {italiano} con «{verso_italiano}»"
    )
    verso_inglese = f"](../../{Path(inglese).name})"
    assert verso_inglese in _testo(italiano), (
        f"{italiano} non rimanda a {inglese} con «{verso_inglese}»"
    )


def test_le_traduzioni_italiane_stanno_tutte_sotto_docs_it():
    """Nessun documento italiano può restare sparso nella radice.

    La radice e' il testo di riferimento in inglese: un file italiano rimasto
    li' e' indistinguibile da quello vero, e GitHub continuerebbe a mostrarlo
    accanto ai documenti ufficiali.
    """
    italiani = [
        p.name
        for p in RADICE.glob("*.md")
        if p.name not in DOCUMENTI_EN and p.name != "LICENSE"
    ]
    assert not italiani, f"documenti italiani da spostare in docs/it/: {sorted(italiani)}"


def test_ogni_file_di_docs_it_e_la_traduzione_di_un_originale():
    """docs/it/ non deve contenere documenti che non hanno un originale.

    Un file rimasto li' dopo aver rinominato l'originale diventa una versione
    che nessuno aggiorna piu', e il lettore non ha modo di accorgersene. I
    nomi possono anche essere diversi dall'inglese (MANUALE.md contro MANUAL.md),
    quindi il confronto e' sulle coppie dichiarate e non sui nomi dei file.
    """
    dichiarati = {Path(i).name for _, i in COPPIE}
    presenti = {p.name for p in (RADICE / "docs" / "it").glob("*.md")}
    assert presenti == dichiarati, (
        f"in docs/it/ ci sono {sorted(presenti - dichiarati)} senza originale, "
        f"e mancano {sorted(dichiarati - presenti)}"
    )


# ------------------------------------------------------- file che devono esistere


def test_la_licenza_e_quella_agpl():
    """Nel LICENSE c'è il testo dell'AGPL, non un segnaposto."""
    testo = _testo("LICENSE")
    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in testo.upper()
    assert "Version 3" in testo


def test_il_file_desktop_registra_i_pdf():
    """Senza ``MimeType`` il doppio clic su un PDF non apre il programma."""
    testo = _testo("resources/korvaxoide-pdf-editor.desktop")
    assert "MimeType=application/pdf" in testo
    assert "Exec=" in testo
    assert "Type=Application" in testo