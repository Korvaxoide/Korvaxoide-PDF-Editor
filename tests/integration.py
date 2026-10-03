"""Prova di integrazione della finestra principale (headless)."""

import os
import shutil
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
from PySide6.QtWidgets import QApplication  # noqa: E402

from pdfeditor.core import settings as sm  # noqa: E402
from pdfeditor.ui import theme  # noqa: E402
from pdfeditor.ui.main_window import MainWindow  # noqa: E402

TMP = Path("/tmp/opencode/integration")
# directory pulita: la libreria delle firme e il recupero accumulerebbero stato
# tra un'esecuzione e l'altra
if TMP.exists():
    shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True, exist_ok=True)

app = QApplication.instance() or QApplication([])
st = sm.Settings()
st.set("recover", False)
st.set("confirm_destructive", False)
app.setStyleSheet(theme.stylesheet(theme.LIGHT))

ok = []
fail = []


def check(label, condition, detail=""):
    (ok if condition else fail).append(f"{label}{(' — ' + str(detail)) if detail else ''}")
    print(f"  {'OK  ' if condition else 'FAIL'} {label}" + (f" ({detail})" if detail else ""))


def pump(n=3):
    for _ in range(n):
        app.processEvents()


print("\n== avvio ==")
w = MainWindow()
w.resize(1400, 900)
w.show()
pump()
check("finestra creata e visibile", w.isVisible())
check("vista creata", w.view is not None)
check("pannello miniature presente", w.thumbs is not None)
check("pannelli laterali presenti", w.tabs.count() >= 6, f"{w.tabs.count()} schede")

print("\n== nuovo documento ==")
w.doc.new()
w.view.set_document(w.doc)
w._on_pages_changed()
pump()
check("pagina creata", w.doc.page_count == 1)
check("nodi scena creati", w.view.page_count() == 1)

print("\n== inserimento testo ==")
import pymupdf

from pdfeditor.core import geometry as geo  # noqa: E402

res = w.doc.insert_text_box(0, pymupdf.Rect(60, 80, 400, 150), "Relazione di prova\nSeconda riga", fontsize=14)
pump()
check("casella di testo inserita", "Relazione" in w.doc.text(0), repr(w.doc.text(0)[:24]))
check("campo stati inizializzati", len(w.view.field_states) == 0)

print("\n== campi modulo ==")
w.doc.add_field(0, "text", pymupdf.Rect(60, 200, 400, 228), name="nome", value="Mario Rossi")
w.doc.add_field(0, "checkbox", pymupdf.Rect(60, 250, 80, 270), name="accetto", value=True)
w.doc.add_field(0, "combo", pymupdf.Rect(60, 290, 250, 312), name="scelta", options=["Uno", "Due", "Tre"], value="Due")
w.doc.add_radio_group(0, [pymupdf.Rect(60, 340, 80, 360), pymupdf.Rect(120, 340, 140, 360)], name="grp", selected=0)
w.view.load_field_states()
w.panel_fields.load(w.doc)
pump()
check("campi riconosciuti dalla vista", len(w.view.field_states) == 6, len(w.view.field_states))
check("campi elencati nel pannello", w.panel_fields.table.rowCount() == 6, w.panel_fields.table.rowCount())
check("statistiche campi", w.doc.field_stats()["total"] == 6)

print("\n== compilazione campi ==")
nome_xref = [f.xref for f in w.doc.fields() if f.name == "nome"][0]
w._on_field_committed(0, nome_xref, "Luigi Verdi")
pump()
check("valore campo aggiornato nel doc", [f.value for f in w.doc.fields() if f.name == "nome"][0] == "Luigi Verdi")
cb_xref = [f.xref for f in w.doc.fields() if f.name == "accetto"][0]
before = [f.value for f in w.doc.fields() if f.name == "accetto"][0]
w.view.begin_field_edit(0, cb_xref)
pump()
after = [f.value for f in w.doc.fields() if f.name == "accetto"][0]
check("casella di spunta invertita", before != after, f"{before} -> {after}")

print("\n== annotazioni ==")
w._dispatch("rect", (0, geo.Rect(300, 400, 450, 470)))
w._dispatch("ink", (0, [(400, 500), (420, 520), (440, 495), (460, 515)]))
w._dispatch("arrow", (0, [geo.Point(100, 600), geo.Point(200, 650)]))
w._dispatch("line", (0, [(100, 680), (300, 700)]))
w._dispatch("circle", (0, geo.Rect(500, 500, 580, 570)))
w._dispatch("polygon", (0, [(120, 200), (200, 180), (170, 260)]))
w._dispatch("highlight", (0, geo.Rect(60, 80, 200, 95)))
# nota e collegamento passano da una finestra di dialogo: si verificano sul
# modello del documento, che e' dove finiscono i dati.
w.doc.add_annot(0, "note", geo.Rect(500, 100, 522, 122), text="Nota di prova")
w.doc.add_annot(0, "link", geo.Rect(60, 400, 200, 420), text="https://example.org")
pump()
types = [a["type"] for a in w.doc.annots(0, include_widgets=False)]
check("annotazioni create", len(types) >= 8, types)
check("rettangolo presente", "Square" in types)
check("ellisse presente", "Circle" in types)
check("inchiostro presente", "Ink" in types)
check("freccia presente", "Line" in types)
check("nota presente", "Text" in types)
check("collegamento presente", any(l["uri"].startswith("https://") for l in w.doc.links(0)),
      w.doc.links(0))
check("evidenziazione presente", "Highlight" in types)
check("poligono presente", "Polygon" in types)
line_xref = [a["xref"] for a in w.doc.annots(0, False) if a["type"] == "Line"][0]
le = w.doc.xref_key(line_xref, "LE")
check("punta freccia impostata", le[0] == "array" and "/R" in le[1], le[1][:44])

print("\n== evidenziazione testo ==")
hits = w.doc.search("Seconda")
check("ricerca testo trova occorrenze", len(hits) >= 1, f"{len(hits)} risultati")
w._highlight_all("Seconda", False, False)
pump()
hl = [a["type"] for a in w.doc.annots(0, include_widgets=False) if a["type"] == "Highlight"]
check("evidenziazione creata", len(hl) >= 1, f"{len(hl)}")

print("\n== firma (mouse, tastiera, immagine) ==")
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from pdfeditor.signature import manager as sigman  # noqa: E402
from pdfeditor.signature import bgremove, render as sigrender, strokes as sk, typed  # noqa: E402

lib = sigman.SignatureLibrary(folder=TMP / "siglib")

c = sk.SignatureCanvas(width=600, height=220)
st1 = c.new_stroke(40, 120)
for i in range(80):
    st1.add(40 + i * 2.4, 120 - (30 * (i % 7)) / 3)
img_draw = sigrender.render_strokes(c, scale=2.0)
check("firma disegnata resa", img_draw.width > 0 and img_draw.height > 0, f"{img_draw.size}")
alpha = img_draw.split()[3]
check("firma disegnata trasparente", alpha.getextrema()[0] == 0, f"min={alpha.getextrema()[0]}")

style = typed.TypedStyle(font_path=typed.pick_default_font(), size=88, color=(18, 32, 74))
img_type = typed.render_typed("Mario Rossi", style)
check("firma digitata resa", img_type.width > 0, f"{img_type.size}")
check("firma digitata non vuota", img_type.split()[3].getbbox() is not None)

photo = Image.new("RGB", (460, 150), (238, 238, 242))
ImageDraw.Draw(photo).text(
    (24, 30), "Mario Rossi",
    font=ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf", 68),
    fill=(25, 30, 45),
)
for method in ("white", "luminance", "flood", "border", "color"):
    stt = bgremove.RemovalSettings(method=method, threshold=34, key_color=(238, 238, 242, 255), seed=(8, 8))
    out = bgremove.remove_background(photo, stt)
    a = out.split()[3]
    check(f"rimozione sfondo «{method}»", a.getextrema()[0] == 0 and a.getbbox() is not None, f"{out.size}")
img_photo = bgremove.remove_background(photo, bgremove.suggest_method(photo))

before_imgs = len(w.doc.image_rects(0))
w._place_signature(0, img_photo, 180, 60)
pump()
after_imgs = len(w.doc.image_rects(0))
check("firma inserita nella pagina", after_imgs > before_imgs, f"{before_imgs} -> {after_imgs}")

e1 = lib.add_canvas(c, name="Disegnata")
e2 = lib.add_typed("Mario Rossi", style)
e3 = lib.add_png(img_photo, name="Da foto", source="image")
check("libreria firme salvate", len(lib) == 3, [e.display_name for e in lib.entries])
check("tratti ricaricati", lib.canvas(e1) is not None)
check("firmatiera ricaricata", lib.image(e2) is not None)

print("\n== inserimento immagine ==")
img_path = TMP / "foto.png"
Image.new("RGB", (400, 300), (200, 120, 60)).save(img_path)
n_before = len(w.doc.image_rects(0))
# lo strumento immagine apre una finestra di scelta file: qui si verifica il
# modello del documento, che e' dove l'immagine viene effettivamente inserita.
w.doc.insert_image(0, geo.Rect(60, 500, 260, 700), str(img_path))
pump()
check("immagine inserita", len(w.doc.image_rects(0)) > n_before, f"{n_before} -> {len(w.doc.image_rects(0))}")
xr = w.doc.image_rects(0)[0]["xref"]
check("immagine estraibile", len(w.doc.extract_image(xr)) > 100, f"{len(w.doc.extract_image(xr))} byte")
w.doc.insert_image(0, geo.Rect(300, 500, 400, 600), img_path.read_bytes(), keep_proportion=False)
pump()
check("immagine inserita da memoria", len(w.doc.image_rects(0)) >= 2)

print("\n== pagine ==")
w.doc.insert_page(1)
w.doc.insert_page(2)
w._on_pages_changed()
pump()
check("pagine inserite", w.doc.page_count == 3, w.doc.page_count)
check(" miniature sincronizzate", w.thumbs.list.count() == 3, w.thumbs.list.count())
w.doc.duplicate_pages([0])
w._on_pages_changed()
pump()
check("pagina duplicata", w.doc.page_count == 4, w.doc.page_count)
w.thumbs.select_pages([0])
w.pages_rotate(90)
pump()
check("pagina ruotata", w.doc.page_info(0).rotation == 90, w.doc.page_info(0).rotation)
w.doc.move_page(3, 0)
w._on_pages_changed()
pump()
check("pagine riordinate", w.doc.page_count == 4)
w.doc.delete_pages([0])
w._on_pages_changed()
pump()
check("pagina eliminata", w.doc.page_count == 3, w.doc.page_count)
w.edit_undo()
pump()
check("annullamento eliminazione", w.doc.page_count == 4, w.doc.page_count)
w.edit_redo()
pump()
check("ripetizione eliminazione", w.doc.page_count == 3, w.doc.page_count)

print("\n== modelli e metadati ==")
w.doc.add_bookmark("Inizio", 0)
w.doc.add_bookmark("Fine", 2)
w.panel_bookmarks.load(w.doc)
check("segnalibri salvati", len(w.doc.outline()) == 2, [e["title"] for e in w.doc.outline()])
check("segnalibri nel pannello", w.panel_bookmarks.tree.topLevelItemCount() == 2)
w.doc.set_metadata({"title": "Relazione", "author": "Mario Rossi"})
check("metadati impostati", w.doc.metadata().get("title") == "Relazione")
att = TMP / "nota.txt"
att.write_text("contenuto allegato", encoding="utf-8")
w.doc.add_attachment(att)
w.panel_attach.load(w.doc)
check("allegato aggiunto", len(w.doc.attachments()) == 1, w.doc.attachments())
check("allegato leggibile", w.doc.attachment_bytes("nota.txt") == b"contenuto allegato")

print("\n== salvataggio e riapertura ==")
out = TMP / "documento.pdf"
w.doc.save(out)
check("file salvato", out.exists(), f"{out.stat().st_size} byte")
w2 = MainWindow()
w2.show()
w2.load_path(str(out))
pump()
check("documento riaperto", w2.doc.page_count == 3, w2.doc.page_count)
check("campi riaperti", len(w2.doc.fields()) >= 6, len(w2.doc.fields()))
check("testo riaperto", "Relazione" in w2.doc.text(0))
check("ricerca nel riaperto", len(w2.doc.search("Relazione")) >= 1)
w2.doc.close()

print("\n== firma digitale ==")
from pdfeditor.features import digitalsign  # noqa: E402

doc_path = TMP / "firmato_src.pdf"
w.doc.export(str(doc_path))
cert = digitalsign.make_self_signed("Mario Rossi", "mario@rossi.it", "Rossi SRL", save_to=TMP / "cert.pem")
signed = TMP / "firmato.pdf"
r = digitalsign.sign_document(str(doc_path), str(signed), cert, page_index=0,
                             rect=(72, 700, 320, 760), reason="Accettazione", location="Milano", name="Mario Rossi")
check("documento firmato", r.ok, r.message)
ver = digitalsign.verify_file(signed)
check("firma verificata", bool(ver) and ver[0].get("valid") is True,
      ver[0].get("integrity") if ver else "nessuna firma")
# la manomissione avviene dentro il primo intervallo firmato: il testo e'
# compresso, quindi si altera un byte noto (l'inizio del corpo della pagina)
import re as _re

tampered = TMP / "manomesso.pdf"
raw = bytearray(signed.read_bytes())
_br = _re.search(rb"/ByteRange\s*\[\s*(\d+)\s+(\d+)", raw)
_lo = int(_br.group(2))
if _lo < len(raw):
    raw[_lo - 8] = (raw[_lo - 8] + 1) % 256
tampered.write_bytes(bytes(raw))
v2 = digitalsign.verify_file(tampered)
check("manomissione rilevata", bool(v2) and v2[0].get("valid") is False,
      v2[0].get("integrity") if v2 else "")

print("\n== sicurezza ==")
prot = TMP / "protetto.pdf"
w.doc.export(str(prot), permissions=-1, owner_pass="prop", user_pass="utente",
             algorithm=pymupdf.PDF_ENCRYPT_AES_256)
check("documento protetto creato", prot.exists())
try:
    d3 = pymupdf.open(str(prot))
    check("richiede password", d3.needs_pass)
    check("password corretta accettata", d3.authenticate("utente"))
    d3.close()
except Exception as exc:
    check("protezione applicata", False, exc)

print("\n== esportazione immagini ==")
png_path = TMP / "pagina1.png"
w.doc.insert_page(0, 595, 842)
w._export_images(TMP, [0], 150, "png", 90)
pump()
check("immagine esportata", (TMP / "pagina_0001.png").exists())

print("\n== strumenti e scorciatoie ==")
for tool in ("select", "hand", "text", "image", "signature", "highlight", "rect", "field_text", "redact"):
    w.select_tool(tool)
    check(f"strumento «{tool}» attivabile", w.tool == tool and w.view.tool == tool)

print("\n== pannelli ==")
w.panel_search.find.setText("Relazione")
hits = w.panel_search.search(w.doc)
check("ricerca nel pannello", len(hits) >= 1, f"{len(hits)} risultati")
w.panel_search.step(1)
check(" navigazione risultati", w.panel_search.current_hit() is not None)
w._reload_panels()
check("pannello commenti caricato", w.panel_comments.rows is not None, f"{len(w.panel_comments.rows)} commenti")
w.panel_props.load(w.doc)
check("pannello proprietà caricato", w.doc.metadata().get("title") == "Relazione")

print("\n== riquadro risultati ==")
from PySide6.QtGui import QImage, QPainter  # noqa: E402

img = QImage(1400, 900, QImage.Format_ARGB32)
img.fill(0xFFF2F3F5)
p = QPainter(img)
w.view.render(p)
p.end()
img.save(str(TMP / "vista.png"))
check("vista renderizzata", (TMP / "vista.png").exists() and (TMP / "vista.png").stat().st_size > 5000,
      f"{(TMP / 'vista.png').stat().st_size} byte")

print(f"\n== ESITO: {len(ok)} ok, {len(fail)} falliti ==")
if fail:
    print("FALLITI:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("TUTTO OK")
