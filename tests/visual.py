"""Cattura la finestra principale per la verifica visiva."""

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
from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from pdfeditor.core import geometry as geo  # noqa: E402
from pdfeditor.core import settings as sm  # noqa: E402
from pdfeditor.signature import bgremove, render as sigrender, strokes as sk, typed  # noqa: E402
from pdfeditor.ui import theme  # noqa: E402
from pdfeditor.ui.main_window import MainWindow  # noqa: E402

OUT = Path("/tmp/opencode/visual")
if OUT.exists():
    shutil.rmtree(OUT, ignore_errors=True)
OUT.mkdir(parents=True, exist_ok=True)

app = QApplication.instance() or QApplication([])
st = sm.Settings()
st.set("recover", False)
st.set("confirm_destructive", False)
st.set("theme", "chiaro")
app.setStyleSheet(theme.stylesheet(theme.LIGHT))


def build_window(dark: bool = False) -> MainWindow:
    s = sm.Settings()
    s.set("theme", "scuro" if dark else "chiaro")
    w = MainWindow()
    w.resize(1500, 950)
    w.show()
    w.doc.new(width=595, height=842)
    w.view.set_document(w.doc)
    w.doc.insert_text_box(0, pymupdf.Rect(50, 50, 545, 90), "Relazione annuale", fontsize=20, align=1)
    w.doc.insert_text_box(
        0, pymupdf.Rect(50, 100, 545, 200),
        "Questo documento contiene testo, campi modulo da compilare e annotazioni.\n"
        "Il testo e' ricercabile e sostituibile.",
        fontsize=11,
    )
    w.doc.add_field(0, "text", pymupdf.Rect(50, 215, 320, 243), name="nome", value="Mario Rossi")
    w.doc.add_field(0, "text", pymupdf.Rect(50, 250, 320, 278), name="cognome", value="")
    w.doc.add_field(0, "checkbox", pymupdf.Rect(50, 292, 70, 312), name="accetto", value=True)
    w.doc.add_field(0, "combo", pymupdf.Rect(50, 322, 250, 344), name="settore",
                    options=["Vendite", "Produzione", "Amministrazione"], value="Vendite")
    w.doc.add_radio_group(
        0, [pymupdf.Rect(50, 360, 70, 380), pymupdf.Rect(110, 360, 130, 380), pymupdf.Rect(170, 360, 190, 380)],
        name="modalita", selected=1,
    )
    w.doc.add_field(0, "signature", pymupdf.Rect(50, 400, 300, 440), name="firma")
    w.doc.insert_text_box(0, pymupdf.Rect(50, 470, 545, 600), "Note finali\nLa presente relazione e' stata redatta in data odierna.", fontsize=10)
    w.doc.add_annot(0, "highlight", pymupdf.Rect(50, 108, 330, 121), color=(1, 0.88, 0.4))
    w.doc.add_annot(0, "rect", pymupdf.Rect(360, 50, 545, 120), color=(0.78, 0.21, 0.18), width=2)
    w.doc.add_annot(0, "circle", pymupdf.Rect(360, 135, 460, 200), color=(0.12, 0.45, 0.8), width=1.6)
    w.doc.add_annot(0, "ink", pymupdf.Rect(0, 0, 1, 1),
                    vertices=[(380 + i * 5, 250 + (18 if i % 3 else -14)) for i in range(30)],
                    color=(0.1, 0.1, 0.6), width=1.8)
    w.doc.add_annot(0, "note", pymupdf.Rect(480, 210, 502, 232), text="Verificare i dati")

    # firma inserita (mouse)
    canvas = sk.SignatureCanvas(width=600, height=200)
    s0 = canvas.new_stroke(30, 120)
    for i in range(90):
        s0.add(30 + i * 2.6, 120 - 26 * ((i % 9) - 4) / 4)
    w._place_signature(0, sigrender.render_strokes(canvas, scale=2.0), 170, 55)

    # firma da immagine con rimozione sfondo
    photo = Image.new("RGB", (440, 140), (240, 240, 244))
    ImageDraw.Draw(photo).text(
        (20, 26), "Luigi Bianchi",
        font=ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf", 62),
        fill=(20, 24, 40),
    )
    w._place_signature(0, bgremove.remove_background(photo, bgremove.suggest_method(photo)), 170, 54)

    w.doc.insert_page(1)
    w.doc.add_bookmark("Pagina 1", 0)
    w.doc.set_metadata({"title": "Relazione annuale", "author": "Mario Rossi"})
    w._on_pages_changed()
    w.view.load_field_states()
    w._reload_panels()
    for _ in range(6):
        app.processEvents()
    # la vista si apre già con la pagina interamente visibile
    w.view.go_to_page(0)
    for _ in range(6):
        app.processEvents()
    return w


def shot(w: MainWindow, name: str) -> None:
    for _ in range(4):
        app.processEvents()
    pm = w.grab()
    path = OUT / f"{name}.png"
    pm.save(str(path))
    print(f"  salvato {path.name} ({path.stat().st_size} byte)")


print("cattura finestra (tema chiaro)…")
w = build_window(dark=False)
shot(w, "01_chiaro_documento")

print("cattura pannello ricerca…")
w.tabs.setCurrentIndex(0)
w.panel_search.find.setText("Relazione")
w.panel_search.search(w.doc)
w.dock_side.setVisible(True)
shot(w, "02_pannello_ricerca")

print("cattura pannello campi…")
w.tabs.setCurrentIndex(1)
w.panel_fields.load(w.doc)
shot(w, "03_pannello_campi")

print("cattura pannello segnalibri…")
w.tabs.setCurrentIndex(2)
w.panel_bookmarks.load(w.doc)
shot(w, "04_pannello_segnalibri")

print("cattura tema scuro…")
w2 = build_window(dark=True)
shot(w2, "05_scuro_documento")

print("cattura strumento annotazione…")
w2.select_tool("rect")
w2.tabs.setCurrentIndex(1)
shot(w2, "06_strumento_annotazione")

print("fatto")
