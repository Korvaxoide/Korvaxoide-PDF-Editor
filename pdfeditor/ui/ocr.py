"""Riconoscimento del testo (OCR) con Tesseract, se installato.

Tesseract e' opzionale: se manca, la funzione lo segnala e lascia il documento
inalterato. L'utente puo' installarlo dal gestore di pacchetti del proprio
sistema (Linux) o dal sito ufficiale (Windows).
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Sequence

import pymupdf

from ..core.i18n import tr

from ..core import document as docmod

# Dove cercare l'eseguibile su Windows
_WINDOWS_CANDIDATES = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)

LANG_CODES = {
    "ita": "ita",
    "eng": "eng",
    "fra": "fra",
    "deu": "deu",
    "spa": "spa",
    "por": "por",
    "osd": "osd",
}


def find_tesseract() -> str | None:
    """Percorso di tesseract, oppure ``None`` se non e' installato.

    Si cerca anche in ``~/.local/bin``: e' dove vengono installati i
    programmi opzionali senza permessi di amministratore, e quella cartella
    non e' sempre nel PATH.
    """
    path = shutil.which("tesseract")
    if path:
        return path
    utente = Path.home() / ".local" / "bin" / "tesseract"
    if utente.exists():
        return str(utente)
    for cand in _WINDOWS_CANDIDATES:
        if Path(cand).exists():
            return cand
    return None


def is_available() -> bool:
    return bool(find_tesseract())


def version() -> str:
    exe = find_tesseract()
    if not exe:
        return ""
    try:
        res = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=15)
        return (res.stdout or res.stderr).splitlines()[0].strip()
    except Exception:
        return ""


def languages() -> list[str]:
    exe = find_tesseract()
    if not exe:
        return []
    try:
        res = subprocess.run([exe, "--list-langs"], capture_output=True, text=True, timeout=20)
        return [ln.strip() for ln in res.stdout.splitlines()[1:] if ln.strip()]
    except Exception:
        return []





def run_ocr(doc: docmod.Document, lang: str = "ita", dpi: int = 300,
            pages: Sequence[int] | None = None) -> tuple[bool, str]:
    """Aggiunge un livello di testo invisibile alle pagine indicate.

    Il testo riconosciuto non viene scritto in modo visibile: viene inserito come
    livello invisibile, cosi' il documento resta identico ma diventa ricercabile
    e selezionabile, che e' cio' che serve per un PDF scansionato.
    """
    exe = find_tesseract()
    if not exe:
        return False, tr(
            "Tesseract non è installato, quindi il riconoscimento del testo non è "
            "disponibile.\n\n"
            "Linux: installa il pacchetto «tesseract-ocr» e la lingua "
            "«tesseract-ocr-ita».\n"
            "Windows: scarica l'installer da github.com/UB-Mannheim/tesseract/wiki"
        )
    code = LANG_CODES.get(lang, lang)
    # una sola invocazione: interrogare due volte l'elenco delle lingue
    # significava due processi e due elenchi che potevano non coincidere
    installate = languages()
    if installate and code not in installate:
        avail = ", ".join(installate[:8])
        return False, f"La lingua «{code}» non è installata. Disponibili: {avail}"
    idxs = list(pages) if pages else list(range(doc.page_count))
    tmp = Path(tempfile.mkdtemp(prefix="korvaxoide_ocr_"))
    done = 0
    try:
        for i in idxs:
            if i < 0 or i >= doc.page_count:
                continue
            img_path = tmp / f"p{i}.png"
            img_path.write_bytes(doc.extract_page_image(i, dpi=dpi, fmt="png"))
            base = tmp / f"p{i}"
            cmd = [exe, str(img_path), str(base), "-l", code, "--psm", "3", "tsv"]
            try:
                subprocess.run(cmd, capture_output=True, timeout=300)
            except subprocess.TimeoutExpired:
                continue
            tsv = base.with_suffix(".tsv")
            if not tsv.exists():
                continue
            words = _parse_tsv(tsv.read_text(encoding="utf-8", errors="replace"))
            if words:
                _add_invisible_text(doc, i, words, dpi)
                done += 1
            img_path.unlink(missing_ok=True)
        if done:
            # il documento viene dichiarato modificato solo se qualcosa e'
            # stato davvero scritto: altrimenti una scansione senza testo
            # lasciava il file con modifiche fantasma e ogni chiusura chiedeva
            # di salvarlo
            doc.mark_dirty()
            return True, f"Riconosciuto il testo di {done} pagine. Ora la ricerca può trovarlo."
        return False, "Nessun testo riconosciuto."
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _parse_tsv(text: str) -> list[tuple[float, float, float, float, str, float]]:
    """Legge il TSV di Tesseract in una lista di parole con posizione e confidenza."""
    out = []
    for line in text.splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) < 12:
            continue
        try:
            left, top, width, height = (float(parts[i]) for i in (6, 7, 8, 9))
            conf = float(parts[10])
        except ValueError:
            continue
        word = parts[11].strip()
        if not word or conf < 30:
            continue
        out.append((left, top, width, height, word, conf))
    return out


def _add_invisible_text(doc: docmod.Document, page_index: int,
                        words: list[tuple[float, float, float, float, str, float]], dpi: int) -> None:
    """Inserisce le parole come testo in modalità 3 (invisibile)."""
    page = doc.page(page_index)
    scale = 72.0 / dpi
    # Le righe del TSV hanno coordinate pixel: si raggruppano per altezza per
    # ricostruire le linee e inserirle come un unico flusso.
    words.sort(key=lambda w: (round(w[1], 1), w[0]))
    lines: list[list[tuple]] = []
    for w in words:
        if lines and abs(w[1] - lines[-1][0][1]) < max(6.0, w[3] * 0.6):
            lines[-1].append(w)
        else:
            lines.append([w])
    for group in lines:
        left = min(w[0] for w in group) * scale
        top = min(w[1] for w in group) * scale
        height = max(w[3] for w in group) * scale
        text = " ".join(w[4] for w in group)
        if not text.strip():
            continue
        fontsize = max(1.0, height * 0.82)
        try:
            page.insert_text(
                (left, top + height),
                text,
                fontsize=fontsize,
                fontname="helv",
                render_mode=3,
                overlay=True,
            )
        except Exception:
            continue


def searchable(doc: docmod.Document, page_index: int) -> bool:
    """Indica se la pagina contiene testo ricercabile."""
    try:
        return bool(doc.text(page_index).strip())
    except Exception:
        return False
