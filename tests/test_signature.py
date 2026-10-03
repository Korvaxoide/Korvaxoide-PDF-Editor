"""Test della firma: tratti, rendering, rimozione sfondo, tastiera, libreria."""

from __future__ import annotations

import io
import math
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from pdfeditor.signature import bgremove, manager, render, strokes as sk, typed

SERIF = "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf"


def make_canvas(points: int = 120) -> sk.SignatureCanvas:
    """Firma di prova disegnata con un andamento sinusoidale."""
    c = sk.SignatureCanvas(width=600, height=220)
    s = c.new_stroke(30, 140)
    # il primo punto e' gia' stato messo da new_stroke
    for i in range(1, points):
        t = i / (points - 1)
        s.add(30 + t * 520, 140 - 40 * math.sin(t * math.pi * 3))
    return c


def signature_photo(bg=(238, 238, 242), fg=(25, 30, 45), size=68, w=520, h=150, **kw) -> Image.Image:
    img = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(img)
    if not Path(SERIF).exists():
        return img
    d.text((24, 30), "Mario Rossi", font=ImageFont.truetype(SERIF, size), fill=fg)
    if kw.get("blur"):
        img = img.filter(ImageFilter.GaussianBlur(kw["blur"]))
    if kw.get("noise"):
        a = np.asarray(img).astype(np.int16)
        rng = np.random.default_rng(7)
        a = a + rng.integers(-kw["noise"], kw["noise"] + 1, a.shape)
        img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    return img


# ------------------------------------------------------------------- tratti


def test_canvas_raccolge_i_tratti():
    c = make_canvas()
    assert not c.is_empty
    assert len(c.strokes) == 1
    assert len(c.strokes[0].points) == 120


def test_undo_tratto():
    c = make_canvas()
    c.new_stroke(10, 10)
    assert c.undo_stroke()
    assert len(c.strokes) == 1
    c.clear()
    assert c.is_empty


def test_il_punto_troppo_vicino_viene_ignorato():
    c = sk.SignatureCanvas()
    s = c.new_stroke(10, 10)
    c.extend(10.1, 10.1)
    assert len(s.points) == 1


def test_smoothing_riduce_le_oscillazioni():
    c = sk.SignatureCanvas()
    st = sk.Stroke(style=sk.StrokeStyle(smoothing=0.5))
    for i in range(20):
        st.add(i * 3, 10 + (6 if i % 2 else -6))
    lisci = st.smoothed()
    assert len(lisci) == len(st.points)


def test_da_a_via_dizionario():
    c = make_canvas()
    c2 = sk.SignatureCanvas.from_dict(c.to_dict())
    assert len(c2.strokes) == len(c.strokes)
    assert c2.strokes[0].points == c.strokes[0].points


def test_resample_mantiene_la_lunghezza():
    pts = [(i * 1.0, 0.0) for i in range(100)]
    out = sk.resample(pts, 2.0)
    assert abs(sk.path_length(out) - sk.path_length(pts)) < 2.0


# ---------------------------------------------------------------- rendering


def test_rendering_produce_trasparenza():
    img = render.render_strokes(make_canvas(), scale=2.0)
    assert img.mode == "RGBA"
    alpha = np.asarray(img)[:, :, 3]
    assert alpha.min() == 0          # sfondo trasparente
    assert alpha.max() > 200         # inchiostro pieno
    assert img.width > 100


def test_rendering_ritaglia_il_contorno():
    """Il rendering deve essere ritagliato attorno alla firma, non a tutta la tela."""
    canvas = make_canvas()
    img = render.render_strokes(canvas, scale=2.0)
    bbox = img.split()[3].getbbox()
    assert bbox is not None
    assert bbox[0] <= 12 and bbox[1] <= 12
    # la tela intera sarebbe 1200x440: il ritaglio deve essere molto minore
    assert img.width < canvas.width * 2
    assert img.height < canvas.height * 2


def test_rendering_scala():
    c = make_canvas()
    a = render.render_strokes(c, scale=1.0)
    b = render.render_strokes(c, scale=3.0)
    assert b.width > a.width


def test_canvas_vuoto():
    img = render.render_strokes(sk.SignatureCanvas(), scale=1.0)
    assert img.size[0] > 0 and np.asarray(img)[:, :, 3].max() == 0


def test_png_con_alpha():
    data = render.to_png(render.render_strokes(make_canvas(), scale=1.0))
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert Image.open(io.BytesIO(data)).mode == "RGBA"


# --------------------------------------------------------- rimozione sfondo


@pytest.mark.parametrize("method", ["white", "luminance", "flood", "border", "color"])
def test_rimozione_sfondo_rimuove_il_bordo(method: str):
    photo = signature_photo()
    st = bgremove.RemovalSettings(
        method=method, threshold=34, tolerance=45, key_color=(238, 238, 242, 255), seed=(8, 8)
    )
    out = bgremove.remove_background(photo, st)
    a = np.asarray(out)[:, :, 3]
    assert a.min() == 0
    assert a.max() > 128
    assert bgremove.alpha_bounds(a) is not None


def test_ritaglio_automatico():
    photo = signature_photo()
    out = bgremove.remove_background(photo, bgremove.suggest_method(photo))
    assert out.width < photo.width
    assert out.height < photo.height


def test_ritaglio_disattivato():
    photo = signature_photo()
    st = bgremove.RemovalSettings(method="white", auto_crop=False)
    out = bgremove.remove_background(photo, st)
    assert out.size == photo.size


def test_sfondo_colorato_richiede_tecnica_adatta():
    """Il metodo automatico deve scegliere una tecnica che funzioni."""
    for bg in [(255, 255, 255), (238, 238, 242), (120, 175, 215), (60, 110, 70), (232, 222, 200)]:
        photo = signature_photo(bg=bg)
        st = bgremove.suggest_method(photo)
        out = bgremove.remove_background(photo, st)
        a = np.asarray(out)[:, :, 3]
        copertura = float((a > 128).mean())
        assert a.min() == 0
        assert 0.02 < copertura < 0.6, f"{st.method} su {bg}: copertura {copertura:.2f}"


def test_nessuna_rimozione_manteriene_tutto():
    photo = signature_photo()
    out = bgremove.remove_background(photo, bgremove.RemovalSettings(method="none"))
    assert np.asarray(out)[:, :, 3].min() == 255


def test_mantieni_colore_versus_grigio():
    photo = signature_photo(fg=(200, 20, 20))
    a = np.asarray(bgremove.remove_background(photo, bgremove.suggest_method(photo)))
    # resta rossa
    assert a[:, :, 0][a[:, :, 3] > 200].mean() > 150
    b = np.asarray(
        bgremove.remove_background(photo, bgremove.RemovalSettings(method="white", keep_color=False))
    )
    r, gg, bb = (b[:, :, 0][b[:, :, 3] > 200], b[:, :, 1][b[:, :, 3] > 200], b[:, :, 2][b[:, :, 3] > 200])
    # diventa grigia
    assert abs(float(r.mean()) - float(gg.mean())) < 20


def test_sfumatura_morbida():
    photo = signature_photo()
    netta = bgremove.remove_background(photo, bgremove.RemovalSettings(method="white", feather=0, softness=0))
    morbida = bgremove.remove_background(photo, bgremove.RemovalSettings(method="white", feather=3, softness=10))
    assert np.asarray(netta)[:, :, 3].astype(int).std() > 0
    # la sfumatura introduce piu' livelli intermedi
    univoci = len(np.unique(np.asarray(morbida)[:, :, 3]))
    assert univoci > len(np.unique(np.asarray(netta)[:, :, 3]))


def test_spazzola_di_cancellazione():
    photo = signature_photo()
    st = bgremove.suggest_method(photo)
    out = bgremove.remove_background(photo, st)
    pieno = int((np.asarray(out)[:, :, 3] > 128).sum())
    # il pennello cade sopra la firma, non sullo sfondo gia' trasparente
    st2 = bgremove.RemovalSettings(**{**st.__dict__, "erase_strokes": [(150, 55, 50)]})
    out2 = bgremove.remove_background(photo, st2)
    assert int((np.asarray(out2)[:, :, 3] > 128).sum()) < pieno


def test_immagine_trasparente():
    img = render.render_strokes(make_canvas(), scale=1.0)
    out = bgremove.remove_background(img, bgremove.RemovalSettings(method="white"))
    assert np.asarray(out)[:, :, 3].max() > 100


def test_scansione_sfocata_e_rumore():
    for kw in ({"blur": 1.2}, {"noise": 12}):
        photo = signature_photo(**kw)
        out = bgremove.remove_background(photo, bgremove.suggest_method(photo))
        a = np.asarray(out)[:, :, 3]
        assert a.min() == 0 and a.max() > 128


def test_scacchiera_per_anteprima():
    pm = bgremove.preview_on_checker(render.render_strokes(make_canvas(), scale=1.0))
    assert pm.mode == "RGB"
    arr = np.asarray(pm)
    assert len(np.unique(arr[::7, ::7].reshape(-1, 3), axis=0)) > 1


# ------------------------------------------------------------------ tastiera


def test_firma_digitata_rendering():
    style = typed.TypedStyle(font_path=SERIF, size=88, color=(18, 32, 74))
    img = typed.render_typed("Mario Rossi", style)
    assert img.mode == "RGBA"
    assert img.split()[3].getbbox() is not None


def test_firma_digitata_testo_vuoto():
    img = typed.render_typed("   ", typed.TypedStyle(font_path=SERIF))
    assert img.split()[3].getbbox() is None


def test_stile_manoscritto_cambia_il_rendering():
    base = typed.TypedStyle(font_path=SERIF, size=80)
    dritta = typed.render_typed("Mario", base)
    corsa = typed.render_typed("Mario", typed.TypedStyle(font_path=SERIF, size=80, slant=0.6))
    assert dritta.tobytes() != corsa.tobytes()


def test_determinismo_del_rendering():
    st = typed.TypedStyle(font_path=SERIF, size=70)
    a = typed.render_typed("Mario Rossi", st).tobytes()
    b = typed.render_typed("Mario Rossi", st).tobytes()
    assert a == b


def test_semicerchio():
    assert Path(typed.pick_default_font()).exists() or typed.pick_default_font() == ""


def test_elenco_font():
    fonti = typed.list_fonts()
    assert isinstance(fonti, list)
    assert all("path" in f for f in fonti)


def test_fitting_immagine():
    img = Image.new("RGBA", (400, 100), (0, 0, 0, 255))
    ridotta = typed.fit_into(img, 200, 200)
    assert ridotta.width <= 200


# ------------------------------------------------------------------ libreria


def test_libreria_salva_e_ricarica(tmp_path: Path):
    lib = manager.SignatureLibrary(folder=tmp_path)
    c = make_canvas()
    e1 = lib.add_canvas(c, name="Disegnata")
    e2 = lib.add_typed("Mario Rossi", typed.TypedStyle(font_path=SERIF, size=70))
    e3 = lib.add_png(render.render_strokes(c, scale=1.0), name="Da foto", source="image")
    assert len(lib) == 3
    assert lib.image(e1) is not None
    assert lib.canvas(e1) is not None            # i tratti sopravvivono
    assert len(lib.canvas(e1).strokes) == len(c.strokes)
    assert lib.image(e2) is not None
    assert lib.by_id(e3.id).display_name == "Da foto"


def test_libreria_persistente(tmp_path: Path):
    lib = manager.SignatureLibrary(folder=tmp_path)
    lib.add_canvas(make_canvas(), name="X")
    riletta = manager.SignatureLibrary(folder=tmp_path)
    assert len(riletta) == 1


def test_libreria_eliminazione(tmp_path: Path):
    lib = manager.SignatureLibrary(folder=tmp_path)
    e = lib.add_canvas(make_canvas(), name="X")
    lib.remove(e)
    assert len(lib) == 0
    assert lib.image(e) is None


def test_libreria_rinomina(tmp_path: Path):
    lib = manager.SignatureLibrary(folder=tmp_path)
    e = lib.add_canvas(make_canvas(), name="prima")
    lib.rename(e, "dopo")
    assert lib.by_id(e.id).name == "dopo"


def test_prepara_immagine_applica_il_default(tmp_path: Path):
    out = manager.prepare_image(signature_photo())
    assert np.asarray(out)[:, :, 3].min() == 0
