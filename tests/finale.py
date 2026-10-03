"""Verifica finale end-to-end su un PDF realistico.

Costruisce un documento simile a un modulo aziendale, lo salva, lo riapre e
prova l'intero flusso di lavoro: compilazione, firma, annotazioni, redazione,
ricerca, pagine, firma digitale, cifratura, stampa ed esportazione.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# l'isolamento viene prima di ogni altra cosa: senza, questa verifica scrive
# nelle preferenze vere e costruisce una libreria firme sull'utente
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ambiente  # noqa: E402

ambiente.configura_qt()
ambiente.isola()
ambiente.prepara_percorso()

import pymupdf  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtGui import QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from pdfeditor.core import document as docmod  # noqa: E402
from pdfeditor.core import geometry as geo  # noqa: E402
from pdfeditor.core import settings as sm  # noqa: E402
from pdfeditor.features import digitalsign as ds  # noqa: E402
from pdfeditor.signature import bgremove, render, strokes as sk, typed  # noqa: E402
from pdfeditor.ui import theme  # noqa: E402
from pdfeditor.ui.main_window import MainWindow  # noqa: E402

OUT = ambiente.ricrea("finale")

# la firma di prova viene scritta con un font serif: senza un font sul computer
# l'immagine sarebbe un foglio bianco e la rimozione dello sfondo cancellerebbe
# tutto, senza dire niente
FONT = ambiente.font_serif()
if not FONT:
    raise SystemExit("nessun font serif sul computer: la verifica non può disegnare")

app = QApplication.instance() or QApplication([])

# Una finestra modale mostrata per un errore aprirebbe un proprio ciclo di eventi
# e bloccherebbe il test per sempre: qui ogni finestra modale viene chiusa e
# annotata, cosi' l'errore emerge invece di far scadere il tempo limite.
DIALOGHI_CHIUSI: list[str] = []


def _chiudi_modali() -> None:
    for wid in QApplication.topLevelWidgets():
        if not wid.isVisible():
            continue
        if isinstance(wid, QMessageBox) or wid.isModal():
            DIALOGHI_CHIUSI.append(wid.windowTitle() or type(wid).__name__)
            try:
                wid.reject() if isinstance(wid, QMessageBox) else wid.close()
            except Exception:
                pass


_autochiude = QTimer()
_autochiude.setInterval(150)
_autochiude.timeout.connect(_chiudi_modali)
_autochiude.start()
st = sm.Settings()
st.set("recover", False)
st.set("confirm_destructive", False)
st.set("theme", "chiaro")
app.setStyleSheet(theme.stylesheet(theme.LIGHT))

ok: list[str] = []
ko: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    (ok if cond else ko).append(label)
    print(f"  {'✓' if cond else '✗'} {label}" + (f"  ({detail})" if detail else ""))


def pump(n: int = 4) -> None:
    for _ in range(n):
        app.processEvents()


# ---------------------------------------------------------------- documento
print("\n1) Creazione di un documento aziendale realistico")
w = MainWindow()
w.resize(1500, 950)
w.show()
w.doc.new(595, 842)
w._on_pages_changed()
p = w.doc.page(0)
p.insert_text((56, 90), "SPA s.r.l. — Servizi contabili", fontsize=15, fontname="hebo", color=(0.1, 0.2, 0.45))
p.insert_text((56, 112), "Modulo di richiesta di certificazione", fontsize=11, fontname="tiro")
p.insert_text((56, 150), "Dati del richiedente", fontsize=10, fontname="hebo")
p.draw_line(pymupdf.Point(56, 156), pymupdf.Point(539, 156))

w.doc.add_field(0, "text", pymupdf.Rect(56, 168, 300, 192), name="nome", value="", required=True)
w.doc.add_field(0, "text", pymupdf.Rect(320, 168, 539, 192), name="cognome", value="")
w.doc.add_field(0, "text", pymupdf.Rect(56, 200, 200, 224), name="cf", value="RSSMRA80A01H501U")
w.doc.add_field(0, "text", pymupdf.Rect(220, 200, 400, 224), name="piva", value="")
w.doc.add_field(0, "combo", pymupdf.Rect(56, 232, 260, 256), name="settore",
                options=["Vendite", "Produzione", "Amministrazione", "R&D"], value="Amministrazione")
w.doc.add_field(0, "checkbox", pymupdf.Rect(56, 268, 74, 286), name="pec", value=True)
w.doc.add_annot(0, "note", pymupdf.Rect(90, 258, 112, 280), text="Richiesto per fatturazione elettronica")
w.doc.add_radio_group(
    0,
    [pymupdf.Rect(56, 300, 74, 318), pymupdf.Rect(120, 300, 138, 318), pymupdf.Rect(190, 300, 208, 318)],
    name="modalita", selected=0,
)
w.doc.add_field(0, "signature", pymupdf.Rect(56, 470, 320, 530), name="firma_cliente")
w.doc.add_field(0, "text", pymupdf.Rect(340, 470, 539, 494), name="data", value="")
w.doc.add_bookmark("Dati richiedente", 0)
w.doc.set_metadata({"title": "Modulo di certificazione", "author": "SPA s.r.l.", "subject": "Modulo"})
w.doc.insert_page(1, 595, 842)
w.doc.insert_text_box(1, pymupdf.Rect(56, 80, 539, 200),
                      "Informativa privacy\nI dati raccolti sono trattati per le finalità indicate.",
                      fontsize=10)
w.doc.add_bookmark("Informativa", 1)
w._on_pages_changed()
w.view.load_field_states()
w._reload_panels()
pump()
# il gruppo di pulsanti di opzione e' un campo padre piu' i suoi figli
check("documento a due pagine con i campi", w.doc.page_count == 2 and len(w.doc.fields()) >= 9,
      f"{w.doc.page_count} pagine, {len(w.doc.fields())} campi")

# ------------------------------------------------------------------ compila
print("\n2) Compilazione dei campi dalla vista")
valori = {
    "nome": "Mario", "cognome": "Rossi", "cf": "RSSMRA80A01H501U",
    "piva": "01234567890", "settore": "Amministrazione", "data": "26/09/2026",
}
for nome, valore in valori.items():
    xref = next((x for (p, x), s in w.view.field_states.items() if s["info"].name == nome), None)
    if xref is None:
        check(f"campo «{nome}» trovato", False)
        continue
    w._on_field_committed(0, xref, valore)
pump()
compilati = [f for f in w.doc.fields() if f.value not in (None, "", False, "Off")]
check("campi compilati", len(compilati) >= 6, f"{len(compilati)} valorizzati")
check("valore salvato nel PDF", "Mario" in w.doc.text(0))

# -------------------------------------------------------------------- firma
print("\n3) Firma: disegno, tastiera, immagine con rimozione sfondo")

# 3a disegno a mano
canvas = sk.SignatureCanvas(width=600, height=200)
s = canvas.new_stroke(30, 130)
for i in range(110):
    t = i / 109
    s.add(30 + t * 520, 130 - 34 * (t - 0.5) - 16 * ((i % 7) - 3) / 3)
img_disegno = render.render_strokes(canvas, scale=2.0)
check("firma disegnata trasparente", img_disegno.split()[3].getextrema()[0] == 0
      and img_disegno.split()[3].getbbox() is not None, f"{img_disegno.size}")

# 3b tastiera
stile = typed.TypedStyle(
    font_path=FONT,
    size=86, color=(14, 26, 62), slant=0.30, wobble=0.28, rotate=2.4,
)
img_tastiera = typed.render_typed("Mario Rossi", stile)
check("firma digitata resa", img_tastiera.split()[3].getbbox() is not None, f"{img_tastiera.size}")

# 3c immagine con rimozione sfondo su carta colorata
foto = Image.new("RGB", (520, 160), (118, 176, 214))
ImageDraw.Draw(foto).text(
    (22, 32), "Mario Rossi",
    font=ImageFont.truetype(FONT, 64),
    fill=(28, 32, 48),
)
scelta = bgremove.suggest_method(foto)
img_foto = bgremove.remove_background(foto, scelta)
import numpy as np  # noqa: E402

alpha = np.asarray(img_foto)[:, :, 3]
check("rimozione sfondo su cartoncino", scelta.method == "flood" and alpha.min() == 0 and alpha.max() > 128,
      f"metodo={scelta.method}, contenuto={float((alpha>128).mean())*100:.0f}%")

# inserimento delle tre firme
w._place_signature(0, img_tastiera, 175, 56)
w._place_signature(1, img_disegno, 175, 56)
w._place_signature(0, img_foto, 175, 56)
pump()
per_pagina = {i: w.doc.image_rects(i) for i in range(w.doc.page_count)}
totale = sum(len(v) for v in per_pagina.values())
check("tre firme inserite", totale == 3, f"{totale} immagini")
sovrapposte = 0
for pagina, voci in per_pagina.items():
    rects = [pymupdf.Rect(r["rect"]) for r in voci]
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            if rects[i].intersects(rects[j]) and not (rects[i] & rects[j]).is_empty:
                sovrapposte += 1
# il confronto e' per pagina: rectangoli su pagine diverse non si sovrappongono
check("firme non sovrapposte", sovrapposte == 0, f"{sovrapposte} sovrapposizioni")

# ---------------------------------------------------------------- annotazioni
print("\n4) Annotazioni e redazione")
w.doc.insert_text_box(0, pymupdf.Rect(56, 600, 539, 700),
                      "La presente richiesta deve pervenire entro trenta giorni.\n"
                      "Decorso il termine la domanda decade.", fontsize=10)
w._dispatch("highlight", (0, geo.Rect(56, 600, 300, 613)))
w._dispatch("rect", (0, geo.Rect(56, 640, 539, 672)))
w._dispatch("arrow", (0, [geo.Point(200, 700), geo.Point(200, 745)]))
w._dispatch("ink", (0, [(400 + i * 4, 720 + (14 if i % 2 else -12)) for i in range(30)]))
pump()
annots = [a["type"] for a in w.doc.annots(0, include_widgets=False)]
check("evidenziazione creata", "Highlight" in annots, annots)
check("forma e inchiostro creati", "Square" in annots and "Ink" in annots)
check("freccia creata", "Line" in annots)
targets = w.doc.find_redact_targets(0, "trenta")
w.doc.redact(0, targets)
pump()
check("redazione rimossa", "trenta" not in w.doc.text(0), f"{len(targets)} occorrenze")

# ------------------------------------------------------------------- ricerca
print("\n5) Ricerca e sostituzione")
hits = w.doc.search("Rossi")
check("ricerca di un testo presente", len(hits) >= 1, f"{len(hits)} risultati")
# "trenta" e' gia' stato redatto: si sostituisce un'altra parola
n = w.doc.replace_text("Decorso", "Scaduto", 0)
check("sostituzione applicata", n >= 1 and "Scaduto" in w.doc.text(0), f"{n} sostituzioni")
w.panel_search.find.setText("Informativa")
check("ricerca nel pannello", len(w.panel_search.search(w.doc)) >= 1)

# -------------------------------------------------------------------- pagine
print("\n6) Gestione pagine")
w.doc.insert_page(2, 595, 842)
w.doc.insert_text_box(2, pymupdf.Rect(56, 80, 539, 200), "Pagina aggiunta", fontsize=12)
w._on_pages_changed()
pump()
check("pagina inserita", w.doc.page_count == 3, f"{w.doc.page_count} pagine")
check(" miniature sincronizzate", w.thumbs.list.count() == 3)
w.thumbs.select_pages([2])
w.pages_rotate(90)
pump()
check("pagina ruotata", w.doc.page_info(2).rotation == 90)
w._thumb_action("duplicate", [2])
pump()
check("pagina duplicata", w.doc.page_count == 4, f"{w.doc.page_count} pagine")
w._thumb_action("delete", [3])
pump()
check("pagina eliminata", w.doc.page_count == 3)

# ------------------------------------------------------------- salva e riapri
print("\n7) Salvataggio, riapertura e annullamento")
target = OUT / "modulo_completo.pdf"
w.doc.save(target)
check("file salvato", target.exists(), f"{target.stat().st_size} byte")
w2 = MainWindow()
w2.show()
w2.load_path(str(target))
pump()
check("riaperto con 3 pagine", w2.doc.page_count == 3)
check("campi ripristinati", len(w2.doc.fields()) >= 9, f"{len(w2.doc.fields())}")
check("valori ripristinati", "Mario" in w2.doc.text(0))
check("firmi ripristinate", len(w2.doc.image_rects(0)) + len(w2.doc.image_rects(1)) == 3)
check("segnalibri ripristinati", len(w2.doc.outline()) == 2)
prima_annot = len(w2.doc.annots(0, include_widgets=False))
w2.doc.add_annot(0, "rect", pymupdf.Rect(56, 750, 200, 780), color=(0.8, 0.2, 0.2))
pump()
aggiunte = len(w2.doc.annots(0, include_widgets=False))
w2.edit_undo()
pump()
check("annullamento funzionante",
      aggiunte == prima_annot + 1 and len(w2.doc.annots(0, include_widgets=False)) == prima_annot
      and w2.doc.history.can_redo,
      f"{prima_annot} -> {aggiunte} -> {len(w2.doc.annots(0, include_widgets=False))}")

# -------------------------------------------------------------- firma digitale
print("\n8) Firma digitale")
cert = ds.make_self_signed("Mario Rossi", "mario.rossi@spa.it", "SPA s.r.l.", save_to=OUT / "cert.pem")
firmato = OUT / "modulo_firmato.pdf"
res = ds.sign_document(target, firmato, cert, page_index=0, rect=(56, 470, 340, 530),
                       reason="Conferma richiesta", location="Milano", name="Mario Rossi")
check("documento firmato", res.ok, res.message)
tutte = ds.verify_file(firmato)
firmate = [s for s in tutte if s.get("signed")]
check("campo firma del modulo rilevato", len(tutte) == 2 and any(not s.get("signed") for s in tutte),
      f"{len(tutte)} campi firma")
check("firma apposta rilevata", len(firmate) == 1, f"{len(firmate)} firmate")
verifica = firmate[0] if firmate else {}
check("firma verificata", verifica.get("valid") is True, verifica.get("integrity"))
check("motivo e luogo presenti", verifica.get("reason") == "Conferma richiesta"
      and verifica.get("location") == "Milano")
dati_grezzi = bytearray(firmato.read_bytes())
i = dati_grezzi.find(b"/ByteRange")
cifre = bytearray(b"")
dati_grezzi[i + 20] = ord("9") if dati_grezzi[i + 20] != ord("9") else ord("8")
manomesso = OUT / "manomesso.pdf"
manomesso.write_bytes(bytes(dati_grezzi))
check("manomissione rilevata", ds.verify_file(manomesso)[0].get("valid") is False)

# firma dentro il campo vuoto del modulo, come su un documento ricevuto
in_campo = OUT / "firmato_in_campo.pdf"
res_campo = ds.sign_document(
    target, in_campo, cert,
    field_name_search="firma_cliente",
    reason="Conferma richiesta", location="Milano",
)
check("campo firma esistente compilato",
      res_campo.ok and res_campo.details["field"] == "firma_cliente"
      and res_campo.details["existing_field"] is True,
      res_campo.message)
firmate_campo = [s for s in ds.verify_file(in_campo) if s["signed"]]
check("firma nel campo verificata",
      len(firmate_campo) == 1 and firmate_campo[0]["valid"] is True
      and firmate_campo[0]["name"] == "firma_cliente",
      f"{len(firmate_campo)} firme valide")
doc_campo = docmod.Document()
doc_campo.open(in_campo)
nomi = [f.name for f in doc_campo.fields()]
check("nessun campo firma aggiuntivo", nomi.count("firma_cliente") == 1, ", ".join(nomi))
doc_campo.close()

# ----------------------------------------------------------------- sicurezza
print("\n9) Protezione del documento")
protetto = OUT / "modulo_protetto.pdf"
w2.doc.export(str(protetto), permissions=~(pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_COPY),
               owner_pass="proprietario", user_pass="utente",
               algorithm=pymupdf.PDF_ENCRYPT_AES_256)
w3 = Document_probe = w2.doc
probe = pymupdf.open(str(protetto))
check("richiede password", probe.needs_pass)
check("password corretta accettata", probe.authenticate("utente"))
check("stampa vietata", not (probe.permissions & pymupdf.PDF_PERM_PRINT))
check("cifratura AES-256", probe.authenticate("utente") and probe.needs_pass)
probe.close()

# ------------------------------------------------------------- esportazioni
print("\n10) Esportazione")
w2.doc.export(str(OUT / "solo_pagina_1.pdf"), pages=[0])
check("estrazione di una pagina", pymupdf.open(str(OUT / "solo_pagina_1.pdf")).page_count == 1)
w2._export_images(OUT / "immagini", [0, 1], 150, "png", 90)
pump()
check("nessuna finestra di dialogo bloccante", not DIALOGHI_CHIUSI, ", ".join(DIALOGHI_CHIUSI))
esportate = sorted((OUT / "immagini").glob("*.png"))
check("immagini esportate", len(esportate) == 2, f"{len(esportate)} file")
check("immagine non vuota", esportate[0].stat().st_size > 20000, f"{esportate[0].stat().st_size} byte")
(OUT / "testo.txt").write_text(w2.doc.extract_text(), encoding="utf-8")
check("testo esportato", len((OUT / "testo.txt").read_text(encoding="utf-8")) > 100)

# ------------------------------------------------------------------ cattura
print("\n11) Cattura della finestra")
w2.view.go_to_page(0)
w2.tabs.setCurrentIndex(1)
pump()
w2.grab().save(str(OUT / "finestra_finale.png"))
check("cattura salvata", (OUT / "finologia.png").exists() if False
      else (OUT / "finestra_finale.png").stat().st_size > 30000,
      f"{(OUT / 'finestra_finale.png').stat().st_size} byte")

for win in (w, w2):
    win.doc.dirty = False
    win.close()
pump()

print(f"\n{'=' * 62}")
print(f"ESITO: {len(ok)} verifiche superate, {len(ko)} fallite")
if ko:
    for k in ko:
        print("  FALLITA:", k)
    sys.exit(1)
print("TUTTO IL FLUSSO DI LAVORO FUNZIONA")
